"""Fail-closed tests for offline report-bank launch binding."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from dataclasses import asdict

from research_service.bind_launch import bind_launch
from research_service.data import digest
from research_service.launch_package import DEFAULT_PLAN, file_hash
from research_service.protocol import RouterProtocol, protocol_from
from research_service.run_manifest import source_fingerprint


class BindLaunchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ticker_patch = patch("research_service.bind_launch.STUDY_TICKERS", ("NVDA",))
        self.date_patch = patch("research_service.bind_launch.QUARTER_DATES", ("2024-03-31", "2024-06-30"))
        self.ticker_patch.start()
        self.date_patch.start()
        self.addCleanup(self.ticker_patch.stop)
        self.addCleanup(self.date_patch.stop)
        self.pairs = [("NVDA", day) for day in ("2024-03-31", "2024-06-30")]
        self.launch = self.root / "launch"
        self.launch.mkdir()
        self.bank = self.root / "bank.sqlite3"
        self.output = self.root / "bound"
        self._write_launch()
        self._write_bank()

    def _write_launch(self, *, stale_artifact=False):
        protocol = RouterProtocol(model=DEFAULT_PLAN["model_a"],
                                  debate_model_a=DEFAULT_PLAN["model_a"], debate_model_b=DEFAULT_PLAN["model_b"],
                                  inference_seed=DEFAULT_PLAN["report_bank_seed"], dataset_kind="historical",
                                  model_context_length=DEFAULT_PLAN["model_context_length"],
                                  ollama_parallel=DEFAULT_PLAN["ollama_parallel"],
                                  debate_assignments=("AA", "AB", "BA", "BB"),
                                  model_endpoints={DEFAULT_PLAN["model_a"]: {"api_base": "http://a.example"},
                                                   DEFAULT_PLAN["model_b"]: {"api_base": "http://b.example"}})
        frame_cases, templates = [], []
        for index, (ticker, day) in enumerate(self.pairs):
            dataset_id = f"dataset-{index}"
            frame_cases.append({"ticker": ticker, "analysis_date": day, "dataset_id": dataset_id})
            templates.append({"dataset_id": dataset_id, "analysis_date": day,
                              "model": protocol.model, "inference_seed": protocol.inference_seed,
                              "model_context_length": protocol.model_context_length,
                              "ollama_parallel": protocol.ollama_parallel,
                              "debate_model_a": protocol.debate_model_a,
                              "debate_model_b": protocol.debate_model_b,
                              "debate_assignments": list(protocol.debate_assignments),
                              "model_endpoints": protocol.model_endpoints})
        artifacts = {
            "frame.json": {"schema": "stance-shift-launch-frame/v1", "cases": frame_cases},
            "experiment-plan.json": DEFAULT_PLAN,
            "report-bank.cases.json": {"cases": templates},
        }
        for name, payload in artifacts.items():
            (self.launch / name).write_text(json.dumps(payload), encoding="utf-8")
        manifest = {"schema": "stance-shift-launch-manifest/v1",
                    "source_fingerprint": source_fingerprint(Path(__file__).resolve().parents[2]),
                    "plan_sha256": digest(DEFAULT_PLAN),
                    "pipeline_sha256": {name: file_hash(Path(__file__).resolve().parents[2] / name) for name in
                                        ("scripts/run_design_pilot.py", "scripts/analyze_rq2_snapshot.py",
                                         "scripts/analyze_rq3_snapshot.py", "scripts/prepare_experiment_launch.py")},
                    "artifacts_sha256": {name: file_hash(self.launch / name) for name in artifacts}}
        (self.launch / "launch-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        if stale_artifact:
            (self.launch / "frame.json").write_text("{}", encoding="utf-8")

    def _write_bank(self, *, decision=False, missing=False, duplicate=False):
        protocol = RouterProtocol(model=DEFAULT_PLAN["model_a"],
                                  debate_model_a=DEFAULT_PLAN["model_a"], debate_model_b=DEFAULT_PLAN["model_b"],
                                  inference_seed=DEFAULT_PLAN["report_bank_seed"], dataset_kind="historical",
                                  model_context_length=DEFAULT_PLAN["model_context_length"],
                                  ollama_parallel=DEFAULT_PLAN["ollama_parallel"],
                                  debate_assignments=("AA", "AB", "BA", "BB"),
                                  model_endpoints={DEFAULT_PLAN["model_a"]: {"api_base": "http://a.example"},
                                                   DEFAULT_PLAN["model_b"]: {"api_base": "http://b.example"}})
        report = {"summary": "locked"}
        state = {"finished": False, "records": [{"decision": True}] if decision else [],
                 "trace": [{"node": "neutral_report_locked"}], "report": report,
                 "report_hash": digest(report), "research": {key: {"ok": True} for key in
                                                               ("technical", "fundamental", "sentiment", "macro")}}
        config_template = {"execution_purpose": "report_bank", "protocol": asdict(protocol),
                           "protocol_hash": protocol.fingerprint, "model_identity": {"id": protocol.model,
                                                                                       "digest": "a-digest"},
                           "routed_model_identities": {
                               DEFAULT_PLAN["model_a"]: {"id": DEFAULT_PLAN["model_a"], "digest": "a-digest"},
                               DEFAULT_PLAN["model_b"]: {"id": DEFAULT_PLAN["model_b"], "digest": "b-digest"}}}
        with closing(sqlite3.connect(self.bank)) as db:
            db.execute("CREATE TABLE jobs(id TEXT, status TEXT, wants_run INTEGER, config TEXT, state TEXT, error TEXT, created_at TEXT, updated_at TEXT)")
            for index, (ticker, day) in enumerate(self.pairs):
                if missing and index == 1:
                    continue
                config = {**config_template, "ticker": ticker, "analysis_date": day,
                          "dataset_id": f"dataset-{index}"}
                job_id = f"job-{index}"
                db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)",
                           (job_id, "paused", 0, json.dumps(config), json.dumps(state), "", "", ""))
                if duplicate and index == 0:
                    db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)",
                               ("duplicate", "paused", 0, json.dumps(config), json.dumps(state), "", "", ""))
            db.commit()

    def test_happy_path_writes_three_seed_batches_and_preserves_bank(self):
        before = file_hash(self.bank)
        with patch("research_service.storage.Store.__init__", side_effect=AssertionError("Store initialized")):
            manifest = bind_launch(self.launch, self.bank, self.output)
        self.assertEqual(file_hash(self.bank), before)
        self.assertEqual(manifest["bank_sha256_before"], manifest["bank_sha256_after"])
        self.assertFalse(manifest["formal_launch_ready"])
        self.assertEqual(manifest["blocking_requirements"],
                         ["same_store_with_report_bank_and_eligibility", "new_registration"])
        for seed in DEFAULT_PLAN["formal_seeds"]:
            artifact = self.output / f"rq2-formal.seed-{seed}.cases.json"
            cases = json.loads(artifact.read_text(encoding="utf-8"))["cases"]
            self.assertEqual(len(cases), len(self.pairs))
            self.assertEqual({case["inference_seed"] for case in cases}, {seed})
            self.assertTrue(all(case["neutral_report_job_id"] and case["neutral_report_hash"] for case in cases))

    def test_missing_and_duplicate_report_bank_sources_fail(self):
        for missing, duplicate in ((True, False), (False, True)):
            with self.subTest(missing=missing, duplicate=duplicate):
                self.bank.unlink()
                self._write_bank(missing=missing, duplicate=duplicate)
                with self.assertRaisesRegex(ValueError, "exactly one"):
                    bind_launch(self.launch, self.bank, self.output)
                self.assertFalse(self.output.exists())

    def test_source_with_decisions_is_rejected(self):
        self.bank.unlink()
        self._write_bank(decision=True)
        with self.assertRaisesRegex(ValueError, "尚無決策"):
            bind_launch(self.launch, self.bank, self.output)
        self.assertFalse(self.output.exists())

    def test_stale_artifact_is_rejected(self):
        self._write_launch(stale_artifact=True)
        with self.assertRaisesRegex(ValueError, "artifact hash mismatch"):
            bind_launch(self.launch, self.bank, self.output)
        self.assertFalse(self.output.exists())

    def test_changed_protocol_and_stale_pipeline_are_rejected(self):
        with self.subTest(reason="template protocol mismatch"):
            with closing(sqlite3.connect(self.bank)) as db:
                raw = db.execute("SELECT config FROM jobs WHERE id='job-0'").fetchone()[0]
                config = json.loads(raw)
                config["protocol"]["voting_samples"] = 5
                config["protocol_hash"] = protocol_from(config["protocol"]).fingerprint
                db.execute("UPDATE jobs SET config=? WHERE id='job-0'", (json.dumps(config),))
                db.commit()
            with self.assertRaisesRegex(ValueError, "does not match launch template"):
                bind_launch(self.launch, self.bank, self.output)
            self.assertFalse(self.output.exists())

        with self.subTest(reason="pipeline hash mismatch"):
            self.bank.unlink()
            self._write_bank()
            manifest_path = self.launch / "launch-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["pipeline_sha256"]["scripts/run_design_pilot.py"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "pipeline hash mismatch"):
                bind_launch(self.launch, self.bank, self.output)
            self.assertFalse(self.output.exists())

    def test_existing_output_is_rejected(self):
        self.output.mkdir()
        with self.assertRaisesRegex(ValueError, "new directory"):
            bind_launch(self.launch, self.bank, self.output)


if __name__ == "__main__":
    unittest.main()
