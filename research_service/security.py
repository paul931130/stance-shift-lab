"""Session issuance, verification, and login-attempt throttling.

Split out of app.py so the FastAPI route module isn't also the place that
knows how session tokens are signed. Single-owner model: one shared
RESEARCH_ACCESS_KEY, no per-user identity.
"""
from dataclasses import dataclass, field
import hashlib
import hmac
import secrets
import threading
import time

from .logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class SessionAuth:
    access_key: str
    session_ttl: int = 43_200
    login_max_attempts: int = 10
    login_window_seconds: int = 300
    _login_attempts: dict = field(default_factory=dict, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def issue_session(self):
        payload = f"{int(time.time())}.{secrets.token_urlsafe(24)}"
        signature = hmac.new(self.access_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return f"{payload}.{signature}"

    def valid_session(self, token):
        try:
            stamp, _, signature = token.split(".", 2)
            payload = token.rsplit(".", 1)[0]
            expected = hmac.new(self.access_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
            age = time.time() - int(stamp)
            return -60 <= age <= self.session_ttl and hmac.compare_digest(signature.encode(), expected.encode())
        except (AttributeError, TypeError, ValueError):
            return False

    def bearer_ok(self, bearer):
        return bool(bearer) and hmac.compare_digest(bearer.encode(), self.access_key.encode())

    def login_rate_limited(self, client_ip):
        """Throttle repeated login failures per client IP.

        Best-effort in-process guard, not a substitute for the reverse
        proxy's own rate limiting: a restart clears it, and it does not
        share state across multiple worker processes.
        """
        now_ts = time.monotonic()
        with self._lock:
            attempts = [t for t in self._login_attempts.get(client_ip, []) if now_ts - t < self.login_window_seconds]
            self._login_attempts[client_ip] = attempts
            return len(attempts) >= self.login_max_attempts

    def record_login_failure(self, client_ip):
        with self._lock:
            self._login_attempts.setdefault(client_ip, []).append(time.monotonic())
        logger.warning("login failed for client=%s", client_ip)

    def clear_login_failures(self, client_ip):
        with self._lock:
            self._login_attempts.pop(client_ip, None)
