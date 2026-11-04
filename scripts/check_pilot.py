"""Acceptance checker for a design-pilot output folder (RQ2 or RQ3, three-case pilot).

Reads the folder written by ``scripts/run_design_pilot.py --mode pilot --execute`` (or its
``data`` directory) and checks the acceptance list in docs/rq-prep/preformal-runbook-20261017.md
section 3. Read-only: the SQLite file is opened with mode=ro and a leftover -wal file is refused.
No model, network or GPU is touched.

Example: python scripts/check_pilot.py work/pilot-rq2 [--output work/pilot-rq2-check.json]
Exit code 0 only if every check passes (not_applicable does not fail).
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research_service.model_router import arm_label
from research_service.rq3_inference import ARMS as RQ3_ARMS

DONE = ("complete", "finished")
RQ2_ASSIGNMENTS = ("AA", "AB", "BA", "BB")
DEFAULT_CONTEXT = 8192
FORMAL_CASES = 180
MAX_DETAIL = 6


def find_database(path):
    """Accept the output folder or its data dir; return the research.sqlite3 path."""
    path = Path(path).resolve(strict=True)
    for candidate in (path / "data" / "research.sqlite3", path / "research.sqlite3"):
        if candidate.is_file():
            if Path(str(candidate) + "-wal").exists():
                raise ValueError("Use a standalone SQLite backup without WAL")
            return candidate
    raise ValueError("research.sqlite3 not found in the folder or its data directory")


def load(path):
    """Return (jobs, degraded_rows, manifest); jobs are dicts with config/state parsed."""
    database = find_database(path)
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
        db.row_factory = sqlite3.Row
        jobs = [{"id": row["id"], "status": row["status"], "error": row["error"],
                 "config": json.loads(row["config"]), "state": json.loads(row["state"] or "{}")}
                for row in db.execute("SELECT id, status, error, config, state FROM jobs ORDER BY created_at")]
        degraded = {row["job_id"]: row["n"] for row in db.execute(
            "SELECT job_id, SUM(degraded) AS n FROM case_results GROUP BY job_id") if row["n"]}
    manifest = None
    for folder in (database.parent.parent, database.parent):
        if (folder / "manifest.json").is_file():
            manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
            break
    return jobs, degraded, manifest


def design_of(config):
    return "RQ3" if config.get("domain_debate") is not None else "RQ2"


def model_calls(state):
    """Every recorded model call as (key, record); deterministic skips are excluded."""
    calls = []
    for field in ("records", "domain_records", "control_records"):
        for record in state.get(field) or []:
            audit = record.get("audit") or {}
            if not audit.get("deterministic"):
                calls.append((record.get("key", "?"), record))
    for domain, item in (state.get("research") or {}).items():
        audit = item.get("audit") if isinstance(item, dict) else None
        if isinstance(audit, dict) and not audit.get("fallback") and not audit.get("mode"):
            calls.append((f"research-{domain}", {"key": f"research-{domain}", "audit": audit}))
    return calls


def call_audits(audit):
    """The final audit plus validation retries that were discarded (not accepted as output)."""
    retries = [item for item in audit.get("validation_retries") or [] if not item.get("accepted_as_output")]
    return [*retries, audit]


def attempt_usages(audit):
    """One usage dict per provider attempt of one logical audit."""
    attempts = audit.get("attempts")
    if attempts:
        return [item.get("usage") or {} for item in attempts]
    return [audit.get("usage") or {}] * max(int(audit.get("provider_attempts") or 1), 1)


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def row(check, ok, detail, status=None):
    return {"check": check, "status": status or ("pass" if ok else "fail"), "detail": detail}


def summarize(problems, ok_text):
    if not problems:
        return ok_text
    shown = "; ".join(problems[:MAX_DETAIL])
    return shown + (f"; ... (+{len(problems) - MAX_DETAIL} more)" if len(problems) > MAX_DETAIL else "")


def check_complete_and_arms(jobs, manifest):
    problems = []
    if manifest is not None and manifest.get("status") != "complete":
        problems.append(f"manifest status {manifest.get('status')!r}")
    if not jobs:
        problems.append("no jobs in database")
    for job in jobs:
        tag, state, config = job["id"][:8], job["state"], job["config"]
        if job["status"] not in DONE or not state.get("finished"):
            problems.append(f"{tag}: status {job['status']!r}, finished={state.get('finished')}")
        records = state.get("records") or []
        groups = {r.get("group") for r in records}
        if design_of(config) == "RQ2":
            wanted = set(config["protocol"].get("debate_assignments") or RQ2_ASSIGNMENTS)
            if wanted != set(RQ2_ASSIGNMENTS):
                problems.append(f"{tag}: configured assignments {sorted(wanted)} are not AA/AB/BA/BB")
            have = {arm_label(r["group"], r.get("assignment") or "") for r in records if r.get("group") in ("C", "D")}
            need = {arm_label(group, assignment) for assignment in RQ2_ASSIGNMENTS for group in ("C", "D")}
        else:
            have = {r["arm"] for field in ("domain_records", "control_records")
                    for r in state.get(field) or [] if r.get("arm")}
            have |= {"C"} if "C" in groups else set()
            need = set(RQ3_ARMS)
            missing_decisions = set(RQ3_ARMS) - set(state.get("decisions") or {})
            if missing_decisions:
                problems.append(f"{tag}: decisions lack {sorted(missing_decisions)}")
        if not {"A", "B", "C", "D"} <= groups:
            problems.append(f"{tag}: records lack groups {sorted({'A', 'B', 'C', 'D'} - groups)}")
        if need - have:
            problems.append(f"{tag}: {design_of(config)} missing arms {sorted(need - have)}")
    return row("jobs_complete_and_arms_present", not problems,
               summarize(problems, f"{len(jobs)} job(s) complete, all arms present"))


def check_traceable(jobs):
    problems, total = [], 0
    for job in jobs:
        for key, record in model_calls(job["state"]):
            total += 1
            audit = record.get("audit")
            if not isinstance(audit, dict) or not audit:
                problems.append(f"{job['id'][:8]}/{key}: no audit")
            elif not isinstance(audit.get("raw_response"), str) or not audit["raw_response"].strip():
                problems.append(f"{job['id'][:8]}/{key}: no raw_response")
            elif not audit.get("prompt_hash"):
                problems.append(f"{job['id'][:8]}/{key}: no prompt_hash")
    if not total:
        return row("raw_response_and_audit_traceable", False, "no model calls recorded")
    return row("raw_response_and_audit_traceable", not problems,
               summarize(problems, f"{total} model calls have raw_response, prompt_hash and audit"))


def check_failures_and_degradation(jobs, degraded_rows):
    problems, recovered = [], 0
    for job in jobs:
        tag, state = job["id"][:8], job["state"]
        if job["error"]:
            problems.append(f"{tag}: job error {str(job['error'])[:60]!r}")
        if state.get("model_identity_failure"):
            problems.append(f"{tag}: model_identity_failure recorded")
        domains = (state.get("report") or {}).get("degraded_research_domains")
        if domains:
            problems.append(f"{tag}: degraded research domains {domains}")
        for domain, item in (state.get("research") or {}).items():
            audit = item.get("audit") if isinstance(item, dict) else None
            if isinstance(item, dict) and (item.get("status") == "degraded" or (audit or {}).get("fallback")):
                problems.append(f"{tag}: research {domain} degraded/fallback")
        if degraded_rows.get(job["id"]):
            problems.append(f"{tag}: {degraded_rows[job['id']]} degraded case_results row(s)")
        kept = {record.get("key") for field in ("records", "domain_records", "control_records")
                for record in state.get(field) or []}
        unresolved = [item.get("key") for item in state.get("failed_model_calls") or []
                      if item.get("key") not in kept]
        if unresolved:
            problems.append(f"{tag}: failed model calls never completed {unresolved[:3]}")
        recovered += len(state.get("failed_model_calls") or []) - len(unresolved)
        for key, record in model_calls(state):
            output, audit = record.get("output") or {}, record.get("audit") or {}
            if output.get("invalid_evidence_ids"):
                problems.append(f"{tag}/{key}: invalid evidence ids (citation/namespace)")
            if (output.get("redacted_numbers") or output.get("numeric_claims_removed")
                    or audit.get("numeric_redaction") or audit.get("unsupported_numbers")):
                problems.append(f"{tag}/{key}: numeric redaction/unsupported numbers")
            if audit.get("fallback"):
                problems.append(f"{tag}/{key}: audit fallback {audit['fallback']!r}")
            if any(item.get("accepted_as_output") for item in audit.get("validation_retries") or []):
                problems.append(f"{tag}/{key}: validation failure accepted as output")
    ok_text = "no degraded, fallback, redaction or invalid-citation outputs"
    if recovered:
        ok_text += f" ({recovered} provider failure(s) were retried and completed)"
    return row("no_citation_schema_namespace_failures_or_degradation", not problems, summarize(problems, ok_text))


def check_budget_prompt(jobs):
    name = "c_budget_aggregation_prompt_not_truncated"
    rq3 = [job for job in jobs if design_of(job["config"]) == "RQ3"]
    if not jobs:
        return row(name, False, "no jobs in database")
    if not rq3:
        return row(name, True, "RQ2 pilot has no C_budget arm", "not_applicable")
    problems, seen, unrecorded = [], [], 0
    for job in rq3:
        tag, protocol = job["id"][:8], job["config"]["protocol"]
        final = [r for r in job["state"].get("control_records") or []
                 if r.get("arm") == "C_budget" and str(r.get("key", "")).endswith("final")]
        if not final:
            problems.append(f"{tag}: no C_budget final aggregation record")
            continue
        audit = final[-1].get("audit") or {}
        context = audit.get("model_context_length") or protocol.get("model_context_length") or DEFAULT_CONTEXT
        limit = context - (protocol.get("max_output_tokens") or 0)
        tokens = [u.get("prompt_tokens") for a in call_audits(audit) for u in attempt_usages(a)]
        if not any(number(t) for t in tokens):
            unrecorded += 1
            continue
        top = max(t for t in tokens if number(t))
        seen.append(f"{tag}: max prompt_tokens {top} < limit {limit}")
        if top >= limit:
            problems.append(f"{tag}: prompt_tokens {top} >= context {context} - output cap = {limit}")
    if problems:
        return row(name, False, summarize(problems, ""))
    if not seen:
        return row(name, True, "prompt_tokens not recorded for the C_budget aggregation call", "not_applicable")
    return row(name, True, summarize(seen, "") + (f" ({unrecorded} job(s) without prompt_tokens)" if unrecorded else ""))


def tally(jobs):
    """Per-job usage totals over every model call, plus the problems that make them incomplete."""
    problems, per_job = [], {}
    for job in jobs:
        totals = {"calls": 0, "attempts": 0, "prompt": 0, "completion": 0, "seconds": 0.0}
        for key, record in model_calls(job["state"]):
            totals["calls"] += 1
            audit = record.get("audit") or {}
            if not isinstance(audit.get("provider_attempts"), int) or audit["provider_attempts"] < 1:
                problems.append(f"{job['id'][:8]}/{key}: no provider_attempts")
            for call_audit in call_audits(audit):
                for usage in attempt_usages(call_audit):
                    totals["attempts"] += 1
                    for field, name in (("prompt_tokens", "prompt"), ("completion_tokens", "completion"),
                                        ("client_elapsed_seconds", "seconds")):
                        if number(usage.get(field)):
                            totals[name] += usage[field]
                        else:
                            problems.append(f"{job['id'][:8]}/{key}: missing {field}")
        per_job[job["id"]] = totals
    return per_job, problems


def check_usage(per_job, problems):
    total = {key: sum(t[key] for t in per_job.values())
             for key in ("calls", "attempts", "prompt", "completion", "seconds")}
    text = (f"{total['calls']} calls, {total['attempts']} provider attempts, "
            f"{total['attempts'] - total['calls']} retries, prompt {total['prompt']} / "
            f"completion {total['completion']} tokens, {total['seconds']:.1f}s")
    return row("tokens_retries_latency_recorded", not problems and total["calls"] > 0,
               summarize(problems, text))


def check_digests(jobs):
    problems, checked = [], 0
    for job in jobs:
        tag, state, config = job["id"][:8], job["state"], job["config"]
        checks = state.get("model_identity_checks") or []
        expected = {}
        if config.get("routed_model_identities"):
            expected = {m: i.get("digest") for m, i in config["routed_model_identities"].items()
                        if m.startswith("ollama/")}
        elif (config.get("model_identity") or {}).get("digest"):
            expected = {config["model_identity"]["id"]: config["model_identity"]["digest"]}
        if not expected or not all(expected.values()):
            problems.append(f"{tag}: no frozen weight digest in config")
        if not checks:
            problems.append(f"{tag}: no model_identity_checks recorded")
            continue
        if state.get("model_identity_failure"):
            problems.append(f"{tag}: model_identity_failure recorded")
        if checks[-1].get("phase") != "after_step":
            problems.append(f"{tag}: last identity check is not after_step")
        for index, check in enumerate(checks):
            checked += 1
            if check.get("status") != "pass":
                problems.append(f"{tag}: check {index} status {check.get('status')!r}")
                continue
            seen = check.get("models") or ({check.get("id"): {"digest": check.get("digest")}}
                                           if check.get("digest") else {})
            for model, digest in expected.items():
                if (seen.get(model) or {}).get("digest") != digest:
                    problems.append(f"{tag}: check {index} digest for {model} differs from frozen digest")
    return row("weight_digest_unchanged", not problems,
               summarize(problems, f"{checked} identity checks, all equal the frozen digest(s)"))


def check_memory(jobs):
    problems = []
    for job in jobs:
        audit = job["state"].get("memory_audit")
        if not isinstance(audit, dict):
            problems.append(f"{job['id'][:8]}: no memory_audit")
        elif audit.get("pending_earlier_cases"):
            problems.append(f"{job['id'][:8]}: pending earlier cases {audit['pending_earlier_cases']}")
    return row("memory_no_pending_earlier_cases", not problems, summarize(problems, "no pending_earlier_cases"))


def timing_summary(jobs, per_job):
    seconds = [per_job[job["id"]]["seconds"] for job in jobs]
    if not seconds:
        return {"cases": 0, "per_case_seconds": [], "estimate_180_cases_seconds": None}
    mean = sum(seconds) / len(seconds)
    return {"cases": len(seconds), "per_case_seconds": [round(s, 3) for s in seconds],
            "total_model_seconds": round(sum(seconds), 3), "mean_per_case_seconds": round(mean, 3),
            "estimate_180_cases_seconds": round(mean * FORMAL_CASES, 1),
            "estimate_180_cases_hours": round(mean * FORMAL_CASES / 3600, 2),
            "note": "ESTIMATE only: mean pilot case time x 180, sequential."}


def check_pilot(path):
    jobs, degraded_rows, manifest = load(path)
    per_job, usage_problems = tally(jobs)
    rows = [check_complete_and_arms(jobs, manifest), check_traceable(jobs),
            check_failures_and_degradation(jobs, degraded_rows), check_budget_prompt(jobs),
            check_usage(per_job, usage_problems), check_digests(jobs), check_memory(jobs)]
    return {"checks": rows, "timing": timing_summary(jobs, per_job),
            "passed": all(item["status"] != "fail" for item in rows)}


def render(result):
    lines = [f"{'check':<56} {'status':<15} detail"]
    lines += [f"{item['check']:<56} {item['status']:<15} {item['detail']}" for item in result["checks"]]
    timing = result["timing"]
    lines.append("")
    if timing.get("cases"):
        lines.append(f"Timing: {timing['cases']} case(s), model seconds per case {timing['per_case_seconds']}, "
                     f"total {timing['total_model_seconds']}s")
        lines.append(f"ESTIMATE for {FORMAL_CASES} cases, sequential: {timing['estimate_180_cases_seconds']}s "
                     f"({timing['estimate_180_cases_hours']} h) = mean per case x {FORMAL_CASES}; not a measurement.")
    lines.append("RESULT: " + ("ALL CHECKS PASS" if result["passed"] else "FAILED"))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, help="pilot output folder (or its data directory)")
    parser.add_argument("--output", type=Path, help="write the JSON result here (must not exist)")
    args = parser.parse_args(argv)
    if args.output is not None and args.output.exists():
        parser.exit(2, "Refusing to overwrite an existing --output file.\n")
    try:
        result = check_pilot(args.folder)
    except (ValueError, OSError, sqlite3.Error) as error:
        parser.exit(2, f"Cannot read pilot output: {error}\n")
    print(render(result))
    if args.output is not None:
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
