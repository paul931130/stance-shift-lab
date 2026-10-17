from copy import deepcopy
import unittest

from research_service.rq_study import matched_seed_inputs, rq2_study_report, select_cases
from research_service.rq3_reporting import _paired_cost_ratio, _resource_totals
from research_service.protocol import StudyProtocol


def run(name, *, day="2024-12-31", advantage=False):
    rows = [{"status": "complete", "horizon": 60, "cost_model": "corwin_schultz",
             "decision_layer": "candidate", "group": group if assignment == "AA" else f"{group}@{assignment}",
             "correct": advantage and group == "D" and assignment in ("AB", "BA")}
            for assignment in ("AA", "AB", "BA", "BB") for group in "CD"]
    return {"id": name, "created_at": "2025-01-01" + name, "status": "complete",
            "config": {"protocol_hash": "p", "ticker": "NVDA", "analysis_date": day,
                       "dataset_id": day, "formal_readiness": {"eligible": True},
                       "model_identity": {"id": "ollama/qwen3:32b", "digest": "fixed"},
                       "protocol": {"dataset_kind": "historical", "debate_assignments": ["AA", "AB", "BA", "BB"]}},
            "state": {"finished": True, "report": {"dataset_kind": "historical"},
                      "cases": [r for r in rows if "@" not in r["group"]],
                      "routed_cases": [r for r in rows if "@" in r["group"]]}}


def summary(jobs):
    return rq2_study_report(jobs, eligible_dataset_ids={j["config"]["dataset_id"] for j in jobs},
                             frozen_at="2024-01-01")


class RQStudyBoundaryTests(unittest.TestCase):
    def test_current_router_defaults_include_both_homogeneous_baselines(self):
        self.assertEqual(StudyProtocol.router().debate_assignments, ("AA", "AB", "BA", "BB"))

    def test_duplicate_repeat_does_not_reweight_the_interaction(self):
        a, b = run("a", advantage=True), run("b", day="2024-09-30")
        repeat = deepcopy(a)
        repeat["id"], repeat["created_at"] = "rerun", "2025-01-02"
        first, repeated = summary([a, b]), summary([a, b, repeat])
        self.assertEqual(first["cases"], 2)
        self.assertEqual(first["interaction"], .5)
        self.assertEqual(repeated["interaction"], first["interaction"])
        self.assertEqual(repeated["excluded"]["duplicates"], 1)
        self.assertEqual(repeated["interactions_by_baseline"], {"AA": .5, "BB": .5})

    def test_nonregistered_and_qualification_runs_are_not_formal(self):
        a = run("a")
        self.assertEqual(rq2_study_report([a])["cases"], 0)
        a["config"]["execution_purpose"] = "qualification"
        result = summary([a])
        self.assertEqual(result["cases"], 0)
        self.assertEqual(result["excluded"]["nonformal_reasons"], {"qualification_run": 1})

    def test_one_missing_assignment_excludes_the_whole_case(self):
        a, b = run("a", advantage=True), run("b", day="2024-09-30")
        a["state"]["routed_cases"] = [r for r in a["state"]["routed_cases"] if r["group"] != "D@BA"]
        result = summary([a, b])
        self.assertEqual(result["cases"], 1)
        self.assertEqual(result["interaction"], 0)
        self.assertEqual(result["excluded_incomplete_pairs"][0]["missing_arms"], ["D@BA"])

    def test_required_bb_is_on_the_same_complete_case_subset(self):
        a = run("a")
        a["state"]["routed_cases"] = [r for r in a["state"]["routed_cases"] if r["group"] != "C@BB"]
        self.assertEqual(summary([a])["cases"], 0)

    def test_mixed_debater_weights_fail_closed(self):
        a, b = run("a"), run("b", day="2024-09-30")
        a["config"]["routed_model_identities"] = {"B": {"digest": "one"}}
        b["config"]["routed_model_identities"] = {"B": {"digest": "two"}}
        with self.assertRaisesRegex(ValueError, "權重"):
            select_cases([a, b], formal_only=False)


class CostMissingnessTests(unittest.TestCase):
    def test_unknown_cost_is_not_zero_filled(self):
        data = [{"resources": {"C": {"total_tokens": 100}}}, {"resources": {"C": {"total_tokens": None}}}]
        result = _resource_totals(data, "C")
        self.assertIsNone(result["means"]["total_tokens"])
        self.assertEqual(result["observed_means"]["total_tokens"], 100)
        self.assertEqual(result["cases_observed_metric"]["total_tokens"], 1)

    def test_cost_ratio_uses_only_jointly_observed_cases(self):
        data = [{"resources": {"C": {"total_tokens": 100}, "C_domain": {"total_tokens": 300}}},
                {"resources": {"C": {"total_tokens": 900}, "C_domain": {"total_tokens": None}}}]
        self.assertEqual(_paired_cost_ratio(data, "C", "C_domain", "total_tokens"),
                         {"ratio": 3, "paired_cases": 1, "excluded_cases": 1})


class SeedFrameTests(unittest.TestCase):
    def test_three_repeats_remain_one_case_and_missing_arms_fail(self):
        arms = {f"{g}@{a}": True for a in ("AA", "AB", "BA", "BB") for g in "CD"}
        values = {seed: {"NVDA:2024-12-31": dict(arms)} for seed in (905, 906, 907)}
        dates = {seed: {"NVDA:2024-12-31": "2024-12-31"} for seed in values}
        result = matched_seed_inputs(values, dates)
        self.assertEqual(len(result["case_ids"]), 1)
        self.assertEqual(len(result["correctness"]), 3)
        del values[907]["NVDA:2024-12-31"]["D@BB"]
        with self.assertRaisesRegex(ValueError, "complete Boolean"):
            matched_seed_inputs(values, dates)
