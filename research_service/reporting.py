"""Study aggregation, pilot gates and reproducible export artifacts."""
from copy import deepcopy
import csv
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import io
import json
import math
import platform
import statistics
import zipfile

import numpy as np

from .backtest import metrics
from .statistics import (aligned_portfolio_returns, mcnemar, jobson_korkie_memmel,
                         ledoit_wolf_block, holm_adjust)


EXPORT_SCHEMA = "stance-shift-export/v1"
MIN_CASES_FOR_INFERENCE = 30
GROUPS = "ABCD"


def _is_complete(job):
    return job.get("status") == "complete" and bool(job.get("state", {}).get("finished"))


def _completed_unique(jobs):
    """Return first valid result per case without mutating rerun audit records."""
    completed = [job for job in jobs if _is_complete(job)]
    degraded = [job for job in completed
                if job.get("state", {}).get("report", {}).get("degraded_research_domains")]
    usable = [job for job in completed if job not in degraded]
    if not usable:
        return [], {"completed": len(completed), "degraded": len(degraded), "duplicates": 0}
    hashes = {job["config"].get("protocol_hash") for job in usable}
    if len(hashes) != 1:
        raise ValueError("不同協議、模型或資料類型不可合併統計")
    unique = {}
    for job in sorted(usable, key=lambda item: item.get("created_at", "")):
        config = job["config"]
        unique.setdefault((config.get("ticker"), config.get("analysis_date")), job)
    return list(unique.values()), {"completed": len(completed), "degraded": len(degraded),
                                    "duplicates": len(usable) - len(unique)}


def _layer(row):
    return row.get("decision_layer", "gated")


def _numeric(values):
    return [float(value) for value in values
            if isinstance(value, (int, float)) and math.isfinite(float(value))]


def _mean_sd(values):
    values = _numeric(values)
    if not values:
        return {"mean": None, "n": 0, "sd": None}
    return {"mean": float(statistics.fmean(values)), "n": len(values),
            "sd": float(statistics.stdev(values)) if len(values) > 1 else 0.0}


def _case_panel(jobs, horizon, cost_model, decision_layer):
    """Create an aligned date × case × group panel, filling inactive sleeves with cash."""
    cases, daily = {}, {}
    for job in jobs:
        key = (job["config"].get("ticker"), job["config"].get("analysis_date"))
        relevant = [row for row in job["state"].get("cases", [])
                    if row.get("horizon") == horizon and row.get("cost_model") == cost_model
                    and _layer(row) == decision_layer and row.get("status") == "complete"]
        by_group = {group: next((row for row in relevant if row.get("group") == group), None)
                    for group in GROUPS}
        if any(row is None for row in by_group.values()):
            continue
        cases[key] = by_group
        selected_daily = [row for row in job["state"].get("daily", [])
                          if row.get("horizon") == horizon and row.get("cost_model") == cost_model
                          and _layer(row) == decision_layer]
        daily[key] = {group: [row for row in selected_daily if row.get("group") == group]
                      for group in GROUPS}
    if not cases:
        return {"cases": {}, "portfolios": {basis: {group: [] for group in GROUPS}
                                                for basis in ("all", "active")},
                "dates": {"all": [], "active": []}, "benchmark": []}
    dates = sorted({row.get("date") for group_rows in daily.values() for rows in group_rows.values()
                    for row in rows if row.get("date")})
    case_keys = sorted(cases)
    date_index = {value: index for index, value in enumerate(dates)}
    case_index = {value: index for index, value in enumerate(case_keys)}
    panel = np.zeros((len(dates), len(case_keys), len(GROUPS)), dtype=float)
    benchmark = np.zeros((len(dates), len(case_keys)), dtype=float)
    benchmark_seen = np.zeros((len(dates), len(case_keys)), dtype=bool)
    active = np.zeros((len(dates), len(case_keys), len(GROUPS)), dtype=bool)
    for key in case_keys:
        for group_index, group in enumerate(GROUPS):
            action = cases[key][group].get("action")
            for row in daily[key][group]:
                day_index = date_index.get(row.get("date"))
                if day_index is None:
                    continue
                stock_index = case_index[key]
                value = row.get("return")
                if isinstance(value, (int, float)) and math.isfinite(float(value)):
                    panel[day_index, stock_index, group_index] = float(value)
                if action in ("Buy", "Sell"):
                    active[day_index, stock_index, group_index] = True
                if not benchmark_seen[day_index, stock_index]:
                    base = row.get("benchmark_return")
                    if isinstance(base, (int, float)) and math.isfinite(float(base)):
                        benchmark[day_index, stock_index] = float(base)
                    benchmark_seen[day_index, stock_index] = True
    fixed = aligned_portfolio_returns(panel)
    portfolios = {"all": {group: fixed[:, index].tolist() for index, group in enumerate(GROUPS)},
                  "active": {group: [] for group in GROUPS}}
    active_date_mask = np.all(np.any(active, axis=1), axis=1)
    for group_index, group in enumerate(GROUPS):
        portfolios["active"][group] = [float(np.mean(panel[day, active[day, :, group_index], group_index]))
                                        for day in np.flatnonzero(active_date_mask)]
    return {"cases": cases, "portfolios": portfolios,
            "dates": {"all": dates, "active": [dates[index] for index in np.flatnonzero(active_date_mask)]},
            "benchmark": np.mean(benchmark, axis=1).tolist()}


