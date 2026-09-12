import unittest
from datetime import date, timedelta

from research_service.data import research_inputs
from research_service.models import validate_financial_numbers, validate_financial_interpretation, validate_decision


class FidelityTests(unittest.TestCase):
    def test_factor_ten_error_is_rejected(self):
        evidence = [{'evidence_id': 'rev', 'claim': 'Revenues = 91166000000 USD'}]
        for value in ('9,116,600,000', '91.166 billion'):
            with self.assertRaises(ValueError):
                validate_financial_numbers({'summary': value, 'evidence_ids': ['rev']}, evidence)
        validate_financial_numbers({'summary': '91,166,000,000 USD', 'evidence_ids': ['rev']}, evidence)

    def test_one_invalid_citation_is_rejected_instead_of_passing_eighty_percent(self):
        result = dict(action='Buy', expected_return_pct=4.0, confidence=.9, rationale='test', risks=[],
                      evidence_ids=['a', 'b', 'c', 'd', 'invented'])
        with self.assertRaisesRegex(ValueError, 'evidence_id'):
            validate_decision(result, [{'evidence_id': key} for key in 'abcd'])

    def test_number_must_be_supported_by_a_cited_source(self):
        evidence = [
            {'evidence_id': 'revenue', 'claim': 'Revenues = 91166000000 USD'},
            {'evidence_id': 'assets', 'claim': 'Assets = 22300000000 USD'},
        ]
        with self.assertRaises(ValueError):
            validate_financial_numbers(
                {'summary': 'Assets are 22,300,000,000 USD', 'evidence_ids': ['revenue']}, evidence)

    def test_comparable_financial_decision_requires_exact_cited_numbers(self):
        evidence = [{'evidence_id': 'revenue-yoy', 'domain': 'fundamental', 'comparative': True,
                     'claim': 'Revenue current=30000000000 USD; prior=18000000000 USD; year_over_year_change_pct=66.666667'}]
        valid = {'action': 'Buy', 'expected_return_pct': 4.0, 'confidence': .8,
                 'rationale': 'Revenue growth was 66.666667%.', 'risks': [],
                 'evidence_ids': ['revenue-yoy']}
        self.assertEqual(validate_decision(valid, evidence)['action'], 'Buy')
        drifted = {**valid, 'rationale': 'Revenue growth was 6.666667%.'}
        with self.assertRaisesRegex(ValueError, '來源未支持的數字'):
            validate_decision(drifted, evidence)

    def test_point_in_time_financial_fields_cannot_be_rewritten_as_a_loss_or_quality_claim(self):
        with self.assertRaisesRegex(ValueError, '品質、盈虧或趨勢'):
            validate_financial_interpretation({
                'summary': 'Net income loss was 50,789,000,000 and creates financial pressure.',
                'risks': ['Significant liabilities may hurt profitability'],
            })
        validate_financial_interpretation({
            'summary': 'NetIncomeLoss = 50,789,000,000 USD; Liabilities = 30,114,000,000 USD.',
            'risks': [],
        })
        with self.assertRaisesRegex(ValueError, '品質、盈虧或趨勢'):
            validate_decision(
                {'action': 'Buy', 'expected_return_pct': 4.0, 'confidence': .8,
                 'rationale': 'Strong revenue and cash flow fundamentals support upside.',
                 'risks': [], 'evidence_ids': ['revenue']},
                [{'evidence_id': 'revenue', 'domain': 'fundamental', 'claim': 'Revenues = 91166000000 USD'}])

    def test_non_financial_news_growth_is_not_blocked_when_a_fundamental_fact_is_cited(self):
        """A headline's sector-growth wording is not a claim about the SEC point fact."""
        result = validate_decision(
            {'action': 'Buy', 'expected_return_pct': 4.0, 'confidence': .8,
             'rationale': 'The cited NVIDIA collaboration may support AI infrastructure growth.',
             'risks': [], 'evidence_ids': ['revenue', 'news']},
            [{'evidence_id': 'revenue', 'domain': 'fundamental', 'claim': 'Revenues = 91166000000 USD'},
             {'evidence_id': 'news', 'domain': 'sentiment',
              'claim': 'NVIDIA collaboration supports AI infrastructure growth'}])
        self.assertEqual(result['action'], 'Buy')
        # AI infrastructure growth can come from cited news; it is not a
        # statement about growth in the SEC point-in-time revenue field.
        validate_decision(
            {'action': 'Buy', 'expected_return_pct': 4.0, 'confidence': .8,
             'rationale': 'The cited NVIDIA collaboration may support AI infrastructure growth.',
             'risks': [], 'evidence_ids': ['revenue', 'news']},
            [{'evidence_id': 'revenue', 'domain': 'fundamental', 'claim': 'Revenues = 91166000000 USD'},
             {'evidence_id': 'news', 'domain': 'sentiment', 'claim': 'NVIDIA collaboration supports AI infrastructure growth'}])

    def test_cross_company_news_is_retained_as_context(self):
        start = date(2024, 1, 1)
        dataset = {
            'ticker': 'NVDA', 'kind': 'historical', 'source': 'unit-test',
            'prices': [{'date': (start + timedelta(days=i)).isoformat(), 'close': 100 + i}
                       for i in range(65)],
            'evidence': [
                {'evidence_id': 'target-news', 'domain': 'sentiment', 'available_at': '2024-03-01',
                 'source_type': 'fnspid', 'claim': 'NVIDIA earnings headline'},
                {'evidence_id': 'market-context', 'domain': 'sentiment', 'available_at': '2024-03-02',
                 'source_type': 'fnspid', 'claim': 'Micron sector headline'},
            ],
        }
        inputs = research_inputs(dataset, '2024-12-31')
        self.assertEqual({item['evidence_id'] for item in inputs['domains']['sentiment']},
                         {'target-news', 'market-context'})
