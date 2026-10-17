"""Offline binding of a frozen RQ2 launch frame to an idle report-bank backup."""
from contextlib import closing
from dataclasses import asdict
import json
from pathlib import Path
import re
import sqlite3

from .data import digest
from .launch_package import file_hash, validate_plan
from .protocol import QUARTER_DATES, STUDY_TICKERS, RouterProtocol, protocol_from
from .run_manifest import source_fingerprint
from .shared_reports import bind_report
from .storage import Store
from .web.context import BatchInput


_ARTIFACTS = ("report-bank.cases.json", "experiment-plan.json", "frame.json")
_PIPELINE = ("scripts/run_design_pilot.py", "scripts/analyze_rq2_snapshot.py",
             "scripts/analyze_rq3_snapshot.py", "scripts/prepare_experiment_launch.py")


class _ReadOnlyStore:
    """The minimal Store interface required by bind_report; never opens a Store."""

    def __init__(self, db):
        self._db = db

    def get(self, job_id):
        row = self._db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return Store.unpack(row)


def _sidecars_free(path):
    for suffix in ("-wal", "-shm", "-journal"):
        if Path(str(path) + suffix).exists():
            raise ValueError("Report bank must be a standalone SQLite backup without sidecars")


def _read_launch(launch_dir, root):
    launch_dir = Path(launch_dir).resolve(strict=True)
    manifest_path = launch_dir / "launch-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if manifest.get("schema") != "stance-shift-launch-manifest/v1":
        raise ValueError("Unsupported launch manifest")
    if manifest.get("source_fingerprint") != source_fingerprint(root):
        raise ValueError("Launch source fingerprint is stale")
    pipeline = manifest.get("pipeline_sha256")
    if not isinstance(pipeline, dict) or not set(_PIPELINE) <= pipeline.keys():
        raise ValueError("Launch manifest is missing required pipeline hashes")
    for name, expected in pipeline.items():
        path = root / name
        if (not path.is_file() or not re.fullmatch(r"[0-9a-f]{64}", str(expected))
                or file_hash(path) != expected):
            raise ValueError(f"Launch pipeline hash mismatch: {name}")
    hashes = manifest.get("artifacts_sha256")
    if not isinstance(hashes, dict) or not set(_ARTIFACTS) <= hashes.keys():
        raise ValueError("Launch manifest is missing required artifact hashes")
    for name, expected in hashes.items():
        if Path(name).name != name or not re.fullmatch(r"[0-9a-f]{64}", str(expected)):
            raise ValueError("Invalid launch artifact entry")
        path = launch_dir / name
        if not path.is_file() or file_hash(path) != expected:
            raise ValueError(f"Launch artifact hash mismatch: {name}")
    plan = validate_plan(json.loads((launch_dir / "experiment-plan.json").read_text(encoding="utf-8-sig")))
    if digest(plan) != manifest.get("plan_sha256"):
        raise ValueError("Launch plan hash mismatch")
    frame = json.loads((launch_dir / "frame.json").read_text(encoding="utf-8-sig"))
    if frame.get("schema") != "stance-shift-launch-frame/v1":
        raise ValueError("Unsupported launch frame")
    cases = frame.get("cases")
    expected = {(ticker, day) for ticker in STUDY_TICKERS for day in QUARTER_DATES}
    expected_count = len(expected)
    pairs = [(case.get("ticker"), case.get("analysis_date")) for case in cases or []]
    ids = [case.get("dataset_id") for case in cases or []]
    if (len(pairs) != expected_count or set(pairs) != expected or len(set(pairs)) != expected_count
            or len(set(ids)) != expected_count or any(not isinstance(value, str) or not value for value in ids)):
        raise ValueError("Launch frame must contain the complete unique 9x20 case grid")
    batch = json.loads((launch_dir / "report-bank.cases.json").read_text(encoding="utf-8-sig"))
    template = BatchInput.model_validate(batch).cases
    by_pair = {(case.dataset_id, case.analysis_date): case for case in template}
    if (len(template) != expected_count or len(by_pair) != expected_count or any(case.neutral_report_job_id or case.neutral_report_hash
                                                           for case in template)):
        raise ValueError("Report-bank template must contain 180 unique unbound cases")
    frame_by_pair = {(case["dataset_id"], case["analysis_date"]): case for case in cases}
    if set(by_pair) != set(frame_by_pair):
        raise ValueError("Report-bank template and launch frame do not match")
    return launch_dir, manifest, plan, frame_by_pair, by_pair


