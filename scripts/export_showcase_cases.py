"""Export a few completed RQ1 cases from a read-only database copy for the public showcase page.

Only model outputs, evidence labels and the 60-day backtest outcome are exported; no prompts,
raw provider responses, keys or local paths.
"""
import argparse
import json
import sqlite3
from pathlib import Path

CASES = [("INTC", "2024-03-31"), ("AAPL", "2023-03-31")]
PROTOCOL = "v3-1002.3"


def outcome(cases, group):
    for case in cases:
        if (case["group"] == group and case["horizon"] == 60 and case["cost_model"] == "corwin_schultz"
                and case["decision_layer"] == "candidate"):
            return {"action": case["action"], "move_pct": round(case["realized_move_pct"], 1),
                    "net_return_pct": round(case["net_return"] * 100, 1), "correct": case["correct"],
                    "entry_date": case["entry_date"], "maturity_date": case["maturity_date"]}
    return None


def export(db, out):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    result = []
    for ticker, date in CASES:
        row = con.execute(
            "select state from jobs where status='complete' and json_extract(config,'$.ticker')=? "
            "and json_extract(config,'$.analysis_date')=? and json_extract(config,'$.protocol.version')=?",
            (ticker, date, PROTOCOL)).fetchone()
        state = json.loads(row[0])
        aliases = state.get("evidence_aliases") or {}
        evidence = [{"id": aliases.get(e["evidence_id"], e["evidence_id"]), "domain": e["domain"],
                     "claim": e["claim"]} for e in state["report"]["evidence"]]
        records = [{"group": r["group"], "kind": r["kind"], "agent": r.get("agent"), "stance": r.get("stance"),
                    "round": r.get("round"), "sample": r.get("sample"), "action": r["output"].get("action"),
                    "expected_return_pct": r["output"].get("expected_return_pct"),
                    "confidence": r["output"].get("confidence"), "rationale": r["output"].get("rationale", ""),
                    "evidence_ids": r["output"].get("evidence_ids", [])}
                   for r in state["records"]]
        result.append({
            "ticker": ticker, "analysis_date": date, "protocol": PROTOCOL,
            "research": {k: {"status": v.get("status"), "summary": v.get("summary", "")}
                         for k, v in state["research"].items()},
            "evidence": evidence, "records": records,
            "decisions": {g: {"action": d["action"], "expected_return_pct": d.get("expected_return_pct"),
                              "confidence": d.get("confidence"), "rationale": d.get("rationale", ""),
                              "vote_distribution": d.get("vote_distribution")}
                          for g, d in state["decisions"].items()},
            "outcome": {g: outcome(state["cases"], g) for g in "ABCD"},
        })
    Path(out).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"exported {len(result)} cases to {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--out", default="work/showcase-cases.json")
    args = parser.parse_args()
    export(args.db, args.out)
