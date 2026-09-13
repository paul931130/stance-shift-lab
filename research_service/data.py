"""Validated point-in-time inputs; future prices never enter research reports."""
from __future__ import annotations

from datetime import date, timedelta, datetime, timezone
from decimal import Decimal, InvalidOperation
import csv
import hashlib
import json
import math
import os
import re
import time
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl
from urllib.request import Request, urlopen

from .protocol import COMPANY_NAMES, DOMAIN_NAMES


MIN_NEWS_RELEVANCE = .35
PRICE_HISTORY_CALENDAR_DAYS = 900
PRICE_FUTURE_CALENDAR_DAYS = 220


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def get_json(url, headers=None):
    with urlopen(Request(url, headers=headers or {}), timeout=30) as response:
        return json.load(response)


def score_sentiment_finbert(data, requester=None, progress=None):
    from .finbert import score
    return score(data, requester, progress)


def validate_dataset(data):
    if data.get("kind") not in ("historical", "synthetic"):
        raise ValueError("資料必須標示 kind: historical 或 synthetic")
    if not isinstance(data.get("source"), str) or not data["source"].strip():
        raise ValueError("必須記錄行情來源 source")
    if data.get("price_basis") != "adjusted_ohlc":
        raise ValueError("price_basis 必須為 adjusted_ohlc；OHLC 須使用相同還原基準")
    rows = data.get("prices", [])
    if not 61 <= len(rows) <= 10000:
        raise ValueError("行情須包含 61–10000 個交易日")
    previous = ""
    for row in rows:
        day = row["date"]
        date.fromisoformat(day)
        if day <= previous:
            raise ValueError("交易日必須嚴格遞增且不可重複")
        previous = day
        for key in ("open", "high", "low", "close"):
            if isinstance(row[key], bool) or not math.isfinite(float(row[key])) or float(row[key]) <= 0:
                raise ValueError("OHLC 必須為有限正數")
            row[key] = float(row[key])
        if row["low"] > min(row["open"], row["close"]) or row["high"] < max(row["open"], row["close"]) or row["low"] > row["high"]:
            raise ValueError(
                f"OHLC 高低價不一致（{day}: open={row['open']}, high={row['high']}, "
                f"low={row['low']}, close={row['close']}）"
            )
    evidence = data.get("evidence", [])
    if len(evidence) > 400:
        raise ValueError("每個資料集最多 400 筆摘要證據")
    ids = set()
    for item in evidence:
        for key in ("evidence_id", "domain", "claim", "source", "available_at"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ValueError(f"證據缺少 {key}")
        if item["domain"] not in DOMAIN_NAMES or item["evidence_id"] in ids:
            raise ValueError("證據領域錯誤或 ID 重複")
        if len(item["claim"]) > 4000 or len(item["source"]) > 2000:
            raise ValueError("證據摘要或來源過長")
        ids.add(item["evidence_id"])
        date.fromisoformat(item["available_at"])
        if item["domain"] == "macro" and not item.get("vintage_date"):
            raise ValueError("總經證據須提供 vintage_date")
        if item.get("vintage_date"):
            date.fromisoformat(item["vintage_date"])
            if item["vintage_date"] > item["available_at"]:
                raise ValueError("vintage_date 不可晚於 available_at")
    data["evidence"] = evidence
    return data


def _chart_rows(payload):
    """Convert Yahoo Chart output to one consistent adjusted-OHLC basis."""
    result = payload.get("chart", {}).get("result") or []
    if not result:
        error = payload.get("chart", {}).get("error") or {}
        raise ValueError(error.get("description") or "Yahoo Chart 未回傳結果")
    result = result[0]
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    quotes = indicators.get("quote") or []
    if not quotes:
        raise ValueError("Yahoo Chart 缺少 OHLC 欄位")
    quote = quotes[0]
    adjusted = (indicators.get("adjclose") or [{}])[0].get("adjclose") or []
    rows = []
    for index, timestamp in enumerate(timestamps):
        try:
            values = [quote[name][index] for name in ("open", "high", "low", "close")]
        except (KeyError, IndexError, TypeError):
            continue
        if any(value is None for value in values):
            continue
        raw_close = float(values[3])
        adj_close = adjusted[index] if index < len(adjusted) else None
        factor = float(adj_close) / raw_close if adj_close is not None and raw_close > 0 else 1.0
        rows.append({
            "date": datetime.fromtimestamp(int(timestamp), timezone.utc).date().isoformat(),
            **{name: float(value) * factor for name, value in zip(("open", "high", "low", "close"), values)},
        })
    return rows


def _download_chart(ticker, start, end, requester=get_json):
    query = urlencode({
        "period1": int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp()),
        "period2": int(datetime(end.year, end.month, end.day, tzinfo=timezone.utc).timestamp()),
        "interval": "1d",
        "events": "div,splits",
    })
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?{query}"
    return _chart_rows(requester(url, {"User-Agent": "Mozilla/5.0 StanceShiftResearch/3"}))


