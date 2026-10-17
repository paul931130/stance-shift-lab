"""RQ3 Domain-Specialized Debate on top of the frozen v3-1002.3 protocol.

The Generalist arms (C, D) debate over the whole locked Neutral Report. A
domain arm (C_domain with the fixed rule, D_domain with the role-switch rule)
instead runs one Bull/Bear debate per research domain over that domain's slice
of the SAME locked report (no new data, no new summary), asks one domain judge
per domain for a standardized Domain View, and lets the Final Aggregator
(``research_service.aggregator``) integrate the four views into one candidate
that goes through the unchanged Gatekeeper and backtest.

Nothing here edits a module covered by ``protocol.prompt_source_digest``: the
frozen v3-1002.3/1002.4 hashes stay valid. An RQ3 job instead stores the base
protocol unchanged plus ``config["domain_debate"]`` and its own hash
(``rq3_fingerprint``: base hash + settings + digest of the RQ3 modules), and
must be run by ``DomainDebateEngine``. A plain ``Engine`` refuses such a job
because its hash does not match the base protocol (fail closed).

Per arm and case the nominal call count is ``4 x (2 x 3 + 1) + 1 = 29``. A
domain without decision-eligible evidence gets an ``InsufficientInfo`` view
without a call, so actual calls may be lower.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import asdict, dataclass, fields
import hashlib
import json
from pathlib import Path
from typing import Literal

from jsonschema import ValidationError as JsonSchemaValidationError

from . import aggregator
from . import models
from .breaker import is_provider_failure
from .data import digest
from .engine import Engine, compute_usage, derive_action, gate, validation_hint
from .logging_config import get_logger
from .models import (_compact_history, _compact_report, _decision_evidence, alias_messages, evidence_aliases,
                     messages_for, prompt_text, validate_financial_interpretation, validate_financial_numbers)
from .protocol import (DOMAIN_NAMES, EVIDENCE_REF_VERSIONS, QUARTERLY_VERSION, SWITCH_ROUND, DecisionCall,
                       decision_plan, protocol_from, protocol_matches_fingerprint)
from .storage import now

logger = get_logger(__name__)

RQ3_VERSION = "rq3-1015.1"
DOMAIN_ARM_RULES = {"C_domain": "fixed", "D_domain": "switch"}
GENERALIST_ARM_FOR = {"C_domain": "C", "D_domain": "D"}
RQ3_SOURCE_MODULES = ("domain_debate", "aggregator", "rq3_controls")
PROMPT_VERSIONS = {"domain_prompt_version": ("domain-debate-v2",), "view_prompt_version": ("domain-view-v2",),
                   "aggregator_prompt_version": ("aggregator-v2",)}

VIEW_MARKER = "Domain View synthesizer"
DIRECTIONS = ("Buy", "Sell", "Abstain", "InsufficientInfo")
BINARY_DIRECTIONS = ("Buy", "Sell")
DEBATERS = (("agent-a", "BULL"), ("agent-b", "BEAR"))

DOMAIN_VIEW_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["direction", "expected_return_pct", "confidence", "supporting_evidence_ids",
                 "counter_evidence_ids", "uncertainty", "information_gaps", "rationale"],
    "properties": {
        "direction": {"type": "string", "enum": list(DIRECTIONS)},
        "expected_return_pct": {"type": ["number", "null"], "minimum": -60, "maximum": 60},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "supporting_evidence_ids": {"type": "array", "maxItems": 6, "items": {"type": "string"}},
        "counter_evidence_ids": {"type": "array", "maxItems": 6, "items": {"type": "string"}},
        "uncertainty": {"type": "string", "maxLength": 300},
        "information_gaps": {"type": "array", "maxItems": 4, "items": {"type": "string", "maxLength": 160}},
        "rationale": {"type": "string", "maxLength": 1500},
    },
}


def _install_view_schema():
    """Let the built-in provider request the Domain View schema without editing frozen models.py.

    ``models.generate`` asks ``models.output_schema_for`` for the response schema. The wrapper
    only answers for prompts that carry the Domain View marker and otherwise delegates, so every
    RQ1/RQ2 prompt gets exactly the schema it got before.
    """
    original = models.output_schema_for
    if getattr(original, "rq3_wrapper", False):
        return

    def output_schema_for(messages):
        if VIEW_MARKER in str(messages[0].get("content", "")):
            return deepcopy(DOMAIN_VIEW_SCHEMA)
        return original(messages)

    output_schema_for.rq3_wrapper = True
    output_schema_for.original = original
    models.output_schema_for = output_schema_for


_install_view_schema()


class NamespaceViolation(ValueError):
    """A domain agent cited evidence outside its own domain's namespace."""


