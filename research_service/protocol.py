"""Immutable v3 protocol and information-symmetric decision call plan.

This module is deliberately independent of model and storage providers so a
saved protocol can be audited before any data download or inference occurs.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import hashlib
import json
import re
from typing import Literal

# The current backtest deliberately excludes ASTS because the frozen FNSPID
# input does not cover it.  The live workspace validates symbols separately and
# can still inspect ASTS or another US ticker.
STUDY_TICKERS = ("AAPL", "NVDA", "GOOGL", "MSFT", "AMZN", "JPM", "MCD", "LLY", "GE")
TICKERS = STUDY_TICKERS  # Backwards-compatible name used by the API and tests.
QUARTER_DATES = tuple(f"{year}-{suffix}" for year in range(2021, 2026) for suffix in ("03-31", "06-30", "09-30", "12-31"))
DOMAIN_NAMES = ("technical", "fundamental", "sentiment", "macro")
LIVE_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.:-]{0,31}$")
DEFAULT_RESEARCH_MODEL = "ollama/qwen3:14b"
SMALL_MODEL_PATTERN = re.compile(r"[:\-/](?:0\.\d+|[1-9]|1[0-3])b\b", re.IGNORECASE)
SWITCH_ROUND = 2

# These names are used only to measure whether a news headline is about the
# requested asset. They do not expand the research universe or alter a source.
COMPANY_NAMES = {
    "AAPL": ("Apple",), "NVDA": ("Nvidia", "NVIDIA"), "GOOGL": ("Alphabet", "Google"),
    "MSFT": ("Microsoft",), "AMZN": ("Amazon",), "JPM": ("JPMorgan", "JP Morgan"),
    "MCD": ("McDonald",), "LLY": ("Eli Lilly", "Lilly"),
    "GE": ("General Electric", "GE Aerospace"), "ASTS": ("AST SpaceMobile",),
}


@dataclass(frozen=True)
class StudyProtocol:
    # Display, extraction and validation rules change what enters a report.
    # Version them so a partially completed job cannot mix evidence rules.
    version: str = "v3-0913.1"
    study: Literal["study1", "study2"] = "study1"
    model: str = DEFAULT_RESEARCH_MODEL
    allow_small_model: bool = False
    temperature: float = 0.2
    voting_temperature: float = 0.8
    max_output_tokens: int = 512
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
    provider_retry_attempts: int = 2
    study_universe: tuple[str, ...] = STUDY_TICKERS

    def __post_init__(self):
        if self.version not in ("v3-0905.1", "v3-0905.2", "v3-0907.1", "v3-0907.2", "v3-0907.3", "v3-0908.1", "v3-0908.2", "v3-0909.1", "v3-0909.2", "v3-0909.3", "v3-0909.4", "v3-0909.5", "v3-0909.6", "v3-0909.7", "v3-0912.1", "v3-0913.1"):
            raise ValueError("Unsupported protocol version")
        if self.missing_data_policy not in ("allow_decision", "force_no_trade"):
            raise ValueError("Unsupported missing-data policy")
        if self.version == "v3-0905.1" and self.missing_data_policy != "force_no_trade":
            raise ValueError("v3-0905.1 always used the force_no_trade policy")
        if self.study not in ("study1", "study2") or not self.model.strip():
            raise ValueError("A supported study and one shared model are required")
        if SMALL_MODEL_PATTERN.search(self.model) and not self.allow_small_model:
            raise ValueError("研究用模型參數量過小；4B 級模型無法區分 A/B/C/D。請改用 14B 以上，或明確設定 allow_small_model=True 進行冒煙測試")
        if self.max_rounds != 3 or self.voting_samples not in (5, 7):
            raise ValueError("v3 fixes three rounds and supports voting n=5 or n=7")
        if self.primary_horizon != 60 or self.horizons != (30, 60, 90):
            raise ValueError("The primary endpoint must remain 60 days")
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

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()).hexdigest()

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


def is_switched(protocol: StudyProtocol, call: DecisionCall) -> bool:
    """Only arm D swaps stance, and only on the designated round."""
    return call.group == "D" and call.kind == "debate" and call.round == SWITCH_ROUND


def temperature_for(protocol: StudyProtocol, call: DecisionCall) -> float:
    """Only the self-consistency arm samples; other calls stay near-greedy."""
    return protocol.voting_temperature if call.group == "B" and call.kind == "sample" else protocol.temperature


def visible_history(call: DecisionCall, records: list[dict], protocol: StudyProtocol) -> list[dict]:
    """Never expose B samples, other groups, or a peer's current-round turn."""
    if protocol.switch_isolation and is_switched(protocol, call):
        # The switched turn must re-derive its case from the neutral report.
        # Reading the prior opponent would measure paraphrase, not completeness.
        return []
    if call.group in ("A", "B"):
        return []
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


def cases(tickers: tuple[str, ...] = STUDY_TICKERS) -> tuple[tuple[str, str], ...]:
    if not tickers or len(set(tickers)) != len(tickers) or any(ticker not in STUDY_TICKERS for ticker in tickers):
        raise ValueError("Select unique tickers from the approved universe")
    return tuple((ticker, analysis_date) for analysis_date in QUARTER_DATES for ticker in tickers)


def validate_case(ticker: str, analysis_date: str) -> None:
    if ticker not in STUDY_TICKERS or analysis_date not in QUARTER_DATES:
        raise ValueError("Case must use an approved ticker and 2021–2025 quarter anchor")
    date.fromisoformat(analysis_date)


def validate_live_symbol(symbol: str) -> str:
    symbol = str(symbol).strip().upper()
    if not LIVE_SYMBOL.fullmatch(symbol):
        raise ValueError("股票代號格式不正確")
    return symbol