def _case_metrics(rows, compute_usages):
    directional = [row for row in rows if row.get("correct") is not None]
    holds = [row for row in rows if row.get("action") == "Hold"]
    justified = [row for row in holds if row.get("hold_was_justified") is not None]
    opportunities = _numeric(row.get("hold_opportunity_cost") for row in holds)
    usage_prompt = _numeric(item.get("prompt_tokens") for item in compute_usages)
    usage_completion = _numeric(item.get("completion_tokens") for item in compute_usages)
    usage_wall = _numeric(item.get("wall_seconds") for item in compute_usages)
    total = len(rows)
    return {
        "cases": total, "directional_cases": len(directional),
        "coverage": len(directional) / total if total else None,
        "selective_accuracy": (sum(bool(row["correct"]) for row in directional) / len(directional)
                               if directional else None),
        "hold_rate": sum(row.get("action") == "Hold" for row in rows) / total if total else None,
        "no_trade_rate": sum(row.get("action") == "NoTrade" for row in rows) / total if total else None,
        "active_rate": sum(row.get("action") in ("Buy", "Sell") for row in rows) / total if total else None,
        "hold_justified_rate": (sum(bool(row["hold_was_justified"]) for row in justified) / len(justified)
                                if justified else None),
        "hold_opportunity_cost_mean": float(statistics.fmean(opportunities)) if opportunities else None,
        "insolvent_cases": sum(bool(row.get("insolvent")) for row in rows),
        "prompt_tokens_mean": float(statistics.fmean(usage_prompt)) if usage_prompt else None,
        "completion_tokens_mean": float(statistics.fmean(usage_completion)) if usage_completion else None,
        "wall_seconds_mean": float(statistics.fmean(usage_wall)) if usage_wall else None,
        "missing_usage_cases": sum(int(item.get("missing_usage_calls", 0) or 0) for item in compute_usages),
    }


def _comparison(rows, portfolios, protocol, group, horizon, cost_model, decision_layer, portfolio_basis):
    lookup = {key: row for key, row in rows[group]}
    paired = [(row.get("correct"), lookup[key].get("correct")) for key, row in rows["D"]
              if key in lookup and row.get("correct") is not None and lookup[key].get("correct") is not None]
    endpoint = ("primary" if decision_layer == "candidate" and horizon == protocol.get("primary_horizon", 60)
                and cost_model == "corwin_schultz" and portfolio_basis == "all" else "robustness")
    result = {"groups": ["D", group], "horizon": horizon, "cost_model": cost_model,
              "decision_layer": decision_layer, "portfolio_basis": portfolio_basis,
              "endpoint": endpoint, "portfolio_dates": len(portfolios["D"])}
    result["mcnemar"] = (mcnemar(np.array([first for first, _ in paired], dtype=bool),
                                  np.array([second for _, second in paired], dtype=bool)) if paired
                          else {"status": "no_paired_directional_cases", "pvalue": None})
    for name, function in (("jobson_korkie", jobson_korkie_memmel), ("ledoit_wolf", ledoit_wolf_block)):
        try:
            kwargs = {} if name == "jobson_korkie" else {
                "block_length": protocol.get("bootstrap_block_length", 20),
                "replicates": protocol.get("bootstrap_replicates", 1999),
                "seed": protocol.get("bootstrap_seed", 905),
            }
            result[name] = function(portfolios["D"], portfolios[group], **kwargs)
        except ValueError as error:
            result[name] = {"status": "not_estimable", "reason": str(error), "pvalue": None}
    return result


