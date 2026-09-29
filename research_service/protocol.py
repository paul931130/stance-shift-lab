"""Immutable v3 protocol and information-symmetric decision call plan.

This module is deliberately independent of model and storage providers so a
saved protocol can be audited before any data download or inference occurs.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
import hashlib
import json
import re
from typing import Literal

from .errors import PreflightError

# The current backtest deliberately excludes ASTS because the frozen FNSPID
# input does not cover it. LLY was replaced by INTC in v3-0923.1: FNSPID has
# no LLY coverage between 2020-07 and 2023-11 (a 17-month gap Alpha Vantage's
# 2023-12-17 archive start cannot bridge), while INTC has the same continuous
# 2021-01..2023-12 FNSPID coverage as the other eight tickers.
STUDY_TICKERS = ("AAPL", "NVDA", "GOOGL", "MSFT", "AMZN", "JPM", "MCD", "INTC", "GE")
TICKERS = STUDY_TICKERS  # Backwards-compatible name used by the API and tests.
QUARTER_DATES = tuple(f"{year}-{suffix}" for year in range(2021, 2026) for suffix in ("03-31", "06-30", "09-30", "12-31"))
def _month_end_dates():
    dates = []
    for year in range(2021, 2026):
        for month in range(1, 13):
            following = date(year + (month == 12), month % 12 + 1, 1)
            dates.append((following - timedelta(days=1)).isoformat())
    return tuple(dates)


MONTH_END_DATES = _month_end_dates()
# Study designs. The quarterly design is the original 180-case study (60-session
# primary horizon, 90-day news window). The monthly design scales it to one
# month: 540 cases, a 20-session primary horizon that does not overlap the next
# case, and a 30-day news window. Robustness horizons keep the same ratios.
DESIGNS = {
    "quarterly": {"dates": QUARTER_DATES, "primary_horizon": 60, "horizons": (30, 60, 90), "news_window_days": 90},
    "monthly": {"dates": MONTH_END_DATES, "primary_horizon": 20, "horizons": (10, 20, 30), "news_window_days": 30},
}
QUARTERLY_VERSION = "v3-0930.3"
MONTHLY_VERSION = "v3-0930.4"
MONTHLY_VERSIONS = frozenset({"v3-0930.2", MONTHLY_VERSION})
# From v3-0930.1 the prompt carries FinBERT indicators computed over every eligible headline instead of a
# 12-headline sample (see data.research_inputs); earlier versions keep the headline sample.
INDICATOR_VERSIONS = ("v3-0930.1", "v3-0930.2", QUARTERLY_VERSION, MONTHLY_VERSION)
NUMERIC_CLAIM_VERSIONS = frozenset({QUARTERLY_VERSION, MONTHLY_VERSION})
DOMAIN_NAMES = ("technical", "fundamental", "sentiment", "macro")
BASE_RATE_MIN_WINDOWS = 8
DEFAULT_RESEARCH_MODEL = "ollama/qwen3:14b"
SMALL_MODEL_PATTERN = re.compile(r"[:\-/](?:0\.\d+|[1-9]|1[0-3])b\b", re.IGNORECASE)
# qwen3:8b has passed the project's structured-output and role-switch canary.
# Keep every other sub-14B model behind the explicit smoke-test override.
FORMAL_SMALL_MODEL_ALLOWLIST = frozenset({"ollama/qwen3:8b"})
SWITCH_ROUND = 2

# These names are used only to measure whether a news headline is about the
# requested asset. They do not expand the research universe or alter a source.
COMPANY_NAMES = {
    "AAPL": ("Apple",), "NVDA": ("Nvidia", "NVIDIA"), "GOOGL": ("Alphabet", "Google"),
    "MSFT": ("Microsoft",), "AMZN": ("Amazon",), "JPM": ("JPMorgan", "JP Morgan"),
    "MCD": ("McDonald",), "INTC": ("Intel",),
    "GE": ("General Electric", "GE Aerospace"), "ASTS": ("AST SpaceMobile",),
    "LLY": ("Eli Lilly", "Lilly"),  # retained for auditing datasets/jobs recorded before v3-0923.1.
}


@dataclass(frozen=True)
class StudyProtocol:
    # Display, extraction and validation rules change what enters a report.
    # Version them so a partially completed job cannot mix evidence rules.
    version: str = QUARTERLY_VERSION
    design: Literal["quarterly", "monthly"] = "quarterly"
    study: Literal["study1", "study2"] = "study1"
    model: str = DEFAULT_RESEARCH_MODEL
    allow_small_model: bool = False
    temperature: float = 0.2
    voting_temperature: float = 0.8
    max_output_tokens: int = 1024
    max_rounds: int = 3
    voting_samples: Literal[5, 7] = 7
    primary_horizon: int = 60
    horizons: tuple[int, ...] = (30, 60, 90)
    cost_models: tuple[str, ...] = ("zero", "corwin_schultz")
    anonymize_ticker: bool = False
    dataset_kind: Literal["historical", "synthetic"] = "historical"
    missing_data_policy: Literal["allow_decision", "force_no_trade"] = "allow_decision"
    allow_point_fundamental: bool = False
    confidence_floor: float | None = None
    volatility_ceiling: float = 0.80
    citation_pass_floor: float = 0.80
    news_relevance_floor: float = 0.35
    target_context_priority: bool = True
    switch_isolation: bool = True
    hold_band_sigma: float = 0.5
    action_source: Literal["model", "derived"] = "derived"
    spread_window: int = 20
    bootstrap_seed: int = 905
    bootstrap_replicates: int = 1999
    bootstrap_block_length: int = 20
    inference_seed: int = 905
    provider_retry_attempts: int = 3
    study_universe: tuple[str, ...] = STUDY_TICKERS

    def __post_init__(self):
        if self.version not in ("v3-0905.1", "v3-0905.2", "v3-0907.1", "v3-0907.2", "v3-0907.3", "v3-0908.1", "v3-0908.2", "v3-0909.1", "v3-0909.2", "v3-0909.3", "v3-0909.4", "v3-0909.5", "v3-0909.6", "v3-0909.7", "v3-0912.1", "v3-0913.1", "v3-0913.2", "v3-0922.1", "v3-0922.2", "v3-0922.3", "v3-0922.4", "v3-0923.1", "v3-0926.1", "v3-0926.2", "v3-0926.3", "v3-0926.4", "v3-0926.5", "v3-0926.6", "v3-0926.7", "v3-0927.1", "v3-0927.2", "v3-0929.1", "v3-0930.1", "v3-0930.2", QUARTERLY_VERSION, MONTHLY_VERSION):
            raise ValueError("Unsupported protocol version")
        if self.missing_data_policy not in ("allow_decision", "force_no_trade"):
            raise ValueError("Unsupported missing-data policy")
        if self.version == "v3-0905.1" and self.missing_data_policy != "force_no_trade":
            raise ValueError("v3-0905.1 always used the force_no_trade policy")
        if self.study not in ("study1", "study2") or not self.model.strip():
            raise ValueError("A supported study and one shared model are required")
        if (SMALL_MODEL_PATTERN.search(self.model)
                and self.model.strip().lower() not in FORMAL_SMALL_MODEL_ALLOWLIST
                and not self.allow_small_model):
            raise PreflightError("model_too_small", "模型參數量未達正式門檻（14B；qwen3:8b 除外）；若只是測試，請勾選「允許 14B 以下的模型」（allow_small_model=True）")
        if self.max_rounds != 3 or self.voting_samples not in (5, 7):
            raise ValueError("v3 fixes three rounds and supports voting n=5 or n=7")
        if self.design not in DESIGNS:
            raise ValueError("Unsupported study design")
        if ((self.design == "monthly") != (self.version in MONTHLY_VERSIONS)):
            raise ValueError(f"Monthly versions are {', '.join(sorted(MONTHLY_VERSIONS))}; quarterly protocols cannot use them")
        design = DESIGNS[self.design]
        if self.primary_horizon != design["primary_horizon"] or tuple(self.horizons) != design["horizons"]:
            raise ValueError(f"The {self.design} design fixes the primary endpoint at {design['primary_horizon']} sessions")
        if not 0 <= self.temperature <= 2 or not 0 <= self.voting_temperature <= 2 or self.voting_temperature < self.temperature or self.max_output_tokens < 64:
            raise ValueError("Invalid model generation parameters")
        if self.confidence_floor is not None and not 0 <= self.confidence_floor <= 1:
            raise ValueError("confidence_floor must be None or a probability")
        if not 0 < self.volatility_ceiling <= 5 or not 0 <= self.citation_pass_floor <= 1:
            raise ValueError("Invalid Gatekeeper threshold")
        if not 0 <= self.news_relevance_floor <= 1 or not 0 <= self.hold_band_sigma <= 3:
            raise ValueError("Invalid evidence or hold-band threshold")
        if self.action_source not in ("model", "derived") or not 2 <= self.spread_window <= 60:
            raise ValueError("Invalid action source or spread window")
        if self.bootstrap_replicates < 199 or self.bootstrap_block_length < 2:
            raise ValueError("Block bootstrap requires >=199 replicates and block length >=2")
        if self.inference_seed < 0 or not 1 <= self.provider_retry_attempts <= 3:
            raise ValueError("Inference seed must be non-negative and retry attempts must be between 1 and 3")
        if not self.cost_models or any(item not in ("zero", "corwin_schultz") for item in self.cost_models):
            raise ValueError("Unsupported transaction-cost model")
        if self.dataset_kind not in ("historical", "synthetic"):
            raise ValueError("Explicit dataset provenance is required")
        if tuple(self.study_universe) != STUDY_TICKERS:
            raise ValueError("v3-0907.3 fixes the current backtest universe to the nine FNSPID-covered stocks")

    @classmethod
    def monthly(cls, **overrides):
        """The monthly study design: month-end anchors, 20-session primary horizon, 30-day news window."""
        design = DESIGNS["monthly"]
        return cls(version=MONTHLY_VERSION, design="monthly", primary_horizon=design["primary_horizon"],
                   horizons=design["horizons"], **overrides)

    @property
    def analysis_dates(self) -> tuple[str, ...]:
        return DESIGNS[self.design]["dates"]

    @property
    def sentiment_indicators(self) -> bool:
        """Whether sentiment reaches the models as FinBERT indicators over all headlines (v3-0930.1+)."""
        return self.version in INDICATOR_VERSIONS

    @property
    def news_window_days(self) -> int:
        return DESIGNS[self.design]["news_window_days"]

    @property
    def fingerprint(self) -> str:
        payload = asdict(self)
        # Protocols saved before the design field existed are quarterly; leaving the
        # default out keeps their recorded hashes valid.
        if payload["design"] == "quarterly":
            del payload["design"]
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @property
    def compute_matched(self) -> bool:
        return self.voting_samples == 7


@dataclass(frozen=True)
class DecisionCall:
    key: str
    group: str
    kind: str
    agent: str
    stance: str
    round: int | None = None
    sample: int | None = None


def decision_plan(protocol: StudyProtocol) -> tuple[DecisionCall, ...]:
    calls = [DecisionCall("a-decision", "A", "decision", "decision", "NEUTRAL")]
    calls.extend(DecisionCall(f"b-sample-{sample}", "B", "sample", "decision", "NEUTRAL", sample=sample) for sample in range(1, protocol.voting_samples + 1))
    for group in ("C", "D"):
        for round_number in range(1, 4):
            for agent, original_stance in (("agent-a", "BULL"), ("agent-b", "BEAR")):
                swapped = group == "D" and round_number == SWITCH_ROUND
                stance = ("BEAR" if original_stance == "BULL" else "BULL") if swapped else original_stance
                calls.append(DecisionCall(f"{group.lower()}-r{round_number}-{agent}", group, "debate", agent, stance, round_number))
        calls.append(DecisionCall(f"{group.lower()}-adjudication", group, "adjudication", "adjudicator", "NEUTRAL"))
    return tuple(calls)


def protocol_is_current(protocol: dict) -> bool:
    """Whether a saved protocol is the current version of its own study design.

    Older versions stay readable but are never resumed on a newer engine. Each design has its
    own current version, so a quarterly and a monthly job never make each other look stale.
    """
    current = MONTHLY_VERSION if protocol.get("design", "quarterly") == "monthly" else QUARTERLY_VERSION
    return protocol.get("version") == current


def is_switched(protocol: StudyProtocol, call: DecisionCall) -> bool:
    """Only arm D swaps stance, and only on the designated round."""
    return call.group == "D" and call.kind == "debate" and call.round == SWITCH_ROUND


def temperature_for(protocol: StudyProtocol, call: DecisionCall) -> float:
    """Only the self-consistency arm samples; other calls stay near-greedy."""
    return protocol.voting_temperature if call.group == "B" and call.kind == "sample" else protocol.temperature


def visible_history(call: DecisionCall, records: list[dict], protocol: StudyProtocol) -> list[dict]:
    """Never expose B samples, other groups, or a peer's current-round turn.

    The switched D round is special: with switch_isolation on, the agent sees
    only ITS OWN prior turn, never its counterpart's. This is what "becoming
    your own opponent" means here -- the agent must confront the position it
    just argued, not paraphrase what the other side said (which would measure
    copying, not genuine self-rebuttal).
    """
    if call.group in ("A", "B"):
        return []
    if protocol.switch_isolation and is_switched(protocol, call):
        return [record for record in records if record["group"] == call.group
                and record.get("kind") == "debate" and record.get("agent") == call.agent
                and record["round"] < call.round]
    return [record for record in records if record["group"] == call.group
            and record.get("kind") == "debate"
            and (call.kind == "adjudication" or record["round"] < call.round)]


def decision_wave(protocol: StudyProtocol, records: list[dict]) -> tuple[DecisionCall, ...]:
    """Return every currently runnable call without crossing round dependencies."""
    plan = decision_plan(protocol)
    done = {record["key"] for record in records}
    ready = [call for call in plan if call.group in ("A", "B") and call.key not in done]
    for group in ("C", "D"):
        for round_number in range(1, 4):
            round_calls = [call for call in plan if call.group == group and call.round == round_number]
            missing = [call for call in round_calls if call.key not in done]
            if missing:
                ready.extend(missing)
                break
        else:
            adjudication = next(call for call in plan if call.group == group and call.kind == "adjudication")
            if adjudication.key not in done:
                ready.append(adjudication)
    order = {call.key: index for index, call in enumerate(plan)}
    return tuple(sorted(ready, key=lambda call: order[call.key]))


def cases(tickers: tuple[str, ...] = STUDY_TICKERS, design: str = "quarterly") -> tuple[tuple[str, str], ...]:
    if not tickers or len(set(tickers)) != len(tickers) or any(ticker not in STUDY_TICKERS for ticker in tickers):
        raise ValueError("Select unique tickers from the approved universe")
    return tuple((ticker, analysis_date) for analysis_date in DESIGNS[design]["dates"] for ticker in tickers)


def is_live_case_date(analysis_date: str) -> bool:
    """Today's date is the one non-quarter anchor allowed, for an ad-hoc,
    current-day read on a ticker. It is never added to `cases()`, so it can
    never enter the frozen 180-case study or its readiness statistics."""
    return analysis_date == date.today().isoformat()


def validate_case(ticker: str, analysis_date: str, design: str = "quarterly") -> None:
    if design not in DESIGNS:
        raise ValueError("Unsupported study design")
    if ticker not in STUDY_TICKERS or (analysis_date not in DESIGNS[design]["dates"] and not is_live_case_date(analysis_date)):
        anchor = "month-end" if design == "monthly" else "quarter"
        raise ValueError(f"Case must use an approved ticker and either a 2021–2025 {anchor} anchor or today's date")
    date.fromisoformat(analysis_date)
