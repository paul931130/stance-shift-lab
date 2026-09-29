from datetime import date, datetime, timedelta, timezone
import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from research_service.data import (_alpha_vantage_cached_news, _alpha_vantage_news, _chart_rows,
                                   _base_rates, _deduplicate_news, _fnspid_news, check_sentiment_sources,
                                   download_prices, fetch_fundamental, fetch_sentiment)
from scripts.prepare_fnspid_news import filter_fnspid


def chart_payload(count=70):
    start = datetime(2024, 1, 2, tzinfo=timezone.utc)
    timestamps = [int((start + timedelta(days=index)).timestamp()) for index in range(count)]
    closes = [100.0 + index for index in range(count)]
    return {"chart": {"result": [{
        "timestamp": timestamps,
        "indicators": {
            "quote": [{
                "open": [value - 1 for value in closes],
                "high": [value + 2 for value in closes],
                "low": [value - 2 for value in closes],
                "close": closes,
            }],
            "adjclose": [{"adjclose": [value / 2 for value in closes]}],
        },
    }], "error": None}}


class BaseRateWindowTests(unittest.TestCase):
    def test_sixty_session_windows_use_sixty_return_intervals(self):
        history = [{"close": 100.0 + index} for index in range(480)]
        result = _base_rates(history, 60, .2, .5)
        self.assertEqual(result["windows"], 7)
        self.assertFalse(result["calibration_ready"])

        history.append({"close": 580.0})
        result = _base_rates(history, 60, .2, .5)
        self.assertEqual(result["windows"], 8)
        self.assertTrue(result["calibration_ready"])


class EmptyFrame:
    empty = True


class YahooFallbackTests(unittest.TestCase):
    def test_chart_rows_adjusts_all_ohlc_on_the_same_basis(self):
        row = _chart_rows(chart_payload(1))[0]
        self.assertEqual(row["close"], 50.0)
        self.assertEqual(row["open"], 49.5)
        self.assertEqual(row["high"], 51.0)
        self.assertEqual(row["low"], 49.0)

    @patch("yfinance.Ticker")
    def test_query1_chart_is_used_when_yfinance_query2_is_empty(self, ticker):
        ticker.return_value.history.return_value = EmptyFrame()
        dataset = download_prices("NVDA", "2025-12-31", chart_requester=lambda url, headers: chart_payload())
        self.assertEqual(len(dataset["prices"]), 70)
        self.assertIn("query1", dataset["source"])
        self.assertIn("本次行情下載路徑", dataset["limitations"][-1])
        self.assertEqual(ticker.return_value.history.call_args.kwargs["start"],
                         (date.fromisoformat("2025-12-31") - timedelta(days=900)).isoformat())
        self.assertEqual(dataset["collection_rules"]["price_history_calendar_days"], 900)

    @patch("research_service.data.time.sleep", return_value=None)
    @patch("yfinance.Ticker")
    def test_all_endpoint_failures_return_an_actionable_error(self, ticker, _sleep):
        ticker.return_value.history.side_effect = ConnectionError("query2 unavailable")

        def unavailable(_url, _headers):
            raise ConnectionError("query1 unavailable")

        with self.assertRaisesRegex(ValueError, "檢查網路後重試"):
            download_prices("NVDA", "2025-12-31", chart_requester=unavailable)


