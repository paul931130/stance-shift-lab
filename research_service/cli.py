"""Cross-platform entry points for setup checks and the research service."""
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


def main(argv=None):
    parser = argparse.ArgumentParser(prog="stance-shift")
    subparsers = parser.add_subparsers(dest="command")
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
    if args.command == "serve":
        import uvicorn
        uvicorn.run("research_service.app:create_app", factory=True, host=args.host, port=args.port, reload=args.reload)
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