# --- settings and hashes ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DomainDebateSettings:
    """RQ3 knobs, all part of an RQ3 job's hash.

    The four Generalist arms (A, B, C, D) always run unchanged, because the frozen call
    plan cannot be filtered without changing the v3-1002.3 hash. ``rule`` picks the
    domain arms: ``fixed`` -> C_domain, ``switch`` -> D_domain, ``both`` -> both; each is
    compared with its rule-matched Generalist arm (C vs C_domain, D vs D_domain).
    ``compute_matching`` only labels the resource metric the analysis plan treats as
    primary; nothing enforces or rebalances it.
    """
    rq3_version: str = RQ3_VERSION
    rule: Literal["fixed", "switch", "both"] = "both"
    domains: tuple[str, ...] = DOMAIN_NAMES
    view_generation: Literal["domain_judge"] = "domain_judge"
    domain_prompt_version: str = "domain-debate-v2"
    view_prompt_version: str = "domain-view-v2"
    aggregator_prompt_version: str = "aggregator-v2"
    aggregator_input: Literal["views", "views_and_transcripts"] = "views"
    aggregator_order: Literal["randomized", "fixed"] = "randomized"
    aggregator_memory: Literal["none", "same_arm_matured"] = "same_arm_matured"
    share_base_rates: bool = True
    compute_matching: Literal["unspecified", "nominal_calls", "total_tokens", "wall_time",
                              "report_frontier"] = "unspecified"
    include_controls: bool = False

    def __post_init__(self):
        object.__setattr__(self, "domains", tuple(self.domains))
        if self.rq3_version != RQ3_VERSION:
            raise ValueError("Unsupported RQ3 version")
        if self.rule not in ("fixed", "switch", "both"):
            raise ValueError("RQ3 domain rule must be fixed, switch or both")
        if not isinstance(self.include_controls, bool) or (self.include_controls and self.rule != "fixed"):
            raise ValueError("RQ3 v7 controls require the fixed rule")
        if self.domains != DOMAIN_NAMES:
            raise ValueError("RQ3 fixes the four research domains")
        if self.view_generation != "domain_judge":
            raise ValueError("Unsupported Domain View generation mode")
        if self.aggregator_input not in ("views", "views_and_transcripts"):
            raise ValueError("Unsupported aggregator input schema")
        if self.aggregator_order not in ("randomized", "fixed"):
            raise ValueError("Unsupported aggregator input order")
        if self.aggregator_memory not in ("none", "same_arm_matured"):
            raise ValueError("Unsupported aggregator memory scope")
        if self.compute_matching not in ("unspecified", "nominal_calls", "total_tokens", "wall_time",
                                         "report_frontier"):
            raise ValueError("Unsupported compute-matching label")
        for name, allowed in PROMPT_VERSIONS.items():
            if getattr(self, name) not in allowed:
                raise ValueError(f"Unknown {name}; its prompt text is not implemented")

    @property
    def domain_arms(self) -> tuple[str, ...]:
        return tuple(arm for arm, rule in DOMAIN_ARM_RULES.items() if self.rule in (rule, "both"))

    @classmethod
    def from_dict(cls, value):
        known = {item.name for item in fields(cls)}
        return cls(**{key: item for key, item in value.items() if key in known})


def settings_from_config(config):
    value = config.get("domain_debate")
    return None if value is None else DomainDebateSettings.from_dict(value)


def rq3_source_digest():
    package = Path(__file__).resolve().parent
    hasher = hashlib.sha256()
    for name in RQ3_SOURCE_MODULES:
        text = (package / f"{name}.py").read_bytes().replace(bytes([13, 10]), bytes([10]))
        hasher.update(f"research_service/{name}.py".encode() + bytes([0]) + text + bytes([0]))
    return hasher.hexdigest()


def rq3_fingerprint(protocol, settings):
    """RQ3 job hash: the unchanged base protocol hash, the RQ3 settings and the RQ3 source."""
    payload = {"base_protocol_hash": protocol.fingerprint, "domain_debate": asdict(settings),
               "rq3_source": rq3_source_digest()}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def config_matches_fingerprint(config):
    """Whether a stored job hash still matches this checkout, for RQ1/RQ2 and RQ3 jobs alike."""
    settings = settings_from_config(config)
    if settings is None:
        return protocol_matches_fingerprint(config.get("protocol", {}), config.get("protocol_hash"))
    try:
        return config.get("protocol_hash") == rq3_fingerprint(protocol_from(config["protocol"]), settings)
    except (KeyError, TypeError, ValueError):
        return False


def settings_from_request(value):
    """Validate RQ3 settings sent by a client; unknown keys are an error, not silently dropped."""
    unknown = sorted(set(value) - {item.name for item in fields(DomainDebateSettings)})
    if unknown:
        raise ValueError(f"未知的 RQ3 設定欄位：{', '.join(unknown)}")
    return DomainDebateSettings.from_dict(value)


def rq3_job_fields(protocol, settings):
    """The config fields that turn a prepared v3-1002.3 job into an RQ3 job."""
    if protocol.version != QUARTERLY_VERSION:
        raise ValueError(f"RQ3 只定義在季度 {QUARTERLY_VERSION} 協議上")
    return {"domain_debate": asdict(settings), "base_protocol_hash": protocol.fingerprint,
            "protocol_hash": rq3_fingerprint(protocol, settings)}


