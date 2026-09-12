from types import SimpleNamespace
from datetime import date, timedelta
import math
import unittest

from research_service.backtest import evaluate, rolling_spread, spread


def protocol():
    return SimpleNamespace(horizons=(60,), cost_models=("zero", "corwin_schultz"),
                           primary_horizon=60, spread_window=20)


def prices():
    rows = []
    for index in range(150):
        value = 100.0 + index * .2
        if index >= 63:
            value = 250.0 + index  # A short position becomes insolvent early.
        rows.append({"date": (date(2024, 1, 1) + timedelta(days=index)).isoformat(),
                     "open": value, "high": value + 2, "low": value - 2, "close": value + .5})
    return rows


class BacktestTests(unittest.TestCase):
    def test_rolling_spread_uses_available_pairs_and_median(self):
        bars = [{"high": 11.0 + index, "low": 9.0 + index} for index in range(5)]
        pairs = [spread(left, right) for left, right in zip(bars[:-1], bars[1:])]
        self.assertEqual(rolling_spread([], 20), 0.0)
        self.assertAlmostEqual(rolling_spread(bars, 20), sorted(pairs)[len(pairs) // 2])
        self.assertAlmostEqual(rolling_spread(bars, 2), sorted(pairs[-2:])[1])

    def test_candidate_and_gated_layers_reconcile_open_to_open_and_keep_insolvency(self):
        analysis_date = prices()[60]["date"]
        decisions = {
            "A": {"candidate_action": "Sell", "action": "Hold", "hold_band_pct": 1.0},
            "B": {"candidate_action": "Buy", "action": "Buy", "hold_band_pct": 1.0},
            "C": {"candidate_action": "Hold", "action": "Hold", "hold_band_pct": 1.0},
            "D": {"candidate_action": "Sell", "action": "Sell", "hold_band_pct": 1.0},
        }
        rows, daily = evaluate(prices(), analysis_date, decisions, protocol())
        self.assertEqual(len(rows), 16)  # Four groups × candidate/gated × two cost models.
        candidate_short = next(row for row in rows if row["group"] == "A" and row["decision_layer"] == "candidate" and row["cost_model"] == "zero")
        gated_hold = next(row for row in rows if row["group"] == "A" and row["decision_layer"] == "gated" and row["cost_model"] == "zero")
        self.assertEqual((candidate_short["status"], candidate_short["net_return"], candidate_short["insolvent"]),
                         ("complete", -1.0, True))
        self.assertEqual(gated_hold["net_return"], 0.0)
        candidate_daily = [row["return"] for row in daily if row["group"] == "A" and row["decision_layer"] == "candidate" and row["cost_model"] == "zero"]
        first_zero = next(index for index, value in enumerate(candidate_daily) if math.isclose(value, 0.0))
        self.assertTrue(all(math.isclose(value, 0.0) for value in candidate_daily[first_zero:]))
        buy = next(row for row in rows if row["group"] == "B" and row["decision_layer"] == "candidate" and row["cost_model"] == "corwin_schultz")
        buy_daily = [row["return"] for row in daily if row["group"] == "B" and row["decision_layer"] == "candidate" and row["cost_model"] == "corwin_schultz"]
        self.assertAlmostEqual(math.prod(1 + value for value in buy_daily) - 1, buy["net_return"], places=12)
        hold = next(row for row in rows if row["group"] == "C" and row["decision_layer"] == "candidate" and row["cost_model"] == "zero")
        self.assertFalse(hold["hold_was_justified"])
        self.assertGreater(hold["hold_opportunity_cost"], 0.0)


if __name__ == "__main__":
    unittest.main()
