#!/usr/bin/env python3
"""Fetch only the Alpha Vantage ticker-months that the local news files do not cover.

The monthly experiment (docs/experiment-architecture.md, E3) needs a news window before
every month-end 2021-01 .. 2025-12 for the nine study tickers. Most windows are already
covered by research-inputs/Stock_news.csv (FNSPID) and alphavantage_news.csv, so a blanket
refresh would waste the free key's 25 requests/day. This finds the month-end windows with
no local headline, fetches one calendar month for each such (ticker, month), appends the
rows to alphavantage_news.csv and records the month in av_checkpoint.json, so the run is
resumable and a month that really has no news is not asked for again.

    python scripts/av_backfill_gaps.py --dry-run     # list the gaps
    python scripts/av_backfill_gaps.py               # fetch up to --limit (default 25)

The key is read from ALPHA_VANTAGE_API_KEY or .env.research and is never printed.
"""
import argparse
import bisect
import csv
import os
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research_service.av_archive import (FIELDS, _fetch_month, _load_checkpoint,  # noqa: E402
                                         _safe_provider_message, _save_checkpoint)
from research_service.protocol import STUDY_TICKERS  # noqa: E402

INPUTS = ROOT / "research-inputs"
WINDOW_DAYS = 30
FIRST_MONTH, LAST_MONTH = (2021, 1), (2025, 12)


def read_key():
    key = os.environ.get("ALPHA_VANTAGE_API_KEY", "").strip()
    env_file = ROOT / ".env.research"
    if not key and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("ALPHA_VANTAGE_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("\"'")
    return key


def month_ends():
    year, month = FIRST_MONTH
    while (year, month) <= LAST_MONTH:
        following = date(year + (month == 12), month % 12 + 1, 1)
        yield following - timedelta(days=1)
        year, month = following.year, following.month


def load_dates(path, raw_format):
    """Headline dates per ticker, sorted. Alpha Vantage rows start YYYYMMDD, FNSPID rows are ISO."""
    dates = defaultdict(list)
    if not path.exists():
        return dates
    csv.field_size_limit(10 ** 9)
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            symbol, value = row.get("symbol", "").strip().upper(), row.get("date", "").strip()
            try:
                dates[symbol].append(date(int(value[:4]), int(value[4:6]), int(value[6:8])) if raw_format
                                     else date.fromisoformat(value[:10]))
            except ValueError:
                continue
    for symbol in dates:
        dates[symbol].sort()
    return dates


def find_gaps(checkpoint):
    alpha = load_dates(INPUTS / "alphavantage_news.csv", raw_format=True)
    fnspid = load_dates(INPUTS / "Stock_news.csv", raw_format=False)
    gaps = []
    for anchor in month_ends():
        start = anchor - timedelta(days=WINDOW_DAYS)
        for ticker in STUDY_TICKERS:
            count = sum(bisect.bisect_left(source[ticker], anchor) - bisect.bisect_left(source[ticker], start)
                        for source in (alpha, fnspid))
            month = anchor.strftime("%Y-%m")
            if count == 0 and (ticker, month) not in checkpoint:
                gaps.append((ticker, month))
    return gaps


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, default=25, help="requests to spend this run (free key: 25/day)")
    parser.add_argument("--delay", type=float, default=13.0, help="seconds between requests (free key: 5/min)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    checkpoint_path = INPUTS / "av_checkpoint.json"
    output_path = INPUTS / "alphavantage_news.csv"
    checkpoint = _load_checkpoint(str(checkpoint_path))
    gaps = find_gaps(checkpoint)
    print(f"{len(gaps)} ticker-months have no local headline in their month-end window", flush=True)
    if args.dry_run or not gaps:
        for ticker, month in gaps[:400]:
            print(f"  {ticker} {month}")
        return
    key = read_key()
    if not key:
        raise SystemExit("ALPHA_VANTAGE_API_KEY is not set")

    if not output_path.exists():
        with open(output_path, "w", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerow(FIELDS)
    gaps.sort(key=lambda item: (item[1], item[0]))
    used = added = 0
    for ticker, month in gaps:
        if used >= args.limit:
            print("request budget for this run is spent; run again after the daily quota resets")
            break
        year, mon = map(int, month.split("-"))
        window_start = datetime(year, mon, 1, tzinfo=timezone.utc)
        window_end = datetime(year + (mon == 12), mon % 12 + 1, 1, tzinfo=timezone.utc) - timedelta(minutes=1)
        try:
            payload = _fetch_month(ticker, window_start, window_end, key)
        except Exception as error:
            print(f"{ticker} {month}: request failed ({type(error).__name__}); will retry next run", flush=True)
            time.sleep(args.delay)
            continue
        used += 1
        feed = payload.get("feed") if isinstance(payload, dict) else None
        if feed is None:
            note = _safe_provider_message(payload, key) if isinstance(payload, dict) else "unexpected response"
            print(f"{ticker} {month}: {note[:160]}", flush=True)
            if "rate limit" in note.lower() or "requests per day" in note.lower() or "spreading" in note.lower():
                print("provider quota reached; stopping without marking this month done")
                break
            time.sleep(args.delay)
            continue
        with open(output_path, "a", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            for item in feed:
                writer.writerow([item.get("time_published", ""), ticker, item.get("title", ""),
                                 item.get("source", ""), item.get("url", "")])
        added += len(feed)
        checkpoint.add((ticker, month))
        _save_checkpoint(str(checkpoint_path), checkpoint)
        print(f"{ticker} {month}: {len(feed)} headlines", flush=True)
        time.sleep(args.delay)
    print(f"done: {used} requests, {added} headlines added, {len(find_gaps(checkpoint))} ticker-months still open")


if __name__ == "__main__":
    main()