def rq3_job_config(protocol, settings, **config):
    """A job config for ``Store.create``; ``config`` holds ticker, analysis_date, dataset_id, ..."""
    if protocol.version not in EVIDENCE_REF_VERSIONS:
        raise ValueError("RQ3 builds on the v3-1002.3/1002.4 evidence-ID protocol")
    return {**config, "protocol": asdict(protocol), "domain_debate": asdict(settings),
            "base_protocol_hash": protocol.fingerprint, "protocol_hash": rq3_fingerprint(protocol, settings)}


# --- evidence namespaces -------------------------------------------------------------------------

def domain_report(report, domain, settings):
    """The slice of the locked Neutral Report one domain's agents may read."""
    calibration = report.get("decision_calibration", {}) or {}
    return {"ticker": report.get("ticker"), "analysis_date": report.get("analysis_date"),
            "domain_scope": domain,
            "research": {key: value for key, value in (report.get("research") or {}).items() if key == domain},
            "evidence": [item for item in report.get("evidence", []) if item.get("domain") == domain],
            "decision_calibration": {key: calibration[key] for key in ("technical", "sentiment")
                                     if key == domain and key in calibration},
            "base_rates": report.get("base_rates", {}) if settings.share_base_rates else {},
            "degraded_research_domains": [key for key in report.get("degraded_research_domains", []) if key == domain]}


def namespace(report, domain):
    """Decision-eligible evidence of one domain (the Generalist decision filter, restricted to it)."""
    return [item for item in report.get("evidence", []) if item.get("domain") == domain
            and (domain != "fundamental" or item.get("comparative") is True)]


def namespace_violations(evidence_ids, items):
    allowed = {item["evidence_id"] for item in items}
    return [value for value in evidence_ids if value not in allowed]


def check_namespace(evidence_ids, items, domain):
    violations = namespace_violations(evidence_ids, items)
    if violations:
        raise NamespaceViolation(f"{domain} 領域代理人引用 namespace 以外的 evidence_id：{violations[:5]}")


# --- plan ------------------------------------------------------------------------------------------

def prompt_group(arm):
    """Domain arms reuse the Generalist C/D debate prompts and validators verbatim."""
    return "D" if DOMAIN_ARM_RULES[arm] == "switch" else "C"


def debate_call(arm, domain, round_number, agent, original_stance):
    group = prompt_group(arm)
    swapped = group == "D" and round_number == SWITCH_ROUND
    stance = ("BEAR" if original_stance == "BULL" else "BULL") if swapped else original_stance
    return DecisionCall(f"{arm.lower()}-{domain}-r{round_number}-{agent}", group, "debate", agent, stance, round_number)


def view_key(arm, domain):
    return f"{arm.lower()}-{domain}-view"


def aggregator_key(arm):
    return f"{arm.lower()}-aggregator"


def plan_keys(protocol, settings):
    keys = []
    for arm in settings.domain_arms:
        for domain in DOMAIN_NAMES:
            for round_number in range(1, protocol.max_rounds + 1):
                keys.extend(debate_call(arm, domain, round_number, agent, stance).key for agent, stance in DEBATERS)
            keys.append(view_key(arm, domain))
        keys.append(aggregator_key(arm))
    return keys


def nominal_calls(protocol, settings):
    """Planned model calls per arm (excluding the shared research layer and any retry)."""
    debate = 2 * protocol.max_rounds
    result = {"A": 1, "B": protocol.voting_samples, "C": debate + 1, "D": debate + 1}
    result.update({arm: len(DOMAIN_NAMES) * (debate + 1) + 1 for arm in settings.domain_arms})
    if settings.include_controls:
        from .rq3_controls import CONTROL_CALLS
        result.update(CONTROL_CALLS)
    return result


def pending(settings, state):
    done = {record["key"] for record in state.get("domain_records", [])}
    from . import rq3_controls
    return (any(aggregator_key(arm) not in done for arm in settings.domain_arms)
            or (settings.include_controls and rq3_controls.pending(state)))


# --- prompts ---------------------------------------------------------------------------------------

def debate_messages(call, sliced, records, protocol, settings, domain):
    messages = messages_for(call, sliced, records, [], protocol)
    messages[0] = {**messages[0], "content": messages[0]["content"] + (
        f" Domain specialization ({settings.domain_prompt_version}): you debate only the {domain} domain. "
        f"The report below contains only {domain} evidence; argue the {protocol.primary_horizon}-session direction "
        "from that domain alone and cite only its evidence IDs. Other domains are argued by separate debaters "
        "and integrated later, so do not import conclusions about them.")}
    return messages


