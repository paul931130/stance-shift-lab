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
import sys
import zipfile

import numpy as np

from .backtest import metrics
from .statistics import (aligned_portfolio_returns, date_cluster_block_accuracy, mcnemar,
                         jobson_korkie_memmel, ledoit_wolf_block, holm_adjust)
from .protocol import DESIGNS, STUDY_TICKERS
from .splits import SPLIT_DEFINITIONS, classify_analysis_date


EXPORT_SCHEMA = "stance-shift-export/v1"
MIN_CASES_FOR_INFERENCE = 30
GROUPS = "ABCD"


def _is_complete(job):
    return job.get("status") == "complete" and bool(job.get("state", {}).get("finished"))


# When the model was looked up, not which model it is: two jobs on the same model
# weights must compare equal even when created minutes apart.
VOLATILE_IDENTITY_FIELDS = ("resolved_at", "modified_at")


def stable_model_identity(config):
    """The model identity used to decide whether jobs may be pooled."""
    identity = {key: value for key, value in (config.get("model_identity") or {}).items()
                if key not in VOLATILE_IDENTITY_FIELDS}
    return json.dumps(identity, sort_keys=True, separators=(",", ":"))


def _formal_exclusion_reason(job, eligible_dataset_ids, frozen_at=None):
    """Fail closed unless a completed job carries formal-study provenance."""
    config = job.get("config", {})
    protocol = config.get("protocol", {})
    report = job.get("state", {}).get("report", {})
    readiness = config.get("formal_readiness")
    if protocol.get("dataset_kind") != "historical" or report.get("dataset_kind") != "historical":
        return "non_historical_dataset"
    if not isinstance(readiness, dict) or readiness.get("eligible") is not True:
        return "formal_readiness_not_proven"
    if config.get("quality_overrides"):
        return "quality_override"
    if protocol.get("allow_small_model"):
        return "small_model_override"
    identity = config.get("model_identity", {})
    if identity.get("provider") in ("built_in_demo", "test_override"):
        return "non_formal_model_provider"
    if str(identity.get("id", "")).startswith("ollama/") and not identity.get("digest"):
        return "model_identity_unresolved"
    if eligible_dataset_ids is None:
        return "study_not_preregistered"
    if config.get("dataset_id") not in eligible_dataset_ids:
        return "not_preregistered_dataset"
    # A sample locked after results existed would let a researcher choose it
    # having seen them: only jobs created after the lock are formal.
    if frozen_at is not None and not str(job.get("created_at", "")) > str(frozen_at):
        return "run_before_preregistration"
    return None