def _completeness(jobs):
    d_values, c_values, paired = [], [], []
    for job in jobs:
        diagnostic = job["state"].get("completeness_diagnostic", {})
        d_value = diagnostic.get("mean_novelty_rate")
        c_value = diagnostic.get("control", {}).get("mean_novelty_rate")
        if isinstance(d_value, (int, float)) and math.isfinite(float(d_value)):
            d_values.append(float(d_value))
        if isinstance(c_value, (int, float)) and math.isfinite(float(c_value)):
            c_values.append(float(c_value))
        if (isinstance(d_value, (int, float)) and isinstance(c_value, (int, float))
                and math.isfinite(float(d_value)) and math.isfinite(float(c_value))):
            paired.append(float(d_value) - float(c_value))
    difference = _mean_sd(paired)
    return {"D": _mean_sd(d_values), "C": _mean_sd(c_values),
            "paired_difference": {**difference, "status": "descriptive_only",
                "reason": "Novelty is a paired diagnostic; registered return tests do not test text-overlap outcomes."}}


def study_report(jobs, *, include_inference=True):
    complete, excluded = _completed_unique(jobs)
    if not complete:
        return {"status": "no_completed_cases", "summary": [], "comparisons": [], "completeness": _completeness([]),
                "excluded_incomplete_runs": len(jobs) - excluded["completed"],
                "excluded_degraded_research_runs": excluded["degraded"]}
    protocol = complete[0]["config"].get("protocol", {})
    layers = sorted({_layer(row) for job in complete for row in job["state"].get("cases", [])}) or ["gated"]
    summary, comparisons = [], []
    for horizon in protocol.get("horizons", (30, 60, 90)):
        for cost_model in protocol.get("cost_models", ("zero", "corwin_schultz")):
            for decision_layer in layers:
                panel = _case_panel(complete, horizon, cost_model, decision_layer)
                case_rows = panel["cases"]
                rows = {group: [(key, values[group]) for key, values in case_rows.items()] for group in GROUPS}
                compute = {group: [job["state"].get("compute_usage", {}).get(group, {}) for job in complete
                                   if (job["config"].get("ticker"), job["config"].get("analysis_date")) in case_rows]
                           for group in GROUPS}
                for portfolio_basis in ("all", "active"):
                    portfolios = panel["portfolios"][portfolio_basis]
                    for group in GROUPS:
                        summary.append({"group": group, "horizon": horizon, "cost_model": cost_model,
                            "decision_layer": decision_layer, "portfolio_basis": portfolio_basis,
                            **_case_metrics([row for _, row in rows[group]], compute[group]),
                            **metrics(portfolios[group])})
                    if portfolio_basis == "all":
                        summary.append({"group": "BuyAndHoldActiveWindows", "horizon": horizon,
                            "cost_model": cost_model, "decision_layer": decision_layer,
                            "portfolio_basis": portfolio_basis, **metrics(panel["benchmark"]),
                            "cases": len(case_rows), "directional_cases": None, "coverage": None,
                            "selective_accuracy": None, "hold_rate": None, "no_trade_rate": None,
                            "active_rate": None, "hold_justified_rate": None,
                            "hold_opportunity_cost_mean": None, "insolvent_cases": None,
                            "prompt_tokens_mean": None, "completion_tokens_mean": None,
                            "wall_seconds_mean": None, "missing_usage_cases": None})
                    if include_inference and len(complete) >= MIN_CASES_FOR_INFERENCE:
                        for group in "ABC":
                            comparisons.append(_comparison(rows, portfolios, protocol, group, horizon,
                                                           cost_model, decision_layer, portfolio_basis))
    for horizon in protocol.get("horizons", (30, 60, 90)):
        for cost_model in protocol.get("cost_models", ("zero", "corwin_schultz")):
            for decision_layer in layers:
                for portfolio_basis in ("all", "active"):
                    for method in ("mcnemar", "jobson_korkie", "ledoit_wolf"):
                        family = [comparison[method] for comparison in comparisons
                                  if comparison["horizon"] == horizon and comparison["cost_model"] == cost_model
                                  and comparison["decision_layer"] == decision_layer
                                  and comparison["portfolio_basis"] == portfolio_basis
                                  and comparison[method].get("pvalue") is not None]
                        for item, adjusted in zip(family, holm_adjust([item["pvalue"] for item in family])):
                            item["holm_pvalue"] = adjusted
    inferred = include_inference and len(complete) >= MIN_CASES_FOR_INFERENCE
    return {"status": "complete" if inferred else "insufficient_cases",
            "protocol_hash": complete[0]["config"].get("protocol_hash"), "unique_cases": len(complete),
            "required_cases": MIN_CASES_FOR_INFERENCE, "excluded_duplicate_runs": excluded["duplicates"],
            "excluded_incomplete_runs": len(jobs) - excluded["completed"],
            "excluded_degraded_research_runs": excluded["degraded"], "summary": summary,
            "comparisons": comparisons, "completeness": _completeness(complete),
            "conventions": [
                "Primary analysis: decision_layer=candidate, horizon=60, cost_model=corwin_schultz, portfolio_basis=all",
                "Candidate actions measure the decision mechanism; gated actions are a separate risk-control sensitivity layer",
                "Open-to-open: entry at t+1 open, exit at t+horizon+1 open",
                "Short positions are floored at -100%; insolvent cases are retained and flagged, not excluded",
                "Hold is scored as abstention: reported via coverage, selective accuracy, and hold opportunity cost, never as a free correct answer",
                "portfolio_basis=all holds equal fixed case weights and treats inactive sleeves as cash; portfolio_basis=active uses changing active-sleeve weights as sensitivity only",
                "Compute matching is by call count (A=1, B=7, C=7, D=7); token counts differ by arm and are reported, not equalised",
                "First valid completed run per ticker/date is fixed for aggregate analysis; later reruns remain separate audit artifacts",
                "McNemar uses mutually directional cases; Holm correction is applied within each horizon/cost/layer/basis/method family",
                "Formal inference is withheld until at least 30 unique completed historical cases are available",
                "Runs using deterministic research-source fallback are excluded from formal aggregate statistics",
            ]}


