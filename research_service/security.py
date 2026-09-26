"""Session issuance, verification, and login-attempt throttling.

Split out of app.py so the FastAPI route module isn't also the place that
knows how session tokens are signed. Single-owner model: one shared
RESEARCH_ACCESS_KEY, no per-user identity.
"""
from dataclasses import dataclass, field
import hashlib
import hmac
import ipaddress
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
    # Sessions are signed with a per-process salt, so a restart invalidates
    # every cookie; logout additionally revokes its token for the rest of its TTL.
    _salt: bytes = field(default_factory=lambda: secrets.token_bytes(16), repr=False)
    _revoked: dict = field(default_factory=dict, repr=False)

    def _sign(self, payload):
        return hmac.new(self.access_key.encode() + self._salt, payload.encode(), hashlib.sha256).hexdigest()

    def issue_session(self):
        payload = f"{int(time.time())}.{secrets.token_urlsafe(24)}"
        return f"{payload}.{self._sign(payload)}"

    def _verified(self, token):
        """Return (signature, issued_at) for an authentic, unexpired token, else None."""
        try:
            stamp, _, signature = token.split(".", 2)
            payload = token.rsplit(".", 1)[0]
            age = time.time() - int(stamp)
            if -60 <= age <= self.session_ttl and hmac.compare_digest(signature.encode(), self._sign(payload).encode()):
                return signature, int(stamp)
        except (AttributeError, TypeError, ValueError):
            pass
        return None

    def valid_session(self, token):
        verified = self._verified(token)
        if not verified:
            return False
        with self._lock:
            return verified[0] not in self._revoked

    def revoke_session(self, token):
        verified = self._verified(token)
        if not verified:
            return
        signature, issued_at = verified
        now_ts = time.time()
        with self._lock:
            self._revoked = {key: expiry for key, expiry in self._revoked.items() if expiry > now_ts}
            self._revoked[signature] = issued_at + self.session_ttl

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


def client_address(peer, forwarded_for, trusted_proxies):
    """The address to rate-limit logins by.

    Behind a reverse proxy every request arrives from the proxy, so one bad
    actor could lock the owner out. X-Forwarded-For is honoured only when the
    direct peer is a configured trusted proxy; its rightmost entry is the
    address that proxy itself observed, which a client cannot forge.
    """
    if peer in trusted_proxies and forwarded_for:
        candidate = forwarded_for.split(",")[-1].strip()
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            pass
    return peer or "unknown"
