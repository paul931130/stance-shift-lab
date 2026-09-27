"""Model knowledge cutoffs: which cases a model could already know the outcome of.

A backtest simulates deciding on the analysis date with only the evidence
available then, but a model whose training data covers the months after that
date may simply remember how the stock moved. Cases are therefore labelled by
where their outcome window falls relative to the model's published knowledge
cutoff, and statistics are reported for each segment. A mechanism effect that
holds before the cutoff but not after it may be an artefact of memory.

Gemini 3.1 Pro, probed without any evidence (27 stock-quarters, 2022-06 to
2024-06), named the 60-session direction correctly 89% of the time against a
59% always-majority baseline, often within 1-2 points of the actual return;
for 2025-03-31 it reported zero confidence and gave the same small guess for
every stock. See docs/knowledge-cutoff.md.
"""
from __future__ import annotations

from datetime import date, timedelta

# cutoff: last day of the published knowledge-cutoff month.
KNOWLEDGE_CUTOFFS = {
    "gemini/gemini-3.1-pro-preview": {
        "cutoff": "2025-01-31",
        "source": "https://ai.google.dev/gemini-api/docs/gemini-3 (Gemini 3 models: knowledge cutoff January 2025)",
    },
}

SEGMENTS = ("before_cutoff", "straddles_cutoff", "after_cutoff")
# 60 trading sessions span about three calendar months.
OUTCOME_WINDOW_FALLBACK = timedelta(days=92)


def cutoff_for(model):
    return KNOWLEDGE_CUTOFFS.get(str(model or "").strip().lower())


def knowledge_segment(job, horizon=60):
    """before_cutoff, straddles_cutoff, after_cutoff, or None when the model's cutoff is not recorded.

    after: the analysis date is after the cutoff, so the model cannot know the outcome.
    before: the whole outcome window ended by the cutoff, so it may.
    straddles: the window crosses the cutoff (e.g. 2024-12-31 for a January 2025 cutoff).
    """
    config = job.get("config", {})
    known = cutoff_for(config.get("protocol", {}).get("model"))
    if not known:
        return None
    cutoff = date.fromisoformat(known["cutoff"])
    analysis = date.fromisoformat(config["analysis_date"])
    if analysis > cutoff:
        return "after_cutoff"
    maturities = [row.get("maturity_date") for row in job.get("state", {}).get("cases", [])
                  if row.get("horizon") == horizon and row.get("maturity_date")]
    maturity = date.fromisoformat(max(maturities)) if maturities else analysis + OUTCOME_WINDOW_FALLBACK
    return "before_cutoff" if maturity <= cutoff else "straddles_cutoff"


def split_by_knowledge(jobs, horizon=60):
    """Group jobs by segment; jobs of models without a recorded cutoff go under ``unknown_cutoff``."""
    groups = {segment: [] for segment in SEGMENTS}
    groups["unknown_cutoff"] = []
    for job in jobs:
        groups[knowledge_segment(job, horizon) or "unknown_cutoff"].append(job)
    return groups