class SecFundamentalTests(unittest.TestCase):
    def test_selector_builds_same_period_comparisons_and_exact_ratio(self):
        def fact(start, end, value, accession, filed, form="10-Q", fp="Q3"):
            return {"start": start, "end": end, "val": value, "accn": accession,
                    "filed": filed, "form": form, "fp": fp}

        current = fact("2024-07-01", "2024-09-29", 30_000_000_000,
                       "0001045810-24-000100", "2024-11-20")
        prior = fact("2023-07-03", "2023-10-01", 18_000_000_000,
                     "0001045810-23-000090", "2023-11-21")
        assets = {"end": "2024-09-29", "val": 90_000_000_000,
                  "accn": current["accn"], "filed": current["filed"], "form": "10-Q", "fp": "Q3"}
        liabilities = {**assets, "val": 30_000_000_000}
        payload = {"facts": {"us-gaap": {
            "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [prior, current]}},
            "NetIncomeLoss": {"units": {"USD": [
                fact("2023-07-03", "2023-10-01", 9_000_000_000, prior["accn"], prior["filed"]),
                fact("2024-07-01", "2024-09-29", 15_000_000_000, current["accn"], current["filed"]),
            ]}},
            "Assets": {"units": {"USD": [assets]}},
            "Liabilities": {"units": {"USD": [liabilities]}},
        }}}
        with patch.dict("os.environ", {"SEC_USER_AGENT": "Research test@example.com"}):
            items, note = fetch_fundamental("NVDA", "2024-12-31", lambda _url, _headers: payload)
        self.assertEqual(note, "")
        self.assertTrue(all(item["comparative"] for item in items))
        revenue = next(item for item in items if item["metric"] == "Revenue")
        self.assertEqual((revenue["current_value"], revenue["prior_value"]),
                         (30_000_000_000, 18_000_000_000))
        self.assertAlmostEqual(revenue["change_pct"], 66.666667, places=6)
        ratio = next(item for item in items if item["metric"] == "LiabilitiesToAssets")
        self.assertAlmostEqual(ratio["ratio_pct"], 33.333333, places=6)
        self.assertIn("current=30000000000 USD", revenue["claim"])

    def test_year_to_date_cash_flow_and_negative_base_sign(self):
        def fact(start, end, val, accn, filed, fp):
            return {"start": start, "end": end, "val": val, "accn": accn, "filed": filed, "form": "10-Q", "fp": fp}

        q1 = fact("2024-01-01", "2024-03-31", -154_000_000_000, "q1-24", "2024-05-01", "Q1")
        q1_prior = fact("2023-01-01", "2023-03-31", -111_000_000_000, "q1-23", "2023-05-01", "Q1")
        # The Q3 10-Q reports cash flow only for the nine months to date.
        ytd = fact("2024-01-01", "2024-09-30", -60_000_000_000, "q3-24", "2024-10-30", "Q3")
        ytd_prior = fact("2023-01-01", "2023-09-30", -40_000_000_000, "q3-23", "2023-10-30", "Q3")
        payload = {"facts": {"us-gaap": {"NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [
            q1_prior, q1, ytd_prior, ytd]}}}}}
        with patch.dict("os.environ", {"SEC_USER_AGENT": "Research test@example.com"}):
            items, _ = fetch_fundamental("JPM", "2024-12-31", lambda _url, _headers: payload)
        cash = next(item for item in items if item["metric"] == "OperatingCashFlow")
        self.assertEqual((cash["current_accession"], cash["period_days"]), ("q3-24", 273))
        self.assertAlmostEqual(cash["change_pct"], -50.0, places=6)  # worse, so negative
        self.assertIn("period_days=273", cash["claim"])

    def test_bank_revenue_uses_net_of_interest_expense_quarters(self):
        def fact(start, end, val, accn, filed, form="10-Q"):
            return {"start": start, "end": end, "val": val, "accn": accn, "filed": filed, "form": form}

        payload = {"facts": {"us-gaap": {
            "Revenues": {"units": {"USD": [
                fact("2022-01-01", "2022-12-31", 128_000_000_000, "k-22", "2023-02-21", "10-K"),
                fact("2023-01-01", "2023-12-31", 158_000_000_000, "k-23", "2024-02-16", "10-K")]}},
            "RevenuesNetOfInterestExpense": {"units": {"USD": [
                fact("2023-07-01", "2023-09-30", 40_000_000_000, "q3-23", "2023-10-30"),
                fact("2024-07-01", "2024-09-30", 43_000_000_000, "q3-24", "2024-10-30")]}},
        }}}
        with patch.dict("os.environ", {"SEC_USER_AGENT": "Research test@example.com"}):
            items, _ = fetch_fundamental("JPM", "2024-12-31", lambda _url, _headers: payload)
        revenue = next(item for item in items if item["metric"] == "Revenue")
        self.assertEqual(revenue["current_period"], "2024-09-30")

    def test_finbert_scores_more_than_one_hundred_headlines(self):
        import tempfile
        from research_service.data import score_sentiment_finbert
        from research_service.demo import demo_dataset

        data = demo_dataset()
        data["evidence"] = [item for item in data["evidence"] if item["domain"] != "sentiment"] + [
            {"evidence_id": f"n{i}", "domain": "sentiment", "claim": f"Headline {i}", "headline": f"Headline {i}",
             "available_at": "2024-12-01", "source": f"https://example.com/{i}"} for i in range(150)]
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"RESEARCH_DATA_DIR": directory}):
            scored = score_sentiment_finbert(
                data, requester=lambda text: [{"label": "positive", "score": 0.6}, {"label": "negative", "score": 0.1},
                                              {"label": "neutral", "score": 0.3}])
        sentiment = [item for item in scored["evidence"] if item["domain"] == "sentiment"]
        self.assertEqual(len(sentiment), 150)
        self.assertTrue(all(item.get("sentiment_score") is not None for item in sentiment))

    def test_refresh_news_carries_live_api_headlines_missing_from_local_files(self):
        import tempfile
        from research_service.collect import refresh_news
        from research_service.demo import demo_dataset
        from research_service.storage import Store

        live = [{"evidence_id": f"av-{i}", "domain": "sentiment", "claim": f"Live {i}", "headline": f"Live {i}",
                 "available_at": "2024-12-01", "source": f"https://example.com/live{i}",
                 "source_type": "alpha_vantage_news_sentiment"} for i in range(5)]
        local = [{"evidence_id": "fn-1", "domain": "sentiment", "claim": "Local", "headline": "Local",
                  "available_at": "2024-12-02", "source": "https://example.com/local", "source_type": "FNSPID"},
                 {**live[0], "evidence_id": "dup-of-live-0", "source_type": "alpha_vantage_news_cache"}]
        base = {**demo_dataset(), "kind": "historical", "requested_analysis_date": "2024-12-31"}
        base["evidence"] = [item for item in base["evidence"] if item["domain"] != "sentiment"] + live
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            old_id = store.add_dataset(base)
            with patch("research_service.collect.fetch_sentiment", return_value=(local, "")), \
                 patch("research_service.collect.score_sentiment_finbert", side_effect=lambda data, progress=None: data):
                result = refresh_news(store, old_id)
        self.assertEqual((result["local_items"], result["carried_live_items"]), (2, 5))
        self.assertEqual(result["items"], 6)  # live-0 and its local copy are one article

    def test_uncapped_news_keeps_every_headline_after_deduplication(self):
        from research_service.data import fetch_sentiment

        rows = [{"evidence_id": f"n{i}", "domain": "sentiment", "claim": f"Headline {i}", "headline": f"Headline {i}",
                 "available_at": f"2024-12-{1 + i % 28:02d}", "source": f"https://example.com/a{i}",
                 "source_type": "FNSPID"} for i in range(150)]
        with patch.dict("os.environ", {"FNSPID_NEWS_PATH": "x.csv", "ALPHA_VANTAGE_NEWS_PATH": "",
                                       "ALPHA_VANTAGE_API_KEY": ""}),              patch("research_service.data._resolve_alpha_vantage_cache_path", return_value=""),              patch("research_service.data._fnspid_news", return_value=rows):
            uncapped, _ = fetch_sentiment("NVDA", "2024-12-31", allow_live=False, item_limit=None)
            legacy, _ = fetch_sentiment("NVDA", "2024-12-31", allow_live=False)
        self.assertEqual(len(uncapped), 150)
        self.assertEqual(len(legacy), 100)

    def test_refresh_news_replaces_only_sentiment_and_marks_uncapped(self):
        import tempfile
        from research_service.collect import refresh_news
        from research_service.demo import demo_dataset
        from research_service.storage import Store

        base = {**demo_dataset(), "kind": "historical", "requested_analysis_date": "2024-12-31"}
        headlines = [{"evidence_id": f"news-{i}", "domain": "sentiment", "claim": f"Headline {i}",
                      "headline": f"Headline {i}", "available_at": "2024-12-01", "source": "https://example.com/",
                      "evidence_scope": "target"} for i in range(60)]
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            old_id = store.add_dataset(base)
            with patch("research_service.collect.fetch_sentiment", return_value=(headlines, "")) as fetch,                  patch("research_service.collect.score_sentiment_finbert", side_effect=lambda data, progress=None: data):
                result = refresh_news(store, old_id)
            fresh = store.dataset(result["id"])
        self.assertEqual(fetch.call_args.kwargs["item_limit"], None)
        self.assertFalse(fetch.call_args.kwargs["allow_live"])
        self.assertEqual(result["items"], 60)
        self.assertEqual(fresh["parent_dataset_id"], old_id)
        self.assertEqual(fresh["collection_rules"]["news_item_limit"], "uncapped")
        self.assertEqual([item["evidence_id"] for item in fresh["evidence"] if item["domain"] == "sentiment"],
                         [item["evidence_id"] for item in headlines])

        def others(data):
            return [item for item in data["evidence"] if item["domain"] != "sentiment"]

        self.assertEqual(others(fresh), others(base))
        self.assertEqual(fresh["prices"], base["prices"])

    def test_refresh_fundamentals_keeps_other_domains_and_links_parent(self):
        import tempfile
        from research_service.collect import refresh_fundamentals
        from research_service.demo import demo_dataset
        from research_service.storage import Store

        base = {**demo_dataset(), "kind": "historical", "requested_analysis_date": "2024-12-31"}
        new_fact = {"evidence_id": "sec-comparison-new", "domain": "fundamental", "claim": "Revenue: new",
                    "available_at": "2024-11-20", "source": "https://www.sec.gov/", "comparative": True}
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            old_id = store.add_dataset(base)
            with patch("research_service.collect.fetch_fundamental", return_value=([new_fact], "")):
                result = refresh_fundamentals(store, old_id, requester=lambda *_: {})
            fresh = store.dataset(result["id"])
        self.assertEqual(fresh["parent_dataset_id"], old_id)
        self.assertEqual([item["evidence_id"] for item in fresh["evidence"] if item["domain"] == "fundamental"],
                         ["sec-comparison-new"])
        def others(data):
            return [item for item in data["evidence"] if item["domain"] != "fundamental"]

        self.assertEqual(others(fresh), others(base))
        self.assertEqual(fresh["prices"], base["prices"])

    def test_selector_falls_back_to_non_directional_point_facts(self):
        payload = {"facts": {"us-gaap": {"Assets": {"units": {"USD": [{
            "end": "2024-09-29", "val": 90_000_000_000,
            "accn": "0001045810-24-000100", "filed": "2024-11-20", "form": "10-Q",
        }]}}}}}
        with patch.dict("os.environ", {"SEC_USER_AGENT": "Research test@example.com"}):
            items, _ = fetch_fundamental("NVDA", "2024-12-31", lambda _url, _headers: payload)
        self.assertEqual(len(items), 1)
        self.assertFalse(items[0]["comparative"])


