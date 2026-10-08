"""Run one RQ3 domain-debate case on the built-in synthetic demo data.

No network, no model: the deterministic demo provider answers every call.
The job is stored in a throwaway directory unless --data-dir is given.

    python scripts/run_rq3_demo.py --rule both --aggregator-input views
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research_service.demo import DEMO_ANALYSIS_DATE, DEMO_MODEL, demo_dataset, demo_model  # noqa: E402
from research_service.domain_debate import DomainDebateEngine, DomainDebateSettings, rq3_job_config  # noqa: E402
from research_service.protocol import StudyProtocol  # noqa: E402
from research_service.rq3_reporting import rq3_study_report  # noqa: E402
from research_service.storage import Store  # noqa: E402


def run(data_dir, settings):
    store = Store(data_dir)
    dataset = demo_dataset()
    dataset_id = store.add_dataset(dataset)
    protocol = StudyProtocol(model=DEMO_MODEL, dataset_kind="synthetic", allow_small_model=True,
                             bootstrap_replicates=199)
    job = store.create(rq3_job_config(protocol, settings, ticker=dataset["ticker"], analysis_date=DEMO_ANALYSIS_DATE,
                                      dataset_id=dataset_id, dataset_hash=dataset_id))
    engine = DomainDebateEngine(store, demo_model)
    for _ in range(80):
        state = engine.advance(job)
        store.save_step(job["id"], state)
        job = store.get(job["id"])
        if job["status"] == "complete":
            return job
    raise RuntimeError("demo RQ3 job did not finish")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rule", choices=("fixed", "switch", "both"), default="both")
    parser.add_argument("--aggregator-input", choices=("views", "views_and_transcripts"), default="views")
    parser.add_argument("--aggregator-order", choices=("randomized", "fixed"), default="randomized")
    parser.add_argument("--data-dir")
    args = parser.parse_args(argv)
    settings = DomainDebateSettings(rule=args.rule, aggregator_input=args.aggregator_input,
                                    aggregator_order=args.aggregator_order)
    with tempfile.TemporaryDirectory() as scratch:
        job = run(args.data_dir or scratch, settings)
        state = job["state"]
        print(json.dumps({"job_id": job["id"], "protocol_version": job["config"]["protocol"]["version"],
                          "rq3_version": settings.rq3_version, "protocol_hash": job["config"]["protocol_hash"],
                          "decisions": {group: {"candidate": item["candidate_action"], "gated": item["action"]}
                                        for group, item in state["decisions"].items()},
                          "rq3_diagnostics": state["rq3_diagnostics"],
                          "study": rq3_study_report([job])}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
