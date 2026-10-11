import unittest

import numpy as np

from research_service.rq_analysis import (
    date_block_bootstrap, date_block_indices, domain_agreement_distribution, interaction_mde,
    performance_cost_table, pooled_assignment_returns, rq2_accuracy_interaction, rq2_case_contrasts,
    rq2_sharpe_interaction, rq3_rule_matched_contrasts, sharpe_block_sensitivity, sharpe_combination_test,
    simulate_interaction_power)
from research_service.statistics import date_cluster_block_accuracy, ledoit_wolf_block

N_DATES, PER_DATE = 20, 9
DATES = np.repeat(np.arange(N_DATES), PER_DATE)
FAST = dict(replicates=199, seed=905)


def _correct(seed, *, duplicate_ba=False):
    rng = np.random.default_rng(seed)
    n = N_DATES * PER_DATE
    arms = {name: rng.random(n) < p for name, p in
            (("C_homo", .52), ("D_homo", .55), ("C_hetero_AB", .50), ("D_hetero_AB", .62),
             ("C_hetero_BA", .51), ("D_hetero_BA", .60))}
    if duplicate_ba:
        arms["C_hetero_BA"] = arms["C_hetero_AB"].copy()
        arms["D_hetero_BA"] = arms["D_hetero_AB"].copy()
    return arms


def _returns(seed, t=400):
    rng = np.random.default_rng(seed)
    market = rng.standard_t(6, t) * .006
    return {name: market * beta + rng.normal(mu, .004, t) for name, beta, mu in
            (("C_homo", .5, .0002), ("D_homo", .5, .0003), ("C_hetero_AB", .4, .0001),
             ("D_hetero_AB", .6, .0005), ("C_hetero_BA", .45, .0002), ("D_hetero_BA", .55, .0004))}


class DateBlockBootstrapTests(unittest.TestCase):
    def test_indices_are_circular_consecutive_dates(self):
        indices = date_block_indices(20, 4, np.random.default_rng(1))
        self.assertEqual(len(indices), 20)
        self.assertTrue(np.all(np.diff(indices.reshape(-1, 4), axis=1) % 20 == 1))
        with self.assertRaises(ValueError):
            date_block_indices(5, 4, np.random.default_rng(1))

    def test_estimate_is_case_mean_and_reproducible(self):
        values = np.random.default_rng(2).normal(.05, 1, len(DATES))
        first = date_block_bootstrap(values, DATES, block_length=2, **FAST)
        self.assertAlmostEqual(first["estimate"], values.mean())
        self.assertEqual(first, date_block_bootstrap(values, DATES, block_length=2, **FAST))
        low, high = first["confidence_interval"]
        self.assertLess(low, high)
        self.assertEqual(first["n_dates"], N_DATES)

    def test_estimate_matches_rq1_date_cluster_helper(self):
        rng = np.random.default_rng(9)
        first, second = rng.random(len(DATES)) < .6, rng.random(len(DATES)) < .5
        pairs = {int(day): [(bool(a), bool(b)) for a, b, d in zip(first, second, DATES) if d == day]
                 for day in range(N_DATES)}
        reference = date_cluster_block_accuracy(pairs, replicates=199)
        ours = date_block_bootstrap(first.astype(float) - second, DATES, **FAST)
        self.assertAlmostEqual(ours["estimate"], reference["estimate"])

    def test_zero_contrast_is_not_significant(self):
        result = date_block_bootstrap(np.zeros(len(DATES)), DATES, **FAST)
        self.assertEqual(result["pvalue"], 1.0)

    def test_dates_not_cases_are_resampled(self):
        # A date-level shock shared by every case on that date must widen the
        # interval relative to the same values scattered independently.
        rng = np.random.default_rng(3)
        shocks = np.repeat(rng.normal(0, 1, N_DATES), PER_DATE)
        clustered = date_block_bootstrap(shocks, DATES, **FAST)
        independent = date_block_bootstrap(rng.permutation(shocks), np.arange(len(DATES)), **FAST)
        width = lambda r: np.diff(r["confidence_interval"])[0]  # noqa: E731
        self.assertGreater(width(clustered), 1.5 * width(independent))


