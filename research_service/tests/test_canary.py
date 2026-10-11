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
        # v3-1002.3: the complete 22-call plan, including both adjudicators.
        checks = {item["call"]: item for item in result["checks"]}
        self.assertEqual(len(checks), 22)
        self.assertTrue(all(item["status"] == "pass" for item in checks.values()))
        self.assertEqual((checks["d-r1-agent-a"]["action"], checks["d-r2-agent-a"]["action"]), ("Buy", "Sell"))
        self.assertIn(checks["c-adjudication"]["action"], ("Buy", "Sell"))

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

    def test_failed_first_call_blocks_remaining_paid_model_calls(self):
        calls = []

        def unavailable(protocol, messages, seed=None):
            calls.append(messages[0]["content"])
            raise TimeoutError("provider unavailable")

        result = run_model_canary(StudyProtocol(dataset_kind="synthetic"), unavailable)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(len(calls), 1)
        self.assertEqual([item["status"] for item in result["checks"]], ["fail"] + ["blocked"] * 21)

    def test_numeric_canary_tells_model_to_copy_a_supported_canonical_fact(self):
        seen = []

        def capture(protocol, messages, seed=None):
            seen.append(messages[0]["content"])
            return fake_provider(protocol, messages, seed)

        # The canonical-statement drill belongs to v3-1001.3/v3-1002.1 only.
        result = run_model_canary(StudyProtocol(version="v3-1002.1", dataset_kind="synthetic"), capture)
        self.assertEqual(result["status"], "pass")
        self.assertTrue(all("return20 [2024-12-31] = 0.01 decimal_return" in prompt for prompt in seen))

    def test_evidence_reference_canary_does_not_ask_for_numbers(self):
        seen = []

        def capture(protocol, messages, seed=None):
            seen.append(messages[0]["content"])
            return fake_provider(protocol, messages, seed)

        run_model_canary(StudyProtocol(dataset_kind="synthetic"), capture)
        self.assertFalse(any("return20 [2024-12-31]" in prompt for prompt in seen))

    def test_adjudicator_hold_fails_the_canary(self):
        def holding(protocol, messages, seed=None):
            result, audit = fake_provider(protocol, messages, seed)
            if "The Adjudicator must choose Buy or Sell" in messages[0]["content"]:
                result.update(action="Hold", expected_return_pct=0.0)
            return result, audit

        result = run_model_canary(StudyProtocol(dataset_kind="synthetic"), holding)
        self.assertEqual(result["status"], "fail")


if __name__ == "__main__":
    unittest.main()
