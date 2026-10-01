"""Stop the GPUtw instance once it has run with an empty research queue for a while.

A rented GPU bills while it is RUNNING, whether or not a case is using it.
This watchdog runs on the service heartbeat. The idle clock starts only when
the instance is *seen* RUNNING while no job is queued or running, so a GPU the
user has just started gets the full ``RESEARCH_GPUTW_AUTOSTOP_MINUTES``
(default 15) to load its model and receive work. A job that fails pauses
itself, so a batch that stalls on a provider error also empties the queue and
ends up here instead of burning GPU time.

It never starts an instance, and it is inert without a GPUtw key and
GPUTW_INSTANCE_ID. A key without the instances:manage scope is tried once and
reported instead of being retried every period.
"""
from __future__ import annotations

import logging
import os
import time

from . import gputw

logger = logging.getLogger(__name__)

DEFAULT_IDLE_MINUTES = 15
STATE_POLL_SECONDS = 60


def idle_minutes() -> float:
    try:
        value = float(os.getenv("RESEARCH_GPUTW_AUTOSTOP_MINUTES", str(DEFAULT_IDLE_MINUTES)))
    except ValueError:
        return DEFAULT_IDLE_MINUTES
    return value if value > 0 else 0.0


class AutoStop:
    def __init__(self, active_jobs, *, clock=time.monotonic, state=gputw.instance_state, stop=gputw.stop_instance):
        self.active_jobs = active_jobs
        self.clock, self.state, self.stop = clock, state, stop
        self.idle_since = None        # first time the GPU was seen RUNNING with an empty queue
        self.checked_at = None
        self.instance_status = None
        self.last_action = None
        self.blocked_key = None       # a key that lacked instances:manage

    def enabled(self) -> bool:
        return bool(gputw.manage_api_key() and gputw.instance_id() and idle_minutes() > 0)

    def tick(self):
        """Called every heartbeat; returns the stop result when it stopped (or tried to stop) the instance."""
        if not self.enabled() or self.blocked_key == gputw.manage_api_key():
            self.idle_since = None
            return None
        if self.active_jobs():
            self.idle_since = None
            return None
        now = self.clock()
        if self.checked_at is not None and now - self.checked_at < STATE_POLL_SECONDS:
            return None
        self.checked_at = now
        self.instance_status = self.state()
        if self.instance_status != "RUNNING":
            self.idle_since = None
            return None
        if self.idle_since is None:
            self.idle_since = now
            return None
        if now - self.idle_since < idle_minutes() * 60:
            return None
        self.idle_since = None
        result = self.stop()
        self.last_action = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **result}
        if result.get("status") == "stopped":
            self.instance_status = "STOPPED"
            logger.warning("GPU idle with an empty research queue for %s min: stopped GPUtw instance %s",
                           idle_minutes(), gputw.instance_id())
        else:
            if result.get("code") == "forbidden":
                self.blocked_key = gputw.manage_api_key()
            logger.error("GPU idle but GPUtw stop failed: %s", result.get("message"))
        return result

    def public(self) -> dict:
        idle = None if self.idle_since is None else round((self.clock() - self.idle_since) / 60, 1)
        return {"enabled": self.enabled() and self.blocked_key != gputw.manage_api_key(),
                "idle_minutes_limit": idle_minutes(), "idle_minutes": idle,
                "last_action": self.last_action}