def view_messages(domain, sliced, records, protocol, settings):
    horizon = protocol.primary_horizon
    system = (
        f"You are the {VIEW_MARKER} for the {domain} domain in a fixed historical experiment "
        f"({settings.view_prompt_version}). A Bull and a Bear debated only {domain} evidence; read that debate and "
        f"the {domain} evidence in the report. Using only that evidence, state this domain's view of the target's "
        f"return over the next {horizon} trading sessions; do not use remembered future facts. Shorter-horizon "
        f"indicators may be evidence, but the view is about {horizon} sessions only. "
        "direction is Buy, Sell, Abstain (evidence exists but supports no defensible direction) or InsufficientInfo "
        f"(this domain's evidence cannot speak to a {horizon}-session direction). Abstain and InsufficientInfo are "
        "legitimate answers for a domain view, not failures; never force Buy or Sell. Assigned Bull/Bear roles and "
        "how often a side argued are not evidence: weigh only what the cited evidence supports. "
        "For Buy expected_return_pct must be positive and for Sell negative; for Abstain or InsufficientInfo it may "
        "be null. supporting_evidence_ids support the direction (at least one for Buy or Sell); counter_evidence_ids "
        "point against it. Use only supplied evidence IDs exactly. "
        "Do not restate source numbers in prose: every reader also receives the evidence list with the exact "
        "values. Refer to a fact by its evidence ID instead, e.g. \"momentum turned negative (E3)\". "
        f"Keep rationale under {protocol.rationale_chars or 320} characters. "
        "Return one compact JSON object with direction, expected_return_pct (number or null, -60..60), confidence "
        "(0..1), supporting_evidence_ids (array), counter_evidence_ids (array), uncertainty (string under 300 "
        "characters), information_gaps (array of at most 4 short strings), rationale (string).")
    debate = [record for record in records if record.get("kind") == "debate"]
    payload = {"domain": domain, "report": _compact_report(sliced),
               "debate": _compact_history(debate, protocol.rationale_chars or 320)}
    return [{"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)}]


# --- validation ------------------------------------------------------------------------------------

def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_view(result, items, domain, context=None):
    """Validate one Domain View against its schema rules and the domain namespace.

    As in v3-1002.3 decisions, numbers in prose are recorded (``unsupported_numbers``),
    never removed or retried; citations outside the namespace are rejected.
    """
    if not isinstance(result, dict) or result.get("direction") not in DIRECTIONS:
        raise ValueError("Domain View direction 須為 Buy、Sell、Abstain 或 InsufficientInfo")
    direction = result["direction"]
    confidence = result.get("confidence")
    if not _number(confidence) or not 0 <= confidence <= 1:
        raise ValueError("Domain View confidence 須介於 0 與 1")
    expected = result.get("expected_return_pct")
    if direction in BINARY_DIRECTIONS:
        if not _number(expected) or not -60 <= expected <= 60:
            raise ValueError("Buy/Sell Domain View 須提供 -60..60 的 expected_return_pct")
        if (direction == "Buy" and expected <= 0) or (direction == "Sell" and expected >= 0):
            raise ValueError("Domain View expected_return_pct 與 direction 方向不一致")
    elif expected is not None and (not _number(expected) or not -60 <= expected <= 60):
        raise ValueError("Domain View expected_return_pct 須為 null 或 -60..60")
    lists = {}
    for key in ("supporting_evidence_ids", "counter_evidence_ids", "information_gaps"):
        value = result.get(key)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"Domain View {key} 格式不正確")
        lists[key] = value
    for key in ("uncertainty", "rationale"):
        if not isinstance(result.get(key), str):
            raise ValueError(f"Domain View {key} 格式不正確")
    if not result["rationale"].strip():
        raise ValueError("Domain View 未提供 rationale")
    if direction in BINARY_DIRECTIONS and not lists["supporting_evidence_ids"]:
        raise ValueError("Buy/Sell Domain View 須引用至少一筆支持證據")
    cited = list(dict.fromkeys(lists["supporting_evidence_ids"] + lists["counter_evidence_ids"]))
    check_namespace(cited, items, domain)
    proxy = {"evidence_ids": cited, "rationale": result["rationale"], "summary": result["uncertainty"],
             "risks": list(lists["information_gaps"])}
    validate_financial_interpretation(proxy, items)
    unsupported = None
    if any(item.get("domain") == "fundamental" and item["evidence_id"] in cited for item in items):
        try:
            validate_financial_numbers(dict(proxy), items, context)
        except ValueError as error:
            unsupported = str(error)[:200]  # record only, never removed
    view = {"domain": domain, "direction": direction, "expected_return_pct": expected,
            "confidence": confidence, "supporting_evidence_ids": lists["supporting_evidence_ids"],
            "counter_evidence_ids": lists["counter_evidence_ids"], "uncertainty": result["uncertainty"],
            "information_gaps": lists["information_gaps"], "rationale": result["rationale"], "evidence_ids": cited,
            "binary": direction in BINARY_DIRECTIONS, "invalid_evidence_ids": []}
    if unsupported:
        view["unsupported_numbers"] = unsupported
    return view


def missing_view(domain, reason):
    """A deterministic view for a domain with nothing to debate; no model call is made."""
    return {"domain": domain, "direction": "InsufficientInfo", "expected_return_pct": None, "confidence": 0.0,
            "supporting_evidence_ids": [], "counter_evidence_ids": [],
            "uncertainty": "No decision-eligible evidence in this domain for this case.",
            "information_gaps": [reason], "rationale": "Deterministic: the domain debate was skipped.",
            "evidence_ids": [], "binary": False, "invalid_evidence_ids": [], "deterministic": True}


def _unalias_view(result, aliases):
    if not isinstance(result, dict):
        return result
    reverse = {alias: evidence_id for evidence_id, alias in aliases.items()}
    result = dict(result)
    for key in ("supporting_evidence_ids", "counter_evidence_ids"):
        if isinstance(result.get(key), list):
            result[key] = [reverse.get(value, value) if isinstance(value, str) else value for value in result[key]]
    return result


class DomainDebateEngine(Engine):
    """The standard engine plus the RQ3 domain stage; jobs without ``domain_debate`` run unchanged."""

    def advance(self, job):
        settings = settings_from_config(job["config"])
        if settings is None:
            return super().advance(job)
        config = job["config"]
        protocol = protocol_from(config["protocol"])
        expected = rq3_fingerprint(protocol, settings)
        if config.get("protocol_hash") != expected:
            raise ValueError("此 RQ3 工作的協議/RQ3 source fingerprint 與目前程式不符；不可續跑")
        # The base engine verifies the frozen base protocol; step() restores the RQ3 hash so
        # memory, case results and the trace stay separate from RQ1 jobs.
        proxy = {**job, "config": {**config, "protocol_hash": protocol.fingerprint, "_rq3_protocol_hash": expected}}
        return super().advance(proxy)

    def step(self, graph):
        job = graph["job"]
        settings = settings_from_config(job["config"])
        if settings is None:
            return super().step(graph)
        config = dict(job["config"])
        if "_rq3_protocol_hash" in config:
            config["protocol_hash"] = config.pop("_rq3_protocol_hash")
        graph = {**graph, "job": {**job, "config": config}}
        state = graph["state"]
        protocol = protocol_from(config["protocol"])
        if ("report" in state and "decisions" not in state
                and len(state["records"]) >= len(decision_plan(protocol)) and pending(settings, state)):
            done = {record["key"] for record in state.get("domain_records", [])}
            if any(aggregator_key(arm) not in done for arm in settings.domain_arms):
                label, workers = self.domain_wave(protocol, settings, config, state)
            else:
                from . import rq3_controls
                label, workers = rq3_controls.wave(self, protocol, config, state)
            state["trace"].append({"node": label, "at": now(), "protocol_hash": config["protocol_hash"],
                                   "report_hash": state.get("report_hash"), "parallel_workers": self.parallel_workers,
                                   "effective_workers": workers})
            return {"state": state}
        had_inputs, had_decisions = "inputs" in state, "decisions" in state
        result = super().step(graph)
        state = result["state"]
        if not had_inputs and "memory" in state:
            state["memory"].update({arm: self.store.memory(config, arm) for arm in settings.domain_arms})
            if settings.include_controls:
                from .rq3_controls import CONTROL_CALLS
                state["memory"].update({arm: self.store.memory(config, arm) for arm in CONTROL_CALLS})
        if not had_decisions and "decisions" in state:
            state["decisions"].update(domain_decisions(protocol, settings, state))
            if settings.include_controls:
                from . import rq3_controls
                state["decisions"].update(rq3_controls.decisions(protocol, state))
            state["rq3_diagnostics"] = case_diagnostics(protocol, settings, state)
        return result

    # --- one dependency wave of every domain arm ---

    def _ready(self, protocol, settings, state):
        report = state["report"]
        records = state.setdefault("domain_records", [])
        done = {record["key"] for record in records}
        ready = []
        for arm in settings.domain_arms:
            for domain in DOMAIN_NAMES:
                key = view_key(arm, domain)
                if key in done:
                    continue
                sliced = domain_report(report, domain, settings)
                items = namespace(report, domain)
                if not items or not _decision_evidence(sliced):
                    reason = ("no decision-eligible evidence in the locked report" if not items else
                              "no evidence of this domain is shown in the decision view")
                    records.append({"key": key, "arm": arm, "domain": domain, "kind": "view",
                                    "agent": "domain-judge", "stance": "NEUTRAL", "round": None,
                                    "group": prompt_group(arm), "output": missing_view(domain, reason),
                                    "audit": {"deterministic": True, "reason": reason},
                                    "report_hash": state.get("report_hash"), "completed_at": now()})
                    done.add(key)
                    continue
                domain_records = [record for record in records if record["arm"] == arm and record["domain"] == domain]
                for round_number in range(1, protocol.max_rounds + 1):
                    calls = [debate_call(arm, domain, round_number, agent, stance) for agent, stance in DEBATERS]
                    missing = [call for call in calls if call.key not in done]
                    if missing:
                        ready.extend(("debate", arm, domain, call, sliced, items, domain_records) for call in missing)
                        break
                else:
                    ready.append(("view", arm, domain, None, sliced, items, domain_records))
            if aggregator_key(arm) not in done and all(view_key(arm, domain) in done for domain in DOMAIN_NAMES):
                ready.append(("aggregate", arm, None, None, None, None,
                              [record for record in records if record["arm"] == arm]))
        return ready

    def domain_wave(self, protocol, settings, config, state):
        ready = self._ready(protocol, settings, state)
        local = self.uses_builtin_provider and protocol.model.startswith("ollama/")
        if local:
            ready = ready[:protocol.ollama_parallel or self.ollama_parallel]
        prepared = {}
        for kind, arm, domain, call, sliced, items, records in ready:
            if kind == "debate":
                own = next((record for record in records if record.get("agent") == call.agent
                            and record.get("round") == 1 and record["kind"] == "debate"), None)
                prepared[call.key] = (kind, arm, domain, call,
                                      debate_messages(call, sliced, records, protocol, settings, domain), items, own)
            elif kind == "view":
                prepared[view_key(arm, domain)] = (kind, arm, domain, None,
                                                   view_messages(domain, sliced, records, protocol, settings),
                                                   items, None)
            else:
                built = aggregator.build(protocol, settings, config, state, arm, records)
                prepared[aggregator_key(arm)] = (kind, arm, None, built, built["messages"], built["evidence"], None)

        def run(key, kind, arm, domain, call, messages, items, own):
            if kind == "debate":
                result, audit = self.validated_decision(protocol, call, messages, items, own_round1=own)
                check_namespace(result["evidence_ids"], items, domain)
                audit["namespace"] = {"domain": domain, "allowed": len(items),
                                      "rejected_attempts": sum("evidence_id" in failure.get("message", "")
                                                               for failure in audit.get("validation_retries", []))}
                return result, audit
            if kind == "view":
                return self.validated_view(protocol, key, messages, items, domain)
            return aggregator.run(self, protocol, call)

        completed, failures, provider_failures = {}, [], []
        workers = max(1, min(self.parallel_workers, len(prepared) or 1))
        if local:
            workers = min(workers, protocol.ollama_parallel or self.ollama_parallel)
        if prepared:
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="domain-debate") as pool:
                futures = {pool.submit(run, key, *value): key for key, value in prepared.items()}
                for future in as_completed(futures):
                    key = futures[future]
                    try:
                        completed[key] = future.result()
                    except Exception as error:
                        logger.error("domain debate failure call=%s: %s: %s", key, type(error).__name__, error)
                        failures.append(f"{key}: {type(error).__name__}: {error}")
                        provider_failures.append(is_provider_failure(error))
                        attempt_audit = getattr(error, "model_attempt_audit", None)
                        if attempt_audit:
                            state.setdefault("failed_model_calls", []).append(
                                {"key": key, "group": prepared[key][1], "domain": prepared[key][2],
                                 "failed_model_call": True, "audit": attempt_audit})
        order = {key: index for index, key in enumerate(plan_keys(protocol, settings))}
        for key in sorted(completed, key=lambda value: order[value]):
            kind, arm, domain, call, _, _, _ = prepared[key]
            result, audit = completed[key]
            base = (asdict(call) if kind == "debate" else
                    {"key": key, "group": prompt_group(arm), "kind": "view" if kind == "view" else "aggregation",
                     "agent": "domain-judge" if kind == "view" else "aggregator", "stance": "NEUTRAL", "round": None})
            state["domain_records"].append({**base, "arm": arm, "domain": domain, "output": result, "audit": audit,
                                            "report_hash": state.get("report_hash"), "completed_at": now()})
        if failures:
            state["_step_error"] = "；".join(failures)
            state["_step_provider_failure"] = any(provider_failures)
        return "domain_debate_wave[" + ",".join(prepared) + "]", workers

    def validated_view(self, protocol, key, messages, items, domain):
        """One Domain View with the same bounded, audited retry policy as decisions."""
        aliases = evidence_aliases(items)
        allowed_ids = [aliases[item["evidence_id"]] for item in items]
        failures, attempt_messages = [], messages
        for attempt in range(1, protocol.provider_retry_attempts + 1):
            retry_key = key if attempt == 1 else f"{key}:validation-retry-{attempt}"
            audit = None
            try:
                result, audit = self.call_model(protocol, alias_messages(attempt_messages, aliases), retry_key,
                                                protocol.temperature)
                view = validate_view(json.loads(json.dumps(_unalias_view(result, aliases))), items, domain,
                                     prompt_text(messages))
                audit = dict(audit)
                audit["validation_retries"] = failures
                if view.get("unsupported_numbers"):
                    audit["unsupported_numbers"] = view["unsupported_numbers"]
                return view, audit
            except (ValueError, JsonSchemaValidationError, TypeError) as error:
                failure = {"attempt": attempt, "error_type": type(error).__name__, "message": str(error)[:200],
                           "call_key": retry_key}
                if audit:
                    failure.update({name: audit[name] for name in ("seed", "prompt_hash") if name in audit})
                    failure["raw_response_hash"] = digest(audit.get("raw_response", ""))
                    failure["usage"] = audit.get("usage", {})
                    failure["provider_attempts"] = audit.get("provider_attempts", 1)
                    failure["attempts"] = audit.get("attempts", [])
                failures.append(failure)
                if attempt >= protocol.provider_retry_attempts:
                    if audit:
                        error.model_attempt_audit = {"provider_attempts": failure["provider_attempts"],
                                                     "attempts": failure["attempts"], "usage": failure["usage"],
                                                     "validation_retries": failures[:-1]}
                    raise
                attempt_messages = [*messages, {"role": "user", "content":
                    "The previous Domain View was rejected by validation. Return a new complete JSON object. "
                    f"Cite only {domain} evidence; copy evidence IDs exactly from this allowed list only: "
                    f"{json.dumps(allowed_ids, ensure_ascii=False)}. Validation error: {validation_hint(error)}"}]


