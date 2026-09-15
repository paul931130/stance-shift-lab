"""Single-owner production research service with persistent resumable jobs."""
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import date, timedelta
import asyncio
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import re
import threading
import zipfile

from fastapi import FastAPI, Request, HTTPException, WebSocket
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from .data import (validate_dataset, download_prices, fetch_fundamental, fetch_sentiment,
                   fetch_macro, research_inputs, get_json, score_sentiment_finbert,
                   check_sentiment_sources)
from .engine import Engine
from .finnhub import configured as finnhub_configured, live_snapshot
from .protocol import (DEFAULT_RESEARCH_MODEL, SMALL_MODEL_PATTERN, StudyProtocol, TICKERS,
                       QUARTER_DATES, validate_case, validate_live_symbol)
from .reporting import (study_report, export_job, csv_text, pilot_diagnostics,
                        hold_band_sensitivity)
from .storage import Store, now
from .settings import Settings
from .finbert import status as finbert_status, prepare_model
from .readiness import coverage, gap_inventory, study_readiness
from .splits import classify_analysis_date
from .live_stream import TradeHub
from .logging_config import get_logger
from .security import SessionAuth

logger = get_logger(__name__)

ROOT = Path(__file__).parent
PARAMETER_SIZE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*[bB]\b")


def _parameter_billions(value):
    """Parse Ollama's model metadata without relying on the model name."""
    match = PARAMETER_SIZE_PATTERN.search(str(value or ""))
    return float(match.group(1)) if match else None


class DownloadInput(BaseModel):
    ticker: str
    analysis_date: str
    refresh: bool = False
    use_finbert: bool = False
    offline_news_only: bool = False


class JobInput(BaseModel):
    dataset_id: str = Field(min_length=1, max_length=128)
    analysis_date: str
    model: str = Field(default=DEFAULT_RESEARCH_MODEL, min_length=1, max_length=200)
    voting_samples: int = 7
    study: str = "study1"
    anonymize_ticker: bool = False
    missing_data_policy: str = "allow_decision"
    allow_point_fundamental: bool = False
    allow_small_model: bool = False
    allow_low_quality_sentiment: bool = False


class BatchInput(BaseModel):
    cases: list[JobInput] = Field(min_length=1, max_length=200)


