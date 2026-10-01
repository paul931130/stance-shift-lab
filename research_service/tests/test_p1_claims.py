"""P1 regressions: bind the whole typed statement, never a numeric substring."""
from dataclasses import asdict
import unittest

from research_service.models import messages_for, validate_numeric_claims
from research_service.protocol import StudyProtocol, decision_plan, protocol_is_current


SOURCE = {"evidence_id": "rev", "domain": "fundamental", "comparative": True,
          "metric": "Revenue", "current_period": "2024-12-31", "current_value": 100}
FACT = "Revenue [2024-12-31] = 100 USD"


def answer(text=FACT, quote=FACT, **claim_changes):
    claim = {"evidence_id": "rev", "metric": "Revenue", "period": "2024-12-31",
             "unit": "USD", "value": 100, "quote": quote, **claim_changes}
    return {"rationale": text, "risks": [], "evidence_ids": ["rev"], "numeric_claims": [claim]}


class CanonicalClaimTests(unittest.TestCase):
    def test_complete_statement_and_all_repeated_occurrences_pass(self):
        for text, quote in ((FACT, FACT), (FACT + ".", FACT + "."),
                            (FACT + ". " + FACT + ".", FACT),
                            ("Evidence supports the view. " + FACT + ".", FACT)):
            with self.subTest(text=text):
                validate_numeric_claims(answer(text, quote), [SOURCE], strict=True)
        result = answer()
        result["risks"] = [FACT]
        validate_numeric_claims(result, [SOURCE], strict=True)

    def test_numeric_substrings_cannot_change_scale_metric_currency_or_period(self):
        bad = (("Revenue was 100 billion USD.", "100"),
               ("Net income was 100 USD.", "100"),
               ("Revenue was 100 EUR.", "Revenue was 100 EUR."),
               ("Revenue [2023-12-31] = 100 USD", "Revenue [2023-12-31] = 100 USD"),
               ("NetIncomeLoss [2024-12-31] = 100 USD", "NetIncomeLoss [2024-12-31] = 100 USD"),
               ("Revenue [2024-12-31] = 100 EUR", "Revenue [2024-12-31] = 100 EUR"),
               ("Net income is " + FACT, FACT), (FACT + " billion", FACT),
               (FACT + " instead of net income", FACT))
        for text, quote in bad:
            with self.subTest(text=text), self.assertRaises(ValueError):
                validate_numeric_claims(answer(text, quote), [SOURCE], strict=True)

    def test_absent_quote_never_covers_another_field(self):
        for canonical, text, quote in ((True, FACT, FACT),
                                       (False, "Revenue was 100 USD in the current reporting period.",
                                        "Revenue was 100 USD in the current reporting period.")):
            result = answer(text, quote)
            result["risks"] = ["Fabricated value is 100."]
            with self.subTest(canonical=canonical), self.assertRaises(ValueError):
                validate_numeric_claims(result, [SOURCE], strict=True, canonical=canonical)

    def test_noncanonical_year_sized_values_are_not_exempt(self):
        result = answer("Revenue was 2000 USD")
        result["numeric_claims"] = []
        with self.assertRaises(ValueError):
            validate_numeric_claims(result, [SOURCE], strict=True)

    def test_a_model_forecast_is_not_a_source_revenue_value(self):
        fact = "Revenue [2024-12-31] = 5 USD"
        result = answer(fact, fact, value=5)
        result["expected_return_pct"] = 5
        with self.assertRaises(ValueError):
            validate_numeric_claims(result, [SOURCE], strict=True)

    def test_source_window_and_period_labels_are_bound_by_the_whole_fact(self):
        metric, period = "20-day momentum", "2023-12-31..2024-12-31"
        source = {"evidence_id": "rev", "numeric_fields": [
            {"metric": metric, "period": period, "unit": "decimal_return", "value": .1}]}
        fact = f"{metric} [{period}] = 0.1 decimal_return"
        validate_numeric_claims(answer(fact + ".", fact, metric=metric, period=period,
                                       value=.1, unit="decimal_return"), [source], strict=True)

    def test_redaction_removes_invalid_claims_and_keeps_supported_facts(self):
        result = answer(FACT + ". Revenue was 100 billion USD.")
        result["numeric_claims"].append({**result["numeric_claims"][0], "quote": "100"})
        validate_numeric_claims(result, [SOURCE], strict=True, redact=True)
        self.assertIn(FACT, result["rationale"])
        self.assertNotIn("100 billion", result["rationale"])
        self.assertEqual(result["numeric_claims_removed"], 1)
        self.assertEqual(len(result["numeric_claims"]), 1)
        self.assertEqual(result["redacted_numbers"], ["100"])
        unused = answer(FACT + " billion")
        validate_numeric_claims(unused, [SOURCE], strict=True, redact=True)
        self.assertEqual(unused["numeric_claims"], [])

    def test_source_value_sign_and_displayed_precision_are_preserved(self):
        source = {**SOURCE, "current_value": -58.9912}
        for value in (-58.99, -59):
            fact = f"Revenue [2024-12-31] = {value} USD"
            validate_numeric_claims(answer(fact, fact, value=value), [source], strict=True)
        for value in (58.99, -58.98):
            fact = f"Revenue [2024-12-31] = {value} USD"
            with self.assertRaises(ValueError):
                validate_numeric_claims(answer(fact, fact, value=value), [source], strict=True)

    def test_percent_and_nonfinancial_typed_units_pass(self):
        for metric, unit, value in (("mean20_vs_mean60", "decimal_return", .025),
                                    ("FEDFUNDS", "percent_per_year", 5.25),
                                    ("CPIAUCSL", "index_points", 309.2)):
            source = {"evidence_id": "rev", "numeric_fields": [
                {"metric": metric, "period": "2024-12-31", "unit": unit, "value": value}]}
            fact = f"{metric} [2024-12-31] = {value} {unit}"
            validate_numeric_claims(answer(fact, fact, metric=metric, unit=unit, value=value),
                                    [source], strict=True)

    def test_new_protocol_and_prompts_do_not_change_recorded_old_hash(self):
        old = StudyProtocol(version="v3-1001.1", model="ollama/qwen3:32b")
        self.assertEqual(old.fingerprint, StudyProtocol(**asdict(old)).fingerprint)
        self.assertEqual(old.fingerprint, "6be8da8372f987ea7a77cf887af5bf37055521a948abdeb150b31949dd2e82a0")
        current = StudyProtocol(model="ollama/qwen3:32b")
        self.assertNotEqual(current.fingerprint, old.fingerprint)
        self.assertFalse(protocol_is_current(asdict(old)))
        call = decision_plan(current)[0]
        report = {"evidence": [SOURCE]}
        new_prompt = messages_for(call, report, [], [], current)[0]["content"]
        old_prompt = messages_for(call, report, [], [], old)[0]["content"]
        self.assertIn("metric [period] = value unit", new_prompt)
        self.assertNotIn("metric [period] = value unit", old_prompt)


if __name__ == "__main__":
    unittest.main()