def download_prices(ticker, analysis_date, chart_requester=get_json):
    import yfinance as yf
    anchor = date.fromisoformat(analysis_date)
    # At least eight non-overlapping 60-session windows are required by the
    # preregistered base-rate diagnostic.  A 400-calendar-day download could
    # never satisfy that requirement; 900 days normally provides 10+ windows.
    start = anchor - timedelta(days=PRICE_HISTORY_CALENDAR_DAYS)
    end = min(date.today(), anchor + timedelta(days=PRICE_FUTURE_CALENDAR_DAYS))
    rows = []
    source = "Yahoo Finance via yfinance"
    errors = []
    try:
        frame = yf.Ticker(ticker).history(start=start.isoformat(), end=end.isoformat(),
            auto_adjust=True, actions=False, timeout=20)
        if not frame.empty:
            rows = [{"date": stamp.date().isoformat(), **{key.lower(): float(row[key]) for key in ("Open", "High", "Low", "Close")}}
                    for stamp, row in frame.iterrows()]
        else:
            errors.append("yfinance 回傳空資料")
    except Exception as error:
        errors.append(f"yfinance {type(error).__name__}")

    # yfinance currently prefers query2. Some networks block only that hostname,
    # while Yahoo's equivalent query1 Chart endpoint remains available.
    if not rows:
        for attempt in range(2):
            try:
                rows = _download_chart(ticker, start, end, chart_requester)
                if rows:
                    source = "Yahoo Finance Chart API query1 (adjusted OHLC)"
                    break
            except Exception as error:
                errors.append(f"query1 {type(error).__name__}")
                if attempt == 0:
                    time.sleep(.5)
    if not rows:
        reason = "、".join(dict.fromkeys(errors))[:240] or "來源未回傳資料"
        raise ValueError(f"無法連線 Yahoo Finance 行情服務（{reason}）。請檢查網路後重試，或匯入已授權的歷史 OHLC")
    return validate_dataset({"ticker": ticker, "kind": "historical", "source": source,
        "requested_analysis_date": analysis_date,
        "price_basis": "adjusted_ohlc", "retrieved_at": date.today().isoformat(), "prices": rows, "evidence": [],
        "collection_rules": {"version": "point-in-time-input-v2",
                             "price_history_calendar_days": PRICE_HISTORY_CALENDAR_DAYS,
                             "price_future_calendar_days": PRICE_FUTURE_CALENDAR_DAYS,
                             "analysis_day_excluded": True},
        "limitations": ["還原行情可能包含事後公司行動調整；來源並非不可變的歷史 vintage。", "Yahoo 資料使用與再散布須符合來源授權。",
            f"本次行情下載路徑：{source}。"]})


def _alpha_vantage_news(ticker, analysis_date, requester=get_json, relevance_floor=MIN_NEWS_RELEVANCE):
    key = os.getenv("ALPHA_VANTAGE_API_KEY", "")
    if not key:
        return None
    anchor = date.fromisoformat(analysis_date)
    query = urlencode({
        "function": "NEWS_SENTIMENT", "tickers": ticker,
        "time_from": (anchor - timedelta(days=90)).strftime("%Y%m%dT0000"),
        "time_to": (anchor - timedelta(days=1)).strftime("%Y%m%dT2359"),
        "sort": "RELEVANCE", "limit": 200, "apikey": key,
    })
    payload = requester("https://www.alphavantage.co/query?" + query)
    provider_error = payload.get("Error Message") or payload.get("Information") or payload.get("Note")
    if provider_error:
        raise ValueError("Alpha Vantage 拒絕新聞請求或已達流量限制")
    feed = payload.get("feed", [])
    if not isinstance(feed, list):
        raise ValueError("Alpha Vantage 新聞回應格式錯誤")
    items = []
    stats = {"fetched": len(feed), "dropped_missing_relevance": 0,
             "dropped_low_relevance": 0, "kept": 0}
    for row in feed:
        published = str(row.get("time_published", ""))
        if len(published) < 8 or not published[:8].isdigit():
            continue
        available_at = f"{published[:4]}-{published[4:6]}-{published[6:8]}"
        if not (anchor - timedelta(days=90)).isoformat() <= available_at < analysis_date:
            continue
        title, source = str(row.get("title", "")).strip(), str(row.get("url", "")).strip()
        if not title or not source:
            continue
        ticker_score = next((score for score in row.get("ticker_sentiment", [])
                             if score.get("ticker") == ticker), {})
        # The endpoint can return broad market stories.  A story without an
        # explicit target-ticker relevance record is not company evidence.
        if not ticker_score:
            stats["dropped_missing_relevance"] += 1
            continue
        try:
            relevance = float(ticker_score["relevance_score"])
        except (KeyError, TypeError, ValueError):
            stats["dropped_missing_relevance"] += 1
            continue
        if not 0 <= relevance <= 1:
            stats["dropped_missing_relevance"] += 1
            continue
        if relevance < relevance_floor:
            stats["dropped_low_relevance"] += 1
            continue
        summary = str(row.get("summary", "")).strip()
        claim = title if not summary else f"{title}。{summary}"
        item = {"evidence_id": "alpha-news-" + digest([ticker, published, source])[:20],
                "domain": "sentiment", "claim": claim[:4000], "headline": title[:1000], "source": source[:2000],
                "available_at": available_at, "source_type": "alpha_vantage_news_sentiment",
                "publisher": str(row.get("source", ""))[:300], "target_ticker": ticker,
                "relevance_score": relevance, "relevance_basis": "alpha_vantage_provider_score"}
        if ticker_score:
            try:
                item["provider_sentiment_score"] = float(ticker_score.get("ticker_sentiment_score"))
                item["sentiment_score"] = item["provider_sentiment_score"]
            except (TypeError, ValueError):
                pass
            item["provider_sentiment_label"] = str(ticker_score.get("ticker_sentiment_label", ""))[:80]
        items.append(item)
    stats["kept"] = len(items)
    return items, stats