class RQ2AccuracyTests(unittest.TestCase):
    def test_mean_option_is_non_binary_and_matches_formula(self):
        arms = _correct(10)
        built = rq2_case_contrasts(arms, "mean")
        self.assertIn(.5, set(np.abs(built["contrasts"]) % 1))
        acc = {k: v.mean() for k, v in arms.items()}
        expected = ((acc["D_hetero_AB"] + acc["D_hetero_BA"]) / 2 - (acc["C_hetero_AB"] + acc["C_hetero_BA"]) / 2
                    - (acc["D_homo"] - acc["C_homo"]))
        result = rq2_accuracy_interaction(arms, DATES, hetero="mean", **FAST)
        self.assertAlmostEqual(result["primary"]["estimate"], expected)
        self.assertEqual(set(result["block_length_sensitivity"]["results"]), {1, 2, 4})
        self.assertNotIn("mean", " ".join(result["secondary_within_condition_mcnemar"]))

    def test_separate_option_reports_ab_and_ba_with_shared_indices(self):
        arms = _correct(11)
        result = rq2_accuracy_interaction(arms, DATES, hetero="separate", **FAST)
        self.assertEqual(result["contrast_labels"], ["interaction_AB", "interaction_BA"])
        ab, ba = result["primary"]["contrasts"]
        self.assertAlmostEqual(ab["estimate"], (arms["D_hetero_AB"].mean() - arms["C_hetero_AB"].mean())
                               - (arms["D_homo"].mean() - arms["C_homo"].mean()))
        self.assertNotAlmostEqual(ab["estimate"], ba["estimate"])

    def test_ab_ba_duplication_does_not_shrink_interval(self):
        duplicated = _correct(12, duplicate_ba=True)
        single = rq2_case_contrasts(duplicated, "separate")["contrasts"][:, 0]
        alone = date_block_bootstrap(single, DATES, **FAST)
        pooled = rq2_accuracy_interaction(duplicated, DATES, hetero="mean", **FAST)["primary"]
        self.assertAlmostEqual(pooled["estimate"], alone["estimate"])
        self.assertAlmostEqual(np.diff(pooled["confidence_interval"])[0],
                               np.diff(alone["confidence_interval"])[0])
        self.assertEqual(pooled["n_cases"], len(DATES))
        # Contrast: naively stacking AB and BA as 2n "independent" cases would
        # shrink the interval -- exactly the error the module rules out.
        stacked = date_block_bootstrap(np.r_[single, single], np.arange(2 * len(DATES)), **FAST)
        self.assertLess(np.diff(stacked["confidence_interval"])[0], np.diff(alone["confidence_interval"])[0])

    def test_rejects_missing_or_non_boolean_arms(self):
        arms = _correct(13)
        del arms["D_hetero_BA"]
        with self.assertRaises(ValueError):
            rq2_case_contrasts(arms)
        arms = _correct(13)
        arms["C_homo"] = arms["C_homo"].astype(float)
        with self.assertRaises(ValueError):
            rq2_case_contrasts(arms)


class SharpeTests(unittest.TestCase):
    def test_two_column_combination_reproduces_ledoit_wolf(self):
        rng = np.random.default_rng(44)
        first = rng.standard_t(7, 300) * .01 + .0004
        second = first * .6 + rng.normal(0, .008, 300)
        config = dict(block_length=10, replicates=199, seed=905)
        reference = ledoit_wolf_block(first, second, **config)
        ours = sharpe_combination_test(np.column_stack((first, second)), (1., -1.), **config)
        self.assertAlmostEqual(ours["annualized_estimate"], reference["annualized_difference"])
        self.assertAlmostEqual(ours["pvalue"], reference["pvalue"])
        np.testing.assert_allclose(ours["confidence_interval"], reference["confidence_interval"])

    def test_interaction_recomputes_sharpes_not_averages(self):
        returns = _returns(5)
        separate = rq2_sharpe_interaction(returns, hetero="separate", block_length=20, **FAST)
        ab = separate["results"]["interaction_AB"]
        sr = {k: v.mean() / v.std() * np.sqrt(252) for k, v in returns.items()}
        self.assertAlmostEqual(ab["annualized_estimate"],
                               sr["D_hetero_AB"] - sr["C_hetero_AB"] - sr["D_homo"] + sr["C_homo"])
        pooled = rq2_sharpe_interaction(returns, hetero="pooled_half_weight", block_length=20, **FAST)
        result = pooled["results"]["interaction_pooled_half_weight"]
        half = pooled_assignment_returns(returns["D_hetero_AB"], returns["D_hetero_BA"])
        self.assertEqual(result["n_days"], 400)
        self.assertAlmostEqual(result["annualized_sharpe"][0], half.mean() / half.std() * np.sqrt(252))
        self.assertNotAlmostEqual(result["annualized_sharpe"][0], (sr["D_hetero_AB"] + sr["D_hetero_BA"]) / 2)
        self.assertEqual(result["status"], "ok")

    def test_misaligned_or_concatenated_series_rejected(self):
        returns = _returns(6)
        returns["D_hetero_AB"] = np.r_[returns["D_hetero_AB"], returns["D_hetero_BA"]]
        with self.assertRaises(ValueError):
            rq2_sharpe_interaction(returns, **FAST)
        with self.assertRaises(ValueError):
            pooled_assignment_returns(np.zeros(5), np.zeros(6))

    def test_identical_arms_are_degenerate_not_significant(self):
        series = _returns(7)["C_homo"]
        returns = {name: series for name in _returns(7)}
        result = rq2_sharpe_interaction(returns, block_length=20, **FAST)["results"]["interaction_AB"]
        self.assertEqual(result["status"], "degenerate")

    def test_sharpe_block_sensitivity(self):
        returns = _returns(8)
        result = sharpe_block_sensitivity(returns, ("D_homo", "C_homo"), (1., -1.), block_lengths=(10, 20, 200),
                                          **FAST)
        self.assertEqual(result["results"][10]["status"], "ok")
        self.assertEqual(result["results"][200]["status"], "not_estimable")


