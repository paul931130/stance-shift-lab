"""Four-domain dataset collection, usable without the web service."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

from .data import (NEWS_WINDOW_DAYS, _deduplicate_news, download_prices, fetch_fundamental, fetch_macro, fetch_sentiment,
                   score_sentiment_finbert, validate_dataset)
from .logging_config import get_logger
from .protocol import DESIGNS, validate_case

logger = get_logger(__name__)

DOMAINS = ("technical", "fundamental", "sentiment", "macro")
SOURCE_NAMES = {"technical": "行情", "fundamental": "SEC", "sentiment": "新聞", "macro": "ALFRED"}


def finbert_version(store, key, progress=None):
    """Score a dataset's headlines with FinBERT and store the result as a new version."""
    data = store.dataset(key)
    data["parent_dataset_id"] = key
    enriched = validate_dataset(score_sentiment_finbert(data, progress=progress))
    return {"id": store.add_dataset(enriched), "parent_dataset_id": key,
            "finbert_applied": True, "items": enriched["processing"]["sentiment"]["items"]}


def refresh_fundamentals(store, key, requester=None):
    """Rebuild only the SEC fundamental evidence of a snapshot, as a new version.

    Prices, news and macro data are kept byte for byte, so no news quota is
    spent. The new snapshot records ``parent_dataset_id`` and is used by jobs
    created afterwards; jobs already run keep pointing at the old snapshot.
    """
    data = store.dataset(key)
    analysis_date = data.get("requested_analysis_date")
    if data.get("kind") != "historical" or not analysis_date:
        raise ValueError("只能重建有研究分析日的歷史資料集")
    fetched, note = (fetch_fundamental(data["ticker"], analysis_date, requester) if requester
                     else fetch_fundamental(data["ticker"], analysis_date))
    if not fetched:
        raise ValueError(note or "SEC 沒有可用的基本面資料")
    by_domain = {domain: [item for item in data["evidence"] if item.get("domain") == domain] for domain in DOMAINS}
    by_domain["fundamental"] = fetched
    data["evidence"] = [item for domain in DOMAINS for item in by_domain[domain]]
    data["parent_dataset_id"] = key
    data.setdefault("processing", {})["fundamental"] = {
        "refreshed_from": key, "items": len(fetched),
        "selection_rule": next((item.get("selection_rule") for item in fetched if item.get("selection_rule")), None)}
    if isinstance(data.get("_collection"), dict):
        data["_collection"]["fundamental"] = {"status": "complete", "records": len(fetched),
                                              "message": f"已重建 {len(fetched)} 筆 SEC 基本面證據"}
    return {"id": store.add_dataset(validate_dataset(data)), "parent_dataset_id": key, "items": len(fetched)}


# Headlines fetched from the live Alpha Vantage API when a snapshot was collected
# were never written to the local archive; refresh_news carries them over.
LIVE_NEWS_SOURCE_TYPES = ("alpha_vantage_news_sentiment",)


def refresh_news(store, key, allow_live=False, progress=None, carry_live=True):
    """Rebuild only the sentiment evidence of a snapshot under the uncapped news rule, as a new version.

    Prices, fundamentals and macro data are kept byte for byte, so an
    experiment rerun on the new snapshot differs from the old one only in its
    news. Every headline of the window is kept and FinBERT-scored. By default
    only local news files are read (no Alpha Vantage quota).
    """
    data = store.dataset(key)
    analysis_date = data.get("requested_analysis_date")
    if data.get("kind") != "historical" or not analysis_date:
        raise ValueError("只能重建有研究分析日的歷史資料集")
    rules = data.get("collection_rules") or {}
    window_days = rules.get("news_window_days", NEWS_WINDOW_DAYS)
    fetched, note = fetch_sentiment(data["ticker"], analysis_date, allow_live=allow_live,
                                    window_days=window_days, item_limit=None)
    by_domain = {domain: [item for item in data["evidence"] if item.get("domain") == domain] for domain in DOMAINS}
    previous = len(by_domain["sentiment"])
    local_items = len(fetched)
    carried = [item for item in by_domain["sentiment"]
               if item.get("source_type") in LIVE_NEWS_SOURCE_TYPES] if carry_live else []
    if carried:
        # Same cross-source de-duplication as a fresh collection, with no cap.
        fetched, _ = _deduplicate_news([*fetched, *carried], limit=None)
    by_domain["sentiment"] = fetched
    data["evidence"] = [item for domain in DOMAINS for item in by_domain[domain]]
    data["parent_dataset_id"] = key
    data["collection_rules"] = {**rules, "news_item_limit": "uncapped"}
    if note:
        data["limitations"] = [*data.get("limitations", []), note]
    data.setdefault("processing", {}).pop("sentiment", None)
    data["processing"]["news_refresh"] = {"refreshed_from": key, "previous_items": previous,
                                          "items": len(fetched), "local_items": local_items,
                                          "carried_live_items": len(carried), "window_days": window_days,
                                          "live_sources": bool(allow_live)}
    if fetched:
        data = score_sentiment_finbert(data, progress=progress)
    if isinstance(data.get("_collection"), dict):
        data["_collection"]["sentiment"] = {"status": "complete" if fetched else "needs_input",
                                            "records": len(fetched),
                                            "message": f"已依不截斷規則重建 {len(fetched)} 則新聞並以 FinBERT 評分"}
    return {"id": store.add_dataset(validate_dataset(data)), "parent_dataset_id": key,
            "items": len(fetched), "previous_items": previous,
            "local_items": local_items, "carried_live_items": len(carried)}