def _fnspid_news(path, ticker, analysis_date, limit=50):
    anchor = date.fromisoformat(analysis_date)
    start = (anchor - timedelta(days=90)).isoformat()
    items = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        aliases = {
            "Date": ("Date", "date"),
            "Article_title": ("Article_title", "headline"),
            "Stock_symbol": ("Stock_symbol", "symbol"),
            "Url": ("Url", "url"),
            "Publisher": ("Publisher", "publisher"),
        }
        fields = set(reader.fieldnames or [])
        columns = {key: next((name for name in names if name in fields), None)
                   for key, names in aliases.items()}
        if any(columns[key] is None for key in ("Date", "Article_title", "Stock_symbol", "Url")):
            raise ValueError("FNSPID CSV 缺少 Date、Article_title、Stock_symbol 或 Url 欄位")
        for row in reader:
            if str(row.get(columns["Stock_symbol"], "")).strip().upper() != ticker:
                continue
            available_at = str(row.get(columns["Date"], ""))[:10]
            try:
                date.fromisoformat(available_at)
            except ValueError:
                continue
            if not start <= available_at < analysis_date:
                continue
            title = str(row.get(columns["Article_title"], "")).strip()
            source = str(row.get(columns["Url"], "")).strip()
            if not title or not source:
                continue
            publisher = str(row.get(columns["Publisher"], "")).strip() if columns["Publisher"] else ""
            items.append({"evidence_id": "fnspid-news-" + digest([ticker, available_at, source])[:20],
                          "domain": "sentiment", "claim": title[:4000], "headline": title[:1000], "source": source[:2000],
                          "available_at": available_at, "source_type": "FNSPID",
                          "publisher": publisher[:300], "target_ticker": ticker,
                          "relevance_score": 1.0, "relevance_basis": "fnspid_per_ticker_file"})
    unique = {}
    for item in sorted(items, key=lambda value: value["available_at"], reverse=True):
        unique.setdefault(item["evidence_id"], item)
    return list(unique.values())[:limit]


def _alpha_vantage_cached_news(path, ticker, analysis_date, limit=50):
    """Read a previously-fetched Alpha Vantage NEWS_SENTIMENT archive from disk.

    Unlike _alpha_vantage_news, this never calls the live API or spends a
    metered request; it exists so a locally accumulated news cache (built
    ahead of time, e.g. covering the 2024/2025 quarters FNSPID does not
    reach) can serve a case without touching the daily rate limit.
    """
    anchor = date.fromisoformat(analysis_date)
    start = (anchor - timedelta(days=90)).isoformat()
    items = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        if not {"date", "symbol", "headline", "url"}.issubset(fields):
            raise ValueError("Alpha Vantage 快取 CSV 缺少 date、symbol、headline 或 url 欄位")
        for row in reader:
            if str(row.get("symbol", "")).strip().upper() != ticker:
                continue
            raw_date = str(row.get("date", "")).strip()
            if len(raw_date) < 8 or not raw_date[:8].isdigit():
                continue
            available_at = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
            try:
                date.fromisoformat(available_at)
            except ValueError:
                continue
            if not start <= available_at < analysis_date:
                continue
            title = str(row.get("headline", "")).strip()
            source = str(row.get("url", "")).strip()
            if not title or not source:
                continue
            publisher = str(row.get("publisher", "")).strip()
            items.append({"evidence_id": "av-cache-" + digest([ticker, available_at, source])[:20],
                          "domain": "sentiment", "claim": title[:4000], "headline": title[:1000], "source": source[:2000],
                          "available_at": available_at, "source_type": "alpha_vantage_news_cache",
                          "publisher": publisher[:300], "target_ticker": ticker,
                          "relevance_score": 1.0, "relevance_basis": "alpha_vantage_cache_per_ticker_file"})
    unique = {}
    for item in sorted(items, key=lambda value: value["available_at"], reverse=True):
        unique.setdefault(item["evidence_id"], item)
    return list(unique.values())[:limit]


def _canonical_news_url(value):
    try:
        parsed = urlsplit(value.strip())
        host = parsed.netloc.lower().removeprefix("www.")
        path = re.sub(r"/+", "/", parsed.path).rstrip("/") or "/"
        tracking = {"fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid"}
        query = urlencode(sorted((key, val) for key, val in parse_qsl(parsed.query, keep_blank_values=True)
                                 if not key.lower().startswith("utm_") and key.lower() not in tracking))
        return urlunsplit(("https", host, path, query, "")) if host else ""
    except (AttributeError, ValueError):
        return ""


