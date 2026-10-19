"""Bind repeated-seed RQ2 jobs to a frozen, content-addressed Neutral Report."""
from copy import deepcopy
from dataclasses import asdict

from .data import digest
from .protocol import ROUTER_VERSION, protocol_from


def bind_report(store, payload, protocol, model_identity=None, routed_identities=None):
    source_id = payload.neutral_report_job_id
    wanted_hash = payload.neutral_report_hash
    if source_id is None and wanted_hash is None:
        return None
    if not source_id or not wanted_hash or protocol.version != ROUTER_VERSION:
        raise ValueError("共用報告需提供新版 RQ2 來源工作 ID 與完整報告 hash")
    source = store.get(source_id)
    config, state = source["config"], source["state"]
    if config.get("protocol_hash") == protocol.fingerprint:
        raise ValueError("研究輸入庫須使用正式 seed 清單以外的 seed，避免來源工作佔用正式案例")
    # A report chosen after inspecting its decisions is a result-dependent
    # input.  Require an idle checkpoint before *any* decision or backtest.
    if (source.get("status") != "paused" or source.get("owner") or source.get("wants_run")
            or state.get("finished") or state.get("model_identity_failure")
            or any(state.get(key) for key in ("records", "routed_records", "decisions", "routed_decisions",
                                             "cases", "routed_cases", "daily", "routed_daily"))
            or not state.get("trace") or state["trace"][-1].get("node") != "neutral_report_locked"):
        raise ValueError("共用報告來源須暫停於 neutral_report_locked，且尚無決策或回測結果")
    target = asdict(protocol)
    original = dict(config.get("protocol", {}))
    target.pop("inference_seed", None)
    original.pop("inference_seed", None)
    # JSON stores tuples as lists.
    if digest(target) != digest(original):
        raise ValueError("共用報告只能來自除 seed 外設定完全相同的工作")
    if config.get("dataset_id") != payload.dataset_id or config.get("analysis_date") != payload.analysis_date:
        raise ValueError("共用報告必須屬於相同資料集與分析日")
    if protocol_from(config["protocol"]).fingerprint != config.get("protocol_hash"):
        raise ValueError("共用報告來源的程式 fingerprint 已過期")
    if model_identity is not None and model_identity.get("digest") != config.get("model_identity", {}).get("digest"):
        raise ValueError("共用報告來源的研究模型權重與目前不同")
    if routed_identities is not None:
        def weights(identities):
            return {key: item.get("digest") for key, item in identities.items()}
        if weights(routed_identities) != weights(config.get("routed_model_identities", {})):
            raise ValueError("共用報告來源的路由模型權重與目前不同")
    report = state.get("report")
    if not report or state.get("report_hash") != wanted_hash or digest(report) != wanted_hash:
        raise ValueError("共用報告內容或 hash 不符")
    if report.get("degraded_research_domains") or len(state.get("research", {})) != 4:
        raise ValueError("共用報告必須含四個完成且未降級的研究輸出")
    return {"source_job_id": source_id, "report_hash": wanted_hash,
            "report": deepcopy(report), "research": deepcopy(state["research"])}


def check_registered_reports(store, protocol_hash, configs):
    frozen = {case["dataset_id"]: case.get("neutral_report_hash")
              for case in (store.registered_cases(protocol_hash) or [])}
    for config in configs:
        dataset_id = config["dataset_id"]
        actual = (config.get("shared_neutral_report") or {}).get("report_hash")
        if dataset_id in frozen and actual != frozen[dataset_id]:
            raise ValueError("Neutral Report hash 與該案例事前登記不符")
