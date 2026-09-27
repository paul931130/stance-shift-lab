import unittest

from research_service.reporting import _completed_unique, stability_report, study_report


def completed_run(run_id, actions, expected):
    decisions = {group: {"candidate_action": action, "action": action,
                         "expected_return_pct": expected.get(group, 1.0),
                         "confidence": .8, "evidence_ids": [f"evidence-{group}"]}
                 for group, action in actions.items()}
    cases = [{"group": group, "decision_layer": "candidate", "horizon": 60,
              "cost_model": "corwin_schultz", "action": action,
              "candidate_action": action, "status": "complete"}
             for group, action in actions.items()]
    return {"id": run_id, "status": "complete", "created_at": run_id,
            "config": {"ticker": "NVDA", "analysis_date": "2024-12-31",
                       "dataset_id": "dataset-a", "protocol_hash": "protocol-a",
                       "model_identity": {"id": "ollama/qwen3:14b", "digest": "model-a"}},
            "state": {"finished": True, "report": {"dataset_kind": "synthetic"}, "decisions": decisions,
                      "cases": cases}}


class StabilityReportTests(unittest.TestCase):
    def test_repeated_runs_are_reported_instead_of_collapsed(self):
        first = completed_run("2024-01-01T00:00:00+00:00",
                              {group: "Buy" for group in "ABCD"}, {})
        second = completed_run("2024-01-02T00:00:00+00:00",
                               {"A": "Sell", "B": "Buy", "C": "Buy", "D": "Buy"},
                               {"A": -2.0})
        result = stability_report([first, second])
        self.assertEqual(result["status"], "descriptive_ready")
        self.assertEqual(result["repeated_cases"], 1)
        self.assertEqual(result["groups"]["A"]["action"]["agreement"], 0.0)
        self.assertGreater(result["groups"]["A"]["expected_return_pct"]["sd"], 0.0)
        self.assertEqual(result["groups"]["B"]["action"]["agreement"], 1.0)

    def test_mixed_protocols_are_not_compared(self):
        first = completed_run("2024-01-01T00:00:00+00:00",
                              {group: "Buy" for group in "ABCD"}, {})
        second = completed_run("2024-01-02T00:00:00+00:00",
                               {group: "Buy" for group in "ABCD"}, {})
        second["config"]["protocol_hash"] = "protocol-b"
        result = stability_report([first, second])
        self.assertEqual(result["status"], "mixed_protocols")
        self.assertEqual(result["repeated_cases"], 0)

    def test_repeatability_compares_runs_of_the_same_case_only(self):
        jobs = []
        for ticker, action in (("NVDA", "Buy"), ("AAPL", "Sell")):
            for repeat in range(2):
                job = completed_run(f"{ticker}-{repeat}", dict.fromkeys("ABCD", action), {})
                job["config"]["ticker"] = ticker
                jobs.append(job)
        result = stability_report(jobs)
        self.assertEqual(result["repeated_cases"], 2)
        self.assertEqual(result["groups"]["A"]["action"], {"agreement": 1.0, "pairs": 2, "basis": "within_case_pairs"})

    def test_stability_requires_the_same_dataset_and_resolved_model(self):
        first = completed_run("2024-01-01T00:00:00+00:00",
                              {group: "Buy" for group in "ABCD"}, {})
        second = completed_run("2024-01-02T00:00:00+00:00",
                               {group: "Sell" for group in "ABCD"}, {})
        second["config"]["dataset_id"] = "dataset-b"
        second["config"]["model_identity"] = {"id": "ollama/qwen3:14b", "digest": "model-b"}
        result = stability_report([first, second])
        self.assertEqual(result["status"], "no_repeated_complete_cases")
        self.assertEqual(result["repeated_cases"], 0)

    def test_synthetic_completed_runs_never_become_formal_inference(self):
        jobs = []
        for index in range(30):
            job = completed_run(f"2024-01-{index + 1:02d}T00:00:00+00:00",
                                {group: "Buy" for group in "ABCD"}, {})
            job["config"]["ticker"] = f"T{index}"
            job["config"]["analysis_date"] = f"D{index}"
            job["config"]["protocol"] = {"dataset_kind": "synthetic"}
            jobs.append(job)
        result = study_report(jobs)
        self.assertEqual(result["status"], "no_formal_cases")
        self.assertEqual(result["excluded_nonformal_runs"], 30)
        self.assertEqual(result["excluded_nonformal_reasons"], {"non_historical_dataset": 30})
        self.assertEqual(result["comparisons"], [])

    def test_formal_report_requires_preregistration_and_resolved_model(self):
        job = completed_run("2024-01-01T00:00:00+00:00",
                            {group: "Buy" for group in "ABCD"}, {})
        job["config"]["protocol"] = {"dataset_kind": "historical", "allow_small_model": False}
        job["config"]["formal_readiness"] = {"eligible": True}
        job["state"]["report"]["dataset_kind"] = "historical"
        not_frozen = study_report([job])
        self.assertEqual(not_frozen["excluded_nonformal_reasons"], {"study_not_preregistered": 1})
        job["config"]["model_identity"].pop("digest")
        unresolved = study_report([job], eligible_dataset_ids={"dataset-a"})
        self.assertEqual(unresolved["excluded_nonformal_reasons"], {"model_identity_unresolved": 1})

    def test_formal_report_excludes_post_freeze_dataset(self):
        job = completed_run("2024-01-01T00:00:00+00:00",
                            {group: "Buy" for group in "ABCD"}, {})
        job["config"]["protocol"] = {"dataset_kind": "historical", "allow_small_model": False}
        job["config"]["formal_readiness"] = {"eligible": True}
        job["state"]["report"]["dataset_kind"] = "historical"
        result = study_report([job], eligible_dataset_ids={"dataset-b"})
        self.assertEqual(result["excluded_nonformal_reasons"], {"not_preregistered_dataset": 1})

    def test_sample_locked_after_a_run_does_not_make_it_formal(self):
        job = completed_run("2024-01-01T00:00:00+00:00",
                            {group: "Buy" for group in "ABCD"}, {})
        job["config"]["protocol"] = {"dataset_kind": "historical", "allow_small_model": False}
        job["config"]["formal_readiness"] = {"eligible": True}
        job["state"]["report"]["dataset_kind"] = "historical"
        late = study_report([job], eligible_dataset_ids={"dataset-a"}, frozen_at="2024-06-01T00:00:00+00:00")
        self.assertEqual(late["excluded_nonformal_reasons"], {"run_before_preregistration": 1})
        from research_service.reporting import _formal_exclusion_reason
        self.assertIsNone(_formal_exclusion_reason(job, {"dataset-a"}, "2023-12-31T00:00:00+00:00"))

    def test_formal_report_keeps_exclusion_reasons_when_other_cases_are_usable(self):
        included = completed_run("2024-01-01T00:00:00+00:00",
                                 {group: "Buy" for group in "ABCD"}, {})
        excluded = completed_run("2024-01-02T00:00:00+00:00",
                                 {group: "Sell" for group in "ABCD"}, {})
        for job in (included, excluded):
            job["config"]["protocol"] = {"dataset_kind": "historical", "allow_small_model": False}
            job["config"]["formal_readiness"] = {"eligible": True}
            job["state"]["report"]["dataset_kind"] = "historical"
        excluded["config"].update(ticker="AAPL", analysis_date="2025-03-31", dataset_id="dataset-b")
        usable, audit = _completed_unique(
            [included, excluded], formal_only=True, eligible_dataset_ids={"dataset-a"})
        self.assertEqual(len(usable), 1)
        self.assertEqual(audit["nonformal_reasons"], {"not_preregistered_dataset": 1})


class StableModelIdentityTests(unittest.TestCase):
    def test_lookup_time_does_not_split_one_model(self):
        from research_service.reporting import stable_model_identity

        first = {"model_identity": {"id": "gemini/gemini-2.5-flash", "provider": "cloud_alias",
                                    "resolved_at": "2026-09-27T01:00:00+00:00"}}
        later = {"model_identity": {"id": "gemini/gemini-2.5-flash", "provider": "cloud_alias",
                                    "resolved_at": "2026-09-27T09:30:00+00:00"}}
        other = {"model_identity": {"id": "ollama/qwen3:14b", "digest": "abc", "modified_at": "x"}}
        self.assertEqual(stable_model_identity(first), stable_model_identity(later))
        self.assertNotEqual(stable_model_identity(first), stable_model_identity(other))


if __name__ == "__main__":
    unittest.main()
