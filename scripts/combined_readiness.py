"""Recompute the 180-case readiness from several SQLite stores (read-only copies).

Each store is copied through SQLite's backup API first, so a running service's
database is never opened for writing.  Datasets are merged by id.
"""
from __future__ import annotations

import argparse
import sqlite3
import tempfile
from collections import Counter
from pathlib import Path

from research_service.readiness import study_readiness
from research_service.storage import Store


def load_datasets(database_file):
    with tempfile.TemporaryDirectory() as directory:
        source = sqlite3.connect(f"file:{Path(database_file).resolve().as_posix()}?mode=ro", uri=True)
        copy = sqlite3.connect(Path(directory) / "research.sqlite3")
        source.backup(copy)
        source.close()
        copy.close()
        return Store(directory).datasets()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("databases", nargs="+", help="research.sqlite3 files to merge")
    args = parser.parse_args()
    merged = {}
    for database in args.databases:
        rows = load_datasets(database)
        print(f"{database}: {len(rows)} datasets")
        merged.update({row["id"]: row for row in rows})
    report = study_readiness(list(merged.values()))
    print(f"\nmerged datasets: {len(merged)}")
    print(f"target cases: {report['target_cases']}  formal-ready: {report['formal_experiment_ready_cases']}  "
          f"partial: {report['partial_cases']}  missing: {report['missing_cases']}")
    print("\nper ticker (ready/total):")
    per_ticker = Counter()
    totals = Counter()
    blockers = Counter()
    for case in report["cases"]:
        totals[case["ticker"]] += 1
        if not case.get("formal_blockers"):
            per_ticker[case["ticker"]] += 1
        for blocker in case.get("formal_blockers", []):
            blockers[blocker] += 1
    for ticker in sorted(totals):
        print(f"  {ticker}: {per_ticker[ticker]}/{totals[ticker]}")
    print("\nblockers:", dict(blockers) or "none")
    for name, split in report.get("temporal_splits", {}).get("splits", {}).items():
        print(f"split {name}: {split.get('formal_ready_cases')}/{split.get('target_cases')}")


if __name__ == "__main__":
    main()
