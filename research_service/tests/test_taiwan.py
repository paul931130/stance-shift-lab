"""Offline acceptance checks for the isolated Taiwan exploratory workflow."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from research_service.app import create_app
from research_service.storage import Store
from research_service.taiwan import TaiwanService, check_quote, validate_output, validate_ticker


MODEL = 'ollama/test-model'


def quote(ticker='2330.TW', price=100):
    return {'ticker': ticker, 'price': price, 'as_of': datetime.now(timezone.utc).date().isoformat(),
            'fetched_at': datetime.now(timezone.utc).isoformat(),
            'evidence_id': 'TWQ-test', 'source': 'offline fixture',
            'history': [{'date': datetime.now(timezone.utc).date().isoformat(), 'close': price}], 'currency': 'TWD'}


class RecordingModel:
    def __init__(self):
        self.calls = []

    def __call__(self, protocol, messages):
        payload = json.loads(messages[-1]['content'])
        self.calls.append((messages[0]['content'], payload))
        return {'action': 'Hold', 'expected_return_pct': 0, 'confidence': .3,
                'rationale': payload['role'] + '：缺少財報與新聞，證據不足。',
                'evidence_ids': [payload['quote']['evidence_id']],
                'risks': ['未提供財報與新聞'], 'numeric_claims': []}, {
                    'usage': {'total_tokens': 10}, 'secret': 'never persist this'}


class TaiwanTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2])
        self.addCleanup(self.directory.cleanup)
        self.model = RecordingModel()
        self.service = TaiwanService(self.directory.name, self.model, quote_loader=quote)
        self.addCleanup(self.service.executor.shutdown, wait=True)
        self.addCleanup(self.service.close)

    def complete(self):
        # Run the same service path synchronously, without a race or network access.
        with patch.object(self.service.executor, 'submit'):
            report = self.service.create('2330.TW', MODEL)
        self.service.run(report['id'])
        result = self.service.get(report['id'])
        self.assertEqual(result['status'], 'complete', result)
        return result

    def test_ticker_and_invalid_or_stale_quote_are_rejected(self):
        self.assertEqual(validate_ticker(' 2330.tw '), '2330.TW')
        self.assertEqual(validate_ticker('8069.TWO'), '8069.TWO')
        for ticker in ('AAPL', '2330', '../2330.TW', '123.TW'):
            with self.subTest(ticker=ticker), self.assertRaises(ValueError):
                validate_ticker(ticker)
        for value in (float('nan'), float('inf'), 0, -1, True, '100'):
            with self.subTest(price=value), self.assertRaises(ValueError):
                check_quote(quote(price=value), '2330.TW')
        stale = quote()
        stale['as_of'] = (datetime.now(timezone.utc) - timedelta(days=8)).date().isoformat()
        with self.assertRaises(ValueError):
            check_quote(stale, '2330.TW')

    def test_roles_evidence_and_missing_data_are_auditable(self):
        report = self.complete()
        self.assertEqual([p['role'] for _, p in self.model.calls], ['bull', 'bear', 'judge'])
        judge = self.model.calls[-1][1]
        self.assertEqual(set(judge['arguments']), {'bull', 'bear'})
        self.assertIn('bull', judge['arguments']['bull']['rationale'])
        self.assertIn('bear', judge['arguments']['bear']['rationale'])
        self.assertTrue(any('財報與新聞' in text for text in report['limitations']))
        self.assertTrue(all('未提供財報與新聞' in system for system, _ in self.model.calls))
        self.assertFalse(report['formal_result'])
        self.assertEqual([a['role'] for a in report['audit']], ['bull', 'bear', 'judge'])
        self.assertNotIn('never persist this', json.dumps(report))
        invalid = deepcopy(report['report']['judge'])
        invalid['evidence_ids'] = ['invented-source']
        with self.assertRaises(ValueError):
            validate_output(invalid, 'TWQ-test')

    def test_narrative_may_name_stock_code_and_idioms_but_not_numbers(self):
        def decision(text):
            return {'action': 'Hold', 'expected_return_pct': 0, 'confidence': .3, 'rationale': text,
                    'evidence_ids': ['TWQ-x'], 'risks': [], 'numeric_claims': []}
        for text in ('2330 與 2330.TW 證據不足', '走勢有一點轉弱', '並非一成不變'):
            validate_output(decision(text), 'TWQ-x', '2330.TW')
        for text in ('上漲十一點', '目標三成', '價格 2331 元', '漲了一點五元'):
            with self.assertRaises(ValueError, msg=text):
                validate_output(decision(text), 'TWQ-x', '2330.TW')

    def test_quote_survives_lunar_new_year_closure(self):
        today = datetime.now(ZoneInfo('Asia/Taipei')).date()
        def aged(days):
            stamp = (today - timedelta(days=days)).isoformat()
            return {'ticker': '2330.TW', 'price': 100, 'as_of': stamp, 'fetched_at': datetime.now(timezone.utc).isoformat(),
                    'evidence_id': 'TWQ-x', 'history': [{'date': stamp, 'close': 100}]}
        check_quote(aged(11), '2330.TW')
        with self.assertRaises(ValueError):
            check_quote(aged(15), '2330.TW')

    def test_report_api_and_decision_survive_restart_without_formal_jobs(self):
        store = Store(self.directory.name)
        with patch.dict(os.environ, {'RESEARCH_ACCESS_KEY': '', 'RESEARCH_DEMO_MODE': 'false'}), \
                patch('research_service.web.taiwan.TaiwanService', return_value=self.service):
            with TestClient(create_app(store, self.model, start_worker=False)) as client:
                with patch.object(self.service.executor, 'submit'):
                    response = client.post('/api/taiwan/reports', json={'ticker': '2330.TW', 'model': MODEL})
                self.assertEqual(response.status_code, 202, response.text)
                report_id = response.json()['id']
                self.service.run(report_id)
                self.assertEqual(client.get('/api/taiwan/reports/' + report_id).json()['status'], 'complete')
                response = client.post('/api/taiwan/decisions', json={
                    'report_id': report_id, 'action': 'Buy', 'quantity': 10, 'note': 'offline test'})
                self.assertEqual(response.status_code, 201, response.text)
                self.assertEqual(client.get('/api/taiwan/reports').json()['items'][0]['id'], report_id)
                self.assertEqual(client.get('/api/jobs').json(), [])
        self.assertEqual(store.active_job_count(), 0)
        restarted = TaiwanService(self.directory.name, self.model, quote_loader=quote)
        self.addCleanup(restarted.executor.shutdown, wait=True)
        self.addCleanup(restarted.close)
        self.assertEqual(restarted.get(report_id)['status'], 'complete')
        decision = restarted.list('decisions')[0]
        self.assertEqual(decision['report_id'], report_id)
        self.assertTrue(decision['simulation_only'])
        self.assertEqual(decision['execution_status'], 'recorded_only')

    def test_decisions_require_recent_complete_report_and_server_quote(self):
        report = self.complete()
        for quantity in (-1, 1.5, True, 0):
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                self.service.decide(report['id'], 'Buy', quantity)
        self.service.quote_loader = lambda ticker: quote(ticker, price=123)
        decision = self.service.decide(report['id'], 'Buy', 10)
        self.assertEqual(decision['reference_price'], 100)
        self.assertEqual(decision['report_quote']['price'], 100)
        for changes in ({'status': 'running'}, {'completed_at': (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()}):
            modified = {**report, **changes}
            self.service.save(modified)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.service.decide(report['id'], 'Buy', 10)
        self.service.save(report)
        with patch.dict(os.environ, {'RESEARCH_ACCESS_KEY': '', 'RESEARCH_DEMO_MODE': 'false'}), \
                patch('research_service.web.taiwan.TaiwanService', return_value=self.service):
            with TestClient(create_app(Store(self.directory.name), self.model, start_worker=False)) as client:
                base = {'report_id': report['id'], 'action': 'Buy', 'quantity': 10}
                for extra in ({'reference_price': 1}, {'quote_snapshot': quote(price=1)}, {'quantity': 1.2}):
                    self.assertEqual(client.post('/api/taiwan/decisions', json={**base, **extra}).status_code, 422)

    def test_taiwan_routes_obey_existing_auth(self):
        key = 'k' * 32
        with patch.dict(os.environ, {'RESEARCH_ACCESS_KEY': key, 'RESEARCH_DEMO_MODE': 'false'}), \
                patch('research_service.web.taiwan.TaiwanService', return_value=self.service):
            with TestClient(create_app(Store(self.directory.name), self.model, start_worker=False)) as client:
                self.assertEqual(client.get('/api/taiwan/reports').status_code, 401)
                self.assertEqual(client.post('/api/taiwan/reports', json={'ticker': '2330.TW', 'model': MODEL}).status_code, 401)
                self.assertEqual(client.get('/api/taiwan/reports', headers={'Authorization': 'Bearer ' + key}).status_code, 200)


if __name__ == '__main__':
    unittest.main()
