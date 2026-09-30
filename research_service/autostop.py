"""Stop the GPUtw instance once the research queue has been idle for a while.

A rented GPU bills while it is RUNNING, whether or not a case is using it.
This watchdog runs on the service heartbeat: whenever no job is queued or
running, it starts an idle clock, and after ``RESEARCH_GPUTW_AUTOSTOP_MINUTES``
(default 15) it stops the configured instance. A job that fails pauses itself,
so a batch that stalls on a provider error also empties the queue and ends up
here instead of burning GPU time.

It never starts an instance, and it is inert unless GPUTW_MANAGE_API_KEY and
GPUTW_INSTANCE_ID are both set.
"""
from __future__ import annotations

import logging
import os
import time

from . import gputw

logger = logging.getLogger(__name__)

DEFAULT_IDLE_MINUTES = 15


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
        self.idle_since = None
        self.last_action = None

    def enabled(self) -> bool:
        return bool(gputw.manage_api_key() and gputw.instance_id() and idle_minutes() > 0)

    def tick(self):
        """Called every heartbeat; returns the stop result when it stopped the instance."""
        if not self.enabled():
            self.idle_since = None
            return None
        if self.active_jobs():
            self.idle_since = None
            return None
        now = self.clock()
        if self.idle_since is None:
            self.idle_since = now
            return None
        if now - self.idle_since < idle_minutes() * 60:
            return None
        # Restart the idle clock either way, so an instance that is already
        # stopped (or unreachable) is polled once per idle period, not every beat.
        self.idle_since = now
        if self.state() != "RUNNING":
            return None
        result = self.stop()
        self.last_action = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **result}
        if result.get("status") == "stopped":
            logger.warning("research queue idle for %s min: stopped GPUtw instance %s",
                           idle_minutes(), gputw.instance_id())
        else:
            logger.error("research queue idle but GPUtw stop failed: %s", result.get("message"))
        return result

    def public(self) -> dict:
        idle = None if self.idle_since is None else round((self.clock() - self.idle_since) / 60, 1)
        return {"enabled": self.enabled(), "idle_minutes_limit": idle_minutes(),
                "idle_minutes": idle, "last_action": self.last_action}