def _deduplicate_news(items, limit=100):
    """Deduplicate syndicated rows across providers by canonical URL or title/date."""
    selected, seen, aliases = [], {}, {}
    for item in sorted(items, key=lambda row: (row["available_at"], row["evidence_id"]), reverse=True):
        canonical = _canonical_news_url(item.get("source", ""))
        title = re.sub(r"[^\w]+", " ", str(item.get("headline") or item["claim"]).lower()).strip()
        # A stable article URL is the stronger identity.  Do not also apply the
        # title/date fallback to URL-bearing rows: two distinct articles can
        # legitimately share a headline, especially in syndicated feeds.
        keys = ([f"url:{canonical}"] if canonical else
                ([f"title:{item['available_at']}:{title}"] if title else []))
        duplicate = next((seen[key] for key in keys if key in seen), None)
        if duplicate is not None:
            sources = set(duplicate.get("source_types", [duplicate.get("source_type", "unknown")]))
            sources.add(item.get("source_type", "unknown"))
            duplicate["source_types"] = sorted(sources)
            aliases[item["evidence_id"]] = duplicate["evidence_id"]
            continue
        item = dict(item)
        item["canonical_url"] = canonical or item.get("source", "")
        item["source_types"] = [item.get("source_type", "unknown")]
        selected.append(item)
        for key in keys:
            seen[key] = item
        if len(selected) >= limit:
            break
    return selected, aliases


def _alpha_note(stats):
    return (f"Alpha Vantage 取得 {stats['fetched']} 筆，保留 {stats['kept']} 筆；"
            f"因缺少相關性分數排除 {stats['dropped_missing_relevance']} 筆，"
            f"因相關性不足排除 {stats['dropped_low_relevance']} 筆")


def fetch_sentiment(ticker, analysis_date, requester=get_json, relevance_floor=MIN_NEWS_RELEVANCE):
    """Fetch point-in-time news without silently inventing sentiment evidence."""
    items, notes = [], []
    cache_path = os.getenv("ALPHA_VANTAGE_NEWS_PATH", "").strip()
    cache_items = []
    if cache_path:
        try:
            cache_items = _alpha_vantage_cached_news(cache_path, ticker, analysis_date)
            items.extend(cache_items)
            if not cache_items:
                notes.append("Alpha Vantage 快取檔在切點前 90 天無相符新聞")
        except FileNotFoundError:
            notes.append("ALPHA_VANTAGE_NEWS_PATH 檔案不存在；請確認路徑或清空改用即時 API")
        except Exception as error:
            notes.append(f"Alpha Vantage 快取讀取失敗：{type(error).__name__}")
    path = os.getenv("FNSPID_NEWS_PATH", "").strip()
    if path:
        try:
            fnspid_items = _fnspid_news(path, ticker, analysis_date)
            items.extend(fnspid_items)
            if not fnspid_items:
                notes.append("FNSPID 在切點前 90 天無相符新聞")
        except FileNotFoundError:
            notes.append("FNSPID 檔案不存在；請將 CSV 放入 research-inputs/Stock_news.csv，或清空 FNSPID_NEWS_PATH 改用 Alpha Vantage")
        except Exception as error:
            notes.append(f"FNSPID 讀取失敗：{type(error).__name__}")
    alpha_configured = bool(os.getenv("ALPHA_VANTAGE_API_KEY", ""))
    # Local archives are free and reproducible. Spend a metered live request
    # only when the cache/FNSPID evidence does not already fill the 50-item
    # source budget for this ticker and point-in-time window.
    if alpha_configured and not cache_items and len(items) < 50:
        try:
            alpha_items, alpha_stats = _alpha_vantage_news(ticker, analysis_date, requester, relevance_floor)
            items.extend(alpha_items)
            notes.append(_alpha_note(alpha_stats))
            if not alpha_items:
                notes.append("Alpha Vantage 在切點前 90 天無相符新聞")
        except Exception as error:
            detail = str(error) if isinstance(error, ValueError) else type(error).__name__
            notes.append(f"Alpha Vantage 下載失敗：{detail[:180]}")
    elif alpha_configured:
        notes.append("本機新聞已達 50 筆，略過 Alpha Vantage 計費請求")
    if not alpha_configured and not path and not cache_path:
        notes.append("未設定 ALPHA_VANTAGE_API_KEY、ALPHA_VANTAGE_NEWS_PATH 或 FNSPID_NEWS_PATH；可匯入具公開時間的新聞摘要")
    unique, aliases = _deduplicate_news(items)
    if aliases:
        notes.append(f"跨來源去除 {len(aliases)} 筆重複新聞")
    return unique, "；".join(notes)


