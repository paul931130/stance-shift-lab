"""Fail-closed RQ3 snapshot adapter and proposed six-endpoint analysis.

This analysis proposal must be preregistered before formal use. It does not
register a study, authorize execution, or count domain views as observations.
"""
import math

import numpy as np

from .data import digest
from .protocol import QUARTER_DATES, STUDY_TICKERS
from .reporting import stable_model_identity
from .rq_analysis import date_block_bootstrap, sharpe_combination_test
from .rq_study import select_cases
from .rq3_reporting import rq3_study_report
from .statistics import holm_adjust

ARMS = ("C", "C_domain", "C_budget", "C_partition")
BASELINES = ("C", "C_budget", "C_partition")


def _primary(row):
    return (row.get("horizon") == 60 and row.get("cost_model") == "corwin_schultz"
            and row.get("decision_layer") == "candidate" and row.get("group") in ARMS)


def build_panel(jobs):
    """Validate one common complete-case panel; never silently omit an arm.

    Market-grid and formal eligibility checks belong to ``analyze_registered``.
    Missing sleeves outside their own holding window are cash, while missing
    daily observations *within* a case are rejected across all four arms.
    """
    if not jobs:
        raise ValueError("No complete RQ3 cases")
    correct, dates, case_ids, daily = [], [], [], {}
    for job in sorted(jobs, key=lambda j: (j["config"]["analysis_date"], j["config"]["ticker"])):
        config, state = job["config"], job["state"]
        key = f"{config['ticker']}:{config['analysis_date']}"
        if key in case_ids:
            raise ValueError("Duplicate stock/date case")
        case_ids.append(key)
        dates.append(config["analysis_date"])
        outcomes = {}
        for row in state.get("cases", []):
            if not _primary(row):
                continue
            arm = row["group"]
            if arm in outcomes:
                raise ValueError("Duplicate primary case/arm outcome")
            if row.get("status") != "complete" or not isinstance(row.get("correct"), bool):
                raise ValueError("Every primary outcome must be a complete Boolean")
            outcomes[arm] = row["correct"]
        if set(outcomes) != set(ARMS):
            raise ValueError("Missing primary arm outcome")
        correct.append([outcomes[arm] for arm in ARMS])
        seen = {arm: set() for arm in ARMS}
        for row in state.get("daily", []):
            if not _primary(row):
                continue
            arm, day, value = row["group"], row.get("date"), row.get("return")
            if not isinstance(day, str) or not day or day in seen[arm]:
                raise ValueError("Missing date or duplicate daily row for case/arm")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("Daily returns must be finite numbers")
            seen[arm].add(day)
            daily.setdefault(day, dict.fromkeys(ARMS, 0.))[arm] += value / len(jobs)
        if not seen[ARMS[0]] or len({tuple(sorted(seen[arm])) for arm in ARMS}) != 1:
            raise ValueError("Incomplete or misaligned per-case daily panel")
    days = sorted(daily)
    return {"case_ids": case_ids, "date_ids": dates, "correctness": np.asarray(correct, dtype=float),
            "trading_dates": days, "returns": np.asarray([[daily[day][arm] for arm in ARMS] for day in days])}


def infer_panel(panel, *, date_block_length, daily_block_length, replicates=1999, bootstrap_seed=905):
    """Three Domain-minus-baseline contrasts, with one shared six-test Holm family."""
    correct, returns = panel["correctness"], panel["returns"]
    contrasts = np.column_stack([correct[:, 1] - correct[:, ARMS.index(arm)] for arm in BASELINES])
    accuracy = date_block_bootstrap(contrasts, panel["date_ids"], block_length=date_block_length,
                                    replicates=replicates, seed=bootstrap_seed)
    results, pvalues = {}, []
    for index, arm in enumerate(BASELINES):
        sharpe = sharpe_combination_test(returns[:, [1, ARMS.index(arm)]], (1., -1.),
                                         block_length=daily_block_length, replicates=replicates, seed=bootstrap_seed)
        if sharpe.get("pvalue") is None:
            raise ValueError("All six proposed family endpoints must be estimable")
        acc = accuracy["contrasts"][index]
        results[arm] = {"accuracy": acc, "sharpe": sharpe}
        pvalues.extend((acc["pvalue"], sharpe["pvalue"]))
    adjusted = holm_adjust(pvalues)
    for index, arm in enumerate(BASELINES):
        for offset, endpoint in enumerate(("accuracy", "sharpe")):
            results[arm][endpoint]["holm_pvalue"] = adjusted[2 * index + offset]
    return {"schema": "rq3-inference-proposal/v1", "n_cases": len(panel["case_ids"]),
            "n_analysis_dates": len(set(panel["date_ids"])), "n_trading_days": len(panel["trading_dates"]),
            "case_ids": panel["case_ids"], "trading_dates": panel["trading_dates"], "contrasts": results,
            "family": [f"C_domain-minus-{arm}:{endpoint}" for arm in BASELINES for endpoint in ("accuracy", "sharpe")],
            "family_status": "conservative_proposal_requires_prior_registration",
            "date_block_length": date_block_length, "daily_block_length": daily_block_length,
            "replicates": replicates, "bootstrap_seed": bootstrap_seed,
            "notes": ["All comparisons use the same complete stock/date cases and daily panel.",
                      "Domain views are intermediate outputs, not independent observations.",
                      "No claim of a pure specialization effect or equal token/compute use."]}


