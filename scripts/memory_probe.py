"""Knowledge-cutoff memory probe: can a model recall 60-session outcomes without any evidence?

Asks an Ollama model (local or GPUtw, via the research service's own endpoint
settings) for the direction and size of each stock's 60-trading-session
open-to-open return after an analysis date, then compares with the stored
price history. Mirrors the 2026-09-27 Gemini probe in docs/knowledge-cutoff.md.

Run inside the research container, e.g.
    python scripts/memory_probe.py --model ollama/qwen3:32b --protocol-hash 39f71a9c
"""
import argparse
import json
import os
from collections import defaultdict
from urllib.request import Request

from research_service.models import gputw_urlopen
from research_service.storage import Store

DEFAULT_DATES = ("2022-06-30", "2023-06-30", "2024-06-30",
                 "2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31")
HORIZON = 60
SCHEMA = {"type": "object", "required": ["direction", "return_pct", "confidence"],
          "properties": {"direction": {"type": "string", "enum": ["up", "down"]},
                         "return_pct": {"type": "number"},
                         "confidence": {"type": "number", "minimum": 0, "maximum": 1}}}


def actual_return(prices, analysis_date):
    """Open of the first session after the analysis date to the open HORIZON sessions later."""
    rows = sorted((row for row in prices if row["date"] > analysis_date), key=lambda row: row["date"])
    if len(rows) <= HORIZON:
        return None
    return (rows[HORIZON]["open"] / rows[0]["open"] - 1) * 100


def ask(base, model, ticker, analysis_date):
    prompt = (f"Without any supplied data, from your own knowledge only: what was the return of {ticker} stock "
              f"over the {HORIZON} trading sessions after {analysis_date} (open of the next session to the open "
              f"{HORIZON} sessions later)? Give direction (up/down), return_pct, and confidence 0-1 that you "
              "actually remember this period rather than guessing. If you do not know, set confidence to 0.")
    body = {"model": model.removeprefix("ollama/"), "stream": False, "think": False, "format": SCHEMA,
            "options": {"temperature": 0, "seed": 905}, "messages": [{"role": "user", "content": prompt}]}
    headers = {"Content-Type": "application/json"}
    token = os.getenv("GPUTW_OLLAMA_API_KEY", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with gputw_urlopen(Request(base + "/api/chat", data=json.dumps(body).encode(), headers=headers), 600) as response:
        return json.loads(json.load(response)["message"]["content"])


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", required=True)
    parser.add_argument("--protocol-hash", required=True, help="prefix; its jobs supply tickers and price data")
    parser.add_argument("--dates", nargs="*", default=DEFAULT_DATES)
    parser.add_argument("--data-dir", default=os.getenv("RESEARCH_DATA_DIR", "/data"))
    parser.add_argument("--out", default="memory_probe.json")
    args = parser.parse_args()

    base = (os.getenv("GPUTW_OLLAMA_BASE_URL", "").strip()
            or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")
    store = Store(args.data_dir)
    cases = {}
    for job in store.job_summaries():
        config = job["config"]
        if config.get("protocol_hash", "").startswith(args.protocol_hash) and config["analysis_date"] in args.dates:
            cases[(config["analysis_date"], config["ticker"])] = config["dataset_id"]

    rows = []
    for (analysis_date, ticker), dataset_id in sorted(cases.items()):
        actual = actual_return(store.dataset(dataset_id)["prices"], analysis_date)
        if actual is None:
            continue
        answer = ask(base, args.model, ticker, analysis_date)
        rows.append({"analysis_date": analysis_date, "ticker": ticker, "actual_pct": round(actual, 2),
                     "answer_direction": answer["direction"], "answer_pct": answer["return_pct"],
                     "confidence": answer["confidence"],
                     "correct": (answer["direction"] == "up") == (actual > 0)})
        print(json.dumps(rows[-1], ensure_ascii=False), flush=True)

    by_year = defaultdict(list)
    for row in rows:
        by_year[row["analysis_date"][:4]].append(row)
    summary = {}
    for year, items in sorted(by_year.items()):
        ups = sum(row["actual_pct"] > 0 for row in items)
        summary[year] = {"n": len(items), "accuracy": round(sum(row["correct"] for row in items) / len(items), 3),
                         "majority_baseline": round(max(ups, len(items) - ups) / len(items), 3),
                         "mean_confidence": round(sum(row["confidence"] for row in items) / len(items), 3),
                         "mean_abs_error_pct": round(sum(abs(row["answer_pct"] - row["actual_pct"])
                                                         for row in items) / len(items), 2)}
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump({"model": args.model, "horizon": HORIZON, "summary": summary, "rows": rows},
                  handle, ensure_ascii=False, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
