"""Stream-filter the official FNSPID CSV for this study without loading it into RAM."""
from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path

from research_service.protocol import TICKERS

ALIASES = {
    "Date": ("Date", "date"),
    "Article_title": ("Article_title", "headline"),
    "Stock_symbol": ("Stock_symbol", "symbol"),
    "Url": ("Url", "url"),
    "Publisher": ("Publisher", "publisher"),
}
OUTPUT_COLUMNS = tuple(ALIASES)


def filter_fnspid(input_path, output_path, tickers=TICKERS,
                  start="2020-01-01", end="2026-01-01"):
    start_day, end_day = date.fromisoformat(start), date.fromisoformat(end)
    if start_day >= end_day:
        raise ValueError("start must be earlier than end")
    ticker_set = {ticker.upper() for ticker in tickers}
    if not ticker_set or not ticker_set.issubset(TICKERS):
        raise ValueError("tickers must be from the approved study universe")
    source, target = Path(input_path), Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    counts = {ticker: 0 for ticker in sorted(ticker_set)}
    with source.open("r", encoding="utf-8-sig", newline="") as reader_handle:
        reader = csv.DictReader(reader_handle)
        fields = set(reader.fieldnames or [])
        columns = {key: next((name for name in names if name in fields), None)
                   for key, names in ALIASES.items()}
        if any(columns[key] is None for key in ("Date", "Article_title", "Stock_symbol", "Url")):
            raise ValueError("FNSPID CSV is missing Date, Article_title, Stock_symbol, or Url")
        with target.open("w", encoding="utf-8-sig", newline="") as writer_handle:
            writer = csv.DictWriter(writer_handle, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            for row in reader:
                ticker = str(row.get(columns["Stock_symbol"], "")).strip().upper()
                raw_day = str(row.get(columns["Date"], ""))[:10]
                try:
                    published = date.fromisoformat(raw_day)
                except ValueError:
                    continue
                if ticker in ticker_set and start_day <= published < end_day:
                    writer.writerow({
                        "Date": row.get(columns["Date"], ""),
                        "Article_title": row.get(columns["Article_title"], ""),
                        "Stock_symbol": ticker,
                        "Url": row.get(columns["Url"], ""),
                        "Publisher": row.get(columns["Publisher"], "") if columns["Publisher"] else "",
                    })
                    counts[ticker] += 1
    return {"output": str(target.resolve()), "rows": sum(counts.values()), "by_ticker": counts,
            "start": start, "end_exclusive": end}


def main():
    parser = argparse.ArgumentParser(description="Filter the official FNSPID Stock_news.csv for the v3 study.")
    parser.add_argument("input", help="Path to the original FNSPID Stock_news.csv")
    parser.add_argument("output", help="Path for the filtered CSV")
    parser.add_argument("--tickers", nargs="+", default=list(TICKERS))
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2026-01-01", help="Exclusive end date")
    args = parser.parse_args()
    result = filter_fnspid(args.input, args.output, args.tickers, args.start, args.end)
    print(f"Wrote {result['rows']} rows to {result['output']}")
    for ticker, count in result["by_ticker"].items():
        print(f"{ticker}: {count}")


if __name__ == "__main__":
    main()