def analyze_registered(jobs, *, eligible_dataset_ids, frozen_at, date_block_length, daily_block_length,
                       replicates=1999, bootstrap_seed=905):
    selected, excluded = select_cases(jobs, eligible_dataset_ids=eligible_dataset_ids, frozen_at=frozen_at)
    grid = {(ticker, day) for ticker in STUDY_TICKERS for day in QUARTER_DATES}
    actual = {(j["config"]["ticker"], j["config"]["analysis_date"]) for j in selected}
    if (len(selected) != 180 or actual != grid or len(eligible_dataset_ids) != 180
            or len(set(eligible_dataset_ids)) != 180
            or {j["config"]["dataset_id"] for j in selected} != set(eligible_dataset_ids)):
        raise ValueError("Require the complete registered 180-case 9x20 stock/date grid")
    reference = selected[0]["config"]
    settings = reference.get("domain_debate", {})
    if (settings.get("rq3_version") != "rq3-1015.1" or settings.get("rule") != "fixed"
            or settings.get("include_controls") is not True):
        raise ValueError("Require fixed RQ3 rq3-1015.1 with both controls")
    identity = reference.get("model_identity", {})
    if not identity.get("digest"):
        raise ValueError("Require a frozen model weight digest")
    reports = {}
    for job in selected:
        config, state = job["config"], job["state"]
        if (config["protocol"] != reference["protocol"] or config.get("domain_debate") != settings
                or stable_model_identity(config) != stable_model_identity(reference)):
            raise ValueError("All cases must share identical protocol, settings and model weights")
        diagnostics = state.get("rq3_diagnostics", {})
        if diagnostics.get("settings") != settings or not set(ARMS) <= diagnostics.get("resources", {}).keys():
            raise ValueError("Missing or inconsistent four-arm resource diagnostics")
        if not state.get("report_hash") or digest(state.get("report")) != state["report_hash"]:
            raise ValueError("Neutral Report hash mismatch")
        reports[job["id"]] = state["report_hash"]
        if not set(ARMS) <= state.get("memory", {}).keys():
            raise ValueError("Missing independently frozen four-arm memories")
        for arm in ARMS:
            for row in state["memory"][arm]:
                if (row.get("group") != arm or row.get("protocol_hash") != config["protocol_hash"]
                        or row.get("ticker") != config["ticker"] or row.get("horizon") != 60
                        or row.get("cost_model") != "corwin_schultz" or row.get("decision_layer") != "gated"
                        or row.get("degraded") not in (0, False)
                        or row.get("maturity_date", "9999") >= config["analysis_date"]
                        or row.get("analysis_date", "9999") >= config["analysis_date"]):
                    raise ValueError("Invalid cross-arm, cross-protocol or immature memory")
        if state.get("memory_audit", {}).get("pending_earlier_cases"):
            raise ValueError("Earlier unresolved cases affected frozen memory")
    result = infer_panel(build_panel(selected), date_block_length=date_block_length,
                         daily_block_length=daily_block_length, replicates=replicates, bootstrap_seed=bootstrap_seed)
    result.update(protocol_hash=reference["protocol_hash"], registered_at=frozen_at,
                  excluded=excluded, job_ids=[j["id"] for j in selected], protocol=reference["protocol"],
                  domain_debate=settings, model_identity=identity, report_manifest_hash=digest(reports),
                  resources=rq3_study_report(selected))
    return result
