"""Freeze a 9x20 frame; optionally run ONE case in its own DB. Never enqueue a batch."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace
from uuid import uuid4
import zipfile

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research_service.canary import run_model_canary
from research_service.data import digest
from research_service.engine import Engine, protocol_from
from research_service.model_identity import ModelIdentityError, verify_model_identity
from research_service.protocol import QUARTERLY_VERSION
from research_service.reporting import export_job
from research_service.readiness import coverage
from research_service.run_manifest import assert_manifest_source, build_manifest, qualification_verdict
from research_service.storage import Store
from research_service.web.context import JobInput
from research_service.web.jobs import prepare


def write_json(path, value, *, exclusive=False):
    with path.open("x" if exclusive else "w", encoding="utf-8") as output:
        json.dump(value, output, ensure_ascii=False, indent=2, allow_nan=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", required=True, type=Path)
    parser.add_argument("--registration-hash", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--run-one", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if output == args.source_db.resolve().parent or args.source_db.resolve().is_relative_to(output):
        raise ValueError("驗證輸出不能是來源正式資料庫的目錄")
    output.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    # Only accept a standalone SQLite backup, never an active WAL database.
    if Path(str(args.source_db) + "-wal").exists():
        raise ValueError("請先用 SQLite backup 建立獨立快照，不能直接讀取活動資料庫")
    with sqlite3.connect(args.source_db.resolve().as_uri() + "?mode=ro&immutable=1", uri=True) as db:
        [content] = db.execute("SELECT cases FROM preregistration_cases WHERE protocol_hash=?",
                               (args.registration_hash,)).fetchone()
        requests = json.loads(content)
        [content] = db.execute("SELECT config FROM jobs WHERE json_extract(config,'$.protocol_hash')=? LIMIT 1",
                               (args.registration_hash,)).fetchone()
        original = json.loads(content)
        protocol = protocol_from({**original["protocol"], "version": QUARTERLY_VERSION,
                                  "anonymize_ticker": True, "action_source": "model"})
        cases = []
        for request in requests:
            ticker, content = db.execute("SELECT ticker,content FROM datasets WHERE id=?", (request["dataset_id"],)).fetchone()
            dataset = json.loads(content)
            if digest(dataset) != request["dataset_id"]:
                raise ValueError("凍結樣本有資料內容不符合 dataset ID")
            if dataset.get("kind") != "historical" or dataset.get("requested_analysis_date") != request["analysis_date"]:
                raise ValueError("凍結樣本的歷史資料日期不符")
            readiness = coverage(dataset, request["analysis_date"])
            cases.append({"ticker": ticker, "analysis_date": request["analysis_date"], "dataset_id": request["dataset_id"],
                          "formal_ready": readiness.get("formal_experiment_ready", False),
                          "data_blockers": readiness.get("formal_blockers", [])})
        selected = min(cases, key=lambda case: (case["analysis_date"], case["ticker"]))
        [data] = db.execute("SELECT content FROM datasets WHERE id=?", (selected["dataset_id"],)).fetchone()
        data = json.loads(data)
    if digest(data) != selected["dataset_id"]:
        raise ValueError("來源資料內容與凍結 dataset ID 不符")
    runtime = {"source_revision": args.source_revision, "image_id": args.image_id,
               "python": sys.version.split()[0], "scope": "isolated_single_case", "source_dirty": True}
    candidate = build_manifest(root, protocol, original["model_identity"], cases, runtime)
    path = output / "manifest.json"
    if path.exists():
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert_manifest_source(manifest, root)
        for key in ("protocol_hash", "model_identity", "dataset_ids_sha256", "cases", "runtime"):
            if candidate[key] != manifest[key]:
                raise ValueError("驗證設定與已凍結 manifest 不符；不得覆蓋")
    else:
        manifest = candidate
        write_json(path, manifest, exclusive=True)
        with zipfile.ZipFile(output / "source.zip", "x", zipfile.ZIP_DEFLATED) as archive:
            for relative in manifest["source"]["files"]:
                archive.write(root / relative, relative)
    print(json.dumps({"manifest": str(path), "protocol_hash": protocol.fingerprint,
                      "sample": len(cases), "qualification_case": selected, "formal_launch_ready": False}), flush=True)
    if not args.run_one:
        return 0
    if (output / "synthetic-canary.json").exists() or (output / "single-case-db").exists():
        raise ValueError("此目錄已有驗證紀錄；請使用新的輸出目錄以保留每次嘗試")
    # No formal DB is opened for writing and no service/auto-stop worker is started.
    verify_model_identity({"protocol": asdict(protocol), "model_identity": manifest["model_identity"]})
    canary = run_model_canary(protocol)
    write_json(output / "synthetic-canary.json", canary, exclusive=True)
    if canary["status"] != "pass":
        write_json(output / "verdict.json", {"formal_launch_ready": False, "blockers": ["synthetic_canary_failed"]})
        return 2
    store = Store(output / "single-case-db")
    dataset_id = store.add_dataset(data)
    ctx = SimpleNamespace(store=store, demo_mode=False, injected_model_call=False)
    request = JobInput(dataset_id=dataset_id, analysis_date=selected["analysis_date"], model=protocol.model,
                       study=protocol.study, voting_samples=protocol.voting_samples,
                       anonymize_ticker=protocol.anonymize_ticker,
                       missing_data_policy=protocol.missing_data_policy,
                       allow_point_fundamental=protocol.allow_point_fundamental,
                       allow_small_model=protocol.allow_small_model, design=protocol.design,
                       model_context_length=protocol.model_context_length, ollama_parallel=protocol.ollama_parallel)
    inventory = {"ready": True, "models": [protocol.model], "details": [manifest["model_identity"]]}
    config = prepare(ctx, request, model_probe=lambda: inventory)
    if config["protocol_hash"] != manifest["protocol_hash"]:
        raise ValueError("單案協議與 manifest 不符；未建立工作")
    config["execution_purpose"] = "qualification"
    job = store.create(config, queued=False)
    owner = "cli:qualification-" + uuid4().hex
    if not store.acquire(job["id"], owner, "0000"):
        raise RuntimeError("無法取得隔離驗證工作")
    engine = Engine(store)
    job = store.get(job["id"])
    try:
        for _ in range(40):
            assert_manifest_source(manifest, root)
            try:
                state = engine.advance(job)
            except Exception as error:
                state = getattr(error, "state", job["state"])
                store.save_step(job["id"], state, type(error).__name__, owner=owner)
                raise
            store.save_step(job["id"], state, owner=owner)
            job = store.get(job["id"])
            print(json.dumps({"status": job["status"], "outputs": len(job["state"]["records"])}), flush=True)
            if job["status"] == "complete":
                break
    finally:
        store.release(job["id"], owner)
        job = store.get(job["id"])
        verdict = qualification_verdict(job)
        write_json(output / "verdict.json", verdict)
        (output / "qualification-result.zip").write_bytes(export_job(job))
    return 0 if verdict["qualification_passed"] else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        # Provider exception tracebacks can contain authenticated URLs.
        detail = str(error) if isinstance(error, ModelIdentityError) else type(error).__name__
        print("Qualification stopped: " + detail, file=sys.stderr)
        sys.exit(1)
