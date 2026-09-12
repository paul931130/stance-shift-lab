"""Centralized logging setup for the research service.

Configured once from RESEARCH_LOG_LEVEL (default INFO). Handlers write to
stderr so container logs pick them up without extra plumbing; this module
never logs request bodies, cookies, or provider API keys.
"""
from logging import Formatter, StreamHandler, getLogger
import os

_CONFIGURED = False


def configure_logging():
    global _CONFIGURED
    if _CONFIGURED:
        return
    level = os.getenv("RESEARCH_LOG_LEVEL", "INFO").upper()
    handler = StreamHandler()
    handler.setFormatter(Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = getLogger("research_service")
    root.setLevel(level)
    root.addHandler(handler)
    root.propagate = False
    _CONFIGURED = True


def get_logger(name):
    configure_logging()
    return getLogger(name)