def reusable_snapshot(store, ticker, analysis_date, design="quarterly"):
    """The newest complete historical snapshot for this case and study design, if any.

    A month-end that is also a quarter-end has two snapshots (90-day and 30-day
    news windows); the design keeps them apart.
    """
    for existing in store.datasets():
        rules = existing.get("collection_rules") or {}
        if (existing.get("ticker") == ticker and existing.get("kind") == "historical"
                and rules.get("design", "quarterly") == design
                and rules.get("news_item_limit") == "uncapped"
                and existing.get("requested_analysis_date") == analysis_date
                and existing.get("coverage", {}).get("research_ready")):
            return existing
    return None


def collect_dataset(store, ticker, analysis_date, *, refresh=False, use_finbert=False,
                    offline_news_only=False, progress=None, apply_finbert=None, design="quarterly"):
    """Build (or reuse) one dataset snapshot for a case.

    Shared by the web API, its background tasks, the CLI and the Python API.
    ``progress(**values)`` receives ``stage`` and per-domain ``agents`` updates.
    """
    report = progress or (lambda **_: None)
    validate_case(ticker, analysis_date, design)
    news_window_days = DESIGNS[design]["news_window_days"]
    existing = None if refresh else reusable_snapshot(store, ticker, analysis_date, design)
    if existing:
        result_id = ((apply_finbert(existing["id"]) if apply_finbert else finbert_version(store, existing["id"]))["id"]
                     if use_finbert else existing["id"])
        return {"id": result_id, "analysis_date": analysis_date,
                "limitations": existing.get("limitations", []), "agents": existing.get("_collection", {}),
                "version": existing.get("version"), "reused": True}
    cutoff = (date.fromisoformat(analysis_date) - timedelta(days=1)).isoformat()
    report(stage="collecting", agents={})
    agents, collected = {}, {}
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="collection-agent") as pool:
        futures = {
            pool.submit(download_prices, ticker, analysis_date): "technical",
            pool.submit(fetch_fundamental, ticker, analysis_date): "fundamental",
            pool.submit(fetch_sentiment, ticker, analysis_date,
                        allow_live=not offline_news_only, window_days=news_window_days,
                        item_limit=None): "sentiment",
            pool.submit(fetch_macro, cutoff): "macro",
        }
        # Report each domain as soon as its agent finishes so the UI can
        # show progress; the snapshot is still assembled in a fixed
        # domain order below, keeping the content-addressed ID stable.
        for future in as_completed(futures):
            domain = futures[future]
            name = SOURCE_NAMES[domain]
            if domain == "technical":
                data = future.result()  # Prices are mandatory; failure aborts the snapshot.
                agents[domain] = {"status": "complete", "records": len(data["prices"]),
                    "message": f"已取得一致還原 OHLC；{data['source']}"}
            else:
                try:
                    evidence, note = future.result()
                    collected[domain] = (evidence, [note] if note else [])
                    empty_status = "needs_input" if domain == "sentiment" else "needs_configuration"
                    message = f"已取得 {len(evidence)} 筆證據"
                    if note:
                        message += f"；附帶來源提醒：{note}"
                    agents[domain] = {"status": "complete" if evidence else empty_status,
                        "records": len(evidence), "message": message if evidence else note}
                except Exception as error:
                    logger.warning("dataset collection failed ticker=%s domain=%s: %s: %s",
                                   ticker, domain, type(error).__name__, error)
                    collected[domain] = ([], [f"{name} 下載失敗；可重新下載或匯入可驗證的摘要"])
                    agents[domain] = {"status": "error", "records": 0,
                        "message": f"{name} 下載失敗：{type(error).__name__}"}
            report(agents={key: dict(value) for key, value in agents.items()})
    # Every headline of the window is kept (no per-source cap); the protocol decides how much reaches a prompt.
    data["collection_rules"] = {**data.get("collection_rules", {}), "news_item_limit": "uncapped"}
    if design != "quarterly":
        data["collection_rules"] = {**data["collection_rules"], "design": design,
                                    "news_window_days": news_window_days}
    for domain in ("fundamental", "sentiment", "macro"):
        evidence, notes = collected[domain]
        data["evidence"].extend(evidence)
        data["limitations"].extend(notes)
    if not any(item["domain"] == "sentiment" for item in data["evidence"]):
        data["limitations"].append("自動新聞來源沒有可用的新聞；情緒面會標記為資料缺口，也可以匯入附發布時間的新聞摘要")
    sentiment_items = [item for item in data["evidence"] if item["domain"] == "sentiment"]
    if use_finbert and sentiment_items:
        report(stage="finbert")
        data = score_sentiment_finbert(data)
        count = data["processing"]["sentiment"]["items"]
        agents["sentiment"]["finbert"] = {"status": "complete", "items": count, "model": "ProsusAI/finbert", "input": "headline"}
        agents["sentiment"]["message"] += f"；本機 FinBERT 已完成 {count} 則標題"
    elif use_finbert:
        agents["sentiment"]["finbert"] = {"status": "skipped", "items": 0,
            "model": "ProsusAI/finbert", "input": "headline", "reason": "no_headlines"}
    agents = {domain: agents[domain] for domain in DOMAINS}
    data["_collection"] = agents
    return {"id": store.add_dataset(validate_dataset(data)), "analysis_date": analysis_date,
        "limitations": data["limitations"], "agents": agents, "reused": False}
