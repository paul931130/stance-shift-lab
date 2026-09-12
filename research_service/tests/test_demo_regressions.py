from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_service.data import _canonical_news_url, _deduplicate_news, score_sentiment_finbert
from research_service.finnhub import live_snapshot
from research_service.readiness import coverage, study_readiness
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
    def test_readiness_excludes_synthetic_and_future_only_cases(self):
        synthetic = historical_fixture("synthetic")
        future = historical_fixture("historical", "2025-01-01")
        def summary(data):
            return {"id": data["id"], "ticker": data["ticker"], "kind": data["kind"],
                    "requested_analysis_date": data["requested_analysis_date"], "version": 1,
                    "coverage": coverage(data)}
        self.assertEqual(study_readiness([summary(synthetic)])["complete_cases"], 0)
        self.assertEqual(study_readiness([summary(future)])["complete_cases"], 0)

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

    def test_empty_finnhub_panels_are_not_ready(self):
        def empty(_url, _headers):
            return {}

        with patch.dict("os.environ", {"FINNHUB_API_KEY": "demo"}):
            result = live_snapshot("ASTS", empty, today=date(2026, 9, 8))
        self.assertEqual(result["status"], "unavailable")
        self.assertTrue(all(panel["status"] != "ready" for panel in result["panels"].values()))

    def test_pause_running_job_changes_state_and_resume_queues_it(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory))
            config = {
                "ticker": "NVDA", "analysis_date": "2024-12-31", "dataset_id": "fixture",
                "protocol": {"version": "v3-0912.1"}, "protocol_hash": "fixture",
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
