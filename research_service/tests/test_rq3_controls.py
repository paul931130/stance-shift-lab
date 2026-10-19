from dataclasses import asdict
import json
import tempfile
import unittest

from research_service.demo import demo_model
from research_service.domain_debate import DomainDebateEngine, DomainDebateSettings, nominal_calls, rq3_job_config
from research_service.rq3_reporting import rq3_study_report
from research_service.storage import Store
from research_service.tests.test_domain_debate import base_protocol, rq3_dataset


class DomainControlTests(unittest.TestCase):
    def test_controls_run_checkpoint_resume_and_share_outcome_without_debate_leakage(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            dataset_id = store.add_dataset(rq3_dataset())
            protocol = base_protocol()
            settings = DomainDebateSettings(rule="fixed", include_controls=True)
            job = store.create(rq3_job_config(protocol, settings, ticker="NVDA", analysis_date="2024-12-31",
                                              dataset_id=dataset_id))
            prompts = []

            def model(protocol, messages, **kwargs):
                if "control:" in messages[0]["content"]:
                    prompts.append((messages[0]["content"], json.loads(messages[1]["content"])))
                return demo_model(protocol, messages, **kwargs)

            for _ in range(100):
                # Re-create the engine at each checkpoint: no control depends on in-memory progress.
                state = DomainDebateEngine(store, model).advance(job)
                store.save_step(job["id"], state)
                job = store.get(job["id"])
                if job["status"] == "complete":
                    break
            self.assertEqual(job["status"], "complete", job["error"])
            state = job["state"]
            self.assertEqual(set(state["decisions"]), {*"ABCD", "C_domain", "C_budget", "C_partition"})
            self.assertEqual(len(state["control_records"]), 30)
            self.assertEqual(nominal_calls(protocol, settings)["C_budget"], 29)
            partition = next(payload for system, payload in prompts if "Partition-only control" in system)
            self.assertNotIn("evidence", partition["report"])
            self.assertEqual(set(partition["report"]["domain_partitions"]),
                             {"technical", "fundamental", "sentiment", "macro"})
            self.assertFalse(partition["history"])
            samples = [payload for system, payload in prompts if "one independent directional proposal" in system]
            self.assertEqual(len(samples), 28)
            self.assertTrue(all(not payload["history"] for payload in samples))
            self.assertTrue(all(not payload.get("matured_same_group_memory") for payload in samples))
            final = next(payload for system, payload in prompts if "integrate 28 independent proposals" in system)
            self.assertEqual(len(final["history"]), 28)
            self.assertEqual({r["group"] for r in state["cases"]}, set(state["decisions"]))
            self.assertEqual(len(rq3_study_report([job])["rule_matched_pairs"]), 3)
            self.assertEqual(state["rq3_diagnostics"]["resources"]["C_budget"]["nominal_calls"], 29)
            self.assertEqual(asdict(settings)["include_controls"], True)

    def test_controls_require_the_registered_fixed_rule(self):
        with self.assertRaisesRegex(ValueError, "fixed rule"):
            DomainDebateSettings(rule="both", include_controls=True)