def check_sentiment_sources(ticker, analysis_date, requester=get_json, relevance_floor=MIN_NEWS_RELEVANCE):
    """Actively verify configured news sources without exposing credentials."""
    results = {}
    cache_path = os.getenv("ALPHA_VANTAGE_NEWS_PATH", "").strip()
    if cache_path:
        try:
            items = _alpha_vantage_cached_news(cache_path, ticker, analysis_date)
            results["alpha_vantage_cache"] = {"status": "ready", "records": len(items),
                "message": ("檔案、欄位與日期格式已驗證" if items else "檔案可讀，但切點前 90 天無相符新聞")}
        except FileNotFoundError:
            results["alpha_vantage_cache"] = {"status": "error", "records": 0,
                "message": "找不到檔案；請確認 ALPHA_VANTAGE_NEWS_PATH"}
        except Exception as error:
            results["alpha_vantage_cache"] = {"status": "error", "records": 0,
                "message": f"實機檢查失敗：{type(error).__name__}"}
    else:
        results["alpha_vantage_cache"] = {"status": "unconfigured", "records": 0,
            "message": "尚未設定 ALPHA_VANTAGE_NEWS_PATH"}
    if os.getenv("ALPHA_VANTAGE_API_KEY", ""):
        try:
            items, stats = _alpha_vantage_news(ticker, analysis_date, requester, relevance_floor)
            results["alpha_vantage"] = {"status": "ready", "records": len(items),
                "message": "連線與回應格式已驗證；" + _alpha_note(stats), "statistics": stats}
        except Exception as error:
            results["alpha_vantage"] = {"status": "error", "records": 0,
                "message": (str(error)[:180] if isinstance(error, ValueError)
                            else f"實機檢查失敗：{type(error).__name__}")}
    else:
        results["alpha_vantage"] = {"status": "unconfigured", "records": 0,
            "message": "尚未設定 ALPHA_VANTAGE_API_KEY"}
    path = os.getenv("FNSPID_NEWS_PATH", "").strip()
    if path:
        try:
            items = _fnspid_news(path, ticker, analysis_date)
            results["fnspid"] = {"status": "ready", "records": len(items),
                "message": ("檔案、欄位與日期格式已驗證"
                            if items else "檔案可讀，但切點前 90 天無相符新聞")}
        except FileNotFoundError:
            alpha_ready = results.get("alpha_vantage", {}).get("status") == "ready" and results["alpha_vantage"]["records"] > 0
            results["fnspid"] = {"status": "optional_missing" if alpha_ready else "error", "records": 0,
                "message": ("選用來源未啟用：找不到檔案；目前由 Alpha Vantage 提供新聞，不影響情緒資料"
                            if alpha_ready else "找不到檔案；請放入 research-inputs/Stock_news.csv，或清空 FNSPID_NEWS_PATH")}
        except Exception as error:
            results["fnspid"] = {"status": "error", "records": 0,
                "message": f"實機檢查失敗：{type(error).__name__}"}
    else:
        results["fnspid"] = {"status": "unconfigured", "records": 0,
            "message": "尚未設定 FNSPID_NEWS_PATH"}
    return results


def fetch_macro(analysis_date):
    key = os.getenv("FRED_API_KEY")
    if not key:
        return [], "未設定 FRED_API_KEY；可匯入具 vintage_date 的 ALFRED 摘要"
    items = []
    for series in ("FEDFUNDS", "CPIAUCSL", "UNRATE"):
        query = urlencode(dict(series_id=series, api_key=key, file_type="json", realtime_start=analysis_date,
            realtime_end=analysis_date, observation_end=analysis_date, sort_order="desc", limit=1))
        result = get_json("https://api.stlouisfed.org/fred/series/observations?" + query)
        for row in result.get("observations", []):
            if row["value"] == ".":
                continue
            items.append({"evidence_id": f"alfred-{series}-{analysis_date}", "domain": "macro",
                "claim": f"{series}: {row['value']}，觀測期間 {row['date']}，截至 {analysis_date} 可知版本",
                "source": f"https://alfred.stlouisfed.org/series?seid={series}",
                "available_at": analysis_date, "vintage_date": analysis_date})
    return items, "" if items else "ALFRED 無可用觀測值"


CIKS = {"AAPL": "0000320193", "NVDA": "0001045810", "GOOGL": "0001652044", "MSFT": "0000789019",
        "AMZN": "0001018724", "JPM": "0000019617", "MCD": "0000063908", "LLY": "0000059478", "GE": "0000040545", "ASTS": "0001780312"}


def _financial_facts(data, tag, analysis_date):
    """Return finite, filed-before-cutoff 10-Q/10-K USD facts for one concept."""
    facts = data.get("facts", {}).get("us-gaap", {}).get(tag, {}).get("units", {}).get("USD", [])
    result, seen = [], set()
    for fact in facts:
        if fact.get("form") not in ("10-Q", "10-K"):
            continue
        if fact.get("filed", "9999") >= analysis_date or fact.get("end", "9999") >= analysis_date:
            continue
        try:
            value = Decimal(str(fact["val"]))
            end = date.fromisoformat(fact["end"])
            start = date.fromisoformat(fact["start"]) if fact.get("start") else None
        except (KeyError, TypeError, ValueError, InvalidOperation):
            continue
        if not value.is_finite():
            continue
        key = (fact.get("accn"), fact.get("start"), fact.get("end"), str(value))
        if key in seen:
            continue
        seen.add(key)
        result.append({**fact, "_value": value, "_end": end, "_start": start,
                       "_duration": (end - start).days if start else None})
    return result


