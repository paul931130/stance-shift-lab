"""Offline launch preparation fails closed on malformed plans and source frames."""
from copy import deepcopy
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from research_service.data import digest
from research_service.launch_package import DEFAULT_PLAN, file_hash, prepare_launch, validate_plan, validate_url
from research_service.protocol import QUARTER_DATES, STUDY_TICKERS


HASH = "a" * 64


class LaunchPackageTests(unittest.TestCase):
    def test_rejects_seed_and_family_changes(self):
        for change in ({"formal_seeds": [905, 905, 907]}, {"formal_seeds": [905, 906]},
                       {"report_bank_seed": 905}):
            plan = deepcopy(DEFAULT_PLAN)
            plan.update(change)
            with self.assertRaises(ValueError):
                validate_plan(plan)
        plan = deepcopy(DEFAULT_PLAN)
        plan["analysis"]["rq3_family"].pop()
        with self.assertRaises(ValueError):
            validate_plan(plan)

    def test_rejects_url_secrets(self):
        for url in ("https://user:secret@host", "https://host/?token=abc", "https://host/#key",
                    "file:///tmp/model", "http://host/path?q=1"):
            with self.assertRaises(ValueError):
                validate_url(url)
        plan = deepcopy(DEFAULT_PLAN)
        plan["api_key"] = "secret"
        with self.assertRaises(ValueError):
            validate_plan(plan)

    def fixture(self, root, *, broken=None):
        source = root / "backup.sqlite3"
        plan = root / "plan.json"
        plan.write_text(json.dumps(DEFAULT_PLAN), encoding="utf-8")
        requests, ids = [], []
        with closing(sqlite3.connect(source)) as db:
            db.execute("CREATE TABLE preregistrations(protocol_hash TEXT, dataset_ids TEXT)")
            db.execute("CREATE TABLE preregistration_cases(protocol_hash TEXT, cases TEXT)")
            db.execute("CREATE TABLE datasets(id TEXT, ticker TEXT, content TEXT)")
            for day in QUARTER_DATES:
                for ticker in STUDY_TICKERS:
                    data = {"kind": "historical", "ticker": ticker, "requested_analysis_date": day}
                    dataset_id = digest(data)
                    if broken == "digest" and not ids:
                        dataset_id = "0" * 64
                    ids.append(dataset_id)
                    requests.append({"dataset_id": dataset_id, "ticker": ticker, "analysis_date": day})
                    db.execute("INSERT INTO datasets VALUES(?,?,?)", (dataset_id, ticker, json.dumps(data)))
            if broken == "grid":
                requests[-1]["analysis_date"] = requests[0]["analysis_date"]
            db.execute("INSERT INTO preregistrations VALUES(?,?)", (HASH, json.dumps(ids)))
            db.execute("INSERT INTO preregistration_cases VALUES(?,?)", (HASH, json.dumps(requests)))
            db.commit()
        return source, plan

    def prepare(self, source, plan, output):
        return prepare_launch(source, HASH, plan, output, "http://127.0.0.1:11434",
                              "https://model-b.example", runner_path=Path(__file__))

    @patch("research_service.launch_package.coverage", return_value={"formal_experiment_ready": True})
    def test_complete_frame_is_offline_and_source_unchanged(self, _coverage):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, plan = self.fixture(root)
            before = file_hash(source)
            with patch("research_service.storage.Store", side_effect=AssertionError("Store called")), \
                    patch("urllib.request.urlopen", side_effect=AssertionError("network called")):
                manifest = self.prepare(source, plan, root / "output")
            self.assertEqual(file_hash(source), before)
            self.assertFalse(manifest["formal_launch_ready"])
            self.assertEqual(manifest["source_database_sha256_before"], before)
            self.assertEqual(manifest["source_database_sha256_after"], before)
            files = root / "output"
            self.assertEqual(len(json.loads((files / "frame.json").read_text())["cases"]), 180)
            self.assertEqual(len(json.loads((files / "report-bank.cases.json").read_text())["cases"]), 180)
            self.assertEqual(len(json.loads((files / "rq2-pilot.cases.json").read_text())["cases"]), 3)
            self.assertEqual(len(json.loads((files / "rq3-formal.cases.json").read_text())["cases"]), 180)
            full_plan = json.loads((files / "experiment-plan.json").read_text())
            self.assertEqual(full_plan["formal_seeds"], [905, 906, 907])
            self.assertEqual(full_plan, DEFAULT_PLAN)
            first = json.loads((files / "rq3-formal.cases.json").read_text())["cases"]
            self.assertNotIn("model_endpoints", first[0])
            runtime = json.loads((files / "rq3-runtime.json").read_text())
            self.assertEqual(runtime["model_a_base"], "http://127.0.0.1:11434")
            self.assertEqual(runtime["required_environment"],
                             {"OLLAMA_BASE_URL": "http://127.0.0.1:11434",
                              "GPUTW_OLLAMA_BASE_URL": "http://127.0.0.1:11434"})
            self.assertEqual(manifest["rq3_runtime_sha256"], file_hash(files / "rq3-runtime.json"))
            self.assertEqual({case["inference_seed"] for case in first}, {905})
            self.assertEqual(manifest["seed_scope"]["rq2_formal_seeds"], [905, 906, 907])
            code_root = Path(__file__).resolve().parents[2]
            for script in ("scripts/analyze_rq2_snapshot.py", "scripts/analyze_rq3_snapshot.py"):
                self.assertEqual(manifest["pipeline_sha256"][script], file_hash(code_root / script))
            self.assertFalse(list(files.glob("rq3-formal.seed-*.cases.json")))
            self.assertEqual(set(json.loads((files / "rq2-pilot.cases.json").read_text())["cases"][0]
                                 ["debate_assignments"]), {"AA", "AB", "BA", "BB"})
            self.assertNotIn("neutral_report_job_id", (files / "rq2-pilot.cases.json").read_text())

    @patch("research_service.launch_package.coverage", return_value={"formal_experiment_ready": True})
    def test_rq3_seed_is_independent_of_rq2_seeds(self, _coverage):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, plan_path = self.fixture(root)
            plan = deepcopy(DEFAULT_PLAN)
            plan["rq3_inference_seed"] = 906
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            self.prepare(source, plan_path, root / "output")
            output = root / "output"
            rq2 = json.loads((output / "rq2-pilot.cases.json").read_text())["cases"]
            rq3_pilot = json.loads((output / "rq3-pilot.cases.json").read_text())["cases"]
            rq3_formal = json.loads((output / "rq3-formal.cases.json").read_text())["cases"]
            self.assertEqual({case["inference_seed"] for case in rq2}, {905})
            self.assertEqual({case["inference_seed"] for case in rq3_pilot}, {906})
            self.assertEqual(len(rq3_formal), 180)
            self.assertEqual({case["inference_seed"] for case in rq3_formal}, {906})
            self.assertEqual(json.loads((output / "experiment-plan.json").read_text())
                             ["rq3_inference_seed"], 906)

    @patch("research_service.launch_package.coverage", return_value={"formal_experiment_ready": True})
    def test_bad_digest_or_grid_is_rejected(self, _coverage):
        for broken in ("digest", "grid"):
            with self.subTest(broken=broken), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source, plan = self.fixture(root, broken=broken)
                with self.assertRaises(ValueError):
                    self.prepare(source, plan, root / "output")
                self.assertFalse((root / "output").exists())

    @patch("research_service.launch_package.coverage", return_value={"formal_experiment_ready": True})
    def test_existing_output_is_rejected(self, _coverage):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, plan = self.fixture(root)
            output = root / "output"
            output.mkdir()
            with self.assertRaises(ValueError):
                self.prepare(source, plan, output)


if __name__ == "__main__":
    unittest.main()
