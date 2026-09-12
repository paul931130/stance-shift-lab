import unittest
import numpy as np
from research_service.statistics import (mcnemar, jobson_korkie_memmel, ledoit_wolf_block,
                                         circular_block_indices, aligned_portfolio_returns, holm_adjust)


class StatisticsTests(unittest.TestCase):
    def test_mcnemar_exact_known_binomial_example(self):
        result = mcnemar([True] * 10, [False] * 10)
        self.assertAlmostEqual(result["pvalue"], 2 / 2 ** 10)
        self.assertEqual(result["table"], [[0, 10], [0, 0]])
        self.assertEqual(mcnemar([True, False], [True, False])["pvalue"], 1)
        with self.assertRaises(ValueError):
            mcnemar([1, 0], [0, 1])

    def test_identical_strategies_not_falsely_significant(self):
        returns = np.random.default_rng(10).normal(.001, .02, 200)
        self.assertIsNone(jobson_korkie_memmel(returns, returns)["pvalue"])
        self.assertEqual(ledoit_wolf_block(returns, returns, replicates=199)["status"], "degenerate")

    def test_circular_blocks_and_date_panel_stay_paired(self):
        indices = circular_block_indices(100, 5, np.random.default_rng(3)).reshape(-1, 5)
        self.assertTrue(np.all(np.diff(indices, axis=1) % 100 == 1))
        panel = np.arange(60).reshape(10, 3, 2)
        result = aligned_portfolio_returns(panel)
        self.assertTrue(np.allclose(result, panel.mean(axis=1)))
        bad = panel.astype(float)
        bad[0, 0, 0] = np.nan
        with self.assertRaises(ValueError):
            aligned_portfolio_returns(bad)

    def test_studentized_bootstrap_reproducible_and_swap_symmetric(self):
        rng = np.random.default_rng(44)
        first = rng.standard_t(7, 300) * .01 + .0004
        second = first * .6 + rng.normal(0, .008, 300)
        config = dict(block_length=10, replicates=199, seed=905)
        a = ledoit_wolf_block(first, second, **config)
        b = ledoit_wolf_block(second, first, **config)
        self.assertEqual(a, ledoit_wolf_block(first, second, **config))
        self.assertAlmostEqual(a["pvalue"], b["pvalue"])
        self.assertAlmostEqual(a["confidence_interval"][0], -b["confidence_interval"][1])
        self.assertGreater(a["valid_replicates"], 180)
        self.assertEqual(a["sampled_n"], 300)

    def test_invalid_or_degenerate_data_fails_closed(self):
        with self.assertRaises(ValueError):
            jobson_korkie_memmel([0] * 10, [0] * 10)
        with self.assertRaises(ValueError):
            ledoit_wolf_block(np.arange(20), np.arange(20) ** 2, block_length=10)
        self.assertEqual(holm_adjust([.01, .04, .03]), [.03, .06, .06])


if __name__ == "__main__":
    unittest.main()
