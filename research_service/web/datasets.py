"""Dataset snapshots: listing, import, collection tasks, FinBERT scoring and news sources."""
import json
import os
import threading
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

from ..collect import collect_dataset as collect_snapshot
from ..data import check_sentiment_sources, score_sentiment_finbert, validate_dataset
from ..errors import NotFoundError
from ..logging_config import get_logger
from ..protocol import TICKERS, validate_case
from ..readiness import gap_inventory, study_readiness
from ..storage import now
from .context import DownloadInput, TaskRegistry

logger = get_logger(__name__)

RUNNING_COLLECTION = ("queued", "collecting", "finbert")
RUNNING_FINBERT = ("queued", "downloading", "loading", "scoring")


def build_router(ctx):
    router = APIRouter()
    store = ctx.store
    finbert_tasks = TaskRegistry()
    collection_tasks = TaskRegistry()
    start_lock = threading.Lock()  # guards check-then-start of background tasks
    av_archive_task = {"stage": "idle", "message": "尚未開始"}
    av_archive_lock = threading.RLock()

    @router.get("/api/datasets")
    def datasets():
        return store.datasets()

    @router.get("/api/datasets/{key}")
    def dataset_content(key: str):
        return store.dataset(key)

    @router.get("/api/readiness")
    def readiness():
        return study_readiness(store.datasets())

    @router.get("/api/readiness/gaps")
    def readiness_gaps():
        return gap_inventory(store.datasets())

    @router.get("/api/readiness/splits")
    def readiness_splits():
        """Expose the train/validation/test manifest without changing datasets."""
        return study_readiness(store.datasets())["temporal_splits"]

    @router.get("/api/template")
    def template():
        return {"ticker": "NVDA", "kind": "historical", "source": "填入實際來源與授權說明",
            "requested_analysis_date": "2024-12-31", "price_basis": "adjusted_ohlc", "prices": [{"date": "2024-01-02", "open": 0, "high": 0, "low": 0, "close": 0}],
            "evidence": [{"evidence_id": "source-001", "domain": "sentiment", "claim": "填入可查證的新聞摘要",
                "source": "https://來源網址", "available_at": "2024-12-30"}],
            "instructions": "這是格式範本，不能直接執行；請填入至少 61 日正數 OHLC 與可驗證證據。四個面向的名稱為 technical／fundamental／sentiment／macro；macro 證據必須另有 vintage_date。"}

    @router.post("/api/datasets/import")
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

    # ---------- FinBERT scoring (creates a new, content-addressed version) ----------
    def perform_finbert(key):
        def progress(**values):
            finbert_tasks.update(key, **values)
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
        with start_lock:
            if (finbert_tasks.get(key) or {}).get("stage") in RUNNING_FINBERT:
                raise HTTPException(409, "此資料集正在評分，請查看進度")
            finbert_tasks.put(key, {"stage": "queued", "completed": 0, "total": 0})

    @router.get("/api/datasets/{key}/finbert")
    def finbert_progress(key: str):
        store.dataset(key)
        return finbert_tasks.get(key) or {"stage": "idle", "message": "尚未開始；若服務曾重啟，可重試並重用成功評分快取"}

    @router.post("/api/datasets/{key}/finbert")
    def apply_finbert(key: str):
        begin_finbert(key)
        return perform_finbert(key)

    @router.post("/api/datasets/{key}/finbert/start", status_code=202)
    def start_finbert(key: str):
        begin_finbert(key)

        def run():
            try:
                perform_finbert(key)
            except Exception:
                pass  # Failure is exposed by the progress endpoint, never silently marked complete.
        threading.Thread(target=run, daemon=True, name="finbert-task").start()
        return {"dataset_id": key, "stage": "queued"}

    # ---------- Four-domain collection (research_service.collect) ----------
    def collect_dataset(payload, progress=None):
        return collect_snapshot(store, payload.ticker, payload.analysis_date, refresh=payload.refresh,
                                use_finbert=payload.use_finbert, offline_news_only=payload.offline_news_only,
                                progress=progress, apply_finbert=apply_finbert)

    # Terminal scripts keep the synchronous call; the web UI uses the
    # background task below so a slow source never trips the browser timeout.
    @router.post("/api/datasets/download")
    def download(payload: DownloadInput):
        return collect_dataset(payload)

    @router.post("/api/collections", status_code=202)
    def start_collection(payload: DownloadInput):
        validate_case(payload.ticker, payload.analysis_date)
        case = f"{payload.ticker}:{payload.analysis_date}"
        # Sync routes run on a thread pool: check and register atomically so two
        # simultaneous clicks cannot start two collections for the same case.
        with start_lock:
            running = collection_tasks.find(lambda task: task["case"] == case and task["stage"] in RUNNING_COLLECTION)
            if running:
                return running  # A double click joins the running collection.
            task_id = uuid4().hex
            task = collection_tasks.put(task_id, {"id": task_id, "case": case, "stage": "queued",
                                                  "agents": {}, "created_at": now()})

        def progress(**values):
            collection_tasks.update(task_id, **values)

        def run():
            try:
                progress(stage="complete", result=collect_dataset(payload, progress))
            except Exception as error:
                logger.warning("collection task failed case=%s: %s: %s", case, type(error).__name__, error)
                # Validation messages are written for researchers; anything else
                # may embed provider URLs, so expose only the exception type.
                detail = str(error) if isinstance(error, ValueError) else f"{type(error).__name__}：資料蒐集未完成，可重試"
                progress(stage="failed", message=detail)
        threading.Thread(target=run, daemon=True, name="collection-task").start()
        return task

    @router.get("/api/collections/{task_id}")
    def collection_status(task_id: str):
        task = collection_tasks.get(task_id)
        if not task:
            raise NotFoundError("找不到資料蒐集任務；若服務曾重啟，請重新啟動資料 Agent")
        return task

    # ---------- News sources ----------
    @router.post("/api/sources/check")
    def source_check(payload: DownloadInput):
        validate_case(payload.ticker, payload.analysis_date)
        return check_sentiment_sources(payload.ticker, payload.analysis_date)

    @router.get("/api/sources/alpha-vantage-archive")
    def alpha_vantage_archive_status():
        with av_archive_lock:
            return dict(av_archive_task)

    @router.post("/api/sources/alpha-vantage-archive/start", status_code=202)
    def start_alpha_vantage_archive():
        if not os.getenv("ALPHA_VANTAGE_API_KEY", "").strip():
            raise ValueError("尚未設定 ALPHA_VANTAGE_API_KEY；請先在上方設定表單填入")
        with av_archive_lock:
            if av_archive_task.get("stage") == "running":
                raise HTTPException(409, "新聞快取正在更新中，請查看進度")
            av_archive_task.clear()
            av_archive_task.update(stage="running", completed=0, total=0, message="準備中…", updated_at=now())

        def run():
            from ..av_archive import refresh_archive

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

    return router
