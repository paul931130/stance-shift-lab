import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from research_service.storage import Store


class JobSummaryTests(unittest.TestCase):
    def test_legacy_database_gains_backfilled_steps_column(self):
        with tempfile.TemporaryDirectory() as directory:
            # A database written before the steps column existed.
            legacy = sqlite3.connect(Path(directory) / "research.sqlite3")
            legacy.execute("""CREATE TABLE jobs(id TEXT PRIMARY KEY, status TEXT, wants_run INTEGER,
                config TEXT, state TEXT, error TEXT, created_at TEXT, updated_at TEXT)""")
            legacy.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)", (
                "old", "paused", 0, json.dumps({"ticker": "NVDA"}),
                json.dumps({"records": [{}, {}, {}]}), "", "2026-01-01", "2026-01-01"))
            legacy.commit()
            legacy.close()

            store = Store(directory)
            [summary] = store.job_summaries()
        self.assertEqual(summary["steps"], 3)
        self.assertEqual(summary["config"], {"ticker": "NVDA"})
        self.assertNotIn("state", summary)

    def test_steps_track_saved_records(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            job = store.create({"ticker": "NVDA", "protocol": {}})
            self.assertEqual(store.job_summaries()[0]["steps"], 0)
            store.save_step(job["id"], {**job["state"], "records": [{}, {}]})
            self.assertEqual(store.job_summaries()[0]["steps"], 2)


if __name__ == "__main__":
    unittest.main()
