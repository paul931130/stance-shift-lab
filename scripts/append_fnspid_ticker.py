"""Append one approved ticker's rows from the official FNSPID CSV to the filtered study CSV.

Why append instead of re-filtering: the other tickers' rows in ``Stock_news.csv``
stay byte-identical, so datasets collected from them remain reproducible.  The
source may be the plain CSV or a zip that contains it (streamed, never unpacked).
"""
from __future__ import annotations

import argparse
import csv
import io
import shutil
import sys
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path

from research_service.protocol import TICKERS

ALIASES = {
    "date": ("Date", "date"),
    "symbol": ("Stock_symbol", "symbol"),
    "headline": ("Article_title", "headline"),
    "article": ("Article", "article"),
    "publisher": ("Publisher", "publisher"),
    "url": ("Url", "url"),
}


def _column(fields, names):
    return next((name for name in names if name in fields), None)


def _open_source(source, member=None):
    path = Path(source)
    if path.suffix.lower() != ".zip":
        return path.open("r", encoding="utf-8-sig", newline="")
    archive = zipfile.ZipFile(path)
    if member is None:
        candidates = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(candidates) != 1:
            raise ValueError(f"zip must contain exactly one CSV or --member must be given: {candidates}")
        member = candidates[0]
    return io.TextIOWrapper(archive.open(member), encoding="utf-8-sig", newline="")


def _existing_symbols(target):
    with Path(target).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        column = _column(set(reader.fieldnames or []), ALIASES["symbol"])
        if column is None:
            raise ValueError("target CSV has no symbol column")
        return {str(row.get(column, "")).strip().upper() for row in reader}


def append_tickers(source, target, tickers, member=None, progress_every=2_000_000):
    wanted = {ticker.upper() for ticker in tickers}
    if not wanted or not wanted.issubset(TICKERS):
        raise ValueError("tickers must be from the approved study universe")
    target_path = Path(target)
    present = wanted & _existing_symbols(target_path)
    if present:
        raise ValueError(f"target already contains {sorted(present)}; remove those rows first")
    with target_path.open("r", encoding="utf-8-sig", newline="") as handle:
        target_fields = next(csv.reader(handle))
    csv.field_size_limit(10_000_000)
    rows, scanned = [], 0
    with _open_source(source, member) as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        columns = {key: _column(fields, names) for key, names in ALIASES.items()}
        if any(columns[key] is None for key in ("date", "symbol", "headline", "url")):
            raise ValueError("source CSV is missing Date, Stock_symbol, Article_title, or Url")
        for row in reader:
            scanned += 1
            if progress_every and scanned % progress_every == 0:
                print(f"...{scanned:,} rows scanned, {len(rows):,} kept", file=sys.stderr, flush=True)
            symbol = str(row.get(columns["symbol"], "")).strip().upper()
            if symbol in wanted:
                rows.append({key: (row.get(column, "") if column else "") for key, column in columns.items()}
                            | {"symbol": symbol})
    rows.sort(key=lambda item: (item["symbol"], str(item["date"])))
    backup = target_path.with_name(f"{target_path.name}.before-append-{datetime.now():%Y%m%d}.csv")
    shutil.copyfile(target_path, backup)
    with target_path.open("rb") as handle:
        handle.seek(-1, 2)
        needs_newline = handle.read(1) not in (b"\n", b"\r")
    with target_path.open("a", encoding="utf-8", newline="") as handle:
        if needs_newline:
            handle.write("\n")
        writer = csv.DictWriter(handle, fieldnames=target_fields, extrasaction="ignore")
        writer.writerows(rows)
    by_year = Counter((item["symbol"], str(item["date"])[:4]) for item in rows)
    return {"scanned": scanned, "appended": len(rows), "backup": str(backup),
            "by_symbol_year": {f"{symbol}:{year}": count for (symbol, year), count in sorted(by_year.items())}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="Official FNSPID CSV, or a zip containing it")
    parser.add_argument("target", help="Filtered study CSV to append to (research-inputs/Stock_news.csv)")
    parser.add_argument("--ticker", action="append", required=True, help="Approved ticker; repeatable")
    parser.add_argument("--member", help="CSV name inside the zip (optional if it holds one CSV)")
    args = parser.parse_args()
    result = append_tickers(args.source, args.target, args.ticker, args.member)
    print(f"Appended {result['appended']} rows after scanning {result['scanned']:,}; backup: {result['backup']}")
    for key, count in result["by_symbol_year"].items():
        print(f"{key}: {count}")


if __name__ == "__main__":
    main()
