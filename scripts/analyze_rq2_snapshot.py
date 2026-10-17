"""Offline repeated-seed RQ2 inference from registered jobs in a standalone snapshot."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research_service.data import digest
from research_service.protocol import QUARTER_DATES, STUDY_TICKERS
from research_service.rq_repeats import rq2_repeated_inference
from research_service.rq_study import rq2_study_report, select_cases
from research_service.run_manifest import source_fingerprint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", required=True, type=Path)
    parser.add_argument("--protocol-hashes", required=True, nargs="+")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--date-block-length", type=int, required=True)
    parser.add_argument("--daily-block-length", type=int, default=20)
    args = parser.parse_args()
    source = args.source_db.resolve(strict=True)
    if len(set(args.protocol_hashes)) < 3 or Path(str(source) + "-wal").exists():
        raise ValueError("Use at least three seed protocols and a standalone SQLite backup without WAL")
    correct, dates, returns, trading_days, provenance = {}, {}, {}, {}, []
    reference, reports, dataset_map, model_weights = None, None, None, None
    with sqlite3.connect(source.as_uri() + "?mode=ro&immutable=1", uri=True) as db:
        db.row_factory = sqlite3.Row
        for protocol_hash in args.protocol_hashes:
            registration = db.execute("SELECT * FROM preregistrations WHERE protocol_hash=?", (protocol_hash,)).fetchone()
            if registration is None:
                raise ValueError("Every seed protocol must have its own prior registration")
            ids = json.loads(registration["dataset_ids"])
            jobs = [{**dict(row), "config": json.loads(row["config"]), "state": json.loads(row["state"])}
                    for row in db.execute("SELECT * FROM jobs WHERE json_extract(config,'$.protocol_hash')=?", (protocol_hash,))]
            kwargs = {"eligible_dataset_ids": ids, "frozen_at": registration["frozen_at"]}
            selected, excluded = select_cases(jobs, **kwargs)
            scored = rq2_study_report(jobs, **kwargs)
            if len(selected) != 180 or scored["cases"] != 180 or len(set(ids)) != 180:
                raise ValueError("All 180 registered cases must have complete AA/AB/BA/BB outcomes")
            protocol = dict(selected[0]["config"]["protocol"])
            if protocol.get("version") != "v3-1015.1":
                raise ValueError("Use the condition-isolated-memory RQ2 protocol v3-1015.1")
            seed = protocol.pop("inference_seed")
            if seed in correct:
                raise ValueError("Duplicate inference seeds are not independent repeats")
            if reference is not None and protocol != reference:
                raise ValueError("Only the inference seed may vary between protocol configurations")
            reference = protocol
            case_map = {f"{j['config']['ticker']}:{j['config']['analysis_date']}": j for j in selected}
            if {(j["config"]["ticker"], j["config"]["analysis_date"]) for j in selected} != {
                    (ticker, day) for ticker in STUDY_TICKERS for day in QUARTER_DATES}:
                raise ValueError("Require the complete registered 9x20 stock/date grid")
            current_reports = {key: job["state"].get("report_hash") for key, job in case_map.items()}
            current_data = {key: job["config"]["dataset_id"] for key, job in case_map.items()}
            current_weights = {key: value.get("digest")
                               for key, value in selected[0]["config"].get("routed_model_identities", {}).items()}
            if not current_weights or any(not value for value in current_weights.values()):
                raise ValueError("All routed model digests must be frozen")
            if model_weights is not None and current_weights != model_weights:
                raise ValueError("Model weights changed across seeds")
            model_weights = current_weights
            if reports is not None and (current_reports != reports or current_data != dataset_map):
                raise ValueError("Seeds must reuse identical frozen reports and datasets; do not pool regenerated inputs")
            reports, dataset_map = current_reports, current_data
            if any(not value for value in reports.values()):
                raise ValueError("Missing locked neutral-report identity")
            for dataset_id in ids:
                row = db.execute("SELECT content FROM datasets WHERE id=?", (dataset_id,)).fetchone()
                if row is None or digest(json.loads(row[0])) != dataset_id:
                    raise ValueError("Dataset content hash does not match registration")
            correct[seed], dates[seed] = {}, {}
            daily = {}
            for key, job in case_map.items():
                state = job["state"]
                if digest(state.get("report")) != state.get("report_hash"):
                    raise ValueError("Neutral Report content hash mismatch")
                if state.get("memory_audit", {}).get("pending_earlier_cases"):
                    raise ValueError("Earlier unresolved cases affected frozen memory")
                required_memories = {"C", "D", "C@AB", "D@AB", "C@BA", "D@BA", "C@BB", "D@BB"}
                if not required_memories <= state.get("memory", {}).keys():
                    raise ValueError("Missing independently frozen condition-memory lists")
                for arm, memory in state.get("memory", {}).items():
                    if any(row.get("group") != arm or row.get("protocol_hash") != protocol_hash
                           or row.get("ticker") != job["config"]["ticker"] or row.get("horizon") != 60
                           or row.get("cost_model") != "corwin_schultz" or row.get("decision_layer") != "gated"
                           or row.get("degraded") not in (0, False)
                           or row.get("analysis_date", "9999") >= job["config"]["analysis_date"]
                           or row.get("maturity_date", "9999") >= job["config"]["analysis_date"] for row in memory):
                        raise ValueError("Cross-condition or immature memory in the exported run")
                rows = [*state.get("cases", []), *state.get("routed_cases", [])]
                correct[seed][key] = {(r["group"] if "@" in r["group"] else f"{r['group']}@AA"): r["correct"]
                                      for r in rows if r.get("horizon") == 60 and r.get("cost_model") == "corwin_schultz"
                                      and r.get("decision_layer") == "candidate" and r.get("group", "").startswith(("C", "D"))}
                dates[seed][key] = job["config"]["analysis_date"]
                seen = {}
                for row in [*state.get("daily", []), *state.get("routed_daily", [])]:
                    if row.get("horizon") != 60 or row.get("cost_model") != "corwin_schultz" or row.get("decision_layer") != "candidate":
                        continue
                    group = row["group"] if "@" in row["group"] else f"{row['group']}@AA"
                    if not group.startswith(("C", "D")):
                        continue
                    if row["date"] in seen.setdefault(group, set()):
                        raise ValueError("Duplicate daily row for one case/arm")
                    seen[group].add(row["date"])
                    day = daily.setdefault(row["date"], {})
                    day[group] = day.get(group, 0.) + row["return"] / 180
                if len(seen) != 8 or len({tuple(sorted(days)) for days in seen.values()}) != 1:
                    raise ValueError("Incomplete per-case daily panel across arms")
            trading_days[seed] = sorted(daily)
            arms = [f"{g}@{a}" for a in ("AA", "AB", "BA", "BB") for g in "CD"]
            returns[seed] = {arm: np.asarray([daily[day].get(arm, 0.) for day in trading_days[seed]]).tolist() for arm in arms}
            provenance.append({"seed": seed, "protocol_hash": protocol_hash, "registered_at": registration["frozen_at"],
                               "job_ids": [j["id"] for j in selected], "excluded": excluded})
    result = rq2_repeated_inference(correct, dates, returns, trading_days,
                                    date_block_length=args.date_block_length, daily_block_length=args.daily_block_length)
    result["provenance"] = provenance
    result["source"] = source_fingerprint(Path(__file__).resolve().parents[1])
    result["report_manifest_hash"] = digest(reports)
    result["dataset_manifest_hash"] = digest(dataset_map)
    result["model_digests"] = model_weights
    with source.open("rb") as stream:
        result["source_database_sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
    result["analysis_cli_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
