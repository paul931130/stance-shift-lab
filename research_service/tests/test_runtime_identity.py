from dataclasses import asdict
import tempfile
import unittest
from unittest.mock import patch

from research_service.engine import Engine, StepFailure
from research_service.model_identity import (ModelIdentityError, ModelIdentityUnavailable, resolve_ollama_identity,
                                             verify_model_identity)
from research_service.protocol import StudyProtocol
from research_service.reporting import _formal_exclusion_reason
from research_service.storage import Store
from research_service.tests.test_workflow import fake_model, fixture


class RuntimeIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        p = StudyProtocol()
        self.identity = {"id": p.model, "digest": "frozen-weights"}
        self.config = {"ticker": "NVDA", "analysis_date": "2024-12-31",
                       "dataset_id": self.store.add_dataset(fixture()),
                       "protocol": asdict(p), "protocol_hash": p.fingerprint,
                       "model_identity": self.identity}

    def engine(self, probe):
        result = Engine(self.store, fake_model, identity_probe=probe)
        # Exercise the built-in provider's guard without making any network call.
        result.uses_builtin_provider = True
        return result

    def test_mismatch_and_missing_digest_block_before_the_graph_runs(self):
        for expected in (self.identity, {"id": self.identity["id"]}):
            job = self.store.create({**self.config, "model_identity": expected})
            engine = self.engine(lambda model: {"id": model, "digest": "different"})
            with patch.object(engine.graph, "invoke") as advance:
                with self.assertRaises(ModelIdentityError):
                    engine.advance(job)
                advance.assert_not_called()

    def test_every_step_checks_before_and_after_and_ignores_lookup_timestamps(self):
        calls = []
        engine = self.engine(lambda model: calls.append(model) or {**self.identity, "resolved_at": "later"})
        job = self.store.create(self.config)
        for _ in range(2):
            state = engine.advance(job)
            self.store.save_step(job["id"], state)
            job = self.store.get(job["id"])
        self.assertEqual(len(calls), 4)
        self.assertEqual([item["phase"] for item in job["state"]["model_identity_checks"]],
                         ["before_step", "after_step"] * 2)

    def test_an_unreachable_weight_list_after_a_step_pauses_without_sealing(self):
        answers = iter([self.identity])

        def probe(model):
            try:
                return next(answers)
            except StopIteration:
                raise ModelIdentityUnavailable("proxy 404") from None
        engine = self.engine(probe)
        job = self.store.create(self.config)
        with self.assertRaises(StepFailure) as failure:
            engine.advance(job)
        self.assertNotIn("model_identity_failure", failure.exception.state)
        self.store.save_step(job["id"], failure.exception.state, str(failure.exception))
        job = self.store.get(job["id"])
        resumed = self.engine(lambda model: self.identity)
        resumed.advance(job)  # the next before-step check decides; no permanent seal

    def test_changed_weights_during_a_step_taint_and_seal_the_job(self):
        results = iter((self.identity, {**self.identity, "digest": "changed"}))
        engine = self.engine(lambda model: next(results))
        job = self.store.create(self.config)
        with self.assertRaises(StepFailure) as failure:
            engine.advance(job)
        self.store.save_step(job["id"], failure.exception.state, str(failure.exception))
        job = self.store.get(job["id"])
        self.assertEqual(job["status"], "paused")
        self.assertEqual(_formal_exclusion_reason(job, []), "runtime_model_identity_failed")
        with self.assertRaises(ModelIdentityError):
            engine.advance(job)

    def test_transport_failure_does_not_leak_endpoint_or_key(self):
        with patch("research_service.web.ollama.get_json", side_effect=RuntimeError("https://secret?key=TOKEN")):
            with self.assertRaises(ModelIdentityError) as error:
                resolve_ollama_identity(self.identity["id"])
        self.assertNotIn("TOKEN", str(error.exception))
        self.assertNotIn("https", str(error.exception))

    def test_resolver_requires_one_installed_digest_and_exact_model_name(self):
        with patch("research_service.web.ollama.get_json", return_value={"models": [
                {"name": self.identity["id"].removeprefix("ollama/"), "digest": "frozen-weights"}]}):
            self.assertEqual(resolve_ollama_identity(self.identity["id"]), self.identity)
        for inventory in ({"models": []}, {"models": [{"name": "qwen3:14b"}]}):
            with patch("research_service.web.ollama.get_json", return_value=inventory):
                with self.assertRaises(ModelIdentityError):
                    resolve_ollama_identity(self.identity["id"])
        with self.assertRaises(ModelIdentityError):
            verify_model_identity(self.config, lambda model: {**self.identity, "id": "ollama/other"})

    def test_memory_and_pending_case_audit_do_not_mix_model_weights(self):
        for weights in ("frozen-weights", "other-weights"):
            config = {**self.config, "analysis_date": "2023-12-31",
                      "model_identity": {**self.identity, "digest": weights}}
            job = self.store.create(config)
            case = {"group": "A", "horizon": 60, "cost_model": "corwin_schultz", "decision_layer": "gated",
                    "maturity_date": "2024-03-31", "action": "Buy", "correct": True, "net_return": .1}
            self.store.save_step(job["id"], {**job["state"], "finished": True, "cases": [case]})
            self.store.create(config)
        self.assertEqual(len(self.store.memory(self.config, "A")), 1)
        self.assertEqual(len(self.store.memory_audit(self.config)["pending_earlier_cases"]), 1)


if __name__ == "__main__":
    unittest.main()
