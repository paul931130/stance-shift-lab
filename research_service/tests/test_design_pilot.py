import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from scripts.run_design_pilot import file_hash, run
from research_service.data import validate_dataset
from research_service.demo import demo_model
from research_service.storage import Store
from research_service.tests.test_workflow import fixture


class DesignPilotTests(unittest.TestCase):
    def setup_run(self, root, *, mode="pilot", execute=False, rq3=False):
        store = Store(root / "source")
        dataset_id = store.add_dataset(validate_dataset(fixture()))
        source = root / "source.sqlite3"
        source.write_bytes(store.backup_bytes())
        case = {"dataset_id": dataset_id, "analysis_date": "2024-12-31", "model": "ollama/qwen3:32b",
                "inference_seed": 904 if mode == "report-bank" else 905}
        if rq3:
            case["domain_debate"] = {"rule": "fixed", "include_controls": True}
        else:
            case["debate_model_b"] = "ollama/gemma3:27b"
        cases = root / "cases.json"
        cases.write_text(json.dumps({"cases": [case]}), encoding="utf-8")
        return SimpleNamespace(source_db=source, cases=cases, output=root / "output", mode=mode, execute=execute)

    def test_offline_never_probes_or_creates_jobs_and_does_not_claim_qualification(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.setup_run(Path(directory))
            before = file_hash(args.source_db)
            with patch("research_service.model_router.probe_ollama_endpoint", side_effect=AssertionError("network")), \
                    patch("research_service.web.jobs.probe_models", side_effect=AssertionError("network")):
                manifest = run(args)
            self.assertEqual(manifest["status"], "offline_prepared")
            self.assertFalse(manifest["formal_launch_ready"])
            self.assertNotIn("model_identity", manifest["cases"][0]["config"])
            self.assertFalse(manifest["cases"][0]["config"]["formal_readiness"]["eligible"])
            self.assertEqual(file_hash(args.source_db), before)
            self.assertEqual(Store(args.output / "data").jobs(), [])

    def test_report_bank_stops_before_decisions_and_can_be_bound_to_next_seed(self):
        from research_service.protocol import protocol_from
        from research_service.shared_reports import bind_report
        with tempfile.TemporaryDirectory() as directory:
            args = self.setup_run(Path(directory), mode="report-bank", execute=True)
            manifest = run(args, model_call=demo_model)
            store = Store(args.output / "data")
            job = store.get(manifest["cases"][0]["job_id"])
            self.assertEqual(job["status"], "paused")
            self.assertFalse(job["owner"])
            self.assertEqual(job["state"]["records"], [])
            self.assertEqual(job["state"]["trace"][-1]["node"], "neutral_report_locked")
            self.assertEqual(store.preregistrations(), [])
            protocol = dict(job["config"]["protocol"], inference_seed=905)
            payload = SimpleNamespace(neutral_report_job_id=job["id"], neutral_report_hash=job["state"]["report_hash"],
                                      dataset_id=job["config"]["dataset_id"], analysis_date="2024-12-31")
            self.assertTrue(bind_report(store, payload, protocol_from(protocol)))

    def test_pilot_runs_both_designs_to_completion_as_qualification(self):
        for rq3 in (False, True):
            with self.subTest(rq3=rq3), tempfile.TemporaryDirectory() as directory:
                args = self.setup_run(Path(directory), execute=True, rq3=rq3)
                manifest = run(args, model_call=demo_model)
                self.assertEqual(manifest["status"], "complete")
                store = Store(args.output / "data")
                job = store.get(manifest["cases"][0]["job_id"])
                self.assertTrue(job["state"]["finished"])
                self.assertEqual(job["config"]["execution_purpose"], "qualification")
                self.assertEqual(store.preregistrations(), [])
                self.assertTrue(list(args.output.glob("*-export.zip")))
                if rq3:
                    self.assertTrue(job["state"]["rq3_diagnostics"])

    def test_limits_and_unsafe_modes_reject_before_creating_output(self):
        for mutation in ("missing_seed", "too_many", "incomplete_arms", "shared_source", "existing_output", "wal"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                args = self.setup_run(Path(directory), mode="report-bank" if mutation == "missing_seed" else "pilot")
                data = json.loads(args.cases.read_text())
                if mutation == "missing_seed":
                    data["cases"][0].pop("inference_seed")
                elif mutation == "too_many":
                    data["cases"] *= 6
                elif mutation == "incomplete_arms":
                    data["cases"][0]["debate_assignments"] = ["AA", "AB", "BA"]
                elif mutation == "shared_source":
                    data["cases"][0]["neutral_report_job_id"] = "source"
                elif mutation == "existing_output":
                    args.output.mkdir()
                elif mutation == "wal":
                    Path(str(args.source_db) + "-wal").touch()
                args.cases.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises((ValueError, FileExistsError)):
                    run(args)

    def test_model_failure_stops_batch_and_exports_failed_case(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.setup_run(Path(directory), execute=True)
            def fail(*_args, **_kwargs):
                raise RuntimeError("intentional test provider failure")
            with self.assertRaises(Exception):
                run(args, model_call=fail)
            manifest = json.loads((args.output / "manifest.json").read_text())
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(len(manifest["cases"]), 1)
            self.assertTrue(manifest["source_unchanged"])
            self.assertTrue(list(args.output.glob("*-export.zip")))
