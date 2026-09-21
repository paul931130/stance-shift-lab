"""Run the synthetic model qualification check; no historical cases are queued."""
import argparse
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research_service.canary import result_json, run_model_canary
from research_service.protocol import StudyProtocol


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=None)
    parser.add_argument("--allow-small-model", action="store_true")
    args = parser.parse_args()
    values = {"dataset_kind": "synthetic", "allow_small_model": args.allow_small_model}
    if args.model:
        values["model"] = args.model
    result = run_model_canary(StudyProtocol(**values))
    print(result_json(result))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
