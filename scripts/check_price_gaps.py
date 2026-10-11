"""Read-only check for holes in stored price bars around each case's analysis date.

The backtest counts the holding period in stored bars (``backtest.evaluate``), so a
missing trading day silently moves the entry later or stretches the horizon. That
module is part of the protocol hash and is left unchanged; this script reports the
affected cases instead, before or after a run.

A bar sequence is flagged when, inside the window the backtest uses (the spread
window before the analysis date and the longest horizon after it):
  * two consecutive bars are more than MAX_CALENDAR_GAP days apart (a long weekend
    plus a holiday is at most 4), or
  * a date that most other tickers in the same store have is missing for this one.

Usage (from the repo root):
    python scripts/check_price_gaps.py research-data
    python scripts/check_price_gaps.py research-data-native --horizon 90 --json gaps.json
Exit code 1 when any case is flagged.
"""
import argparse
from collections import Counter
from datetime import date
import json
from pathlib import Path
import sqlite3
import sys

MAX_CALENDAR_GAP = 4
SPREAD_WINDOW = 20


def _read_rows(uri):
    db = sqlite3.connect(uri, uri=True)
    try:
        return db.execute("SELECT id, ticker, content FROM datasets").fetchall()
    finally:
        db.close()


def load_datasets(store):
    path = Path(store) / "research.sqlite3"
    if not path.is_file():
        sys.exit(f"找不到資料庫：{path}")
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    try:
        rows = _read_rows(uri)
    except sqlite3.OperationalError:
        # A WAL database on a read-only mount (e.g. a Docker volume mounted :ro) cannot
        # create its -shm file; immutable mode reads the main file without it.
        print("注意：資料庫位於唯讀位置，改以 immutable 模式讀取（尚未 checkpoint 的 WAL 內容不會納入）")
        rows = _read_rows(uri + "&immutable=1")
    datasets = []
    for key, ticker, content in rows:
        data = json.loads(content)
        when = data.get("requested_analysis_date") or data.get("analysis_date")
        bars = sorted(bar["date"] for bar in data.get("prices", []) if bar.get("date"))
        if when and bars and data.get("kind") != "synthetic":
            datasets.append({"id": key, "ticker": ticker, "analysis_date": when, "dates": bars})
    return datasets


def window(dates, analysis_date, horizon):
    past = [d for d in dates if d < analysis_date][-(SPREAD_WINDOW + 1):]
    future = [d for d in dates if d > analysis_date][:horizon + 1]
    return past + future


def check(datasets, horizon):
    # How many tickers have a bar on each date: the store's own trading calendar.
    tickers_by_date = Counter()
    for ticker in {d["ticker"] for d in datasets}:
        dates = set().union(*(set(d["dates"]) for d in datasets if d["ticker"] == ticker))
        tickers_by_date.update(dates)
    ticker_count = len({d["ticker"] for d in datasets})
    flagged = []
    for data in datasets:
        span = window(data["dates"], data["analysis_date"], horizon)
        if len(span) < 2:
            continue
        problems = []
        for earlier, later in zip(span, span[1:]):
            days = (date.fromisoformat(later) - date.fromisoformat(earlier)).days
            if days > MAX_CALENDAR_GAP:
                problems.append(f"{earlier} → {later} 相隔 {days} 天")
        have = set(data["dates"])
        if ticker_count >= 3:
            peers_expected = [d for d, n in tickers_by_date.items()
                              if span[0] <= d <= span[-1] and d not in have and n > ticker_count / 2]
            problems.extend(f"缺 {d}（其他股票有）" for d in sorted(peers_expected))
        future = [d for d in data["dates"] if d > data["analysis_date"]]
        if len(future) < horizon + 1:
            problems.append(f"分析日後只有 {len(future)} 根 K 線，不足 {horizon + 1}（回測會標為 pending）")
        if problems:
            flagged.append({**{k: data[k] for k in ("id", "ticker", "analysis_date")}, "problems": problems})
    return flagged


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("store", help="資料目錄，例如 research-data")
    parser.add_argument("--horizon", type=int, default=90, help="檢查到的最長持有期（交易日），預設 90")
    parser.add_argument("--json", help="另存結果為 JSON")
    args = parser.parse_args(argv)
    datasets = load_datasets(args.store)
    flagged = check(datasets, args.horizon)
    print(f"檢查 {len(datasets)} 個資料集（{len({d['ticker'] for d in datasets})} 檔股票），"
          f"發現 {len(flagged)} 個有缺口")
    for item in flagged:
        print(f"- {item['ticker']} {item['analysis_date']}（{item['id'][:12]}）")
        for problem in item["problems"][:8]:
            print(f"    {problem}")
        if len(item["problems"]) > 8:
            print(f"    …另有 {len(item['problems']) - 8} 項")
    if args.json:
        Path(args.json).write_text(json.dumps(flagged, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
