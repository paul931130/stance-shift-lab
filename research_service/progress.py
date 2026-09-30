"""Batch progress for one preregistered study: counts, errors, throughput and an honest ETA."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .protocol import protocol_is_current

RATE_WINDOW = timedelta(minutes=60)
MIN_RATE_SAMPLES = 3


def _parse(stamp):
    try:
        value = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def study_progress(preregistration, rows, now=None):
    """Summarize a study from its preregistration and the job rows of its protocol.

    ``rows`` come from Store.study_rows. Only jobs whose dataset is in the
    preregistered sample count toward progress; others are reported separately.
    """
    now = now or datetime.now(timezone.utc)
    frozen = set(preregistration["dataset_ids"]) if preregistration else set()
    formal = [row for row in rows if not frozen or row["dataset_id"] in frozen]
    counts = {status: 0 for status in ("queued", "running", "paused", "complete", "cancelled")}
    for row in formal:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    total = len(frozen) or len(formal)
    created_datasets = {row["dataset_id"] for row in formal}
    not_created = len(frozen - created_datasets) if frozen else 0
    errors = sorted(({"id": row["id"], "ticker": row["ticker"], "analysis_date": row["analysis_date"],
                      "error": (row["error"] or "")[:300]}
                     for row in formal if row["status"] == "paused" and row["error"]),
                    key=lambda item: (item["analysis_date"] or "", item["ticker"] or ""))

    finished = sorted(t for t in (_parse(row["updated_at"]) for row in formal if row["status"] == "complete") if t)
    recent = [t for t in finished if now - t <= RATE_WINDOW]
    rate_per_hour = None
    if len(recent) >= MIN_RATE_SAMPLES:
        span = max(now - recent[0], timedelta(minutes=1))
        rate_per_hour = len(recent) / (span.total_seconds() / 3600)
    remaining = counts["queued"] + counts["running"]
    active = remaining > 0
    eta_hours = round(remaining / rate_per_hour, 2) if active and rate_per_hour else None
    labelled = next((row for row in formal if row.get("version")), {})
    # Jobs of an older protocol stay readable but can never be resumed on this engine.
    current = (not labelled or protocol_is_current({"version": labelled["version"],
                                                    "design": labelled.get("design") or "quarterly"}))
    return {
        "protocol_hash": preregistration["protocol_hash"] if preregistration else None,
        "version": labelled.get("version"), "model": labelled.get("model"), "current": current,
        "preregistered": bool(preregistration), "frozen_at": preregistration["frozen_at"] if preregistration else None,
        "total": total, "not_created": not_created, "counts": counts,
        "done_fraction": round(counts["complete"] / total, 4) if total else 0.0,
        "active": active, "remaining": remaining, "errors": errors,
        "rate_cases_per_hour": round(rate_per_hour, 1) if rate_per_hour else None,
        "eta_hours": eta_hours,
        "last_completed_at": finished[-1].isoformat() if finished else None,
        "outside_sample_jobs": len(rows) - len(formal),
    }
