"""Prepare an offline RQ2/RQ3 launch package from a standalone RQ1 backup."""
import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research_service.launch_package import prepare_launch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", required=True, type=Path)
    parser.add_argument("--registration-hash", required=True)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model-a-base", required=True)
    parser.add_argument("--model-b-base", required=True)
    args = parser.parse_args()
    try:
        manifest = prepare_launch(args.source_db, args.registration_hash, args.plan, args.output,
                                  args.model_a_base, args.model_b_base, runner_path=Path(__file__))
    except Exception as error:
        parser.exit(1, f"Stopped: {type(error).__name__}\n")
    print(json.dumps({"output": str(args.output.resolve()), "formal_launch_ready": False,
                      "artifacts": len(manifest["artifacts_sha256"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
