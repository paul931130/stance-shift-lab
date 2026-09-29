"""Readiness rules behind POST /api/jobs/preflight.

The web UI no longer re-implements these rules; it asks the server, which
runs the same validation used when a job is created. These cases replace
the former Node tests of the client-side copy.
"""
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from research_service.app import create_app
from research_service.data import validate_dataset
from research_service.storage import Store
from research_service.tests.test_workflow import fake_model, fixture

GOOD_SENTIMENT = {"items": 10, "passes_quality_gate": True, "finbert_complete": True}
GOOD_FUNDAMENTAL = {"items": 4, "passes_quality_gate": True}


def ollama_tags(*models):
    """A fake Ollama /api/tags response listing (name, parameter_size) pairs."""
    return {"models": [{"name": name, "details": {"parameter_size": size}} for name, size in models]}


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name)
        historical = validate_dataset(fixture())
        historical.update(kind="historical", collection_rules={"news_item_limit": "uncapped"}, requested_analysis_date="2024-12-31")
        self.historical_id = self.store.add_dataset(historical)
        self.synthetic_id = self.store.add_dataset(validate_dataset(fixture()))

    def tearDown(self):
        self.tmp.cleanup()

    def preflight(self, quality=None, model_call=fake_model, tags=None, **payload):
        """Run one preflight with controlled dataset quality and Ollama inventory."""
        body = {"dataset_id": self.historical_id, "analysis_date": "2024-12-31",
                "model": "ollama/qwen3:14b", **payload}
        coverage_result = {"sentiment_quality": GOOD_SENTIMENT, "fundamental_quality": GOOD_FUNDAMENTAL, **(quality or {})}
        with patch("research_service.web.jobs.coverage", return_value=coverage_result), \
             patch("research_service.web.ollama.get_json", return_value=tags or ollama_tags(("qwen3:14b", "14.8B"))) as probe:
            with TestClient(create_app(self.store, model_call, start_worker=False)) as client:
                result = client.post("/api/jobs/preflight", json=body).json()
        self.probe_calls = probe.call_count
        return result

    def assertBlocked(self, result, reason):
        self.assertFalse(result["ready"], result)
        self.assertEqual(result["reason"], reason)
        self.assertTrue(result["message"])

    def test_everything_satisfied_is_ready_and_creates_nothing(self):
        result = self.preflight()
        self.assertTrue(result["ready"], result)
        self.assertEqual(result["reason"], "ready")
        self.assertEqual(self.store.jobs(), [])

    def test_unknown_dataset(self):
        self.assertBlocked(self.preflight(dataset_id="missing"), "no_dataset")

    def test_analysis_date_must_match_historical_cut(self):
        self.assertBlocked(self.preflight(analysis_date="2024-09-30"), "date_mismatch")

    def test_synthetic_dataset_is_exempt_from_date_match(self):
        self.assertTrue(self.preflight(dataset_id=self.synthetic_id, analysis_date="2024-09-30")["ready"])

    def test_low_quality_sentiment_blocks_unless_overridden(self):
        bad = {"sentiment_quality": {"items": 10, "passes_quality_gate": False, "finbert_complete": True}}
        self.assertBlocked(self.preflight(quality=bad), "sentiment_quality")
        self.assertTrue(self.preflight(quality=bad, allow_low_quality_sentiment=True)["ready"])

    def test_missing_sentiment_domain_is_not_a_quality_failure(self):
        empty = {"sentiment_quality": {"items": 0, "passes_quality_gate": False, "finbert_complete": False}}
        self.assertTrue(self.preflight(quality=empty)["ready"])

    def test_point_only_fundamentals_block_unless_overridden(self):
        bad = {"fundamental_quality": {"items": 4, "passes_quality_gate": False}}
        self.assertBlocked(self.preflight(quality=bad), "fundamental_quality")
        self.assertTrue(self.preflight(quality=bad, allow_point_fundamental=True)["ready"])

    # The model checks only apply to the real provider, so these runs build
    # the app without an injected model and fake the Ollama inventory instead.
    def test_uninstalled_local_model_blocks(self):
        result = self.preflight(model_call=None, tags=ollama_tags(("gemma3:4b", "4.3B")))
        self.assertBlocked(result, "model_not_installed")

    def test_small_local_model_needs_smoke_test_override(self):
        tags = ollama_tags(("gemma3:4b", "4.3B"))
        self.assertBlocked(self.preflight(model_call=None, tags=tags, model="ollama/gemma3:4b"), "model_too_small")
        self.assertTrue(self.preflight(model_call=None, tags=tags, model="ollama/gemma3:4b", allow_small_model=True)["ready"])

    def test_qwen3_8b_is_the_formal_small_model_exception(self):
        result = self.preflight(model_call=None, tags=ollama_tags(("qwen3:8b", "8.2B")), model="ollama/qwen3:8b")
        self.assertTrue(result["ready"], result)

    def test_cloud_model_skips_the_ollama_probe(self):
        result = self.preflight(model_call=None, tags=ollama_tags(), model="openrouter/openai/gpt-4.1-mini")
        self.assertTrue(result["ready"], result)
        self.assertEqual(self.probe_calls, 0)

    def test_preflight_reuses_a_recent_ollama_probe(self):
        with patch("research_service.web.ollama.get_json", return_value=ollama_tags(("qwen3:14b", "14.8B"))) as probe, \
             patch("research_service.web.jobs.coverage", return_value={"sentiment_quality": GOOD_SENTIMENT,
                                                                   "fundamental_quality": GOOD_FUNDAMENTAL}):
            with TestClient(create_app(self.store, start_worker=False)) as client:
                body = {"dataset_id": self.historical_id, "analysis_date": "2024-12-31", "model": "ollama/qwen3:14b"}
                for _ in range(3):
                    self.assertTrue(client.post("/api/jobs/preflight", json=body).json()["ready"])
                # Creating the job still probes Ollama live rather than trusting the cache.
                self.assertEqual(client.post("/api/jobs", json=body).status_code, 200)
        self.assertEqual(probe.call_count, 2)