class RQ3Tests(unittest.TestCase):
    def test_rule_matched_contrasts_and_holm_family(self):
        rng = np.random.default_rng(20)
        n = len(DATES)
        correct = {name: rng.random(n) < .55 for name in ("C_domain", "C_generalist", "D_domain", "D_generalist")}
        returns = {name: rng.normal(.0003, .01, 300) for name in correct}
        result = rq3_rule_matched_contrasts(correct, DATES, returns=returns, sharpe_block_length=20,
                                            holm_family=("C:accuracy", "D:accuracy"), **FAST)
        c = result["contrasts"]["C_domain - C_generalist"]
        self.assertAlmostEqual(c["accuracy"]["date_block_bootstrap"]["estimate"],
                               correct["C_domain"].mean() - correct["C_generalist"].mean())
        self.assertEqual(c["sharpe"]["status"], "ok")
        self.assertEqual(set(result["holm"]), {"C:accuracy", "D:accuracy"})
        self.assertGreaterEqual(result["holm"]["C:accuracy"], result["raw_pvalues"]["C:accuracy"])

    def test_performance_cost_table_keeps_missing_separate(self):
        records = [{"arm": "D_domain", "case_id": 1, "calls": 30, "retries": 2, "prompt_tokens": 1000,
                    "completion_tokens": 200, "wall_seconds": 50., "latency_seconds": 60.},
                   {"arm": "D_domain", "case_id": 2, "calls": 28, "retries": 0, "prompt_tokens": None,
                    "completion_tokens": 100, "wall_seconds": 40.},
                   {"arm": "D_generalist", "case_id": 1, "calls": 7, "retries": 1, "prompt_tokens": 400,
                    "completion_tokens": 90}]
        rows = {row["arm"]: row for row in performance_cost_table(records, {"D_domain": {"accuracy": .6}})}
        self.assertEqual(rows["D_domain"]["calls_total"], 58)
        self.assertEqual(rows["D_domain"]["prompt_tokens_missing_cases"], 1)
        self.assertEqual(rows["D_domain"]["latency_seconds_per_case_mean"], 60.)
        self.assertEqual(rows["D_domain"]["accuracy"], .6)
        self.assertIsNone(rows["D_generalist"]["wall_seconds_total"])
        with self.assertRaises(ValueError):
            performance_cost_table(records + [records[0]])

    def test_agreement_distribution_separates_abstentions(self):
        views = [dict(technical="Buy", fundamental="Buy", sentiment="Buy", macro="Buy"),
                 dict(technical="Sell", fundamental="Sell", sentiment="Sell", macro="Sell"),
                 dict(technical="Buy", fundamental="Sell", sentiment="Buy", macro="Buy"),
                 dict(technical="Buy", fundamental="Sell", sentiment="Sell", macro="Buy"),
                 dict(technical="Buy", fundamental="Sell", sentiment="Abstain", macro="Buy"),
                 dict(technical="Buy", fundamental=None, sentiment="Insufficient", macro="Sell")]
        result = domain_agreement_distribution(views, final_correct=np.array([1, 0, 1, 1, 0, 1], dtype=bool))
        self.assertEqual(result["complete_binary_cases"], 4)
        self.assertEqual({k: v["cases"] for k, v in result["distribution"].items()}, {"4:0": 2, "3:1": 1, "2:2": 1})
        self.assertEqual(result["with_abstention"], {"valid_2_of_4": 1, "valid_3_of_4": 1})
        self.assertEqual(result["exploratory_accuracy_by_pattern"]["4:0"]["accuracy"], .5)


class PlanningPowerTests(unittest.TestCase):
    def test_power_is_reproducible_and_labelled(self):
        config = dict(interaction=.15, discordance_rate=.4, replicates=100, seed=1)
        first = simulate_interaction_power(**config)
        self.assertEqual(first, simulate_interaction_power(**config))
        self.assertEqual(first["status"], "planning_only")
        self.assertLessEqual(simulate_interaction_power(interaction=0., replicates=200, seed=2)["estimated_power"],
                             .12)

    def test_duplicate_assignments_do_not_add_power(self):
        common = dict(interaction=.15, discordance_rate=.4, replicates=200, seed=3)
        independent = simulate_interaction_power(assignment_agreement=0., **common)
        duplicate = simulate_interaction_power(assignment_agreement=1., **common)
        ab_only = simulate_interaction_power(assignment_agreement=1., hetero="separate", **common)
        self.assertGreaterEqual(independent["estimated_power"], duplicate["estimated_power"])
        self.assertEqual(duplicate["estimated_power"], ab_only["estimated_power"])

    def test_mde_grid(self):
        result = interaction_mde(interactions=(.05, .3), discordance_rate=.4, replicates=100, seed=4)
        self.assertEqual(result["status"], "planning_only")
        self.assertEqual(result["minimum_detectable_interaction"], .3)
        with self.assertRaises(ValueError):
            simulate_interaction_power(interaction=.5, discordance_rate=.3)


if __name__ == "__main__":
    unittest.main()
