from datetime import date
import os
import unittest
from unittest.mock import patch
from urllib.parse import urlparse

from research_service.finnhub import live_snapshot, quote_snapshot
from research_service.protocol import validate_live_symbol


class FinnhubTests(unittest.TestCase):
    def requester(self, url, headers):
        self.calls.append((url, headers))
        path = urlparse(url).path
        if path.endswith("/quote"):
            return {"c": 25.5, "d": .5, "dp": 2, "h": 26, "l": 24, "o": 25, "pc": 25, "t": 123}
        if path.endswith("/stock/market-status"):
            return {"exchange": "US", "isOpen": True, "session": "regular"}
        if path.endswith("/stock/market-holiday"):
            return {"data": [{"atDate": "2026-12-25", "eventName": "Christmas"}]}
        if path.endswith("/calendar/earnings"):
            return {"earningsCalendar": [{"date": "2026-09-10", "symbol": "ASTS", "hour": "amc"}]}
        if path.endswith("/stock/recommendation"):
            return [{"symbol": "ASTS", "period": "2026-09-01", "buy": 2, "hold": 1}]
        if path.endswith("/stock/price-target"):
            return {"symbol": "ASTS", "targetMean": 42, "numberAnalysts": 3}
        raise AssertionError(url)

    def setUp(self):
        self.calls = []

    def test_live_snapshot_keeps_key_in_header_and_degrades_by_panel(self):
        with patch.dict(os.environ, {"FINNHUB_API_KEY": "test-finnhub-key"}):
            result = live_snapshot("asts", self.requester, today=date(2026, 9, 7))
        self.assertEqual((result["mode"], result["symbol"], result["trading_enabled"]), ("live", "ASTS", False))
        self.assertEqual(set(result["panels"]), {"quote", "market_status", "market_holidays", "earnings_calendar", "recommendation_trends", "price_target"})
        self.assertTrue(all(panel["status"] == "ready" for panel in result["panels"].values()))
        self.assertTrue(all("test-finnhub-key" not in url for url, _ in self.calls))
        self.assertTrue(all(headers["X-Finnhub-Token"] == "test-finnhub-key" for _, headers in self.calls))

    def test_missing_key_and_invalid_symbol_fail_closed(self):
        with patch.dict(os.environ, {"FINNHUB_API_KEY": ""}):
            with self.assertRaisesRegex(ValueError, "FINNHUB_API_KEY"):
                quote_snapshot("AAPL", self.requester)
        with self.assertRaises(ValueError):
            validate_live_symbol("AAPL/../../secret")


if __name__ == "__main__":
    unittest.main()
