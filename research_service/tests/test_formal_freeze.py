"""v3-1002.3 freeze rules: weight digest, source fingerprint, identity errors, splits, usage."""
from dataclasses import asdict
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from research_service.app import create_app
from research_service.data import validate_dataset
from research_service.engine import Engine, compute_usage
from research_service.model_identity import ModelIdentityUnavailable, resolve_ollama_identity
from research_service.protocol import PROTOCOL_SOURCE_MODULES, StudyProtocol, protocol_matches_fingerprint
from research_service.splits import temporal_split_summary
from research_service.storage import Store
from research_service.tests.test_preflight import GOOD_FUNDAMENTAL, GOOD_SENTIMENT
from research_service.tests.test_workflow import fake_model, fixture

MODEL = "ollama/qwen3:32b"


def inventory(digest):
    return {"ready": True, "models": [MODEL],
            "details": [{"id": MODEL, "digest": digest, "parameter_size": "32.8B"}]}


class RegistrationDigestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        historical = validate_dataset(fixture())
        historical.update(kind="historical", collection_rules={"news_item_limit": "uncapped"},
                          requested_analysis_date="2024-12-31")
        self.dataset_id = self.store.add_dataset(historical)
        self.case = {"dataset_id": self.dataset_id, "analysis_date": "2024-12-31", "model": MODEL}

    def client(self, digest):
        coverage_result = {"sentiment_quality": GOOD_SENTIMENT, "fundamental_quality": GOOD_FUNDAMENTAL}
        patches = [patch("research_service.web.jobs.coverage", return_value=coverage_result),
                   patch("research_service.web.jobs.probe_models", return_value=inventory(digest))]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        return TestClient(create_app(self.store, None, start_worker=False))

    def test_registration_freezes_the_digest_and_enqueue_refuses_other_weights(self):
        with self.client("weights-A") as client:
            registered = client.post("/api/studies/preregister", json={"cases": [self.case]})
            self.assertEqual(registered.status_code, 200, registered.text)
            protocol_hash = registered.json()["protocol_hash"]
            self.assertEqual(self.store.registration_meta(protocol_hash)["model_digest"], "weights-A")
        with self.client("weights-B") as client:
            refused = client.post(f"/api/studies/{protocol_hash}/enqueue")
        self.assertEqual(refused.status_code, 422)
        self.assertIn("digest", refused.text)
        self.assertEqual(self.store.study_rows(protocol_hash), [])

    def test_new_version_registration_must_be_anonymized(self):
        with self.client("weights-A") as client:
            refused = client.post("/api/studies/preregister",
                                  json={"cases": [{**self.case, "anonymize_ticker": False}]})
        self.assertEqual(refused.status_code, 422)
        self.assertIn("匿名", refused.text)

    def test_default_request_is_anonymized(self):
        self.assertTrue(StudyProtocol().anonymize_ticker)
        self.assertFalse(StudyProtocol(version="v3-1002.1").anonymize_ticker)


class SourceFingerprintTests(unittest.TestCase):
    def test_a_changed_source_digest_blocks_resuming_a_new_version_job(self):
        protocol = StudyProtocol(model=MODEL)
        saved, stored_hash = asdict(protocol), protocol.fingerprint
        self.assertTrue(protocol_matches_fingerprint(saved, stored_hash))
        with patch("research_service.protocol.prompt_source_digest", return_value="edited"):
            self.assertFalse(protocol_matches_fingerprint(saved, stored_hash))
            # Older versions never hashed source code, so they are not affected.
            old = StudyProtocol(version="v3-1002.1", model=MODEL)
            self.assertTrue(protocol_matches_fingerprint(asdict(old), old.fingerprint))

    def test_engine_refuses_a_job_whose_source_changed(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = Store(tmp.name)
        protocol = StudyProtocol(dataset_kind="synthetic", bootstrap_replicates=199)
        job = store.create({"ticker": "NVDA", "analysis_date": "2024-12-31",
                            "dataset_id": store.add_dataset(fixture()),
                            "protocol": asdict(protocol), "protocol_hash": protocol.fingerprint})
        with patch("research_service.protocol.prompt_source_digest", return_value="edited"):
            with self.assertRaises(ValueError):
                Engine(store, fake_model).advance(job)

    def test_only_experiment_modules_are_hashed(self):
        self.assertNotIn("reporting", PROTOCOL_SOURCE_MODULES)
        self.assertIn("models", PROTOCOL_SOURCE_MODULES)


class IdentityAvailabilityTests(unittest.TestCase):
    def test_an_empty_or_digestless_list_is_unavailable_not_a_mismatch(self):
        for tags in ({"models": []}, {"models": [{"name": "qwen3:32b"}]}):
            with self.subTest(tags=tags), patch("research_service.web.ollama.get_json", return_value=tags):
                with self.assertRaises(ModelIdentityUnavailable):
                    resolve_ollama_identity(MODEL)


class MonthlySplitTests(unittest.TestCase):
    def test_monthly_targets_are_twelve_dates_per_year(self):
        summary = temporal_split_summary([], design="monthly")
        self.assertEqual(sum(item["target_cases"] for item in summary["splits"].values()), 540)
        self.assertTrue(all(item["missing_cases"] >= 0 for item in summary["splits"].values()))
        quarterly = temporal_split_summary([], design="quarterly")
        self.assertEqual(sum(item["target_cases"] for item in quarterly["splits"].values()), 180)


class UsageAccountingTests(unittest.TestCase):
    def test_validation_retries_and_provider_retries_are_counted(self):
        attempt = {"status": "complete", "usage": {"prompt_tokens": 10, "completion_tokens": 5,
                                                   "client_elapsed_seconds": 1.0}}
        failed = {"status": "failed", "usage": {"prompt_tokens": 10, "completion_tokens": 0,
                                                "client_elapsed_seconds": 2.0}}
        record = {"group": "A", "audit": {"attempts": [failed, attempt],
                                          "validation_retries": [{"attempts": [attempt]}]}}
        usage = compute_usage([record])["A"]
        self.assertEqual(usage["completed_calls"], 1)
        self.assertEqual(usage["provider_attempts"], 3)
        self.assertEqual(usage["failed_provider_attempts"], 1)
        self.assertEqual(usage["prompt_tokens"], 30)


if __name__ == "__main__":
    unittest.main()
