"""Temporal dataset roles for reproducible model construction and evaluation.

The research engine is an inference system rather than a trainable classifier,
so these roles describe which historical cases may be used for prompt/model
selection and which cases are held out for the final evaluation.  The mapping
is deliberately based on the analysis date, never on when a snapshot happened
to be downloaded.
"""
from __future__ import annotations

from datetime import date

from .protocol import QUARTER_DATES, TICKERS


SPLIT_SCHEMA = "stance-shift-temporal-split/v1"
SPLIT_DEFINITIONS = {
    "training": {
        "label": "Training",
        "years": (2021, 2022, 2023),
        "purpose": "建構提示詞、規則與候選模型；不得讀取 validation/test 結果。",
        "frozen": False,
    },
    "validation": {
        "label": "Validation",
        "years": (2024,),
        "purpose": "調整超參數與門檻；不得用於最後成績宣告。",
        "frozen": False,
    },
    "test": {
        "label": "Test",
        "years": (2025,),
        "purpose": "模型與設定凍結後的獨立最終評估。",
        "frozen": True,
    },
}


def classify_analysis_date(analysis_date: str) -> str:
    """Return a temporal role, or ``live`` for a non-quarter live case."""
    try:
        parsed = date.fromisoformat(str(analysis_date))
    except (TypeError, ValueError):
        return "live"
    if str(analysis_date) not in QUARTER_DATES:
        return "live"
    for name, definition in SPLIT_DEFINITIONS.items():
        if parsed.year in definition["years"]:
            return name
    return "live"


def split_for_date(analysis_date: str) -> str:
    """Return the formal split for a protocol quarter date.

    Live dates are intentionally rejected here so a current observation cannot
    silently enter the historical train/validation/test counts.
    """
    split = classify_analysis_date(analysis_date)
    if split == "live":
        raise ValueError("只有 2021–2025 季末研究日可以加入時間切分；即時分析屬於 live")
    return split


def temporal_split_summary(cases: list[dict]) -> dict:
    """Aggregate readiness independently for each temporal split."""
    result = {}
    for name, definition in SPLIT_DEFINITIONS.items():
        target = len(TICKERS) * len(definition["years"]) * 4
        result[name] = {
            "label": definition["label"],
            "years": list(definition["years"]),
            "purpose": definition["purpose"],
            "frozen": definition["frozen"],
            "target_cases": target,
            "available_cases": 0,
            "evidence_complete_cases": 0,
            "formal_ready_cases": 0,
            "partial_cases": 0,
            "missing_cases": target,
            "finbert_ready_cases": 0,
            "backtest_ready_cases": 0,
            "all_horizons_ready_cases": 0,
        }
    for case in cases:
        split = case.get("split") or classify_analysis_date(case.get("analysis_date"))
        if split not in result:
            continue
        item = result[split]
        item["available_cases"] += 1
        if case.get("research_ready"):
            item["evidence_complete_cases"] += 1
        else:
            item["partial_cases"] += 1
        if case.get("formal_experiment_ready"):
            item["formal_ready_cases"] += 1
        if case.get("sentiment_quality", {}).get("finbert_complete"):
            item["finbert_ready_cases"] += 1
        if case.get("backtest_ready"):
            item["backtest_ready_cases"] += 1
        if case.get("all_horizons_ready"):
            item["all_horizons_ready_cases"] += 1
    for item in result.values():
        item["missing_cases"] = item["target_cases"] - item["available_cases"]
    return {
        "schema": SPLIT_SCHEMA,
        "test_frozen": True,
        "basis": "requested_analysis_date",
        "splits": result,
    }

