"""RQ2 Model Router (protocol v3-1006.1). Stub providers only: no model, GPU or network is used."""
from dataclasses import asdict
import io
import json
import os
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import URLError

from fastapi.testclient import TestClient

from research_service import model_router
from research_service.app import create_app
from research_service.breaker import is_provider_failure
from research_service.data import digest, validate_dataset
from research_service.demo import demo_model
from research_service.engine import Engine, StepFailure
from research_service.model_identity import ModelIdentityError, ModelIdentityMismatch
from research_service.models import generate
from research_service.protocol import (DEFAULT_DEBATE_MODEL_A, DEFAULT_DEBATE_MODEL_B, QUARTERLY_VERSION, ROUTER_VERSION,
                                       DecisionCall, RoutedDecisionCall, RouterProtocol, StudyProtocol, decision_plan,
                                       decision_wave, protocol_from, visible_history)
from research_service.storage import Store
from research_service.tests.test_workflow import fixture

MODEL_A, MODEL_B = DEFAULT_DEBATE_MODEL_A, DEFAULT_DEBATE_MODEL_B


def router_protocol(**overrides):
    return StudyProtocol.router(dataset_kind="synthetic", bootstrap_replicates=199, **overrides)


class RecordingModel:
    """Schema-valid stub that records which model each prompt was routed to."""

    def __init__(self, fail_model=None, reported_model=None):
        self.calls, self.lock = [], threading.Lock()
        self.fail_model, self.reported_model = fail_model, reported_model

    def __call__(self, protocol, messages, seed=None, temperature=None):
        with self.lock:
            self.calls.append({"model": protocol.model, "messages": messages, "seed": seed})
        if protocol.model == self.fail_model:
            raise URLError("connection refused")
        system = messages[0]["content"]
        if "neutral research agent" in system:
            items = json.loads(messages[1]["content"].split("Evidence: ")[1])
            result = {"summary": "Synthetic summary", "evidence_ids": [items[0]["evidence_id"]], "risks": ["test"],
                      "numeric_claims": []}
        else:
            items = json.loads(messages[1]["content"])["report"]["evidence"]
            action = "Sell" if "action MUST be Sell" in system else "Buy"
            result = {"action": action, "expected_return_pct": -5.0 if action == "Sell" else 5.0, "confidence": .8,
                      "rationale": "Synthetic test decision", "evidence_ids": [items[0]["evidence_id"]],
                      "risks": ["test"], "numeric_claims": []}
            if "assigned debate stance" in system:
                result["strongest_counterpoint"] = "Synthetic counterpoint supported by the shared evidence."
            if "role-switch round" in system:
                result["rebutted_claim"] = "Synthetic test decision"
                result["confidence_shift"] = 0.0
        usage = {"prompt_tokens": 10, "completion_tokens": 5, "client_elapsed_seconds": 0.01,
                 "model": self.reported_model or protocol.model.removeprefix("ollama/")}
        return result, {"prompt_hash": digest(messages), "usage": usage, "raw_response": json.dumps(result),
                        "provider_attempts": 1}


