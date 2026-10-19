"""Analyze a standalone, read-only registered RQ3 snapshot; no models are called."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research_service.data import digest
from research_service.rq3_inference import analyze_registered
from research_service.run_manifest import source_fingerprint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", required=True, type=Path)
    parser.add_argument("--protocol-hash", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--date-block-length", required=True, type=int)
    parser.add_argument("--daily-block-length", required=True, type=int)
    parser.add_argument("--replicates", type=int, default=1999)
    parser.add_argument("--bootstrap-seed", type=int, default=905)
    args = parser.parse_args()
    source = args.source_db.resolve(strict=True)
    if any(Path(str(source) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise ValueError("Use a standalone SQLite backup without WAL, SHM or journal")
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
        db.row_factory = sqlite3.Row
        registration = db.execute("SELECT * FROM preregistrations WHERE protocol_hash=?", (args.protocol_hash,)).fetchone()
        if registration is None:
            raise ValueError("No prior registration for this protocol")
        meta = db.execute("SELECT * FROM preregistration_meta WHERE protocol_hash=?", (args.protocol_hash,)).fetchone()
        if meta is None or not dict(meta).get("model_digest"):
            raise ValueError("Registration must freeze a model weight digest")
        ids = json.loads(registration["dataset_ids"])
        datasets = {}
        for dataset_id in ids:
            row = db.execute("SELECT content FROM datasets WHERE id=?", (dataset_id,)).fetchone()
            if row is None or digest(json.loads(row[0])) != dataset_id:
                raise ValueError("Registered dataset content digest mismatch")
            datasets[dataset_id] = json.loads(row[0])
        jobs = [{**dict(row), "config": json.loads(row["config"]), "state": json.loads(row["state"])}
                for row in db.execute("SELECT * FROM jobs WHERE json_extract(config,'$.protocol_hash')=?", (args.protocol_hash,))]
        for job in jobs:
            config = job["config"]
            if config.get("dataset_id") not in datasets:
                continue  # Formal eligibility reports nonregistered jobs as exclusions.
            data = datasets[config["dataset_id"]]
            if data.get("ticker") != config.get("ticker") or data.get("requested_analysis_date") != config.get("analysis_date"):
                raise ValueError("Dataset content does not match the stock/date case")
            if config.get("model_identity", {}).get("digest") != meta["model_digest"]:
                raise ValueError("Model weights differ from prior registration")
        result = analyze_registered(jobs, eligible_dataset_ids=ids, frozen_at=registration["frozen_at"],
                                    date_block_length=args.date_block_length, daily_block_length=args.daily_block_length,
                                    replicates=args.replicates, bootstrap_seed=args.bootstrap_seed)
    if hashlib.sha256(source.read_bytes()).hexdigest() != before:
        raise ValueError("Source database changed during analysis")
    result.update(source_database_sha256=before, dataset_manifest_hash=digest(sorted(ids)),
                  source=source_fingerprint(Path(__file__).resolve().parents[1]),
                  analysis_cli_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