def _comparable_pair(facts):
    """Select the latest quarter/annual fact with a same-period prior-year fact."""
    durations = [fact for fact in facts
                 if fact["_duration"] is not None
                 and (70 <= fact["_duration"] <= 110 or 330 <= fact["_duration"] <= 380)]
    for current in sorted(durations, key=lambda item: (item["_end"], item.get("filed", "")), reverse=True):
        candidates = [prior for prior in durations
                      if 300 <= (current["_end"] - prior["_end"]).days <= 430
                      and abs(current["_duration"] - prior["_duration"]) <= 25]
        if not candidates:
            continue
        prior = max(candidates, key=lambda item: (
            item.get("fp") == current.get("fp"),
            -abs((current["_end"] - item["_end"]).days - 365),
            -abs(current["_duration"] - item["_duration"]),
            item.get("filed", "")))
        return current, prior
    return None


def _filing_url(ticker, fact):
    return (f"https://www.sec.gov/Archives/edgar/data/{int(CIKS[ticker])}/"
            f"{fact['accn'].replace('-', '')}/")


def _decimal_text(value):
    return format(value, "f")


def fetch_fundamental(ticker, analysis_date, requester=get_json):
    agent = os.getenv("SEC_USER_AGENT", "")
    if "@" not in agent:
        return [], "未設定含聯絡信箱的 SEC_USER_AGENT；可匯入具 filing date 的財報摘要"
    data = requester(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIKS[ticker]}.json",
                     {"User-Agent": agent, "Accept-Encoding": "identity"})
    items = []
    metric_tags = (
        ("Revenue", ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues")),
        ("NetIncomeLoss", ("NetIncomeLoss",)),
        ("OperatingCashFlow", ("NetCashProvidedByUsedInOperatingActivities",)),
    )
    for metric, tags in metric_tags:
        choices = [(tag, pair, priority) for priority, tag in enumerate(tags)
                   if (pair := _comparable_pair(_financial_facts(data, tag, analysis_date)))]
        if not choices:
            continue
        selected_tag, selected, _ = max(choices, key=lambda choice: (
            choice[1][0]["_end"], choice[1][0].get("filed", ""), -choice[2]))
        current, prior = selected
        change = (current["_value"] / prior["_value"] - 1) * 100 if prior["_value"] else None
        if change is None or not change.is_finite():
            continue
        claim = (f"{metric}: current={_decimal_text(current['_value'])} USD; current_period="
                 f"{current.get('start', '')}–{current['end']}; prior={_decimal_text(prior['_value'])} USD; "
                 f"prior_period={prior.get('start', '')}–{prior['end']}; "
                 f"year_over_year_change_pct={change:.6f}; current_form={current['form']}; "
                 f"current_filed={current['filed']}")
        items.append({"evidence_id": f"sec-comparison-{selected_tag}-{current['accn']}-{prior['accn']}",
            "domain": "fundamental", "claim": claim, "source": _filing_url(ticker, current),
            "available_at": current["filed"], "comparative": True, "metric": metric,
            "current_value": current["val"], "prior_value": prior["val"],
            "change_pct": round(float(change), 6), "current_period": current["end"],
            "prior_period": prior["end"], "current_accession": current["accn"],
            "prior_accession": prior["accn"], "selection_rule": "same_concept_similar_duration_prior_year_v1"})

    assets = _financial_facts(data, "Assets", analysis_date)
    liabilities = _financial_facts(data, "Liabilities", analysis_date)
    pairs = [(asset, liability) for asset in assets for liability in liabilities
             if asset["_end"] == liability["_end"] and asset.get("accn") == liability.get("accn")
             and asset["_value"] > 0]
    if pairs:
        asset, liability = max(pairs, key=lambda pair: (pair[0]["_end"], pair[0].get("filed", "")))
        ratio = liability["_value"] / asset["_value"] * 100
        items.append({"evidence_id": f"sec-ratio-liabilities-assets-{asset['accn']}",
            "domain": "fundamental",
            "claim": (f"LiabilitiesToAssets: Assets={_decimal_text(asset['_value'])} USD; "
                      f"Liabilities={_decimal_text(liability['_value'])} USD; liabilities_to_assets_pct={ratio:.6f}; "
                      f"period_end={asset['end']}; form={asset['form']}; filed={asset['filed']}"),
            "source": _filing_url(ticker, asset), "available_at": asset["filed"],
            "comparative": True, "metric": "LiabilitiesToAssets",
            "assets": asset["val"], "liabilities": liability["val"],
            "ratio_pct": round(float(ratio), 6), "current_accession": asset["accn"],
            "selection_rule": "same_accession_same_period_ratio_v1"})

    # Keep the domain auditable when a company has no comparable pair, but mark
    # these point fields so they remain excluded from directional decisions.
    if not items:
        for tag in ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "NetIncomeLoss",
                    "Assets", "Liabilities", "NetCashProvidedByUsedInOperatingActivities"):
            facts = _financial_facts(data, tag, analysis_date)
            if not facts:
                continue
            fact = max(facts, key=lambda item: (item["_end"], item.get("filed", "")))
            items.append({"evidence_id": f"sec-point-{tag}-{fact['accn']}", "domain": "fundamental",
                "claim": f"{tag} = {_decimal_text(fact['_value'])} USD; period {fact.get('start', '')}–{fact['end']}; form {fact['form']}",
                "source": _filing_url(ticker, fact), "available_at": fact["filed"],
                "comparative": False, "selection_rule": "latest_filed_point_fallback_v1"})
    return items, "" if items else "SEC 在資料切點前無可用 XBRL 財報"