def _decision_action(decision):
    return decision.get("candidate_action", decision.get("action"))


def _primary_candidate_row(job, group):
    protocol = job["config"].get("protocol", {})
    return next((row for row in job["state"].get("cases", [])
                 if row.get("group") == group and _layer(row) == "candidate"
                 and row.get("horizon") == protocol.get("primary_horizon", 60)
                 and row.get("cost_model") == "corwin_schultz"), None)


def pilot_diagnostics(jobs):
    """Decide whether a pilot can identify A/B/C/D before a large experiment."""
    complete, _ = _completed_unique(jobs)
    actions = {group: [] for group in GROUPS}
    finals = {group: [] for group in GROUPS}
    expected = {group: [] for group in GROUPS}
    inside = {group: [] for group in GROUPS}
    mismatch = {group: [] for group in GROUPS}
    outside_correct = {group: [] for group in GROUPS}
    inside_correct = {group: [] for group in GROUPS}
    hold_justified = {group: [] for group in GROUPS}
    vote_agreement = []
    pairwise = {"D_vs_A": [], "D_vs_B": [], "D_vs_C": [], "C_vs_A": [], "B_vs_A": []}
    identical = []
    for job in complete:
        decisions = job["state"].get("decisions", {})
        if any(group not in decisions for group in GROUPS):
            continue
        case_actions = {}
        for group in GROUPS:
            decision = decisions[group]
            candidate, final = _decision_action(decision), decision.get("action")
            actions[group].append(candidate)
            finals[group].append(final)
            case_actions[group] = candidate
            value, band = decision.get("expected_return_pct"), decision.get("hold_band_pct")
            if isinstance(value, (int, float)) and math.isfinite(float(value)):
                expected[group].append(float(value))
                if isinstance(band, (int, float)) and math.isfinite(float(band)):
                    in_band = abs(float(value)) <= float(band)
                    inside[group].append(in_band)
                    row = _primary_candidate_row(job, group)
                    if row and row.get("correct") is not None:
                        (inside_correct if in_band else outside_correct)[group].append(bool(row["correct"]))
            if "model_action" in decision and "derived_action" in decision:
                mismatch[group].append(decision["model_action"] != decision["derived_action"])
            row = _primary_candidate_row(job, group)
            if row and row.get("action") == "Hold" and row.get("hold_was_justified") is not None:
                hold_justified[group].append(bool(row["hold_was_justified"]))
        for key, left, right in (("D_vs_A", "D", "A"), ("D_vs_B", "D", "B"),
                                 ("D_vs_C", "D", "C"), ("C_vs_A", "C", "A"), ("B_vs_A", "B", "A")):
            pairwise[key].append(case_actions[left] != case_actions[right])
        identical.append(len(set(case_actions.values())) == 1)
        b_value = decisions["B"].get("vote_agreement")
        if isinstance(b_value, (int, float)) and math.isfinite(float(b_value)):
            vote_agreement.append(float(b_value))
    cases = len(identical)
    def rate(values, predicate=lambda value: bool(value)):
        return sum(predicate(value) for value in values) / len(values) if values else None
    result = {
        "cases": cases,
        "hold_rate": {group: rate(actions[group], lambda value: value == "Hold") for group in GROUPS},
        "no_trade_rate": {group: rate(finals[group], lambda value: value == "NoTrade") for group in GROUPS},
        "directional_rate": {group: rate(actions[group], lambda value: value in ("Buy", "Sell")) for group in GROUPS},
        "pairwise_disagreement": {key: rate(values) for key, values in pairwise.items()},
        "all_four_identical_rate": rate(identical),
        "b_vote_agreement_mean": float(statistics.fmean(vote_agreement)) if vote_agreement else None,
        "gate_override_rate": {group: rate([candidate != final for candidate, final in zip(actions[group], finals[group])]) for group in GROUPS},
        "expected_return_stats": {group: {**_mean_sd(expected[group]), "inside_band_rate": rate(inside[group])}
                                  for group in GROUPS},
        "action_disagreement_rate": {group: rate(mismatch[group]) for group in GROUPS},
        "accuracy_outside_band": {group: rate(outside_correct[group]) for group in GROUPS},
        "accuracy_inside_band": {group: rate(inside_correct[group]) for group in GROUPS},
        "hold_justified_rate": {group: rate(hold_justified[group]) for group in GROUPS},
    }
    reasons = ["no_completed_cases"] if not cases else []
    for group, value in result["hold_rate"].items():
        if value is not None and value > .40:
            reasons.append(f"hold_rate_too_high:{group}")
    if result["pairwise_disagreement"]["D_vs_A"] is not None and result["pairwise_disagreement"]["D_vs_A"] < .20:
        reasons.append("insufficient_D_vs_A_disagreement")
    if result["all_four_identical_rate"] is not None and result["all_four_identical_rate"] > .60:
        reasons.append("arms_not_identifiable")
    if result["b_vote_agreement_mean"] is not None and result["b_vote_agreement_mean"] > .95:
        reasons.append("self_consistency_arm_degenerate")
    for group in GROUPS:
        standard_deviation = result["expected_return_stats"][group]["sd"]
        if standard_deviation is not None and standard_deviation < .5:
            reasons.append(f"forecast_variance_collapsed:{group}")
        accuracy = result["accuracy_outside_band"][group]
        if accuracy is not None and accuracy < .45:
            reasons.append(f"directional_calls_worse_than_chance:{group}")
        disagreement = result["action_disagreement_rate"][group]
        if disagreement is not None and disagreement > .30:
            reasons.append(f"narrative_forecast_mismatch:{group}")
    return {**result, "verdict": "blocked" if reasons else "proceed", "blocking_reasons": reasons}


