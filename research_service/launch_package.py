"""Prepare an offline, content-addressed launch proposal from a frozen RQ1 backup."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit

from .data import digest
from .protocol import QUARTER_DATES, STUDY_TICKERS
from .readiness import coverage
from .run_manifest import source_fingerprint

SCHEMA = "stance-shift-experiment-plan/v1"
RQ2_FAMILY = [f"{arm}:{metric}" for arm in ("AA", "BB") for metric in ("accuracy", "sharpe")]
RQ3_FAMILY = [f"{arm}:{metric}" for arm in ("C", "C_budget", "C_partition")
              for metric in ("accuracy", "sharpe")]
DEFAULT_PLAN = {
    "schema": SCHEMA, "model_a": "ollama/qwen3:32b", "model_b": "ollama/gemma3:27b",
    "formal_seeds": [905, 906, 907], "rq3_inference_seed": 905,
    "report_bank_seed": 904, "pilot_cases": 3,
    "model_context_length": 8192, "ollama_parallel": 1,
    "analysis": {"alpha": 0.05, "date_block_length": 2, "daily_block_length": 20,
                 "replicates": 1999, "bootstrap_seed": 905,
                 "rq2_family": RQ2_FAMILY, "rq3_family": RQ3_FAMILY},
}


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _no_secrets(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            if re.search(r"password|passwd|secret|token|credential|api.?key|authorization", str(key), re.I):
                raise ValueError("Plan cannot contain credentials")
            _no_secrets(nested)
    elif isinstance(value, list):
        for nested in value:
            _no_secrets(nested)


def validate_plan(plan):
    if not isinstance(plan, dict) or plan.get("schema") != SCHEMA:
        raise ValueError("Expected stance-shift-experiment-plan/v1")
    plan = dict(plan)
    plan.setdefault("rq3_inference_seed", 905)
    _no_secrets(plan)
    for key in ("model_a", "model_b", "model_context_length", "ollama_parallel"):
        if plan.get(key) != DEFAULT_PLAN[key]:
            raise ValueError(f"Plan {key} must match the fixed design")
    seeds = plan.get("formal_seeds")
    if (not isinstance(seeds, list) or len(seeds) < 3 or any(type(s) is not int or s < 0 for s in seeds)
            or len(set(seeds)) != len(seeds)):
        raise ValueError("Require at least three distinct nonnegative formal seeds")
    bank = plan.get("report_bank_seed")
    if type(bank) is not int or bank < 0 or bank in seeds:
        raise ValueError("Report-bank seed must be distinct from formal seeds")
    if type(plan["rq3_inference_seed"]) is not int or plan["rq3_inference_seed"] < 0:
        raise ValueError("RQ3 inference seed must be nonnegative")
    if type(plan.get("pilot_cases")) is not int or not 1 <= plan["pilot_cases"] <= 5:
        raise ValueError("pilot_cases must be between 1 and 5")
    analysis = plan.get("analysis")
    if not isinstance(analysis, dict):
        raise ValueError("Missing analysis plan")
    for family, expected in (("rq2_family", RQ2_FAMILY), ("rq3_family", RQ3_FAMILY)):
        if analysis.get(family) != expected:
            raise ValueError(f"Incomplete or reordered {family}")
    if analysis.get("alpha") != .05:
        raise ValueError("alpha must be 0.05")
    for key in ("date_block_length", "daily_block_length", "replicates"):
        if type(analysis.get(key)) is not int or analysis[key] <= 0:
            raise ValueError(f"{key} must be positive")
    if type(analysis.get("bootstrap_seed")) is not int or analysis["bootstrap_seed"] < 0:
        raise ValueError("bootstrap_seed must be nonnegative")
    return plan


def validate_url(url):
    if not isinstance(url, str):
        raise ValueError("Endpoint URL required")
    parsed = urlsplit(url)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment or any(c.isspace() for c in url)):
        raise ValueError("Endpoint URL must be http(s) without credentials, query or fragment")
    return url.rstrip("/")


def _source_cases(source, registration_hash):
    for suffix in ("-wal", "-shm", "-journal"):
        if Path(str(source) + suffix).exists():
            raise ValueError("Use a standalone SQLite backup without sidecar files")
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
        registration = db.execute("SELECT dataset_ids FROM preregistrations WHERE protocol_hash=?",
                                  (registration_hash,)).fetchone()
        saved = db.execute("SELECT cases FROM preregistration_cases WHERE protocol_hash=?",
                           (registration_hash,)).fetchone()
        if registration is None or saved is None:
            raise ValueError("Complete source registration is missing")
        ids = json.loads(registration[0])
        requests = json.loads(saved[0])
        if len(ids) != 180 or len(set(ids)) != 180 or len(requests) != 180:
            raise ValueError("Registration must contain 180 unique datasets and cases")
        cases = []
        for request in requests:
            dataset_id = request["dataset_id"]
            row = db.execute("SELECT ticker,content FROM datasets WHERE id=?", (dataset_id,)).fetchone()
            if row is None:
                raise ValueError("Registered dataset is missing")
            ticker, content = row
            data = json.loads(content)
            day = data.get("requested_analysis_date")
            if (digest(data) != dataset_id or data.get("kind") != "historical"
                    or data.get("ticker") != ticker or request.get("analysis_date") != day
                    or request.get("ticker", ticker) != ticker):
                raise ValueError("Dataset digest, ticker or analysis date mismatch")
            if coverage(data, day).get("formal_experiment_ready") is not True:
                raise ValueError("Registered dataset lacks complete formal coverage")
            cases.append({"ticker": ticker, "analysis_date": day, "dataset_id": dataset_id})
    expected = {(ticker, day) for ticker in STUDY_TICKERS for day in QUARTER_DATES}
    pairs = [(case["ticker"], case["analysis_date"]) for case in cases]
    if set(ids) != {case["dataset_id"] for case in cases} or len(set(pairs)) != 180 or set(pairs) != expected:
        raise ValueError("Registration is not the complete unique 9x20 grid")
    return sorted(cases, key=lambda c: (c["analysis_date"], c["ticker"]))


def _rq2_case(case, plan, endpoints, seed):
    return {"dataset_id": case["dataset_id"], "analysis_date": case["analysis_date"],
            "model": plan["model_a"], "inference_seed": seed,
            "model_context_length": plan["model_context_length"], "ollama_parallel": plan["ollama_parallel"],
            "debate_model_a": plan["model_a"], "debate_model_b": plan["model_b"],
            "debate_assignments": ["AA", "AB", "BA", "BB"],
            "model_endpoints": endpoints}


def _rq3_case(case, plan, seed):
    return {"dataset_id": case["dataset_id"], "analysis_date": case["analysis_date"],
            "model": plan["model_a"], "inference_seed": seed,
            "model_context_length": plan["model_context_length"], "ollama_parallel": plan["ollama_parallel"],
            "domain_debate": {"rq3_version": "rq3-1015.1", "rule": "fixed", "include_controls": True}}


def _write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def prepare_launch(source_db, registration_hash, plan_path, output, model_a_base, model_b_base,
                   *, runner_path=None):
    source = Path(source_db).resolve(strict=True)
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Output must be a new directory")
    if source.is_relative_to(output):
        raise ValueError("Output cannot contain the source backup")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", registration_hash):
        raise ValueError("Require full 64-character registration hash")
    plan = validate_plan(json.loads(Path(plan_path).read_text(encoding="utf-8-sig")))
    endpoints = {plan["model_a"]: {"api_base": validate_url(model_a_base)},
                 plan["model_b"]: {"api_base": validate_url(model_b_base)}}
    source_before = file_hash(source)
    cases = _source_cases(source, registration_hash)
    if file_hash(source) != source_before:
        raise RuntimeError("Source backup changed while reading")
    root = Path(__file__).resolve().parents[1]
    runner = Path(runner_path or root / "scripts" / "prepare_experiment_launch.py")
    pipeline = {}
    for name in ("scripts/run_design_pilot.py", "scripts/analyze_rq2_snapshot.py",
                 "scripts/analyze_rq3_snapshot.py", "scripts/prepare_experiment_launch.py",
                 "scripts/bind_rq2_launch.py", "scripts/check_experiment_environment.py",
                 "docs/rq-prep/analysis-plan-20261015.json"):
        path = root / name
        if not path.is_file():
            if name.startswith("scripts/"):
                raise ValueError(f"Required pipeline script is missing: {name}")
            continue
        pipeline[name] = file_hash(path)
    artifacts = {
        "report-bank.cases.json": {"cases": [_rq2_case(c, plan, endpoints, plan["report_bank_seed"]) for c in cases]},
        "rq2-pilot.cases.json": {"cases": [_rq2_case(c, plan, endpoints, plan["formal_seeds"][0])
                                           for c in cases[:plan["pilot_cases"]]]},
        "rq3-pilot.cases.json": {"cases": [_rq3_case(c, plan, plan["rq3_inference_seed"])
                                           for c in cases[:plan["pilot_cases"]]]},
        "rq3-formal.cases.json": {"cases": [_rq3_case(c, plan, plan["rq3_inference_seed"])
                                             for c in cases]},
        "rq3-runtime.json": {"schema": "stance-shift-rq3-runtime/v1", "model_a_base": endpoints[plan["model_a"]]["api_base"],
                             "required_environment": {"OLLAMA_BASE_URL": endpoints[plan["model_a"]]["api_base"],
                                                      "GPUTW_OLLAMA_BASE_URL": endpoints[plan["model_a"]]["api_base"]}},
        "experiment-plan.json": plan,
        "analysis-plan.json": plan["analysis"],
        "frame.json": {"schema": "stance-shift-launch-frame/v1", "source_registration_hash": registration_hash,
                       "cases": cases},
    }
    output.mkdir(parents=True, exist_ok=False)
    for name, data in artifacts.items():
        _write_json(output / name, data)
    source_after = file_hash(source)
    if source_after != source_before:
        raise RuntimeError("Source backup changed during preparation")
    manifest = {"schema": "stance-shift-launch-manifest/v1", "formal_launch_ready": False,
                "blocking_requirements": ["real_model_qualification", "pilot_verdict", "report_bank",
                                          "new_registration"],
                "source_registration_hash": registration_hash, "source_database_sha256_before": source_before,
                "source_database_sha256_after": source_after, "plan_sha256": digest(plan),
                "source_fingerprint": source_fingerprint(root), "cli_sha256": file_hash(runner),
                "pipeline_sha256": pipeline,
                "artifacts_sha256": {name: file_hash(output / name) for name in artifacts},
                "rq3_runtime_sha256": file_hash(output / "rq3-runtime.json"),
                "rq3_runtime_requirement": "Apply rq3-runtime.json environment before RQ3 execution and verify its SHA256 against rq3_runtime_sha256.",
                "seed_scope": {"rq2_formal_seeds": plan["formal_seeds"],
                               "rq3_inference_seed": plan["rq3_inference_seed"],
                               "note": "RQ2 reserves three formal inference seeds; RQ3 has one protocol and one formal seed."},
                "note": "Offline proposal only. No model weights, report references, jobs or registration are verified."}
    _write_json(output / "launch-manifest.json", manifest)
    return manifest
