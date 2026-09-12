#!/usr/bin/env python3
"""
FNSPID 下載 + 篩選腳本（v2，個人早期版本，已由 scripts/prepare_fnspid_news.py 取代）

還原自私人交接備份（曾誤刪，2026-09-13 尋回）。兩者篩選同一份官方原始檔會
得到逐行相同的結果；保留這支只是為了留下當初繞過 datasets 套件 ArrowInvalid
問題的紀錄，日常操作請用 scripts/prepare_fnspid_news.py。

背景：
    Hugging Face 上 Zihan1004/FNSPID 的自動 parquet 轉換有已知 bug
    （ArrowInvalid: 某些欄位混雜了非數值字串），會讓 `datasets` 套件的
    streaming 模式跑到一半直接崩潰。
    改用 GitHub 官方 repo 建議的方式：直接抓原始 CSV，用 pandas 分批處理。

流程：
    Step 1（shell，先手動跑一次，只需跑一次）：
        wget -c https://huggingface.co/datasets/Zihan1004/FNSPID/resolve/main/Stock_news/nasdaq_exteral_data.csv -O raw_stock_news.csv

    Step 2（這支 python 腳本）：
        讀取 raw_stock_news.csv，分批篩選出目標股票，
        輸出成專案根目錄 research-inputs/Stock_news.csv

使用前：
    pip install pandas
"""

import pandas as pd
import os
from pathlib import Path

# ---- 設定區 ----
SCRIPT_DIR = Path(__file__).resolve().parent
RAW_CSV_PATH = SCRIPT_DIR / "raw_stock_news.csv"
OUTPUT_PATH = SCRIPT_DIR.parents[1] / "research-inputs" / "Stock_news.csv"
TICKERS = {"AAPL", "NVDA", "GOOGL", "MSFT", "AMZN", "JPM", "MCD", "LLY", "ASTS", "GE"}
CHUNK_SIZE = 100_000  # 每次讀多少列，CPU-only 機器建議別設太大

# 保留欄位並改名成好讀的名稱
KEEP_COLUMNS = {
    "Date": "date",
    "Stock_symbol": "symbol",
    "Article_title": "headline",
    "Article": "article",
    "Publisher": "publisher",
    "Url": "url",
}
# ----------------


def main():
    if not os.path.exists(RAW_CSV_PATH):
        print(f"❌ 找不到 {RAW_CSV_PATH}，請先執行：")
        print(
            "wget -c https://huggingface.co/datasets/Zihan1004/FNSPID/"
            "resolve/main/Stock_news/nasdaq_exteral_data.csv -O raw_stock_news.csv"
        )
        return

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    print(f"目標股票：{sorted(TICKERS)}")
    print(f"開始分批讀取 {RAW_CSV_PATH} ...")

    matched_chunks = []
    total_rows = 0
    found_tickers = set()

    reader = pd.read_csv(RAW_CSV_PATH, chunksize=CHUNK_SIZE, low_memory=False)

    for i, chunk in enumerate(reader, start=1):
        total_rows += len(chunk)

        filtered = chunk[chunk["Stock_symbol"].isin(TICKERS)]
        if not filtered.empty:
            matched_chunks.append(filtered)
            found_tickers.update(filtered["Stock_symbol"].unique())

        if i % 20 == 0:
            hit_count = sum(len(c) for c in matched_chunks)
            print(
                f"已掃描約 {total_rows:,} 列 | 已命中 {hit_count:,} 筆 | "
                f"已涵蓋 {sorted(found_tickers)}"
            )

    if not matched_chunks:
        print("⚠️ 完全沒有命中任何資料，請確認欄位名稱或股票代號是否正確。")
        return

    df = pd.concat(matched_chunks, ignore_index=True)

    # 只保留需要的欄位並改名
    available_cols = [c for c in KEEP_COLUMNS if c in df.columns]
    df = df[available_cols].rename(columns=KEEP_COLUMNS)

    # 依股票代號、日期排序，方便之後依股票逐一取用
    df = df.sort_values(["symbol", "date"]).reset_index(drop=True)

    df.to_csv(OUTPUT_PATH, index=False)

    print("\n===== 完成 =====")
    print(f"總共命中 {len(df):,} 筆新聞")
    print(f"已存到：{OUTPUT_PATH}")

    missing = TICKERS - found_tickers
    if missing:
        print(f"\n⚠️ 這些股票完全沒找到資料，需要另外補來源：{sorted(missing)}")

    print("\n各股票筆數：")
    print(df["symbol"].value_counts())


if __name__ == "__main__":
    main()
