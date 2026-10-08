"""RQ3 domain-specialized debate: namespaces, views, aggregator, accounting. Stub models only."""
from dataclasses import asdict, replace
import json
import tempfile
import unittest

from research_service import aggregator, domain_debate, models
from research_service.data import digest, validate_dataset
from research_service.demo import demo_dataset, demo_model
from research_service.domain_debate import (DomainDebateEngine, DomainDebateSettings, rq3_fingerprint,
                                            rq3_job_config)
from research_service.engine import Engine
from research_service.protocol import (DOMAIN_NAMES, PROTOCOL_SOURCE_MODULES, StudyProtocol, decision_plan,
                                       prompt_source_digest)
from research_service.rq3_reporting import rq3_study_report
from research_service.storage import Store

RATIONALE = "Stub decision rationale for the synthetic test case."


def rq3_dataset(drop_domains=()):
    data = demo_dataset()
    evidence = []
    for item in data["evidence"]:
        if item["domain"] in drop_domains:
            continue
        if item["domain"] == "sentiment":
            # Three scored headlines naming the company become target FinBERT indicators.
            evidence.extend({**item, "evidence_id": f"demo-sentiment-{index}",
                             "headline": f"Nvidia shares rise in synthetic test headline {index}",
                             "claim": f"Nvidia shares rise in synthetic test headline {index}"}
                            for index in range(1, 4))
            continue
        evidence.append(item)
    return validate_dataset({**data, "evidence": evidence})


class StubModel:
    """Deterministic answers for every prompt kind; records what each prompt showed."""

    def __init__(self, directions=None, cross_cite_once=None):
        self.directions = directions or {}
        self.cross_cite_once = cross_cite_once  # (domain, real foreign evidence id)
        self.prompts = []

    def __call__(self, protocol, messages, seed=None, temperature=None):
        system, user = messages[0]["content"], messages[1]["content"]
        self.prompts.append((system, user))
        if "neutral research agent" in system:
            items = json.loads(user.split("Evidence: ")[1])
            result = {"summary": "stub summary", "evidence_ids": [items[0]["evidence_id"]], "risks": ["stub"],
                      "numeric_claims": []}
        elif domain_debate.VIEW_MARKER in system:
            payload = json.loads(user)
            ids = [item["evidence_id"] for item in payload["report"]["evidence"]]
            direction = self.directions.get(payload["domain"], "Buy")
            binary = direction in ("Buy", "Sell")
            result = {"direction": direction, "expected_return_pct": {"Buy": 3.0, "Sell": -3.0}.get(direction),
                      "confidence": .6, "supporting_evidence_ids": ids[:1] if binary else [],
                      "counter_evidence_ids": [], "uncertainty": "stub", "information_gaps": [],
                      "rationale": "stub domain view"}
        else:
            items = json.loads(user)["report"]["evidence"]
            action = "Sell" if "action MUST be Sell" in system else "Buy"
            cited = [items[0]["evidence_id"]]
            if self.cross_cite_once and f"only the {self.cross_cite_once[0]} domain" in system:
                cited = [self.cross_cite_once[1]]
                self.cross_cite_once = None
            result = {"action": action, "expected_return_pct": -5.0 if action == "Sell" else 5.0,
                      "confidence": .8, "rationale": RATIONALE, "evidence_ids": cited, "risks": ["stub"],
                      "numeric_claims": []}
            if "assigned debate stance" in system:
                result["strongest_counterpoint"] = "stub counterpoint"
            if "role-switch round" in system:
                result["rebutted_claim"] = RATIONALE
                result["confidence_shift"] = 0.0
        usage = {"prompt_tokens": 100, "completion_tokens": 10, "client_elapsed_seconds": 0.01}
        return result, {"prompt_hash": digest(messages), "usage": usage, "raw_response": json.dumps(result),
                        "provider_attempts": 1}

    def payloads(self, marker):
        return [(system, json.loads(user)) for system, user in self.prompts if marker in system]


def base_protocol():
    return StudyProtocol(dataset_kind="synthetic", bootstrap_replicates=199)


