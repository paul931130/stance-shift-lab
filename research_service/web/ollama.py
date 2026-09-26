"""Ollama model inventory, shared by the model picker and job validation."""
import os
import re
import time
from urllib.error import HTTPError, URLError

from ..data import get_json
from ..gputw import ollama_base_url as gputw_ollama_base_url
from ..protocol import DEFAULT_RESEARCH_MODEL, FORMAL_SMALL_MODEL_ALLOWLIST

PARAMETER_SIZE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*[bB]\b")
PROBE_CACHE_SECONDS = 15


def parameter_billions(value):
    """Parse Ollama's model metadata without relying on the model name."""
    match = PARAMETER_SIZE_PATTERN.search(str(value or ""))
    return float(match.group(1)) if match else None


def _unavailable(message, **extra):
    return {"ready": False, "models": [], "details": [], "formal_models": [],
            "formal_ready": False, "default_available": False, **extra, "message": message}


CLOUD_KEYS = {"openrouter": "OPENROUTER_API_KEY", "openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY"}


def _cloud_default():
    """The configured cloud model (non-ollama RESEARCH_MODEL) and whether its key is set."""
    model = os.getenv("RESEARCH_MODEL", DEFAULT_RESEARCH_MODEL).strip()
    if not model or model.startswith("ollama/"):
        return None
    key = CLOUD_KEYS.get(model.split("/", 1)[0])
    return {"model": model, "key_name": key, "ready": bool(key and os.getenv(key, "").strip())}


def _with_cloud(result, cloud):
    """Report a keyed cloud model as available next to (or instead of) Ollama.

    Cloud jobs never depend on Ollama; without this the status chip read
    'MODEL OFFLINE' whenever no Ollama was running (e.g. in a Codespace).
    """
    if not cloud:
        return result
    result = {**result, "cloud": cloud}
    if cloud["ready"]:
        result["ready"] = True
        result["models"] = [*result.get("models", []), cloud["model"]]
        result["details"] = [*result.get("details", []), {"id": cloud["model"], "name": cloud["model"],
                                                           "parameter_size": None, "provider": "cloud"}]
        result["default_available"] = True
    return result


def probe_models(ctx):
    """List installed models from the configured (local or GPUtw) Ollama endpoint."""
    return _with_cloud(_probe_ollama(ctx), None if ctx.demo_mode else _cloud_default())


def _probe_ollama(ctx):
    if ctx.demo_mode:
        return {"ready": True, "models": [ctx.demo_model_id],
                "details": [{"id": ctx.demo_model_id, "name": "Deterministic demo provider",
                             "parameter_size": "synthetic", "context_length": 8192}],
                "configured_default": ctx.demo_model_id, "default_available": True,
                "formal_ready": False, "formal_models": [],
                "message": "目前使用內建合成 demo；不會呼叫外部模型或建立正式資料。"}
    configured_remote_ollama = bool(gputw_ollama_base_url())
    endpoint_label = "遠端 Ollama（GPUtw）" if configured_remote_ollama else "本機 Ollama"
    try:
        ollama_url = (gputw_ollama_base_url() or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")
        headers = {}
        if os.getenv("GPUTW_OLLAMA_API_KEY", "").strip():
            headers["Authorization"] = f"Bearer {os.getenv('GPUTW_OLLAMA_API_KEY').strip()}"
        result = get_json(ollama_url + "/api/tags", headers=headers)
        details = [{"id": "ollama/" + m["name"], "name": m["name"], "digest": m.get("digest"),
                    "size": m.get("size"), "modified_at": m.get("modified_at"),
                    "parameter_size": (m.get("details") or {}).get("parameter_size"),
                    "context_length": (m.get("details") or {}).get("context_length")} for m in result.get("models", [])]
        model_ids = [item["id"] for item in details]
        formal_models = [item["id"] for item in details
                         if ((parameter_billions(item.get("parameter_size")) or 0) >= 14
                             or item["id"].strip().lower() in FORMAL_SMALL_MODEL_ALLOWLIST)]
        configured_default = os.getenv("RESEARCH_MODEL", DEFAULT_RESEARCH_MODEL)
        return {"ready": True, "models": model_ids, "details": details,
                "configured_default": configured_default,
                "default_available": configured_default in model_ids,
                "formal_ready": bool(formal_models), "formal_models": formal_models}
    except HTTPError as error:
        if error.code in (401, 403):
            message = (f"{endpoint_label} 拒絕連線（HTTP {error.code}）。"
                       f"請確認 {endpoint_label} 可從本機存取，或填入端點存取 key；這不是 NoTrade。")
        elif error.code == 429:
            message = "遠端 Ollama 暫時限流（HTTP 429），請稍後重試；這不是 NoTrade。"
        else:
            message = f"模型服務回應 HTTP {error.code}；請稍後重試。這不是 NoTrade。"
        return _unavailable(message, error_code="model_endpoint_http_error", http_status=error.code)
    except (URLError, TimeoutError, OSError):
        return _unavailable(f"模型服務目前無法連線；請確認 {endpoint_label} 仍在執行。這不是 NoTrade。",
                            error_code="model_endpoint_unreachable")
    except Exception:
        return _unavailable("Ollama 尚未連線；請開啟 Ollama，或設定可用的雲端模型金鑰")


class CachedProbe:
    """Reuse a recent probe so preflight, which runs on every form change,
    cannot stall on an unreachable endpoint. Job creation probes live."""

    def __init__(self, ctx, seconds=PROBE_CACHE_SECONDS):
        self.ctx, self.seconds, self._at, self._result = ctx, seconds, 0.0, None

    def __call__(self):
        if time.monotonic() - self._at > self.seconds:
            self._result, self._at = probe_models(self.ctx), time.monotonic()
        return self._result
