"""Stop the worker from burning through the queue while the model endpoint is down.

A dead endpoint fails each job in seconds, so without this the worker pauses
the whole queue in a few minutes (2026-10-01: 11 cases in 30 s after the GPUtw
port began returning 404). After `threshold` failed steps in a row the worker
stops claiming jobs; queued jobs stay queued, and every `retry_seconds` a cheap
probe (list the endpoint's models) decides whether to resume.
"""
import threading
import time

from .logging_config import get_logger

logger = get_logger(__name__)


PROVIDER_FAILURE_NAMES = ("HTTPError", "URLError", "TimeoutError", "timeout", "ConnectionError",
                          "RemoteDisconnected", "ConnectionRefusedError", "ConnectionResetError", "ModelIdentityUnavailable", "APIConnectionError",
                          "ServiceUnavailableError", "InternalServerError")


def is_provider_failure(error) -> bool:
    """Transport or provider trouble; a rejected answer or a data problem is not an endpoint failure.

    Step failures carry the underlying errors as text ("technical: HTTPError: ..."), so the
    names are matched in the message as well as in the exception chain.
    """
    seen = error
    while seen is not None:
        if type(seen).__name__ in PROVIDER_FAILURE_NAMES:
            return True
        seen = seen.__cause__ or seen.__context__
    return any(f"{name}:" in str(error) for name in PROVIDER_FAILURE_NAMES)


class Breaker:
    def __init__(self, probe, *, threshold=3, retry_seconds=60, clock=time.monotonic):
        self.probe = probe
        self.threshold = threshold
        self.retry_seconds = retry_seconds
        self.clock = clock
        self.failures = 0
        self.opened_at = None
        self.last_probe = None
        self.lock = threading.Lock()

    @property
    def open(self) -> bool:
        return self.opened_at is not None

    def record(self, ok: bool):
        with self.lock:
            if ok:
                self.failures = 0
                return
            self.failures += 1
            if self.failures >= self.threshold and not self.open:
                self.opened_at = self.last_probe = self.clock()
                logger.error("%s failed steps in a row: holding the queue until the model endpoint answers", self.failures)

    def allow(self) -> bool:
        """True when the worker may claim a job."""
        with self.lock:
            if not self.open:
                return True
            if self.clock() - self.last_probe < self.retry_seconds:
                return False
            self.last_probe = self.clock()
        try:
            ready = bool(self.probe())
        except Exception as error:
            logger.warning("model endpoint probe failed: %s", type(error).__name__)
            ready = False
        if ready:
            with self.lock:
                self.opened_at, self.failures = None, 0
            logger.warning("model endpoint answers again: resuming the queue")
        return ready

    def held_for(self, seconds) -> bool:
        """True once the queue has been held this long (lets the GPU auto-stop stop a broken endpoint)."""
        with self.lock:
            return self.opened_at is not None and self.clock() - self.opened_at >= seconds

    def public(self) -> dict:
        return {"open": self.open, "consecutive_failures": self.failures, "threshold": self.threshold}
