"""Print a no-model-call power-planning grid for the study design."""
import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research_service.power import power_grid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--total-cases", type=int, default=180)
    parser.add_argument("--cluster-size", type=int, default=9)
    parser.add_argument("--replicates", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=905)
    args = parser.parse_args()
    result = power_grid(total_cases=args.total_cases, cluster_size=args.cluster_size,
                        replicates=args.replicates, seed=args.seed)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
