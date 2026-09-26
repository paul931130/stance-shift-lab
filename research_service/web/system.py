"""UI assets, login/logout, configuration, settings, GPUtw and model status."""
from dataclasses import asdict
import hmac
import os
from pathlib import Path
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from ..finbert import prepare_model, status as finbert_status
from ..gputw import (active as gputw_active, api_url as gputw_api_url, configured as gputw_configured,
                     instance_id as gputw_instance_id, ollama_base_url as gputw_ollama_base_url,
                     resources as gputw_resources, status as gputw_status)
from ..logging_config import get_logger
from ..protocol import DEFAULT_RESEARCH_MODEL, QUARTER_DATES, TICKERS, StudyProtocol
from ..security import client_address
from .ollama import probe_models

logger = get_logger(__name__)

STATIC = Path(__file__).resolve().parent.parent / "static"
STATIC_ASSETS = ("app.css", "dataset.css", "flow.css")
JS_MODULE_NAME = re.compile(r"[a-z][a-z0-9-]*\.js")
# Paths the login screen needs before a session exists; they hold no research data.
PUBLIC_PATHS = {"/", "/health", "/api/login", *(f"/assets/{name}" for name in STATIC_ASSETS)}


def is_public_path(path):
    return path in PUBLIC_PATHS or path.startswith("/assets/js/")


def build_router(ctx):
    router = APIRouter()

    @router.get("/")
    def home():
        return FileResponse(STATIC / "index.html")

    @router.get("/assets/{name}")
    def asset(name: str):
        if name not in STATIC_ASSETS:
            raise HTTPException(404)
        return FileResponse(STATIC / name)

    @router.get("/assets/js/{name}")
    def js_module(name: str):
        # Frontend ES modules; the strict name pattern rules out path traversal.
        path = STATIC / "js" / name
        if not JS_MODULE_NAME.fullmatch(name) or not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, media_type="text/javascript")

    @router.get("/health")
    def health():
        return {"status": "ok", "version": StudyProtocol().version,
                "authentication_required": bool(ctx.access_key), "demo_mode": ctx.demo_mode}

    @router.post("/api/login")
    async def login(request: Request):
        client_ip = client_address(request.client.host if request.client else None,
                                   request.headers.get("x-forwarded-for", ""), ctx.trusted_proxies)
        if ctx.auth.login_rate_limited(client_ip):
            logger.warning("login rate limited for client=%s", client_ip)
            raise HTTPException(429, "登入嘗試次數過多，請稍後再試")
        data = await request.json()
        if not ctx.access_key or not hmac.compare_digest(str(data.get("key", "")).encode(), ctx.access_key.encode()):
            ctx.auth.record_login_failure(client_ip)
            raise HTTPException(401, "存取金鑰不正確")
        ctx.auth.clear_login_failures(client_ip)
        response = JSONResponse({"ok": True})
        response.set_cookie("research_session", ctx.auth.issue_session(), httponly=True, secure=ctx.remote,
                            samesite="strict", max_age=ctx.auth.session_ttl)
        return response

    @router.post("/api/logout")
    def logout(request: Request):
        ctx.auth.revoke_session(request.cookies.get("research_session", ""))
        response = JSONResponse({"ok": True})
        response.delete_cookie("research_session")
        return response

    @router.get("/api/config")
    def config():
        return {"tickers": TICKERS, "dates": QUARTER_DATES, "default_protocol": asdict(StudyProtocol()),
            "model": ctx.demo_model_id if ctx.demo_mode else os.getenv("RESEARCH_MODEL", DEFAULT_RESEARCH_MODEL),
            "remote": ctx.remote, "demo_mode": ctx.demo_mode, "demo_dataset_id": ctx.demo_dataset_id,
            "parallel_workers": ctx.engine.parallel_workers,
            "study_cases": len(TICKERS) * len(QUARTER_DATES),
            "sources": {"sec": bool(os.getenv("SEC_USER_AGENT")), "alfred": bool(os.getenv("FRED_API_KEY")),
                "alpha_vantage": bool(os.getenv("ALPHA_VANTAGE_API_KEY")),
                "fnspid": bool(os.getenv("FNSPID_NEWS_PATH")), "finbert_local": finbert_status()["installed"],
                "gputw": gputw_configured()},
            "cloud_models": {"openrouter": bool(os.getenv("OPENROUTER_API_KEY")),
                "openai": bool(os.getenv("OPENAI_API_KEY")), "gemini": bool(os.getenv("GEMINI_API_KEY"))},
            "gputw": {"configured": gputw_configured(), "api_url": gputw_api_url(),
                "instance_configured": bool(gputw_instance_id()),
                "ollama_configured": bool(gputw_ollama_base_url())},
            "capabilities": ["settings", "clone", "collect", "readiness", "temporal_splits", "import", "finbert", "run", "batch", "jobs",
                "pause", "resume", "cancel", "export", "backup", "statistics",
                "gputw_status", "gputw_resources", "gputw_active", *(["demo"] if ctx.demo_mode else [])]}

    @router.get("/api/settings")
    def get_settings():
        return ctx.settings.public()

    @router.post("/api/settings")
    async def save_settings(request: Request):
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError("設定內容必須為物件")
        return ctx.settings.save(body.get("values", {}), body.get("clear", []))

    @router.get("/api/gputw/status")
    def gpu_cloud_status():
        """Read GPUtw status; this endpoint never creates or stops compute."""
        return gputw_status()

    @router.get("/api/gputw/resources")
    def gpu_cloud_resources():
        """Read live GPU resources for the explicitly selected instance."""
        return gputw_resources()

    @router.get("/api/gputw/active")
    def gpu_cloud_active():
        """List active GPUtw instances using the read-only instances:read scope."""
        return gputw_active()

    @router.get("/api/finbert/status")
    def finbert_info():
        return finbert_status()

    @router.post("/api/finbert/prepare")
    def finbert_prepare():
        prepare_model()
        return finbert_status()

    @router.get("/api/models")
    def models():
        return probe_models(ctx)

    return router
