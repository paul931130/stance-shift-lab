"""Python API: run one research case end to end without the web service.

    from research_service import StanceShiftResearch

    research = StanceShiftResearch(model="gemini/gemini-2.5-flash")
    result = research.run("NVDA", "2024-12-31")
    print(result["decisions"]["D"]["action"])

Runs go through the same collection, job validation, engine and storage as the
web service, so every case is stored, auditable and visible in the web UI
(``stance-shift serve``) afterwards.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from types import SimpleNamespace
from uuid import uuid4

from .app import _redact
from .collect import collect_dataset
from .engine import Engine, protocol_from
from .protocol import DEFAULT_RESEARCH_MODEL, StudyProtocol, decision_plan
from .settings import Settings
from .storage import JobLeaseLost, Store, now

# A CLI lease untouched this long belongs to a killed process and may be taken over.
STALE_LEASE = timedelta(minutes=30)
GROUP_NAMES = {"A": "單次判斷", "B": "獨立投票", "C": "固定立場辯論", "D": "立場交換辯論"}


class ResearchRunError(RuntimeError):
    """A run stopped part way; the job is saved and can be resumed with ``resume``."""

    def __init__(self, message, job_id):
        super().__init__(message)
        self.job_id = job_id


class StanceShiftResearch:
    """Collect data, run the four decision groups and backtest one case.

    ``data_dir`` defaults to ``RESEARCH_DATA_DIR`` (or ``research-data``), the
    same store the web service uses. Keys saved from the web settings panel or
    the CLI are loaded from there, and environment variables work as well.
    ``model_call`` replaces the model provider (tests, custom providers).
    """

    def __init__(self, data_dir=None, model=None, model_call=None, parallel_workers=None):
        self.store = Store(data_dir or os.getenv("RESEARCH_DATA_DIR", "research-data"))
        self.settings = Settings(self.store.root)
        # RESEARCH_DEMO_MODE=true: the web service's keyless walkthrough. The
        # built-in synthetic dataset and provider replace every external call.
        self.demo_mode = model_call is None and os.getenv("RESEARCH_DEMO_MODE", "").strip().lower() in ("1", "true", "yes", "on")
        if self.demo_mode:
            from .demo import DEMO_MODEL, demo_model
            model, model_call = DEMO_MODEL, demo_model
        self.model = model or os.getenv("RESEARCH_MODEL", DEFAULT_RESEARCH_MODEL)
        self.engine = (Engine(self.store, model_call, parallel_workers) if model_call
                       else Engine(self.store, parallel_workers=parallel_workers))
        self._ctx = SimpleNamespace(store=self.store, demo_mode=False, demo_model_id="",
                                    injected_model_call=model_call is not None)

    def collect(self, ticker, analysis_date, *, refresh=False, use_finbert=False, progress=None):
        """Build or reuse the four-domain dataset for a case; returns its id and agent report."""
        if self.demo_mode:
            from .demo import DEMO_ANALYSIS_DATE, demo_dataset

            demo = demo_dataset()
            if (ticker.upper(), analysis_date) != (demo["ticker"], DEMO_ANALYSIS_DATE):
                raise ValueError(f"展示模式只有 {demo['ticker']} {DEMO_ANALYSIS_DATE} 的合成資料")
            return {"id": self.store.add_dataset(demo), "analysis_date": analysis_date, "reused": True,
                    "limitations": demo.get("limitations", []), "agents": {}}
        return collect_dataset(self.store, ticker.upper(), analysis_date, refresh=refresh,
                               use_finbert=use_finbert, progress=_forward(progress, "collect"))

    def start(self, ticker, analysis_date, *, model=None, dataset_id=None, use_finbert=False,
              refresh=False, progress=None, **options):
        """Validate and store a job without running it; returns the job id.

        ``options`` are the web form's job fields, e.g. ``voting_samples``,
        ``anonymize_ticker``, ``missing_data_policy``, ``allow_small_model``,
        ``allow_low_quality_sentiment`` and ``allow_point_fundamental``.
        """
        from .web.context import JobInput
        from .web.jobs import prepare

        if dataset_id is None:
            dataset_id = self.collect(ticker, analysis_date, refresh=refresh, use_finbert=use_finbert,
                                      progress=progress)["id"]
        payload = JobInput(dataset_id=dataset_id, analysis_date=analysis_date, model=model or self.model, **options)
        # Created paused in one statement: a web worker sharing this store
        # must never claim the job between creation and this process running it.
        return self.store.create(prepare(self._ctx, payload), queued=False)["id"]

    def run(self, ticker, analysis_date, *, progress=None, **kwargs):
        """Run one case to completion and return :func:`summarize` of the job."""
        return self.resume(self.start(ticker, analysis_date, progress=progress, **kwargs), progress=progress)

    def resume(self, job_id, progress=None):
        """Continue a stored job from its last checkpoint until it finishes."""
        report = _forward(progress, "run")
        job, owner = self._take_over(job_id)
        protocol = protocol_from(job["config"]["protocol"])
        total = len(decision_plan(protocol))
        try:
            while not job["state"].get("finished"):
                before = len(job["state"].get("records", []))
                try:
                    state = self.engine.advance(job)
                except Exception as error:
                    state = getattr(error, "state", job["state"])
                    message = f"{type(error).__name__}: {_redact(str(error), os.getenv('RESEARCH_ACCESS_KEY', ''))[:700]}"
                    state.setdefault("attempts", []).append({"at": now(), "status": "error", "message": message})
                    self._save(job_id, state, owner, message)
                    raise ResearchRunError(message, job_id) from error
                state.setdefault("attempts", []).append({"at": now(), "status": "ok", "node": state["trace"][-1]["node"]})
                self._save(job_id, state, owner)
                report(node=state["trace"][-1]["node"], completed=len(state.get("records", [])), total=total,
                       new_records=state.get("records", [])[before:], research=state.get("research", {}),
                       decisions=state.get("decisions"))
                job = self.store.get(job_id)
                if not job["state"].get("finished") and job["status"] in ("paused", "cancelled"):
                    done = "取消" if job["status"] == "cancelled" else "暫停"
                    raise ResearchRunError(f"此實驗已在網頁上被{done}；已完成的步驟都保留", job_id)
        finally:
            if owner:
                self.store.release(job_id, owner)
        return summarize(job)

    def _save(self, job_id, state, owner, error=""):
        try:
            self.store.save_step(job_id, state, error, owner=owner)
        except JobLeaseLost as lost:
            raise ResearchRunError(str(lost), job_id) from lost

    def _take_over(self, job_id):
        """Take exclusive ownership of a stored job; returns the job and this run's lease token."""
        job = self.store.get(job_id)
        if job["state"].get("finished") or job["status"] == "complete":
            return job, None
        if job["status"] == "cancelled":
            raise ValueError("此實驗已取消，不能繼續；請建立新實驗")
        if job["config"]["protocol"].get("version") != StudyProtocol().version:
            raise ValueError("舊版協議的實驗不能用新版引擎繼續；請在網頁用「複製至新版重新執行」")
        owner = f"cli:{uuid4().hex}"
        stale_before = (datetime.now(timezone.utc) - STALE_LEASE).isoformat()
        if not self.store.acquire(job_id, owner, stale_before):
            raise ValueError("此實驗正由其他程序執行（網頁服務的背景 worker 或另一個 stance-shift）；"
                             "請等它結束，或在網頁暫停後再從這裡繼續")
        return self.store.get(job_id), owner


def summarize(job):
    """The decisions and backtest rows a person reads first, from a stored job."""
    state, config = job["state"], job["config"]
    decisions = {}
    for group, item in (state.get("decisions") or {}).items():
        decisions[group] = {"name": GROUP_NAMES[group], "action": item.get("action"),
                            "candidate_action": item.get("candidate_action"),
                            "expected_return_pct": item.get("expected_return_pct"),
                            "confidence": item.get("confidence"), "rationale": item.get("rationale"),
                            "gate_reasons": item.get("gate", {}).get("reasons", [])}
    return {"job_id": job["id"], "status": job["status"], "ticker": config["ticker"],
            "analysis_date": config["analysis_date"], "model": config["protocol"]["model"],
            "dataset_id": config["dataset_id"], "protocol_version": config["protocol"].get("version"),
            "decisions": decisions, "backtest": state.get("cases", []),
            "degraded_research_domains": state.get("report", {}).get("degraded_research_domains", [])}


def _forward(progress, phase):
    if progress is None:
        return lambda **_: None
    return lambda **values: progress(phase=phase, **values)
