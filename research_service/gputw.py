"""Small, read-only GPUtw API client used by the local research service.

GPUtw manages GPU containers; it is not a model provider by itself.  This
module deliberately exposes only read operations so a mistyped setting cannot
start billable compute.  Model traffic is sent separately to the configured
Ollama endpoint (usually an Ollama template running in a GPUtw instance).
"""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


DEFAULT_API_URL = "https://gputw.ai"
_TIMEOUT = 20


class GpuTwError(RuntimeError):
    """A bounded, user-safe error from the GPUtw API."""

    def __init__(self, message: str, *, status_code: int | None = None,
                 code: str = "upstream_error", retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.retryable = retryable


def api_url() -> str:
    return (os.getenv("GPUTW_API_URL", DEFAULT_API_URL).strip() or DEFAULT_API_URL).rstrip("/")


def api_key() -> str:
    return os.getenv("GPUTW_API_KEY", "").strip()


def instance_id() -> str:
    return os.getenv("GPUTW_INSTANCE_ID", "").strip()


def configured() -> bool:
    return bool(api_key())


def ollama_base_url() -> str:
    """Return the optional remote Ollama URL, without leaking credentials."""
    return os.getenv("GPUTW_OLLAMA_BASE_URL", "").strip().rstrip("/")


def _error_from_http(error: HTTPError) -> GpuTwError:
    code_by_status = {401: "unauthorized", 403: "forbidden", 404: "not_found", 429: "rate_limited"}
    code = code_by_status.get(error.code, "upstream_error")
    retryable = error.code == 429 or error.code >= 500
    # Do not return the response body: APIs and reverse proxies sometimes echo
    # request headers, and a token must never appear in a job/UI diagnostic.
    messages = {
        401: "GPUtw API 金鑰無效或已撤銷",
        403: "GPUtw API 金鑰缺少目前查詢所需的 scope",
        404: "GPUtw 執行個體不存在或目前帳號無權限讀取",
        429: "GPUtw API 暫時限流，請稍後重試",
    }
    message = messages.get(error.code, "GPUtw API 暫時無法使用")
    return GpuTwError(message, status_code=error.code, code=code, retryable=retryable)


def _request(path: str, *, requester=None):
    if not configured():
        raise GpuTwError("尚未設定 GPUTW_API_KEY", code="not_configured")
    requester = requester or urlopen
    url = f"{api_url()}/api/{path.lstrip('/')}"
    request = Request(url, headers={
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key()}",
        "User-Agent": "StanceShiftResearch/3 GPUtw integration",
    })
    try:
        with requester(request, timeout=_TIMEOUT) as response:
            payload = json.load(response)
    except HTTPError as error:
        raise _error_from_http(error) from error
    except (URLError, TimeoutError, OSError) as error:
        raise GpuTwError("GPUtw API 網路連線失敗，請確認網路與 API 位址", code="network_error",
                         retryable=True) from error
    except (ValueError, json.JSONDecodeError) as error:
        raise GpuTwError("GPUtw API 回應不是有效 JSON", code="invalid_response") from error
    if not isinstance(payload, dict):
        raise GpuTwError("GPUtw API 回應格式無法辨識", code="invalid_response")
    # Some endpoints wrap their result in {data: ...}; preserve the useful
    # payload shape for callers while accepting both documented forms.
    data = payload.get("data")
    return data if isinstance(data, (dict, list)) else payload


def _result_error(error: GpuTwError) -> dict:
    return {"status": "error", "code": error.code, "retryable": error.retryable,
            **({"http_status": error.status_code} if error.status_code else {}),
            "message": str(error)}


def status() -> dict:
    """Read a configured instance status, or the active list if no ID is set."""
    if not configured():
        return {"configured": False, "status": "not_configured", "api_url": api_url(),
                "instance_configured": bool(instance_id()),
                "ollama_configured": bool(ollama_base_url()),
                "message": "尚未設定 GPUTW_API_KEY；可在設定頁或 setup 填入。"}
    try:
        if instance_id():
            value = _request(f"instances/{quote(instance_id(), safe='')}/status")
            return {"configured": True, "api_url": api_url(), "instance_id": instance_id(),
                    "status": "ready", "instance": value,
                    "ollama_configured": bool(ollama_base_url())}
        value = _request("instances/active")
        instances = value if isinstance(value, list) else value.get("instances", []) if isinstance(value, dict) else []
        return {"configured": True, "api_url": api_url(), "instance_configured": False,
                "status": "ready", "active_instances": instances,
                "ollama_configured": bool(ollama_base_url()),
                "message": "API 已連線；尚未指定 GPUTW_INSTANCE_ID，顯示目前 active 執行個體。"}
    except GpuTwError as error:
        return {"configured": True, "api_url": api_url(),
                "instance_configured": bool(instance_id()),
                "ollama_configured": bool(ollama_base_url()), **_result_error(error)}


def resources() -> dict:
    """Read live resources for the explicitly configured instance."""
    if not configured():
        return {"configured": False, "status": "not_configured",
                "message": "尚未設定 GPUTW_API_KEY；可在設定頁或 setup 填入。"}
    if not instance_id():
        return {"configured": True, "status": "needs_instance",
                "message": "請設定 GPUTW_INSTANCE_ID 後才能讀取 GPU 資源用量。"}
    try:
        return {"configured": True, "status": "ready", "api_url": api_url(),
                "instance_id": instance_id(),
                "resources": _request(f"instances/{quote(instance_id(), safe='')}/resources")}
    except GpuTwError as error:
        return {"configured": True, "api_url": api_url(),
                "instance_id": instance_id(), **_result_error(error)}


def active() -> dict:
    """List active instances without exposing the management key."""
    if not configured():
        return {"configured": False, "status": "not_configured",
                "message": "尚未設定 GPUTW_API_KEY；可在設定頁或 setup 填入。"}
    try:
        value = _request("instances/active")
        return {"configured": True, "status": "ready", "api_url": api_url(),
                "active_instances": value if isinstance(value, list) else value.get("instances", value)}
    except GpuTwError as error:
        return {"configured": True, "api_url": api_url(), **_result_error(error)}
