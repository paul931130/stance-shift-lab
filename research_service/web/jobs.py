"""Job validation (the single source of readiness rules), queue control and exports."""
from dataclasses import asdict
import hashlib
import io
import json
import zipfile

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from ..data import research_inputs
from ..errors import NotFoundError, PreflightError
from ..protocol import (DEFAULT_RESEARCH_MODEL, FORMAL_SMALL_MODEL_ALLOWLIST, SMALL_MODEL_PATTERN,
                        StudyProtocol, validate_case)
from ..readiness import coverage
from ..reporting import export_job, study_report
from ..splits import classify_analysis_date
from ..storage import now
from .context import BatchInput, JobInput
from .ollama import CachedProbe, parameter_billions, probe_models


def prepare(ctx, payload, model_probe=None):
    """Validate a job request and freeze its config.

    Job creation, batches, clones and the UI's preflight all go through here,
    so each readiness rule exists exactly once. Named failures raise
    PreflightError with a reason code the UI maps to an override checkbox.
    """
    data = ctx.store.dataset(payload.dataset_id)
    validate_case(data["ticker"], payload.analysis_date)
    requested_date = data.get("requested_analysis_date")
    if data.get("kind") == "historical" and requested_date != payload.analysis_date:
        shown = requested_date or "未記錄"
        raise PreflightError("date_mismatch", f"資料集研究日是 {shown}，不能用於 {payload.analysis_date}；請選擇日期完全相同的資料集")
    effective_model = ctx.demo_model_id if ctx.demo_mode else payload.model
    protocol = StudyProtocol(model=effective_model, voting_samples=payload.voting_samples, study=payload.study,
        anonymize_ticker=payload.anonymize_ticker, dataset_kind=data["kind"],
        missing_data_policy=payload.missing_data_policy,
        allow_point_fundamental=payload.allow_point_fundamental,
        allow_small_model=payload.allow_small_model)
    # Build the frozen evidence selection once before accepting a job.  The
    # quality gate catches stale broad-market news while retaining a
    # researcher-visible override for deliberate sensitivity cases.
    research_inputs(data, payload.analysis_date, protocol)
    coverage_result = coverage(data, payload.analysis_date)
    quality = coverage_result.get("sentiment_quality", {})
    fundamental_quality = coverage_result.get("fundamental_quality", {})
    # An intentionally missing sentiment domain remains a valid missing-data
    # control.  When news is present, historical experiments require both
    # target relevance and a complete, auditable FinBERT pass unless the
    # researcher records an explicit data-quality sensitivity override.
    quality_problem = (data.get("kind") == "historical" and quality.get("items", 0) > 0
                       and (not quality.get("passes_quality_gate") or not quality.get("finbert_complete")))
    if quality_problem and not payload.allow_low_quality_sentiment:
        reasons = []
        if not quality.get("passes_quality_gate"):
            reasons.append(f"新聞目標相關率 {quality.get('target_relevance_rate', quality.get('ticker_mention_rate', 0.0)):.2f} 未達 0.50")
        if not quality.get("finbert_complete"):
            reasons.append(f"FinBERT 標題評分 {quality.get('finbert_scored', 0)}/{quality.get('items', 0)}")
        raise PreflightError("sentiment_quality", "此歷史資料集的新聞品質檢查未通過（" + "；".join(reasons)
                             + "）；請建立完整 FinBERT 評分版本、重新蒐集資料，或在「資料品質例外」勾選新聞品質例外（只算敏感性測試）")
    fundamental_problem = (data.get("kind") == "historical" and fundamental_quality.get("items", 0) > 0
                           and not fundamental_quality.get("passes_quality_gate"))
    if fundamental_problem and not payload.allow_point_fundamental:
        raise PreflightError("fundamental_quality", "此歷史資料集只有 SEC 點時欄位，沒有可比較的前期數字；請重新蒐集新版資料，"
                             "或在「資料品質例外」勾選舊版 SEC 基本面例外（只算敏感性測試）")
    if effective_model.startswith("ollama/") and not ctx.injected_model_call:
        installed = (model_probe or (lambda: probe_models(ctx)))()
        if not installed.get("ready") or effective_model not in installed.get("models", []):
            raise PreflightError("model_not_installed", f"Ollama 模型 {effective_model} 尚未安裝，或 Ollama 目前連不上；請先執行 ollama pull，或改用其他模型來源")
        model_identity = next(item for item in installed["details"] if item["id"] == effective_model)
        parameter_count = parameter_billions(model_identity.get("parameter_size"))
        if (parameter_count is not None and parameter_count < 14
                and effective_model.strip().lower() not in FORMAL_SMALL_MODEL_ALLOWLIST
                and not payload.allow_small_model):
            raise PreflightError("model_too_small", f"{effective_model} 參數量為 {model_identity.get('parameter_size') or '未知'}，未達正式門檻（14B；qwen3:8b 除外）。若只是測試，請在「資料品質例外」勾選「允許 14B 以下的模型」")
    else:
        model_identity = {"id": effective_model,
                          "provider": "built_in_demo" if ctx.demo_mode else ("test_override" if ctx.injected_model_call else "cloud_alias"),
                          "resolved_at": now()}
    return {"ticker": data["ticker"], "analysis_date": payload.analysis_date,
        "evaluation_split": classify_analysis_date(payload.analysis_date), "dataset_id": payload.dataset_id,
        "dataset_hash": payload.dataset_id, "protocol": asdict(protocol), "protocol_hash": protocol.fingerprint,
        "formal_readiness": {
            "eligible": bool(coverage_result.get("formal_experiment_ready")),
            "blockers": list(coverage_result.get("formal_blockers", [])),
            "base_rate_windows": coverage_result.get("base_rate_windows"),
            "base_rate_windows_required": coverage_result.get("base_rate_windows_required"),
        },
        "model_identity": model_identity,
        "quality_overrides": {
            **({"allow_low_quality_sentiment": True, "sentiment_quality": quality}
               if payload.allow_low_quality_sentiment and quality_problem else {}),
            **({"allow_point_fundamental": True, "fundamental_quality": fundamental_quality}
               if payload.allow_point_fundamental and fundamental_problem else {}),
        }}


