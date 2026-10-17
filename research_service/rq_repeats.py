"""Offline RQ2 v7 analysis: matched repeated seeds, both homogeneous baselines.

This module consumes a validated, frozen export. It never registers or runs an
experiment and does not merge protocol hashes on its own.
"""
import numpy as np

from .rq_analysis import date_block_bootstrap, sharpe_combination_test
from .rq_study import matched_seed_inputs
from .statistics import holm_adjust


def rq2_repeated_inference(correct_by_seed, dates_by_seed, returns_by_seed, trading_dates_by_seed, *,
                           date_block_length=1, daily_block_length=20, replicates=1999, bootstrap_seed=905):
    frame = matched_seed_inputs(correct_by_seed, dates_by_seed)
    seeds, arms = frame["seeds"], frame["arm_names"]
    if set(returns_by_seed) != set(seeds) or set(trading_dates_by_seed) != set(seeds):
        raise ValueError("Correctness and daily returns must contain the identical seed set")
    values = np.asarray(frame["correctness"], dtype=float)
    slot = {arm: i for i, arm in enumerate(arms)}
    hetero = ((values[:, :, slot["D@AB"]] - values[:, :, slot["C@AB"]])
              + (values[:, :, slot["D@BA"]] - values[:, :, slot["C@BA"]])) / 2
    per_seed = np.stack([hetero - (values[:, :, slot[f"D@{baseline}"]]
                                 - values[:, :, slot[f"C@{baseline}"]]) for baseline in ("AA", "BB")], axis=2)
    # Average repeat contributions within each case BEFORE date resampling.
    # The same date draw is used for every seed, stock, arm and baseline.
    accuracy = date_block_bootstrap(per_seed.mean(axis=0), frame["date_ids"],
                                    block_length=date_block_length, replicates=replicates, seed=bootstrap_seed)
    reference_days = list(trading_dates_by_seed[seeds[0]])
    if not reference_days or reference_days != sorted(set(reference_days)):
        raise ValueError("Trading days must be unique and sorted")
    panels = []
    for seed in seeds:
        if list(trading_dates_by_seed[seed]) != reference_days:
            raise ValueError("All seeds must have exactly aligned trading dates")
        series = returns_by_seed[seed]
        if not set(arms) <= series.keys():
            raise ValueError("Every seed needs eight AA/AB/BA/BB daily return columns")
        panel = np.asarray([series[arm] for arm in arms], dtype=float).T
        if panel.shape != (len(reference_days), len(arms)) or not np.isfinite(panel).all():
            raise ValueError("Incomplete or misaligned daily return panel")
        panels.append(panel)
    pooled = np.mean(panels, axis=0)
    het_d = .5 * (pooled[:, slot["D@AB"]] + pooled[:, slot["D@BA"]])
    het_c = .5 * (pooled[:, slot["C@AB"]] + pooled[:, slot["C@BA"]])
    contrasts, pvalues = {}, []
    for index, baseline in enumerate(("AA", "BB")):
        daily = np.column_stack((het_d, het_c, pooled[:, slot[f"D@{baseline}"]], pooled[:, slot[f"C@{baseline}"]]))
        sharpe = sharpe_combination_test(daily, (1., -1., -1., 1.), block_length=daily_block_length,
                                         replicates=replicates, seed=bootstrap_seed)
        acc = accuracy["contrasts"][index]
        if sharpe.get("pvalue") is None:
            raise ValueError("All four family endpoints must be estimable")
        pvalues.extend((acc["pvalue"], sharpe["pvalue"]))
        by_seed = per_seed[:, :, index].mean(axis=1)
        seed_sharpe = {}
        for seed, panel in zip(seeds, panels):
            seed_het_d = .5 * (panel[:, slot["D@AB"]] + panel[:, slot["D@BA"]])
            seed_het_c = .5 * (panel[:, slot["C@AB"]] + panel[:, slot["C@BA"]])
            endpoints = np.column_stack((seed_het_d, seed_het_c,
                                         panel[:, slot[f"D@{baseline}"]],
                                         panel[:, slot[f"C@{baseline}"]]))
            variances = endpoints.var(axis=0)
            if np.any(variances <= 1e-24):
                seed_sharpe[seed] = None
            else:
                endpoint_sharpes = endpoints.mean(axis=0) / np.sqrt(variances)
                seed_sharpe[seed] = float(np.sqrt(252) * np.dot((1., -1., -1., 1.), endpoint_sharpes))
        observed_sharpe = [value for value in seed_sharpe.values() if value is not None]
        sharpe_sd = (float(np.std(observed_sharpe, ddof=1))
                     if len(observed_sharpe) == len(seeds) and len(observed_sharpe) >= 2 else None)
        contrasts[baseline] = {"accuracy": acc, "sharpe": sharpe,
                               "seed_accuracy_interactions": dict(zip(seeds, by_seed.tolist())),
                               "seed_accuracy_sd": float(by_seed.std(ddof=1)),
                               "seed_sharpe_interactions": seed_sharpe,
                               "seed_sharpe_sd": sharpe_sd,
                               "seed_sharpe_observed_count": len(observed_sharpe)}
    adjusted = holm_adjust(pvalues)
    for index, baseline in enumerate(("AA", "BB")):
        contrasts[baseline]["accuracy"]["holm_pvalue"] = adjusted[2 * index]
        contrasts[baseline]["sharpe"]["holm_pvalue"] = adjusted[2 * index + 1]
    return {"schema": "rq2-repeated-analysis/v1", "case_ids": frame["case_ids"],
            "n_cases": len(frame["case_ids"]), "n_seeds": len(seeds),
            "n_analysis_dates": len(set(frame["date_ids"])), "trading_days": len(reference_days),
            "seeds": seeds, "contrasts": contrasts,
            "family": [f"{baseline}:{endpoint}" for baseline in ("AA", "BB") for endpoint in ("accuracy", "sharpe")],
            "date_block_length": date_block_length, "daily_block_length": daily_block_length,
            "replicates": replicates, "bootstrap_seed": bootstrap_seed,
            "estimand": "Within-case mean correctness and equal-weight mean-seed/assignment portfolio",
            "notes": ["Seeds and AB/BA repeats do not increase the number of independent market cases.",
                      "This fixed four-endpoint Holm family must be declared before formal use.",
                      "Seed variability is descriptive; inference is conditional on the locked seed list.",
                      "Raw outputs, report identity, snapshot identity and seed-isolated memory must be validated upstream."]}
