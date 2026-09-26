"""Protocol-level statistics, preregistration and diagnostics."""
from fastapi import APIRouter
from fastapi.responses import Response

from ..reporting import csv_text, hold_band_sensitivity, pilot_diagnostics, stability_report, study_report


def build_router(ctx):
    router = APIRouter()
    store = ctx.store

    def protocol_jobs(protocol_hash):
        return [j for j in store.jobs() if j["config"]["protocol_hash"] == protocol_hash]

    @router.get("/api/studies/{protocol_hash}")
    def report(protocol_hash: str):
        jobs = protocol_jobs(protocol_hash)
        preregistration = store.preregistration(protocol_hash)
        eligible_dataset_ids = preregistration["dataset_ids"] if preregistration else None
        result = study_report(jobs, eligible_dataset_ids=eligible_dataset_ids)
        if preregistration:
            frozen = set(preregistration["dataset_ids"])
            post_freeze = sorted({j["config"]["dataset_id"] for j in jobs
                                  if j["config"].get("dataset_id") not in frozen})
            result["preregistration"] = {**preregistration, "post_freeze_dataset_ids": post_freeze}
        else:
            result["preregistration"] = None
        return result

    @router.post("/api/studies/{protocol_hash}/freeze")
    def freeze_study(protocol_hash: str):
        dataset_ids = {j["config"]["dataset_id"] for j in protocol_jobs(protocol_hash) if j["config"].get("dataset_id")}
        if not dataset_ids:
            raise ValueError("此協議尚無任何實驗，無法凍結 preregistration")
        return store.freeze(protocol_hash, dataset_ids)

    @router.get("/api/studies/{protocol_hash}/pilot")
    def pilot(protocol_hash: str):
        return pilot_diagnostics(protocol_jobs(protocol_hash))

    @router.get("/api/studies/{protocol_hash}/stability")
    def stability(protocol_hash: str):
        return stability_report(protocol_jobs(protocol_hash))

    @router.get("/api/studies/{protocol_hash}/hold-band")
    def hold_band(protocol_hash: str):
        return hold_band_sensitivity(protocol_jobs(protocol_hash))

    @router.get("/api/studies/{protocol_hash}/summary.csv")
    def summary(protocol_hash: str):
        return Response("﻿" + csv_text(report(protocol_hash)["summary"]), media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="summary.csv"'})

    return router