def _reprice_case(row, action, hold_band_pct, daily_rows):
    """Reprice stored open-to-open marks for a new threshold without a model call."""
    result = dict(row)
    result.update(action=action, candidate_action=action, gated_action=action, hold_band_pct=hold_band_pct)
    base_returns = [float(item.get("benchmark_return", 0.0)) for item in daily_rows]
    benchmark_return = float(row.get("benchmark_return", math.prod(1 + value for value in base_returns) - 1))
    realized_move_pct = benchmark_return * 100
    result["realized_move_pct"] = realized_move_pct
    if action == "Hold":
        result.update(net_return=0.0, gross_return=0.0, cost=0.0, correct=None, insolvent=False,
                      insolvent_date=None, hold_was_justified=abs(realized_move_pct) <= hold_band_pct,
                      hold_opportunity_cost=max(0.0, abs(realized_move_pct) - hold_band_pct))
        return result, [{**item, "return": 0.0} for item in daily_rows]
    direction = 1 if action == "Buy" else -1
    entry, exit_price = row.get("entry_price"), row.get("exit_price")
    entry_spread, exit_spread = row.get("entry_spread", 0.0), row.get("exit_spread", 0.0)
    cost = 0.0
    if row.get("cost_model") == "corwin_schultz" and isinstance(entry, (int, float)) and entry:
        cost = float(entry_spread) / 2 + float(exit_spread) / 2 * float(exit_price) / float(entry)
    gross = direction * benchmark_return
    result.update(gross_return=gross, cost=cost, net_return=max(-1.0, gross - cost),
                  correct=direction * benchmark_return > 0, hold_was_justified=None,
                  hold_opportunity_cost=0.0)
    equity, previous, cumulative, insolvent_date = 1.0, 1.0, 1.0, None
    repriced = []
    for index, item in enumerate(daily_rows):
        cumulative *= 1 + base_returns[index]
        applied_cost = float(entry_spread) / 2 if index == 0 and row.get("cost_model") == "corwin_schultz" else 0.0
        if index == len(daily_rows) - 1 and row.get("cost_model") == "corwin_schultz" and isinstance(entry, (int, float)) and entry:
            applied_cost += float(exit_spread) / 2 * cumulative
        equity = max(0.0, 1 + direction * (cumulative - 1) - applied_cost) if equity > 0 else 0.0
        if equity == 0.0 and insolvent_date is None:
            insolvent_date = item.get("date")
        repriced.append({**item, "return": equity / previous - 1 if previous > 0 else 0.0})
        previous = equity
    result.update(insolvent=insolvent_date is not None, insolvent_date=insolvent_date)
    if insolvent_date is not None:
        result["net_return"] = -1.0
    return result, repriced


