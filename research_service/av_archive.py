"""Background-refreshable local archive of Alpha Vantage NEWS_SENTIMENT headlines.

Building this ahead of time lets fetch_sentiment() satisfy a ticker/date
window from disk (free) instead of a metered live call. Mirrors
scripts/alphavantage_news_fetch.py's month-window design (current month is
always re-fetched and overwritten; earlier months are fetched once and
checkpointed) so the two stay interchangeable; this is the version the web
UI's background task calls, writing into the server's own data directory
rather than requiring a terminal.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import csv
import json
import os
import time
from urllib.parse import urlencode

from .data import get_json
from .protocol import STUDY_TICKERS

FIELDS = ("date", "symbol", "headline", "publisher", "url")
DEFAULT_DAILY_LIMIT = 25
DEFAULT_CALL_DELAY = 13
DEFAULT_START_DATE = datetime(2023, 12, 17, tzinfo=timezone.utc)


def default_archive_dir():
    return Path(os.getenv("RESEARCH_DATA_DIR", "research-data")) / "alpha_vantage_cache"


def default_archive_path():
    return default_archive_dir() / "alphavantage_news.csv"


def default_checkpoint_path():
    return default_archive_dir() / "av_checkpoint.json"


def month_windows(start, end):
    """Split [start, end] into one (window_start, window_end) pair per calendar month."""
    windows = []
    current = start.replace(day=1)
    while current <= end:
        next_month = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
        window_start = max(current, start)
        window_end = min(next_month - timedelta(seconds=1), end)
        windows.append((window_start, window_end))
        current = next_month
    return windows


def _fetch_month(ticker, window_start, window_end, api_key, requester=get_json):
    query = urlencode({
        "function": "NEWS_SENTIMENT", "tickers": ticker,
        "time_from": window_start.strftime("%Y%m%dT%H%M"),
        "time_to": window_end.strftime("%Y%m%dT%H%M"),
        "limit": 1000, "sort": "EARLIEST", "apikey": api_key,
    })
    return requester("https://www.alphavantage.co/query?" + query)


def _load_checkpoint(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            return set(tuple(item) for item in json.load(handle))
    return set()


def _save_checkpoint(path, done):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump([list(item) for item in done], handle)


def _purge_current_month_rows(output_path, ticker, month_str):
    """Drop this ticker's rows for the still-open month before re-appending them."""
    if not os.path.exists(output_path):
        return
    with open(output_path, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        return
    header, body = rows[0], rows[1:]
    yyyymm = month_str.replace("-", "")
    kept = [row for row in body if not (len(row) > 1 and row[1] == ticker and row[0][:6] == yyyymm)]
    with open(output_path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(kept)


def refresh_archive(output_path=None, checkpoint_path=None, tickers=STUDY_TICKERS, start_date=None,
                     end_date=None, daily_limit=DEFAULT_DAILY_LIMIT, call_delay=DEFAULT_CALL_DELAY,
                     requester=get_json, progress=None, sleep=time.sleep):
    """Fetch/refresh the local Alpha Vantage headline archive for `tickers`.

    Stops after `daily_limit` new (successfully attempted) calls and reports
    stage="rate_limited" rather than raising, since Alpha Vantage's free tier
    exhausting is an expected, resumable stopping point, not a failure.
    """
    def report(**kwargs):
        if progress:
            progress(**kwargs)

    api_key = os.getenv("ALPHA_VANTAGE_API_KEY", "").strip()
    if not api_key:
        raise ValueError("尚未設定 ALPHA_VANTAGE_API_KEY")

    output_path = str(output_path or default_archive_path())
    checkpoint_path = str(checkpoint_path or default_checkpoint_path())
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    end = end_date or datetime.now(timezone.utc)
    start = start_date or DEFAULT_START_DATE
    current_month_start = end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def is_current_month(window_start):
        return window_start >= current_month_start

    done = _load_checkpoint(checkpoint_path)
    windows = month_windows(start, end)
    all_tasks = [(ticker, *window) for ticker in tickers for window in windows]
    remaining = [task for task in all_tasks
                 if is_current_month(task[1]) or (task[0], task[1].strftime("%Y-%m")) not in done]

    report(stage="running", completed=0, total=min(daily_limit, len(remaining)),
           message=f"共 {len(all_tasks)} 個股票×月份組合，待處理 {len(remaining)} 個")

    if not os.path.exists(output_path):
        with open(output_path, "w", newline="", encoding="utf-8-sig") as handle:
            csv.writer(handle).writerow(FIELDS)

    calls_used, added_rows = 0, 0
    for index, (ticker, window_start, window_end) in enumerate(remaining):
        if calls_used >= daily_limit:
            report(stage="rate_limited", completed=index, total=len(remaining),
                   message=f"今日額度（{daily_limit} 次）已用完，明天重新開始即可繼續")
            return {"status": "rate_limited", "added_rows": added_rows, "remaining": len(remaining) - index}
        month_str = window_start.strftime("%Y-%m")
        report(stage="running", completed=index, total=len(remaining), current=f"{ticker} {month_str}")
        try:
            payload = _fetch_month(ticker, window_start, window_end, api_key, requester)
        except Exception as error:
            report(stage="running", completed=index, total=len(remaining),
                   message=f"{ticker} {month_str} 請求失敗：{type(error).__name__}")
            sleep(call_delay)
            continue
        calls_used += 1
        feed = payload.get("feed") if isinstance(payload, dict) else None
        if feed is None:
            note = payload.get("Information") or payload.get("Note") or payload.get("Error Message") or "回應格式異常"
            report(stage="running", completed=index, total=len(remaining),
                   message=f"{ticker} {month_str}：{note}")
            sleep(call_delay)
            continue
        current_month = is_current_month(window_start)
        if current_month:
            _purge_current_month_rows(output_path, ticker, month_str)
        with open(output_path, "a", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            for item in feed:
                writer.writerow([item.get("time_published", ""), ticker, item.get("title", ""),
                                 item.get("source", ""), item.get("url", "")])
        added_rows += len(feed)
        if not current_month:
            done.add((ticker, month_str))
            _save_checkpoint(checkpoint_path, done)
        sleep(call_delay)

    report(stage="complete", completed=len(remaining), total=len(remaining),
           message=f"本輪新增 {added_rows} 筆，已無待處理組合" if remaining else "已無待處理組合")
    return {"status": "complete", "added_rows": added_rows, "remaining": 0}
