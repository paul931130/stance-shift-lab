"""Server-side live data with typed panel states, bounded caches and rate control."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import hashlib
import math
import os
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, quote

from .data import get_json
from .protocol import validate_live_symbol

_cache, _request_locks = {}, {}
_cache_lock, _rate_lock = threading.Lock(), threading.Lock()
_next_request = 0.0


class ProviderError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def configured():
    return bool(os.getenv("FINNHUB_API_KEY", "").strip())


def _get(path, params, requester=get_json):
    global _next_request
    token = os.getenv("FINNHUB_API_KEY", "").strip()
    if not token:
        raise ProviderError("unconfigured", "尚未設定 FINNHUB_API_KEY；可在網頁或終端設定")
    base = os.getenv("FINNHUB_BASE_URL", "https://finnhub.io/api/v1").rstrip("/")
    url = f"{base}/{path.lstrip('/')}?{urlencode(params)}"
    identity = hashlib.sha256((token + url).encode()).hexdigest()
    with _cache_lock:
        lock = _request_locks.setdefault(identity, threading.Lock())
    with lock:
        if requester is get_json:
            with _cache_lock:
                cached = _cache.get(identity)
            if cached and time.monotonic() < cached[0]:
                return cached[1]
        for attempt in range(2):
            if requester is get_json:
                with _rate_lock:
                    delay = max(0, _next_request - time.monotonic())
                    _next_request = max(time.monotonic(), _next_request) + 1.1
                time.sleep(delay)
            try:
                payload = requester(url, {"X-Finnhub-Token": token, "User-Agent": "StanceShiftResearch/3"})
                break
            except HTTPError as error:
                states = {401: ("unauthorized", "Finnhub 金鑰無效"), 403: ("forbidden", "目前 Finnhub 方案無此權限"),
                          429: ("rate_limited", "Finnhub 已限流，請稍後重試")}
                if error.code == 429 and attempt == 0:
                    try:
                        delay = min(5, max(1, float(error.headers.get("Retry-After", "1"))))
                    except (ValueError, AttributeError):
                        delay = 1
                    time.sleep(delay)
                    continue
                state, message = states.get(error.code, ("failed", f"Finnhub HTTP {error.code}"))
                raise ProviderError(state, message) from None
        if isinstance(payload, dict) and payload.get("error"):
            # Provider messages can echo request URLs containing credentials.
            raise ProviderError("failed", "Finnhub 拒絕請求；請檢查金鑰、代號與方案權限")
        if requester is get_json:
            ttl = 10 if path == "quote" else 30 if path == "stock/market-status" else 300
            with _cache_lock:
                if len(_cache) >= 500:
                    _cache.clear()
                _cache[identity] = (time.monotonic() + ttl, payload)
        return payload


def finite(value, positive=False):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and (not positive or value > 0)


def quote_snapshot(symbol, requester=get_json):
    symbol = validate_live_symbol(symbol)
    row = _get("quote", {"symbol": symbol}, requester)
    if not isinstance(row, dict) or not row or row.get("c") == 0:
        raise ProviderError("no_data", "Finnhub 未提供此股票的報價")
    if not finite(row.get("c"), True) or not finite(row.get("t"), True):
        raise ProviderError("failed", "Finnhub 報價缺少有效價格或來源時間")
    age = datetime.now(timezone.utc).timestamp() - row["t"]
    return {"symbol": symbol, "current": row["c"], "change": row.get("d"), "change_percent": row.get("dp"),
            "high": row.get("h"), "low": row.get("l"), "open": row.get("o"), "previous_close": row.get("pc"),
            "timestamp": row["t"], "age_seconds": max(0, age), "stale": age > 300 or age < -60,
            "freshness_note": "超過 5 分鐘標示過期；休市時可能是最後成交價"}


def validate_panel(name, payload, today):
    if name == "quote":
        return payload
    if payload is None or payload == {} or payload == []:
        raise ProviderError("no_data", "來源未回傳資料")
    if name == "market_status":
        if not isinstance(payload, dict) or not isinstance(payload.get("isOpen"), bool):
            raise ProviderError("failed", "市場狀態格式錯誤")
        return payload
    if name == "price_target":
        if not isinstance(payload, dict) or not finite(payload.get("targetMean"), True):
            raise ProviderError("no_data", "沒有可用目標價；部分方案不包含此端點")
        return payload
    nested = {"market_holidays": "data", "earnings_calendar": "earningsCalendar"}.get(name)
    rows = payload.get(nested) if nested and isinstance(payload, dict) else payload
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ProviderError("failed", "來源資料格式錯誤")
    field = "atDate" if name == "market_holidays" else "date" if name == "earnings_calendar" else "period"
    if any(not isinstance(row.get(field), str) for row in rows):
        raise ProviderError("failed", "來源資料缺少日期")
    try:
        for row in rows:
            date.fromisoformat(row[field])
    except ValueError:
        raise ProviderError("failed", "來源日期格式錯誤") from None
    if name != "recommendation_trends":
        rows = [row for row in rows if row[field] >= today.isoformat()]
    rows = sorted(rows, key=lambda row: row[field], reverse=name == "recommendation_trends")
    if not rows:
        raise ProviderError("no_data", "此期間沒有資料")
    return {**payload, nested: rows} if nested else rows


def _safe(name, fn, today):
    try:
        return name, {"status": "ready", "data": validate_panel(name, fn(), today)}
    except ProviderError as error:
        return name, {"status": error.status, "message": str(error)}
    except Exception as error:
        return name, {"status": "failed", "message": f"來源處理失敗：{type(error).__name__}"}


def live_snapshot(symbol, requester=get_json, today=None):
    symbol = validate_live_symbol(symbol)
    today = today or datetime.now(ZoneInfo("America/New_York")).date()
    calls = {
        "quote": lambda: quote_snapshot(symbol, requester),
        "market_status": lambda: _get("stock/market-status", {"exchange": "US"}, requester),
        "market_holidays": lambda: _get("stock/market-holiday", {"exchange": "US"}, requester),
        "earnings_calendar": lambda: _get("calendar/earnings", {"from": today.isoformat(), "to": (today + timedelta(days=45)).isoformat(), "symbol": symbol}, requester),
        "recommendation_trends": lambda: _get("stock/recommendation", {"symbol": symbol}, requester),
        "price_target": lambda: _get("stock/price-target", {"symbol": symbol}, requester),
    }
    results = {}
    with ThreadPoolExecutor(max_workers=6, thread_name_prefix="finnhub-live") as pool:
        futures = [pool.submit(_safe, name, call, today) for name, call in calls.items()]
        for future in as_completed(futures):
            name, result = future.result()
            results[name] = result
    ready = sum(panel["status"] == "ready" for panel in results.values())
    return {"mode": "live", "symbol": symbol, "source": "Finnhub", "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "status": "ready" if ready == len(results) else "partial" if ready else "unavailable",
            "trading_enabled": False, "panels": results,
            "note": "即時資料不寫入歷史回測；報價與串流只供觀察，不會送單。"}


def websocket_url():
    token = os.getenv("FINNHUB_API_KEY", "").strip()
    if not token:
        raise ProviderError("unconfigured", "未設定 FINNHUB_API_KEY；無法啟動即時成交串流")
    return os.getenv("FINNHUB_WS_URL", "wss://ws.finnhub.io").rstrip("/") + "?token=" + quote(token, safe="")