def domain_decisions(protocol, settings, state):
    """Each domain arm's aggregator output, prepared and gated exactly like a Generalist candidate."""
    lookup = {record["key"]: record for record in state.get("domain_records", [])}
    hold_band_pct = state["inputs"]["base_rates"]["hold_band_pct"]
    decisions = {}
    for arm in settings.domain_arms:
        if aggregator_key(arm) not in lookup:
            continue
        candidate = lookup[aggregator_key(arm)]["output"]
        model_action = candidate["action"]
        derived = derive_action(candidate["expected_return_pct"], hold_band_pct)
        prepared = {**candidate, "model_action": model_action, "derived_action": derived,
                    "action": derived if protocol.action_source == "derived" else model_action,
                    "action_disagreement": model_action != derived, "hold_band_pct": hold_band_pct}
        decisions[arm] = gate(prepared, state["inputs"], state["memory"].get(arm, []), protocol)
    return decisions


# --- diagnostics ---------------------------------------------------------------------------------

def agreement(views, final_action=None):
    """4:0 / 3:1 / 2:2 over valid binary views only; abstentions are counted separately."""
    directions = {view["domain"]: view["direction"] for view in views}
    buy = sum(value == "Buy" for value in directions.values())
    sell = sum(value == "Sell" for value in directions.values())
    valid = buy + sell
    pattern = f"{max(buy, sell)}:{min(buy, sell)}" if valid == len(DOMAIN_NAMES) else None
    majority = "Buy" if buy > sell else "Sell" if sell > buy else ("tie" if valid else None)
    if final_action is None or majority is None:
        relation = None
    elif final_action not in BINARY_DIRECTIONS:
        relation = "final_not_directional"
    elif majority == "tie":
        relation = "no_majority"
    else:
        relation = "follows_majority" if final_action == majority else "against_majority"
    return {"directions": directions, "buy": buy, "sell": sell, "valid_binary": valid,
            "abstain": sum(value == "Abstain" for value in directions.values()),
            "insufficient_info": sum(value == "InsufficientInfo" for value in directions.values()),
            "pattern": pattern,
            "pattern_note": None if pattern else f"only {valid} of {len(DOMAIN_NAMES)} views are binary; "
                                                 "not classified as 4:0/3:1/2:2",
            "majority": majority, "final_relation": relation}