def _sentiment_scope(item, ticker):
    """Classify news for a decision prompt without deleting market context.

    FNSPID rows were selected by Stock_symbol before they reached this service,
    so they are target evidence.  Alpha Vantage's ticker query can still return
    a story that merely compares another company with the requested ticker; a
    target alias must occur in the headline before treating it as direct target
    evidence.  Everything else remains available as explicitly labelled
    context instead of being silently discarded.
    """
    if str(item.get("source_type", "")).casefold() == "fnspid" or item.get("relevance_basis") == "fnspid_per_ticker_file":
        return "target"
    headline = str(item.get("headline") or "")
    aliases = (ticker,) + tuple(COMPANY_NAMES.get(ticker, ()))
    if any(re.search(r"(?<![A-Za-z0-9])" + re.escape(alias) + r"(?![A-Za-z0-9])", headline, re.I)
           for alias in aliases):
        return "target"
    return "context"


def _passes_relevance(item, floor):
    """Keep manually imported/FNSPID evidence while enforcing provider scores."""
    if item.get("relevance_basis") == "fnspid_per_ticker_file" or str(item.get("source_type", "")).casefold() == "fnspid":
        return True
    if item.get("source_type") != "alpha_vantage_news_sentiment":
        return True
    try:
        score = float(item["relevance_score"])
    except (KeyError, TypeError, ValueError):
        return False
    return math.isfinite(score) and score >= floor


def _relevance_value(item):
    """Return a sortable relevance value without trusting imported strings."""
    try:
        value = float(item.get("relevance_score", 0.0))
    except (TypeError, ValueError):
        return 0.0
    return value if math.isfinite(value) else 0.0


def _source_balanced(items, limit):
    """Return a bounded deterministic sample without allowing one feed to dominate."""
    queues = {}
    for item in items:
        queues.setdefault(item.get("source_type", "unknown"), []).append(item)
    selected = []
    while len(selected) < limit and any(queues.values()):
        for source_type in sorted(queues):
            if queues[source_type] and len(selected) < limit:
                selected.append(queues[source_type].pop(0))
    return selected


