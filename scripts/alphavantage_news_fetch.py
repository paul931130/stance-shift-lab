#!/usr/bin/env python3
"""
Alpha Vantage 新聞抓取腳本 —— 補齊 FNSPID 資料 2023-12 之後到現在的缺口
(v3：支援「每月重跑=自動更新最新資料」，修正月中執行導致當月資料被誤判完成的問題)

還原自私人交接備份（曾誤刪，2026-09-13 尋回）。輸出的 alphavantage_news.csv
現在會被 research_service/data.py 讀取（設定 ALPHA_VANTAGE_NEWS_PATH 指向它），
在打即時 Alpha Vantage API 之前優先查這份本機快取，查得到就不消耗當日額度。
腳本會直接寫入 research-inputs/alphavantage_news.csv，完成後立即可供服務讀取。

背景：
    - FNSPID 最後一筆新聞日期是 2023-12-16，這支腳本從 2023-12-17 開始抓
    - Alpha Vantage 免費版限制：每個 key 每分鐘 5 次、每天 25 次呼叫
    - 為避免熱門股（NVDA/AAPL）單一時間窗新聞量超過 1000 筆上限被截斷，
      按「月份」分窗口逐月抓取
    - 有 checkpoint 機制：已經「完整結束」的月份存進 checkpoint，不會重複抓取
    - 【v3新增】「當月」（還沒結束的月份）永遠不會被存進 checkpoint，每次執行都會：
        1. 先把 CSV 裡舊的「當月」資料刪掉
        2. 重新抓一次「當月1號到今天」的完整資料，覆蓋寫回去
      這樣你之後只要每個月(或每週、每天都行)重跑一次這支腳本，
      就能自動、乾淨地更新到最新資料，不會有資料破洞，也不會重複累積

使用前：
    1. 把下面 API_KEYS 換成你自己的 key
    2. pip install requests

執行：
    python alphavantage_news_fetch.py
    （之後每月固定重跑一次即可自動更新最新一個月的新聞）
"""

import requests
import sys
import time
import json
import os
import csv
from datetime import datetime, timedelta
from pathlib import Path

# Windows' console/redirect encoding is often cp950/cp1252, not UTF-8; the
# emoji in this script's own print() calls (⏸ etc.) crash on that with
# UnicodeEncodeError. Force UTF-8 so a status message can never kill a run
# that already did real, saved work.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def env_file_value(name):
    """Read one value from .env.research without printing or persisting it elsewhere."""
    path = PROJECT_ROOT / ".env.research"
    if not path.exists():
        return ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == name:
            return value.strip().strip('"').strip("'")
    return ""


# Prefer the process environment, then the project's server-side .env file.
# A real key never needs to be hardcoded into this script.
API_KEYS = [
    os.environ.get("ALPHA_VANTAGE_API_KEY")
    or env_file_value("ALPHA_VANTAGE_API_KEY")
    or "YOUR_API_KEY_HERE",
]
TICKERS = ["AAPL", "NVDA", "GOOGL", "MSFT", "AMZN", "JPM", "MCD", "LLY", "GE"]
START_DATE = datetime(2023, 12, 17)  # 接續 FNSPID 最後一筆之後
END_DATE = datetime.now()

RESEARCH_INPUTS_DIR = PROJECT_ROOT / "research-inputs"
CHECKPOINT_FILE = str(RESEARCH_INPUTS_DIR / "av_checkpoint.json")
OUTPUT_FILE = str(RESEARCH_INPUTS_DIR / "alphavantage_news.csv")
DAILY_LIMIT_PER_KEY = 25
DAILY_LIMIT = DAILY_LIMIT_PER_KEY * len(API_KEYS)
CALL_DELAY_SEC = 13  # 每次呼叫之間的間隔，不管用哪組key都保持這個間隔比較安全

CURRENT_MONTH_START = END_DATE.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def month_windows(start, end):
    """把時間範圍切成一個月一個月的 (start, end) 區間"""
    windows = []
    current = start.replace(day=1)
    while current <= end:
        next_month = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
        window_start = max(current, start)
        window_end = min(next_month - timedelta(seconds=1), end)
        windows.append((window_start, window_end))
        current = next_month
    return windows


def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, encoding="utf-8") as f:
            return set(tuple(x) for x in json.load(f))
    return set()


def save_checkpoint(done):
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump([list(x) for x in done], f)


def fetch_news(ticker, time_from, time_to, api_key):
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "NEWS_SENTIMENT",
        "tickers": ticker,
        "time_from": time_from.strftime("%Y%m%dT%H%M"),
        "time_to": time_to.strftime("%Y%m%dT%H%M"),
        "limit": 1000,
        "sort": "EARLIEST",
        "apikey": api_key,
    }
    r = requests.get(url, params=params, timeout=30)
    return r.json()


def safe_api_message(data, api_key):
    """Return a useful provider error without ever echoing the API key."""
    message = next(
        (str(data.get(field, "")) for field in ("Information", "Note", "Error Message") if data.get(field)),
        "Alpha Vantage 回應缺少 feed",
    )
    if api_key:
        message = message.replace(api_key, "[REDACTED]")
    return message


