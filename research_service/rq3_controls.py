"""Versioned RQ3 controls: 28 independent proposals + judge, or partitioned evidence without debate."""
from dataclasses import asdict
import json

from .breaker import is_provider_failure
from .engine import derive_action, gate
from .models import messages_for
from .protocol import DOMAIN_NAMES, DecisionCall
from .storage import now

CONTROL_CALLS = {"C_budget": 29, "C_partition": 1}


def keys(arm):
    if arm == "C_budget":
        return [*(f"c-budget-sample-{i}" for i in range(28)), "c-budget-final"]
    return ["c-partition-final"]


def pending(state):
    done = {r["key"] for r in state.get("control_records", [])}
    return any(keys(arm)[-1] not in done for arm in CONTROL_CALLS)


def wave(engine, protocol, config, state):
    records = state.setdefault("control_records", [])
    done = {r["key"] for r in records}
    arm = next(arm for arm in CONTROL_CALLS if keys(arm)[-1] not in done)
    key = next(key for key in keys(arm) if key not in done)
    final = key.endswith("final")
    call = DecisionCall(key, "C", "adjudication", "control-judge", "NEUTRAL")
    own = [r for r in records if r["arm"] == arm]
    history = [{**r, "group": "C", "kind": "debate", "round": 1,
                "agent": f"sampler-{i}"} for i, r in enumerate(own)] if final and arm == "C_budget" else []
    memory = state["memory"].get(arm, []) if final else []
    messages = messages_for(call, state["report"], history, memory, protocol)
    payload = json.loads(messages[1]["content"])
    if not final:
        payload.pop("matured_same_group_memory", None)
    if arm == "C_partition":
        evidence = payload["report"].pop("evidence", [])
        # Same compact evidence as the Generalist, grouped explicitly into four
        # slices. No new summaries or domain inference calls are introduced.
        payload["report"]["domain_partitions"] = {
            domain: [item for item in evidence if item.get("domain") == domain] for domain in DOMAIN_NAMES}
        note = (" Partition-only control: read the four domain_partitions directly as one neutral judge. "
                "There are no domain debaters, synthesized views or votes. Cite supplied evidence IDs.")
    elif final:
        note = (" Call-budget control: integrate 28 independent proposals; they have not debated each other. "
                "Repeated claims and vote counts are not evidence. Decide using the same locked report.")
    else:
        note = (" Call-budget control: produce one independent directional proposal from the locked report. "
                "No other proposal or debate is visible. This is not a discussion round.")
    messages = [{**messages[0], "content": messages[0]["content"] + note},
                {**messages[1], "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)}]
    try:
        result, audit = engine.validated_decision(protocol, call, messages, state["report"]["evidence"])
    except Exception as error:
        audit = getattr(error, "model_attempt_audit", None)
        if audit:
            state.setdefault("failed_model_calls", []).append(
                {"key": key, "group": arm, "failed_model_call": True, "audit": audit})
        state["_step_error"] = f"{key}: {type(error).__name__}: {error}"
        state["_step_provider_failure"] = is_provider_failure(error)
        return f"rq3_control[{key}]", 1
    records.append({**asdict(call), "arm": arm, "output": result, "audit": audit,
                    "report_hash": state["report_hash"], "completed_at": now()})
    return f"rq3_control[{key}]", 1


def decisions(protocol, state):
    result = {}
    lookup = {r["key"]: r for r in state.get("control_records", [])}
    hold_band = state["inputs"]["base_rates"]["hold_band_pct"]
    for arm in CONTROL_CALLS:
        candidate = lookup[keys(arm)[-1]]["output"]
        derived = derive_action(candidate["expected_return_pct"], hold_band)
        prepared = {**candidate, "model_action": candidate["action"], "derived_action": derived,
                    "action": derived if protocol.action_source == "derived" else candidate["action"],
                    "action_disagreement": candidate["action"] != derived, "hold_band_pct": hold_band}
        result[arm] = gate(prepared, state["inputs"], state["memory"].get(arm, []), protocol)
    return result
