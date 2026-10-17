"""Bind an offline RQ2 launch frame to a standalone report-bank backup."""
import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research_service.bind_launch import bind_launch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launch-dir", required=True, type=Path)
    parser.add_argument("--bank-db", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = bind_launch(args.launch_dir, args.bank_db, args.output)
    except Exception as error:
        parser.exit(1, f"Stopped: {type(error).__name__}\n")
    print(json.dumps({"output": str(args.output.resolve()), "formal_launch_ready": False,
                      "seeds": result["seeds"], "cases_per_seed": result["n_cases_per_seed"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
