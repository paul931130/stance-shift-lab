"""Worker checkpoints are fenced, including pause/resume, cancellation and failure."""
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import os
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from research_service.app import create_app
from research_service.protocol import StudyProtocol
from research_service.storage import JobLeaseLost, Store


class WorkerFencingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        p = StudyProtocol(dataset_kind="synthetic")
        self.job = self.store.create({"ticker": "NVDA", "dataset_id": "d", "analysis_date": "2024-12-31",
                                      "protocol": asdict(p), "protocol_hash": p.fingerprint})

    def save(self, job, state=None, error=""):
        self.store.save_step(job["id"], state or job["state"], error,
                             owner=job["owner"], generation=job["lease_generation"])

    def test_each_worker_checkpoint_releases_the_lease_for_the_next_step(self):
        first = self.store.claim("worker:a")
        self.assertEqual((first["status"], first["owner"]), ("running", "worker:a"))
        with self.assertRaises(JobLeaseLost):
            self.store.save_step(first["id"], first["state"], owner=first["owner"])
        self.save(first)
        self.assertEqual((self.store.get(first["id"])["status"], self.store.get(first["id"])["owner"]),
                         ("queued", ""))
        second = self.store.claim("worker:a")
        self.assertGreater(second["lease_generation"], first["lease_generation"])
        with self.assertRaises(JobLeaseLost):
            self.save(first, {**first["state"], "finished": True})
        self.save(second, {**second["state"], "finished": True})
        self.assertEqual(self.store.get(second["id"])["status"], "complete")

    def test_pause_cannot_be_taken_over_while_the_call_is_still_in_flight(self):
        first = self.store.claim("worker:a")
        self.store.control(first["id"], "pause")
        self.assertEqual(self.store.active_job_count(), 1)
        self.assertFalse(self.store.acquire(first["id"], "cli:new", "0000"))
        self.store.control(first["id"], "resume")
        self.assertIsNone(self.store.claim("worker:b"))
        self.save(first)
        second = self.store.claim("worker:b")
        self.assertIsNotNone(second)
        snapshot = self.store.get(second["id"])
        with self.assertRaises(JobLeaseLost):
            self.save(first, {**first["state"], "finished": True, "marker": "stale"})
        with self.assertRaises(JobLeaseLost):
            self.store.save_step(first["id"], {**first["state"], "finished": True})
        self.assertEqual(self.store.get(second["id"]), snapshot)

    def test_paused_or_cancelled_call_can_finish_without_indexing_cancelled_results(self):
        for command in ("pause", "cancel"):
            with self.subTest(command=command):
                job = self.store.claim("worker:a")
                self.store.control(job["id"], command)
                state = {**job["state"], "finished": command == "cancel", "cases": [{
                    "group": "A", "horizon": 60, "cost_model": "corwin_schultz",
                    "maturity_date": "2025-03-31", "action": "Buy", "correct": True, "net_return": .1}]}
                self.save(job, state)
                result = self.store.get(job["id"])
                self.assertEqual((result["status"], result["owner"]), ("paused" if command == "pause" else "cancelled", ""))
                self.assertEqual(self.store.active_job_count(), 0)
                with self.store.connect() as db:
                    self.assertIsNone(db.execute("SELECT 1 FROM case_results").fetchone())
                if command == "pause":
                    self.store.control(job["id"], "resume")

    def test_dead_paused_worker_recovers_but_live_worker_is_not_released(self):
        self.store.heartbeat("a")
        first = self.store.claim("worker:a")
        self.store.control(first["id"], "pause")
        now = datetime.now(timezone.utc)
        self.assertEqual(self.store.recover((now - timedelta(seconds=90)).isoformat(), "0000"), 0)
        self.assertEqual(self.store.recover("9999", "9999"), 1)
        self.store.control(first["id"], "resume")
        self.assertIsNotNone(self.store.claim("worker:a"))
        with self.assertRaises(JobLeaseLost):
            self.save(first, error="old provider failure")

    def test_cli_can_take_over_after_dead_worker_recovery_but_not_accept_its_write(self):
        first = self.store.claim("worker:dead")
        self.store.control(first["id"], "pause")
        self.assertEqual(self.store.recover("9999", "9999"), 1)
        self.assertTrue(self.store.acquire(first["id"], "cli:new", "0000"))
        current = self.store.get(first["id"])
        with self.assertRaises(JobLeaseLost):
            self.save(first, {**first["state"], "finished": True})
        self.assertEqual(self.store.get(first["id"]), current)
        self.store.save_step(current["id"], {**current["state"], "marker": "cli"},
                             owner=current["owner"], generation=current["lease_generation"])
        self.assertEqual(self.store.get(current["id"])["status"], "running")
        self.store.release(current["id"], "cli:new")
        self.assertEqual(self.store.get(current["id"])["status"], "paused")

    def test_live_worker_error_is_paused_and_releases_its_lease(self):
        first = self.store.claim("worker:a")
        self.save(first, error="provider failure")
        job = self.store.get(first["id"])
        self.assertEqual((job["status"], job["owner"], job["error"]), ("paused", "", "provider failure"))

    def test_legacy_ownerless_running_jobs_recover_without_touching_idle_jobs(self):
        paused = self.store.create(self.job["config"])
        self.store.control(paused["id"], "pause")
        with self.store.connect() as db:
            db.execute("UPDATE jobs SET status='running', owner='' WHERE id=?", (self.job["id"],))
        self.assertEqual(self.store.recover("9999", "9999"), 1)
        self.assertEqual(self.store.get(self.job["id"])["status"], "paused")
        self.assertEqual(self.store.get(paused["id"])["lease_generation"], 0)

    def test_app_worker_supplies_the_fence_on_success_and_failure(self):
        for failing in (False, True):
            with self.subTest(failing=failing):
                if failing:
                    self.job = self.store.create(self.job["config"])
                started, release, saved = threading.Event(), threading.Event(), threading.Event()

                def advance(job):
                    started.set()
                    if not release.wait(3):
                        raise RuntimeError("test release timed out")
                    if failing:
                        raise RuntimeError("stale provider failure")
                    return {**job["state"], "trace": [{"node": "done"}], "finished": True, "marker": "stale"}

                original_save = self.store.save_step

                def save_step(*args, **kwargs):
                    try:
                        return original_save(*args, **kwargs)
                    finally:
                        saved.set()

                with patch.dict(os.environ, {"RESEARCH_GPUTW_AUTOSTOP_MINUTES": "0"}), \
                        patch("research_service.app.DomainDebateEngine", return_value=SimpleNamespace(advance=advance)), \
                        patch.object(self.store, "save_step", side_effect=save_step):
                    app = create_app(self.store, model_call=lambda *a, **k: None)
                    with TestClient(app):
                        try:
                            self.assertTrue(started.wait(3))
                            with self.store.connect() as db:
                                db.execute("""UPDATE jobs SET owner='worker:new',
                                    lease_generation=lease_generation+1 WHERE id=?""", (self.job["id"],))
                            before = self.store.get(self.job["id"])
                            release.set()
                            self.assertTrue(saved.wait(3))
                            self.assertEqual(self.store.get(self.job["id"]), before)
                        finally:
                            release.set()
                self.store.control(self.job["id"], "cancel")


if __name__ == "__main__":
    unittest.main()
