"""Protocol-level statistics, preregistration and diagnostics."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from .context import BatchInput
from .jobs import prepare

from ..progress import study_progress
from ..reporting import csv_text, hold_band_sensitivity, pilot_diagnostics, stability_report, study_report


def build_router(ctx):
    router = APIRouter()
    store = ctx.store

    def protocol_jobs(protocol_hash):
        return store.jobs(protocol_hash)

    @router.get("/api/studies/{protocol_hash}")
    def report(protocol_hash: str):
        jobs = protocol_jobs(protocol_hash)
        preregistration = store.preregistration(protocol_hash)
        result = study_report(jobs, eligible_dataset_ids=preregistration["dataset_ids"] if preregistration else None,
                              frozen_at=preregistration["frozen_at"] if preregistration else None)
        if preregistration:
            frozen = set(preregistration["dataset_ids"])
            post_freeze = sorted({j["config"]["dataset_id"] for j in jobs
                                  if j["config"].get("dataset_id") not in frozen})
            result["preregistration"] = {**preregistration, "post_freeze_dataset_ids": post_freeze}
        else:
            result["preregistration"] = None
        return result

    @router.get("/api/studies")
    def studies():
        """Preregistered studies, newest first, each with its batch progress."""
        return [{**item, "progress": study_progress(store.preregistration(item["protocol_hash"]),
                                                    store.study_rows(item["protocol_hash"]))}
                for item in store.preregistrations()]

    @router.get("/api/studies/{protocol_hash}/progress")
    def progress(protocol_hash: str):
        return study_progress(store.preregistration(protocol_hash), store.study_rows(protocol_hash))

    @router.post("/api/studies/{protocol_hash}/enqueue")
    def enqueue(protocol_hash: str, payload: BatchInput):
        """Queue a preregistered study. Safe to repeat: cases that already have a job are skipped."""
        registration = store.preregistration(protocol_hash)
        if not registration:
            raise ValueError("這個協議還沒有事前登記；請先用 POST /api/studies/preregister 鎖定樣本")
        frozen = set(registration["dataset_ids"])
        prepared = [prepare(ctx, item) for item in payload.cases]
        wrong = [item["dataset_id"] for item in prepared if item["protocol_hash"] != protocol_hash]
        if wrong:
            raise ValueError(f"{len(wrong)} 個案例的協議與登記不符（例如設定或模型不同），全部未排入")
        outside = [item["dataset_id"] for item in prepared if item["dataset_id"] not in frozen]
        if outside:
            raise ValueError(f"{len(outside)} 個案例不在事前登記的樣本內，全部未排入")
        existing = {row["dataset_id"] for row in store.study_rows(protocol_hash) if row["status"] != "cancelled"}
        created = [store.create(item)["id"] for item in prepared if item["dataset_id"] not in existing]
        return {"created": len(created), "skipped_existing": len(prepared) - len(created),
                "progress": study_progress(registration, store.study_rows(protocol_hash))}

    @router.post("/api/studies/{protocol_hash}/{command}-all")
    def control_all(protocol_hash: str, command: str):
        """Pause or resume every job of a study in one step (e.g. before stopping the GPU)."""
        if command not in ("pause", "resume"):
            raise HTTPException(404)
        rows = store.study_rows(protocol_hash)
        if command == "resume" and not study_progress(store.preregistration(protocol_hash), rows)["current"]:
            raise ValueError("這是舊版協議的研究，不能用目前的引擎續跑；結果保留供查看")
        movable = ("queued", "running") if command == "pause" else ("paused",)
        changed = 0
        for row in rows:
            if row["status"] in movable:
                store.control(row["id"], command)
                changed += 1
        return {"changed": changed,
                "progress": study_progress(store.preregistration(protocol_hash), store.study_rows(protocol_hash))}

    @router.post("/api/studies/preregister")
    def preregister(payload: BatchInput):
        """Lock a planned sample before any of it runs; creates no jobs.

        Every case goes through the same validation as a real job, so the lock
        records the exact protocol the batch will run under. Only jobs created
        after this lock count as formal results.
        """
        prepared = [prepare(ctx, item) for item in payload.cases]
        hashes = {item["protocol_hash"] for item in prepared}
        if len(hashes) != 1:
            raise ValueError("批次內的案例必須使用同一套研究協議（相同模型與設定）才能一起鎖定樣本")
        [protocol_hash] = hashes
        return {**store.freeze(protocol_hash, {item["dataset_id"] for item in prepared}), "cases": len(prepared)}

    @router.post("/api/studies/{protocol_hash}/freeze")
    def freeze_study(protocol_hash: str):
        # Locking the datasets of jobs that already ran is a retrospective
        # freeze, not a preregistration; plans are locked before running.
        if protocol_jobs(protocol_hash):
            raise ValueError("此協議已有實驗；事後鎖定不算事前登記。請用 POST /api/studies/preregister "
                             "在執行前鎖定研究計畫，既有結果保留為探索性分析")
        dataset_ids = {j["config"]["dataset_id"] for j in protocol_jobs(protocol_hash) if j["config"].get("dataset_id")}
        if not dataset_ids:
            raise ValueError("這個協議版本還沒有任何實驗，無法鎖定研究樣本")
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
