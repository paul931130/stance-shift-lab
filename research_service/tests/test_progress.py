import unittest
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


if __name__ == "__main__":
    unittest.main()
