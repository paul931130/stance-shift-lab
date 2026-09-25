"""Print one ticker's per-quarter formal-readiness verdict from a running service.

Read-only: it only calls ``GET /api/readiness`` and never changes stored data.
"""
from __future__ import annotations

import argparse
import json
import urllib.request
from collections import Counter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ticker")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    ticker = args.ticker.upper()
    with urllib.request.urlopen(args.base_url.rstrip("/") + "/api/readiness", timeout=120) as response:
        report = json.load(response)
    cases = [case for case in report["cases"] if case["ticker"] == ticker]
    blockers = Counter()
    for case in cases:
        verdict = "READY" if not case.get("formal_blockers") else "BLOCKED " + ",".join(case["formal_blockers"])
        for blocker in case.get("formal_blockers", []):
            blockers[blocker] += 1
        print(f"{ticker} {case['analysis_date']} [{case.get('split')}] {verdict} "
              f"(base-rate windows {case.get('base_rate_windows')}, "
              f"news {case.get('domains', {}).get('sentiment')})")
    ready = sum(not case.get("formal_blockers") for case in cases)
    print(f"\n{ticker}: {ready}/{len(cases)} cases formal-ready; blockers: {dict(blockers) or 'none'}")


if __name__ == "__main__":
    main()