class RouterProtocolTests(unittest.TestCase):
    def test_defaults_follow_the_researcher_decision(self):
        protocol = router_protocol()
        self.assertEqual(protocol.version, ROUTER_VERSION)
        self.assertEqual((protocol.model, protocol.debate_model_a, protocol.debate_model_b),
                         (MODEL_A, MODEL_A, MODEL_B))
        self.assertEqual(protocol.debate_assignments, ("AA", "AB", "BA"))
        self.assertEqual(router_protocol(debate_assignments=("BB", "BA", "AA", "AB")).debate_assignments,
                         ("AA", "AB", "BA", "BB"))

    def test_existing_versions_are_untouched(self):
        legacy = StudyProtocol()
        self.assertEqual(legacy.version, QUARTERLY_VERSION)
        self.assertNotIn("debate_model_b", asdict(legacy))
        plan = decision_plan(legacy)
        self.assertEqual(len(plan), 22)
        self.assertTrue(all(type(call) is DecisionCall for call in plan))
        with self.assertRaises(ValueError):
            StudyProtocol(version=ROUTER_VERSION)
        with self.assertRaises(ValueError):
            RouterProtocol(version=QUARTERLY_VERSION, debate_model_b=MODEL_B)

    def test_invalid_assignments_and_models_are_rejected(self):
        for overrides in ({"debate_model_b": MODEL_A}, {"debate_assignments": ("AB", "BA")},
                          {"debate_assignments": ("AA", "AB")}, {"debate_assignments": ("AA", "XY")}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                router_protocol(**overrides)

    def test_endpoints_never_hold_secrets_and_url_is_not_identity(self):
        bad = ({MODEL_B: {"api_base": "http://user:pw@lab.example:11434"}},
               {MODEL_B: {"api_base": "http://lab.example:11434?token=x"}},
               {MODEL_B: {"password": "x"}}, {MODEL_B: {"api_key_env": "lower_case"}},
               {MODEL_B: {"timeout_seconds": 5}}, {"ollama/other:70b": {"timeout_seconds": 60}})
        for endpoints in bad:
            with self.subTest(endpoints=endpoints), self.assertRaises(ValueError):
                router_protocol(model_endpoints=endpoints)
        one = router_protocol(model_endpoints={MODEL_B: {"api_base": "http://lab-a.example:11434", "timeout_seconds": 600}})
        two = router_protocol(model_endpoints={MODEL_B: {"api_base": "http://lab-b.example:11434", "timeout_seconds": 600}})
        three = router_protocol(model_endpoints={MODEL_B: {"api_base": "http://lab-b.example:11434", "timeout_seconds": 900}})
        self.assertEqual(one.fingerprint, two.fingerprint)
        self.assertNotEqual(two.fingerprint, three.fingerprint)
        self.assertNotEqual(router_protocol().fingerprint, router_protocol(debate_model_b="ollama/llama3.3:70b").fingerprint)
        round_trip = protocol_from(json.loads(json.dumps(asdict(one))))
        self.assertIsInstance(round_trip, RouterProtocol)
        self.assertEqual(round_trip.fingerprint, one.fingerprint)

    def test_plan_fixes_model_per_agent_and_flips_only_the_d_round2_stance(self):
        protocol = router_protocol(debate_assignments=("AA", "AB", "BA", "BB"))
        plan = decision_plan(protocol)
        self.assertEqual(len(plan), 1 + 7 + 4 * 2 * 7)
        self.assertEqual(len({call.key for call in plan}), len(plan))
        debate = [call for call in plan if isinstance(call, RoutedDecisionCall) and call.kind == "debate"]
        expected_slots = {"AA": ("A", "A"), "AB": ("A", "B"), "BA": ("B", "A"), "BB": ("B", "B")}
        for call in debate:
            index = 0 if call.agent == "agent-a" else 1
            self.assertEqual(call.model_slot, expected_slots[call.assignment][index])
            self.assertEqual(call.original_stance, "BULL" if call.agent == "agent-a" else "BEAR")
            switched = call.group == "D" and call.round == 2
            self.assertEqual(call.stance != call.original_stance, switched)
        # AA keeps the RQ1 keys, so the homogeneous arm is still "C"/"D" for every RQ1 consumer.
        self.assertIn("c-r1-agent-a", {call.key for call in plan})
        self.assertIn("d-ba-r2-agent-b", {call.key for call in plan})
        first_wave = decision_wave(protocol, [])
        self.assertEqual({call.round for call in first_wave if call.round}, {1})
        self.assertEqual(len([call for call in first_wave if call.group in "CD"]), 4 * 2 * 2)

    def test_switch_round_sees_only_its_own_round1_in_the_same_arm(self):
        protocol = router_protocol()
        plan = {call.key: call for call in decision_plan(protocol)}
        records = [{**asdict(call), "output": {}} for call in plan.values() if call.group in "CD" and call.round == 1]
        visible = visible_history(plan["d-ab-r2-agent-a"], records, protocol)
        self.assertEqual([record["key"] for record in visible], ["d-ab-r1-agent-a"])
        visible = visible_history(plan["c-ba-r2-agent-b"], records, protocol)
        self.assertEqual(sorted(record["key"] for record in visible), ["c-ba-r1-agent-a", "c-ba-r1-agent-b"])

    def test_seeds_are_shared_across_assignments(self):
        self.assertEqual(model_router.seed_key("d-ab-r2-agent-a:validation-retry-2"), "d-r2-agent-a:validation-retry-2")
        self.assertEqual(model_router.seed_key("c-r1-agent-b"), "c-r1-agent-b")


class RouterEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name)
        self.dataset_id = self.store.add_dataset(validate_dataset(fixture()))

    def tearDown(self):
        self.tmp.cleanup()

    def run_job(self, protocol, model, max_steps=60):
        job = self.store.create({"ticker": "NVDA", "analysis_date": "2024-12-31", "dataset_id": self.dataset_id,
                                 "protocol": asdict(protocol), "protocol_hash": protocol.fingerprint})
        engine = Engine(self.store, model)
        for _ in range(max_steps):
            state = engine.advance(job)
            self.store.save_step(job["id"], state)
            job = self.store.get(job["id"])
            if job["status"] == "complete":
                return job
        self.fail("router workflow did not complete")

    def test_full_router_case_records_routes_and_blinds_the_judge(self):
        model = RecordingModel()
        job = self.run_job(router_protocol(), model)
        state = job["state"]
        records = {record["key"]: record for record in state["records"]}
        self.assertEqual(len(records), 1 + 7 + 3 * 2 * 7)
        bull_bear = {"AA": (MODEL_A, MODEL_A), "AB": (MODEL_A, MODEL_B), "BA": (MODEL_B, MODEL_A)}
        for record in records.values():
            route = record["audit"]["model_route"]
            for field in ("agent", "original_stance", "round_stance", "model_slot", "provider", "endpoint",
                          "seed_requested", "seed_applied", "temperature", "prompt_tokens", "completion_tokens",
                          "latency_seconds", "provider_attempts", "validation_retries"):
                self.assertIn(field, route)
            if record["kind"] == "debate":
                expected = bull_bear[record["assignment"]][0 if record["agent"] == "agent-a" else 1]
                self.assertEqual(route["model"], expected, record["key"])
                self.assertEqual(route["round_stance"], record["stance"])
                self.assertEqual(route["seed_applied"], True)
            else:
                self.assertEqual(route["model"], MODEL_A)  # Judge and arms A/B never leave the fixed model.
        for domain, item in state["research"].items():
            if item.get("audit", {}).get("model_route"):
                self.assertEqual(item["audit"]["model_route"]["model_slot"], "RESEARCH")
        # Common random numbers: the same turn has the same seed in every assignment.
        self.assertEqual(records["c-r1-agent-a"]["audit"]["seed"], records["c-ab-r1-agent-a"]["audit"]["seed"])
        # The D switch turn of AB quotes only its own (model A) round-1 turn, from the AB arm.
        switch_prompt = next(call for call in model.calls
                             if "role-switch round" in call["messages"][0]["content"] and call["model"] == MODEL_B)
        history = json.loads(switch_prompt["messages"][1]["content"])["history"]
        self.assertEqual(len(history), 1)
        self.assertNotIn("-ab-", history[0]["key"])
        # The Judge sees blinded speakers only, in a recorded order.
        judge_prompts = [call["messages"] for call in model.calls if "neutral Adjudicator" in call["messages"][0]["content"]]
        self.assertEqual(len(judge_prompts), 6)
        for messages in judge_prompts:
            text = messages[1]["content"]
            for leak in (MODEL_A, MODEL_B, "qwen", "gemma", "agent-a", "agent-b", "-ab-", "-ba-"):
                self.assertNotIn(leak, text)
            speakers = [item["speaker"] for item in json.loads(text)["history"]]
            self.assertEqual(sorted(set(speakers)), ["Debater 1", "Debater 2"])
            self.assertEqual(speakers[0], "Debater 1")
        presentation = records["d-ba-adjudication"]["judge_presentation"]
        self.assertEqual(sorted(presentation["order"]), ["agent-a", "agent-b"])
        # RQ1 outputs are the AA arm; heterogeneous arms are gated and backtested separately.
        self.assertEqual(set(state["decisions"]), set("ABCD"))
        self.assertEqual(set(state["routed_decisions"]), {"C@AB", "D@AB", "C@BA", "D@BA"})
        self.assertEqual({row["group"] for row in state["routed_cases"]}, {"C@AB", "D@AB", "C@BA", "D@BA"})
        self.assertEqual(set(state["routed_compute_usage"]), {"C@AA", "D@AA", "C@AB", "D@AB", "C@BA", "D@BA"})
        self.assertEqual(state["routed_compute_usage"]["D@AB"]["calls"], 7)
        summary = model_router.rq2_summary([job])
        self.assertEqual(summary["cases"], 1)
        self.assertIn("D@BA", summary["accuracy"])

    def test_unreachable_model_b_fails_the_step_without_fallback(self):
        model = RecordingModel(fail_model=MODEL_B)
        protocol = router_protocol(model_endpoints={MODEL_B: {"api_base": "http://lab.example:11434"}})
        job = self.store.create({"ticker": "NVDA", "analysis_date": "2024-12-31", "dataset_id": self.dataset_id,
                                 "protocol": asdict(protocol), "protocol_hash": protocol.fingerprint})
        engine = Engine(self.store, model)
        with self.assertRaises(StepFailure) as raised:
            for _ in range(10):
                state = engine.advance(job)
                self.store.save_step(job["id"], state)
                job = self.store.get(job["id"])
        self.assertIn(MODEL_B, str(raised.exception))
        self.assertIn("http://lab.example:11434", str(raised.exception))
        self.assertTrue(raised.exception.provider_failure)
        self.assertNotIn(MODEL_B, {record["audit"]["model_route"]["model"] for record in raised.exception.state["records"]})
        # Model B was asked, and no B turn was ever answered by another model.
        self.assertTrue(any(call["model"] == MODEL_B for call in model.calls))

    def test_provider_answering_with_another_model_is_rejected(self):
        model = RecordingModel(reported_model="llama3:8b")
        protocol = router_protocol()
        call = next(call for call in decision_plan(protocol) if call.key == "c-ab-r1-agent-b")
        with self.assertRaises(model_router.ModelRouteMismatch):
            model_router.call_with_route(model, protocol, call, call.key, [
                {"role": "system", "content": "You are a neutral research agent."},
                {"role": "user", "content": 'Evidence: [{"evidence_id": "E1"}]'}], 1, {})

    def test_cloud_model_b_records_reported_seed_support(self):
        def cloud(protocol, messages, seed=None, temperature=None):
            return {"ok": True}, {"usage": {"seed_applied": False, "provider_model": "gemini-2.5-flash"}}
        protocol = router_protocol(debate_model_b="gemini/gemini-2.5-flash")
        call = next(call for call in decision_plan(protocol) if call.key == "c-ab-r1-agent-b")
        _, audit = model_router.call_with_route(cloud, protocol, call, call.key, [], 7, {"seed": 7, "temperature": .2})
        route = audit["model_route"]
        self.assertEqual((route["provider"], route["seed_applied"], route["seed_applied_basis"]),
                         ("gemini", False, "provider_report"))
        self.assertEqual(route["endpoint"], "gemini:provider-default")


