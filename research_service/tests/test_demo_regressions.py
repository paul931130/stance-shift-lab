from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_service.data import _canonical_news_url, _deduplicate_news, score_sentiment_finbert
from research_service.readiness import coverage, gap_inventory, study_readiness
from research_service.splits import classify_analysis_date, split_for_date, temporal_split_summary
from research_service.storage import Store


def historical_fixture(kind="historical", evidence_date="2024-12-01"):
    start = date(2023, 1, 1)
    prices = []
    for offset in range(100):
        day = start + timedelta(days=offset)
        if day.weekday() < 5:
            prices.append({"date": day.isoformat(), "open": 1, "high": 2, "low": 1, "close": 1.5})
    evidence = [{"evidence_id": domain, "domain": domain, "claim": "headline", "headline": "headline",
                 "source": "https://example.org/" + domain, "available_at": evidence_date,
                 **({"vintage_date": evidence_date} if domain == "macro" else {})}
                for domain in ("fundamental", "sentiment", "macro")]
    return {"id": kind, "ticker": "NVDA", "kind": kind, "source": "fixture",
            "requested_analysis_date": "2024-12-31", "price_basis": "adjusted_ohlc",
            "prices": prices, "evidence": evidence}


class DemoRegressionTests(unittest.TestCase):
    def test_temporal_roles_are_chronological_and_live_is_excluded(self):
        self.assertEqual(split_for_date("2021-03-31"), "training")
        self.assertEqual(split_for_date("2023-12-31"), "training")
        self.assertEqual(split_for_date("2024-12-31"), "validation")
        self.assertEqual(split_for_date("2025-03-31"), "test")
        self.assertEqual(classify_analysis_date("2026-09-15"), "live")
        with self.assertRaises(ValueError):
            split_for_date("2026-09-15")

    def test_temporal_summary_has_the_full_180_case_target(self):
        summary = temporal_split_summary([])
        self.assertEqual(summary["schema"], "stance-shift-temporal-split/v1")
        self.assertTrue(summary["test_frozen"])
        self.assertEqual(summary["splits"]["training"]["target_cases"], 108)
        self.assertEqual(summary["splits"]["validation"]["target_cases"], 36)
        self.assertEqual(summary["splits"]["test"]["target_cases"], 36)

    def test_readiness_cases_expose_temporal_role(self):
        data = historical_fixture()
        row = {"id": data["id"], "ticker": data["ticker"], "kind": data["kind"],
               "requested_analysis_date": data["requested_analysis_date"], "version": 1,
               "coverage": coverage(data)}
        result = study_readiness([row])
        self.assertEqual(result["cases"][0]["split"], "validation")
        self.assertEqual(result["temporal_splits"]["splits"]["validation"]["available_cases"], 1)

    def test_gap_inventory_lists_every_missing_case_with_reproducible_collection(self):
        inventory = gap_inventory([])
        self.assertEqual(inventory["target_cases"], 180)
        self.assertEqual(inventory["gap_count"], 180)
        first = inventory["gap_cases"][0]
        self.assertEqual(first["ticker"], "AAPL")
        self.assertEqual(first["status"], "missing")
        self.assertEqual(first["deficits"], ["dataset", "technical", "fundamental", "sentiment", "macro"])
        self.assertEqual(first["collect_command"], ".\\research.ps1 collect AAPL 2021-03-31 -UseFinbert")

    def test_readiness_excludes_synthetic_and_future_only_cases(self):
        synthetic = historical_fixture("synthetic")
        future = historical_fixture("historical", "2025-01-01")
        def summary(data):
            return {"id": data["id"], "ticker": data["ticker"], "kind": data["kind"],
                    "requested_analysis_date": data["requested_analysis_date"], "version": 1,
                    "coverage": coverage(data)}
        self.assertEqual(study_readiness([summary(synthetic)])["complete_cases"], 0)
        self.assertEqual(study_readiness([summary(future)])["complete_cases"], 0)

    def test_outcome_counts_are_independent_from_research_domain_completeness(self):
        data = historical_fixture()
        data["evidence"] = [item for item in data["evidence"] if item["domain"] != "sentiment"]
        start = date(2025, 1, 1)
        for offset in range(140):
            day = start + timedelta(days=offset)
            if day.weekday() < 5:
                data["prices"].append({"date": day.isoformat(), "open": 1, "high": 2,
                                       "low": 1, "close": 1.5})
        row = {"id": "outcomes-without-news", "ticker": "NVDA", "kind": "historical",
               "requested_analysis_date": "2024-12-31", "version": 1,
               "coverage": coverage(data)}
        readiness = study_readiness([row])
        self.assertEqual(readiness["evidence_complete_cases"], 0)
        self.assertEqual(readiness["backtest_ready_cases"], 1)
        self.assertEqual(readiness["all_horizons_ready_cases"], 1)

    def test_formal_readiness_requires_comparable_sec_finbert_quality_and_outcomes(self):
        data = historical_fixture()
        start = date(2025, 1, 1)
        for offset in range(100):
            day = start + timedelta(days=offset)
            if day.weekday() < 5:
                data["prices"].append({"date": day.isoformat(), "open": 1, "high": 2,
                                       "low": 1, "close": 1.5})
        fundamental = next(item for item in data["evidence"] if item["domain"] == "fundamental")
        fundamental["comparative"] = True
        sentiment = next(item for item in data["evidence"] if item["domain"] == "sentiment")
        sentiment.update(headline="NVIDIA reports quarterly results",
                         sentiment_scores={"positive": .7, "neutral": .2, "negative": .1},
                         sentiment_input="headline", sentiment_input_hash="hash",
                         sentiment_revision="revision")
        complete = coverage(data)
        self.assertTrue(complete["research_ready"])
        self.assertTrue(complete["formal_experiment_ready"])

        unscored = deepcopy(data)
        for key in ("sentiment_scores", "sentiment_input", "sentiment_input_hash", "sentiment_revision"):
            next(item for item in unscored["evidence"] if item["domain"] == "sentiment").pop(key)
        rows = [
            {"id": "new-unscored", "ticker": "NVDA", "kind": "historical",
             "requested_analysis_date": "2024-12-31", "version": 2, "coverage": coverage(unscored)},
            {"id": "older-complete", "ticker": "NVDA", "kind": "historical",
             "requested_analysis_date": "2024-12-31", "version": 1, "coverage": complete},
        ]
        readiness = study_readiness(rows)
        self.assertEqual((readiness["evidence_complete_cases"],
                          readiness["formal_experiment_ready_cases"]), (1, 1))
        self.assertEqual(readiness["cases"][0]["dataset_id"], "older-complete")

    def test_news_identity_keeps_distinct_query_articles(self):
        self.assertEqual(_canonical_news_url("https://example.org/news?id=1&utm_source=x"),
                         "https://example.org/news?id=1")
        items = [{"evidence_id": "one", "domain": "sentiment", "claim": "same", "headline": "same",
                  "source": "https://example.org/news?id=1", "available_at": "2024-12-01", "source_type": "a"},
                 {"evidence_id": "two", "domain": "sentiment", "claim": "same", "headline": "same",
                  "source": "https://example.org/news?id=2", "available_at": "2024-12-01", "source_type": "b"}]
        self.assertEqual(len(_deduplicate_news(items)[0]), 2)

    def test_sentiment_quality_rejects_unrelated_headlines(self):
        data = historical_fixture()
        sentiment = next(item for item in data["evidence"] if item["domain"] == "sentiment")
        sentiment.update(headline="Broad market commentary", claim="Micron and Palantir market commentary")
        quality = coverage(data)["sentiment_quality"]
        self.assertEqual(quality["ticker_mention_rate"], 0.0)
        self.assertFalse(quality["passes_quality_gate"])

    def test_sentiment_quality_accepts_auditable_provider_ticker_mapping(self):
        data = historical_fixture()
        sentiment = next(item for item in data["evidence"] if item["domain"] == "sentiment")
        sentiment.update(headline="Semiconductor market roundup", claim="Sector news",
                         target_ticker="NVDA", relevance_score=.8,
                         relevance_basis="alpha_vantage_provider_score")
        quality = coverage(data)["sentiment_quality"]
        self.assertEqual(quality["ticker_mention_rate"], 0.0)
        self.assertEqual(quality["target_relevance_rate"], 1.0)
        self.assertTrue(quality["passes_quality_gate"])

        cached = deepcopy(data)
        cached_item = next(item for item in cached["evidence"] if item["domain"] == "sentiment")
        cached_item["relevance_basis"] = "alpha_vantage_cache_per_ticker_file"
        self.assertTrue(coverage(cached)["sentiment_quality"]["passes_quality_gate"])

    def test_sentiment_quality_rejects_untrusted_or_low_relevance_mapping(self):
        for basis, score in (("manual", 1.0), ("alpha_vantage_provider_score", .2)):
            with self.subTest(basis=basis, score=score):
                data = historical_fixture()
                sentiment = next(item for item in data["evidence"] if item["domain"] == "sentiment")
                sentiment.update(headline="Broad market commentary", claim="Sector news",
                                 target_ticker="NVDA", relevance_score=score,
                                 relevance_basis=basis)
                self.assertFalse(coverage(data)["sentiment_quality"]["passes_quality_gate"])

    def test_finbert_failure_does_not_mutate_dataset(self):
        data = historical_fixture()
        data["evidence"].append({"evidence_id": "sentiment-2", "domain": "sentiment", "claim": "second",
                                  "headline": "second", "source": "https://example.org/second",
                                  "available_at": "2024-12-02"})
        original = deepcopy(data)
        calls = 0

        def requester(_text):
            nonlocal calls
            calls += 1
            if calls == 2:
                return [{"label": "positive", "score": 2.0}]
            return [{"label": "positive", "score": .7}, {"label": "negative", "score": .1}, {"label": "neutral", "score": .2}]

        with self.assertRaises(ValueError):
            score_sentiment_finbert(data, requester)
        self.assertEqual(data, original)

    def test_pause_running_job_changes_state_and_resume_queues_it(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory))
            config = {
                "ticker": "NVDA", "analysis_date": "2024-12-31", "dataset_id": "fixture",
                "protocol": {"version": "v3-0913.1"}, "protocol_hash": "fixture",
            }
            job = store.create(config)
            store.claim()  # transition queued -> running, as the worker does
            store.control(job["id"], "pause")
            self.assertEqual(store.get(job["id"])["status"], "paused")
            store.control(job["id"], "resume")
            resumed = store.get(job["id"])
            self.assertEqual(resumed["status"], "queued")
            self.assertEqual(resumed["wants_run"], 1)


if __name__ == "__main__":
    unittest.main()
