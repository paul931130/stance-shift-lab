"""Point-in-time coverage and outcome availability are separate properties."""
import math
import re
from statistics import median

from .protocol import COMPANY_NAMES, TICKERS, QUARTER_DATES
from .splits import split_for_date, temporal_split_summary


def _mentions_target(item, ticker):
    text = " ".join(str(item.get(key, "")) for key in ("headline", "claim"))
    if re.search(r"(?<![A-Za-z0-9])" + re.escape(ticker) + r"(?![A-Za-z0-9])", text, re.I):
        return True
    lowered = text.casefold()
    return any(name.casefold() in lowered for name in COMPANY_NAMES.get(ticker, ()))


def _sentiment_quality(data, day):
    items = [item for item in data.get("evidence", []) if item.get("domain") == "sentiment"
             and item.get("available_at", "") < day]
    mentions = sum(_mentions_target(item, data.get("ticker", "")) for item in items)
    relevance = []
    source_mapped = 0
    target_relevant = 0
    for item in items:
        mapped = False
        try:
            value = float(item["relevance_score"])
        except (KeyError, TypeError, ValueError):
            value = None
        if value is not None and math.isfinite(value):
            relevance.append(value)
            # Both supported news collectors attach the requested ticker from
            # provider metadata rather than inferring it from prose.  A title
            # need not repeat the company name (market roundups and ETF news
            # are common), so use the auditable source mapping when available.
            mapped_ticker = str(item.get("target_ticker", "")).upper()
            basis = item.get("relevance_basis")
            trusted_mapping = basis in ("alpha_vantage_provider_score", "alpha_vantage_cache_per_ticker_file",
                                        "fnspid_per_ticker_file")
            if mapped_ticker == str(data.get("ticker", "")).upper() and trusted_mapping and value >= .35:
                mapped = True
                source_mapped += 1
        if _mentions_target(item, data.get("ticker", "")) or mapped:
            target_relevant += 1
    def valid_finbert(item):
        scores = item.get("sentiment_scores")
        if not isinstance(scores, dict):
            return False
        try:
            probabilities = [float(scores[name]) for name in ("positive", "neutral", "negative")]
        except (KeyError, TypeError, ValueError):
            return False
        return (all(math.isfinite(value) and 0 <= value <= 1 for value in probabilities)
                and abs(sum(probabilities) - 1) <= 1e-4
                and item.get("sentiment_input") == "headline"
                and bool(item.get("sentiment_input_hash"))
                and bool(item.get("sentiment_revision")))

    finbert_scored = sum(valid_finbert(item) for item in items)
    mention_rate = mentions / len(items) if items else 0.
    target_rate = target_relevant / len(items) if items else 0.
    return {"items": len(items), "ticker_mentions": mentions, "ticker_mention_rate": mention_rate,
            "source_mapped_items": source_mapped, "target_relevance_rate": target_rate,
            "quality_rule": "source-target-v1",
            "median_relevance": median(relevance) if relevance else None,
            "passes_quality_gate": bool(items) and target_rate >= .5,
            "finbert_scored": finbert_scored,
            "finbert_complete": bool(items) and finbert_scored == len(items)}


def _fundamental_quality(data, day):
    items = [item for item in data.get("evidence", []) if item.get("domain") == "fundamental"
             and item.get("available_at", "") < day]
    comparable = sum(item.get("comparative") is True for item in items)
    return {"items": len(items), "comparative_items": comparable,
            "passes_quality_gate": comparable > 0}


def coverage(data, analysis_date=None):
    day = analysis_date or data.get("requested_analysis_date")
    if not day:
        return {"research_ready": False, "formal_experiment_ready": False,
                "reason": "missing_analysis_date", "domains": {}, "backtest_ready": False,
                "all_horizons_ready": False,
                "fundamental_quality": {"items": 0, "comparative_items": 0,
                                        "passes_quality_gate": False},
                "sentiment_quality": {"items": 0, "ticker_mentions": 0, "ticker_mention_rate": 0.,
                                      "source_mapped_items": 0, "target_relevance_rate": 0.,
                                      "quality_rule": "source-target-v1",
                                      "median_relevance": None, "passes_quality_gate": False,
                                      "finbert_scored": 0, "finbert_complete": False}}
    past = [row for row in data["prices"] if row["date"] < day]
    future = [row for row in data["prices"] if row["date"] > day]
    counts = {domain: sum(item["domain"] == domain and item["available_at"] < day
                         and item.get("vintage_date", item["available_at"]) < day for item in data["evidence"])
              for domain in ("fundamental", "sentiment", "macro")}
    counts["technical"] = len(past)
    ready = len(past) >= 61 and all(counts[name] for name in ("fundamental", "sentiment", "macro"))
    sentiment_quality = _sentiment_quality(data, day)
    fundamental_quality = _fundamental_quality(data, day)
    historical = data["kind"] == "historical"
    horizons = {str(n): len(future) >= n + 1 for n in (30, 60, 90)}
    backtest_ready = horizons["60"]
    all_horizons_ready = all(horizons.values())
    formal_ready = (historical and ready and backtest_ready
                    and fundamental_quality["passes_quality_gate"]
                    and sentiment_quality["passes_quality_gate"]
                    and sentiment_quality["finbert_complete"])
    return {"research_ready": bool(ready), "formal_experiment_ready": bool(formal_ready),
            "domains": counts, "analysis_date": day,
            "historical": historical, "future_sessions": len(future),
            "backtest_ready": backtest_ready, "all_horizons_ready": all_horizons_ready,
            "horizons": horizons,
            "sentiment_quality": sentiment_quality, "fundamental_quality": fundamental_quality,
            "reason": ("formal_experiment_ready" if formal_ready else "evidence_ready"
                       if ready else "insufficient_pre_cutoff_evidence")}


