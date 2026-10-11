"""Content-addressed qualification manifests, separate from study registration."""
from dataclasses import asdict
import hashlib
from pathlib import Path

from .data import digest
from .protocol import QUARTER_DATES, STUDY_TICKERS, StudyProtocol, decision_plan
from .storage import now


def source_fingerprint(root):
    root = Path(root)
    files = [path for path in (root / "research_service").rglob("*")
             if path.is_file() and "tests" not in path.parts
             and path.suffix in (".py", ".js", ".css", ".html")]
    files.append(root / "pyproject.toml")
    runner = root / "scripts" / "qualify_experiment.py"
    if runner.exists():
        files.append(runner)
    hashes = {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(files)}
    return {"sha256": digest(hashes), "files": hashes}


def build_manifest(root, protocol, identity, cases, runtime):
    expected = {(ticker, day) for ticker in STUDY_TICKERS for day in QUARTER_DATES}
    keys = [(case["ticker"], case["analysis_date"]) for case in cases]
    ids = [case["dataset_id"] for case in cases]
    if protocol.design != "quarterly" or len(keys) != 180 or set(keys) != expected or len(set(ids)) != 180:
        raise ValueError("本驗證入口只接受完整且唯一的季度 9×20 凍結樣本；月度尚未放行")
    if identity.get("id") != protocol.model or not identity.get("digest"):
        raise ValueError("manifest 必須凍結同一模型的完整 digest")
    if not runtime.get("image_id") or not runtime.get("source_revision"):
        raise ValueError("manifest 必須記錄實際映像 ID 及來源 revision")
    return {"schema": "stance-shift-qualification/v1", "frozen_at": now(),
            "purpose": "qualification_only", "formal_launch_ready": False,
            "protocol": asdict(protocol), "protocol_hash": protocol.fingerprint,
            "model_identity": identity, "runtime": runtime, "source": source_fingerprint(root),
            "dataset_ids_sha256": hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest(),
            "cases": sorted(cases, key=lambda case: (case["analysis_date"], case["ticker"])),
            "qualification_case": min(cases, key=lambda case: (case["analysis_date"], case["ticker"])),
            "approval_requirements": ["unit_and_browser_tests", "strict_synthetic_canary",
                                      "historical_qualification_case", "new_preregistration",
                                      "matching_immutable_deployment_manifest"]}


def assert_manifest_source(manifest, root):
    if source_fingerprint(root) != manifest["source"]:
        raise ValueError("程式已不同於凍結 manifest；禁止以舊 manifest 執行，請另建驗證版本")


def qualification_verdict(job):
    state = job.get("state", {})
    config = job.get("config", {})
    checks = state.get("model_identity_checks", [])
    blockers = []
    if job.get("config", {}).get("execution_purpose") != "qualification":
        blockers.append("not_isolated_qualification")
    if job.get("status") != "complete" or not state.get("finished"):
        blockers.append("incomplete")
    if set(state.get("decisions", {})) != set("ABCD"):
        blockers.append("missing_decision_arms")
    identity = config.get("model_identity", {})
    if (state.get("model_identity_failure") or not checks or checks[-1].get("phase") != "after_step"
            or any(check.get("status") != "pass" or check.get("digest") != identity.get("digest")
                   or check.get("id") != identity.get("id") for check in checks)):
        blockers.append("runtime_identity_not_proven")
    if state.get("report", {}).get("degraded_research_domains"):
        blockers.append("degraded_research")
    outputs = [record for record in state.get("records", [])]
    protocol = StudyProtocol(**config["protocol"])
    expected_calls = {call.key for call in decision_plan(protocol)}
    if len(outputs) != len(expected_calls) or {item.get("key") for item in outputs} != expected_calls:
        blockers.append("incomplete_model_call_plan")
    if set(state.get("research", {})) != {"technical", "fundamental", "sentiment", "macro"}:
        blockers.append("missing_research_outputs")
    expected_rows = {(group, horizon, cost, layer) for group in "ABCD" for horizon in protocol.horizons
                     for cost in protocol.cost_models for layer in ("candidate", "gated")}
    case_rows = state.get("cases", [])
    if len(case_rows) != len(expected_rows) or {
            (row.get("group"), row.get("horizon"), row.get("cost_model"), row.get("decision_layer"))
            for row in case_rows} != expected_rows:
        blockers.append("incomplete_backtest_rows")
    if config.get("formal_readiness", {}).get("eligible") is not True:
        blockers.append("case_data_not_formal_ready")
    outputs += [{"output": result} for result in state.get("research", {}).values()]
    numeric_redacted = sum(bool(record.get("output", {}).get("redacted_numbers")
                                or record.get("output", {}).get("numeric_claims_removed")) for record in outputs)
    # Predefined conservative canary gate, not an exclusion rule for a future study.
    if numeric_redacted:
        blockers.append("numeric_redaction_requires_review")
    return {"qualification_passed": not blockers, "formal_launch_ready": False,
            "blockers": blockers, "outputs_checked": len(outputs),
            "numeric_redacted_outputs": numeric_redacted,
            "note": "單案驗證不納入正式結果；即使通過，仍需新登記與匹配的部署 manifest。"}
