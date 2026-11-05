import contextlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from research_service.demo import demo_model
from research_service.tests import test_design_pilot
from scripts import check_pilot
from scripts.run_design_pilot import run

DIGEST = "sha256:" + "a" * 64


def mutate(output, change):
    """Edit every stored job (config, state) of a synthetic pilot, as a fault injector."""
    with contextlib.closing(sqlite3.connect(Path(output) / "data" / "research.sqlite3")) as db, db:
        for job_id, config, state in db.execute("SELECT id, config, state FROM jobs").fetchall():
            config, state = json.loads(config), json.loads(state)
            change(config, state)
            db.execute("UPDATE jobs SET config=?, state=? WHERE id=?",
                       (json.dumps(config), json.dumps(state), job_id))


def freeze_identity(config, state):
    """What a real GPU run records: frozen digests and an after_step pass for each of them."""
    if config.get("routed_model_identities"):
        for item in config["routed_model_identities"].values():
            item["digest"] = DIGEST
        state["model_identity_checks"] = [{"status": "pass", "phase": "after_step", "models": {
            model: {"digest": DIGEST} for model in config["routed_model_identities"]}}]
    else:
        config["model_identity"]["digest"] = DIGEST
        state["model_identity_checks"] = [{"status": "pass", "phase": "after_step",
                                           "id": config["model_identity"]["id"], "digest": DIGEST}]