class RouterIdentityTests(unittest.TestCase):
    def setUp(self):
        self.protocol = router_protocol(model_endpoints={MODEL_B: {"api_base": "http://lab.example:11434"}})
        self.digests = {MODEL_A: "sha-a", MODEL_B: "sha-b"}

    def probe(self, protocol, model):
        return {"id": model, "digest": self.digests[model], "endpoint": model_router.endpoint_label(protocol, model)}

    def test_identities_lock_every_model_on_its_own_endpoint(self):
        identities = model_router.resolve_identities(self.protocol, probe=self.probe)
        self.assertEqual(identities[MODEL_B]["endpoint"], "http://lab.example:11434")
        self.assertEqual(identities[MODEL_A]["slots"], ["JUDGE", "A"])
        config = {"protocol": asdict(self.protocol), "routed_model_identities": identities}
        locked = model_router.registration_digest(config)
        self.assertTrue(locked.startswith("route-sha256:"))
        self.assertEqual(model_router.verify_identities(config, self.probe)["status"], "pass")
        self.digests[MODEL_B] = "sha-b-new"
        with self.assertRaises(ModelIdentityMismatch):
            model_router.verify_identities(config, self.probe)
        self.assertIsNone(model_router.registration_digest({**config, "routed_model_identities": {MODEL_A: {"digest": "x"}, MODEL_B: {}}}))
        with self.assertRaises(ModelIdentityError):
            model_router.verify_identities({**config, "routed_model_identities": {}}, self.probe)

    def test_unreachable_endpoint_is_reported_by_host_only(self):
        def refuse(request, timeout):
            raise URLError("refused")
        with patch.object(model_router, "gputw_urlopen", refuse), \
                self.assertRaises(model_router.ModelRouteUnavailable) as raised:
            model_router.probe_ollama_endpoint(self.protocol, MODEL_B)
        self.assertIn("http://lab.example:11434", str(raised.exception))
        self.assertTrue(is_provider_failure(raised.exception))


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class GenerateEndpointTests(unittest.TestCase):
    def test_model_b_uses_its_own_endpoint_timeout_and_token_only(self):
        protocol = router_protocol(model_endpoints={MODEL_B: {"api_base": "http://lab.example:11434",
                                                              "timeout_seconds": 900, "api_key_env": "LAB_OLLAMA_TOKEN"}})
        call = next(call for call in decision_plan(protocol) if call.key == "c-ab-r1-agent-b")
        routed = model_router.protocol_for(protocol, call)
        seen = []

        def fake_urlopen(request, timeout):
            seen.append((request.full_url, dict(request.header_items()), timeout, json.loads(request.data)))
            body = {"message": {"content": json.dumps({"summary": "s", "evidence_ids": ["E1"], "risks": [],
                                                       "numeric_claims": []})},
                    "model": "gemma3:27b", "prompt_eval_count": 1, "eval_count": 1}
            return FakeResponse(json.dumps(body).encode())
        env = {"LAB_OLLAMA_TOKEN": "lab-secret", "GPUTW_OLLAMA_API_KEY": "gputw-secret",
               "GPUTW_OLLAMA_BASE_URL": "https://gpu.example"}
        with patch.dict(os.environ, env), patch("research_service.models.gputw_urlopen", fake_urlopen):
            generate(routed, [{"role": "system", "content": "You are a neutral research agent."},
                              {"role": "user", "content": "x"}], seed=3)
        url, headers, timeout, body = seen[0]
        self.assertEqual(url, "http://lab.example:11434/api/chat")
        self.assertEqual(timeout, 900)
        self.assertEqual(headers.get("Authorization"), "Bearer lab-secret")
        self.assertEqual(body["model"], "gemma3:27b")
        # The Judge/model A keeps the default endpoint and its own token.
        seen.clear()
        with patch.dict(os.environ, env), patch("research_service.models.gputw_urlopen", fake_urlopen):
            generate(protocol, [{"role": "system", "content": "You are a neutral research agent."},
                                {"role": "user", "content": "x"}], seed=3)
        self.assertEqual(seen[0][0], "https://gpu.example/api/chat")
        self.assertEqual(seen[0][1].get("Authorization"), "Bearer gputw-secret")