def clone_request(ctx, original):
    """Rebuild a job request under the current protocol, keeping legacy exceptions auditable."""
    old = original["config"]
    p = old["protocol"]
    legacy = p.get("version") != StudyProtocol().version
    model = p.get("model", DEFAULT_RESEARCH_MODEL)
    old_quality = coverage(ctx.store.dataset(old["dataset_id"]), old["analysis_date"]).get("sentiment_quality", {})
    # A user pressing the explicit migration action asks to reproduce a
    # legacy run under the new protocol.  Preserve any legacy model/data
    # exception as auditable overrides rather than failing silently before
    # the replacement job can be inspected or exported.
    allow_small = (bool(p.get("allow_small_model", False))
                   or (legacy and bool(SMALL_MODEL_PATTERN.search(model))
                       and model.strip().lower() not in FORMAL_SMALL_MODEL_ALLOWLIST))
    old_quality_problem = (old_quality.get("items", 0) > 0
                           and (not old_quality.get("passes_quality_gate") or not old_quality.get("finbert_complete")))
    allow_low_quality = (bool(old.get("quality_overrides", {}).get("allow_low_quality_sentiment", False))
                         or (legacy and old_quality_problem))
    allow_point_fundamental = (bool(p.get("allow_point_fundamental", False))
                               or bool(old.get("quality_overrides", {}).get("allow_point_fundamental", False))
                               or legacy)
    payload = JobInput(dataset_id=old["dataset_id"], analysis_date=old["analysis_date"],
        model=model, study=p.get("study", "study1"), voting_samples=p.get("voting_samples", 7),
        anonymize_ticker=p.get("anonymize_ticker", False),
        missing_data_policy=p.get("missing_data_policy", "allow_decision"),
        allow_point_fundamental=allow_point_fundamental,
        allow_small_model=allow_small, allow_low_quality_sentiment=allow_low_quality)
    migration = ({"from_protocol_version": p.get("version", "unknown"),
                  "legacy_small_model_override": allow_small,
                  "legacy_low_quality_sentiment_override": allow_low_quality} if legacy else None)
    return payload, migration


