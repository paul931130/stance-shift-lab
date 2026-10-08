"""RQ2 Model Router: per-debater model assignment for arms C and D (protocol ROUTER_VERSION).

Design (application report, "RQ2 Heterogeneous Model Design" / "Model Router"):

* Bull ("agent-a", original stance BULL) and Bear ("agent-b", original stance BEAR) of C and D are
  routed to model A or B by assignment: AA (homogeneous), AB (Bull=A, Bear=B), BA (Bull=B, Bear=A)
  and the optional BB control. A model is fixed per agent for all three rounds; in D only the round-2
  stance flips, and the switch turn still sees and must quote the SAME agent's own round-1 text.
* Research agents, the Judge (Adjudicator) and arms A/B always use ``protocol.model``. The
  Gatekeeper is deterministic code, not a model.
* The Judge never sees model names, assignment labels or agent ids: debaters are shown as
  "Debater 1/2" and the presentation order is drawn per case and arm from the report hash and
  recorded with the adjudication record.
* Every call carries ``audit["model_route"]``: agent, original/round stance, assignment, model slot,
  model id, provider, endpoint host label, provider-reported model, seed requested/applied,
  temperature, tokens, latency and retries. A call never falls back to another model: an
  unreachable endpoint fails the step (ModelRouteUnavailable, which pauses the job) and a provider
  answering with a different model fails it permanently (ModelRouteMismatch).
* Endpoints are per model (``protocol.model_endpoints``); only host labels and weight digests are
  recorded. Tokens are read from the environment variable NAMED by ``api_key_env``, never stored.

Older protocol versions never reach this module's routing paths: every public helper is a no-op
(or delegates unchanged) unless ``is_routed(protocol)`` is true.
"""
from __future__ import annotations

from copy import copy
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from urllib.parse import urlsplit
from urllib.request import Request

from .breaker import is_provider_failure
from .data import digest
from .model_identity import ModelIdentityError, ModelIdentityMismatch, ModelIdentityUnavailable
from .models import gputw_urlopen, messages_for as base_messages_for
from .protocol import (ROUTER_VERSIONS, RoutedDecisionCall, arm_prefix, assignment_models)

JUDGE_LABELS = ("Debater 1", "Debater 2")
JUDGE_BLINDING_NOTE = (" The debaters are labelled Debater 1 and Debater 2; each label is the same debater in "
                       "every round, and in a role-switch debate a debater may argue both stances. Labels and "
                       "presentation order carry no information about quality.")
_ASSIGNMENT_IN_KEY = re.compile(r"^([cd])-(?:ab|ba|bb)-")


class ModelRouteError(RuntimeError):
    """Routing is misconfigured or a provider broke the no-fallback rule; the step fails."""


class ModelRouteMismatch(ModelRouteError):
    """The provider answered with a model other than the one this call was routed to."""


class ModelRouteUnavailable(ModelIdentityUnavailable):
    """A routed model's endpoint could not be reached; the job pauses and can resume."""
    provider_failure = True


def _now():
    return datetime.now(timezone.utc).isoformat()


def is_routed(protocol) -> bool:
    version = protocol.get("version") if isinstance(protocol, dict) else getattr(protocol, "version", None)
    return version in ROUTER_VERSIONS


def provider_of(model: str) -> str:
    return "ollama" if model.startswith("ollama/") else (model.split("/", 1)[0] if "/" in model else "litellm")


def routed_models(protocol) -> dict:
    """{model id: [slots]} for the Judge/research model and debate models A and B."""
    models = {}
    for slot, model in (("JUDGE", protocol.model), ("A", protocol.debate_model_a), ("B", protocol.debate_model_b)):
        models.setdefault(model, []).append(slot)
    return models


def uses_ollama(protocol) -> bool:
    if not is_routed(protocol):
        return protocol.model.startswith("ollama/")
    return any(model.startswith("ollama/") for model in routed_models(protocol))


def model_for(protocol, call) -> tuple[str, str]:
    """(model id, slot) for one call. Only routed C/D debate turns leave the fixed model."""
    if isinstance(call, RoutedDecisionCall) and call.kind == "debate":
        bull_model, bear_model = assignment_models(protocol, call.assignment)
        return (bull_model, call.model_slot) if call.agent == "agent-a" else (bear_model, call.model_slot)
    if call is None:
        return protocol.model, "RESEARCH"
    return protocol.model, "JUDGE" if call.kind == "adjudication" else "FIXED"