def _usage(records, failed=()):
    """engine.compute_usage over arbitrary records, so every arm uses one accounting rule."""
    relabel = [{**record, "group": "A"} for record in records]
    relabel_failed = [{**record, "group": "A"} for record in failed]
    return compute_usage(relabel, relabel_failed)["A"]


def _seconds(record):
    return _usage([record])["wall_seconds"]


def _path(waves):
    """Critical path: sum over dependent waves of the slowest call in each wave (None if unknown)."""
    total = 0.
    for wave in waves:
        values = [_seconds(record) for record in wave if not (record.get("audit") or {}).get("deterministic")]
        if any(value is None for value in values):
            return None
        total += max(values, default=0.)
    return total


def resources(records, failed, nominal, critical_path):
    model_records = [record for record in records if not (record.get("audit") or {}).get("deterministic")]
    usage = _usage(model_records, failed)
    prompt, completion = usage["prompt_tokens"], usage["completion_tokens"]
    return {"nominal_calls": nominal, "completed_calls": usage["completed_calls"],
            "deterministic_skips": len(records) - len(model_records),
            "logical_calls": usage["logical_calls"], "provider_attempts": usage["provider_attempts"],
            "validation_retry_calls": usage["validation_retry_calls"],
            "failed_logical_calls": usage["failed_logical_calls"],
            "prompt_tokens": prompt, "completion_tokens": completion,
            "total_tokens": None if prompt is None or completion is None else prompt + completion,
            "missing_usage_attempts": usage["missing_usage_attempts"],
            "sum_call_seconds": usage["wall_seconds"], "critical_path_seconds": critical_path,
            "duration_source": "client_monotonic per provider attempt (engine.compute_usage)"}