def purge_current_month_rows(ticker, month_str):
    """把 CSV 裡屬於「這檔股票 + 當月」的舊資料先移除，準備覆蓋寫入新的一批"""
    if not os.path.exists(OUTPUT_FILE):
        return
    with open(OUTPUT_FILE, encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        return
    header, body = rows[0], rows[1:]
    yyyymm = month_str.replace("-", "")  # "2026-10" -> "202610"
    kept = [
        row for row in body
        if not (row[1] == ticker and row[0][:6] == yyyymm)
    ]
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(kept)


def main():
    if any(k.startswith("YOUR_API_KEY") for k in API_KEYS):
        print("❌ 請先把 API_KEYS 換成你自己申請的 key。")
        return

    print(f"目前設定 {len(API_KEYS)} 組 key，每日總額度 {DAILY_LIMIT} 次。")
    print(f"當月（{CURRENT_MONTH_START:%Y-%m}）視為進行中，每次執行都會重新抓取覆蓋，不計入 checkpoint。")

    done = {item for item in load_checkpoint() if item[1] < CURRENT_MONTH_START.strftime("%Y-%m")}
    windows = month_windows(START_DATE, END_DATE)
    all_tasks = [(t, w[0], w[1]) for t in TICKERS for w in windows]

    def is_current_month(win_start):
        return win_start >= CURRENT_MONTH_START

    def done_count(ticker):
        return sum(1 for (t, _month) in done if t == ticker)

    # Prioritize tickers with the least history filled in yet, and only
    # re-fetch the still-open current month once every ticker's past-month
    # backlog is caught up — otherwise a ticker that already has data keeps
    # eating the daily quota on repeat current-month overwrites while an
    # empty ticker never gets a turn.
    backlog_tasks = [
        t for t in all_tasks
        if not is_current_month(t[1]) and (t[0], t[1].strftime("%Y-%m")) not in done
    ]
    backlog_tasks.sort(key=lambda t: (done_count(t[0]), t[1]))
    current_tasks = [t for t in all_tasks if is_current_month(t[1])]
    current_tasks.sort(key=lambda t: done_count(t[0]))
    remaining_tasks = backlog_tasks + current_tasks

    print(f"總共需要 {len(all_tasks)} 個「股票×月份」組合，已完成(不含當月) {len(done)} 個，"
          f"這次要處理 {min(DAILY_LIMIT, len(remaining_tasks))} 個。")

    if not remaining_tasks:
        print("\n✅ 全部抓取完成！可以去看 alphavantage_news.csv 了。")
        return

    file_exists = os.path.exists(OUTPUT_FILE)
    calls_today = 0
    key_index = 0

    if not file_exists:
        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["date", "symbol", "headline", "publisher", "url"])

    for ticker, win_start, win_end in remaining_tasks:
        if calls_today >= DAILY_LIMIT:
            print(f"\n⏸ 今天的 {DAILY_LIMIT} 次額度用完了，明天重跑這支腳本會自動接續。")
            break

        api_key = API_KEYS[key_index % len(API_KEYS)]
        key_index += 1
        cur_month = is_current_month(win_start)
        tag = "當月/持續更新" if cur_month else "歷史/一次性"

        print(f"抓取 {ticker} {win_start:%Y-%m} [{tag}] (key #{key_index % len(API_KEYS) + 1}) ...")
        try:
            data = fetch_news(ticker, win_start, win_end, api_key)
        except Exception as e:
            print(f"  ❌ 請求失敗：{e}，跳過這個組合，下次會重試。")
            time.sleep(CALL_DELAY_SEC)
            continue

        calls_today += 1

        if "feed" not in data:
            message = safe_api_message(data, api_key)
            print(f"  ⚠️ 回應異常：{message}")
            if "rate limit" in message.lower() or "requests per day" in message.lower():
                print("  今日 Alpha Vantage 額度已用完；停止本輪，checkpoint 不會把失敗月份標成完成。")
                break
            time.sleep(CALL_DELAY_SEC)
            continue

        if cur_month:
            # 當月：先清掉這檔股票+這個月的舊資料，再整批覆蓋寫入，避免重複累積
            purge_current_month_rows(ticker, win_start.strftime("%Y-%m"))

        with open(OUTPUT_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for item in data["feed"]:
                writer.writerow([
                    item.get("time_published", ""),
                    ticker,
                    item.get("title", ""),
                    item.get("source", ""),
                    item.get("url", ""),
                ])
        print(f"  取得 {len(data['feed'])} 筆" + ("（已覆蓋當月舊資料）" if cur_month else ""))

        if not cur_month:
            done.add((ticker, win_start.strftime("%Y-%m")))
            save_checkpoint(done)

        time.sleep(CALL_DELAY_SEC)

    left = len([t for t in all_tasks if not is_current_month(t[1])]) - len(done)
    print(f"\n本次跑完，歷史部分還剩 {max(left, 0)} 個「股票×月份」組合待抓取。")
    if left > 0:
        print("明天同一時間再重跑一次這支腳本即可繼續補歷史缺口。")
    else:
        print("✅ 歷史缺口已全部補齊。之後只要每月重跑一次，就會自動更新最新月份的新聞。")


if __name__ == "__main__":
    main()
