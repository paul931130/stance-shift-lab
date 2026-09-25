"""Collect one ticker's quarterly datasets by calling the service's own download API.

This adds no collection logic: each quarter is one ``POST /api/datasets/download``,
exactly what the web form and ``research.ps1 collect`` send.  News is read only
from the local FNSPID file and Alpha Vantage cache (``offline_news_only``), so a
re-run is deterministic and never spends live API quota.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

from research_service.protocol import QUARTER_DATES, TICKERS


def collect(base_url, ticker, analysis_date, refresh=False, use_finbert=False, timeout=1800):
    body = json.dumps({"ticker": ticker, "analysis_date": analysis_date, "refresh": refresh,
                       "use_finbert": use_finbert, "offline_news_only": True}).encode()
    request = urllib.request.Request(base_url.rstrip("/") + "/api/datasets/download", data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def summarize(result):
    agents = result.get("agents", {})
    parts = [f"{name}={agent.get('status')}:{agent.get('records')}" for name, agent in agents.items()]
    return ("reused " if result.get("reused") else "new    ") + " ".join(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ticker")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--dates", nargs="+", default=list(QUARTER_DATES))
    parser.add_argument("--refresh", action="store_true", help="build new snapshots even if a complete one exists")
    parser.add_argument("--finbert", action="store_true", help="score headlines with FinBERT after collecting")
    args = parser.parse_args()
    ticker = args.ticker.upper()
    if ticker not in TICKERS:
        raise SystemExit("ticker must be in the approved study universe")
    failures = 0
    for analysis_date in args.dates:
        try:
            result = collect(args.base_url, ticker, analysis_date, args.refresh, args.finbert)
            print(f"{ticker} {analysis_date}: {summarize(result)}", flush=True)
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            failures += 1
            print(f"{ticker} {analysis_date}: FAILED {type(error).__name__}: {error}", flush=True)
    print(f"done: {len(args.dates) - failures}/{len(args.dates)} quarters collected", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