class DemoModeRouterTests(unittest.TestCase):
    def test_demo_api_creates_and_runs_an_ab_ba_case(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            with patch.dict(os.environ, {"RESEARCH_DEMO_MODE": "true"}, clear=False):
                with TestClient(create_app(store, start_worker=False)) as client:
                    dataset = client.get("/api/datasets").json()[0]
                    response = client.post("/api/jobs", json={
                        "dataset_id": dataset["id"], "analysis_date": "2024-12-31",
                        "debate_model_b": "ollama/demo-synthetic-b", "debate_assignments": ["AA", "AB", "BA"]})
                    self.assertEqual(response.status_code, 200, response.text)
                    job = response.json()
            config = job["config"]
            self.assertEqual(config["protocol"]["version"], ROUTER_VERSION)
            self.assertEqual(set(config["routed_model_identities"]), {"ollama/demo-synthetic", "ollama/demo-synthetic-b"})
            job = store.get(job["id"])
            engine = Engine(store, demo_model)
            for _ in range(60):
                store.save_step(job["id"], engine.advance(job))
                job = store.get(job["id"])
                if job["status"] == "complete":
                    break
            self.assertEqual(job["status"], "complete")
            self.assertEqual(set(job["state"]["routed_decisions"]), {"C@AB", "D@AB", "C@BA", "D@BA"})


if __name__ == "__main__":
    unittest.main()
