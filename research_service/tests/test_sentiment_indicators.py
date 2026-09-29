"""v3-0930.1: sentiment reaches the models as FinBERT indicators over every headline."""
import json
import unittest
from types import SimpleNamespace

from research_service.data import research_inputs, validate_dataset
from research_service.errors import PreflightError
from research_service.models import _compact_calibration, _decision_evidence, messages_for
from research_service.protocol import DecisionCall, StudyProtocol
from research_service.tests.test_workflow import fixture
from research_service.web.context import JobInput
from research_service.web.jobs import prepare

DAY = "2024-12-31"


def headline(index, scope, score, day="2024-12-10"):
    text = (f"NVIDIA distinctive headline number {index}" if scope == "target"
            else f"Chip sector distinctive headline number {index}")
    return {"evidence_id": f"news-{scope}-{index}", "domain": "sentiment", "claim": text, "headline": text,
            "source": f"https://example.com/{scope}/{index}", "available_at": day,
            "source_type": "alpha_vantage_news_sentiment", "relevance_score": .9,
            "relevance_basis": "alpha_vantage_provider_score", "sentiment_score": score}


def dataset(target_scores, context_scores):
    data = fixture()
    data["evidence"] = [item for item in data["evidence"] if item["domain"] != "sentiment"]
    data["evidence"] += [headline(i, "target", score) for i, score in enumerate(target_scores)]
    data["evidence"] += [headline(i, "context", score) for i, score in enumerate(context_scores)]
    return validate_dataset(data)


class IndicatorProtocolTests(unittest.TestCase):
    def test_versions_choose_the_rule(self):
        self.assertTrue(StudyProtocol().sentiment_indicators)
        self.assertTrue(StudyProtocol.monthly().sentiment_indicators)
        self.assertFalse(StudyProtocol(version="v3-0929.1").sentiment_indicators)
        self.assertFalse(StudyProtocol(version="v3-0927.2").sentiment_indicators)


class IndicatorInputTests(unittest.TestCase):
    def setUp(self):
        # 40 direct headlines (well above the old 12-headline sample) and 20 context headlines.
        self.target_scores = [.5] * 10 + [.05] * 20 + [-.4] * 10
        self.context_scores = [.2] * 20
        self.data = dataset(self.target_scores, self.context_scores)

    def indicators(self, inputs):
        return {item["evidence_id"].split("-" + DAY)[0]: item for item in inputs["evidence"]
                if item.get("source_type") == "finbert_indicator"}

    def test_indicators_use_every_headline_and_carry_no_headline_text(self):
        inputs = research_inputs(self.data, DAY, StudyProtocol())
        found = self.indicators(inputs)
        self.assertEqual(set(found), {"sentiment-target-mean", "sentiment-target-positive_share",
                                      "sentiment-target-negative_share", "sentiment-context-mean"})
        mean = sum(self.target_scores) / len(self.target_scores)
        self.assertAlmostEqual(found["sentiment-target-mean"]["value"], mean)
        self.assertAlmostEqual(found["sentiment-target-positive_share"]["value"], .25)   # 10 of 40 above +0.10
        self.assertAlmostEqual(found["sentiment-target-negative_share"]["value"], .25)   # 10 of 40 below -0.10
        self.assertAlmostEqual(found["sentiment-context-mean"]["value"], .2)
        self.assertEqual(found["sentiment-target-mean"]["headline_count"], 40)
        self.assertEqual(inputs["evidence_selection"]["sentiment"]["strategy"], "finbert_indicators_v1")
        self.assertEqual(inputs["evidence_selection"]["sentiment"]["target_available"], 40)
        self.assertFalse([item for item in inputs["evidence"]
                          if item["domain"] == "sentiment" and item.get("source_type") != "finbert_indicator"])

    def test_the_old_rule_still_samples_twelve_headlines(self):
        inputs = research_inputs(self.data, DAY, StudyProtocol(version="v3-0929.1"))
        self.assertEqual(sum(item["domain"] == "sentiment" for item in inputs["evidence"]), 12)
        self.assertEqual(inputs["evidence_selection"]["sentiment"]["selected"], 12)

    def test_calibration_shows_shares_but_no_headline_counts(self):
        inputs = research_inputs(self.data, DAY, StudyProtocol())
        calibration = inputs["decision_calibration"]
        self.assertEqual(calibration["rules_version"], "finbert-indicators-v1")
        self.assertEqual(calibration["sentiment"]["target"]["headline_count"], 40)  # kept for audit
        shown = _compact_calibration(calibration)
        self.assertEqual(set(shown["sentiment_target"]), {"mean_score", "positive_share", "negative_share", "direction"})
        self.assertEqual(set(shown["sentiment_context"]), {"mean_score"})

    def test_decision_prompt_has_indicators_and_never_a_headline(self):
        inputs = research_inputs(self.data, DAY, StudyProtocol())
        report = {"ticker": "NVDA", "analysis_date": DAY, "evidence": inputs["evidence"], "research": {},
                  "decision_calibration": inputs["decision_calibration"], "base_rates": inputs["base_rates"]}
        evidence = _decision_evidence(report)
        self.assertEqual(sum(item["domain"] == "sentiment" for item in evidence), 4)
        call = DecisionCall("a-decision", "A", "decision", "decision", "NEUTRAL")
        prompt = json.dumps(messages_for(call, report, [], [], StudyProtocol()), ensure_ascii=False)
        self.assertIn("sentiment_target_mean", prompt)
        self.assertNotIn("distinctive headline", prompt)

    def test_no_headline_in_the_window_leaves_the_sentiment_domain_empty(self):
        inputs = research_inputs(dataset([], []), DAY, StudyProtocol())
        self.assertEqual(inputs["evidence_selection"]["sentiment"]["selected"], 0)
        self.assertFalse([item for item in inputs["evidence"] if item["domain"] == "sentiment"])

    def test_a_dataset_may_keep_more_than_400_headlines(self):
        many = dataset([.1] * 1500, [])
        self.assertEqual(sum(item["domain"] == "sentiment" for item in many["evidence"]), 1500)
        inputs = research_inputs(many, DAY, StudyProtocol())
        self.assertEqual(inputs["evidence_selection"]["sentiment"]["target_available"], 1500)


class CappedNewsGuardTests(unittest.TestCase):
    def prepare(self, rules):
        class Store:
            @staticmethod
            def dataset(_key):
                return {"ticker": "AAPL", "kind": "historical", "requested_analysis_date": DAY,
                        "collection_rules": rules}

        payload = JobInput(dataset_id="snapshot", analysis_date=DAY)
        ctx = SimpleNamespace(store=Store, demo_mode=False, injected_model_call=True, demo_model_id="")
        return prepare(ctx, payload)

    def test_a_dataset_with_capped_news_is_refused(self):
        with self.assertRaises(PreflightError) as caught:
            self.prepare({"version": "point-in-time-input-v2"})
        self.assertEqual(caught.exception.reason, "news_capped")


if __name__ == "__main__":
    unittest.main()
