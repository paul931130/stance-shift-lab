"""scripts/check_price_gaps.py: read-only detection of holes in stored price bars."""
from datetime import date, timedelta
import importlib.util
from pathlib import Path
import tempfile
import unittest

from research_service.storage import Store

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_price_gaps.py"
spec = importlib.util.spec_from_file_location("check_price_gaps", SCRIPT)
check_price_gaps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_price_gaps)


def business_days(start, count, skip=()):
    days, cursor = [], start
    while len(days) < count:
        if cursor.weekday() < 5 and cursor.isoformat() not in skip:
            days.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return days


def dataset(ticker, dates, analysis_date="2024-03-29"):
    bars = [{"date": day, "open": 10., "high": 11., "low": 9., "close": 10.} for day in dates]
    return {"ticker": ticker, "kind": "real", "requested_analysis_date": analysis_date, "prices": bars}


class CheckPriceGapsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_check(self, horizon=60):
        return check_price_gaps.check(check_price_gaps.load_datasets(self.tmp.name), horizon)

    def test_complete_bars_are_not_flagged(self):
        for ticker in ("AAA", "BBB", "CCC"):
            self.store.add_dataset(dataset(ticker, business_days(date(2024, 1, 2), 200)))
        self.assertEqual(self.run_check(), [])

    def test_long_calendar_gap_and_day_missing_versus_peers_are_flagged(self):
        full = business_days(date(2024, 1, 2), 200)
        for ticker in ("AAA", "BBB"):
            self.store.add_dataset(dataset(ticker, full))
        # CCC lacks one day inside the holding window and a whole week a little later.
        week = {(date(2024, 5, 6) + timedelta(days=offset)).isoformat() for offset in range(5)}
        self.store.add_dataset(dataset("CCC", [day for day in full if day != "2024-04-10" and day not in week]))
        flagged = self.run_check()
        self.assertEqual([item["ticker"] for item in flagged], ["CCC"])
        problems = " ".join(flagged[0]["problems"])
        self.assertIn("缺 2024-04-10", problems)
        self.assertIn("2024-05-03 → 2024-05-13", problems)

    def test_too_few_future_bars_and_synthetic_data(self):
        self.store.add_dataset(dataset("AAA", business_days(date(2024, 1, 2), 80)))
        self.store.add_dataset({**dataset("BBB", business_days(date(2024, 1, 2), 80)), "kind": "synthetic"})
        flagged = self.run_check(horizon=60)
        self.assertEqual([item["ticker"] for item in flagged], ["AAA"])
        self.assertIn("不足 61", flagged[0]["problems"][-1])


if __name__ == "__main__":
    unittest.main()
