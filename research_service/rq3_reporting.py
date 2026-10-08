"""RQ3 study summary: rule-matched Generalist vs Domain arms, cost, and view agreement.

Descriptive only. Formal inference (paired McNemar, Ledoit--Wolf / block
bootstrap with date clustering) belongs to the preregistered analysis; the
discordant-pair counts here are its inputs. Per-domain views are intermediate
outputs of one case, never four independent observations.
"""
from __future__ import annotations

from collections import Counter

from .domain_debate import GENERALIST_ARM_FOR

RESOURCE_METRICS = ("nominal_calls", "logical_calls", "provider_attempts", "validation_retry_calls", "prompt_tokens",
                    "completion_tokens", "total_tokens", "sum_call_seconds", "critical_path_seconds",
                    "end_to_end_critical_path_seconds")


def _correct(job, group, horizon, cost_model, layer):
    for row in job["state"].get("cases", []):
        if (row.get("group") == group and row.get("horizon") == horizon and row.get("cost_model") == cost_model
                and row.get("decision_layer") == layer and row.get("status") == "complete"):
            return row.get("correct")
    return None


def _resource_totals(diagnostics, arm):
    totals, missing = {}, Counter()
    for item in diagnostics:
        values = item["resources"].get(arm, {})
        for metric in RESOURCE_METRICS:
            value = values.get(metric)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[metric] = totals.get(metric, 0) + value
            else:
                missing[metric] += 1
    n = len(diagnostics)
    return {"cases": n, "totals": totals, "means": {key: value / n for key, value in totals.items()} if n else {},
            "cases_missing_metric": dict(missing)}


def rq3_study_report(jobs, horizon=60, cost_model="corwin_schultz", layer="candidate"):
    complete = [job for job in jobs if job["state"].get("finished") and job["state"].get("rq3_diagnostics")]
    if not complete:
        return {"status": "no_complete_rq3_cases"}
    hashes = sorted({job["config"].get("protocol_hash") for job in complete})
    if len(hashes) > 1:
        return {"status": "mixed_protocols", "protocol_hashes": hashes}
    diagnostics = [job["state"]["rq3_diagnostics"] for job in complete]
    settings = diagnostics[0]["settings"]
    arms = sorted({arm for item in diagnostics for arm in item["resources"]})
    pairs = []
    for item in diagnostics[0]["rule_matched_pairs"]:
        generalist, domain = item["generalist"], item["domain"]
        counts = Counter()
        for job in complete:
            a, b = (_correct(job, generalist, horizon, cost_model, layer),
                    _correct(job, domain, horizon, cost_model, layer))
            if a is None or b is None:
                counts["not_scored"] += 1
            else:
                counts[("both_correct" if a and b else "generalist_only" if a else
                        "domain_only" if b else "both_wrong")] += 1
        scored = sum(counts[key] for key in ("both_correct", "generalist_only", "domain_only", "both_wrong"))
        generalist_cost, domain_cost = _resource_totals(diagnostics, generalist), _resource_totals(diagnostics, domain)
        ratios = {metric: (domain_cost["totals"][metric] / generalist_cost["totals"][metric]
                           if generalist_cost["totals"].get(metric) and metric in domain_cost["totals"] else None)
                  for metric in RESOURCE_METRICS}
        pairs.append({"rule": item["rule"], "generalist": generalist, "domain": domain, "scored_pairs": scored,
                      "outcomes": dict(counts),
                      "accuracy": {generalist: (counts["both_correct"] + counts["generalist_only"]) / scored
                                   if scored else None,
                                   domain: (counts["both_correct"] + counts["domain_only"]) / scored
                                   if scored else None},
                      "discordant": {"generalist_only": counts["generalist_only"],
                                     "domain_only": counts["domain_only"]},
                      "domain_over_generalist_cost": ratios})
    agreement = {}
    for arm in arms:
        if arm not in GENERALIST_ARM_FOR:
            continue
        rows = [item["agreement"][arm] for item in diagnostics if arm in item["agreement"]]
        agreement[arm] = {
            "patterns": dict(Counter(row["pattern"] or f"incomplete:{row['valid_binary']}_binary" for row in rows)),
            "abstain_views": sum(row["abstain"] for row in rows),
            "insufficient_info_views": sum(row["insufficient_info"] for row in rows),
            "final_relation": dict(Counter(row["final_relation"] or "not_applicable" for row in rows))}
    return {"status": "complete", "protocol_hash": hashes[0], "cases": len(complete), "horizon": horizon,
            "cost_model": cost_model, "decision_layer": layer, "settings": settings,
            "compute_matching": diagnostics[0]["compute_matching"],
            "resources": {arm: _resource_totals(diagnostics, arm) for arm in arms},
            "rule_matched_pairs": pairs, "agreement": agreement,
            "note": "Descriptive. Formal tests (paired McNemar, Ledoit-Wolf/block bootstrap, date clusters) are "
                    "not run here; per-domain views are not independent samples."}