def _sensitivity_jobs(jobs, sigma):
    clones = []
    for job in jobs:
        clone = deepcopy(job)
        horizon_sigma = clone["state"].get("inputs", {}).get("horizon_sigma_pct")
        if not isinstance(horizon_sigma, (int, float)):
            continue
        band = float(horizon_sigma) * sigma
        actions = {}
        for group, decision in clone["state"].get("decisions", {}).items():
            forecast = decision.get("expected_return_pct")
            if not isinstance(forecast, (int, float)):
                continue
            action = "Buy" if forecast > band else "Sell" if forecast < -band else "Hold"
            decision.update(candidate_action=action, action=action, derived_action=action,
                            hold_band_pct=band, action_disagreement=decision.get("model_action") != action)
            actions[group] = action
        selected_daily, new_cases, new_daily = {}, [], []
        for row in clone["state"].get("cases", []):
            if _layer(row) != "candidate" or row.get("group") not in actions:
                new_cases.append(row)
                continue
            key = (row.get("group"), row.get("horizon"), row.get("cost_model"), _layer(row))
            original_daily = [item for item in clone["state"].get("daily", [])
                              if (item.get("group"), item.get("horizon"), item.get("cost_model"), _layer(item)) == key]
            repriced, repriced_daily = _reprice_case(row, actions[row["group"]], band, original_daily)
            new_cases.append(repriced)
            selected_daily[key] = repriced_daily
        for item in clone["state"].get("daily", []):
            key = (item.get("group"), item.get("horizon"), item.get("cost_model"), _layer(item))
            if key not in selected_daily:
                new_daily.append(item)
        for rows in selected_daily.values():
            new_daily.extend(rows)
        clone["state"]["cases"], clone["state"]["daily"] = new_cases, new_daily
        clone["config"]["protocol"]["hold_band_sigma"] = sigma
        clones.append(clone)
    return clones


def hold_band_sensitivity(jobs, sigmas=(0.0, 0.25, 0.5, 1.0)):
    """Re-evaluate stored point forecasts across preregistered neutral-band widths."""
    complete, _ = _completed_unique(jobs)
    results = []
    for sigma in sigmas:
        rerun = _sensitivity_jobs(complete, float(sigma))
        report = study_report(rerun, include_inference=False) if rerun else {"summary": [], "status": "no_completed_cases"}
        primary = [row for row in report.get("summary", [])
                   if row.get("decision_layer") == "candidate" and row.get("horizon") == 60
                   and row.get("cost_model") == "corwin_schultz" and row.get("portfolio_basis") == "all"]
        results.append({"hold_band_sigma": float(sigma), "status": report.get("status"),
                        "summary": primary, "pilot": pilot_diagnostics(rerun) if rerun else None})
    return {"basis": "stored expected_return_pct re-derived without any model call; descriptive only", "sigmas": results}