def protocol_for(protocol, call):
    """The protocol object handed to the provider: identical except for ``model``.

    A shallow copy is used (not dataclasses.replace) so the frozen protocol is not re-validated
    with a debate model in the Judge's place.
    """
    model, _ = model_for(protocol, call)
    if model == protocol.model:
        return protocol
    routed = copy(protocol)
    object.__setattr__(routed, "model", model)
    return routed


def seed_key(call_key: str) -> str:
    """Seeds are shared across assignments (common random numbers): c-ab-r1-agent-a seeds like c-r1-agent-a."""
    return _ASSIGNMENT_IN_KEY.sub(r"\1-", call_key)


def endpoint_spec(protocol, model: str) -> dict:
    return dict((getattr(protocol, "model_endpoints", None) or {}).get(model) or {})


def _host_label(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or "unknown"
    return f"{parts.scheme}://{host}" + (f":{parts.port}" if parts.port else "")


def ollama_base(protocol, model: str) -> str:
    spec = endpoint_spec(protocol, model)
    return (spec.get("api_base") or os.getenv("GPUTW_OLLAMA_BASE_URL", "").strip()
            or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")


def endpoint_label(protocol, model: str) -> str:
    """Host label only (scheme://host:port); paths, credentials and tokens are never recorded."""
    spec = endpoint_spec(protocol, model)
    if model.startswith("ollama/"):
        return _host_label(ollama_base(protocol, model))
    if spec.get("api_base"):
        return _host_label(spec["api_base"])
    return f"{provider_of(model)}:provider-default"


def _auth_headers(protocol, model: str) -> dict:
    spec = endpoint_spec(protocol, model)
    if spec.get("api_key_env"):
        token = os.getenv(spec["api_key_env"], "").strip()
    elif spec.get("api_base"):
        token = ""  # Never send the default endpoint's token to another host.
    else:
        token = os.getenv("GPUTW_OLLAMA_API_KEY", "").strip()
    headers = {"User-Agent": "stance-shift-lab/1.0"}
    if token:
        headers["Authorization"] = "Bearer " + token
    return headers


def probe_ollama_endpoint(protocol, model: str) -> dict:
    """Read one model's weight digest from its own endpoint; never falls back to another endpoint."""
    label = endpoint_label(protocol, model)
    try:
        with gputw_urlopen(Request(ollama_base(protocol, model) + "/api/tags",
                                   headers=_auth_headers(protocol, model)), 30) as response:
            inventory = json.load(response)
    except Exception as error:
        raise ModelRouteUnavailable(f"模型 {model} 的端點 {label} 無法連線（{type(error).__name__}）；未放行推理") from None
    name = model.removeprefix("ollama/")
    matches = [item for item in (inventory.get("models") or []) if isinstance(item, dict) and item.get("name") == name] \
        if isinstance(inventory, dict) else []
    if len(matches) != 1 or not matches[0].get("digest"):
        raise ModelRouteUnavailable(f"端點 {label} 沒有模型 {model} 的唯一權重 digest；未放行推理")
    return {"id": model, "digest": matches[0]["digest"], "endpoint": label}


def resolve_identities(protocol, probe=probe_ollama_endpoint, provider_label=None) -> dict:
    """Identity of every routed model, for the job config (``routed_model_identities``).

    Ollama models must report a weight digest from their own endpoint; cloud models are recorded
    as aliases (no digest exists). ``provider_label`` replaces probing for demo/test providers.
    """
    identities = {}
    for model, slots in routed_models(protocol).items():
        if provider_label:
            identity = {"id": model, "provider": provider_label}
        elif model.startswith("ollama/"):
            identity = {**probe(protocol, model), "provider": "ollama"}
        else:
            identity = {"id": model, "provider": "cloud_alias", "endpoint": endpoint_label(protocol, model)}
        identities[model] = {**identity, "slots": slots, "resolved_at": _now()}
    return identities


def verify_identities(config: dict, probe=probe_ollama_endpoint) -> dict:
    """Before/after-step weight check of every routed Ollama model against the frozen digests."""
    from .protocol import protocol_from
    protocol = protocol_from(config["protocol"])
    expected = config.get("routed_model_identities") or {}
    checked = {}
    for model in routed_models(protocol):
        if not model.startswith("ollama/"):
            continue
        frozen = expected.get(model) or {}
        if not frozen.get("digest"):
            raise ModelIdentityError(f"工作沒有模型 {model} 的凍結 digest；請重新建立工作")
        observed = probe(protocol, model)
        if observed.get("digest") != frozen["digest"]:
            raise ModelIdentityMismatch(f"模型 {model} 的權重與工作凍結的 digest 不符；未放行推理")
        checked[model] = {"digest": observed["digest"], "endpoint": observed.get("endpoint")}
    return {"checked_at": _now(), "status": "pass", "models": checked}


def registration_digest(config: dict) -> str | None:
    """One value that locks every model of a case: the plain weight digest, or for a routed job a
    hash over all routed Ollama digests (None while any of them is missing)."""
    if not is_routed(config.get("protocol", {})):
        return (config.get("model_identity") or {}).get("digest")
    identities = config.get("routed_model_identities") or {}
    ollama = {model: item.get("digest") for model, item in identities.items() if model.startswith("ollama/")}
    if not ollama or not all(ollama.values()):
        return None
    return "route-sha256:" + hashlib.sha256(json.dumps(ollama, sort_keys=True).encode()).hexdigest()


def presentation(report_hash: str, call) -> dict:
    """Judge presentation order for one case and arm, drawn from the report hash and recorded."""
    arm = arm_prefix(call.group, getattr(call, "assignment", None))
    first = "agent-a" if int(hashlib.sha256(f"{report_hash}|{arm}".encode()).hexdigest()[:8], 16) % 2 == 0 else "agent-b"
    order = [first, "agent-b" if first == "agent-a" else "agent-a"]
    return {"order": order, "labels": dict(zip(order, JUDGE_LABELS)), "basis": "sha256(report_hash|arm) parity"}


def messages_for(call, report, records, memory, protocol, report_hash=None):
    """models.messages_for, plus assignment-free debate keys and a blinded Judge under the router version."""
    messages = base_messages_for(call, report, records, memory, protocol)
    if not is_routed(protocol) or call.group not in ("C", "D"):
        return messages
    payload = json.loads(messages[1]["content"])
    history = payload.get("history", [])
    if call.kind == "adjudication":
        order = presentation(report_hash or "", call)
        agents = {record["key"]: record.get("agent") for record in records}
        position = {agent: index for index, agent in enumerate(order["order"])}
        blinded = []
        for item in history:
            agent = agents.get(item.get("key"))
            blinded.append({"speaker": order["labels"][agent], "round": item.get("round"),
                            "stance": item.get("stance"), "output": item.get("output"), "_position": position[agent]})
        blinded.sort(key=lambda item: (item["round"], item.pop("_position")))
        payload["history"] = blinded
        system = messages[0]["content"] + JUDGE_BLINDING_NOTE
    else:
        # Debaters see the same prompt in every assignment; only the model answering it differs.
        for item in history:
            item["key"] = seed_key(item.get("key", ""))
        system = messages[0]["content"]
    return [{"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)}]


def record_extras(protocol, call, report_hash) -> dict:
    """Extra record fields: the Judge's recorded presentation order (router version only)."""
    if is_routed(protocol) and call.kind == "adjudication" and call.group in ("C", "D"):
        return {"judge_presentation": presentation(report_hash, call)}
    return {}


def call_with_route(model_call, protocol, call, call_key, messages, seed, kwargs):
    """Run one provider call on the routed model and return (result, audit with model_route)."""
    target = protocol_for(protocol, call)
    model, slot = model_for(protocol, call)
    try:
        result, audit = model_call(target, messages, **kwargs)
    except (ValueError, ModelRouteError):
        raise  # Answer-format problems keep their existing validation-retry semantics.
    except Exception as error:
        if isinstance(error, ModelIdentityError) or not is_provider_failure(error):
            raise  # Only transport/provider trouble means "unavailable"; a bug stays a bug.
        wrapped = ModelRouteUnavailable(f"{slot} 模型 {model}（{endpoint_label(protocol, model)}）呼叫失敗："
                                        f"{type(error).__name__}；不會改用其他模型")
        if getattr(error, "model_attempt_audit", None):
            wrapped.model_attempt_audit = error.model_attempt_audit
        raise wrapped from error
    audit = dict(audit)
    usage = audit.get("usage") or {}
    reported = usage.get("model") or usage.get("provider_model")
    if model.startswith("ollama/") and reported and reported != model.removeprefix("ollama/"):
        raise ModelRouteMismatch(f"呼叫 {call_key} 指派給 {model}，但服務回覆的模型是 {reported}；不接受任何備援模型")
    if "seed_applied" in usage:
        seed_applied, basis = usage["seed_applied"], "provider_report"
    elif model.startswith("ollama/") and "seed" in kwargs:
        seed_applied, basis = True, "ollama_options_seed"
    else:
        seed_applied, basis = None, "unknown"
    audit["model_route"] = {
        "call_key": call_key, "agent": getattr(call, "agent", None) if call is not None else "research",
        "original_stance": getattr(call, "original_stance", None) or getattr(call, "stance", None),
        "round_stance": getattr(call, "stance", None), "round": getattr(call, "round", None),
        "assignment": getattr(call, "assignment", None), "model_slot": slot, "model": model,
        "provider": provider_of(model), "endpoint": endpoint_label(protocol, model),
        "provider_model": reported, "seed_requested": seed, "seed_key": seed_key(call_key),
        "seed_applied": seed_applied, "seed_applied_basis": basis,
        "temperature": kwargs.get("temperature", audit.get("temperature")),
        "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
        "latency_seconds": usage.get("client_elapsed_seconds"),
        "provider_attempts": audit.get("provider_attempts", 1)}
    return result, audit


def finalize_route(audit: dict) -> dict:
    """Add the validation-retry count once the final answer of a logical call is known."""
    route = audit.get("model_route")
    if isinstance(route, dict):
        route["validation_retries"] = len(audit.get("validation_retries") or [])
    return audit


def arm_label(group: str, assignment: str) -> str:
    return f"{group}@{assignment}"


def arm_records(records, group, assignment):
    return [record for record in records if record.get("group") == group and record.get("assignment") == assignment]


def arm_usage(state, compute_usage) -> dict:
    """compute_usage per routed arm (C@AA, D@AB, ...): calls, retries, tokens and latency."""
    usage = {}
    assignments = sorted({record["assignment"] for record in state.get("records", []) if record.get("assignment")})
    for assignment in assignments:
        for group in ("C", "D"):
            records = arm_records(state["records"], group, assignment)
            if records:
                usage[arm_label(group, assignment)] = compute_usage(records)[group]
    return usage


def rq2_summary(jobs, horizon=None, cost_model="zero", layer="candidate") -> dict:
    """Descriptive per-arm accuracy and the pre-specified interaction contrast (no inference).

    Heterogeneous accuracy is the same-case mean over AB and BA (no longer binary, so ordinary
    McNemar does not apply), and Delta = (D_het - C_het) - (D_AA - C_AA). Inference (paired /
    date-clustered resampling) is left to the registered analysis plan.
    """
    per_case = []
    for job in jobs:
        state = job.get("state", {})
        protocol = job.get("config", {}).get("protocol", {})
        target = horizon or protocol.get("primary_horizon", 60)
        rows = [*state.get("cases", []), *state.get("routed_cases", [])]
        correct = {}
        for row in rows:
            if (row.get("status") == "complete" and row.get("horizon") == target
                    and row.get("cost_model") == cost_model and row.get("decision_layer") == layer):
                group = row["group"] if "@" in row["group"] else f"{row['group']}@AA"
                if row.get("correct") is not None:
                    correct[group] = 1.0 if row["correct"] else 0.0
        if correct:
            per_case.append(correct)
    arms = sorted({arm for case in per_case for arm in case if arm[0] in "CD"})

    def mean(values):
        values = [value for value in values if value is not None]
        return sum(values) / len(values) if values else None

    accuracy = {arm: mean([case.get(arm) for case in per_case]) for arm in arms}
    hetero = {}
    for group in ("C", "D"):
        hetero[group] = mean([mean([case.get(f"{group}@AB"), case.get(f"{group}@BA")]) for case in per_case
                              if case.get(f"{group}@AB") is not None or case.get(f"{group}@BA") is not None])
    interaction = None
    if None not in (hetero["C"], hetero["D"], accuracy.get("C@AA"), accuracy.get("D@AA")):
        interaction = (hetero["D"] - hetero["C"]) - (accuracy["D@AA"] - accuracy["C@AA"])
    return {"cases": len(per_case), "accuracy": accuracy, "hetero_case_mean_accuracy": hetero,
            "interaction": interaction, "basis": f"{layer} layer, {cost_model} cost, directional correctness",
            "note": "descriptive only; AB and BA share cases and are not independent observations",
            "summary_hash": digest(per_case)}
