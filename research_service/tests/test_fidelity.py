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

    def test_indicator_windows_and_protocol_horizons_are_supported_numbers(self):
        # v3-0926.3: these were rejected in real Gemini runs although nothing was invented.
        evidence = [{'evidence_id': 'tech', 'claim': 'return20 = -0.014023; price_vs_mean60 = -0.012453'}]
        validate_financial_numbers({'rationale': 'The 20-day return of -0.014023 and the 60-day mean '
                                                 'support a view over the next 60 sessions (30 and 90 too).',
                                    'evidence_ids': ['tech']}, evidence)

    def test_rounded_converted_or_invented_numbers_are_still_rejected(self):
        evidence = [{'evidence_id': 'tech', 'claim': 'return20 = -0.014023; price_vs_mean60 = -0.012453'},
                    {'evidence_id': 'vol', 'claim': 'volatility60_annual = 0.41'}]
        for text in ('return20 was -0.014', 'a -1.4% 20-day return', 'a 45-day outlook', 'score 4.64'):
            with self.assertRaises(ValueError, msg=text):
                validate_financial_numbers({'rationale': text, 'evidence_ids': ['tech']}, evidence)

    def test_numbers_from_calibration_shown_in_the_prompt_are_supported(self):
        # v3-0926.5: a real Gemini run quoted sentiment mean_score -0.9309722604230046
        # from decision_calibration, which is not an evidence claim.
        evidence = [{'evidence_id': 'rev', 'claim': 'Revenues = 91166000000 USD'}]
        context = {'decision_calibration': {'sentiment_target': {'mean_score': -0.9309722604230046}},
                   'base_rates': {'hold_band_pct': 1.25}}
        result = {'rationale': 'Sentiment mean -0.9309722604230046 is outside the 1.25% band.',
                  'evidence_ids': ['rev']}
        validate_financial_numbers(result, evidence, context)
        with self.assertRaises(ValueError):  # without the prompt context it is still unsupported
            validate_financial_numbers(result, evidence)
        with self.assertRaises(ValueError):  # rounding a calibration value is still rejected
            validate_financial_numbers({'rationale': 'mean -0.93', 'evidence_ids': ['rev']}, evidence, context)

    def test_exact_percent_conversion_is_supported_but_rounding_is_not(self):
        # v3-0926.6: a real Gemini run wrote 0.500153 as 50.0153% and -0.0677 as -6.77%.
        evidence = [{'evidence_id': 'rates', 'claim': 'positive_rate = 0.500153; return20 = -0.0677; band 1.25%'}]
        validate_financial_numbers({'rationale': 'Positive 50.0153% of windows; return20 was -6.77%; '
                                                 'band 0.0125.', 'evidence_ids': ['rates']}, evidence)
        for text in ('Positive 50.02% of windows', 'return20 was -6.8%', 'Positive 50% of windows'):
            with self.assertRaises(ValueError, msg=text):
                validate_financial_numbers({'rationale': text, 'evidence_ids': ['rates']}, evidence)

    def test_own_forecast_and_prompt_numbers_are_supported(self):
        # v3-0926.7: restating one's own forecast, or a figure from an earlier
        # round shown in the prompt, is not inventing a number.
        evidence = [{'evidence_id': 'rev', 'claim': 'Revenues = 91166000000 USD'}]
        result = {'rationale': 'I expect 3.5% with 0.65 confidence; the bear case said -2.25.',
                  'expected_return_pct': 3.5, 'confidence': 0.65, 'evidence_ids': ['rev']}
        prompt = '{"history": [{"output": {"expected_return_pct": -2.25}}]}'
        validate_financial_numbers(result, evidence, prompt)
        with self.assertRaises(ValueError):  # -2.25 was not in anything the model saw
            validate_financial_numbers(result, evidence)
        with self.assertRaises(ValueError):  # a rounded restatement of its own forecast
            validate_financial_numbers({**result, 'rationale': 'I expect 4% with 0.65 confidence.'}, evidence, prompt)

    def test_one_invalid_citation_is_rejected_instead_of_passing_eighty_percent(self):
        result = dict(action='Buy', expected_return_pct=4.0, confidence=.9, rationale='test', risks=[],
                      evidence_ids=['a', 'b', 'c', 'd', 'invented'])
        with self.assertRaisesRegex(ValueError, 'evidence_id'):
            validate_decision(result, [{'evidence_id': key} for key in 'abcd'])

    def test_exact_number_from_available_but_uncited_evidence_passes(self):
        # v3-0926.4: real Gemini runs quoted exact technical values while citing only
        # fundamental evidence. The number must exist in the evidence passed in;
        # a real citation is still required.
        evidence = [
            {'evidence_id': 'revenue', 'claim': 'Revenues = 91166000000 USD'},
            {'evidence_id': 'vol', 'claim': 'volatility60_annual = 0.364565'},
        ]
        validate_financial_numbers(
            {'summary': 'Revenues 91,166,000,000 USD; volatility 0.364565', 'evidence_ids': ['revenue']}, evidence)
        with self.assertRaisesRegex(ValueError, '沒有可驗證的引用來源'):
            validate_financial_numbers({'summary': 'volatility 0.364565', 'evidence_ids': ['invented']}, evidence)

    def test_comparable_financial_decision_requires_exact_cited_numbers(self):
        evidence = [{'evidence_id': 'revenue-yoy', 'domain': 'fundamental', 'comparative': True,
                     'claim': 'Revenue current=30000000000 USD; prior=18000000000 USD; year_over_year_change_pct=66.666667'}]
        valid = {'action': 'Buy', 'expected_return_pct': 4.0, 'confidence': .8,
                 'rationale': 'Revenue growth was 66.666667%.', 'risks': [],
                 'evidence_ids': ['revenue-yoy']}
        self.assertEqual(validate_decision(valid, evidence)['action'], 'Buy')
        drifted = {**valid, 'rationale': 'Revenue growth was 6.666667%.'}
        with self.assertRaisesRegex(ValueError, r'來源未支持的數字（6\.666667）'):
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
                {'evidence_id': 'target-news', 'domain': 'sentiment', 'available_at': '2024-12-01',
                 'source_type': 'fnspid', 'claim': 'NVIDIA earnings headline'},
                {'evidence_id': 'market-context', 'domain': 'sentiment', 'available_at': '2024-12-02',
                 'source_type': 'fnspid', 'claim': 'Micron sector headline'},
            ],
        }
        inputs = research_inputs(dataset, '2024-12-31')
        self.assertEqual({item['evidence_id'] for item in inputs['domains']['sentiment']},
                         {'target-news', 'market-context'})
