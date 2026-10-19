"""Registered study batches stop when a frozen case is paused or cancelled."""

from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research_service.storage import Store


class StudyStopGuardTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = Store(self.directory.name)

    def job(self, protocol="registered", dataset="frozen", date="2026-01-02", purpose=None):
        config = {"protocol_hash": protocol, "dataset_id": dataset,
                  "ticker": "NVDA", "analysis_date": date, "protocol": {}}
        if purpose:
            config["execution_purpose"] = purpose
        return self.store.create(config)

    def register(self, protocol="registered"):
        self.store.freeze(protocol, ["frozen"])
        # Fixed timestamp keeps the test independent of clock resolution.
        with self.store.connect() as db:
            db.execute("UPDATE preregistrations SET frozen_at='2026-01-01' WHERE protocol_hash=?",
                       (protocol,))

    def claim(self):
        with patch("research_service.protocol.protocol_is_current", return_value=True):
            return self.store.claim()

    def test_pause_error_and_cancel_each_block_registered_study(self):
        for command in ("pause", "cancel"):
            with self.subTest(command=command):
                protocol = command
                self.register(protocol)
                stopped = self.job(protocol, date="2026-01-01")
                waiting = self.job(protocol)
                self.store.control(stopped["id"], command)
                self.assertIsNone(self.claim())
                self.assertEqual(self.store.get(waiting["id"])["status"], "queued")

        self.register("error")
        stopped = self.job("error", date="2026-01-01")
        waiting = self.job("error")
        self.store.save_step(stopped["id"], stopped["state"], error="provider failure")
        self.assertIsNone(self.claim())
        self.assertEqual(self.store.get(waiting["id"])["status"], "queued")

    def test_resume_stopped_case_allows_study_to_run(self):
        self.register()
        first = self.job(date="2026-01-01")
        second = self.job()
        self.store.control(first["id"], "pause")
        self.assertIsNone(self.claim())
        with patch("research_service.protocol.protocol_is_current", return_value=True):
            self.store.control(first["id"], "resume")
        self.assertEqual(self.claim()["id"], first["id"])
        self.assertEqual(self.claim()["id"], second["id"])

    def test_stopped_study_does_not_block_other_study(self):
        self.register()
        stopped = self.job(date="2026-01-01")
        waiting = self.job(date="2026-01-02")
        other = self.job("other", date="2026-01-03")
        self.store.control(stopped["id"], "pause")
        self.assertEqual(self.claim()["id"], other["id"])
        self.assertEqual(self.store.get(waiting["id"])["status"], "queued")

    def test_qualification_and_report_bank_do_not_stop_or_get_stopped(self):
        self.register()
        qualifier = self.job(date="2026-01-01", purpose="qualification")
        self.store.control(qualifier["id"], "pause")
        regular = self.job(date="2026-01-02")
        self.assertEqual(self.claim()["id"], regular["id"])

        stopped = self.job(date="2026-01-03")
        self.store.control(stopped["id"], "pause")
        report = self.job(date="2026-01-04", purpose="report_bank")
        another_qualifier = self.job(date="2026-01-05", purpose="qualification")
        self.assertEqual(self.claim()["id"], report["id"])
        self.assertEqual(self.claim()["id"], another_qualifier["id"])

    def test_unregistered_and_outside_frozen_sample_keep_old_behavior(self):
        unregistered = self.job("unregistered", date="2026-01-01")
        self.store.control(unregistered["id"], "pause")
        next_unregistered = self.job("unregistered", date="2026-01-02")
        self.assertEqual(self.claim()["id"], next_unregistered["id"])

        self.register()
        outside = self.job(dataset="outside", date="2026-01-03")
        self.store.control(outside["id"], "pause")
        inside = self.job(date="2026-01-04")
        self.assertEqual(self.claim()["id"], inside["id"])

        self.register("pre-freeze")
        old = self.job("pre-freeze", date="2025-12-31")
        with self.store.connect() as db:
            db.execute("UPDATE jobs SET created_at='2025-12-31' WHERE id=?", (old["id"],))
        self.store.control(old["id"], "pause")
        fresh = self.job("pre-freeze", date="2026-01-05")
        self.assertEqual(self.claim()["id"], fresh["id"])


if __name__ == "__main__":
    unittest.main()