def case_diagnostics(protocol, settings, state):
    """Agreement and full resource accounting for every arm of one RQ3 case."""
    planned = nominal_calls(protocol, settings)
    failed = state.get("failed_model_calls", [])
    research_records = [{"key": f"research-{domain}", "audit": item.get("audit")}
                        for domain, item in (state.get("research") or {}).items()
                        if isinstance(item, dict) and isinstance(item.get("audit"), dict)
                        and not item["audit"].get("fallback") and item["audit"].get("usage") is not None]
    research_failed = [{"key": f"research-{domain}", "audit": item["audit"]["failed_model_audit"]}
                       for domain, item in (state.get("research") or {}).items()
                       if isinstance(item, dict) and isinstance(item.get("audit"), dict)
                       and item["audit"].get("failed_model_audit")]
    research = resources(research_records, research_failed, None, _path([research_records]))
    arms = {}
    for group in "ABCD":
        records = [record for record in state["records"] if record["group"] == group]
        if group in "AB":
            waves = [records]
        else:
            waves = ([[record for record in records if record.get("round") == number]
                      for number in range(1, protocol.max_rounds + 1)]
                     + [[record for record in records if record.get("kind") == "adjudication"]])
        arms[group] = resources(records, [item for item in failed if item.get("group") == group],
                                planned[group], _path(waves))
    domain_records = state.get("domain_records", [])
    decisions = state.get("decisions", {})
    views = {}
    for arm in settings.domain_arms:
        arm_records = [record for record in domain_records if record["arm"] == arm]
        chains = {domain: [[record for record in arm_records if record["domain"] == domain
                            and record.get("round") == number] for number in range(1, protocol.max_rounds + 1)]
                  + [[record for record in arm_records if record["domain"] == domain and record["kind"] == "view"]]
                  for domain in DOMAIN_NAMES}
        aggregate = [record for record in arm_records if record["kind"] == "aggregation"]
        paths = [_path(chain) for chain in chains.values()]
        tail = _path([aggregate])
        critical = None if tail is None or any(path is None for path in paths) else max(paths, default=0.) + tail
        arm_failed = [item for item in failed if item.get("group") == arm]
        summary = resources(arm_records, arm_failed, planned[arm], critical)
        summary["per_domain"] = {
            domain: resources([record for record in arm_records if record["domain"] == domain],
                              [item for item in arm_failed if item.get("domain") == domain],
                              2 * protocol.max_rounds + 1, _path(chain))
            for domain, chain in chains.items()}
        arms[arm] = summary
        decision = decisions.get(arm, {})
        views[arm] = {**agreement([record["output"] for record in arm_records if record["kind"] == "view"],
                                  decision.get("candidate_action")),
                      "candidate_action": decision.get("candidate_action"), "gated_action": decision.get("action"),
                      "aggregator": next((record["audit"].get("aggregator") for record in aggregate), None)}
    if settings.include_controls:
        from .rq3_controls import CONTROL_CALLS
        for arm, nominal in CONTROL_CALLS.items():
            records = [r for r in state.get("control_records", []) if r["arm"] == arm]
            arms[arm] = resources(records, [r for r in failed if r.get("group") == arm], nominal,
                                  _path([[record] for record in records]))
    for summary in arms.values():
        first, second = research["critical_path_seconds"], summary["critical_path_seconds"]
        summary["end_to_end_critical_path_seconds"] = None if first is None or second is None else first + second
    metrics = ("nominal_calls", "provider_attempts", "total_tokens", "sum_call_seconds", "critical_path_seconds")
    pairs = []
    for arm in settings.domain_arms:
        generalist = GENERALIST_ARM_FOR[arm]
        ratios = {}
        for metric in metrics:
            numerator, denominator = arms[arm].get(metric), arms[generalist].get(metric)
            ratios[metric] = numerator / denominator if _number(numerator) and _number(denominator) and denominator else None
        pairs.append({"rule": DOMAIN_ARM_RULES[arm], "generalist": generalist, "domain": arm,
                      "domain_over_generalist": ratios})
    if settings.include_controls:
        for control in ("C_budget", "C_partition"):
            pairs.append({"rule": "fixed", "generalist": control, "domain": "C_domain",
                          "domain_over_generalist": {}})
    return {"rq3_version": settings.rq3_version, "settings": asdict(settings), "nominal_calls": planned,
            "shared_research": research, "resources": arms, "agreement": views, "rule_matched_pairs": pairs,
            "view_directions": dict(Counter(record["output"]["direction"] for record in domain_records
                                            if record["kind"] == "view")),
            "compute_matching": {"declared": settings.compute_matching, "enforced": False,
                                 "note": "Calls, retries, tokens and latency are reported for every arm; the "
                                         "engine does not rebalance any budget."}}
