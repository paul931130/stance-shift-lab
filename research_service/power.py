"""Simulation-based power planning for the preregistered paired endpoint.

This module never reads study results and never calls a model.  It is a design
tool: the assumptions are explicit so a later paper can report them instead of
calling the 180-case target automatically "powered".
"""
from __future__ import annotations

import numpy as np


def _probability(name, value):
    value = float(value)
    if not 0 <= value <= 1:
        raise ValueError(f"{name} must be between 0 and 1")
    return value


def effective_directional_cases(total_cases=180, directional_coverage=0.7,
                                cluster_size=1, intracluster_correlation=0.0):
    """Return nominal and design-effect-adjusted directional sample sizes."""
    if int(total_cases) != total_cases or total_cases < 1:
        raise ValueError("total_cases must be a positive integer")
    if int(cluster_size) != cluster_size or cluster_size < 1:
        raise ValueError("cluster_size must be a positive integer")
    coverage = _probability("directional_coverage", directional_coverage)
    icc = _probability("intracluster_correlation", intracluster_correlation)
    nominal = max(1, int(round(total_cases * coverage)))
    design_effect = 1 + (int(cluster_size) - 1) * icc
    effective = max(1, int(round(nominal / design_effect)))
    return {"total_cases": int(total_cases), "directional_coverage": coverage,
            "nominal_directional_cases": nominal, "cluster_size": int(cluster_size),
            "intracluster_correlation": icc, "design_effect": float(design_effect),
            "effective_directional_cases": effective}


def _mcnemar_pvalue(control_wins, treatment_wins):
    discordant = int(control_wins) + int(treatment_wins)
    if discordant == 0:
        return 1.0
    from scipy.stats import binomtest
    return float(binomtest(int(treatment_wins), discordant, p=0.5,
                           alternative="two-sided").pvalue)


def simulate_mcnemar_power(total_cases=180, accuracy_delta=0.10,
                            discordant_rate=0.30, directional_coverage=0.70,
                            cluster_size=1, intracluster_correlation=0.0,
                            alpha=0.05, replicates=2000, seed=905):
    """Estimate paired McNemar power under an explicit discordance model.

    ``accuracy_delta`` is treatment accuracy minus control accuracy.  Given a
    discordant-pair rate ``d``, the simulation sets control-wins to
    ``(d-delta)/2`` and treatment-wins to ``(d+delta)/2``.  This is a planning
    assumption, not an estimate from the study and not a substitute for the
    eventual paired data analysis.
    """
    delta = float(accuracy_delta)
    discordant = _probability("discordant_rate", discordant_rate)
    alpha = _probability("alpha", alpha)
    if abs(delta) > discordant:
        raise ValueError("abs(accuracy_delta) cannot exceed discordant_rate")
    if int(replicates) != replicates or replicates < 1:
        raise ValueError("replicates must be a positive integer")
    sample = effective_directional_cases(total_cases, directional_coverage,
                                         cluster_size, intracluster_correlation)
    control_win = (discordant - delta) / 2
    treatment_win = (discordant + delta) / 2
    probabilities = np.array([1 - discordant, control_win, treatment_win], dtype=float)
    rng = np.random.default_rng(seed)
    rejected = 0
    pvalues = []
    for _ in range(int(replicates)):
        _, control_wins, treatment_wins = rng.multinomial(
            sample["effective_directional_cases"], probabilities)
        pvalue = _mcnemar_pvalue(control_wins, treatment_wins)
        pvalues.append(pvalue)
        rejected += int(pvalue < alpha)
    return {"status": "planning_only", "method": "paired_mcnemar_monte_carlo",
            "accuracy_delta": delta, "discordant_rate": discordant,
            "alpha": alpha, "replicates": int(replicates), "seed": seed,
            "assumptions": sample, "control_win_probability": control_win,
            "treatment_win_probability": treatment_win,
            "estimated_power": rejected / int(replicates),
            "pvalue_mean": float(np.mean(pvalues)),
            "note": "模擬規劃值，不是正式資料的檢定結果；跨股票與重疊視窗的相依性需以設計效果敏感度呈現。"}


def power_grid(total_cases=180, accuracy_deltas=(0.05, 0.10, 0.15),
               directional_coverages=(0.5, 0.7, 0.9),
               intracluster_correlations=(0.0, 0.05, 0.10), cluster_size=9,
               discordant_rate=0.30, alpha=0.05, replicates=2000, seed=905):
    """Evaluate a small, reproducible sensitivity grid for planning."""
    results = []
    index = 0
    for coverage in directional_coverages:
        for icc in intracluster_correlations:
            for delta in accuracy_deltas:
                results.append(simulate_mcnemar_power(
                    total_cases=total_cases, accuracy_delta=delta,
                    discordant_rate=discordant_rate,
                    directional_coverage=coverage, cluster_size=cluster_size,
                    intracluster_correlation=icc, alpha=alpha,
                    replicates=replicates, seed=int(seed) + index))
                index += 1
    return {"status": "planning_only", "scenarios": results,
            "note": "請以 effective_directional_cases 與敏感度範圍報告，不以單一 power 值宣稱 180 案例已足夠。"}