def build_router(ctx):
    router = APIRouter()
    store = ctx.store
    cached_probe = CachedProbe(ctx)

    @router.post("/api/jobs")
    def create_job(payload: JobInput):
        return store.create(prepare(ctx, payload))

    @router.post("/api/jobs/preflight")
    def preflight(payload: JobInput):
        """Dry-run the exact job validation so the UI never re-implements it."""
        try:
            config = prepare(ctx, payload, model_probe=cached_probe)
        except PreflightError as error:
            return {"ready": False, "reason": error.reason, "message": str(error)}
        except NotFoundError as error:
            return {"ready": False, "reason": "no_dataset", "message": str(error)}
        except ValueError as error:
            return {"ready": False, "reason": "invalid", "message": str(error)}
        return {"ready": True, "reason": "ready", "model": config["protocol"]["model"],
                "formal_readiness": config["formal_readiness"]}

    @router.post("/api/batches")
    def batch(payload: BatchInput):
        prepared = [prepare(ctx, item) for item in payload.cases]
        keys = [(item["ticker"], item["analysis_date"], item["protocol_hash"]) for item in prepared]
        if len(set(keys)) != len(keys):
            raise ValueError("批次內不可重複 case")
        return [store.create(item)["id"] for item in prepared]

    @router.get("/api/jobs")
    def jobs():
        return store.job_summaries()

    @router.get("/api/dashboard")
    def dashboard(selected: str | None = None):
        return {"jobs": store.job_summaries(), "selected": store.get(selected) if selected else None}

    @router.get("/api/jobs/{key}")
    def job(key: str, detail: bool = False):
        result = store.get(key)
        if detail:
            return result
        state = result.pop("state")
        result["state_summary"] = {
            "finished": bool(state.get("finished")),
            "records": len(state.get("records", [])),
            "trace": len(state.get("trace", [])),
            "attempts": len(state.get("attempts", [])),
            "cases": len(state.get("cases", [])),
            "has_report": bool(state.get("report")),
        }
        return result

    @router.post("/api/jobs/{key}/clone")
    def clone_job(key: str):
        payload, migration = clone_request(ctx, store.get(key))
        config = prepare(ctx, payload)
        config["parent_job_id"] = key
        if migration:
            config["migration"] = migration
        return store.create(config)

    @router.post("/api/jobs/{key}/{command}")
    def control(key: str, command: str):
        if command not in ("pause", "resume", "cancel"):
            raise HTTPException(404)
        store.control(key, command)
        return store.get(key)

    @router.get("/api/jobs/{key}/export")
    def export(key: str):
        job = store.get(key)
        protocol_hash = job["config"]["protocol_hash"]
        same_protocol = store.jobs(protocol_hash)
        preregistration = store.preregistration(protocol_hash) or {}
        report = study_report(same_protocol, eligible_dataset_ids=preregistration.get("dataset_ids"),
                              frozen_at=preregistration.get("frozen_at"))
        return Response(export_job(job, report),
                        media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="research-{key}.zip"'})

    @router.get("/api/backup")
    def backup():
        database = store.backup_bytes()
        metadata = {
            "schema": "stance-shift-backup/v1",
            "created_at": now(),
            "service_version": StudyProtocol().version,
            "files": [{"path": "research.sqlite3", "bytes": len(database),
                       "sha256": hashlib.sha256(database).hexdigest()}],
            "excludes": [".env.research", "API keys", "local Ollama models", "research-inputs CSV"],
        }
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            archive.writestr("research.sqlite3", database)
            archive.writestr("manifest.json", json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False))
        stamp = metadata["created_at"].replace("+00:00", "Z").replace(":", "")
        return Response(output.getvalue(), media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="stance-shift-backup-{stamp}.zip"'})

    return router
