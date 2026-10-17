"""Isolated RQ2/RQ3 pilot or report bank; offline planning unless --execute.

Example: python scripts/run_design_pilot.py --source-db backup.sqlite3
  --cases pilot.json --output work/new-pilot --mode pilot [--execute]
Credentials and endpoint settings are read from the environment. No registration
is created. Report banks need an explicit seed outside all future formal seeds.
"""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research_service.data import digest, validate_dataset
from research_service.domain_debate import DomainDebateEngine
from research_service.engine import StepFailure
from research_service.reporting import export_job
from research_service.run_manifest import source_fingerprint
from research_service.storage import Store
from research_service.web.context import BatchInput
from research_service.web.jobs import prepare


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def run(args, *, model_call=None):
    """The optional model_call is a test seam, never a command-line option."""
    source = args.source_db.resolve(strict=True)
    if Path(str(source) + "-wal").exists():
        raise ValueError("Use a standalone SQLite backup without WAL")
    source_hash = file_hash(source)
    code_root = Path(__file__).resolve().parents[1]
    code_source = source_fingerprint(code_root)
    runner_hash = file_hash(Path(__file__))
    raw = json.loads(args.cases.read_text(encoding="utf-8-sig"))
    batch = BatchInput.model_validate(raw)
    if len(batch.cases) > (5 if args.mode == "pilot" else 180):
        raise ValueError("pilot allows at most 5 cases; report-bank allows at most 180")
    if len({(c.dataset_id, c.analysis_date) for c in batch.cases}) != len(batch.cases):
        raise ValueError("Duplicate cases are not allowed")
    if args.mode == "report-bank" and (any("inference_seed" not in c for c in raw["cases"])
                                       or len({c.inference_seed for c in batch.cases}) != 1):
        raise ValueError("report-bank requires one explicitly specified bank inference_seed (e.g. 904)")
    for case in batch.cases:
        if case.neutral_report_job_id or case.neutral_report_hash:
            raise ValueError("This isolated runner does not import shared-report source jobs")
        routed = any(getattr(case, key) is not None for key in
                     ("debate_model_a", "debate_model_b", "debate_assignments", "model_endpoints"))
        if args.mode == "report-bank" and (not routed or case.domain_debate is not None):
            raise ValueError("report-bank requires RQ2 router cases")
        if not routed and case.domain_debate is None:
            raise ValueError("Select RQ2 router or RQ3 domain_debate")
        if case.debate_assignments is not None and set(case.debate_assignments) != {"AA", "AB", "BA", "BB"}:
            raise ValueError("RQ2 pilot requires AA/AB/BA/BB")
        if case.domain_debate is not None and (case.domain_debate.get("rule", "fixed") != "fixed"
                                               or case.domain_debate.get("include_controls") is not True):
            raise ValueError("RQ3 pilot requires fixed rule and include_controls=true")
    # Read only selected content. Never open the source with Store/migrations.
    datasets = {}
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
        for case in batch.cases:
            row = db.execute("SELECT content FROM datasets WHERE id=?", (case.dataset_id,)).fetchone()
            if row is None:
                raise ValueError("Selected dataset is absent from source snapshot")
            data = json.loads(row[0])
            if digest(data) != case.dataset_id:
                raise ValueError("Dataset content does not match its ID")
            datasets[case.dataset_id] = validate_dataset(data)
    args.output.mkdir(parents=True, exist_ok=False)
    store = Store(args.output / "data")
    for key, data in datasets.items():
        if store.add_dataset(data) != key:
            raise ValueError("Dataset validation changed content identity")
    ctx = SimpleNamespace(store=store, demo_mode=False, injected_model_call=not args.execute or model_call is not None,
                          demo_model_id="unused")
    manifest = {"schema": "design-pilot/v1", "mode": args.mode, "execute": args.execute,
                "formal_launch_ready": False, "source_database_sha256": source_hash,
                "source": code_source, "runner_sha256": runner_hash,
                "cases_file_sha256": file_hash(args.cases), "cases": [], "status": "preparing",
                "note": "Qualification/report-bank only; no formal registration. Offline mode proves no model qualification."}
    failure = None
    try:
        configs = [prepare(ctx, case) for case in batch.cases]
        for config in configs:
            config["execution_purpose"] = "qualification" if args.mode == "pilot" else "report_bank"
            if not args.execute:
                config.pop("model_identity", None)
                config.pop("routed_model_identities", None)
                config["formal_readiness"] = {"eligible": False, "blockers": ["offline_model_not_verified"]}
        if len({c["protocol_hash"] for c in configs}) != 1:
            raise ValueError("Each run must use one protocol and inference seed")
        engine = (DomainDebateEngine(store, model_call) if model_call else DomainDebateEngine(store)) if args.execute else None
        for index, config in enumerate(sorted(configs, key=lambda c: (c["analysis_date"], c["ticker"]))):
            item = {"config": config, "status": "offline_prepared"}
            manifest["cases"].append(item)
            write_json(args.output / f"case-{index:03d}-config.json", config)
            if not args.execute:
                continue
            job = store.create(config, queued=False)
            item["job_id"] = job["id"]
            try:
                for _ in range(100):
                    if source_fingerprint(code_root) != code_source or file_hash(Path(__file__)) != runner_hash:
                        raise RuntimeError("Code changed during execution; stopped before next checkpoint")
                    try:
                        state = engine.advance(job)
                    except StepFailure as error:
                        store.save_step(job["id"], error.state, error=type(error).__name__)
                        raise
                    if source_fingerprint(code_root) != code_source or file_hash(Path(__file__)) != runner_hash:
                        raise RuntimeError("Code changed during checkpoint; result not accepted")
                    store.save_step(job["id"], state)
                    job = store.get(job["id"])
                    if state.get("finished") or (args.mode == "report-bank" and state.get("report")):
                        break
                else:
                    raise RuntimeError("Exceeded 100 checkpoints; stopped without skipping case")
                if args.mode == "report-bank" and (job["status"] != "paused" or job.get("owner")
                                                    or state.get("records") or state.get("finished")):
                    raise RuntimeError("Report-bank checkpoint is not idle and predecision")
                item.update(status="report_locked" if args.mode == "report-bank" else "complete",
                            neutral_report_job_id=job["id"], neutral_report_hash=state.get("report_hash"))
            except Exception:
                item["status"] = "failed"
                raise
            finally:
                job = store.get(job["id"])
                (args.output / f"case-{index:03d}-export.zip").write_bytes(export_job(job))
        manifest["status"] = "complete" if args.execute else "offline_prepared"
    except Exception as error:
        manifest.update(status="failed", error_type=type(error).__name__)
        failure = error
    finally:
        manifest["source_unchanged"] = file_hash(source) == source_hash
        write_json(args.output / "manifest.json", manifest)
    if not manifest["source_unchanged"]:
        raise RuntimeError("Source snapshot changed during execution")
    if failure is not None:
        raise failure
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", required=True, type=Path)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", choices=("pilot", "report-bank"), default="pilot")
    parser.add_argument("--execute", action="store_true", help="Contact configured models; may incur provider costs")
    args = parser.parse_args()
    try:
        result = run(args)
    except Exception as error:
        parser.exit(1, f"Stopped: {type(error).__name__}; inspect manifest.json if created.\n")
    print(json.dumps({"status": result["status"], "cases": len(result["cases"]), "formal_launch_ready": False}))


if __name__ == "__main__":
    main()
