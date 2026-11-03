"""Offline shared-database ownership and shutdown regression checks."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import tempfile
import threading
import unittest
from unittest.mock import patch

from research_service.taiwan import TaiwanService, now


MODEL = 'ollama/test-model'


def quote(ticker):
    stamp = datetime.now(timezone.utc).date().isoformat()
    return {'ticker': ticker, 'price': 100, 'as_of': stamp, 'fetched_at': now(),
            'evidence_id': 'TWQ-lifecycle', 'history': [{'date': stamp, 'close': 100}]}


class BlockingModel:
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    def __call__(self, protocol, messages):
        self.calls += 1
        self.entered.set()
        if not self.release.wait(10):
            raise TimeoutError('test model was not released')
        payload = json.loads(messages[-1]['content'])
        return {'action': 'Hold', 'expected_return_pct': 0, 'confidence': .3,
                'rationale': '缺少財報與新聞，證據不足。',
                'evidence_ids': [payload['quote']['evidence_id']],
                'risks': ['未提供財報與新聞'], 'numeric_claims': []}, {}


class TaiwanLifecycleTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[2] / 'tmp'
        root.mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(prefix='taiwan-lifecycle-', dir=root)
        self.services = []
        self.models = []

    def tearDown(self):
        for model in self.models:
            model.release.set()
        for service in self.services:
            service.close()
            service.executor.shutdown(wait=True, cancel_futures=True)
        self.directory.cleanup()

    def service(self):
        model = BlockingModel()
        self.models.append(model)
        service = TaiwanService(self.directory.name, model, quote_loader=quote)
        self.services.append(service)
        return service, model

    def queued(self, service, ticker='2330.TW'):
        with patch.object(service.executor, 'submit'):
            return service.create(ticker, MODEL)

    def test_starting_another_service_preserves_live_owner_work(self):
        first, model = self.service()
        report = first.create('2330.TW', MODEL)
        self.assertTrue(model.entered.wait(5))
        second, _ = self.service()
        self.assertEqual(second.get(report['id'])['status'], 'running')
        self.assertNotEqual(first.service_id, second.service_id)
        self.assertEqual(second.get(report['id'])['owner'], first.service_id)
        self.assertEqual(second.recover(), 0)

    def test_recover_marks_legacy_and_missing_owner_jobs_failed(self):
        service, _ = self.service()
        legacy = self.queued(service)
        orphan = self.queued(service, '2317.TW')
        legacy.pop('owner', None)
        orphan['owner'] = 'missing-service'
        service.save(legacy)
        service.save(orphan)
        self.assertEqual(service.recover(), 2)
        for report in (legacy, orphan):
            failed = service.get(report['id'])
            self.assertEqual(failed['status'], 'failed')
            self.assertTrue(failed['error'])
        self.assertEqual(service.recover(), 0)

    def test_recover_only_reclaims_expired_owner(self):
        first, _ = self.service()
        stale = self.queued(first)
        second, _ = self.service()
        fresh = self.queued(second, '2317.TW')
        expired = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        with second.connect() as db:
            db.execute('UPDATE services SET heartbeat=? WHERE id=?', (expired, first.service_id))
        self.assertEqual(second.recover(), 1)
        self.assertEqual(second.get(stale['id'])['status'], 'failed')
        self.assertEqual(second.get(fresh['id'])['status'], 'queued')

    def race_creates(self, services, tickers):
        gate = threading.Barrier(len(services))

        def create(item):
            service, ticker = item
            gate.wait(timeout=5)
            try:
                return service.create(ticker, MODEL)
            except ValueError:
                return None

        patches = [patch.object(service.executor, 'submit') for service in services]
        for item in patches:
            item.start()
        try:
            with ThreadPoolExecutor(max_workers=len(services)) as executor:
                return list(executor.map(create, zip(services, tickers)))
        finally:
            for item in reversed(patches):
                item.stop()

    def test_concurrent_services_accept_only_one_duplicate(self):
        services = [self.service()[0] for _ in range(4)]
        results = self.race_creates(services, ['2330.TW'] * len(services))
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(services[0].active_count(), 1)

    def test_concurrent_services_enforce_global_queue_capacity(self):
        services = [self.service()[0] for _ in range(6)]
        results = self.race_creates(services, [f'{2300 + index}.TW' for index in range(6)])
        self.assertEqual(sum(result is not None for result in results), 3)
        self.assertEqual(services[0].active_count(), 3)

    def test_close_preserves_other_owner_and_rejects_late_model_results(self):
        first, model = self.service()
        second, _ = self.service()
        other = self.queued(second, '2317.TW')
        running = first.create('2330.TW', MODEL)
        self.assertTrue(model.entered.wait(5))
        queued = self.queued(first, '2454.TW')
        first.close()
        before = first.get(running['id'])
        self.assertEqual(before['status'], 'failed')
        self.assertEqual(first.get(queued['id'])['status'], 'failed')
        self.assertEqual(second.get(other['id'])['status'], 'queued')
        model.release.set()
        first.executor.shutdown(wait=True)
        self.assertEqual(first.get(running['id']), before)
        self.assertEqual(model.calls, 1)

    def test_closed_service_rejects_create_without_persisting_work(self):
        service, _ = self.service()
        service.close()
        with self.assertRaises(ValueError):
            service.create('2330.TW', MODEL)
        self.assertEqual(service.list('reports'), [])

    def test_close_is_idempotent_and_recovery_keeps_completed_work(self):
        service, model = self.service()
        model.release.set()
        report = service.create('2330.TW', MODEL)
        service.executor.shutdown(wait=True)
        completed = service.get(report['id'])
        self.assertEqual(completed['status'], 'complete')
        service.close()
        service.close()
        second, _ = self.service()
        self.assertEqual(second.get(report['id']), completed)
        self.assertEqual(second.recover(), 0)

    def test_expired_running_owner_cannot_publish_late_result(self):
        first, model = self.service()
        second, _ = self.service()
        report = first.create('2330.TW', MODEL)
        self.assertTrue(model.entered.wait(5))
        expired = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        with second.connect() as db:
            db.execute('UPDATE services SET heartbeat=? WHERE id=?', (expired, first.service_id))
        self.assertEqual(second.recover(), 1)
        failed = second.get(report['id'])
        self.assertEqual(failed['status'], 'failed')
        model.release.set()
        first.executor.shutdown(wait=True)
        self.assertEqual(second.get(report['id']), failed)
        self.assertEqual(model.calls, 1)
        with self.assertRaises(ValueError):
            first.create('2317.TW', MODEL)

    def test_heartbeat_renews_live_lease_but_cannot_revive_expired_lease(self):
        service, _ = self.service()
        previous = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
        with service.connect() as db:
            db.execute('UPDATE services SET heartbeat=? WHERE id=?', (previous, service.service_id))
        self.assertTrue(service.heartbeat())
        with service.connect() as db:
            renewed = db.execute('SELECT heartbeat FROM services WHERE id=?', (service.service_id,)).fetchone()[0]
        self.assertGreater(datetime.fromisoformat(renewed), datetime.fromisoformat(previous))
        expired = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        with service.connect() as db:
            db.execute('UPDATE services SET heartbeat=? WHERE id=?', (expired, service.service_id))
        self.assertFalse(service.heartbeat())
        with service.connect() as db:
            row = db.execute('SELECT heartbeat FROM services WHERE id=?', (service.service_id,)).fetchone()
        self.assertTrue(row is None or row[0] == expired)
        with self.assertRaises(ValueError):
            service.create('2330.TW', MODEL)

    def test_rejoin_after_expired_lease_fences_old_reports_and_accepts_new_ones(self):
        service, model = self.service()
        stale = service.create('2330.TW', MODEL)
        self.assertTrue(model.entered.wait(5))
        old_id = service.service_id
        expired = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        with service.connect() as db:
            db.execute('UPDATE services SET heartbeat=? WHERE id=?', (expired, old_id))
        self.assertFalse(service.heartbeat())
        self.assertTrue(service.rejoin())
        self.assertNotEqual(service.service_id, old_id)
        self.assertEqual(service.get(stale['id'])['status'], 'failed')
        model.release.set()
        self.assertEqual(service.create('2317.TW', MODEL)['owner'], service.service_id)

    def test_run_cannot_claim_other_owner_or_repeat_completed_work(self):
        first, first_model = self.service()
        second, second_model = self.service()
        report = self.queued(second)
        first.run(report['id'])
        self.assertEqual(first_model.calls, 0)
        self.assertEqual(second.get(report['id'])['status'], 'queued')
        second_model.release.set()
        second.run(report['id'])
        completed = second.get(report['id'])
        self.assertEqual(completed['status'], 'complete')
        self.assertEqual(second_model.calls, 3)
        second.run(report['id'])
        first.run(report['id'])
        self.assertEqual(second.get(report['id']), completed)
        self.assertEqual(second_model.calls, 3)
        self.assertEqual(first_model.calls, 0)

    def test_failed_executor_submission_releases_queue_capacity(self):
        service, model = self.service()
        with patch.object(service.executor, 'submit', side_effect=RuntimeError('executor unavailable')):
            with self.assertRaises(RuntimeError):
                service.create('2330.TW', MODEL)
        reports = service.list('reports')
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]['status'], 'failed')
        self.assertTrue(reports[0]['error'])
        self.assertEqual(model.calls, 0)
        self.assertEqual(service.active_count(), 0)
        for ticker in ('2330.TW', '2317.TW', '2454.TW'):
            self.queued(service, ticker)
        self.assertEqual(service.active_count(), 3)


if __name__ == '__main__':
    unittest.main()
