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
    # GPU idle watchdog (research_service.autostop); None in tests that build a bare context.
    autostop: object = None
    # Holds the queue while the model endpoint keeps failing (research_service.breaker).
    breaker: object = None


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


class BatchCollectInput(BaseModel):
    tickers: list[str] = Field(min_length=1, max_length=20)
    dates: list[str] = Field(min_length=1, max_length=120)
    refresh: bool = False
    use_finbert: bool = True
    offline_news_only: bool = False
    design: str = "quarterly"


class JobInput(BaseModel):
    dataset_id: str = Field(min_length=1, max_length=128)
    analysis_date: str
    model: str = Field(default=DEFAULT_RESEARCH_MODEL, min_length=1, max_length=200)
    voting_samples: int = 7
    inference_seed: int = Field(default=905, ge=0)
    neutral_report_job_id: str | None = None
    neutral_report_hash: str | None = Field(default=None, min_length=64, max_length=64)
    study: str = "study1"
    anonymize_ticker: bool | None = None
    missing_data_policy: str = "allow_decision"
    allow_point_fundamental: bool = False
    allow_small_model: bool = False
    allow_low_quality_sentiment: bool = False
    design: str = "quarterly"
    # Frozen inference settings; None keeps the protocol default (8192 tokens, one call at a time).
    model_context_length: int | None = None
    ollama_parallel: int | None = None
    # RQ2 Model Router (protocol v3-1006.1). Giving debate_model_b selects the router version;
    # `model` stays the Judge/research model and is model A unless debate_model_a says otherwise.
    debate_model_a: str | None = Field(default=None, max_length=200)
    debate_model_b: str | None = Field(default=None, max_length=200)
    debate_assignments: list[str] | None = None
    # {model id: {"api_base", "timeout_seconds", "api_key_env"}}; never a password or token.
    model_endpoints: dict | None = None
    # RQ3 domain-specialized debate settings (domain_debate.DomainDebateSettings); not combinable with RQ2.
    domain_debate: dict | None = None


class BatchInput(BaseModel):
    cases: list[JobInput] = Field(min_length=1, max_length=600)


class PlanInput(BaseModel):
    """Tickers x analysis dates plus the settings every case of a study shares."""
    tickers: list[str] = Field(min_length=1, max_length=20)
    dates: list[str] = Field(min_length=1, max_length=120)
    model: str = Field(default=DEFAULT_RESEARCH_MODEL, min_length=1, max_length=200)
    voting_samples: int = 7
    inference_seed: int = Field(default=905, ge=0)
    study: str = "study1"
    anonymize_ticker: bool | None = None
    missing_data_policy: str = "allow_decision"
    design: str = "quarterly"
    model_context_length: int | None = None
    ollama_parallel: int | None = None
    debate_model_a: str | None = Field(default=None, max_length=200)
    debate_model_b: str | None = Field(default=None, max_length=200)
    debate_assignments: list[str] | None = None
    model_endpoints: dict | None = None
    domain_debate: dict | None = None
