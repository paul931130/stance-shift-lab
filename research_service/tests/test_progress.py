import contextlib
import io
import os
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

from research_service.progress import study_progress

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def row(index, status, minutes_ago=0, error="", dataset=None):
    return {"id": f"job-{index}", "status": status, "error": error, "ticker": "NVDA",
            "analysis_date": f"2024-0{index % 9 + 1}-30", "dataset_id": dataset or f"d{index}",
            "updated_at": (NOW - timedelta(minutes=minutes_ago)).isoformat(), "created_at": NOW.isoformat(), "steps": 0}


class StudyProgressTests(unittest.TestCase):
    def test_eta_uses_recent_throughput(self):
        registration = {"protocol_hash": "h", "dataset_ids": [f"d{i}" for i in range(10)], "frozen_at": "t"}
        rows = [row(i, "complete", minutes_ago=40 - 10 * i) for i in range(4)]  # 4 done in the last 40 minutes
        rows += [row(i, "queued") for i in range(4, 10)]
        result = study_progress(registration, rows, now=NOW)
        self.assertEqual((result["total"], result["counts"]["complete"], result["remaining"]), (10, 4, 6))
        self.assertEqual(result["rate_cases_per_hour"], 6.0)
        self.assertEqual(result["eta_hours"], 1.0)

    def test_too_few_recent_completions_give_no_eta(self):
        registration = {"protocol_hash": "h", "dataset_ids": ["d0", "d1", "d2"], "frozen_at": "t"}
        result = study_progress(registration, [row(0, "complete", 5), row(1, "queued"), row(2, "queued")], now=NOW)
        self.assertIsNone(result["eta_hours"])
        self.assertTrue(result["active"])

    def test_errors_not_created_and_outside_sample_are_reported(self):
        registration = {"protocol_hash": "h", "dataset_ids": ["d0", "d1", "d2"], "frozen_at": "t"}
        rows = [row(0, "paused", error="ProviderError: timeout"), row(9, "complete", dataset="elsewhere")]
        result = study_progress(registration, rows, now=NOW)
        self.assertEqual(result["not_created"], 2)
        self.assertEqual([e["id"] for e in result["errors"]], ["job-0"])
        self.assertEqual(result["outside_sample_jobs"], 1)
        self.assertFalse(result["active"])


class DuplicateCaseTests(unittest.TestCase):
    def test_a_case_with_two_jobs_counts_once(self):
        registration = {"protocol_hash": "h", "dataset_ids": ["d0"], "frozen_at": "t"}
        rows = [row(0, "complete", 5, dataset="d0"), row(1, "paused", error="x", dataset="d0")]
        result = study_progress(registration, rows, now=NOW)
        self.assertEqual((result["counts"]["complete"], result["done_fraction"], result["duplicate_jobs"]), (1, 1.0, 1))
        self.assertEqual(result["errors"], [])


class StudiesCommandTests(unittest.TestCase):
    def test_studies_command_lists_preregistered_samples(self):
        from research_service.cli import main
        from research_service.storage import Store

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"RESEARCH_DATA_DIR": directory}):
            Store(directory).freeze("abcdef1234", ["d1", "d2"])
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(["studies"]), 0)
        self.assertIn("abcdef12", out.getvalue())
        self.assertIn("0/2 完成", out.getvalue())


if __name__ == "__main__":
    unittest.main()
