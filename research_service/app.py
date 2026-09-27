"""Single-owner production research service with persistent resumable jobs.

Launch with ``uvicorn research_service.app:create_app --factory``. This module
only assembles the service: shared context, the background research worker,
request protection and error mapping. Routes live in ``research_service.web``.
"""
from contextlib import asynccontextmanager
import asyncio
import os
import threading
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .engine import Engine
from .errors import NotFoundError
from .logging_config import get_logger
from .security import SessionAuth
from .settings import Settings
from .storage import Store, now
from .web import datasets, jobs, studies, system
from .web.context import AppContext

logger = get_logger(__name__)

# Provider credentials that must never appear in a persisted job error.
REDACTED_ENV = ("OPENROUTER_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY", "FRED_API_KEY",
                "ALPHA_VANTAGE_API_KEY", "GPUTW_API_KEY", "GPUTW_OLLAMA_API_KEY", "HF_TOKEN",
                # A contact string, not a secret, but still someone's identifying info.
                "SEC_USER_AGENT")
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                               "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
}


def _env_flag(name):
    return os.getenv(name, "false").strip().lower() in ("1", "true", "yes", "on")


def _env_list(name, default=""):
    return {item.strip() for item in os.getenv(name, default).split(",") if item.strip()}


def _redact(message, access_key):
    if access_key:
        message = message.replace(access_key, "[redacted]")
    for name in REDACTED_ENV:
        if os.getenv(name):
            message = message.replace(os.environ[name], "[redacted]")
    return message


def create_app(store=None, model_call=None, start_worker=True):
    store = store or Store(os.getenv("RESEARCH_DATA_DIR", "research-data"))
    settings = Settings(store.root)
    demo_mode = _env_flag("RESEARCH_DEMO_MODE")
    demo_dataset_id, demo_model_id = None, "ollama/demo-synthetic"
    if demo_mode:
        from .demo import DEMO_MODEL, demo_dataset, demo_model

        demo_model_id = DEMO_MODEL
        demo_dataset_id = store.add_dataset(demo_dataset())
        if model_call is None:
            model_call = demo_model
    access_key = os.getenv("RESEARCH_ACCESS_KEY", "")
    remote = os.getenv("RESEARCH_REMOTE", "false") == "true"
    if remote and len(access_key) < 32:
        raise RuntimeError("Remote mode requires RESEARCH_ACCESS_KEY with at least 32 characters")
    ctx = AppContext(
        store=store, settings=settings,
        engine=Engine(store, model_call) if model_call else Engine(store),
        auth=SessionAuth(access_key), access_key=access_key, remote=remote,
        demo_mode=demo_mode, demo_model_id=demo_model_id, demo_dataset_id=demo_dataset_id,
        injected_model_call=model_call is not None,
        trusted_proxies=_env_list("RESEARCH_TRUSTED_PROXIES"))
    container_local = os.getenv("RESEARCH_CONTAINER_LOCAL", "false") == "true"
    public_origin = os.getenv("RESEARCH_PUBLIC_ORIGIN", "").rstrip("/")
    allowed_hosts = _env_list("RESEARCH_ALLOWED_HOSTS", "localhost,127.0.0.1,::1,testserver")
    stop = threading.Event()

    def work():
        # One worker advances one checkpointed step at a time; see Store.claim for ordering.
        # An exception escaping this loop would silently kill the only worker
        # thread and leave every queued job stuck, so storage errors (e.g. a
        # locked database) are logged and retried after a short back-off.
        while not stop.is_set():
            try:
                job = store.claim()
            except Exception:
                logger.exception("worker could not claim a job; retrying")
                stop.wait(5)
                continue
            if not job:
                stop.wait(.7)
                continue
            state = job["state"]
            try:
                state = ctx.engine.advance(job)
                state["attempts"].append({"at": now(), "status": "ok", "node": state["trace"][-1]["node"]})
                store.save_step(job["id"], state)
            except Exception as error:
                # Persist progress before exposing a bounded diagnostic; never dump provider keys.
                state = getattr(error, "state", state)
                message = f"{type(error).__name__}: {_redact(str(error), access_key)[:700]}"
                logger.error("job %s failed: %s", job["id"], message)
                state["attempts"].append({"at": now(), "status": "error", "message": message})
                try:
                    store.save_step(job["id"], state, message)
                except Exception:
                    # The job stays 'running'; recover() pauses it on the next restart.
                    logger.exception("job %s: could not persist failure state", job["id"])
                    stop.wait(5)

    @asynccontextmanager
    async def lifespan(app):
        store.recover()
        thread = threading.Thread(target=work, daemon=True, name="research-worker")
        if start_worker:
            thread.start()
        yield
        stop.set()
        if start_worker:
            await asyncio.to_thread(thread.join, 5)

    # Keep the generated API contract available for review and integration.
    # The auth middleware below still protects it in remote mode.
    app = FastAPI(title="Stance Shift Research v3", lifespan=lifespan)
    app.state.store = store

    @app.middleware("http")
    async def protect(request, call_next):
        # Rejections below get the same security headers as normal responses.
        response = await guard(request, call_next)
        response.headers.update(SECURITY_HEADERS)
        return response

    async def guard(request, call_next):
        if request.url.hostname not in allowed_hosts:
            return JSONResponse({"detail": "Host not allowed"}, status_code=403)
        if not remote and not container_local and request.client and request.client.host not in ("127.0.0.1", "::1", "testclient"):
            return JSONResponse({"detail": "Local mode accepts loopback clients only"}, status_code=403)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            expected_origin = public_origin or f"{request.url.scheme}://{request.url.netloc}"
            # Local mode also accepts any origin on an allowed host: a forwarding
            # proxy such as Codespaces may rewrite Host or Origin, so exact
            # scheme://host:port equality is too strict there. Remote mode keeps
            # the exact public-origin check.
            local_origin_ok = not remote and urlsplit(origin or "").hostname in allowed_hosts
            if origin and origin.rstrip("/") != expected_origin and not local_origin_ok:
                logger.warning("blocked cross-origin %s from origin=%s host=%s", request.method, origin,
                               request.url.netloc)
                return JSONResponse({"detail": "Cross-origin mutation blocked"}, status_code=403)
            if request.headers.get("content-length", "").isdigit() and int(request.headers["content-length"]) > 6_000_000:
                return JSONResponse({"detail": "Upload exceeds 6 MB"}, status_code=413)
        if access_key and not system.is_public_path(request.url.path):
            bearer = request.headers.get("authorization", "").removeprefix("Bearer ")
            cookie = request.cookies.get("research_session", "")
            if not ctx.auth.bearer_ok(bearer) and not ctx.auth.valid_session(cookie):
                return JSONResponse({"detail": "請先輸入研究室存取金鑰"}, status_code=401)
        return await call_next(request)

    # ValueError is the codebase-wide convention for rejected research input.
    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(NotFoundError)
    async def missing(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=404)

    # Anything else is a bug: log the traceback, but never echo internals
    # (paths, provider URLs, partial keys) back to the browser.
    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        logger.error("unhandled %s on %s %s", type(exc).__name__, request.method, request.url.path, exc_info=exc)
        return JSONResponse({"detail": f"伺服器內部錯誤（{type(exc).__name__}）；詳細原因已記錄在服務日誌"},
                            status_code=500)

    for area in (system, datasets, jobs, studies):
        app.include_router(area.build_router(ctx))
    return app
