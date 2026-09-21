import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from research_service.data import validate_dataset
from research_service.demo import DEMO_MODEL, demo_dataset
from research_service.app import create_app
from research_service.storage import Store


class DemoModeTests(unittest.TestCase):
    def test_demo_dataset_is_valid_and_has_all_domains(self):
        data = validate_dataset(demo_dataset())
        self.assertEqual(data["kind"], "synthetic")
        self.assertGreaterEqual(len(data["prices"]), 61)
        self.assertEqual({item["domain"] for item in data["evidence"]},
                         {"technical", "fundamental", "sentiment", "macro"})

    def test_demo_app_exposes_synthetic_provider_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            with patch.dict(os.environ, {"RESEARCH_DEMO_MODE": "true"}, clear=False):
                with TestClient(create_app(store, start_worker=False)) as client:
                    self.assertTrue(client.get("/health").json()["demo_mode"])
                    config = client.get("/api/config").json()
                    self.assertTrue(config["demo_mode"])
                    self.assertEqual(config["model"], DEMO_MODEL)
                    self.assertEqual(client.get("/api/models").json()["models"], [DEMO_MODEL])
                    datasets = client.get("/api/datasets").json()
                    self.assertEqual(len(datasets), 1)
                    job = client.post("/api/jobs", json={
                        "dataset_id": datasets[0]["id"], "analysis_date": "2024-12-31",
                        "model": "ollama/qwen3:14b",
                    })
                    self.assertEqual(job.status_code, 200)
                    self.assertEqual(job.json()["config"]["protocol"]["model"], DEMO_MODEL)


if __name__ == "__main__":
    unittest.main()