class FrozenProtocolTests(unittest.TestCase):
    def test_rq3_touches_no_frozen_module_or_protocol_field(self):
        self.assertNotIn("domain_debate", PROTOCOL_SOURCE_MODULES)
        self.assertNotIn("aggregator", PROTOCOL_SOURCE_MODULES)
        self.assertNotIn("domain_debate", asdict(StudyProtocol()))
        self.assertEqual(len(decision_plan(StudyProtocol())), 22)
        self.assertTrue(prompt_source_digest())

    def test_schema_wrapper_only_answers_domain_view_prompts(self):
        wrapper = models.output_schema_for
        self.assertTrue(wrapper.rq3_wrapper)
        for system in ("neutral research agent", "x action MUST be Sell", "The Adjudicator must choose Buy or Sell"):
            messages = [{"role": "system", "content": system}, {"role": "user", "content": "{}"}]
            self.assertEqual(wrapper(messages), wrapper.original(messages))
        view = [{"role": "system", "content": domain_debate.VIEW_MARKER}, {"role": "user", "content": "{}"}]
        self.assertEqual(wrapper(view)["properties"]["direction"]["enum"],
                         ["Buy", "Sell", "Abstain", "InsufficientInfo"])

    def test_rq3_hash_is_separate_and_settings_are_validated(self):
        protocol = base_protocol()
        settings = DomainDebateSettings()
        config = rq3_job_config(protocol, settings, ticker="NVDA")
        self.assertEqual(config["base_protocol_hash"], protocol.fingerprint)
        self.assertNotEqual(config["protocol_hash"], protocol.fingerprint)
        self.assertNotEqual(rq3_fingerprint(protocol, replace(settings, rule="fixed")), config["protocol_hash"])
        self.assertEqual(DomainDebateSettings.from_dict(json.loads(json.dumps(asdict(settings)))), settings)
        with self.assertRaises(ValueError):
            DomainDebateSettings(aggregator_prompt_version="aggregator-v9")
        with self.assertRaises(ValueError):
            DomainDebateSettings(rule="sometimes")
        with self.assertRaises(ValueError):
            rq3_job_config(StudyProtocol(version="v3-0929.1", dataset_kind="synthetic"), settings)

    def test_nominal_calls_per_rule(self):
        protocol = base_protocol()
        generalist = {"A": 1, "B": 7, "C": 7, "D": 7}
        expected = {"fixed": {"C_domain": 29}, "switch": {"D_domain": 29}, "both": {"C_domain": 29, "D_domain": 29}}
        for rule, arms in expected.items():
            settings = DomainDebateSettings(rule=rule)
            self.assertEqual(domain_debate.nominal_calls(protocol, settings), {**generalist, **arms})
            self.assertEqual(len(domain_debate.plan_keys(protocol, settings)), sum(arms.values()))


