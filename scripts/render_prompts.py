"""Render the exact prompts one case sends to the model, for review before a registration.

Reads a job from a copy of the database, rebuilds its research inputs under the
current protocol version and writes every distinct prompt (research agents and
one call of each decision kind) to a Markdown file. Never calls a model.

    python scripts/render_prompts.py --db /tmp/copy.sqlite3 --job <id> --out prompts.md
"""
import argparse
import json
from dataclasses import asdict, replace
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research_service.engine import Engine, protocol_from
from research_service.models import alias_messages, messages_for
from research_service.protocol import QUARTERLY_VERSION, decision_plan
from research_service.storage import Store


class Captured(Exception):
    pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--job", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    store = Store(args.db)
    job = store.get(args.job)
    protocol = replace(protocol_from(job["config"]["protocol"]), version=QUARTERLY_VERSION)
    job["config"]["protocol"] = asdict(protocol)
    state = job["state"]
    sections = [f"# 實際 prompt：{job['config']['ticker']} {job['config']['analysis_date']}（協議 {protocol.version}）\n"]

    research = {}

    def capture(_protocol, messages, **kwargs):
        research[threading_name()] = messages
        raise Captured()

    def threading_name():
        import threading
        return threading.current_thread().name + str(len(research))

    engine = Engine(store, capture)
    fresh = {"research": {}, "records": [], "trace": [], "attempts": [],
             "inputs": state["inputs"], "evidence_aliases": state["evidence_aliases"], "memory": state["memory"]}
    try:
        engine.step({"job": job, "state": fresh})
    except Exception:
        pass
    for messages in research.values():
        domain = next((line.split(": ", 1)[1] for line in messages[1]["content"].splitlines() if line.startswith("Domain: ")), "?")
        sections.append(render(f"研究代理人：{domain}", messages, evidence_cut=True))

    report, records = state["report"], list(state["records"])
    # A paused case may stop before D round 1; borrow C's round 1 so the switch prompt shows a history.
    if not any(r["group"] == "D" and r.get("round") == 1 for r in records):
        records += [{**r, "group": "D", "key": r["key"].replace("c-", "d-", 1)} for r in records
                    if r["group"] == "C" and r.get("round") == 1]
    wanted = ["a-decision", "b-sample-1", "c-r1-agent-a", "c-r2-agent-a", "d-r2-agent-a", "c-adjudication"]
    plan = {call.key: call for call in decision_plan(protocol)}
    for key in wanted:
        call = plan[key]
        before = [r for r in records if r.get("round") is None or call.round is None or r["round"] < (call.round or 9)]
        messages = messages_for(call, report, before if call.kind != "decision" else [], state["memory"][call.group], protocol)
        messages = alias_messages(messages, state["evidence_aliases"])
        sections.append(render(f"決策：{key}", messages, evidence_cut=True))
    Path(args.out).write_text("\n".join(sections), encoding="utf-8")
    print("wrote", args.out, len(sections) - 1, "prompts")


def render(title, messages, evidence_cut):
    out = [f"\n## {title}\n"]
    for message in messages:
        text = message["content"]
        if evidence_cut and message["role"] == "user" and len(text) > 6000:
            text = text[:6000] + f"\n…（以下省略 {len(text) - 6000} 字的證據／報告資料）"
        out.append(f"**{message['role']}**\n\n```text\n{text}\n```\n")
    return "\n".join(out)


if __name__ == "__main__":
    main()
