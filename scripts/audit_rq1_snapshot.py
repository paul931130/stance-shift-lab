"""Recompute RQ1 from a standalone, read-only SQLite snapshot; never start a model."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import types
import zipfile

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research_service.data import digest


def file_hash(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", type=Path, required=True)
    parser.add_argument("--protocol-hash", required=True)
    parser.add_argument("--analysis-ref", default="eb36a8a")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = args.source_db.resolve(strict=True)
    if any(Path(str(source) + suffix).exists() for suffix in ("-wal", "-journal")):
        raise ValueError("Use a standalone backup without a WAL/journal")
    output = args.output.resolve()
    if output == source.parent or source.is_relative_to(output):
        raise ValueError("Output must be separate from the source snapshot")
    output.mkdir(parents=True, exist_ok=False)
    before = file_hash(source)
    revision = subprocess.check_output(["git", "rev-parse", args.analysis_ref], cwd=root, text=True).strip()

    def historical_code(name):
        return subprocess.check_output(["git", "show", f"{revision}:research_service/{name}.py"], cwd=root)

    # The old reporting module uses these local dependencies. Require byte-equivalence
    # before importing, instead of silently evaluating with a changed implementation.
    for name in ("statistics", "backtest", "splits"):
        old = historical_code(name).replace(b"\r\n", b"\n")
        current = (root / "research_service" / f"{name}.py").read_bytes().replace(b"\r\n", b"\n")
        if old != current:
            raise ValueError(f"{name}.py differs from the analysis revision; use its matching checkout")
    reporting_source = historical_code("reporting")
    analysis = types.ModuleType("research_service._snapshot_reporting")
    analysis.__package__ = "research_service"
    exec(compile(reporting_source, f"{revision}:reporting.py", "exec"), analysis.__dict__)

    with sqlite3.connect(source.as_uri() + "?mode=ro&immutable=1", uri=True) as db:
        db.row_factory = sqlite3.Row
        registration = db.execute("SELECT * FROM preregistrations WHERE protocol_hash=?",
                                  (args.protocol_hash,)).fetchone()
        if registration is None:
            raise ValueError("No registration for requested hash")
        registration = dict(registration)
        ids = json.loads(registration["dataset_ids"])
        raw_jobs = db.execute("SELECT * FROM jobs WHERE json_extract(config,'$.protocol_hash')=?",
                              (args.protocol_hash,)).fetchall()
        jobs = [{**dict(row), "config": json.loads(row["config"]), "state": json.loads(row["state"])}
                for row in raw_jobs]
        datasets = []
        for dataset_id in sorted(ids):
            row = db.execute("SELECT content FROM datasets WHERE id=?", (dataset_id,)).fetchone()
            if row is None or digest(json.loads(row[0])) != dataset_id:
                raise ValueError(f"Missing or invalid content-addressed dataset {dataset_id}")
            datasets.append({"id": dataset_id, "content": json.loads(row[0])})
    if len(ids) != 180 or len(set(ids)) != 180 or len(jobs) != 180:
        raise ValueError("Expected 180 unique registered datasets and exactly 180 jobs")
    selected, excluded = analysis._completed_unique(
        jobs, formal_only=True, eligible_dataset_ids=set(ids), frozen_at=registration["frozen_at"])
    if len(selected) != 180:
        raise ValueError(f"Not all registered cases qualify: {excluded}")

    print("Validated 180 datasets and 180 registered cases; recomputing frozen analysis", flush=True)
    report = analysis.study_report(jobs, eligible_dataset_ids=ids, frozen_at=registration["frozen_at"])
    panel = analysis._case_panel(selected, 60, "corwin_schultz", "candidate")
    daily = io.StringIO(newline="")
    writer = csv.writer(daily)
    writer.writerow(["date", "A", "B", "C", "D", "buy_and_hold_active_windows"])
    for index, day in enumerate(panel["dates"]["all"]):
        writer.writerow([day, *(panel["portfolios"]["all"][g][index] for g in "ABCD"), panel["benchmark"][index]])
    case_keys = [(j["config"]["ticker"], j["config"]["analysis_date"]) for j in selected]
    checks = {
        "protocol_hash": args.protocol_hash, "registered_at": registration["frozen_at"],
        "cases": len(selected), "unique_stock_dates": len(set(case_keys)),
        "analysis_dates": len({day for _, day in case_keys}), "dataset_content_hashes_verified": len(datasets),
        "daily_T": len(panel["dates"]["all"]), "daily_start": panel["dates"]["all"][0],
        "daily_end": panel["dates"]["all"][-1], "excluded": excluded,
        "analysis_revision": revision, "analysis_kind": "historical reporting source with verified identical numerical dependencies",
        "source_snapshot": str(source), "source_sha256": before,
        "decision_records": sum(len(j["state"].get("records", [])) for j in selected),
        "missing_raw_responses": sum("raw_response" not in (r.get("audit") or {})
                                     for j in selected for r in j["state"].get("records", [])),
        "summary": [row for row in report["summary"] if row["horizon"] == 60
                    and row["cost_model"] == "corwin_schultz" and row["decision_layer"] == "candidate"
                    and row["portfolio_basis"] == "all"],
        "primary_inference": report["primary_inference"],
    }
    payloads = {"statistics.json": json_bytes(report), "audit.json": json_bytes(checks),
                "registration.json": json_bytes({**registration, "dataset_ids": ids}),
                "primary-daily-panel.csv": daily.getvalue().encode("utf-8"),
                "analysis/reporting.py": reporting_source}
    for name in ("statistics", "backtest", "splits"):
        payloads[f"analysis/{name}.py"] = historical_code(name)
    for job in selected:
        payloads[f"jobs/{job['id']}.json"] = json_bytes(job)
    for data in datasets:
        payloads[f"datasets/{data['id']}.json"] = json_bytes(data)
    manifest = {"schema": "rq1-readonly-audit/v1", "analysis_revision": revision,
                "source_sha256": before,
                "files": [{"path": name, "bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
                          for name, value in sorted(payloads.items())]}
    with zipfile.ZipFile(output / "rq1-evidence.zip", "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in sorted(payloads.items()):
            archive.writestr(name, value)
        archive.writestr("manifest.json", json_bytes(manifest))
    for name in ("audit.json", "statistics.json", "primary-daily-panel.csv"):
        (output / name).write_bytes(payloads[name])
    (output / "manifest.json").write_bytes(json_bytes(manifest))
    after = file_hash(source)
    if before != after:
        raise RuntimeError("Source snapshot changed during analysis")
    with zipfile.ZipFile(output / "rq1-evidence.zip") as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Archive CRC validation failed")
        for row in manifest["files"]:
            if hashlib.sha256(archive.read(row["path"])).hexdigest() != row["sha256"]:
                raise RuntimeError(f"Export verification failed: {row['path']}")
    print(json.dumps({"source_unchanged": True, "cases": len(selected), "T": checks["daily_T"],
                      "output": str(output)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
