import unittest

from research_service.canary import run_model_canary
from research_service.protocol import StudyProtocol


def fake_provider(protocol, messages, seed=None):
    switched = "action MUST be Sell" in messages[0]["content"]
    role_switch = "role-switch round" in messages[0]["content"]
    debate = "action MUST be" in messages[0]["content"]
    action = "Sell" if switched else "Buy"
    fact = "return20 [2024-12-31] = 0.01 decimal_return"
    return ({"action": action, "expected_return_pct": -3.0 if switched else 3.0,
             "confidence": .8, "rationale": "Synthetic canary response. " + fact + ".",
             "evidence_ids": ["canary-technical"], "risks": [],
             "numeric_claims": [{"evidence_id": "canary-technical", "metric": "return20",
                                 "period": "2024-12-31", "unit": "decimal_return", "value": .01, "quote": fact}],
             **({"strongest_counterpoint": "Synthetic counterpoint"} if debate else {}),
             **({"rebutted_claim": "Synthetic canary response", "confidence_shift": 0} if role_switch else {})},
            {"provider_attempts": 1})


class ModelCanaryTests(unittest.TestCase):
    def test_canary_checks_citation_and_switched_stance_without_jobs(self):
        protocol = StudyProtocol(model="ollama/demo", dataset_kind="synthetic",
                                 bootstrap_replicates=199)
        result = run_model_canary(protocol, fake_provider)
        self.assertEqual(result["status"], "pass")
        self.assertFalse(result["formal_data_touched"])
        self.assertEqual([item["action"] for item in result["checks"]], ["Buy", "Buy", "Sell"])

    def test_empty_rebuttal_and_short_numeric_quotes_fail_qualification(self):
        for defect in ("rebuttal", "numeric"):
            def broken(protocol, messages, seed=None):
                result, audit = fake_provider(protocol, messages, seed)
                if defect == "numeric":
                    result["numeric_claims"][0]["quote"] = "0.01"
                elif "role-switch round" in messages[0]["content"]:
                    result["rebutted_claim"] = "!!!"
                return result, audit
            with self.subTest(defect=defect):
                result = run_model_canary(StudyProtocol(dataset_kind="synthetic"), broken)
                self.assertEqual(result["status"], "fail")


if __name__ == "__main__":
    unittest.main()
