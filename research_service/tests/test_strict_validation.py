"""v3-1001.x: numbers must keep their source scale/unit/metric; the switch round must rebut a real round-1 claim."""
import unittest

from research_service.models import validate_numeric_claims, validate_self_rebuttal

REVENUE = {"evidence_id": "rev", "domain": "fundamental", "comparative": True, "metric": "Revenue",
           "current_period": "2024-12-31", "prior_period": "2023-12-31",
           "current_value": 100, "prior_value": 80, "change_pct": 25.0}


def decision(text, value, unit="USD", metric="Revenue", period="2024-12-31"):
    return {"rationale": text, "risks": [], "evidence_ids": ["rev"],
            "numeric_claims": [{"evidence_id": "rev", "metric": metric, "period": period, "unit": unit,
                                "value": value, "quote": text}]}


class ImmediateRedactionTests(unittest.TestCase):
    def test_v3_1001_redacts_unbound_numbers_without_retrying(self):
        import tempfile
        from research_service.engine import Engine
        from research_service.models import messages_for
        from research_service.protocol import StudyProtocol, decision_plan
        from research_service.storage import Store
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(Store(directory), lambda *a, **k: None)
            protocol = StudyProtocol(version="v3-1002.1", dataset_kind="synthetic", bootstrap_replicates=199)
            call = next(item for item in decision_plan(protocol) if item.key == "a-decision")
            evidence = [{"evidence_id": "rev", "domain": "technical", "claim": "return20 = 0.01", "value": 0.01}]
            answer = {"action": "Buy", "expected_return_pct": 2.0, "confidence": .6, "rationale": "Margins near 12.5",
                      "evidence_ids": ["rev"], "risks": [], "numeric_claims": []}
            calls = []
            engine.call_model = lambda *a, **k: (calls.append(1) or dict(answer), {"prompt_hash": "x", "usage": {}, "raw_response": "x"})
            result, audit = engine.validated_decision(protocol, call, messages_for(call, {"evidence": evidence}, [], [], protocol), evidence)
        self.assertEqual(len(calls), 1)
        self.assertNotIn("12.5", result["rationale"])
        self.assertIn("12.5", audit["numeric_redaction"])


class StrictNumericClaimTests(unittest.TestCase):
    def check(self, text, value, strict, **kwargs):
        result = decision(text, value, **kwargs)
        try:
            validate_numeric_claims(result, [REVENUE], strict=strict, canonical=False)
            return True
        except ValueError:
            return False

    def test_source_value_in_its_own_unit_passes(self):
        self.assertTrue(self.check("Revenue was 100 USD", 100, strict=True))
        self.assertTrue(self.check("Revenue grew 25%", 25.0, strict=True, unit="percent",
                                   metric="Revenue year-over-year change", period="2023-12-31..2024-12-31"))

    def test_rescaled_relabelled_or_misnamed_numbers_fail_when_strict(self):
        self.assertFalse(self.check("Revenue was 100 billion USD", 100, strict=True))
        self.assertFalse(self.check("Revenue was 100億美元", 100, strict=True))
        self.assertFalse(self.check("Net income was 100 USD", 100, strict=True))
        self.assertFalse(self.check("Revenue rose 100%", 100, strict=True))
        self.assertFalse(self.check("Revenue grew 25", 25.0, strict=True, unit="percent",
                                    metric="Revenue year-over-year change", period="2023-12-31..2024-12-31"))

    def test_rounding_to_the_shown_decimals_and_window_labels_pass_when_strict(self):
        source = {**REVENUE, "change_pct": -58.9912}
        def ok(text, value):
            result = decision(text, value, unit="percent", metric="Revenue year-over-year change",
                              period="2023-12-31..2024-12-31")
            try:
                validate_numeric_claims(result, [source], strict=True, canonical=False)
                return True
            except ValueError:
                return False
        self.assertTrue(ok("Revenue fell -58.99% over 20 trading days in 2024", -58.99))
        self.assertTrue(ok("Revenue fell -59%", -59))
        self.assertFalse(ok("Revenue fell -58.98%", -58.98))
        loose = {"rationale": "The 60-day trend and the 20 日 window", "risks": [], "evidence_ids": ["rev"], "numeric_claims": []}
        validate_numeric_claims(loose, [source], strict=True, canonical=False)
        with self.assertRaises(ValueError):
            validate_numeric_claims({**loose, "rationale": "Margins near 12.5"}, [source], strict=True)

    def test_registered_older_versions_keep_their_rule(self):
        # The loophole exists by design in v3-0930.3 (already preregistered runs stay reproducible).
        self.assertTrue(self.check("Revenue was 100 billion USD", 100, strict=False))


class SelfRebuttalTests(unittest.TestCase):
    ROUND1 = {"output": {"rationale": "Data-center demand keeps margins expanding into next quarter.",
                         "strongest_counterpoint": "Export limits could cut China sales.",
                         "risks": ["Valuation is stretched"], "confidence": .7}}

    def test_quoting_an_own_round1_claim_with_the_true_shift_passes(self):
        validate_self_rebuttal({"rebutted_claim": "Data-center demand keeps margins expanding",
                                "confidence": .5, "confidence_shift": -0.2}, self.ROUND1)

    def test_an_invented_claim_fails(self):
        with self.assertRaisesRegex(ValueError, "rebutted_claim"):
            validate_self_rebuttal({"rebutted_claim": "Interest rates will fall sharply this year",
                                    "confidence": .5, "confidence_shift": -0.2}, self.ROUND1)

    def test_empty_numeric_and_trivial_claims_fail_closed(self):
        for text in ("!!!", "...", "123456789", "risk", "a b", "", " "):
            with self.subTest(text=text), self.assertRaises(ValueError):
                validate_self_rebuttal({"rebutted_claim": text, "confidence": .5,
                                       "confidence_shift": -.2}, self.ROUND1)

    def test_chinese_prior_claim_is_supported(self):
        prior = {"rationale": "需求成長有助維持利潤", "confidence": .7}
        validate_self_rebuttal({"rebutted_claim": "需求成長有助維持利潤", "confidence": .5,
                               "confidence_shift": -.2}, prior)

    def test_a_wrong_shift_is_replaced_by_the_true_change_and_kept_for_audit(self):
        result = {"rebutted_claim": "Export limits could cut China sales", "confidence": .5, "confidence_shift": 0.3}
        validate_self_rebuttal(result, self.ROUND1)
        self.assertEqual((result["confidence_shift"], result["confidence_shift_reported"]), (-0.2, 0.3))


