"""Shared state handed to every router, plus request models and a task registry."""
from dataclasses import dataclass, field
import threading

from pydantic import BaseModel, Field

from ..engine import Engine
from ..protocol import DEFAULT_RESEARCH_MODEL
from ..security import SessionAuth
from ..settings import Settings
from ..storage import Store, now


@dataclass
class AppContext:
    """Everything one service instance shares across routers."""
    store: Store
    settings: Settings
    engine: Engine
    auth: SessionAuth
    access_key: str
    remote: bool
    demo_mode: bool
    demo_model_id: str
    demo_dataset_id: str | None
    # A test or demo model replaces the real provider, so Ollama checks are skipped.
    injected_model_call: bool
    trusted_proxies: set = field(default_factory=set)


class TaskRegistry:
    """In-memory progress for background tasks (FinBERT, collections).

    Tasks are process-local: a restart forgets them, and the UI tells the user
    to start again. Finished tasks beyond ``history`` are pruned oldest-first.
    """

    def __init__(self, history=50):
        self._tasks, self._lock, self.history = {}, threading.RLock(), history

    def get(self, key):
        with self._lock:
            task = self._tasks.get(key)
            return dict(task) if task is not None else None

    def find(self, predicate):
        with self._lock:
            return next((dict(task) for task in self._tasks.values() if predicate(task)), None)

    def put(self, key, task):
        with self._lock:
            finished = [k for k, t in self._tasks.items() if t.get("stage") in ("complete", "failed") and k != key]
            for stale in finished[:max(0, len(self._tasks) - self.history + 1)]:
                del self._tasks[stale]
            self._tasks[key] = {**task, "updated_at": now()}
            return dict(self._tasks[key])

    def update(self, key, **values):
        with self._lock:
            self._tasks[key].update(values, updated_at=now())


class DownloadInput(BaseModel):
    ticker: str
    analysis_date: str
    refresh: bool = False
    use_finbert: bool = False
    offline_news_only: bool = False
    design: str = "quarterly"


class JobInput(BaseModel):
    dataset_id: str = Field(min_length=1, max_length=128)
    analysis_date: str
    model: str = Field(default=DEFAULT_RESEARCH_MODEL, min_length=1, max_length=200)
    voting_samples: int = 7
    study: str = "study1"
    anonymize_ticker: bool = False
    missing_data_policy: str = "allow_decision"
    allow_point_fundamental: bool = False
    allow_small_model: bool = False
    allow_low_quality_sentiment: bool = False
    design: str = "quarterly"


class BatchInput(BaseModel):
    cases: list[JobInput] = Field(min_length=1, max_length=600)
