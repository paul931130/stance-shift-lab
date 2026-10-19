from copy import deepcopy
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from research_service.data import digest
from research_service.protocol import QUARTER_DATES, STUDY_TICKERS
from research_service.rq3_inference import ARMS, BASELINES, analyze_registered, build_panel, infer_panel
from scripts.analyze_rq3_snapshot import main


class RQ3InferenceTests(unittest.TestCase):
    def fixture(self):
        rng = np.random.default_rng(123)
        jobs = []
        for index in range(20):
            cases = [{"group": arm, "horizon": 60, "cost_model": "corwin_schultz", "decision_layer": "candidate",
                      "status": "complete", "correct": bool(rng.random() < .5)} for arm in ARMS]
            daily = [{"group": arm, "horizon": 60, "cost_model": "corwin_schultz", "decision_layer": "candidate",
                      "date": f"day-{day:03d}", "return": float(rng.normal(.001, .01))}
                     for day in range(80) for arm in ARMS]
            jobs.append({"id": str(index), "config": {"ticker": "TEST", "analysis_date": f"date-{index:02d}"},
                         "state": {"cases": cases, "daily": daily}})
        return jobs

    def test_common_panel_accuracy_matches_hand_calculation_and_six_family(self):
        jobs = self.fixture()
        panel = build_panel(jobs)
        result = infer_panel(panel, date_block_length=1, daily_block_length=10, replicates=199)
        self.assertEqual(result["n_cases"], 20)
        self.assertEqual(len(result["family"]), 6)
        for arm in BASELINES:
            expected = sum(int(j["state"]["cases"][1]["correct"])
                           - int(j["state"]["cases"][ARMS.index(arm)]["correct"]) for j in jobs) / len(jobs)
            self.assertAlmostEqual(result["contrasts"][arm]["accuracy"]["estimate"], expected)
            self.assertGreaterEqual(result["contrasts"][arm]["accuracy"]["holm_pvalue"],
                                    result["contrasts"][arm]["accuracy"]["pvalue"])
        expected_return = sum(j["state"]["daily"][0]["return"] for j in jobs) / len(jobs)
        self.assertAlmostEqual(panel["returns"][0, 0], expected_return)

    def test_missing_or_duplicate_arm_rejected_for_all_comparisons(self):
        for mode in ("missing", "duplicate", "nonboolean"):
            with self.subTest(mode=mode):
                jobs = self.fixture()
                rows = jobs[0]["state"]["cases"]
                if mode == "missing":
                    rows.pop()
                elif mode == "duplicate":
                    rows.append(deepcopy(rows[0]))
                else:
                    rows[0]["correct"] = 1
                with self.assertRaises(ValueError):
                    build_panel(jobs)

    def test_duplicate_daily_or_misalignment_or_nonfinite_rejected(self):
        for mode in ("duplicate", "missing", "nan"):
            with self.subTest(mode=mode):
                jobs = self.fixture()
                rows = jobs[0]["state"]["daily"]
                if mode == "duplicate":
                    rows.append(deepcopy(rows[0]))
                elif mode == "missing":
                    rows.pop()
                else:
                    rows[0]["return"] = float("nan")
                with self.assertRaises(ValueError):
                    build_panel(jobs)

    def test_duplicate_case_rejected(self):
        jobs = self.fixture()
        jobs.append(deepcopy(jobs[0]))
        with self.assertRaisesRegex(ValueError, "Duplicate stock/date"):
            build_panel(jobs)

    def registered_fixture(self):
        template = self.fixture()[0]
        jobs, datasets = [], {}
        settings = {"rq3_version": "rq3-1015.1", "rule": "fixed", "include_controls": True}
        for index, (day, ticker) in enumerate((d, t) for d in QUARTER_DATES for t in STUDY_TICKERS):
            job = deepcopy(template)
            content = {"ticker": ticker, "requested_analysis_date": day}
            dataset_id = digest(content)
            datasets[dataset_id] = content
            job.update(id=str(index), status="complete", created_at="2026-10-15T01:00:00+00:00")
            job["config"].update(ticker=ticker, analysis_date=day, dataset_id=dataset_id, protocol_hash="fixture-hash",
                                 protocol={"dataset_kind": "historical"}, formal_readiness={"eligible": True},
                                 model_identity={"id": "ollama/test", "digest": "fixture-weight"}, domain_debate=settings)
            state = job["state"]
            state.update(finished=True, report={"dataset_kind": "historical"}, memory={arm: [] for arm in ARMS})
            state["report_hash"] = digest(state["report"])
            state["rq3_diagnostics"] = {"settings": settings, "resources": {arm: {} for arm in ARMS},
                                         "rule_matched_pairs": [{"rule": "fixed", "generalist": arm, "domain": "C_domain"}
                                                                for arm in BASELINES],
                                         "agreement": {}, "compute_matching": {"enforced": False}}
            jobs.append(job)
        return jobs, datasets

    def test_registered_snapshot_cli_mock_fixture_is_readonly_and_complete(self):
        # Synthetic fixture proves the adapter/CLI plumbing, not real-model qualification.
        jobs, datasets = self.registered_fixture()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "fixture.sqlite3"
            output = Path(directory) / "analysis.json"
            with closing(sqlite3.connect(source)) as db:
                db.executescript("CREATE TABLE datasets(id TEXT,content TEXT);"
                                 "CREATE TABLE jobs(id TEXT,status TEXT,created_at TEXT,config TEXT,state TEXT);"
                                 "CREATE TABLE preregistrations(protocol_hash TEXT,dataset_ids TEXT,frozen_at TEXT);"
                                 "CREATE TABLE preregistration_meta(protocol_hash TEXT,model_digest TEXT);")
                db.executemany("INSERT INTO datasets VALUES(?,?)", [(key, json.dumps(value)) for key, value in datasets.items()])
                db.executemany("INSERT INTO jobs VALUES(?,?,?,?,?)", [(j["id"], j["status"], j["created_at"],
                                                                      json.dumps(j["config"]), json.dumps(j["state"])) for j in jobs])
                db.execute("INSERT INTO preregistrations VALUES(?,?,?)",
                           ("fixture-hash", json.dumps(list(datasets)), "2026-10-15T00:00:00+00:00"))
                db.execute("INSERT INTO preregistration_meta VALUES(?,?)", ("fixture-hash", "fixture-weight"))
                db.commit()
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            with patch.object(sys, "argv", ["analyze_rq3_snapshot", "--source-db", str(source), "--output", str(output),
                                            "--protocol-hash", "fixture-hash", "--date-block-length", "1",
                                            "--daily-block-length", "10", "--replicates", "199"]):
                main()
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["n_cases"], 180)
            self.assertEqual(result["n_analysis_dates"], 20)
            self.assertEqual(result["source_database_sha256"], before)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
            self.assertEqual(result["resources"]["cases"], 180)

    def test_registered_grid_and_cross_arm_memory_fail_closed(self):
        jobs, datasets = self.registered_fixture()
        kwargs = {"eligible_dataset_ids": list(datasets), "frozen_at": "2026-10-15T00:00:00+00:00",
                  "date_block_length": 1, "daily_block_length": 10, "replicates": 199}
        with self.assertRaisesRegex(ValueError, "180-case"):
            analyze_registered(jobs[:-1], **kwargs)
        jobs[0]["state"]["memory"]["C"] = [{"group": "C_domain"}]
        with self.assertRaisesRegex(ValueError, "memory"):
            analyze_registered(jobs, **kwargs)


if __name__ == "__main__":
    unittest.main()
