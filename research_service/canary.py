"""Synthetic model qualification checks; never used as formal study data."""
from __future__ import annotations

import json

from .models import generate, messages_for, validate_decision
from .protocol import StudyProtocol, decision_plan


def _synthetic_report():
    evidence = [
        {"evidence_id": "canary-technical", "domain": "technical",
         "claim": "Synthetic technical return is mildly positive."},
        {"evidence_id": "canary-fundamental", "domain": "fundamental",
         "comparative": True, "claim": "Synthetic comparable metric: current=10 units; prior=9 units."},
        {"evidence_id": "canary-sentiment", "domain": "sentiment",
         "headline": "Synthetic target headline", "evidence_scope": "target",
         "sentiment_score": 0.2, "direction": "positive"},
        {"evidence_id": "canary-macro", "domain": "macro",
         "claim": "Synthetic macro context is neutral.", "vintage_date": "2024-12-20"},
    ]
    return {"ticker": "SYNTHETIC", "analysis_date": "2024-12-31",
            "research": {domain: {"status": "complete", "summary": "Synthetic canary input.",
                                    "evidence_ids": [f"canary-{domain}"]}
                          for domain in ("technical", "fundamental", "sentiment", "macro")},
            "decision_calibration": {"technical": {"return20": 0.01, "direction": "upward"},
                                      "sentiment": {"target": {"count": 1, "scored_count": 1,
                                                                    "mean_score": 0.2, "direction": "positive"}}},
            "base_rates": {"horizon_sessions": 60, "hold_band_pct": 1.0,
                           "horizon_sigma_pct": 2.0, "basis": "synthetic"},
            "evidence": evidence}


def run_model_canary(protocol: StudyProtocol, provider=generate):
    """Run two short synthetic calls and report qualification checks.

    The first call checks ordinary citation/schema compliance.  The second is
    the switched-round BEAR prompt, which checks whether the provider follows
    the assigned stance.  The function does not create a job or touch stored
    historical data.
    """
    report = _synthetic_report()
    calls = [next(call for call in decision_plan(protocol) if call.key == "a-decision"),
             next(call for call in decision_plan(protocol) if call.key == "d-r2-agent-a")]
    checks = []
    for index, call in enumerate(calls, start=1):
        try:
            result, audit = provider(protocol, messages_for(call, report, [], [], protocol),
                                     seed=protocol.inference_seed + index)
            validate_decision(result, report["evidence"], call)
            checks.append({"call": call.key, "group": call.group, "stance": call.stance,
                           "action": result["action"], "citation_count": len(result["evidence_ids"]),
                           "provider_attempts": audit.get("provider_attempts", 1), "status": "pass"})
        except Exception as error:
            checks.append({"call": call.key, "group": call.group, "stance": call.stance,
                           "status": "fail", "error_type": type(error).__name__,
                           "message": str(error)[:240]})
    return {"status": "pass" if all(item["status"] == "pass" for item in checks) else "fail",
            "qualification": "synthetic_only", "formal_data_touched": False,
            "model": protocol.model, "protocol_hash": protocol.fingerprint,
            "checks": checks,
            "note": "通過只代表能完成最小引用與立場格式檢查，不代表模型可用於正式研究。"}


def result_json(result):
    return json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
