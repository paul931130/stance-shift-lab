import unittest

from research_service.canary import run_model_canary
from research_service.protocol import StudyProtocol


def fake_provider(protocol, messages, seed=None):
    switched = "action MUST be Sell" in messages[0]["content"]
    role_switch = "role-switch round" in messages[0]["content"]
    action = "Sell" if switched else "Buy"
    return ({"action": action, "expected_return_pct": -3.0 if switched else 3.0,
             "confidence": .8, "rationale": "Synthetic canary response",
             "evidence_ids": ["canary-technical"], "risks": [],
             **({"strongest_counterpoint": "Synthetic counterpoint"} if switched else {}),
             **({"rebutted_claim": "Synthetic round-1 claim", "confidence_shift": -0.2} if role_switch else {})},
            {"provider_attempts": 1})


class ModelCanaryTests(unittest.TestCase):
    def test_canary_checks_citation_and_switched_stance_without_jobs(self):
        protocol = StudyProtocol(model="ollama/demo", dataset_kind="synthetic",
                                 bootstrap_replicates=199)
        result = run_model_canary(protocol, fake_provider)
        self.assertEqual(result["status"], "pass")
        self.assertFalse(result["formal_data_touched"])
        self.assertEqual([item["action"] for item in result["checks"]], ["Buy", "Sell"])


if __name__ == "__main__":
    unittest.main()
