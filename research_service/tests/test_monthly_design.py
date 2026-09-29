"""The monthly study design: month-end anchors, 20-session horizon, 30-day news window."""
import csv
import dataclasses
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from types import SimpleNamespace

from fastapi.testclient import TestClient

from research_service.app import create_app
from research_service.data import validate_dataset
from research_service.errors import PreflightError
from research_service.web.context import JobInput
from research_service.web.jobs import prepare
from research_service.engine import Engine
from research_service.reporting import study_report
from research_service.storage import Store
from research_service.tests.test_workflow import fake_model, fixture

from research_service.collect import reusable_snapshot
from research_service.data import _alpha_vantage_cached_news, _fnspid_news
from research_service.demo import DEMO_ANALYSIS_DATE, demo_dataset
from research_service.protocol import (DESIGNS, MONTH_END_DATES, MONTHLY_VERSION, QUARTER_DATES, STUDY_TICKERS,
                                       StudyProtocol, cases, protocol_is_current, validate_case)
from research_service.readiness import coverage
from research_service.reporting import _primary_rows
from research_service.splits import classify_analysis_date


class MonthlyProtocolTests(unittest.TestCase):
    def test_month_end_dates_cover_2021_to_2025(self):
        self.assertEqual(len(MONTH_END_DATES), 60)
        self.assertEqual((MONTH_END_DATES[0], MONTH_END_DATES[-1]), ("2021-01-31", "2025-12-31"))
        self.assertIn("2024-02-29", MONTH_END_DATES)
        self.assertTrue(set(QUARTER_DATES) <= set(MONTH_END_DATES))
        self.assertEqual(len(cases(design="monthly")), 540)
        self.assertEqual(len(cases()), 180)

    def test_monthly_protocol_scales_the_quarterly_design(self):
        monthly = StudyProtocol.monthly()
        self.assertEqual((monthly.version, monthly.design), (MONTHLY_VERSION, "monthly"))
        self.assertEqual((monthly.primary_horizon, monthly.horizons, monthly.news_window_days), (20, (10, 20, 30), 30))
        self.assertEqual(monthly.analysis_dates, MONTH_END_DATES)
        quarterly = StudyProtocol()
        self.assertEqual((quarterly.design, quarterly.primary_horizon, quarterly.horizons, quarterly.news_window_days),
                         ("quarterly", 60, (30, 60, 90), 90))
        self.assertNotEqual(monthly.fingerprint, quarterly.fingerprint)

    def test_design_and_version_cannot_be_mixed(self):
        with self.assertRaises(ValueError):
            StudyProtocol(design="monthly")
        with self.assertRaises(ValueError):
            StudyProtocol(version=MONTHLY_VERSION)
        with self.assertRaises(ValueError):  # the monthly version with the quarterly 60-session horizon
            StudyProtocol(version=MONTHLY_VERSION, design="monthly")

    def test_quarterly_hash_is_unchanged_by_the_design_field(self):
        protocol = StudyProtocol()
        legacy = dataclasses.asdict(protocol)
        del legacy["design"]
        expected = hashlib.sha256(json.dumps(legacy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(protocol.fingerprint, expected)

    def test_saved_protocols_round_trip_and_are_current_for_their_own_design(self):
        monthly = dataclasses.asdict(StudyProtocol.monthly())
        self.assertTrue(protocol_is_current(monthly))
        self.assertTrue(protocol_is_current(dataclasses.asdict(StudyProtocol())))
        old = dataclasses.asdict(StudyProtocol())
        old.pop("design")
        old["version"] = "v3-0927.2"
        self.assertFalse(protocol_is_current(old))
        self.assertFalse(protocol_is_current({**monthly, "version": "v3-0929.1"}))

    def test_case_validation_uses_the_design_anchor_set(self):
        validate_case("AAPL", "2021-01-31", "monthly")
        validate_case("AAPL", "2021-03-31", "monthly")
        validate_case("AAPL", "2021-03-31", "quarterly")
        with self.assertRaises(ValueError):
            validate_case("AAPL", "2021-01-31", "quarterly")
        with self.assertRaises(ValueError):
            validate_case("AAPL", "2021-01-30", "monthly")
        with self.assertRaises(ValueError):
            validate_case("AAPL", "2021-01-31", "weekly")

    def test_month_ends_get_a_temporal_split(self):
        self.assertEqual(classify_analysis_date("2021-01-31"), "training")
        self.assertEqual(classify_analysis_date("2024-05-31"), "validation")
        self.assertEqual(classify_analysis_date("2025-11-30"), "test")
        self.assertEqual(classify_analysis_date("2021-01-30"), "live")

    def test_universe_is_unchanged(self):
        self.assertEqual(len(STUDY_TICKERS), 9)
        self.assertEqual(DESIGNS["monthly"]["primary_horizon"] * 3, DESIGNS["quarterly"]["primary_horizon"])


class NewsWindowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def write(self, name, header, rows):
        path = self.root / name
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(rows)
        return str(path)

    def test_fnspid_window_follows_the_requested_length(self):
        path = self.write("fnspid.csv", ["date", "symbol", "headline", "url"], [
            ["2021-03-25", "AAPL", "inside both windows", "https://example.com/a"],
            ["2021-02-15", "AAPL", "only in the 90-day window", "https://example.com/b"],
            ["2021-03-31", "AAPL", "analysis day is excluded", "https://example.com/c"],
        ])
        long_window = {item["headline"] for item in _fnspid_news(path, "AAPL", "2021-03-31")}
        short_window = {item["headline"] for item in _fnspid_news(path, "AAPL", "2021-03-31", window_days=30)}
        self.assertEqual(long_window, {"inside both windows", "only in the 90-day window"})
        self.assertEqual(short_window, {"inside both windows"})

    def test_alpha_vantage_archive_window_follows_the_requested_length(self):
        path = self.write("alpha.csv", ["date", "symbol", "headline", "publisher", "url"], [
            ["20210325T101500", "AAPL", "inside both windows", "P", "https://example.com/a"],
            ["20210215T101500", "AAPL", "only in the 90-day window", "P", "https://example.com/b"],
        ])
        long_window = {item["headline"] for item in _alpha_vantage_cached_news(path, "AAPL", "2021-03-31")}
        short_window = {item["headline"] for item in _alpha_vantage_cached_news(path, "AAPL", "2021-03-31", window_days=30)}
        self.assertEqual(long_window, {"inside both windows", "only in the 90-day window"})
        self.assertEqual(short_window, {"inside both windows"})


class DatasetDesignTests(unittest.TestCase):
    def test_a_month_end_that_is_also_a_quarter_end_keeps_two_snapshots(self):
        class Store:
            def __init__(self, datasets):
                self._datasets = datasets

            def datasets(self):
                return self._datasets

        def snapshot(key, rules):
            return {"id": key, "ticker": "AAPL", "kind": "historical", "requested_analysis_date": "2021-03-31",
                    "coverage": {"research_ready": True}, "collection_rules": rules}

        uncapped = {"version": "point-in-time-input-v2", "news_item_limit": "uncapped"}
        store = Store([snapshot("capped-legacy", {"version": "point-in-time-input-v2"}),
                       snapshot("quarterly", uncapped),
                       snapshot("monthly", {**uncapped, "design": "monthly", "news_window_days": 30})])
        self.assertEqual(reusable_snapshot(store, "AAPL", "2021-03-31")["id"], "quarterly")
        self.assertEqual(reusable_snapshot(store, "AAPL", "2021-03-31", "monthly")["id"], "monthly")
        # A snapshot whose news was capped at collection time is never reused.
        self.assertIsNone(reusable_snapshot(Store([snapshot("capped-legacy", {"version": "x"})]), "AAPL", "2021-03-31"))

    def test_readiness_follows_the_dataset_design(self):
        data = demo_dataset()
        quarterly = coverage(data, DEMO_ANALYSIS_DATE)
        self.assertEqual(set(quarterly["horizons"]), {"30", "60", "90"})
        monthly_data = {**data, "collection_rules": {**data["collection_rules"], "design": "monthly"}}
        monthly = coverage(monthly_data, DEMO_ANALYSIS_DATE)
        self.assertEqual(set(monthly["horizons"]), {"10", "20", "30"})
        self.assertEqual(monthly["base_rate_windows"], quarterly["base_rate_windows"] * 3)
        self.assertTrue(monthly["backtest_ready"])


class ReportingDesignTests(unittest.TestCase):
    def test_primary_rows_use_the_reports_primary_horizon(self):
        rows = [{"group": "D", "horizon": horizon, "cost_model": "corwin_schultz", "decision_layer": "candidate",
                 "portfolio_basis": "all"} for horizon in (10, 20, 30, 60)]
        self.assertEqual([row["horizon"] for row in _primary_rows({"summary": rows, "primary_horizon": 20})], [20])
        self.assertEqual([row["horizon"] for row in _primary_rows({"summary": rows})], [60])


class MonthlyWorkflowTests(unittest.TestCase):
    """A monthly job runs end to end and is scored on its own 20-session horizon."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        data = validate_dataset(fixture())
        data["collection_rules"] = {"version": "unit-test", "design": "monthly", "news_window_days": 30}
        self.dataset_id = self.store.add_dataset(data)
        self.protocol = StudyProtocol.monthly(dataset_kind="synthetic", bootstrap_replicates=199)

    def test_monthly_job_completes_with_monthly_horizons(self):
        job = self.store.create({"ticker": "NVDA", "analysis_date": "2024-12-31", "dataset_id": self.dataset_id,
                                 "protocol": dataclasses.asdict(self.protocol),
                                 "protocol_hash": self.protocol.fingerprint})
        engine = Engine(self.store, fake_model)
        for _ in range(40):
            self.store.save_step(job["id"], engine.advance(job))
            job = self.store.get(job["id"])
            if job["status"] == "complete":
                break
        self.assertEqual(job["status"], "complete")
        self.assertEqual({row["horizon"] for row in job["state"]["cases"]}, {10, 20, 30})
        primary = {row["horizon"] for row in job["state"]["cases"] if row["endpoint"] == "primary"}
        self.assertEqual(primary, {20})
        report = study_report([job], formal_only=False)
        self.assertEqual((report["primary_horizon"], report["design"]), (20, "monthly"))
        self.assertTrue(all(row["horizon"] == 20 for row in _primary_rows(report)))
        self.assertIn("horizon=20", " ".join(report["conventions"]))

    def test_api_creates_a_monthly_job_with_its_own_protocol(self):
        with TestClient(create_app(self.store, fake_model, start_worker=False)) as client:
            response = client.post("/api/jobs", json={"dataset_id": self.dataset_id, "analysis_date": "2024-12-31",
                                                      "design": "monthly", "model": "test-model"})
        self.assertEqual(response.status_code, 200, response.text)
        config = response.json()["config"]
        self.assertEqual((config["protocol"]["design"], config["protocol"]["version"]), ("monthly", MONTHLY_VERSION))
        self.assertEqual(config["protocol"]["horizons"], [10, 20, 30])
        self.assertEqual(config["protocol_hash"], StudyProtocol.monthly(
            model="test-model", dataset_kind="synthetic").fingerprint)

    def test_a_dataset_built_for_the_other_design_is_refused(self):
        class Store:
            @staticmethod
            def dataset(_key):
                return {"ticker": "AAPL", "kind": "historical", "requested_analysis_date": "2024-12-31",
                        "collection_rules": {"version": "point-in-time-input-v2"}}

        payload = JobInput(dataset_id="quarterly-snapshot", analysis_date="2024-12-31", design="monthly")
        with self.assertRaises(PreflightError) as caught:
            prepare(SimpleNamespace(store=Store, demo_mode=False, injected_model_call=True, demo_model_id=""), payload)
        self.assertEqual(caught.exception.reason, "design_mismatch")


if __name__ == "__main__":
    unittest.main()
