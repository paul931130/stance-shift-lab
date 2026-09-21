import unittest

from research_service.power import effective_directional_cases, power_grid, simulate_mcnemar_power


class PowerPlanningTests(unittest.TestCase):
    def test_effective_sample_size_exposes_design_effect(self):
        result = effective_directional_cases(180, .7, cluster_size=9,
                                             intracluster_correlation=.05)
        self.assertEqual(result["nominal_directional_cases"], 126)
        self.assertGreater(result["design_effect"], 1.0)
        self.assertLess(result["effective_directional_cases"], 126)

    def test_simulation_is_reproducible_and_marked_planning_only(self):
        first = simulate_mcnemar_power(total_cases=180, accuracy_delta=.1,
                                       replicates=40, seed=123)
        second = simulate_mcnemar_power(total_cases=180, accuracy_delta=.1,
                                        replicates=40, seed=123)
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "planning_only")
        self.assertGreaterEqual(first["estimated_power"], 0.0)
        self.assertLessEqual(first["estimated_power"], 1.0)

    def test_grid_contains_sensitivity_scenarios(self):
        result = power_grid(accuracy_deltas=(.05,), directional_coverages=(.7,),
                            intracluster_correlations=(0.0, .1), replicates=10)
        self.assertEqual(result["status"], "planning_only")
        self.assertEqual(len(result["scenarios"]), 2)


if __name__ == "__main__":
    unittest.main()
