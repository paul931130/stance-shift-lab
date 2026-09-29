"""Deterministic, clearly labelled demo data and provider.

The demo is for checking the web workflow without API keys or a local model.
It never reads external data, never pretends to be a formal observation, and
is only enabled when ``RESEARCH_DEMO_MODE=true`` is set explicitly.
"""
from __future__ import annotations

from datetime import date, timedelta
import json
import math

from .data import digest, validate_dataset


DEMO_MODEL = "ollama/demo-synthetic"
DEMO_ANALYSIS_DATE = "2024-12-31"
DEMO_SOURCE = "built-in deterministic demo; not research data"


def _business_days(start: date, count: int) -> list[date]:
    days = []
    cursor = start
    while len(days) < count:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def demo_dataset() -> dict:
    """Return one reproducible synthetic dataset with a full four-domain view."""
    days = _business_days(date(2024, 1, 2), 360)
    prices = []
    previous = 100.0
    for index, day in enumerate(days):
        close = 100.0 + index * 0.045 + 2.4 * math.sin(index / 11) + .7 * math.cos(index / 5)
        opening = previous
        high = max(opening, close) + .8
        low = min(opening, close) - .8
        prices.append({"date": day.isoformat(), "open": opening, "high": high,
                       "low": low, "close": close})
        previous = close
    evidence = [
        {"evidence_id": "demo-technical-1", "domain": "technical",
         "claim": "Synthetic technical trend is mildly positive before the analysis date.",
         "source": DEMO_SOURCE, "available_at": "2024-12-20"},
        {"evidence_id": "demo-fundamental-1", "domain": "fundamental",
         "comparative": True,
         "claim": "Synthetic comparative revenue: current=110; prior=100 units.",
         "source": DEMO_SOURCE, "available_at": "2024-12-20"},
        {"evidence_id": "demo-sentiment-1", "domain": "sentiment",
         "headline": "Synthetic target headline for the demonstration.",
         "claim": "Synthetic target headline for the demonstration.",
         "evidence_scope": "target", "relevance_score": 1.0,
         "sentiment_score": 0.2, "sentiment_label": "positive", "direction": "positive",
         "source": DEMO_SOURCE, "available_at": "2024-12-20"},
        {"evidence_id": "demo-macro-1", "domain": "macro",
         "claim": "Synthetic macro context is neutral.", "source": DEMO_SOURCE,
         "available_at": "2024-12-20", "vintage_date": "2024-12-20"},
    ]
    return validate_dataset({
        "ticker": "NVDA", "kind": "synthetic", "source": DEMO_SOURCE,
        "requested_analysis_date": DEMO_ANALYSIS_DATE, "price_basis": "adjusted_ohlc",
        "retrieved_at": "2025-01-03", "prices": prices, "evidence": evidence,
        "collection_rules": {"version": "built-in-demo-v1", "external_calls": False},
        "limitations": [
            "所有價格與證據都是固定合成內容，只用來展示介面與可追溯流程。",
            "demo 結果不得當作正式案例、模型資格或投資績效。",
        ],
    })


def _evidence_ids_from_research_message(message: str) -> list[str]:
    evidence_text = message.split("Evidence: ", 1)[-1]
    items = json.loads(evidence_text)
    return [item["evidence_id"] for item in items[:6]]


def demo_model(protocol, messages, seed=None, temperature=None):
    """Produce schema-valid deterministic responses without a model call."""
    system = messages[0]["content"]
    if "neutral research agent" in system:
        evidence_ids = _evidence_ids_from_research_message(messages[1]["content"])
        result = {"summary": "Deterministic demo summary of the supplied synthetic evidence.",
                  "evidence_ids": evidence_ids or ["demo-technical-1"],
                  "risks": ["這是合成展示資料，不代表真實研究結論。"], "numeric_claims": []}
    else:
        payload = json.loads(messages[1]["content"])
        evidence = payload.get("report", {}).get("evidence", [])
        evidence_ids = [item["evidence_id"] for item in evidence[:1]] or ["demo-technical-1"]
        if "action MUST be Sell" in system:
            action, expected = "Sell", -4.0
        else:
            action, expected = "Buy", 4.0
        result = {"action": action, "expected_return_pct": expected, "confidence": .75,
                  "rationale": "Deterministic demo response; not a research conclusion.",
                  "evidence_ids": evidence_ids, "risks": ["合成展示資料不具外部效度。"], "numeric_claims": []}
        if "assigned debate stance" in system:
            result["strongest_counterpoint"] = "The opposing stance remains possible in this synthetic example."
        if "role-switch round" in system:
            result["rebutted_claim"] = "Synthetic round-1 claim, retained only for the demo walkthrough."
            result["confidence_shift"] = 0.1 if action == "Buy" else -0.1
    audit = {"prompt_hash": digest(messages), "usage": {"prompt_tokens": 0,
             "completion_tokens": 0, "client_elapsed_seconds": 0.0},
             "raw_response": json.dumps(result, ensure_ascii=False), "provider_attempts": 1,
             "seed": seed, "temperature": temperature, "demo": True}
    return result, audit
