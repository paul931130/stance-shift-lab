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


class StrictNumericClaimTests(unittest.TestCase):
    def check(self, text, value, strict, **kwargs):
        result = decision(text, value, **kwargs)
        try:
            validate_numeric_claims(result, [REVENUE], strict=strict)
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

    def test_a_wrong_shift_is_replaced_by_the_true_change_and_kept_for_audit(self):
        result = {"rebutted_claim": "Export limits could cut China sales", "confidence": .5, "confidence_shift": 0.3}
        validate_self_rebuttal(result, self.ROUND1)
        self.assertEqual((result["confidence_shift"], result["confidence_shift_reported"]), (-0.2, 0.3))


if __name__ == "__main__":
    unittest.main()
