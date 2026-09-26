"""Guards for two research-validity properties introduced in v3-0926.1."""
from dataclasses import asdict
import json
import tempfile
import unittest

from research_service.data import research_inputs, validate_dataset
from research_service.protocol import StudyProtocol
from research_service.storage import Store
from research_service.tests.test_workflow import fixture


def rescaled(dataset, factor):
    """The same history as an adjusted series rescaled by a later corporate action."""
    copy = json.loads(json.dumps(dataset))
    for row in copy["prices"]:
        for key in ("open", "high", "low", "close"):
            row[key] *= factor
    return copy


class TechnicalFeatureTests(unittest.TestCase):
    def test_technical_evidence_ignores_later_price_rescaling(self):
        # A 1:10 split after the analysis date divides every adjusted price by 10.
        # What the model sees must not change, or the features leak that future event.
        dataset = validate_dataset(fixture())
        original = research_inputs(dataset, "2024-12-31")
        split = research_inputs(rescaled(dataset, 0.1), "2024-12-31")

        def technical(inputs):
            return [(item["evidence_id"], item["claim"]) for item in inputs["domains"]["technical"]]

        self.assertEqual(technical(original), technical(split))
        self.assertEqual(original["decision_calibration"]["technical"], split["decision_calibration"]["technical"])

    def test_no_absolute_price_level_reaches_the_model(self):
        inputs = research_inputs(validate_dataset(fixture()), "2024-12-31")
        names = {item["evidence_id"].split("-")[1] for item in inputs["domains"]["technical"]}
        self.assertEqual(names, {"return20", "price_vs_mean20", "price_vs_mean60",
                                 "mean20_vs_mean60", "volatility60_annual"})
        self.assertNotIn("mean20", inputs["decision_calibration"]["technical"])


class MemoryOrderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name)
        self.protocol = StudyProtocol(dataset_kind="synthetic")

    def tearDown(self):
        self.tmp.cleanup()

    def create(self, analysis_date, ticker="NVDA"):
        return self.store.create({"ticker": ticker, "analysis_date": analysis_date, "dataset_id": "d",
                                  "protocol": asdict(self.protocol), "protocol_hash": self.protocol.fingerprint})

    def test_worker_claims_cases_in_analysis_date_order(self):
        # Queued newest-first, as a batch file might list them.
        for analysis_date in ("2024-12-31", "2023-12-29", "2024-06-28"):
            self.create(analysis_date)
        claimed = []
        while (job := self.store.claim()):
            claimed.append(job["config"]["analysis_date"])
            self.store.save_step(job["id"], {**job["state"], "finished": True})
        self.assertEqual(claimed, ["2023-12-29", "2024-06-28", "2024-12-31"])

    def test_memory_audit_lists_unfinished_earlier_cases_only(self):
        earlier = self.create("2023-12-29")
        self.create("2023-09-29", ticker="AAPL")  # other ticker: irrelevant to NVDA memory
        finished = self.create("2023-06-30")
        self.store.save_step(finished["id"], {**finished["state"], "finished": True})
        later = self.create("2024-12-31")

        audit = self.store.memory_audit(later["config"])
        self.assertEqual([case["id"] for case in audit["pending_earlier_cases"]], [earlier["id"]])
        self.assertEqual(self.store.memory_audit(earlier["config"])["pending_earlier_cases"], [])


if __name__ == "__main__":
    unittest.main()
