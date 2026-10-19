import unittest
import numpy as np

from research_service.rq_repeats import rq2_repeated_inference
from research_service.rq_analysis import date_block_bootstrap


class RepeatedInferenceTests(unittest.TestCase):
    def fixture(self):
        rng = np.random.default_rng(17)
        seeds = (905, 906, 907)
        arms = [f"{g}@{a}" for a in ("AA", "AB", "BA", "BB") for g in "CD"]
        correct = {str(case): {arm: bool(rng.random() < .55) for arm in arms} for case in range(40)}
        dates = {str(case): f"date-{case // 2:02d}" for case in range(40)}
        returns = {arm: rng.normal(.0002, .01, 120).tolist() for arm in arms}
        days = [f"day-{i:03d}" for i in range(120)]
        return ({seed: correct for seed in seeds}, {seed: dates for seed in seeds},
                {seed: returns for seed in seeds}, {seed: days for seed in seeds})

    def test_copying_seeds_does_not_triple_case_count_or_shrink_accuracy_ci(self):
        values, dates, returns, days = self.fixture()
        result = rq2_repeated_inference(values, dates, returns, days, replicates=199)
        self.assertEqual(result["n_cases"], 40)
        self.assertEqual(result["n_analysis_dates"], 20)
        self.assertEqual(len(result["family"]), 4)
        ids = sorted(values[905])
        rows = values[905]
        contrast = [((int(rows[k]["D@AB"]) - int(rows[k]["C@AB"]))
                     + (int(rows[k]["D@BA"]) - int(rows[k]["C@BA"]))) / 2
                    - (int(rows[k]["D@AA"]) - int(rows[k]["C@AA"])) for k in ids]
        single = date_block_bootstrap(contrast, [dates[905][k] for k in ids], replicates=199)
        self.assertEqual(result["contrasts"]["AA"]["accuracy"]["confidence_interval"], single["confidence_interval"])
        self.assertEqual(result["contrasts"]["AA"]["seed_accuracy_sd"], 0)
        self.assertEqual(result["contrasts"]["AA"]["seed_sharpe_sd"], 0)
        self.assertEqual(result["contrasts"]["AA"]["seed_sharpe_observed_count"], 3)

    def test_seed_sharpe_interactions_match_hand_calculation(self):
        values, dates, returns, days = self.fixture()
        rng = np.random.default_rng(2026)
        for seed in (906, 907):
            returns[seed] = {arm: rng.normal(.0001 * (seed - 904), .008 + .001 * (seed - 905), 120).tolist()
                             for arm in returns[905]}
        result = rq2_repeated_inference(values, dates, returns, days, replicates=199)
        for baseline in ("AA", "BB"):
            expected = []
            for seed in (905, 906, 907):
                series = returns[seed]
                endpoint = np.column_stack((.5 * (np.array(series["D@AB"]) + np.array(series["D@BA"])),
                                            .5 * (np.array(series["C@AB"]) + np.array(series["C@BA"])),
                                            series[f"D@{baseline}"], series[f"C@{baseline}"]))
                sr = endpoint.mean(axis=0) / endpoint.std(axis=0)
                expected.append(float(np.sqrt(252) * np.dot((1., -1., -1., 1.), sr)))
            observed = result["contrasts"][baseline]["seed_sharpe_interactions"]
            np.testing.assert_allclose([observed[s] for s in (905, 906, 907)], expected)
            self.assertAlmostEqual(result["contrasts"][baseline]["seed_sharpe_sd"], np.std(expected, ddof=1))

    def test_degenerate_seed_endpoint_is_none_and_excluded_from_sd(self):
        values, dates, returns, days = self.fixture()
        returns[906] = dict(returns[906])
        returns[907] = dict(returns[907])
        returns[906]["D@AA"] = [0.] * len(days[906])
        returns[907]["D@AA"] = [0.] * len(days[907])
        result = rq2_repeated_inference(values, dates, returns, days, replicates=199)
        aa = result["contrasts"]["AA"]
        self.assertIsNone(aa["seed_sharpe_interactions"][906])
        self.assertIsNone(aa["seed_sharpe_interactions"][907])
        self.assertEqual(aa["seed_sharpe_observed_count"], 1)
        self.assertIsNone(aa["seed_sharpe_sd"])

    def test_partial_seed_sharpe_coverage_has_no_sd(self):
        values, dates, returns, days = self.fixture()
        returns[907] = dict(returns[907])
        returns[907]["D@AA"] = [0.] * len(days[907])
        result = rq2_repeated_inference(values, dates, returns, days, replicates=199)
        aa = result["contrasts"]["AA"]
        self.assertIsNone(aa["seed_sharpe_interactions"][907])
        self.assertEqual(aa["seed_sharpe_observed_count"], 2)
        self.assertIsNone(aa["seed_sharpe_sd"])

    def test_misaligned_days_fail_instead_of_concatenating_seed_series(self):
        values, dates, returns, days = self.fixture()
        days[907] = days[907][:-1]
        with self.assertRaisesRegex(ValueError, "aligned trading"):
            rq2_repeated_inference(values, dates, returns, days, replicates=199)