if __name__ == "__main__":
    unittest.main()


class OutputCapTests(unittest.TestCase):
    def test_v3_1002_allows_2048_tokens_and_older_versions_keep_1024(self):
        from research_service.protocol import StudyProtocol
        self.assertEqual(StudyProtocol().max_output_tokens, 2048)
        self.assertEqual(StudyProtocol(version="v3-1001.3").max_output_tokens, 1024)
        self.assertEqual(StudyProtocol(version="v3-1002.1").max_output_tokens, 2048)
        self.assertEqual(StudyProtocol(version="v3-0930.3").max_output_tokens, 1024)


class EvidenceReferencePromptTests(unittest.TestCase):
    def test_v3_1002_3_asks_for_evidence_ids_instead_of_numbers(self):
        from research_service.models import messages_for
        from research_service.protocol import DecisionCall, StudyProtocol
        call = DecisionCall("a-decision", "A", "decision", "decision", "NEUTRAL")
        report = {"base_rates": {"hold_band_pct": 3.0}, "evidence": [], "research": {}}
        new = messages_for(call, report, [], [], StudyProtocol())[0]["content"]
        old = messages_for(call, report, [], [], StudyProtocol(version="v3-1002.1"))[0]["content"]
        self.assertIn("Do not restate source numbers", new)
        self.assertNotIn("metric [period] = value unit", new)
        self.assertIn("metric [period] = value unit", old)


class V3_1002_3DefaultsTests(unittest.TestCase):
    def test_new_defaults_apply_only_to_the_new_version(self):
        from research_service.protocol import StudyProtocol
        new, old = StudyProtocol(), StudyProtocol(version="v3-1002.1")
        self.assertEqual((new.hold_band_sigma, new.rationale_chars, new.action_source), (0.5, 600, "model"))
        self.assertEqual((old.hold_band_sigma, old.rationale_chars, old.action_source), (0.5, None, "derived"))

    def test_model_action_prompt_drops_the_neutral_band_rule(self):
        from research_service.models import messages_for
        from research_service.protocol import DecisionCall, StudyProtocol
        call = DecisionCall("a-decision", "A", "decision", "decision", "NEUTRAL")
        report = {"base_rates": {"hold_band_pct": 3.0}, "evidence": [], "research": {}}
        text = messages_for(call, report, [], [], StudyProtocol())[0]["content"]
        self.assertIn("Hold takes no position", text)
        self.assertNotIn("neutral band", text)

    def test_record_only_keeps_the_model_wording(self):
        from research_service.engine import keep_prose
        original = {"rationale": "Revenue was 999 USD (E2).", "risks": ["r 5"], "action": "Buy"}
        redacted = {"rationale": "Revenue was [x] USD (E2).", "risks": ["r [x]"], "action": "Buy",
                    "redacted_numbers": ["999"], "redacted_number_claims": [{"field": "rationale", "value": "999"}]}
        kept = keep_prose(redacted, original)
        self.assertEqual(kept["rationale"], original["rationale"])
        self.assertEqual(kept["risks"], original["risks"])
        self.assertNotIn("redacted_numbers", kept)


class AdjudicatorAndRecordTests(unittest.TestCase):
    def test_v3_1002_3_adjudicator_must_choose_buy_or_sell(self):
        from research_service.models import messages_for, output_schema_for
        from research_service.protocol import StudyProtocol, decision_plan
        report = {"base_rates": {"hold_band_pct": 3.0}, "evidence": [], "research": {}}
        for version, enum in (("v3-1002.3", ["Buy", "Sell"]), ("v3-1002.1", ["Buy", "Hold", "Sell"])):
            protocol = StudyProtocol(version=version)
            call = next(c for c in decision_plan(protocol) if c.key == "d-adjudication")
            schema = output_schema_for(messages_for(call, report, [], [], protocol))
            self.assertEqual(schema["properties"]["action"]["enum"], enum, version)

    def test_record_only_ignores_labels_and_source_values(self):
        from research_service.models import unsupported_numbers
        evidence = [{"evidence_id": "E12", "claim": "return20=-0.041720",
                     "numeric_fields": [{"metric": "return20", "period": "2021-03-30", "unit": "ratio", "value": -0.04172}]}]
        text = "On March 30, 2021 the 20-day return was -0.041720 (E12), about 4.17%, and revenue hit 999 (E2)."
        claims = []
        import re
        from research_service.models import NUMBER_PATTERN
        for m in re.finditer(NUMBER_PATTERN, text):
            claims.append({"field": "rationale", "value": m.group(0), "start": m.start(), "end": m.end()})
        left = unsupported_numbers(claims, {"rationale": text}, evidence)
        self.assertEqual([c["value"] for c in left], ["999"])
