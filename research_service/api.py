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

import os
from types import SimpleNamespace

from .collect import collect_dataset
from .engine import Engine, protocol_from
from .protocol import DEFAULT_RESEARCH_MODEL, decision_plan
from .settings import Settings
from .storage import Store, now

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
        self.model = model or os.getenv("RESEARCH_MODEL", DEFAULT_RESEARCH_MODEL)
        self.engine = (Engine(self.store, model_call, parallel_workers) if model_call
                       else Engine(self.store, parallel_workers=parallel_workers))
        self._ctx = SimpleNamespace(store=self.store, demo_mode=False, demo_model_id="",
                                    injected_model_call=model_call is not None)

    def collect(self, ticker, analysis_date, *, refresh=False, use_finbert=False, progress=None):
        """Build or reuse the four-domain dataset for a case; returns its id and agent report."""
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
        job = self.store.create(prepare(self._ctx, payload))
        # Keep a running web worker sharing this store from claiming the job.
        self.store.control(job["id"], "pause")
        return job["id"]

    def run(self, ticker, analysis_date, *, progress=None, **kwargs):
        """Run one case to completion and return :func:`summarize` of the job."""
        return self.resume(self.start(ticker, analysis_date, progress=progress, **kwargs), progress=progress)

    def resume(self, job_id, progress=None):
        """Continue a stored job from its last checkpoint until it finishes."""
        report = _forward(progress, "run")
        job = self.store.get(job_id)
        protocol = protocol_from(job["config"]["protocol"])
        total = len(decision_plan(protocol))
        while not job["state"].get("finished"):
            before = len(job["state"].get("records", []))
            try:
                state = self.engine.advance(job)
            except Exception as error:
                state = getattr(error, "state", job["state"])
                message = f"{type(error).__name__}: {str(error)[:700]}"
                state.setdefault("attempts", []).append({"at": now(), "status": "error", "message": message})
                self.store.save_step(job_id, state, message)
                raise ResearchRunError(message, job_id) from error
            state.setdefault("attempts", []).append({"at": now(), "status": "ok", "node": state["trace"][-1]["node"]})
            self.store.save_step(job_id, state)
            report(node=state["trace"][-1]["node"], completed=len(state.get("records", [])), total=total,
                   new_records=state.get("records", [])[before:], research=state.get("research", {}),
                   decisions=state.get("decisions"))
            job = self.store.get(job_id)
        return summarize(job)


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