if __name__ == "__main__":
    unittest.main()


class CloudModelStatusTests(unittest.TestCase):
    """The status chip used to read 'MODEL OFFLINE' for keyed cloud models
    whenever no Ollama was reachable (e.g. in a Codespace)."""

    def probe(self, env):
        from types import SimpleNamespace
        from urllib.error import URLError
        from research_service.web.ollama import probe_models
        with patch.dict("os.environ", env, clear=False), \
             patch("research_service.web.ollama.get_json", side_effect=URLError("no ollama")):
            return probe_models(SimpleNamespace(demo_mode=False))

    def test_keyed_cloud_model_is_ready_without_ollama(self):
        result = self.probe({"RESEARCH_MODEL": "gemini/gemini-3.1-pro-preview", "GEMINI_API_KEY": "k",
                             "GPUTW_OLLAMA_BASE_URL": ""})
        self.assertTrue(result["ready"])
        self.assertEqual(result["models"], ["gemini/gemini-3.1-pro-preview"])
        self.assertEqual(result["cloud"]["key_name"], "GEMINI_API_KEY")

    def test_cloud_model_without_key_is_not_ready(self):
        result = self.probe({"RESEARCH_MODEL": "gemini/gemini-3.1-pro-preview", "GEMINI_API_KEY": "",
                             "GPUTW_OLLAMA_BASE_URL": ""})
        self.assertFalse(result["ready"])
        self.assertFalse(result["cloud"]["ready"])

    def test_ollama_default_is_unchanged(self):
        result = self.probe({"RESEARCH_MODEL": "ollama/qwen3:14b", "GPUTW_OLLAMA_BASE_URL": ""})
        self.assertFalse(result["ready"])
        self.assertNotIn("cloud", result)
