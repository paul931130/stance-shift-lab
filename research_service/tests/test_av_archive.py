from datetime import datetime, timezone
import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_service.av_archive import default_archive_path, default_checkpoint_path, month_windows, refresh_archive


class MonthWindowsTests(unittest.TestCase):
    def test_splits_a_range_into_calendar_months(self):
        start = datetime(2023, 12, 17, tzinfo=timezone.utc)
        end = datetime(2024, 2, 10, tzinfo=timezone.utc)
        windows = month_windows(start, end)
        self.assertEqual(len(windows), 3)
        self.assertEqual(windows[0][0], start)
        self.assertEqual(windows[0][1].strftime("%Y-%m"), "2023-12")
        self.assertEqual(windows[-1][1], end)


class RefreshArchiveTests(unittest.TestCase):
    def _run(self, tickers, responses, **kwargs):
        calls = []
        def requester(url):
            calls.append(url)
            return responses.pop(0) if responses else {"feed": []}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "alphavantage_news.csv"
            checkpoint = Path(directory) / "av_checkpoint.json"
            progress_events = []
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "test-key"}):
                result = refresh_archive(
                    output_path=output, checkpoint_path=checkpoint, tickers=tickers,
                    start_date=kwargs.get("start_date"), end_date=kwargs.get("end_date"),
                    daily_limit=kwargs.get("daily_limit", 25), call_delay=0,
                    requester=requester, progress=lambda **kw: progress_events.append(kw), sleep=lambda _: None,
                )
            rows = []
            if output.exists():
                with output.open(encoding="utf-8-sig", newline="") as handle:
                    rows = list(csv.DictReader(handle))
            return result, rows, calls, progress_events

    def test_requires_an_api_key(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": ""}):
                with self.assertRaisesRegex(ValueError, "ALPHA_VANTAGE_API_KEY"):
                    refresh_archive(output_path=Path(directory) / "a.csv",
                                    checkpoint_path=Path(directory) / "c.json")

    def test_fetches_a_single_month_and_writes_rows(self):
        start = datetime(2024, 1, 15, tzinfo=timezone.utc)
        end = datetime(2024, 1, 20, tzinfo=timezone.utc)
        payload = {"feed": [{"time_published": "20240116T120000", "title": "Headline",
                             "source": "Wire", "url": "https://example.com/one"}]}
        result, rows, calls, _ = self._run(["NVDA"], [payload], start_date=start, end_date=end)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["added_rows"], 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["symbol"], rows[0]["headline"]), ("NVDA", "Headline"))
        self.assertIn("NEWS_SENTIMENT", calls[0])
        self.assertIn("tickers=NVDA", calls[0])

    def test_stops_at_the_daily_limit_without_marking_remaining_as_done(self):
        start = datetime(2023, 12, 1, tzinfo=timezone.utc)
        end = datetime(2024, 3, 1, tzinfo=timezone.utc)
        result, rows, calls, _ = self._run(["NVDA"], [{"feed": []}] * 10,
                                           start_date=start, end_date=end, daily_limit=2)
        self.assertEqual(result["status"], "rate_limited")
        self.assertEqual(len(calls), 2)
        self.assertGreater(result["remaining"], 0)

    def test_provider_rate_limit_stops_immediately_and_redacts_key(self):
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 3, 1, tzinfo=timezone.utc)
        response = {"Information": "key test-key reached 25 requests per day rate limit"}
        result, _, calls, events = self._run(["NVDA"], [response] * 3,
                                            start_date=start, end_date=end)
        self.assertEqual(result["status"], "rate_limited")
        self.assertEqual(len(calls), 1)
        self.assertNotIn("test-key", " ".join(str(event) for event in events))

    def test_configured_archive_and_checkpoint_are_shared_with_terminal(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "alphavantage_news.csv"
            with patch.dict("os.environ", {"ALPHA_VANTAGE_NEWS_PATH": str(archive)}):
                self.assertEqual(default_archive_path(), archive)
                self.assertEqual(default_checkpoint_path(), archive.with_name("av_checkpoint.json"))

    def test_second_run_skips_already_checkpointed_past_months(self):
        # Two months in range: December (ends before end_date's month, so it
        # is "past") and January (end_date falls inside it, so it is
        # "current" and always re-fetched regardless of the checkpoint).
        start = datetime(2023, 12, 15, tzinfo=timezone.utc)
        end = datetime(2024, 1, 10, tzinfo=timezone.utc)
        calls = []
        def requester(url):
            calls.append(url)
            return {"feed": []}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "a.csv"
            checkpoint = Path(directory) / "c.json"
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "test-key"}):
                refresh_archive(output_path=output, checkpoint_path=checkpoint, tickers=["NVDA"],
                                start_date=start, end_date=end, requester=requester, sleep=lambda _: None)
                self.assertEqual(len(calls), 2)
                calls.clear()
                refresh_archive(output_path=output, checkpoint_path=checkpoint, tickers=["NVDA"],
                                start_date=start, end_date=end, requester=requester, sleep=lambda _: None)
        # December is checkpointed and skipped; January (current) is redone.
        self.assertEqual(len(calls), 1)

    def test_prioritizes_tickers_with_no_data_over_current_month_refresh(self):
        # NVDA already has December checkpointed (i.e. some history); AAPL
        # has nothing at all. With only 1 call of daily budget, AAPL's
        # untouched backlog should be fetched before NVDA's current-month
        # re-fetch, even though NVDA sorts first alphabetically.
        start = datetime(2023, 12, 15, tzinfo=timezone.utc)
        end = datetime(2024, 1, 10, tzinfo=timezone.utc)
        calls = []
        def requester(url):
            calls.append(url)
            return {"feed": []}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "a.csv"
            checkpoint = Path(directory) / "c.json"
            checkpoint.write_text('[["NVDA", "2023-12"]]', encoding="utf-8")
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "test-key"}):
                refresh_archive(output_path=output, checkpoint_path=checkpoint,
                                tickers=["NVDA", "AAPL"], start_date=start, end_date=end,
                                daily_limit=1, requester=requester, sleep=lambda _: None)
        self.assertIn("tickers=AAPL", calls[0])

    def test_current_month_is_purged_and_overwritten_not_appended(self):
        now = datetime.now(timezone.utc)
        start = now.replace(day=1)
        first = {"feed": [{"time_published": now.strftime("%Y%m%dT%H%M%S"), "title": "Old",
                           "source": "Wire", "url": "https://example.com/old"}]}
        second = {"feed": [{"time_published": now.strftime("%Y%m%dT%H%M%S"), "title": "New",
                            "source": "Wire", "url": "https://example.com/new"}]}
        calls = []
        def requester(url):
            calls.append(url)
            return first if len(calls) == 1 else second
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "a.csv"
            checkpoint = Path(directory) / "c.json"
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "test-key"}):
                refresh_archive(output_path=output, checkpoint_path=checkpoint, tickers=["NVDA"],
                                start_date=start, end_date=now, requester=requester, sleep=lambda _: None)
                refresh_archive(output_path=output, checkpoint_path=checkpoint, tickers=["NVDA"],
                                start_date=start, end_date=now, requester=requester, sleep=lambda _: None)
            with output.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
        self.assertEqual(len(calls), 2)
        self.assertEqual([row["headline"] for row in rows], ["New"])


if __name__ == "__main__":
    unittest.main()
