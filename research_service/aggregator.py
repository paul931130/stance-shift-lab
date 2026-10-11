"""RQ3 Final Aggregator: integrate four standardized Domain Views into one candidate decision.

The aggregator is a domain arm's Adjudicator. Its prompt starts from the exact
v3-1002.3 C/D Adjudicator text (``models.messages_for`` with an adjudication
call), so it inherits the evidence-ID citation rule and the Buy/Sell commitment
rule, and it is validated by the same ``Engine.validated_decision``. Abstain and
InsufficientInfo exist only in Domain Views, never in the aggregator's answer.
The unchanged Gatekeeper still runs after it. Input schema ("views" or
"views_and_transcripts"), input order ("randomized" with a recorded seed, or
"fixed"), memory scope and prompt version come from the RQ3 settings and are
written into the call's audit.
"""
from __future__ import annotations

import json
import random

from .data import digest
from .models import messages_for
from .protocol import DOMAIN_NAMES, DecisionCall

AGGREGATOR_MARKER = "RQ3 Final Aggregator"
VIEW_FIELDS = ("direction", "expected_return_pct", "confidence", "supporting_evidence_ids", "counter_evidence_ids",
               "uncertainty", "information_gaps", "rationale")


def input_order(protocol, settings, config, arm):
    """Domain order shown to the aggregator, and the seed that produced it (None when fixed)."""
    domains = list(DOMAIN_NAMES)
    if settings.aggregator_order == "fixed":
        return domains, None
    seed = (protocol.inference_seed + int(digest(["aggregator-order", config.get("ticker"),
                                                  config.get("analysis_date"), arm])[:8], 16)) % 2_147_483_647
    random.Random(seed).shuffle(domains)
    return domains, seed


def aggregator_text(protocol, settings):
    horizon = protocol.primary_horizon
    return (f" {AGGREGATOR_MARKER} ({settings.aggregator_prompt_version}): in this experiment the debate was split "
            "by domain. Four domain teams (technical, fundamental, sentiment, macro) each debated only their own "
            "evidence and returned a standardized Domain View in report.domain_views for the same "
            f"{horizon}-session horizon. Integrate them into one decision: weigh each view by what its cited "
            "evidence supports, its counter-evidence, uncertainty and information gaps, and resolve cross-domain "
            "conflicts in the rationale instead of counting views. Abstain and InsufficientInfo views carry no "
            "direction and are never votes for either side. The order of the views is arbitrary. Cite only IDs "
            "from report.evidence.")


def build(protocol, settings, config, state, arm, records):
    """Messages, citable evidence and audit metadata for one arm's aggregator call."""
    report = state["report"]
    order, seed = input_order(protocol, settings, config, arm)
    views = {record["domain"]: record.get("output") for record in records if record["kind"] == "view"}
    shown, cited, missing_views = [], [], []
    for domain in order:
        view = views.get(domain)
        if not view:
            # A domain arm that produced no View is shown as carrying no direction (never a
            # vote) and is recorded in the audit, instead of failing the whole aggregator step.
            missing_views.append(domain)
            view = {"direction": "InsufficientInfo", "information_gaps": ["domain view missing"]}
        shown.append({"domain": domain, **{key: view.get(key) for key in VIEW_FIELDS}})
        cited.extend((view.get("supporting_evidence_ids") or []) + (view.get("counter_evidence_ids") or []))
    history = []
    if settings.aggregator_input == "views_and_transcripts":
        for domain in order:
            debate = sorted((record for record in records if record["domain"] == domain and record["kind"] == "debate"),
                            key=lambda record: (record["round"], record["agent"]))
            history.extend({**record, "group": arm} for record in debate)
            for record in debate:
                cited.extend((record.get("output") or {}).get("evidence_ids") or [])
    wanted = set(cited)
    evidence = [item for item in report.get("evidence", []) if item.get("evidence_id") in wanted]
    evidence_fallback = None
    if not evidence:
        # Every view abstained without citing anything. The aggregator still has to commit to
        # Buy or Sell, so it may cite any decision-eligible evidence of the locked report.
        evidence_fallback = "all_domain_namespaces"
        evidence = [item for item in report.get("evidence", [])
                    if item.get("domain") != "fundamental" or item.get("comparative") is True]
    pseudo_report = {"ticker": report.get("ticker"), "analysis_date": report.get("analysis_date"), "research": {},
                     "evidence": evidence, "decision_calibration": {},
                     "base_rates": report.get("base_rates", {}), "degraded_research_domains": []}
    call = DecisionCall(f"{arm.lower()}-aggregator", arm, "adjudication", "aggregator", "NEUTRAL")
    memory = (state.get("memory") or {}).get(arm, []) if settings.aggregator_memory == "same_arm_matured" else []
    messages = messages_for(call, pseudo_report, history, memory, protocol)
    payload = json.loads(messages[1]["content"])
    payload["report"]["domain_views"] = shown
    if settings.aggregator_memory == "none":
        payload.pop("matured_same_group_memory", None)
    messages = [{**messages[0], "content": messages[0]["content"] + aggregator_text(protocol, settings)},
                {**messages[1], "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)}]
    meta = {"prompt_version": settings.aggregator_prompt_version, "input_schema": settings.aggregator_input,
            "input_order": order, "order_mode": settings.aggregator_order, "order_seed": seed,
            "memory": settings.aggregator_memory, "citable_evidence": len(evidence),
            "evidence_fallback": evidence_fallback, "missing_views": missing_views, "prompt_hash": digest(messages)}
    return {"messages": messages, "evidence": evidence, "meta": meta, "call": call}


def run(engine, protocol, built):
    """Call the aggregator through the Generalist decision validator (same retries and checks)."""
    result, audit = engine.validated_decision(protocol, built["call"], built["messages"], built["evidence"])
    audit = dict(audit)
    audit["aggregator"] = built["meta"]
    return result, audit