def _completed_unique(jobs, *, formal_only=False, eligible_dataset_ids=None, frozen_at=None):
    """Return first valid result per case without mutating rerun audit records."""
    completed = [job for job in jobs if _is_complete(job)]
    degraded = [job for job in completed
                if job.get("state", {}).get("report", {}).get("degraded_research_domains")]
    nonformal = [(job, _formal_exclusion_reason(job, eligible_dataset_ids, frozen_at) if formal_only else None)
                 for job in completed if job not in degraded]
    excluded_nonformal = [(job, reason) for job, reason in nonformal if reason]
    usable = [job for job, reason in nonformal if not reason]
    reasons = {}
    for _, reason in excluded_nonformal:
        reasons[reason] = reasons.get(reason, 0) + 1
    if not usable:
        return [], {"completed": len(completed), "degraded": len(degraded), "nonformal": len(excluded_nonformal),
                    "nonformal_reasons": reasons, "duplicates": 0}
    hashes = {job["config"].get("protocol_hash") for job in usable}
    if len(hashes) != 1:
        raise ValueError("不同協議、模型或資料類型不可合併統計")
    if formal_only:
        identities = {stable_model_identity(job["config"]) for job in usable}
        if len(identities) != 1:
            raise ValueError("不同解析模型版本不可合併正式統計")
        case_datasets = {}
        for job in usable:
            config = job["config"]
            key = (config.get("ticker"), config.get("analysis_date"))
            case_datasets.setdefault(key, set()).add(config.get("dataset_id"))
        if any(len(dataset_ids) != 1 for dataset_ids in case_datasets.values()):
            raise ValueError("同一正式案例不可混用不同資料集版本")
    unique = {}
    for job in sorted(usable, key=lambda item: item.get("created_at", "")):
        config = job["config"]
        unique.setdefault((config.get("ticker"), config.get("analysis_date")), job)
    return list(unique.values()), {"completed": len(completed), "degraded": len(degraded),
                                    "nonformal": len(excluded_nonformal), "nonformal_reasons": reasons,
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
                    # Keep the benchmark on the same transaction-cost basis as
                    # the strategy.  Older stored runs do not have the new
                    # field, so retain a backwards-compatible gross fallback.
                    base = (row.get("benchmark_net_return")
                            if cost_model == "corwin_schultz"
                            else row.get("benchmark_return"))
                    if not isinstance(base, (int, float)) or not math.isfinite(float(base)):
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
    paired = [(key, row.get("correct"), lookup[key].get("correct")) for key, row in rows["D"]
              if key in lookup and row.get("correct") is not None and lookup[key].get("correct") is not None]
    endpoint = ("primary" if decision_layer == "candidate" and horizon == protocol.get("primary_horizon", 60)
                and cost_model == "corwin_schultz" and portfolio_basis == "all" else "robustness")
    result = {"groups": ["D", group], "horizon": horizon, "cost_model": cost_model,
              "decision_layer": decision_layer, "portfolio_basis": portfolio_basis,
              "endpoint": endpoint, "portfolio_dates": len(portfolios["D"])}
    result["mcnemar"] = (mcnemar(np.array([first for _, first, _ in paired], dtype=bool),
                                  np.array([second for _, _, second in paired], dtype=bool)) if paired
                          else {"status": "no_paired_directional_cases", "pvalue": None})
    by_date = {key[1]: [] for key, _ in rows["D"]}
    for key, first, second in paired:
        by_date.setdefault(key[1], []).append((bool(first), bool(second)))
    lengths = (1, 2, 4) if protocol.get("design", "quarterly") == "quarterly" else (1, 3, 6, 12)
    result["date_cluster_direction_sensitivity"] = date_cluster_block_accuracy(
        by_date, block_lengths=lengths,
        replicates=protocol.get("bootstrap_replicates", 1999),
        seed=protocol.get("inference_seed", 905))
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


def _stability_value(job, group):
    """Extract the primary decision values needed for a test-retest audit."""
    decision = job.get("state", {}).get("decisions", {}).get(group, {})
    row = _primary_candidate_row(job, group)
    action = _decision_action(decision) or (row or {}).get("action")
    evidence_ids = decision.get("evidence_ids", [])
    if not isinstance(evidence_ids, list):
        evidence_ids = []
    return {"action": action, "expected_return_pct": decision.get("expected_return_pct"),
            "confidence": decision.get("confidence"), "evidence_ids": evidence_ids}


def _pairwise_agreement(values, key):
    pairs = []
    for left_index, left in enumerate(values):
        for right in values[left_index + 1:]:
            left_value, right_value = left.get(key), right.get(key)
            if left_value is not None and right_value is not None:
                pairs.append(left_value == right_value)
    return {"agreement": sum(pairs) / len(pairs) if pairs else None, "pairs": len(pairs)}


def _evidence_jaccard(left, right):
    left_ids, right_ids = set(left.get("evidence_ids", [])), set(right.get("evidence_ids", []))
    if not left_ids and not right_ids:
        return 1.0
    return len(left_ids & right_ids) / len(left_ids | right_ids)


def stability_report(jobs):
    """Describe full-run test-retest variation without adding formal inference.

    Aggregate study statistics intentionally keep the first valid run for each
    case.  This companion report keeps repeated runs visible so action changes
    are not mistaken for a stance effect.  It is descriptive and never used to
    promote a model or protocol to a formal result.
    """
    completed = [job for job in jobs if _is_complete(job)]
    eligible = [job for job in completed
                if not job.get("state", {}).get("report", {}).get("degraded_research_domains")]
    hashes = sorted({job.get("config", {}).get("protocol_hash") for job in eligible})
    if len(hashes) > 1:
        return {"status": "mixed_protocols", "protocol_hashes": hashes,
                "completed_runs": len(completed), "eligible_runs": len(eligible),
                "repeated_cases": 0, "groups": {},
                "note": "重複性只能在同一 protocol_hash、同一資料與完整研究執行間描述。"}
    by_case = {}
    for job in sorted(eligible, key=lambda item: item.get("created_at", "")):
        config = job.get("config", {})
        key = (config.get("ticker"), config.get("analysis_date"), config.get("dataset_id"), stable_model_identity(config))
        by_case.setdefault(key, []).append(job)
    repeated = {key: runs for key, runs in by_case.items() if len(runs) >= 2}
    groups = {}
    for group in GROUPS:
        # Test-retest compares runs of the SAME case only; pooling all runs
        # would count differences between cases as instability.
        agreeing = pairs = 0
        expected, confidence, evidence_overlap = [], [], []
        expected_sd, confidence_sd = [], []
        case_count = 0
        run_count = 0
        for runs in repeated.values():
            values = [_stability_value(job, group) for job in runs]
            case_count += 1
            run_count += len(values)
            within = _pairwise_agreement(values, "action")
            pairs += within["pairs"]
            agreeing += round((within["agreement"] or 0) * within["pairs"])
            case_expected = _numeric([value["expected_return_pct"] for value in values])
            case_confidence = _numeric([value["confidence"] for value in values])
            expected.extend(case_expected)
            confidence.extend(case_confidence)
            if len(case_expected) > 1:
                expected_sd.append(statistics.stdev(case_expected))
            if len(case_confidence) > 1:
                confidence_sd.append(statistics.stdev(case_confidence))
            for left_index, left in enumerate(values):
                evidence_overlap.extend(_evidence_jaccard(left, right)
                                        for right in values[left_index + 1:])
        groups[group] = {"cases": case_count, "runs": run_count,
                         "action": {"agreement": agreeing / pairs if pairs else None, "pairs": pairs,
                                    "basis": "within_case_pairs"},
                         "expected_return_pct": {**_mean_sd(expected), "within_case_sd": _mean_sd(expected_sd)},
                         "confidence": {**_mean_sd(confidence), "within_case_sd": _mean_sd(confidence_sd)},
                         "evidence_jaccard": _mean_sd(evidence_overlap)}
    return {"status": "descriptive_ready" if repeated else "no_repeated_complete_cases",
            "protocol_hash": hashes[0] if hashes else None,
            "completed_runs": len(completed), "eligible_runs": len(eligible),
            "repeated_cases": len(repeated),
            "case_run_counts": {f"{key[0]}:{key[1]}:{key[2]}": len(value) for key, value in repeated.items()},
            "groups": groups,
            "note": "重複性指標是 full-protocol test-retest 的描述統計；一致率只比較同一案例的重跑配對。"
                    "expected_return_pct／confidence 的 sd 含案例間差異，within_case_sd 才是案例內的重跑離散程度。"
                    "未做正式顯著性檢定，也不取代主分析。"}


def _primary_rows(report):
    primary_horizon = report.get("primary_horizon", 60)
    return [row for row in report.get("summary", [])
            if row.get("horizon") == primary_horizon and row.get("cost_model") == "corwin_schultz"
            and row.get("decision_layer") == "candidate" and row.get("portfolio_basis") == "all"
            and row.get("group") in GROUPS]


def knowledge_cutoff_report(complete, include_inference=True):
    """Primary results before, across and after the model's knowledge cutoff.

    Pre-registered companion analysis: if the model remembers outcomes before
    its cutoff, accuracy there is inflated and group differences may be an
    artefact of memory. Claims should hold after the cutoff as well.
    """
    from .knowledge import KNOWLEDGE_CUTOFFS, cutoff_for, split_by_knowledge

    groups = split_by_knowledge(complete, horizon=complete[0]["config"].get("protocol", {}).get("primary_horizon", 60))
    models = sorted({job["config"].get("protocol", {}).get("model") for job in complete})
    segments = {}
    for name in ("before_cutoff", "straddles_cutoff", "after_cutoff"):
        subset = groups[name]
        if not subset:
            segments[name] = {"cases": 0}
            continue
        part = study_report(subset, include_inference=include_inference, formal_only=False, split_knowledge=False)
        segments[name] = {"cases": part.get("unique_cases", 0), "status": part.get("status"),
                          "primary": _primary_rows(part),
                          "comparisons": [item for item in part.get("comparisons", [])
                                          if item.get("horizon") == part.get("primary_horizon", 60)
                                          and item.get("cost_model") == "corwin_schultz"
                                          and item.get("decision_layer") == "candidate"
                                          and item.get("portfolio_basis") == "all"]}
    by_group = {}
    for group in GROUPS:
        values = {name: next((row.get("selective_accuracy") for row in segments[name].get("primary", [])
                              if row["group"] == group), None) for name in segments}
        before, after = values.get("before_cutoff"), values.get("after_cutoff")
        by_group[group] = {"selective_accuracy": values,
                           "after_minus_before": None if before is None or after is None else after - before}
    known = [cutoff_for(model) for model in models if cutoff_for(model)]
    return {"models": models, "cutoffs": {model: KNOWLEDGE_CUTOFFS.get(str(model).lower()) for model in models},
            "unknown_cutoff_cases": len(groups["unknown_cutoff"]), "segments": segments, "by_group": by_group,
            "status": "cutoff_recorded" if known else "cutoff_not_recorded",
            "note": "截止日前（模型可能記得結果）、跨越截止日、截止日後（樣本外）分開計算。"
                    "主要結論應在截止日後同樣成立；只在截止日前成立的組間差異可能來自模型記憶。"
                    "截止日後樣本較少且市場環境不同，差異需一併考量。"}


def _expected_protocol_cases(protocol):
    design = protocol.get("design", "quarterly")
    dates = protocol.get("analysis_dates") or DESIGNS.get(design, DESIGNS["quarterly"])["dates"]
    tickers = protocol.get("study_universe") or STUDY_TICKERS
    return {(ticker, analysis_date) for analysis_date in dates for ticker in tickers}


def _completion_status(jobs, protocol, quality_complete, *, eligible_dataset_ids=None, frozen_at=None):
    expected = _expected_protocol_cases(protocol) if protocol else set()
    completed_keys = {(job["config"].get("ticker"), job["config"].get("analysis_date"))
                      for job in jobs if _is_complete(job)}
    quality_keys = {(job["config"].get("ticker"), job["config"].get("analysis_date"))
                    for job in quality_complete}
    work_complete = bool(expected) and expected <= completed_keys
    preregistered = eligible_dataset_ids is not None and frozen_at is not None
    formal_complete = preregistered and bool(expected) and expected <= quality_keys
    return {
        "target_cases": len(expected) if expected else None,
        "work_completed_cases": len(expected & completed_keys) if expected else len(completed_keys),
        "work_complete": work_complete,
        "work_status": "complete" if work_complete else "incomplete",
        "quality_passed_cases": len(quality_keys),
        "quality_excluded_completed_cases": len(expected & completed_keys) - len(expected & quality_keys)
        if expected else None,
        "quality_status": "passed_for_all_completed" if completed_keys and completed_keys == quality_keys else
                          "has_exclusions" if quality_keys or completed_keys else "not_assessed",
        "formal_sample_preregistered": preregistered,
        "formal_sample_complete": formal_complete,
        "formal_sample_status": "complete" if formal_complete else
                                "incomplete" if preregistered else "not_preregistered",
    }


def _temporal_split_results(complete, protocol):
    design = protocol.get("design", "quarterly")
    dates = protocol.get("analysis_dates") or DESIGNS.get(design, DESIGNS["quarterly"])["dates"]
    tickers = protocol.get("study_universe") or STUDY_TICKERS
    splits = {}
    for name, definition in SPLIT_DEFINITIONS.items():
        target_dates = [day for day in dates if classify_analysis_date(day) == name]
        jobs = [job for job in complete if classify_analysis_date(job["config"].get("analysis_date")) == name]
        by_group = {}
        for group in "ABCD":
            rows = [_primary_candidate_row(job, group) for job in jobs]
            rows = [row for row in rows if row is not None]
            directional = [row for row in rows if row.get("correct") is not None]
            by_group[group] = {
                "cases": len(rows), "directional_cases": len(directional),
                "coverage": len(directional) / len(rows) if rows else None,
                "selective_accuracy": (sum(bool(row["correct"]) for row in directional) / len(directional)
                                       if directional else None),
                "mean_net_return": (statistics.fmean(float(row["net_return"]) for row in rows
                                    if isinstance(row.get("net_return"), (int, float)))
                                    if any(isinstance(row.get("net_return"), (int, float)) for row in rows) else None),
            }
        splits[name] = {"label": definition["label"], "years": list(definition["years"]),
                        "purpose": definition["purpose"], "frozen": definition["frozen"],
                        "target_cases": len(tickers) * len(target_dates), "completed_cases": len(jobs),
                        "by_group": by_group}
    return {"basis": "analysis_date_year", "primary_horizon": protocol.get("primary_horizon", 60),
            "cost_model": "corwin_schultz", "decision_layer": "candidate", "splits": splits,
            "note": "Train、Validation、Test 分開呈現描述統計；不以 Test 調參，也不把小分組 p 值當正式結論。"}


def _numeric_validation_quality(complete):
    by_flag = {"no_redaction": [], "redaction": []}
    redacted_calls = redacted_values = removed_claims = 0
    known = False
    for job in complete:
        version = job.get("config", {}).get("protocol", {}).get("version")
        if version in {"v3-0929.1", "v3-0930.1", "v3-0930.2", "v3-0930.3", "v3-0930.4"}:
            known = True
        records = job.get("state", {}).get("records", [])
        case_redacted_calls = 0
        for record in records:
            audit = record.get("audit", {}) or {}
            values = audit.get("numeric_redaction", [])
            claims_removed = int(audit.get("numeric_claims_removed", 0) or 0)
            if values or claims_removed:
                case_redacted_calls += 1
                redacted_calls += 1
                redacted_values += len(values)
                removed_claims += claims_removed
        by_flag["redaction" if case_redacted_calls else "no_redaction"].append(job)
    strata = {}
    for name, jobs in by_flag.items():
        by_group = {}
        for group in "ABCD":
            rows = [_primary_candidate_row(job, group) for job in jobs]
            rows = [row for row in rows if row is not None]
            directional = [row for row in rows if row.get("correct") is not None]
            by_group[group] = {"cases": len(rows), "directional_cases": len(directional),
                               "coverage": len(directional) / len(rows) if rows else None,
                               "selective_accuracy": (sum(bool(row["correct"]) for row in directional) / len(directional)
                                                      if directional else None),
                               "mean_net_return": (statistics.fmean(float(row["net_return"]) for row in rows
                                                   if isinstance(row.get("net_return"), (int, float)))
                                                   if any(isinstance(row.get("net_return"), (int, float)) for row in rows) else None)}
        strata[name] = {"cases": len(jobs), "by_group": by_group}
    return {"status": "available" if known else "not_recorded",
            "redacted_cases": len(by_flag["redaction"]), "redacted_calls": redacted_calls,
            "redacted_numeric_tokens": redacted_values, "removed_numeric_claims": removed_claims,
            "strata": strata,
            "note": "依每案任一決策呼叫曾移除數字分層；僅作品質／選擇診斷，不代表移除數字造成或未造成決策改變。"}


def _sentiment_coverage_report(complete):
    aggregate = {}
    observed = 0
    for job in complete:
        coverage = (job.get("state", {}).get("inputs", {}).get("sentiment_coverage")
                    or job.get("state", {}).get("report", {}).get("sentiment_coverage"))
        ticker, year = job["config"].get("ticker"), str(job["config"].get("analysis_date", ""))[:4]
        key = f"{ticker}:{year}"
        row = aggregate.setdefault(key, {"ticker": ticker, "year": year, "cases": 0,
            "coverage_recorded_cases": 0, "window_days": None,
            "scopes": {scope: {"headline_count": 0, "scored_count": 0, "source_counts": {},
                               "indicator_cases": 0} for scope in ("target", "context")}})
        row["cases"] += 1
        if not isinstance(coverage, dict):
            continue
        observed += 1
        row["coverage_recorded_cases"] += 1
        if row["window_days"] is None:
            row["window_days"] = coverage.get("window_days")
        for scope in ("target", "context"):
            info = coverage.get("scopes", {}).get(scope, {})
            dst = row["scopes"][scope]
            dst["headline_count"] += int(info.get("headline_count", 0) or 0)
            dst["scored_count"] += int(info.get("scored_count", 0) or 0)
            dst["indicator_cases"] += int(bool(info.get("indicator_emitted")))
            for source, counts in info.get("source_counts", {}).items():
                bucket = dst["source_counts"].setdefault(source, {"headline_count": 0, "scored_count": 0})
                bucket["headline_count"] += int(counts.get("headline_count", 0) or 0)
                bucket["scored_count"] += int(counts.get("scored_count", 0) or 0)
    for row in aggregate.values():
        for info in row["scopes"].values():
            info["missing_score_count"] = info["headline_count"] - info["scored_count"]
            info["missing_score_rate"] = (info["missing_score_count"] / info["headline_count"]
                                          if info["headline_count"] else None)
    return {"status": "available" if observed else "not_recorded", "cases_with_coverage": observed,
            "cases_without_coverage": max(0, len(complete) - observed),
            "coverage_record_rate": observed / len(complete) if complete else None,
            "by_ticker_year": sorted(aggregate.values(), key=lambda row: (row["ticker"], row["year"])),
            "source_counts_are_nonexclusive": True,
            "note": "新聞來源組成按去重後的來源標籤計數；跨來源重複會使各來源小計不互斥。缺失率以符合相關性篩選的窗口新聞為分母。"}


def study_report(jobs, *, include_inference=True, formal_only=True, eligible_dataset_ids=None, frozen_at=None,
                 split_knowledge=True):
    complete, excluded = _completed_unique(
        jobs, formal_only=formal_only,
        eligible_dataset_ids=None if eligible_dataset_ids is None else set(eligible_dataset_ids),
        frozen_at=frozen_at)
    quality_complete, _ = _completed_unique(
        jobs, formal_only=True,
        eligible_dataset_ids=None if eligible_dataset_ids is None else set(eligible_dataset_ids),
        frozen_at=frozen_at)
    protocol = (complete[0] if complete else next((job for job in jobs if job.get("config", {}).get("protocol")), None))
    protocol = protocol.get("config", {}).get("protocol", {}) if protocol else {}
    completion = _completion_status(jobs, protocol, quality_complete,
                                    eligible_dataset_ids=eligible_dataset_ids, frozen_at=frozen_at)
    stability = stability_report(jobs)
    if not complete:
        return {"status": "no_formal_cases" if formal_only and excluded["completed"] else "no_completed_cases",
                "summary": [], "comparisons": [], "completeness": _completeness([]),
                "excluded_incomplete_runs": len(jobs) - excluded["completed"],
                "excluded_degraded_research_runs": excluded["degraded"],
                "excluded_nonformal_runs": excluded["nonformal"],
                "excluded_nonformal_reasons": excluded["nonformal_reasons"], "stability": stability,
                "completion": completion, "sentiment_coverage": _sentiment_coverage_report([]),
                "numeric_validation_quality": _numeric_validation_quality([])}
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
    completion["inference_ready"] = inferred
    completion["inference_minimum_cases"] = MIN_CASES_FOR_INFERENCE
    return {"status": "complete" if inferred else "insufficient_cases",
            "protocol_hash": complete[0]["config"].get("protocol_hash"), "unique_cases": len(complete),
            "primary_horizon": protocol.get("primary_horizon", 60), "design": protocol.get("design", "quarterly"),
            "required_cases": MIN_CASES_FOR_INFERENCE, "excluded_duplicate_runs": excluded["duplicates"],
            "excluded_incomplete_runs": len(jobs) - excluded["completed"],
            "excluded_degraded_research_runs": excluded["degraded"],
            "excluded_nonformal_runs": excluded["nonformal"],
            "excluded_nonformal_reasons": excluded["nonformal_reasons"], "summary": summary,
            "comparisons": comparisons, "completeness": _completeness(complete),
            "completion": completion,
            "temporal_split_results": _temporal_split_results(complete, protocol),
            "numeric_validation_quality": _numeric_validation_quality(complete),
            "sentiment_coverage": _sentiment_coverage_report(complete),
            "stability": stability,
            **({"knowledge_cutoff": knowledge_cutoff_report(complete, include_inference)} if split_knowledge else {}),
            "conventions": [
                f"Primary analysis: decision_layer=candidate, horizon={protocol.get('primary_horizon', 60)}, "
                "cost_model=corwin_schultz, portfolio_basis=all",
                "Candidate actions measure the decision mechanism; gated actions are a separate risk-control sensitivity layer",
                "Open-to-open: entry at t+1 open, exit at t+horizon+1 open",
                "Short positions are floored at -100%; insolvent cases are retained and flagged, not excluded",
                "Hold is scored as abstention: reported via coverage, selective accuracy, and hold opportunity cost, never as a free correct answer",
                "portfolio_basis=all holds equal fixed case weights and treats inactive sleeves as cash; portfolio_basis=active uses changing active-sleeve weights as sensitivity only",
                "Compute matching is by call count (A=1, B=7, C=7, D=7); token counts differ by arm and are reported, not equalised",
                "First valid completed run per ticker/date is fixed for aggregate analysis; later reruns remain separate audit artifacts",
                "McNemar uses mutually directional cases; paired date-cluster and contiguous-date-block percentile intervals are an additional direction-accuracy sensitivity analysis, not a second p-value",
                "Holm correction is applied within each horizon/cost/layer/basis/method p-value family",
                "Formal inference is withheld until at least 30 unique completed historical cases are available",
                "Inference readiness is not the same as all jobs complete, quality passing, or a complete preregistered sample",
                "Runs using deterministic research-source fallback are excluded from formal aggregate statistics",
                "Repeated complete runs are summarized separately by stability_report; they are not collapsed into the primary case panel",
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
                   if row.get("decision_layer") == "candidate" and row.get("horizon") == report.get("primary_horizon", 60)
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
    # ``platform.platform()`` performs a WMI query on Windows.  That query can
    # fail or exhaust desktop resources during repeated exports, while the
    # portable interpreter identifier is sufficient for the audit manifest.
    return {"python": platform.python_version(), "platform": sys.platform, "packages": versions,
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