class NewsSourceTests(unittest.TestCase):
    def alpha_payload(self):
        return {"feed": [{
            "time_published": "20241220T134500", "title": "Pre-cutoff NVIDIA report",
            "summary": "Verified test summary", "url": "https://example.com/one", "source": "Example",
            "ticker_sentiment": [{"ticker": "NVDA", "relevance_score": "0.90", "ticker_sentiment_score": "0.42",
                                  "ticker_sentiment_label": "Bullish"}],
        }, {
            "time_published": "20241231T010000", "title": "Same-day excluded",
            "url": "https://example.com/future", "ticker_sentiment": [],
        }, {
            "time_published": "20241219T010000", "title": "Broad market story without NVDA relevance",
            "url": "https://example.com/broad", "ticker_sentiment": [{"ticker": "AAPL", "relevance_score": "0.9"}],
        }]}

    def test_alpha_vantage_query_and_point_in_time_filter(self):
        calls = []
        def requester(url):
            calls.append(url)
            return self.alpha_payload()
        with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "test-key"}):
            items, stats = _alpha_vantage_news("NVDA", "2024-12-31", requester)
        query = parse_qs(urlparse(calls[0]).query)
        self.assertEqual(query["function"], ["NEWS_SENTIMENT"])
        self.assertEqual(query["tickers"], ["NVDA"])
        self.assertEqual(query["time_to"], ["20241230T2359"])
        self.assertEqual(query["sort"], ["RELEVANCE"])
        self.assertEqual(query["limit"], ["200"])
        self.assertEqual(len(items), 1)
        self.assertEqual((items[0]["available_at"], items[0]["sentiment_score"]), ("2024-12-20", .42))
        self.assertEqual(stats, {"fetched": 3, "dropped_missing_relevance": 1, "dropped_low_relevance": 0, "kept": 1})

    def test_alpha_relevance_floor_drops_low_and_unscored_articles(self):
        payload = {"feed": [
            {"time_published":"20241220T000000","title":"NVIDIA direct","url":"https://e/x", "ticker_sentiment":[{"ticker":"NVDA","relevance_score":"0.9"}]},
            {"time_published":"20241220T000000","title":"NVIDIA broad","url":"https://e/y", "ticker_sentiment":[{"ticker":"NVDA","relevance_score":"0.2"}]},
            {"time_published":"20241220T000000","title":"NVIDIA missing","url":"https://e/z", "ticker_sentiment":[{"ticker":"NVDA"}]},
        ]}
        with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "test-key"}):
            items, stats = _alpha_vantage_news("NVDA", "2024-12-31", lambda _url: payload)
        self.assertEqual([item["headline"] for item in items], ["NVIDIA direct"])
        self.assertEqual(stats["dropped_low_relevance"], 1)
        self.assertEqual(stats["dropped_missing_relevance"], 1)

    def test_cross_provider_news_deduplicates_canonical_url(self):
        items, aliases = _deduplicate_news([
            {"evidence_id":"alpha-1", "available_at":"2024-12-20", "claim":"Same headline",
             "headline":"Same headline", "source":"https://www.example.com/story?utm_source=x", "source_type":"alpha"},
            {"evidence_id":"fnspid-1", "available_at":"2024-12-20", "claim":"Same headline",
             "headline":"Same headline", "source":"http://example.com/story", "source_type":"FNSPID"},
        ])
        self.assertEqual(len(items), 1)
        self.assertEqual(set(items[0]["source_types"]), {"alpha", "FNSPID"})
        self.assertEqual(len(aliases), 1)

    def test_fnspid_schema_filter_and_preparation_script(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "original.csv"
            filtered = Path(directory) / "filtered.csv"
            fields = ["Date", "Article_title", "Stock_symbol", "Url", "Publisher"]
            rows = [
                {"Date":"2024-12-20 09:00:00","Article_title":"NVIDIA news","Stock_symbol":"NVDA","Url":"https://example.com/nvda","Publisher":"P"},
                {"Date":"2024-12-31 09:00:00","Article_title":"Same day","Stock_symbol":"NVDA","Url":"https://example.com/same","Publisher":"P"},
                {"Date":"2024-12-19 09:00:00","Article_title":"Apple news","Stock_symbol":"AAPL","Url":"https://example.com/aapl","Publisher":"P"},
            ]
            with source.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            result = filter_fnspid(source, filtered, ["NVDA"], "2024-01-01", "2025-01-01")
            self.assertEqual((result["rows"], result["by_ticker"]["NVDA"]), (2, 2))
            items = _fnspid_news(filtered, "NVDA", "2024-12-31")
            self.assertEqual(len(items), 1)
            self.assertEqual((items[0]["claim"], items[0]["publisher"]), ("NVIDIA news", "P"))
            self.assertEqual((items[0]["relevance_score"], items[0]["relevance_basis"]), (1.0, "fnspid_per_ticker_file"))
            lowercase = Path(directory) / "filtered-lowercase.csv"
            with lowercase.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["date", "symbol", "headline", "publisher", "url"])
                writer.writeheader()
                writer.writerow({"date":"2024-12-20 09:00:00 UTC", "symbol":"NVDA",
                    "headline":"Filtered headline", "publisher":"Publisher", "url":"https://example.com/lower"})
            lowercase_items = _fnspid_news(lowercase, "NVDA", "2024-12-31")
            self.assertEqual((len(lowercase_items), lowercase_items[0]["claim"]), (1, "Filtered headline"))
            compacted = Path(directory) / "compacted.csv"
            compact_result = filter_fnspid(lowercase, compacted, ["NVDA"], "2024-01-01", "2025-01-01")
            self.assertEqual(compact_result["rows"], 1)
            with compacted.open("r", encoding="utf-8-sig", newline="") as handle:
                self.assertEqual(csv.DictReader(handle).fieldnames,
                    ["Date", "Article_title", "Stock_symbol", "Url", "Publisher"])

    def test_automatic_news_combines_configured_sources_and_reports_live_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "fnspid.csv"
            with source.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["Date","Article_title","Stock_symbol","Url"])
                writer.writeheader()
                writer.writerow({"Date":"2024-12-15","Article_title":"FNSPID item","Stock_symbol":"NVDA","Url":"https://example.com/two"})
            env = {"ALPHA_VANTAGE_API_KEY":"test-key", "ALPHA_VANTAGE_NEWS_PATH":"",
                   "FNSPID_NEWS_PATH":str(source)}
            with patch.dict("os.environ", env, clear=False):
                items, note = fetch_sentiment("NVDA", "2024-12-31", lambda _url: self.alpha_payload())
                checks = check_sentiment_sources("NVDA", "2024-12-31", lambda _url: self.alpha_payload())
        self.assertEqual(len(items), 2)
        self.assertIn("Alpha Vantage 取得", note)
        self.assertEqual(checks["alpha_vantage"]["status"], "ready")
        self.assertEqual(checks["fnspid"]["status"], "ready")
        # The local Alpha cache is an independent optional source.
        self.assertIn(checks["alpha_vantage_cache"]["status"], {"ready", "unconfigured"})

    def test_missing_optional_fnspid_keeps_alpha_news_available(self):
        with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY":"test-key", "ALPHA_VANTAGE_NEWS_PATH":"",
                                       "FNSPID_NEWS_PATH":"/missing/Stock_news.csv"}):
            items, note = fetch_sentiment("NVDA", "2024-12-31", lambda _url: self.alpha_payload())
            checks = check_sentiment_sources("NVDA", "2024-12-31", lambda _url: self.alpha_payload())
        self.assertEqual(len(items), 1)
        self.assertIn("FNSPID 檔案不存在", note)
        self.assertEqual(checks["fnspid"]["status"], "optional_missing")
        self.assertIn("不影響情緒資料", checks["fnspid"]["message"])

    def test_alpha_vantage_cache_reads_the_fetch_script_output_format(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "alphavantage_news.csv"
            with cache.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["date", "symbol", "headline", "publisher", "url"])
                writer.writeheader()
                writer.writerow({"date": "20241220T134500", "symbol": "NVDA",
                    "headline": "Cached NVIDIA report", "publisher": "Wire", "url": "https://example.com/cached"})
                writer.writerow({"date": "20241231T010000", "symbol": "NVDA",
                    "headline": "Same-day excluded", "publisher": "Wire", "url": "https://example.com/future"})
                writer.writerow({"date": "20241220T090000", "symbol": "AAPL",
                    "headline": "Different ticker", "publisher": "Wire", "url": "https://example.com/other"})
            items = _alpha_vantage_cached_news(str(cache), "NVDA", "2024-12-31")
        self.assertEqual(len(items), 1)
        self.assertEqual((items[0]["available_at"], items[0]["claim"]), ("2024-12-20", "Cached NVIDIA report"))
        self.assertEqual((items[0]["relevance_score"], items[0]["relevance_basis"]),
                         (1.0, "alpha_vantage_cache_per_ticker_file"))

    def test_alpha_vantage_cache_is_tried_before_spending_a_live_call(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "alphavantage_news.csv"
            with cache.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["date", "symbol", "headline", "publisher", "url"])
                writer.writeheader()
                writer.writerow({"date": "20241220T134500", "symbol": "NVDA",
                    "headline": "Cached NVIDIA report", "publisher": "Wire", "url": "https://example.com/cached"})
            live_calls = []
            def requester(url):
                live_calls.append(url)
                return self.alpha_payload()
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "test-key", "ALPHA_VANTAGE_NEWS_PATH": str(cache)}):
                items, note = fetch_sentiment("NVDA", "2024-12-31", requester)
        self.assertEqual(live_calls, [])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["source_type"], "alpha_vantage_news_cache")
        self.assertNotIn("Alpha Vantage 取得", note)

    def test_alpha_vantage_cache_miss_still_falls_back_to_the_live_call(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "alphavantage_news.csv"
            with cache.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["date", "symbol", "headline", "publisher", "url"])
                writer.writeheader()
                writer.writerow({"date": "20200101T000000", "symbol": "NVDA",
                    "headline": "Way too old to matter", "publisher": "Wire", "url": "https://example.com/old"})
            live_calls = []
            def requester(url):
                live_calls.append(url)
                return self.alpha_payload()
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "test-key", "ALPHA_VANTAGE_NEWS_PATH": str(cache)}):
                items, note = fetch_sentiment("NVDA", "2024-12-31", requester)
        self.assertEqual(len(live_calls), 1)
        self.assertIn("Alpha Vantage 取得", note)
        self.assertTrue(any(item["source_type"] == "alpha_vantage_news_sentiment" for item in items))

    def test_offline_news_mode_never_calls_live_alpha(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "empty.csv"
            cache.write_text("ticker,time_published,title,url,relevance_score\n", encoding="utf-8")
            with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "test-key",
                                             "ALPHA_VANTAGE_NEWS_PATH": str(cache),
                                             "FNSPID_NEWS_PATH": ""}):
                items, note = fetch_sentiment(
                    "NVDA", "2024-12-31", lambda _url: self.fail("live Alpha was called"),
                    allow_live=False)
        self.assertEqual(items, [])
        self.assertIn("離線新聞模式", note)

    def test_alpha_provider_limit_is_actionable_without_exposing_a_key(self):
        def limited(_url):
            return {"Information": "rate limited"}
        with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY":"secret-test-key",
                                       "ALPHA_VANTAGE_NEWS_PATH":"", "FNSPID_NEWS_PATH":""}):
            items, note = fetch_sentiment("NVDA", "2024-12-31", limited)
            checks = check_sentiment_sources("NVDA", "2024-12-31", limited)
        self.assertEqual(items, [])
        self.assertIn("已達流量限制", note)
        self.assertIn("已達流量限制", checks["alpha_vantage"]["message"])
        self.assertNotIn("secret-test-key", note + checks["alpha_vantage"]["message"])


if __name__ == "__main__":
    unittest.main()