def _sentiment_summary(items):
    scores = []
    for item in items:
        try:
            score = float(item["sentiment_score"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(score) and -1 <= score <= 1:
            scores.append(score)
    mean_score = sum(scores) / len(scores) if scores else None
    if mean_score is None:
        direction = "unscored"
    elif mean_score > .10:
        direction = "positive"
    elif mean_score < -.10:
        direction = "negative"
    else:
        direction = "neutral"
    return {"count": len(items), "scored_count": len(scores),
            "mean_score": round(mean_score, 6) if mean_score is not None else None,
            "direction": direction, "score_definition": "mean(P(positive)-P(negative))"}


def _technical_calibration(return20, mean20, mean60, volatility):
    mean_gap = mean20 / mean60 - 1
    if return20 > 0 and mean_gap > 0:
        direction = "upward"
    elif return20 < 0 and mean_gap < 0:
        direction = "downward"
    else:
        direction = "mixed"
    magnitude = max(abs(return20), abs(mean_gap))
    strength = "weak" if magnitude < .02 else "moderate" if magnitude < .07 else "strong"
    return {"return20": round(return20, 6), "mean20": round(mean20, 6), "mean60": round(mean60, 6),
            "mean20_vs_mean60": round(mean_gap, 6), "annual_volatility": round(volatility, 6),
            "direction": direction, "strength": strength,
            "rule": "upward/downward only when return20 and mean20_vs_mean60 have the same non-zero sign"}


def _base_rates(history, primary_horizon, volatility, hold_band_sigma):
    """Calculate a pre-cutoff, non-overlapping horizon prior without leakage."""
    windows = []
    end = len(history)
    while end >= primary_horizon:
        chunk = history[end - primary_horizon:end]
        windows.append(chunk[-1]["close"] / chunk[0]["close"] - 1)
        end -= primary_horizon
    horizon_sigma_pct = volatility * math.sqrt(primary_horizon / 252) * 100
    result = {"horizon_sessions": primary_horizon, "windows": len(windows),
              "horizon_sigma_pct": round(horizon_sigma_pct, 6),
              "hold_band_pct": round(hold_band_sigma * horizon_sigma_pct, 6),
              "basis": "non_overlapping_windows_strictly_before_analysis_date"}
    if len(windows) < 8:
        return {**result, "positive_rate": None, "median_return_pct": None, "basis": "insufficient_history"}
    return {**result, "positive_rate": round(sum(value > 0 for value in windows) / len(windows), 6),
            "median_return_pct": round(sorted(windows)[len(windows) // 2] * 100, 6)}


def research_inputs(dataset, analysis_date, protocol=None):
    history = [row for row in dataset["prices"] if row["date"] < analysis_date]
    if len(history) < 61:
        raise ValueError("分析日前須至少有 61 個交易日；分析日當天資料保守排除")
    closes = [row["close"] for row in history]
    returns = [math.log(b / a) for a, b in zip(closes[-61:-1], closes[-60:])]
    mean = sum(returns) / len(returns)
    vol = math.sqrt(sum((r - mean)**2 for r in returns) / (len(returns) - 1) * 252)
    eligible = [dict(e) for e in dataset["evidence"] if e["available_at"] < analysis_date]
    # News APIs can return dozens of long summaries. A bounded, deterministic
    # sample keeps local-model prompts reliable while the original dataset still
    # preserves every downloaded row for audit and export.
    primary_horizon = getattr(protocol, "primary_horizon", 60)
    hold_band_sigma = getattr(protocol, "hold_band_sigma", .5)
    relevance_floor = getattr(protocol, "news_relevance_floor", MIN_NEWS_RELEVANCE)
    target_context_priority = getattr(protocol, "target_context_priority", True)
    evidence = []
    selection = {}
    ticker = str(dataset.get("ticker", "")).upper()
    for domain in ("fundamental", "sentiment", "macro"):
        domain_items = [item for item in eligible if item["domain"] == domain]
        if domain == "sentiment":
            domain_items = [item for item in domain_items if _passes_relevance(item, relevance_floor)]
            domain_items.sort(key=lambda item: (round(_relevance_value(item), 2),
                                                item["available_at"], item["evidence_id"]), reverse=True)
        else:
            domain_items.sort(key=lambda item: (item["available_at"], item["evidence_id"]), reverse=True)
        limit = 12 if domain == "sentiment" else len(domain_items)
        if domain == "sentiment":
            for item in domain_items:
                item["evidence_scope"] = _sentiment_scope(item, ticker)
            target_items = [item for item in domain_items if item["evidence_scope"] == "target"]
            context_items = [item for item in domain_items if item["evidence_scope"] == "context"]
            if target_context_priority:
                # Direct company evidence gets the first eight slots, while a
                # bounded contextual sample remains available for sector risk.
                selected = _source_balanced(target_items, min(8, len(target_items)))
                selected += _source_balanced(context_items, limit - len(selected))
                if len(selected) < limit:
                    selected_ids = {item["evidence_id"] for item in selected}
                    selected += _source_balanced([item for item in target_items if item["evidence_id"] not in selected_ids],
                                                 limit - len(selected))
                strategy = "relevance_target_priority_source_balanced"
            else:
                selected = _source_balanced(domain_items, limit)
                strategy = "relevance_then_recency_source_balanced"
        else:
            selected = domain_items[:limit]
        for item in selected:
            if domain == "sentiment" and len(item.get("claim", "")) > 1200:
                item["claim"] = item["claim"][:1199] + "…"
        evidence.extend(selected)
        if domain == "sentiment":
            selection[domain] = {"available": len(domain_items), "selected": len(selected),
                                 "target_available": len(target_items), "context_available": len(context_items),
                                 "target_selected": sum(item["evidence_scope"] == "target" for item in selected),
                                 "context_selected": sum(item["evidence_scope"] == "context" for item in selected),
                                 "relevance_floor": relevance_floor, "strategy": strategy}
        else:
            selection[domain] = {"available": len(domain_items), "selected": len(selected),
                                 "strategy": "latest_then_evidence_id"}
    technical = [("return20", closes[-1] / closes[-21] - 1), ("mean20", sum(closes[-20:]) / 20),
                 ("mean60", sum(closes[-60:]) / 60), ("volatility60_annual", vol)]
    for key, value in technical:
        evidence.append({"evidence_id": f"price-{key}-{history[-1]['date']}", "domain": "technical",
            "claim": f"{key} = {value:.6f}", "value": value, "available_at": history[-1]["date"], "source": dataset["source"]})
    selection["technical"] = {"available": len(technical), "selected": len(technical),
                              "strategy": "derived_from_pre_cutoff_ohlc"}
    selected_sentiment = [item for item in evidence if item["domain"] == "sentiment"]
    selected_fundamental = [item for item in evidence if item["domain"] == "fundamental"]
    target_sentiment = [item for item in selected_sentiment if item.get("evidence_scope") == "target"]
    context_sentiment = [item for item in selected_sentiment if item.get("evidence_scope") == "context"]
    base_rates = _base_rates(history, primary_horizon, vol, hold_band_sigma)
    decision_calibration = {
        "rules_version": "target-context-calibration-v1",
        "technical": _technical_calibration(technical[0][1], technical[1][1], technical[2][1], technical[3][1]),
        "sentiment": {"target": _sentiment_summary(target_sentiment),
                      "context": _sentiment_summary(context_sentiment)},
        "limits": [
            "Context-only news is market or sector context, not a direct target-company fact.",
            ("Supplied fundamental evidence contains deterministic same-concept comparisons or ratios; it still provides no valuation or peer benchmark."
             if any(item.get("comparative") is True for item in selected_fundamental) else
             "Supplied fundamental facts have no comparative ratio or growth series; a field name or magnitude alone does not prove high/low, gain/loss, or direction."),
            "Supplied macro values are point-in-time levels; they do not by themselves prove a rate, inflation, or employment trend.",
        ],
    }
    return {"domains": {domain: [e for e in evidence if e["domain"] == domain] for domain in DOMAIN_NAMES},
            "evidence": evidence, "volatility": vol, "last_price_date": history[-1]["date"],
            "evidence_selection": selection, "decision_calibration": decision_calibration,
            "base_rates": base_rates, "horizon_sigma_pct": base_rates["horizon_sigma_pct"],
            "boundary": "strictly before analysis_date; analysis-day releases excluded"}