class CheckPilotTests(unittest.TestCase):
    def build(self, directory, rq3):
        helper = test_design_pilot.DesignPilotTests()
        args = helper.setup_run(Path(directory), execute=True, rq3=rq3)
        run(args, model_call=demo_model)
        mutate(args.output, freeze_identity)
        return args.output

    def statuses(self, output):
        return {item["check"]: item["status"] for item in check_pilot.check_pilot(output)["checks"]}

    def failing(self, output):
        return sorted(name for name, status in self.statuses(output).items() if status == "fail")

    def test_clean_runs_pass_and_accept_data_directory(self):
        for rq3 in (False, True):
            with self.subTest(rq3=rq3), tempfile.TemporaryDirectory() as directory:
                output = self.build(directory, rq3)
                for target in (output, output / "data"):
                    result = check_pilot.check_pilot(target)
                    self.assertTrue(result["passed"], result["checks"])
                    self.assertEqual(len(result["checks"]), 9)
                statuses = self.statuses(output)
                self.assertEqual(statuses["c_budget_aggregation_prompt_not_truncated"],
                                 "pass" if rq3 else "not_applicable")
                timing = check_pilot.check_pilot(output)["timing"]
                self.assertEqual(timing["cases"], 1)
                self.assertIn("ESTIMATE", timing["note"])

    def test_missing_arm_fails_arm_check(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self.build(directory, False)
            mutate(output, lambda c, s: s.update(records=[
                r for r in s["records"] if not (r["group"] == "D" and r.get("assignment") == "BB")]))
            self.assertEqual(self.failing(output), ["jobs_complete_and_arms_present"])
        with tempfile.TemporaryDirectory() as directory:
            output = self.build(directory, True)
            mutate(output, lambda c, s: s.update(control_records=[
                r for r in s["control_records"] if r["arm"] != "C_partition"]))
            self.assertIn("jobs_complete_and_arms_present", self.failing(output))

    def test_missing_raw_response_fails_traceability(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self.build(directory, False)
            mutate(output, lambda c, s: s["records"][0]["audit"].pop("raw_response"))
            self.assertEqual(self.failing(output), ["raw_response_and_audit_traceable"])

    def test_digest_change_fails_digest_check(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self.build(directory, False)
            def swap(config, state):
                state["model_identity_checks"].append({"status": "pass", "phase": "after_step",
                    "models": {model: {"digest": "sha256:" + "b" * 64} for model in config["routed_model_identities"]}})
            mutate(output, swap)
            self.assertEqual(self.failing(output), ["weight_digest_unchanged"])

    def test_degraded_research_and_numeric_redaction_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self.build(directory, False)
            mutate(output, lambda c, s: s["report"].update(degraded_research_domains=["macro"]))
            self.assertEqual(self.failing(output), ["no_citation_schema_namespace_failures_or_degradation"])
        with tempfile.TemporaryDirectory() as directory:
            output = self.build(directory, False)
            mutate(output, lambda c, s: s["records"][0]["output"].update(invalid_evidence_ids=["E99"]))
            self.assertEqual(self.failing(output), ["no_citation_schema_namespace_failures_or_degradation"])

    def test_unbound_numbers_are_a_reported_rate_not_a_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self.build(directory, False)
            def keep(config, state):
                state["records"][0]["audit"]["validation_retries"] = [{"accepted_as_output": True}]
                state["records"][1]["audit"]["unsupported_numbers"] = [{"value": "12.3"}]
            mutate(output, keep)
            result = check_pilot.check_pilot(output)
            self.assertTrue(result["passed"], result["checks"])
            item = next(c for c in result["checks"] if c["check"] == "unbound_numbers_recorded")
            self.assertEqual((item["status"], item["flagged"]), ("info", 2))
            self.assertIn("RQ1 source snapshot", item["detail"])
            self.assertGreater(item["calls"], 2)
        with tempfile.TemporaryDirectory() as directory:
            output = self.build(directory, False)
            mutate(output, lambda c, s: s["records"][0]["audit"].update(numeric_redaction=["12.3"]))
            self.assertEqual(self.failing(output), ["no_citation_schema_namespace_failures_or_degradation"])

    def test_debate_engagement_is_reported_not_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self.build(directory, False)
            def repeat(config, state):
                records = {r["key"]: r for r in state["records"]}
                for key, record in records.items():
                    if "-r3-" in key and key.startswith("c"):
                        record["output"]["rationale"] = records[key.replace("-r3-", "-r2-")]["output"]["rationale"]
            mutate(output, repeat)
            result = check_pilot.check_pilot(output)
            self.assertTrue(result["passed"], result["checks"])
            item = next(c for c in result["checks"] if c["check"] == "debate_engagement")
            self.assertEqual(item["status"], "info")
            self.assertEqual(item["c_round3"]["identical"], 1.0)
            self.assertIn("RQ1 reference", item["detail"])

    def test_budget_prompt_at_context_limit_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self.build(directory, True)
            def fill(config, state):
                final = next(r for r in state["control_records"] if r["key"] == "c-budget-final")
                final["audit"]["usage"]["prompt_tokens"] = 8192
            mutate(output, fill)
            self.assertEqual(self.failing(output), ["c_budget_aggregation_prompt_not_truncated"])

    def test_missing_usage_and_pending_memory_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self.build(directory, False)
            mutate(output, lambda c, s: s["records"][0]["audit"]["usage"].pop("client_elapsed_seconds"))
            self.assertEqual(self.failing(output), ["tokens_retries_latency_recorded"])
        with tempfile.TemporaryDirectory() as directory:
            output = self.build(directory, False)
            mutate(output, lambda c, s: s["memory_audit"].update(pending_earlier_cases=["2024-01-02"]))
            self.assertEqual(self.failing(output), ["memory_no_pending_earlier_cases"])

    def test_cli_exit_codes_output_file_and_wal_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self.build(directory, False)
            report = Path(directory) / "check.json"
            with contextlib.redirect_stdout(io.StringIO()) as shown:
                self.assertEqual(check_pilot.main([str(output), "--output", str(report)]), 0)
            self.assertIn("ALL CHECKS PASS", shown.getvalue())
            self.assertTrue(json.loads(report.read_text(encoding="utf-8"))["passed"])
            with self.assertRaises(SystemExit) as stopped, contextlib.redirect_stderr(io.StringIO()):
                check_pilot.main([str(output), "--output", str(report)])
            self.assertEqual(stopped.exception.code, 2)
            mutate(output, lambda c, s: s["records"][0]["audit"].pop("raw_response"))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(check_pilot.main([str(output)]), 1)
            (output / "data" / "research.sqlite3-wal").touch()
            with self.assertRaises(ValueError):
                check_pilot.find_database(output)


if __name__ == "__main__":
    unittest.main()
