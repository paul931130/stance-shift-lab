"""RQ study summaries with the same eligibility and deduplication boundary as RQ1.

Kept outside frozen routing/prompt modules: changing analysis must not silently
change a completed experiment's protocol identity.
"""
from copy import deepcopy

from .model_router import rq2_summary
from .reporting import _completed_unique
from .rq3_reporting import rq3_study_report


def select_cases(jobs, *, formal_only=True, eligible_dataset_ids=None, frozen_at=None):
    selected, excluded = _completed_unique(jobs, formal_only=formal_only,
                                          eligible_dataset_ids=eligible_dataset_ids, frozen_at=frozen_at)
    # The RQ1 identity guard covers the primary model; RQ2 additionally freezes
    # every routed debater. Timestamps are not part of model identity.
    identities = set()
    for job in selected:
        routes = job["config"].get("routed_model_identities") or {}
        identities.add(tuple(sorted((model, value.get("digest"), value.get("id"))
                                    for model, value in routes.items())))
    if len(identities) > 1:
        raise ValueError("不同辯論模型權重不可合併 RQ2 統計")
    return selected, excluded


def rq2_study_report(jobs, *, formal_only=True, eligible_dataset_ids=None, frozen_at=None,
                     horizon=60, cost_model="corwin_schultz", layer="candidate"):
    selected, excluded = select_cases(jobs, formal_only=formal_only,
                                      eligible_dataset_ids=eligible_dataset_ids, frozen_at=frozen_at)
    complete, missing = [], []
    required = {f"{group}@{assignment}" for assignment in ("AA", "AB", "BA") for group in "CD"}
    for job in selected:
        state = job["state"]
        rows = [*state.get("cases", []), *state.get("routed_cases", [])]
        correctness = {}
        for row in rows:
            if (row.get("status") == "complete" and row.get("horizon") == horizon
                    and row.get("cost_model") == cost_model and row.get("decision_layer") == layer
                    and isinstance(row.get("correct"), bool)):
                group = row["group"] if "@" in row["group"] else f"{row['group']}@AA"
                if group in correctness:
                    raise ValueError("同一案例與 arm 有重複計分列")
                correctness[group] = row["correct"]
        if not required <= correctness.keys():
            missing.append({"job_id": job["id"], "missing_arms": sorted(required - correctness.keys())})
            continue
        complete.append(job)
    # BB is a second baseline, so show it on the same common complete subset.
    bb_required = any("BB" in j["config"].get("protocol", {}).get("debate_assignments", []) for j in selected)
    if bb_required:
        kept = []
        for job in complete:
            rows = job["state"].get("routed_cases", [])
            available = {r["group"] for r in rows if r.get("status") == "complete"
                         and r.get("horizon") == horizon and r.get("cost_model") == cost_model
                         and r.get("decision_layer") == layer and isinstance(r.get("correct"), bool)}
            if {"C@BB", "D@BB"} <= available:
                kept.append(job)
            else:
                missing.append({"job_id": job["id"], "missing_arms": sorted({"C@BB", "D@BB"} - available)})
        complete = kept
    result = rq2_summary(complete, horizon=horizon, cost_model=cost_model, layer=layer)
    hetero = result["hetero_case_mean_accuracy"]
    accuracy = result["accuracy"]
    result["interactions_by_baseline"] = {
        baseline: ((hetero["D"] - hetero["C"]) - (accuracy[f"D@{baseline}"] - accuracy[f"C@{baseline}"]))
        for baseline in ("AA", "BB") if all(accuracy.get(f"{g}@{baseline}") is not None for g in "CD")
        and all(hetero[g] is not None for g in "CD")}
    return {**result, "formal_only": formal_only, "excluded": excluded,
            "excluded_incomplete_pairs": missing, "horizon": horizon, "cost_model": cost_model,
            "decision_layer": layer, "pairing": "same complete cases for every requested arm and assignment"}


def rq3_summary(jobs, *, formal_only=True, eligible_dataset_ids=None, frozen_at=None):
    selected, excluded = select_cases(jobs, formal_only=formal_only,
                                      eligible_dataset_ids=eligible_dataset_ids, frozen_at=frozen_at)
    return {**rq3_study_report(selected), "formal_only": formal_only, "excluded": excluded}


def matched_seed_inputs(correct_by_seed, dates_by_seed):
    """Validate a repeated-seed analysis without counting repeats as extra cases.

    Input keys must be pre-registered seeds; values map stable stock-date IDs to
    complete arm correctness. Return arrays with dimensions seed x case x arm.
    """
    if len(correct_by_seed) < 3 or set(correct_by_seed) != set(dates_by_seed):
        raise ValueError("RQ2 v7 requires at least three matching seeds")
    seeds = sorted(correct_by_seed)
    first = correct_by_seed[seeds[0]]
    cases = sorted(first)
    arms = tuple(f"{g}@{a}" for a in ("AA", "AB", "BA", "BB") for g in "CD")
    reference_dates = dates_by_seed[seeds[0]]
    if not cases or set(reference_dates) != set(cases):
        raise ValueError("Every case requires an analysis date")
    values = []
    for seed in seeds:
        current = correct_by_seed[seed]
        if set(current) != set(cases) or dates_by_seed[seed] != reference_dates:
            raise ValueError("All seeds must share identical case IDs and dates")
        if any(not set(arms) <= current[key].keys()
               or any(not isinstance(current[key][arm], bool) for arm in arms) for key in cases):
            raise ValueError("All seeds require complete Boolean AA/AB/BA/BB C/D pairs")
        values.append([[current[key][arm] for arm in arms] for key in cases])
    return {"seeds": seeds, "case_ids": cases, "arm_names": list(arms),
            "date_ids": [reference_dates[key] for key in cases], "correctness": deepcopy(values)}
