from dataclasses import asdict
from copy import deepcopy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from research_service.data import validate_dataset
from research_service.engine import Engine
from research_service.protocol import StudyProtocol
from research_service.shared_reports import bind_report, check_registered_reports
from research_service.storage import Store
from research_service.tests.test_model_router import RecordingModel
from research_service.tests.test_workflow import fixture


class SharedReportTests(unittest.TestCase):
    def test_new_seed_reuses_a_locked_report_without_repeating_research_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            dataset_id = store.add_dataset(validate_dataset(fixture()))
            first = StudyProtocol.router(dataset_kind="synthetic")
            config = {"ticker": "NVDA", "analysis_date": "2024-12-31", "dataset_id": dataset_id,
                      "protocol": asdict(first), "protocol_hash": first.fingerprint}
            bank = store.create(config, queued=False)
            for _ in range(10):
                state = Engine(store, RecordingModel()).advance(bank)
                store.save_step(bank["id"], state)
                bank = store.get(bank["id"])
                if "report" in bank["state"]:
                    break
            self.assertFalse(bank["state"]["records"])
            next_protocol = StudyProtocol.router(dataset_kind="synthetic", inference_seed=906)
            payload = SimpleNamespace(neutral_report_job_id=bank["id"], neutral_report_hash=bank["state"]["report_hash"],
                                       dataset_id=dataset_id, analysis_date="2024-12-31")
            shared = bind_report(store, payload, next_protocol)
            job = store.create({**config, "protocol": asdict(next_protocol), "protocol_hash": next_protocol.fingerprint,
                                "shared_neutral_report": shared})
            model = RecordingModel()
            for _ in range(2):
                state = Engine(store, model).advance(job)
                store.save_step(job["id"], state)
                job = store.get(job["id"])
            self.assertEqual(model.calls, [])
            self.assertEqual(job["state"]["report_hash"], bank["state"]["report_hash"])
            self.assertEqual(job["state"]["shared_report_provenance"]["source_job_id"], bank["id"])
            payload.neutral_report_hash = "0" * 64
            with self.assertRaisesRegex(ValueError, "hash"):
                bind_report(store, payload, next_protocol)

    def test_report_bank_must_be_an_idle_predecision_checkpoint_outside_the_target_seed(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            dataset_id = store.add_dataset(validate_dataset(fixture()))
            bank_protocol = StudyProtocol.router(dataset_kind="synthetic", inference_seed=904)
            config = {"ticker": "NVDA", "analysis_date": "2024-12-31", "dataset_id": dataset_id,
                      "protocol": asdict(bank_protocol), "protocol_hash": bank_protocol.fingerprint}
            bank = store.create(config, queued=False)
            engine = Engine(store, RecordingModel())
            for _ in range(10):
                state = engine.advance(bank)
                store.save_step(bank["id"], state)
                bank = store.get(bank["id"])
                if "report" in state:
                    break
            payload = SimpleNamespace(neutral_report_job_id=bank["id"], neutral_report_hash=state["report_hash"],
                                      dataset_id=dataset_id, analysis_date="2024-12-31")
            target = StudyProtocol.router(dataset_kind="synthetic", inference_seed=905)
            self.assertTrue(bind_report(store, payload, target))
            with self.assertRaisesRegex(ValueError, "seed"):
                bind_report(store, payload, bank_protocol)
            # These are independent disqualifiers, including an unsaved/in-flight
            # source and any evidence that source decisions were already seen.
            variants = [{"status": "running"}, {"status": "queued"}, {"owner": "worker"},
                        {"wants_run": 1}, {"state": {"finished": True}},
                        {"state": {"model_identity_failure": {"reason": "changed weights"}}},
                        *({"state": {key: [{"seen": True}]}} for key in
                          ("records", "routed_records", "decisions", "routed_decisions", "cases", "routed_cases")),
                        {"state": {"trace": [{"node": "parallel_decision_wave"}]}}]
            for change in variants:
                with self.subTest(change=change):
                    invalid = deepcopy(bank)
                    invalid.update({key: value for key, value in change.items() if key != "state"})
                    invalid["state"].update(change.get("state", {}))
                    fake_store = SimpleNamespace(get=lambda _: invalid)
                    with self.assertRaisesRegex(ValueError, "尚無決策"):
                        bind_report(fake_store, payload, target)

    def test_enqueue_cannot_replace_a_cases_preregistered_report_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory))
            store.save_registered_cases("protocol", [{"dataset_id": "case", "neutral_report_hash": "a" * 64}])
            with self.assertRaisesRegex(ValueError, "事前登記"):
                check_registered_reports(store, "protocol", [{"dataset_id": "case", "shared_neutral_report": {"report_hash": "b" * 64}}])
