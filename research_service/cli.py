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


def _jobs():
    from .storage import Store

    store = Store(os.getenv("RESEARCH_DATA_DIR", "research-data"))
    for job in store.job_summaries()[:30]:
        config = job["config"]
        print(f"{job['id']}  {job['status']:<9} {config['ticker']:<5} {config['analysis_date']}  "
              f"{config['protocol']['model']}  {job['steps']} 步")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="stance-shift",
        description="多代理人立場交換回測。不加指令直接執行 stance-shift，會一步步問股票、分析日與模型。")
    subparsers = parser.add_subparsers(dest="command")
    run = subparsers.add_parser("run", help="跑一個案例（不問問題，給腳本用）")
    run.add_argument("ticker")
    run.add_argument("date", help="季末日期，例如 2024-12-31，或今天")
    run.add_argument("--model", default=None, help="例如 gemini/gemini-2.5-flash、ollama/qwen3:14b；預設 RESEARCH_MODEL")
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
    subparsers.add_parser("version")
    subparsers.add_parser("doctor")
    power = subparsers.add_parser("power-plan", help="simulation-based design planning")
    power.add_argument("--total-cases", type=int, default=180)
    power.add_argument("--cluster-size", type=int, default=9)
    power.add_argument("--replicates", type=int, default=2000)
    power.add_argument("--seed", type=int, default=905)
    canary = subparsers.add_parser("model-canary", help="synthetic provider qualification")
    canary.add_argument("--model", default=None)
    canary.add_argument("--allow-small-model", action="store_true")
    serve = subparsers.add_parser("serve", help="start the FastAPI service")
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
    if args.command == "jobs":
        return _jobs()
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
