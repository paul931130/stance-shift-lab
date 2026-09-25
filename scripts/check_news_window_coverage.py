"""Report how many news rows each study quarter's 90-day window has for one ticker.

Read-only diagnostic for the FNSPID CSV; it never writes.  The window matches
``research_service.data._fnspid_news``: ``[analysis_date - 90 days, analysis_date)``.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
from pathlib import Path

from research_service.protocol import QUARTER_DATES, TICKERS


def window_counts(path, ticker):
    days = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        symbol_column = "symbol" if "symbol" in (reader.fieldnames or []) else "Stock_symbol"
        date_column = "date" if "date" in (reader.fieldnames or []) else "Date"
        for row in reader:
            if str(row.get(symbol_column, "")).strip().upper() == ticker:
                try:
                    days.append(date.fromisoformat(str(row.get(date_column, ""))[:10]))
                except ValueError:
                    continue
    counts = {}
    for analysis_date in QUARTER_DATES:
        anchor = date.fromisoformat(analysis_date)
        start = anchor - timedelta(days=90)
        counts[analysis_date] = sum(start <= day < anchor for day in days)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path")
    parser.add_argument("ticker")
    args = parser.parse_args()
    ticker = args.ticker.upper()
    if ticker not in TICKERS:
        raise SystemExit("ticker must be in the approved study universe")
    for analysis_date, count in window_counts(args.csv_path, ticker).items():
        print(f"{ticker} {analysis_date}: {count}")


if __name__ == "__main__":
    main()
