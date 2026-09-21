import unittest

from research_service.reporting import stability_report


def completed_run(run_id, actions, expected):
    decisions = {group: {"candidate_action": action, "action": action,
                         "expected_return_pct": expected.get(group, 1.0),
                         "confidence": .8, "evidence_ids": [f"evidence-{group}"]}
                 for group, action in actions.items()}
    cases = [{"group": group, "decision_layer": "candidate", "horizon": 60,
              "cost_model": "corwin_schultz", "action": action,
              "candidate_action": action, "status": "complete"}
             for group, action in actions.items()]
    return {"id": run_id, "status": "complete", "created_at": run_id,
            "config": {"ticker": "NVDA", "analysis_date": "2024-12-31",
                       "protocol_hash": "protocol-a"},
            "state": {"finished": True, "report": {}, "decisions": decisions,
                      "cases": cases}}


class StabilityReportTests(unittest.TestCase):
    def test_repeated_runs_are_reported_instead_of_collapsed(self):
        first = completed_run("2024-01-01T00:00:00+00:00",
                              {group: "Buy" for group in "ABCD"}, {})
        second = completed_run("2024-01-02T00:00:00+00:00",
                               {"A": "Sell", "B": "Buy", "C": "Buy", "D": "Buy"},
                               {"A": -2.0})
        result = stability_report([first, second])
        self.assertEqual(result["status"], "descriptive_ready")
        self.assertEqual(result["repeated_cases"], 1)
        self.assertEqual(result["groups"]["A"]["action"]["agreement"], 0.0)
        self.assertGreater(result["groups"]["A"]["expected_return_pct"]["sd"], 0.0)
        self.assertEqual(result["groups"]["B"]["action"]["agreement"], 1.0)

    def test_mixed_protocols_are_not_compared(self):
        first = completed_run("2024-01-01T00:00:00+00:00",
                              {group: "Buy" for group in "ABCD"}, {})
        second = completed_run("2024-01-02T00:00:00+00:00",
                               {group: "Buy" for group in "ABCD"}, {})
        second["config"]["protocol_hash"] = "protocol-b"
        result = stability_report([first, second])
        self.assertEqual(result["status"], "mixed_protocols")
        self.assertEqual(result["repeated_cases"], 0)


if __name__ == "__main__":
    unittest.main()