def _template_matches_protocol(template, protocol, bank_seed):
    if template.allow_low_quality_sentiment:
        raise ValueError("Report-bank template cannot allow low-quality sentiment")
    if template.domain_debate is not None:
        raise ValueError("Report-bank template must use the RQ2 router")
    router_fields = {key: value for key in ("debate_model_a", "debate_model_b", "debate_assignments", "model_endpoints")
                     if (value := getattr(template, key)) is not None}
    if "debate_assignments" in router_fields:
        router_fields["debate_assignments"] = tuple(router_fields["debate_assignments"])
    expected = RouterProtocol(
        model=template.model, voting_samples=template.voting_samples, study=template.study,
        inference_seed=template.inference_seed, anonymize_ticker=template.anonymize_ticker,
        dataset_kind="historical", missing_data_policy=template.missing_data_policy,
        allow_point_fundamental=template.allow_point_fundamental,
        allow_small_model=template.allow_small_model,
        **{key: value for key in ("model_context_length", "ollama_parallel")
           if (value := getattr(template, key)) is not None},
        **router_fields)
    if template.inference_seed != bank_seed or digest(asdict(expected)) != digest(asdict(protocol)):
        raise ValueError("Report-bank source configuration does not match launch template")


def bind_launch(launch_dir, bank_db, output_dir):
    """Bind report-bank jobs to formal seed cases without creating jobs or registrations."""
    root = Path(__file__).resolve().parents[1]
    launch_dir, launch_manifest, plan, frame, templates = _read_launch(launch_dir, root)
    bank = Path(bank_db).resolve(strict=True)
    output = Path(output_dir).resolve()
    if output.exists():
        raise ValueError("Output must be a new directory")
    _sidecars_free(bank)
    bank_before = file_hash(bank)
    selected = {}
    with closing(sqlite3.connect(bank.as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
        db.row_factory = sqlite3.Row
        try:
            rows = db.execute("SELECT * FROM jobs").fetchall()
        except sqlite3.Error as error:
            raise ValueError("Report-bank backup has no readable jobs table") from error
        for row in rows:
            try:
                config = json.loads(row["config"])
            except (TypeError, json.JSONDecodeError):
                continue
            if config.get("execution_purpose") != "report_bank":
                continue
            pair = (config.get("dataset_id"), config.get("analysis_date"))
            if pair in templates:
                selected.setdefault(pair, []).append(row)
        if set(selected) != set(templates) or any(len(matches) != 1 for matches in selected.values()):
            raise ValueError("Each launch frame case must have exactly one report_bank source job")

        adapter = _ReadOnlyStore(db)
        formal_cases = {seed: [] for seed in plan["formal_seeds"]}
        canonical_protocol = None
        canonical_digests = None
        for pair, frame_case in sorted(frame.items(), key=lambda item: (item[0][1], item[0][0])):
            template = templates[pair]
            row = selected[pair][0]
            source = Store.unpack(row)
            config = source["config"]
            protocol_data = config.get("protocol")
            if not isinstance(protocol_data, dict) or not config.get("protocol_hash"):
                raise ValueError("Report-bank source is missing its frozen protocol")
            source_protocol = protocol_from(protocol_data)
            if (source_protocol.inference_seed != plan["report_bank_seed"]
                    or config.get("protocol_hash") != source_protocol.fingerprint):
                raise ValueError("Report-bank source protocol is stale or uses the wrong seed")
            _template_matches_protocol(template, source_protocol, plan["report_bank_seed"])
            target_protocols = {}
            for seed in plan["formal_seeds"]:
                target_data = dict(protocol_data)
                target_data["inference_seed"] = seed
                target_protocols[seed] = protocol_from(target_data)
                protocol_identity = asdict(target_protocols[seed])
                protocol_identity.pop("inference_seed", None)
                if canonical_protocol is None:
                    canonical_protocol = digest(protocol_identity)
                elif canonical_protocol != digest(protocol_identity):
                    raise ValueError("Report-bank jobs do not share one protocol configuration")

            identity = config.get("model_identity") or {}
            routed = config.get("routed_model_identities") or {}
            expected_models = {source_protocol.model, source_protocol.debate_model_a, source_protocol.debate_model_b}
            routed_digests = {key: value.get("digest") for key, value in routed.items()
                              if isinstance(value, dict)}
            if (identity.get("id") != source_protocol.model or not identity.get("digest")
                    or set(routed) != expected_models or not all(isinstance(value, dict) for value in routed.values())
                    or routed[source_protocol.debate_model_a].get("digest") != identity.get("digest")
                    or any(not value for value in routed_digests.values())):
                raise ValueError("Report-bank source must record nonempty model digests")
            digest_identity = (identity.get("id"), identity.get("digest"), tuple(sorted(routed_digests.items())))
            if canonical_digests is None:
                canonical_digests = digest_identity
            elif canonical_digests != digest_identity:
                raise ValueError("Report-bank model digests differ across cases")

            payload = template.model_copy(update={"neutral_report_job_id": source["id"],
                                                  "neutral_report_hash": source["state"].get("report_hash")})
            if (config.get("ticker") != frame_case["ticker"] or config.get("analysis_date") != pair[1]
                    or config.get("dataset_id") != pair[0]):
                raise ValueError("Report-bank source dataset/date does not match the launch frame")
            for target_protocol in target_protocols.values():
                shared = bind_report(adapter, payload, target_protocol, identity, routed)
                if not shared:
                    raise ValueError("Report-bank source did not produce a locked shared report")

            neutral = {"neutral_report_job_id": source["id"],
                       "neutral_report_hash": source["state"].get("report_hash")}
            for seed in plan["formal_seeds"]:
                case = template.model_dump(exclude_none=True)
                case.update(neutral)
                case["inference_seed"] = seed
                formal_cases[seed].append(case)

    _sidecars_free(bank)
    bank_after = file_hash(bank)
    if bank_after != bank_before:
        raise RuntimeError("Report-bank backup changed while binding")
    expected_count = len(frame)
    if any(len(items) != expected_count for items in formal_cases.values()):
        raise ValueError(f"Each formal seed batch must contain {expected_count} cases")
    output.mkdir(parents=True, exist_ok=False)
    artifacts = {}
    for seed, cases in formal_cases.items():
        name = f"rq2-formal.seed-{seed}.cases.json"
        path = output / name
        path.write_text(json.dumps({"cases": cases}, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                        encoding="utf-8")
        artifacts[name] = file_hash(path)
    result = {"schema": "rq2-formal-launch-binding/v1", "formal_launch_ready": False,
              "blocking_requirements": ["same_store_with_report_bank_and_eligibility", "new_registration"],
              "source_registration_hash": launch_manifest.get("source_registration_hash"),
              "launch_manifest_sha256": file_hash(launch_dir / "launch-manifest.json"),
              "launch_artifacts_sha256": launch_manifest["artifacts_sha256"],
              "bank_path": str(bank), "bank_sha256_before": bank_before, "bank_sha256_after": bank_after,
              "n_cases_per_seed": expected_count, "seeds": plan["formal_seeds"], "artifacts_sha256": artifacts,
              "note": "Offline binding only; source model digests are recorded claims, not runtime identity verification."}
    (output / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result
