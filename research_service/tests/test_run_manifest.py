from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import tempfile
import unittest

from research_service.protocol import QUARTER_DATES, STUDY_TICKERS, StudyProtocol, decision_plan
from research_service.reporting import _formal_exclusion_reason
from research_service.run_manifest import assert_manifest_source, build_manifest, qualification_verdict


class RunManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "research_service").mkdir()
        (self.root / "research_service" / "engine.py").write_text("frozen source", encoding="utf-8")
        (self.root / "pyproject.toml").write_text("version = 'test'", encoding="utf-8")
        self.protocol = StudyProtocol()
        self.identity = {"id": self.protocol.model, "digest": "fixed-model"}
        self.cases = [{"ticker": ticker, "analysis_date": day, "dataset_id": ticker + day}
                      for ticker in STUDY_TICKERS for day in QUARTER_DATES]

    def manifest(self, cases=None):
        return build_manifest(self.root, self.protocol, self.identity, cases or self.cases,
                              {"source_revision": "revision", "image_id": "sha256:image"})

    def test_freezes_exact_sample_and_rejects_duplicates_or_missing_cases(self):
        manifest = self.manifest()
        self.assertFalse(manifest["formal_launch_ready"])
        self.assertEqual(manifest["qualification_case"]["ticker"], "AAPL")
        for cases in (self.cases[:-1], self.cases[:-1] + [self.cases[0]]):
            with self.assertRaises(ValueError):
                self.manifest(cases)

    def test_source_drift_invalidates_a_frozen_manifest(self):
        manifest = self.manifest()
        assert_manifest_source(manifest, self.root)
        (self.root / "research_service" / "engine.py").write_text("changed source", encoding="utf-8")
        with self.assertRaises(ValueError):
            assert_manifest_source(manifest, self.root)

    def complete_job(self):
        p = self.protocol
        return {"status": "complete", "config": {"protocol": asdict(p), "model_identity": self.identity,
                "execution_purpose": "qualification", "formal_readiness": {"eligible": True}},
                "state": {"finished": True, "decisions": {group: {} for group in "ABCD"},
                          "model_identity_checks": [{**self.identity, "phase": "after_step", "status": "pass"}],
                          "records": [{"key": call.key, "output": {}} for call in decision_plan(p)],
                          "research": {domain: {} for domain in ("technical", "fundamental", "sentiment", "macro")},
                          "cases": [{"group": group, "horizon": horizon, "cost_model": cost, "decision_layer": layer}
                                    for group in "ABCD" for horizon in p.horizons for cost in p.cost_models
                                    for layer in ("candidate", "gated")]}}

    def test_completed_job_is_not_enough_if_calls_rows_identity_or_quality_are_missing(self):
        job = self.complete_job()
        self.assertTrue(qualification_verdict(job)["qualification_passed"])
        self.assertFalse(qualification_verdict(job)["formal_launch_ready"])
        self.assertEqual(_formal_exclusion_reason(job, []), "qualification_run")
        variants = []
        changed = deepcopy(job)
        changed["state"]["records"].pop()
        variants.append(changed)
        changed = deepcopy(job)
        changed["state"]["cases"].pop()
        variants.append(changed)
        changed = deepcopy(job)
        changed["state"]["model_identity_checks"][0]["digest"] = "other-model"
        variants.append(changed)
        changed = deepcopy(job)
        changed["state"]["records"][0]["output"]["redacted_numbers"] = ["100"]
        variants.append(changed)
        changed = deepcopy(job)
        changed["config"]["formal_readiness"]["eligible"] = False
        variants.append(changed)
        for changed in variants:
            with self.subTest(changed=qualification_verdict(changed)["blockers"]):
                self.assertFalse(qualification_verdict(changed)["qualification_passed"])


if __name__ == "__main__":
    unittest.main()
