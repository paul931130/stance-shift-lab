"""The stance-shift command: interactive runs, scripted runs, the web service and checks."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys


def _doctor():
    required = ("fastapi", "uvicorn", "langgraph", "numpy", "scipy")
    checks = {name: bool(importlib.util.find_spec(name)) for name in required}
    result = {"status": "ok" if all(checks.values()) else "missing_dependencies",
              "python": sys.version.split()[0], "dependencies": checks,
              "data_dir": os.getenv("RESEARCH_DATA_DIR", "research-data"),
              "model": os.getenv("RESEARCH_MODEL", "ollama/qwen3:14b"),
              "model_timeout_seconds": os.getenv("RESEARCH_MODEL_TIMEOUT_SECONDS", "240"),
              "model_context_length": os.getenv("RESEARCH_MODEL_CONTEXT_LENGTH", "8192"),
              "network_calls": False,
              "note": "doctor 只檢查本機環境與設定，不呼叫模型、不建立正式案例。"}
    return result


def _run(args):
    """Non-interactive run for scripts: stance-shift run NVDA 2024-12-31 --model …"""
    from . import ResearchRunError, StanceShiftResearch
    from .interactive import load_env_files, print_result, progress

    load_env_files()
    research = StanceShiftResearch(model=args.model)
    options = {name: True for name in ("allow_small_model", "allow_low_quality_sentiment", "allow_point_fundamental")
               if getattr(args, name)}
    try:
        if args.command == "resume":
            result = research.resume(args.job_id, progress=None if args.json else progress)
        else:
            result = research.run(args.ticker.upper(), args.date, use_finbert=args.finbert, refresh=args.refresh,
                                  progress=None if args.json else progress, **options)
    except ResearchRunError as error:
        print(f"[中斷] {error}\n進度已保存。排除問題後執行：stance-shift resume {error.job_id}", file=sys.stderr)
        return 1
    except ValueError as error:
        print(f"[未通過檢查] {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_result(result)
    return 0


def _refresh_news(args):
    from .collect import refresh_news
    from .interactive import load_env_files
    from .storage import Store

    load_env_files()
    store = Store(os.getenv("RESEARCH_DATA_DIR", "research-data"))
    registration = store.preregistration(args.preregistered)
    if not registration:
        print(f"找不到協議 {args.preregistered} 的事前登記", file=sys.stderr)
        return 2
    results, failures = [], 0
    for index, key in enumerate(registration["dataset_ids"], 1):
        data = store.dataset(key)
        label = f"[{index}/{len(registration['dataset_ids'])}] {data['ticker']} {data.get('requested_analysis_date')}"
        try:
            result = refresh_news(store, key, allow_live=args.allow_live)
        except Exception as error:  # one case must not stop the batch
            print(f"{label}: 失敗 {type(error).__name__}: {error}", flush=True)
            failures += 1
            continue
        results.append({"ticker": data["ticker"], "analysis_date": data.get("requested_analysis_date"),
                        "old_dataset_id": key, "dataset_id": result["id"],
                        "previous_items": result["previous_items"], "items": result["items"],
                        "local_items": result["local_items"], "carried_live_items": result["carried_live_items"]})
        print(f"{label}: 新聞 {result['previous_items']} -> {result['items']} 則（本機 {result['local_items']}、"
              f"沿用即時抓取 {result['carried_live_items']}），{key[:12]} -> {result['id'][:12]}", flush=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump({"source_protocol_hash": args.preregistered, "datasets": results}, handle, ensure_ascii=False, indent=2)
    print(f"完成 {len(results)} 個，失敗 {failures} 個；對照表：{args.output}")
    return 1 if failures else 0


def _refresh_fundamentals(args):
    from .collect import refresh_fundamentals, reusable_snapshot
    from .interactive import load_env_files
    from .protocol import QUARTER_DATES, STUDY_TICKERS
    from .storage import Store

    load_env_files()
    store = Store(os.getenv("RESEARCH_DATA_DIR", "research-data"))
    cases = ([(ticker, day) for ticker in STUDY_TICKERS for day in QUARTER_DATES] if args.all
             else [tuple(case.upper().split(":", 1)) for case in args.cases])
    if not cases or any(len(case) != 2 for case in cases):
        print("請指定 TICKER:分析日（例如 NVDA:2024-12-31），或加 --all", file=sys.stderr)
        return 2
    # One SEC companyfacts download per company, not one per quarter.
    from .data import get_json
    downloads = {}

    def requester(url, headers):
        if url not in downloads:
            downloads[url] = get_json(url, headers)
        return downloads[url]

    failures = 0
    for ticker, day in cases:
        existing = reusable_snapshot(store, ticker, day)
        if not existing:
            print(f"{ticker} {day}: 沒有完整的既有資料集，略過")
            failures += 1
            continue
        try:
            result = refresh_fundamentals(store, existing["id"], requester)
        except Exception as error:  # one case must not stop the batch
            print(f"{ticker} {day}: 失敗 {type(error).__name__}: {error}")
            failures += 1
            continue
        print(f"{ticker} {day}: {existing['id'][:12]} -> {result['id'][:12]}（{result['items']} 筆基本面證據）")
    return 1 if failures else 0


def _jobs():
    from .storage import Store

    store = Store(os.getenv("RESEARCH_DATA_DIR", "research-data"))
    for job in store.job_summaries()[:30]:
        config = job["config"]
        print(f"{job['id']}  {job['status']:<9} {config['ticker']:<5} {config['analysis_date']}  "
              f"{config['protocol']['model']}  {job['steps']} 步")
    return 0


def _studies():
    from .labels import ljust
    from .progress import study_progress
    from .storage import Store

    store = Store(os.getenv("RESEARCH_DATA_DIR", "research-data"))
    studies = store.preregistrations()
    if not studies:
        print("尚無事前登記的研究。")
        return 0
    for item in studies:
        p = study_progress(store.preregistration(item["protocol_hash"]), store.study_rows(item["protocol_hash"]),
                           meta=store.registration_meta(item["protocol_hash"]))
        c = p["counts"]
        label = f"{p['version']} · {p['model']}" if p["version"] else "尚未排入"
        eta = f"，預估還要 {p['eta_hours']} 小時" if p["eta_hours"] is not None else ""
        state = "舊版（只能查看）" if not p["current"] else f"執行中 {c['running']}、等待 {c['queued']}、暫停 {c['paused']}{eta}"
        print(f"{item['protocol_hash'][:8]}  {ljust(label, 34)} {c['complete']:>3}/{p['total']} 完成  {state}")
        for error in (p["errors"] if p["current"] else [])[:5]:
            print(f"    ! {error['ticker']} {error['analysis_date']}：{error['error'][:100]}")
        if p["current"] and len(p["errors"]) > 5:
            print(f"    … 另有 {len(p['errors']) - 5} 案錯誤")
    return 0


def _utf8_output():
    """Output redirected to a file or pipe (e.g. --json > run.json on Windows) is
    written as UTF-8 instead of the legacy code page, which cannot hold Chinese."""
    for stream in (sys.stdout, sys.stderr):
        try:
            if not stream.isatty() and (stream.encoding or "").lower().replace("-", "") != "utf8":
                stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError, OSError):
            pass


def main(argv=None):
    _utf8_output()
    parser = argparse.ArgumentParser(
        prog="stance-shift",
        description="多代理人立場交換回測。不加指令直接執行 stance-shift，會一步步問股票、分析日與模型。")
    subparsers = parser.add_subparsers(dest="command")
    run = subparsers.add_parser("run", help="跑一個案例（不問問題，給腳本用）")
    run.add_argument("ticker")
    run.add_argument("date", help="季末日期，例如 2024-12-31，或今天")
    run.add_argument("--model", default=None, help="例如 ollama/qwen3:32b、gemini/gemini-2.5-flash；預設 RESEARCH_MODEL")
    run.add_argument("--finbert", action="store_true", help="用本機 FinBERT 分析新聞標題")
    run.add_argument("--refresh", action="store_true", help="重新下載資料，不重用既有資料集")
    run.add_argument("--json", action="store_true", help="只輸出 JSON 結果")
    for flag in ("allow-small-model", "allow-low-quality-sentiment", "allow-point-fundamental"):
        run.add_argument(f"--{flag}", action="store_true", help="資料品質或模型例外（只算敏感性測試）")
    resume = subparsers.add_parser("resume", help="從中斷處繼續一個實驗")
    resume.add_argument("job_id")
    resume.add_argument("--model", default=None, help=argparse.SUPPRESS)
    resume.add_argument("--json", action="store_true")
    subparsers.add_parser("jobs", help="列出最近的實驗")
    refresh = subparsers.add_parser("refresh-fundamentals",
                                    help="只重建資料集的 SEC 基本面證據（另存新版本，不重抓新聞與行情）")
    refresh.add_argument("cases", nargs="*", help="TICKER:分析日，例如 NVDA:2024-12-31")
    refresh.add_argument("--all", action="store_true", help="研究範圍內所有股票 × 季末")
    news = subparsers.add_parser("refresh-news",
                                 help="只重建資料集的新聞（不截斷、全部以 FinBERT 評分；另存新版本，行情、財報、總經不變）")
    news.add_argument("--preregistered", required=True, metavar="PROTOCOL_HASH",
                      help="重建這個協議事前登記的所有資料集")
    news.add_argument("--output", default="refreshed-news.json", help="寫出舊→新資料集對照（JSON）")
    news.add_argument("--allow-live", action="store_true", help="本機新聞檔不足時呼叫 Alpha Vantage（會用掉額度）")
    subparsers.add_parser("studies", help="正式實驗（事前登記的研究）的整批進度")
    subparsers.add_parser("version", help="顯示版本")
    subparsers.add_parser("doctor", help="檢查安裝、資料目錄與金鑰是否就緒")
    power = subparsers.add_parser("power-plan", help="以模擬估計樣本數與檢定力")
    power.add_argument("--total-cases", type=int, default=180)
    power.add_argument("--cluster-size", type=int, default=9)
    power.add_argument("--replicates", type=int, default=2000)
    power.add_argument("--seed", type=int, default=905)
    canary = subparsers.add_parser("model-canary", help="用合成案例檢查模型是否能正確回答（正式實驗前的資格測試）")
    canary.add_argument("--model", default=None)
    canary.add_argument("--allow-small-model", action="store_true")
    serve = subparsers.add_parser("serve", help="開啟網頁研究台（預設 http://127.0.0.1:8000/）")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "version":
        print("stance-shift-research 3.0.0")
        return 0
    if args.command == "doctor":
        print(json.dumps(_doctor(), ensure_ascii=False, indent=2))
        return 0 if _doctor()["status"] == "ok" else 1
    if args.command == "power-plan":
        from .power import power_grid
        result = power_grid(total_cases=args.total_cases, cluster_size=args.cluster_size,
                            replicates=args.replicates, seed=args.seed)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    if args.command == "model-canary":
        from .canary import result_json, run_model_canary
        from .protocol import StudyProtocol
        values = {"dataset_kind": "synthetic", "allow_small_model": args.allow_small_model}
        if args.model:
            values["model"] = args.model
        result = run_model_canary(StudyProtocol(**values))
        print(result_json(result))
        return 0 if result["status"] == "pass" else 1
    if args.command in ("run", "resume"):
        return _run(args)
    if args.command == "refresh-news":
        return _refresh_news(args)
    if args.command == "refresh-fundamentals":
        return _refresh_fundamentals(args)
    if args.command == "jobs":
        return _jobs()
    if args.command == "studies":
        return _studies()
    if args.command == "serve":
        import uvicorn
        uvicorn.run("research_service.app:create_app", factory=True, host=args.host, port=args.port, reload=args.reload)
        return 0
    from .interactive import interactive

    try:
        return interactive()
    except KeyboardInterrupt:
        print("\n已取消。已完成的步驟都有保存；用 stance-shift jobs 查看，stance-shift resume <ID> 繼續。")
        return 130


if __name__ == "__main__":
    sys.exit(main())