def study_readiness(rows):
    by_case = {}
    for row in rows:
        key = row.get("ticker"), row.get("requested_analysis_date")
        if row.get("kind") != "historical" or key[0] not in TICKERS or key[1] not in QUARTER_DATES:
            continue
        c = row["coverage"]
        rank = (c.get("formal_experiment_ready", False), c["research_ready"],
                c.get("all_horizons_ready", False), c["backtest_ready"],
                c.get("fundamental_quality", {}).get("passes_quality_gate", False),
                c.get("sentiment_quality", {}).get("finbert_complete", False),
                sum(bool(n) for n in c["domains"].values()))
        previous = by_case.get(key)
        # Rows arrive newest first; prefer complete older snapshots to incomplete new ones.
        if previous is None or rank > previous["rank"]:
            by_case[key] = {**c, "rank": rank, "status": "complete" if c["research_ready"] else "partial",
                            "formal_status": "ready" if c.get("formal_experiment_ready") else
                                             "evidence_only" if c["research_ready"] else "partial",
                            "dataset_id": row["id"], "version": row["version"], "ticker": key[0],
                            "split": split_for_date(key[1])}
    tickers = []
    for ticker in TICKERS:
        complete = [day for day in QUARTER_DATES if by_case.get((ticker, day), {}).get("status") == "complete"]
        partial = [day for day in QUARTER_DATES if by_case.get((ticker, day), {}).get("status") == "partial"]
        formal = [day for day in QUARTER_DATES if by_case.get((ticker, day), {}).get("formal_status") == "ready"]
        tickers.append({"ticker": ticker, "complete": len(complete), "partial": len(partial),
                        "formal_ready": len(formal),
                        "missing": len(QUARTER_DATES) - len(complete) - len(partial),
                        "complete_dates": complete, "formal_ready_dates": formal, "partial_dates": partial})
    complete = sum(row["research_ready"] for row in by_case.values())
    target = len(TICKERS) * len(QUARTER_DATES)
    formal = sum(row.get("formal_experiment_ready", False) for row in by_case.values())
    cases = [{k: v for k, v in row.items() if k != "rank"} for row in by_case.values()]
    return {"universe": list(TICKERS), "dates": list(QUARTER_DATES), "target_cases": target,
            "complete_cases": complete, "evidence_complete_cases": complete,
            "formal_experiment_ready_cases": formal,
            "partial_cases": len(by_case) - complete, "missing_cases": target - len(by_case),
            # These counters describe independent data dimensions.  Do not
            # suppress available outcome, FinBERT, or SEC coverage merely
            # because another research domain is missing for the same case.
            "backtest_ready_cases": sum(row["backtest_ready"] for row in by_case.values()),
            "all_horizons_ready_cases": sum(row.get("all_horizons_ready", False) for row in by_case.values()),
            "finbert_ready_cases": sum(row.get("sentiment_quality", {}).get("finbert_complete", False)
                                       for row in by_case.values()),
            "comparable_fundamental_cases": sum(row.get("fundamental_quality", {}).get("passes_quality_gate", False)
                                                for row in by_case.values()),
            "cases": cases, "tickers": tickers,
            "temporal_splits": temporal_split_summary(cases),
            "note": "四域完整、可比較 SEC 基本面、FinBERT／新聞品質、60 日主要回測與 90 日次要回測分開計數；正式主分析需通過前四項，90 日另計。ASTS 只用於即時查詢。"}


def gap_inventory(rows):
    """Return every formal-study gap with an explicit, reproducible repair path."""
    readiness = study_readiness(rows)
    available = {(item["ticker"], item["analysis_date"]): item for item in readiness["cases"]}
    gaps = []
    for ticker in TICKERS:
        for analysis_date in QUARTER_DATES:
            item = available.get((ticker, analysis_date))
            if item is None:
                deficits = ["dataset", "technical", "fundamental", "sentiment", "macro"]
                status = "missing"
                dataset_id = None
            elif item.get("formal_experiment_ready"):
                continue
            else:
                status = item.get("formal_status", item.get("status", "partial"))
                dataset_id = item.get("dataset_id")
                domains = item.get("domains", {})
                deficits = [domain for domain in ("technical", "fundamental", "sentiment", "macro")
                            if not domains.get(domain)]
                sentiment = item.get("sentiment_quality", {})
                fundamental = item.get("fundamental_quality", {})
                if domains.get("sentiment") and not sentiment.get("passes_quality_gate"):
                    deficits.append("sentiment_relevance")
                if domains.get("sentiment") and not sentiment.get("finbert_complete"):
                    deficits.append("finbert")
                if domains.get("fundamental") and not fundamental.get("passes_quality_gate"):
                    deficits.append("fundamental_comparability")
                if item.get("research_ready") and not item.get("backtest_ready"):
                    deficits.append("60d_outcome")
                if not deficits:
                    deficits.append("formal_quality")
            gaps.append({
                "ticker": ticker,
                "analysis_date": analysis_date,
                "status": status,
                "dataset_id": dataset_id,
                "deficits": deficits,
                "collect_command": f".\\research.ps1 collect {ticker} {analysis_date} -UseFinbert",
            })
    return {
        "target_cases": readiness["target_cases"],
        "formal_ready_cases": readiness["formal_experiment_ready_cases"],
        "gap_cases": gaps,
        "gap_count": len(gaps),
        "note": "重新蒐集會建立不可變新版資料集；舊版本與既有實驗不會被改寫。",
    }