class ViewAndNamespaceTests(unittest.TestCase):
    items = [{"evidence_id": "tech-1", "domain": "technical", "claim": "return20 = 0.010000"}]

    def view(self, **changes):
        base = {"direction": "Buy", "expected_return_pct": 3.0, "confidence": .5,
                "supporting_evidence_ids": ["tech-1"], "counter_evidence_ids": [], "uncertainty": "u",
                "information_gaps": [], "rationale": "r"}
        return {**base, **changes}

    def test_abstain_and_insufficient_info_are_representable(self):
        for direction in ("Abstain", "InsufficientInfo"):
            view = domain_debate.validate_view(self.view(direction=direction, expected_return_pct=None,
                                                         supporting_evidence_ids=[]), self.items, "technical")
            self.assertFalse(view["binary"])
            self.assertIsNone(view["expected_return_pct"])

    def test_binary_view_rules(self):
        self.assertTrue(domain_debate.validate_view(self.view(), self.items, "technical")["binary"])
        for bad in (dict(expected_return_pct=-1.0), dict(supporting_evidence_ids=[]), dict(direction="Hold")):
            with self.assertRaises(ValueError):
                domain_debate.validate_view(self.view(**bad), self.items, "technical")

    def test_citation_outside_namespace_is_rejected(self):
        with self.assertRaises(domain_debate.NamespaceViolation):
            domain_debate.validate_view(self.view(counter_evidence_ids=["macro-1"]), self.items, "technical")
        self.assertEqual(domain_debate.namespace_violations(["tech-1", "macro-1"], self.items), ["macro-1"])

    def test_domain_report_keeps_only_its_slice(self):
        report = {"ticker": "NVDA", "analysis_date": "2024-12-31",
                  "research": {domain: {"status": "complete", "summary": domain, "evidence_ids": []}
                               for domain in DOMAIN_NAMES},
                  "evidence": [{"evidence_id": f"{domain}-1", "domain": domain, "claim": domain,
                                **({"comparative": True} if domain == "fundamental" else {})}
                               for domain in DOMAIN_NAMES]
                  + [{"evidence_id": "fundamental-point", "domain": "fundamental", "claim": "point fact"}],
                  "decision_calibration": {"technical": {"direction": "up"}, "sentiment": {"target": {}}},
                  "base_rates": {"hold_band_pct": 1.0}, "degraded_research_domains": ["macro"]}
        settings = DomainDebateSettings()
        for domain in DOMAIN_NAMES:
            sliced = domain_debate.domain_report(report, domain, settings)
            self.assertEqual({item["domain"] for item in sliced["evidence"]}, {domain})
            self.assertEqual(set(sliced["research"]), {domain})
            self.assertTrue(set(sliced["decision_calibration"]) <= {domain})
            self.assertEqual(sliced["base_rates"], {"hold_band_pct": 1.0})
        self.assertEqual([item["evidence_id"] for item in domain_debate.namespace(report, "fundamental")],
                         ["fundamental-1"])
        self.assertEqual(domain_debate.domain_report(report, "technical", replace(settings, share_base_rates=False))
                         ["base_rates"], {})

    def test_agreement_counts_only_valid_binary_views(self):
        def views(*directions):
            return [{"domain": domain, "direction": direction} for domain, direction in zip(DOMAIN_NAMES, directions)]
        self.assertEqual(domain_debate.agreement(views("Buy", "Buy", "Buy", "Buy"), "Buy")["pattern"], "4:0")
        self.assertEqual(domain_debate.agreement(views("Buy", "Sell", "Buy", "Buy"), "Sell")["final_relation"],
                         "against_majority")
        two = domain_debate.agreement(views("Buy", "Sell", "Sell", "Buy"), "Buy")
        self.assertEqual((two["pattern"], two["majority"], two["final_relation"]), ("2:2", "tie", "no_majority"))
        partial = domain_debate.agreement(views("Buy", "Abstain", "InsufficientInfo", "Sell"), "Buy")
        self.assertIsNone(partial["pattern"])
        self.assertEqual((partial["valid_binary"], partial["abstain"], partial["insufficient_info"]), (2, 1, 1))

    def test_aggregator_order_is_seeded_recorded_or_fixed(self):
        config = {"ticker": "NVDA", "analysis_date": "2024-12-31"}
        protocol, settings = base_protocol(), DomainDebateSettings()
        first = aggregator.input_order(protocol, settings, config, "C_domain")
        self.assertEqual(first, aggregator.input_order(protocol, settings, config, "C_domain"))
        self.assertIsNotNone(first[1])
        self.assertEqual(sorted(first[0]), sorted(DOMAIN_NAMES))
        self.assertEqual(aggregator.input_order(protocol, replace(settings, aggregator_order="fixed"), config,
                                                "C_domain"), (list(DOMAIN_NAMES), None))


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def create(self, settings, dataset=None):
        dataset_id = self.store.add_dataset(dataset or rq3_dataset())
        return self.store.create(rq3_job_config(base_protocol(), settings, ticker="NVDA",
                                                analysis_date="2024-12-31", dataset_id=dataset_id))

    def run_case(self, settings, model, dataset=None):
        job = self.create(settings, dataset)
        engine = DomainDebateEngine(self.store, model, parallel_workers=4)
        for _ in range(60):
            state = engine.advance(job)
            self.store.save_step(job["id"], state)
            job = self.store.get(job["id"])
            if job["status"] == "complete":
                return job
        self.fail(f"RQ3 case did not finish: {job['status']} {job['error']}")

    def test_plain_engine_and_tampered_hash_fail_closed(self):
        job = self.create(DomainDebateSettings())
        with self.assertRaises(ValueError):
            Engine(self.store, StubModel()).advance(job)
        tampered = {**job, "config": {**job["config"], "domain_debate": {**job["config"]["domain_debate"],
                                                                         "rule": "fixed"}}}
        with self.assertRaises(ValueError):
            DomainDebateEngine(self.store, StubModel()).advance(tampered)

    def test_both_rules_run_rule_matched_arms_through_the_same_gatekeeper(self):
        model = StubModel(directions={"sentiment": "Sell", "macro": "Abstain"})
        job = self.run_case(DomainDebateSettings(rule="both", aggregator_input="views_and_transcripts"), model)
        state = job["state"]
        self.assertEqual(len(state["records"]), 22)
        self.assertEqual(len(state["domain_records"]), 58)
        self.assertEqual(set(state["decisions"]), {"A", "B", "C", "D", "C_domain", "D_domain"})
        self.assertEqual(set(state["decisions"]["C_domain"]["gate"]), set(state["decisions"]["C"]["gate"]))
        self.assertIn(state["decisions"]["C_domain"]["candidate_action"], ("Buy", "Sell"))
        self.assertIn("C_domain", {row["group"] for row in state["cases"]})
        self.assertTrue(all(entry["protocol_hash"] == job["config"]["protocol_hash"] for entry in state["trace"]))
        diagnostics = state["rq3_diagnostics"]
        for arm in ("C_domain", "D_domain"):
            cost = diagnostics["resources"][arm]
            self.assertEqual((cost["nominal_calls"], cost["completed_calls"], cost["provider_attempts"]), (29, 29, 29))
            self.assertEqual((cost["prompt_tokens"], cost["completion_tokens"]), (2900, 290))
            self.assertIsNotNone(cost["critical_path_seconds"])
            self.assertIsNotNone(cost["end_to_end_critical_path_seconds"])
            agreement = diagnostics["agreement"][arm]
            self.assertIsNone(agreement["pattern"])  # macro abstained: only three binary views
            self.assertEqual((agreement["buy"], agreement["sell"], agreement["abstain"]), (2, 1, 1))
            self.assertEqual(agreement["aggregator"]["input_schema"], "views_and_transcripts")
        self.assertEqual(diagnostics["resources"]["C"]["prompt_tokens"], 700)
        self.assertEqual([pair["rule"] for pair in diagnostics["rule_matched_pairs"]], ["fixed", "switch"])
        self.assertAlmostEqual(diagnostics["rule_matched_pairs"][0]["domain_over_generalist"]["nominal_calls"], 29 / 7)
        self.assertFalse(diagnostics["compute_matching"]["enforced"])
        # The aggregator is the v3-1002.3 Adjudicator: Buy/Sell only, evidence-ID citations.
        aggregate = model.payloads(aggregator.AGGREGATOR_MARKER)
        self.assertEqual(len(aggregate), 2)
        for system, payload in aggregate:
            self.assertIn("The Adjudicator must choose Buy or Sell", system)
            self.assertIn("Refer to a fact by its evidence ID", system)
            self.assertEqual(models.output_schema_for([{"content": system}])["properties"]["action"]["enum"],
                             ["Buy", "Sell"])
            self.assertEqual(len(payload["report"]["domain_views"]), 4)
            self.assertTrue(payload["history"])
        for domain in DOMAIN_NAMES:
            prompts = model.payloads(f"you debate only the {domain} domain")
            self.assertEqual(len(prompts), 12)
            self.assertTrue(all(set(payload["report"]["research"]) == {domain} for _, payload in prompts))
            self.assertTrue(all("Refer to a fact by its evidence ID" in system for system, _ in prompts))
        report = rq3_study_report([job])
        self.assertEqual(report["status"], "complete")
        self.assertEqual([pair["domain"] for pair in report["rule_matched_pairs"]], ["C_domain", "D_domain"])

    def test_switched_domain_round_sees_only_its_own_round_one_turn(self):
        model = StubModel()
        job = self.run_case(DomainDebateSettings(rule="switch"), model)
        switched = [(system, payload) for system, payload in model.payloads("role-switch round")
                    if "Domain specialization" in system]
        self.assertEqual(len(switched), 8)
        for system, payload in switched:
            domain = next(name for name in DOMAIN_NAMES if f"only the {name} domain" in system)
            self.assertEqual(len(payload["history"]), 1)
            self.assertTrue(payload["history"][0]["key"].startswith(f"d_domain-{domain}-r1-"))
        stances = [record["stance"] for record in job["state"]["domain_records"]
                   if record["domain"] == "technical" and record["kind"] == "debate"]
        self.assertEqual(stances, ["BULL", "BEAR", "BEAR", "BULL", "BULL", "BEAR"])

    def test_foreign_citation_is_rejected_retried_and_costed(self):
        model = StubModel(cross_cite_once=("technical", "demo-macro-1"))
        job = self.run_case(DomainDebateSettings(rule="fixed"), model)
        retried = [record for record in job["state"]["domain_records"] if record["audit"].get("validation_retries")]
        self.assertEqual(len(retried), 1)
        self.assertEqual(retried[0]["domain"], "technical")
        self.assertEqual(retried[0]["audit"]["namespace"]["rejected_attempts"], 1)
        self.assertTrue(all(item.startswith("price-") for item in retried[0]["output"]["evidence_ids"]))
        cost = job["state"]["rq3_diagnostics"]["resources"]["C_domain"]
        self.assertEqual((cost["completed_calls"], cost["provider_attempts"], cost["validation_retry_calls"]),
                         (29, 30, 1))
        self.assertEqual(cost["prompt_tokens"], 3000)

    def test_missing_domain_is_insufficient_info_without_a_call(self):
        job = self.run_case(DomainDebateSettings(rule="fixed"), StubModel(), rq3_dataset(drop_domains=("macro",)))
        macro = [record for record in job["state"]["domain_records"] if record["domain"] == "macro"]
        self.assertEqual(len(macro), 1)
        self.assertEqual(macro[0]["output"]["direction"], "InsufficientInfo")
        self.assertTrue(macro[0]["audit"]["deterministic"])
        cost = job["state"]["rq3_diagnostics"]["resources"]["C_domain"]
        self.assertEqual((cost["nominal_calls"], cost["completed_calls"], cost["deterministic_skips"]), (29, 22, 1))
        self.assertEqual(job["state"]["rq3_diagnostics"]["agreement"]["C_domain"]["insufficient_info"], 1)

    def test_all_abstaining_views_still_get_a_committed_aggregator_decision(self):
        model = StubModel(directions={domain: "Abstain" for domain in DOMAIN_NAMES})
        job = self.run_case(DomainDebateSettings(rule="fixed", aggregator_order="fixed"), model)
        decision = job["state"]["decisions"]["C_domain"]
        self.assertIn(decision["candidate_action"], ("Buy", "Sell"))
        agreement = job["state"]["rq3_diagnostics"]["agreement"]["C_domain"]
        self.assertEqual((agreement["pattern"], agreement["abstain"]), (None, 4))
        self.assertEqual(agreement["aggregator"]["evidence_fallback"], "all_domain_namespaces")

    def test_demo_provider_completes_an_rq3_case(self):
        job = self.run_case(DomainDebateSettings(rule="both"), demo_model, demo_dataset())
        self.assertEqual(set(job["state"]["decisions"]), {"A", "B", "C", "D", "C_domain", "D_domain"})


if __name__ == "__main__":
    unittest.main()