def create_app(store=None, model_call=None, start_worker=True):
    store = store or Store(os.getenv("RESEARCH_DATA_DIR", "research-data"))
    settings = Settings(store.root)
    trade_hub = TradeHub()
    finbert_tasks = {}
    finbert_task_lock = threading.RLock()
    av_archive_task = {"stage": "idle", "message": "尚未開始"}
    av_archive_lock = threading.RLock()
    injected_model_call = model_call is not None
    engine = Engine(store, model_call) if model_call else Engine(store)
    stop = threading.Event()
    access_key = os.getenv("RESEARCH_ACCESS_KEY", "")
    remote = os.getenv("RESEARCH_REMOTE", "false") == "true"
    container_local = os.getenv("RESEARCH_CONTAINER_LOCAL", "false") == "true"
    live_enabled = os.getenv("RESEARCH_ENABLE_LIVE", "false").lower() == "true"
    public_origin = os.getenv("RESEARCH_PUBLIC_ORIGIN", "").rstrip("/")
    if remote and len(access_key) < 32:
        raise RuntimeError("Remote mode requires RESEARCH_ACCESS_KEY with at least 32 characters")
    allowed_hosts = {host.strip() for host in os.getenv("RESEARCH_ALLOWED_HOSTS", "localhost,127.0.0.1,::1,testserver").split(",")}
    auth = SessionAuth(access_key)

    def work():
        while not stop.is_set():
            job = store.claim()
            if not job:
                stop.wait(.7)
                continue
            state = job["state"]
            try:
                state = engine.advance(job)
                state["attempts"].append({"at": now(), "status": "ok", "node": state["trace"][-1]["node"]})
                store.save_step(job["id"], state)
            except Exception as error:
                state = getattr(error, "state", state)
                # Persist progress before exposing a bounded diagnostic; never dump provider keys.
                # SEC_USER_AGENT is a contact string, not a secret, but it is still
                # someone's identifying info and gets the same redaction treatment.
                message = str(error).replace(access_key, "[redacted]") if access_key else str(error)
                for name in ("OPENROUTER_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY", "FRED_API_KEY",
                             "ALPHA_VANTAGE_API_KEY", "FINNHUB_API_KEY", "HF_TOKEN", "SEC_USER_AGENT"):
                    if os.getenv(name):
                        message = message.replace(os.environ[name], "[redacted]")
                message = f"{type(error).__name__}: {message[:700]}"
                logger.error("job %s failed: %s", job["id"], message)
                state["attempts"].append({"at": now(), "status": "error", "message": message})
                store.save_step(job["id"], state, message)

    @asynccontextmanager
    async def lifespan(app):
        store.recover()
        thread = threading.Thread(target=work, daemon=True, name="research-worker")
        if start_worker:
            thread.start()
        yield
        stop.set()
        await trade_hub.close()
        if start_worker:
            await asyncio.to_thread(thread.join, 5)

    app = FastAPI(title="Stance Shift Research v3", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.store = store

    @app.middleware("http")
    async def protect(request, call_next):
        if request.url.hostname not in allowed_hosts:
            return JSONResponse({"detail": "Host not allowed"}, status_code=403)
        if not remote and not container_local and request.client and request.client.host not in ("127.0.0.1", "::1", "testclient"):
            return JSONResponse({"detail": "Local mode accepts loopback clients only"}, status_code=403)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            expected_origin = public_origin or f"{request.url.scheme}://{request.url.netloc}"
            if origin and origin.rstrip("/") != expected_origin:
                return JSONResponse({"detail": "Cross-origin mutation blocked"}, status_code=403)
            if request.headers.get("content-length", "").isdigit() and int(request.headers["content-length"]) > 6_000_000:
                return JSONResponse({"detail": "Upload exceeds 6 MB"}, status_code=413)
        public_paths = {"/", "/health", "/assets/app.js", "/assets/readiness-rules.js",
                        "/assets/app.css", "/assets/dataset.css", "/api/login"}
        if access_key and request.url.path not in public_paths:
            bearer = request.headers.get("authorization", "").removeprefix("Bearer ")
            cookie = request.cookies.get("research_session", "")
            if not auth.bearer_ok(bearer) and not auth.valid_session(cookie):
                return JSONResponse({"detail": "請先輸入研究室存取金鑰"}, status_code=401)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.get("/")
    def home():
        return FileResponse(ROOT / "static/index.html")

    @app.get("/assets/{name}")
    def asset(name: str):
        if name not in ("app.js", "readiness-rules.js", "app.css", "dataset.css"):
            raise HTTPException(404)
        return FileResponse(ROOT / "static" / name)

    @app.get("/health")
    def health():
        return {"status": "ok", "version": StudyProtocol().version, "authentication_required": bool(access_key)}

    @app.post("/api/login")
    async def login(request: Request):
        client_ip = request.client.host if request.client else "unknown"
        if auth.login_rate_limited(client_ip):
            logger.warning("login rate limited for client=%s", client_ip)
            raise HTTPException(429, "登入嘗試次數過多，請稍後再試")
        data = await request.json()
        if not access_key or not hmac.compare_digest(str(data.get("key", "")).encode(), access_key.encode()):
            auth.record_login_failure(client_ip)
            raise HTTPException(401, "存取金鑰不正確")
        auth.clear_login_failures(client_ip)
        response = JSONResponse({"ok": True})
        response.set_cookie("research_session", auth.issue_session(), httponly=True, secure=remote,
                            samesite="strict", max_age=auth.session_ttl)
        return response

    @app.post("/api/logout")
    def logout():
        response = JSONResponse({"ok": True})
        response.delete_cookie("research_session")
        return response

    @app.get("/api/config")
    def config():
        return {"tickers": TICKERS, "dates": QUARTER_DATES, "default_protocol": asdict(StudyProtocol()),
            "model": os.getenv("RESEARCH_MODEL", DEFAULT_RESEARCH_MODEL), "remote": remote,
            "live_enabled": live_enabled,
            "parallel_workers": engine.parallel_workers,
            "study_cases": len(TICKERS) * len(QUARTER_DATES),
            "sources": {"sec": bool(os.getenv("SEC_USER_AGENT")), "alfred": bool(os.getenv("FRED_API_KEY")),
                "alpha_vantage": bool(os.getenv("ALPHA_VANTAGE_API_KEY")),
                "fnspid": bool(os.getenv("FNSPID_NEWS_PATH")), "finbert_local": finbert_status()["installed"],
                "finnhub": finnhub_configured()},
            "cloud_models": {"openrouter": bool(os.getenv("OPENROUTER_API_KEY")),
                "openai": bool(os.getenv("OPENAI_API_KEY")), "gemini": bool(os.getenv("GEMINI_API_KEY"))},
            "capabilities": ["settings", "clone", "collect", "readiness", "temporal_splits", "import", "finbert", "run", "batch", "jobs",
                "pause", "resume", "cancel", "export", "backup", "statistics", "live_snapshot", "live_trades"]}

    @app.get("/api/settings")
    def get_settings():
        return settings.public()

    @app.post("/api/settings")
    async def save_settings(request: Request):
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError("設定內容必須為物件")
        result = settings.save(body.get("values", {}), body.get("clear", []))
        return result

    @app.get("/api/finbert/status")
    def finbert_info():
        return finbert_status()

    @app.post("/api/finbert/prepare")
    def finbert_prepare():
        prepare_model()
        return finbert_status()

    @app.get("/api/models")
    def models():
        try:
            result = get_json(os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/tags")
            details = [{"id": "ollama/" + m["name"], "name": m["name"], "digest": m.get("digest"),
                "size": m.get("size"), "modified_at": m.get("modified_at"),
                "parameter_size": (m.get("details") or {}).get("parameter_size"),
                "context_length": (m.get("details") or {}).get("context_length")} for m in result.get("models", [])]
            model_ids = [item["id"] for item in details]
            formal_models = [item["id"] for item in details
                             if (_parameter_billions(item.get("parameter_size")) or 0) >= 14]
            configured_default = os.getenv("RESEARCH_MODEL", DEFAULT_RESEARCH_MODEL)
            return {"ready": True, "models": model_ids, "details": details,
                    "configured_default": configured_default,
                    "default_available": configured_default in model_ids,
                    "formal_ready": bool(formal_models), "formal_models": formal_models}
        except Exception:
            return {"ready": False, "models": [], "details": [], "formal_models": [],
                    "formal_ready": False, "default_available": False,
                    "message": "Ollama 尚未連線；請開啟 Ollama，或設定可用的雲端模型金鑰"}

    @app.get("/api/datasets")
    def datasets():
        return store.datasets()

    @app.get("/api/datasets/{key}")
    def dataset_content(key: str):
        return store.dataset(key)

    @app.get("/api/readiness")
    def readiness():
        return study_readiness(store.datasets())

    @app.get("/api/readiness/gaps")
    def readiness_gaps():
        return gap_inventory(store.datasets())

    @app.get("/api/readiness/splits")
    def readiness_splits():
        """Expose the train/validation/test manifest without changing datasets."""
        return study_readiness(store.datasets())["temporal_splits"]

    @app.get("/api/template")
    def template():
        return {"ticker": "NVDA", "kind": "historical", "source": "填入實際來源與授權說明",
            "requested_analysis_date": "2024-12-31", "price_basis": "adjusted_ohlc", "prices": [{"date": "2024-01-02", "open": 0, "high": 0, "low": 0, "close": 0}],
            "evidence": [{"evidence_id": "source-001", "domain": "sentiment", "claim": "填入可查證的新聞摘要",
                "source": "https://來源網址", "available_at": "2024-12-30"}],
            "instructions": "這是格式範本，不能直接執行；請填入至少 61 日正數 OHLC 與可驗證證據。四域名稱為 technical/fundamental/sentiment/macro；macro 必須另有 vintage_date。"}

    @app.post("/api/datasets/import")
    async def import_dataset(request: Request, use_finbert: bool = False):
        body = await request.body()
        if len(body) > 6_000_000:
            raise HTTPException(413, "Upload exceeds 6 MB")
        try:
            data = json.loads(body)
        except json.JSONDecodeError as error:
            raise ValueError("上傳內容不是有效 JSON") from error
        data.pop("_collection", None)  # Collection status is server-generated audit metadata.
        if data.get("ticker") not in TICKERS:
            raise ValueError("股票不在研究名單")
        data = validate_dataset(data)
        if data["kind"] == "historical":
            validate_case(data["ticker"], data.get("requested_analysis_date", ""))
        if use_finbert:
            data = validate_dataset(score_sentiment_finbert(data))
        return {"id": store.add_dataset(data), "finbert_applied": use_finbert}

    def perform_finbert(key):
        def progress(**values):
            with finbert_task_lock:
                finbert_tasks[key].update(values, updated_at=now())
        try:
            data = store.dataset(key)
            data["parent_dataset_id"] = key
            enriched = validate_dataset(score_sentiment_finbert(data, progress=progress))
            result = {"id": store.add_dataset(enriched), "parent_dataset_id": key,
                      "finbert_applied": True, "items": enriched["processing"]["sentiment"]["items"]}
            progress(stage="complete", result=result)
            return result
        except Exception as error:
            logger.warning("finbert scoring failed dataset=%s: %s: %s", key, type(error).__name__, error)
            progress(stage="failed", message=f"{type(error).__name__}：評分未完成，原資料未變更；可重試")
            raise

    def begin_finbert(key):
        store.dataset(key)
        with finbert_task_lock:
            task = finbert_tasks.get(key, {})
            if task.get("stage") in ("queued", "downloading", "loading", "scoring"):
                raise HTTPException(409, "此資料集正在評分，請查看進度")
            finbert_tasks[key] = {"stage": "queued", "completed": 0, "total": 0, "updated_at": now()}

    @app.get("/api/datasets/{key}/finbert")
    def finbert_progress(key: str):
        store.dataset(key)
        with finbert_task_lock:
            return dict(finbert_tasks.get(key, {"stage": "idle", "message": "尚未開始；若服務曾重啟，可重試並重用成功評分快取"}))

    @app.post("/api/datasets/{key}/finbert")
    def apply_finbert(key: str):
        begin_finbert(key)
        return perform_finbert(key)

    @app.post("/api/datasets/{key}/finbert/start", status_code=202)
    def start_finbert(key: str):
        begin_finbert(key)
        def run():
            try:
                perform_finbert(key)
            except Exception:
                pass  # Failure is exposed by the progress endpoint, never silently marked complete.
        threading.Thread(target=run, daemon=True, name="finbert-task").start()
        return {"dataset_id": key, "stage": "queued"}

    @app.post("/api/datasets/download")
    def download(payload: DownloadInput):
        validate_case(payload.ticker, payload.analysis_date)
        if not payload.refresh:
            for existing in store.datasets():
                agents = existing.get("_collection", {})
                if (existing.get("ticker") == payload.ticker and existing.get("kind") == "historical"
                        and existing.get("requested_analysis_date") == payload.analysis_date
                        and existing.get("coverage", {}).get("research_ready")):
                    result_id = existing["id"]
                    if payload.use_finbert:
                        result_id = apply_finbert(result_id)["id"]
                    return {"id": result_id, "analysis_date": payload.analysis_date,
                        "limitations": existing.get("limitations", []), "agents": agents,
                        "version": existing.get("version"), "reused": True}
        cutoff = (date.fromisoformat(payload.analysis_date) - timedelta(days=1)).isoformat()
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="collection-agent") as pool:
            futures = {
                "technical": pool.submit(download_prices, payload.ticker, payload.analysis_date),
                "fundamental": pool.submit(fetch_fundamental, payload.ticker, payload.analysis_date),
                "sentiment": pool.submit(fetch_sentiment, payload.ticker, payload.analysis_date,
                                         allow_live=not payload.offline_news_only),
                "macro": pool.submit(fetch_macro, cutoff),
            }
            data = futures["technical"].result()
        agents = {
            "technical": {"status": "complete", "records": len(data["prices"]),
                "message": f"已取得一致還原 OHLC；{data['source']}"},
        }
        for domain, name in (("fundamental", "SEC"), ("sentiment", "新聞"), ("macro", "ALFRED")):
            try:
                evidence, note = futures[domain].result()
                data["evidence"].extend(evidence)
                empty_status = "needs_input" if domain == "sentiment" else "needs_configuration"
                message = f"已取得 {len(evidence)} 筆證據"
                if note:
                    message += f"；附帶來源提醒：{note}"
                agents[domain] = {"status": "complete" if evidence else empty_status,
                    "records": len(evidence), "message": message if evidence else note}
                if note:
                    data["limitations"].append(note)
            except Exception as error:
                logger.warning("dataset collection failed ticker=%s domain=%s: %s: %s",
                               payload.ticker, domain, type(error).__name__, error)
                agents[domain] = {"status": "error", "records": 0,
                    "message": f"{name} 下載失敗：{type(error).__name__}"}
                data["limitations"].append(f"{name} 下載失敗；可重新下載或匯入可驗證的摘要")
        if not any(item["domain"] == "sentiment" for item in data["evidence"]):
            data["limitations"].append("自動新聞來源無可用摘要；情緒域保留缺資料標記，也可匯入具公開時間的新聞摘要")
        sentiment_items = [item for item in data["evidence"] if item["domain"] == "sentiment"]
        if payload.use_finbert and sentiment_items:
            data = score_sentiment_finbert(data)
            count = data["processing"]["sentiment"]["items"]
            agents["sentiment"]["finbert"] = {"status": "complete", "items": count, "model": "ProsusAI/finbert", "input": "headline"}
            agents["sentiment"]["message"] += f"；本機 FinBERT 已完成 {count} 則標題"
        elif payload.use_finbert:
            agents["sentiment"]["finbert"] = {"status": "skipped", "items": 0,
                "model": "ProsusAI/finbert", "input": "headline", "reason": "no_headlines"}
        data["_collection"] = agents
        return {"id": store.add_dataset(validate_dataset(data)), "analysis_date": payload.analysis_date,
            "limitations": data["limitations"], "agents": agents, "reused": False}

    @app.post("/api/sources/check")
    def source_check(payload: DownloadInput):
        validate_case(payload.ticker, payload.analysis_date)
        return check_sentiment_sources(payload.ticker, payload.analysis_date)

    @app.get("/api/sources/alpha-vantage-archive")
    def alpha_vantage_archive_status():
        with av_archive_lock:
            return dict(av_archive_task)

    @app.post("/api/sources/alpha-vantage-archive/start", status_code=202)
    def start_alpha_vantage_archive():
        if not os.getenv("ALPHA_VANTAGE_API_KEY", "").strip():
            raise ValueError("尚未設定 ALPHA_VANTAGE_API_KEY；請先在上方設定表單填入")
        with av_archive_lock:
            if av_archive_task.get("stage") == "running":
                raise HTTPException(409, "新聞快取正在更新中，請查看進度")
            av_archive_task.clear()
            av_archive_task.update(stage="running", completed=0, total=0, message="準備中…", updated_at=now())

        def run():
            from .av_archive import refresh_archive

            def progress(**values):
                with av_archive_lock:
                    av_archive_task.update(values, updated_at=now())
            try:
                refresh_archive(progress=progress)
            except Exception as error:
                logger.warning("alpha vantage archive refresh failed: %s: %s", type(error).__name__, error)
                progress(stage="failed", message=f"{type(error).__name__}：更新未完成，已抓到的資料仍保留；可重試")
        threading.Thread(target=run, daemon=True, name="av-archive-refresh").start()
        with av_archive_lock:
            return dict(av_archive_task)

    def prepare(payload):
        data = store.dataset(payload.dataset_id)
        validate_case(data["ticker"], payload.analysis_date)
        requested_date = data.get("requested_analysis_date")
        if data.get("kind") == "historical" and requested_date != payload.analysis_date:
            shown = requested_date or "未記錄"
            raise ValueError(f"資料集研究日是 {shown}，不能用於 {payload.analysis_date}；請選擇日期完全相同的資料集")
        protocol = StudyProtocol(model=payload.model, voting_samples=payload.voting_samples, study=payload.study,
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
                           and (not quality.get("passes_quality_gate")
                                or not quality.get("finbert_complete")))
        if quality_problem and not payload.allow_low_quality_sentiment:
            reasons = []
            if not quality.get("passes_quality_gate"):
                reasons.append(f"新聞目標相關率 {quality.get('target_relevance_rate', quality.get('ticker_mention_rate', 0.0)):.2f} 未達 0.50")
            if not quality.get("finbert_complete"):
                reasons.append(f"FinBERT 標題評分 {quality.get('finbert_scored', 0)}/{quality.get('items', 0)}")
            raise ValueError("此歷史資料集的新聞品質檢查未通過（" + "；".join(reasons)
                             + "）；請建立完整 FinBERT 評分版本、重新採集，或明確使用資料品質敏感性覆寫")
        fundamental_problem = (data.get("kind") == "historical" and fundamental_quality.get("items", 0) > 0
                               and not fundamental_quality.get("passes_quality_gate"))
        if fundamental_problem and not payload.allow_point_fundamental:
            raise ValueError("此歷史資料集只有不可比較的 SEC 點時欄位；請重新採集新版資料，"
                             "或明確使用點時基本面敏感性覆寫")
        if payload.model.startswith("ollama/") and not injected_model_call:
            installed = models()
            if not installed.get("ready") or payload.model not in installed.get("models", []):
                raise ValueError(f"Ollama 模型 {payload.model} 尚未安裝或目前無法連線")
            model_identity = next(item for item in installed["details"] if item["id"] == payload.model)
            parameter_count = _parameter_billions(model_identity.get("parameter_size"))
            if parameter_count is not None and parameter_count < 14 and not payload.allow_small_model:
                raise ValueError("研究用模型參數量過小；14B 以下模型無法穩定區分 A/B/C/D。請改用 14B 以上，或明確設定 allow_small_model=True 進行冒煙測試")
        else:
            model_identity = {"id": payload.model, "provider": "test_override" if injected_model_call else "cloud_alias",
                              "resolved_at": now()}
        return {"ticker": data["ticker"], "analysis_date": payload.analysis_date,
            "evaluation_split": classify_analysis_date(payload.analysis_date), "dataset_id": payload.dataset_id,
            "dataset_hash": payload.dataset_id, "protocol": asdict(protocol), "protocol_hash": protocol.fingerprint,
            "model_identity": model_identity,
            "quality_overrides": {
                **({"allow_low_quality_sentiment": True, "sentiment_quality": quality}
                   if payload.allow_low_quality_sentiment and quality_problem else {}),
                **({"allow_point_fundamental": True, "fundamental_quality": fundamental_quality}
                   if payload.allow_point_fundamental and fundamental_problem else {}),
            }}

    @app.post("/api/jobs")
    def create_job(payload: JobInput):
        return store.create(prepare(payload))

    @app.post("/api/batches")
    def batch(payload: BatchInput):
        prepared = [prepare(item) for item in payload.cases]
        keys = [(item["ticker"], item["analysis_date"], item["protocol_hash"]) for item in prepared]
        if len(set(keys)) != len(keys):
            raise ValueError("批次內不可重複 case")
        return [store.create(item)["id"] for item in prepared]

    @app.get("/api/live/status")
    def live_status():
        if not live_enabled:
            return {"enabled": False, "configured": False, "provider": "Finnhub",
                    "mode": "backtest_only", "message": "目前是回測 demo 模式；即時 Finnhub 功能已停用。"}
        return {"configured": finnhub_configured(), "provider": "Finnhub",
            "mode": "server_managed_key",
            "message": ("Finnhub 已設定；可取得即時快照並嘗試成交串流"
                        if finnhub_configured() else "尚未設定 FINNHUB_API_KEY；執行 .\\research.ps1 setup 後重啟")}

    @app.get("/api/live/{symbol}")
    def live(symbol: str):
        if not live_enabled:
            raise HTTPException(404, "目前是回測 demo 模式；即時功能尚未開啟")
        return live_snapshot(validate_live_symbol(symbol))

    @app.websocket("/ws/live")
    async def live_trades(websocket: WebSocket):
        if not live_enabled:
            await websocket.close(code=4404)
            return
        host = websocket.url.hostname or ""
        origin = (websocket.headers.get("origin") or "").rstrip("/")
        expected_origin = public_origin or f"{websocket.url.scheme.replace('ws', 'http')}://{websocket.url.netloc}"
        local_clients = ("127.0.0.1", "::1", "testclient")
        if host not in allowed_hosts or (not remote and not container_local and websocket.client and websocket.client.host not in local_clients):
            await websocket.close(code=4403)
            return
        if origin and origin != expected_origin:
            await websocket.close(code=4403)
            return
        if access_key:
            bearer = websocket.headers.get("authorization", "").removeprefix("Bearer ")
            if not auth.bearer_ok(bearer) and not auth.valid_session(websocket.cookies.get("research_session", "")):
                await websocket.close(code=4401)
                return
        raw_symbols = (websocket.query_params.get("symbols") or "").split(",")
        try:
            symbols = list(dict.fromkeys(validate_live_symbol(symbol) for symbol in raw_symbols if symbol.strip()))
        except ValueError:
            await websocket.close(code=4400)
            return
        if not symbols or len(symbols) > 50:
            await websocket.close(code=4400)
            return
        await websocket.accept()
        if not finnhub_configured():
            await websocket.send_json({"type": "error", "message": "尚未設定 FINNHUB_API_KEY"})
            await websocket.close(code=1013)
            return
        queue = None
        async def send_updates():
            while True:
                await websocket.send_json(await queue.get())
        async def receive_disconnect():
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    return
        try:
            queue = await trade_hub.add(symbols)
            sender = asyncio.create_task(send_updates())
            receiver = asyncio.create_task(receive_disconnect())
            done, pending = await asyncio.wait((sender, receiver), return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(sender, receiver, return_exceptions=True)
        except ValueError as error:
            await websocket.send_json({"type": "error", "message": str(error)})
            await websocket.close(code=1013)
        finally:
            if queue is not None:
                await trade_hub.remove(queue)

    def job_summaries():
        return [{"id": j["id"], "status": j["status"], "config": j["config"], "error": j["error"],
            "updated_at": j["updated_at"], "steps": len(j["state"]["records"]), "wants_run": j["wants_run"]} for j in store.jobs()]

    @app.get("/api/jobs")
    def jobs():
        return job_summaries()

    @app.get("/api/dashboard")
    def dashboard(selected: str | None = None):
        return {"jobs": job_summaries(), "selected": store.get(selected) if selected else None}

    @app.get("/api/jobs/{key}")
    def job(key: str):
        return store.get(key)

    @app.post("/api/jobs/{key}/clone")
    def clone_job(key: str):
        original = store.get(key)
        old = original["config"]
        p = old["protocol"]
        legacy = p.get("version") != StudyProtocol().version
        model = p.get("model", DEFAULT_RESEARCH_MODEL)
        old_quality = coverage(store.dataset(old["dataset_id"]), old["analysis_date"]).get("sentiment_quality", {})
        # A user pressing the explicit migration action asks to reproduce a
        # legacy run under the new protocol.  Preserve any legacy model/data
        # exception as auditable overrides rather than failing silently before
        # the replacement job can be inspected or exported.
        allow_small = bool(p.get("allow_small_model", False)) or (legacy and bool(SMALL_MODEL_PATTERN.search(model)))
        old_quality_problem = (old_quality.get("items", 0) > 0
                               and (not old_quality.get("passes_quality_gate")
                                    or not old_quality.get("finbert_complete")))
        allow_low_quality = (bool(old.get("quality_overrides", {}).get("allow_low_quality_sentiment", False))
                             or (legacy and old_quality_problem))
        allow_point_fundamental = (bool(p.get("allow_point_fundamental", False))
                                   or bool(old.get("quality_overrides", {}).get("allow_point_fundamental", False))
                                   or legacy)
        config = prepare(JobInput(dataset_id=old["dataset_id"], analysis_date=old["analysis_date"],
            model=model, study=p.get("study", "study1"), voting_samples=p.get("voting_samples", 7),
            anonymize_ticker=p.get("anonymize_ticker", False),
            missing_data_policy=p.get("missing_data_policy", "allow_decision"),
            allow_point_fundamental=allow_point_fundamental,
            allow_small_model=allow_small, allow_low_quality_sentiment=allow_low_quality))
        config["parent_job_id"] = key
        if legacy:
            config["migration"] = {"from_protocol_version": p.get("version", "unknown"),
                                   "legacy_small_model_override": allow_small,
                                   "legacy_low_quality_sentiment_override": allow_low_quality}
        return store.create(config)

    @app.post("/api/jobs/{key}/{command}")
    def control(key: str, command: str):
        if command not in ("pause", "resume", "cancel"):
            raise HTTPException(404)
        store.control(key, command)
        return store.get(key)

    @app.get("/api/jobs/{key}/export")
    def export(key: str):
        job = store.get(key)
        same_protocol = [item for item in store.jobs() if item["config"]["protocol_hash"] == job["config"]["protocol_hash"]]
        return Response(export_job(job, study_report(same_protocol)), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="research-{key}.zip"'})

    @app.get("/api/backup")
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

    @app.get("/api/studies/{protocol_hash}")
    def report(protocol_hash: str):
        jobs = [j for j in store.jobs() if j["config"]["protocol_hash"] == protocol_hash]
        result = study_report(jobs)
        preregistration = store.preregistration(protocol_hash)
        if preregistration:
            frozen = set(preregistration["dataset_ids"])
            post_freeze = sorted({j["config"]["dataset_id"] for j in jobs
                                   if j["config"].get("dataset_id") not in frozen})
            result["preregistration"] = {**preregistration, "post_freeze_dataset_ids": post_freeze}
        else:
            result["preregistration"] = None
        return result

    @app.post("/api/studies/{protocol_hash}/freeze")
    def freeze_study(protocol_hash: str):
        jobs = [j for j in store.jobs() if j["config"]["protocol_hash"] == protocol_hash]
        dataset_ids = {j["config"]["dataset_id"] for j in jobs if j["config"].get("dataset_id")}
        if not dataset_ids:
            raise ValueError("此協議尚無任何實驗，無法凍結 preregistration")
        return store.freeze(protocol_hash, dataset_ids)

    @app.get("/api/studies/{protocol_hash}/pilot")
    def pilot(protocol_hash: str):
        return pilot_diagnostics([j for j in store.jobs() if j["config"]["protocol_hash"] == protocol_hash])

    @app.get("/api/studies/{protocol_hash}/hold-band")
    def hold_band(protocol_hash: str):
        return hold_band_sensitivity([j for j in store.jobs() if j["config"]["protocol_hash"] == protocol_hash])

    @app.get("/api/studies/{protocol_hash}/summary.csv")
    def summary(protocol_hash: str):
        return Response("\ufeff" + csv_text(report(protocol_hash)["summary"]), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="summary.csv"'})

    return app


app = create_app()