def csv_text(rows):
    if not rows:
        return "status\nno_data\n"
    keys = list(dict.fromkeys(key for row in rows for key in row))
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, keys)
    writer.writeheader()
    for row in rows:
        clean = {key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
                 for key, value in row.items()}
        writer.writerow({key: "'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")) else value
                         for key, value in clean.items()})
    return output.getvalue()


def _json_bytes(data):
    return json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")


def _archive_timestamp(value):
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        stamp = stamp.astimezone(timezone.utc)
        return (max(stamp.year, 1980), stamp.month, stamp.day, stamp.hour, stamp.minute, stamp.second)
    except (TypeError, ValueError):
        return (1980, 1, 1, 0, 0, 0)


def _write_zip_entry(archive, name, payload, timestamp):
    info = zipfile.ZipInfo(filename=name, date_time=timestamp)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o600 << 16
    archive.writestr(info, payload)


def runtime_environment():
    """Record the libraries that decide the numbers, not just the model.

    The protocol hash pins the research design and model_identity pins the
    model, but the statistics and the FinBERT scores are also a function of
    the installed numeric/ML stack. Without this, two runs of the same
    protocol_hash could report different figures with nothing in the audit
    trail to distinguish them.
    """
    versions = {}
    for name in ("numpy", "scipy", "pandas", "transformers", "torch", "litellm", "yfinance"):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return {"python": platform.python_version(), "platform": platform.platform(), "packages": versions,
            "note": "Statistics and FinBERT scores depend on these versions; record them alongside any published figure."}


def _export_manifest(job, payloads):
    config = job["config"]
    protocol = config.get("protocol", {})
    return {"schema": EXPORT_SCHEMA,
        "job": {"id": job["id"], "created_at": job.get("created_at"), "updated_at": job.get("updated_at"),
                "ticker": config.get("ticker"), "analysis_date": config.get("analysis_date"),
                "dataset_id": config.get("dataset_id"), "dataset_hash": config.get("dataset_hash"),
                "protocol_version": protocol.get("version"), "protocol_hash": config.get("protocol_hash"),
                "model_identity": config.get("model_identity", {}), "quality_overrides": config.get("quality_overrides", {})},
        "runtime_environment": runtime_environment(),
        "files": [{"path": name, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
                  for name, payload in sorted(payloads.items())],
        "integrity_scope": "All payload files listed above; manifest.json is not self-hashed."}


def export_job(job, study=None):
    state = job["state"]
    files = {"protocol.json": job["config"], "neutral_report.json": state.get("report", {}),
        "evidence_registry.json": state.get("inputs", {}).get("evidence", []), "state_trace.json": state,
        "memory.json": state.get("memory", {}), "decisions.json": state.get("decisions", {}),
        "completeness_diagnostic.json": state.get("completeness_diagnostic", {})}
    payloads = {name: _json_bytes(data) for name, data in files.items()}
    payloads["cases.csv"] = csv_text(state.get("cases", [])).encode("utf-8")
    payloads["daily_returns.csv"] = csv_text(state.get("daily", [])).encode("utf-8")
    if study is not None:
        payloads["summary.csv"] = csv_text(study.get("summary", [])).encode("utf-8")
        payloads["statistics.json"] = _json_bytes(study)
    payloads["debate_transcript.md"] = "\n\n".join(
        f"## {record['group']} · {record['key']} · {record['stance']}\n{record['output']['rationale']}\n\n引用：{', '.join(record['output']['evidence_ids'])}"
        for record in state.get("records", [])).encode("utf-8")
    manifest = _export_manifest(job, payloads)
    timestamp = _archive_timestamp(job.get("updated_at") or job.get("created_at"))
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, payload in sorted(payloads.items()):
            _write_zip_entry(archive, name, payload, timestamp)
        _write_zip_entry(archive, "manifest.json", _json_bytes(manifest), timestamp)
    return output.getvalue()
