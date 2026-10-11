import copy
import tempfile
import unittest

from research_service.demo import demo_dataset
from research_service.storage import Store
from scripts.dataset_bundle import import_bundle


class DatasetBundleTests(unittest.TestCase):
    def setUp(self):
        self.source_dir = tempfile.TemporaryDirectory()
        self.target_dir = tempfile.TemporaryDirectory()
        self.source = Store(self.source_dir.name)
        self.dataset_id = self.source.add_dataset(demo_dataset())
        self.bundle = {"ticker": "NVDA", "datasets": [
            {"id": self.dataset_id, "created_at": "2026-01-01", "content": self.source.dataset(self.dataset_id)}]}

    def tearDown(self):
        self.source_dir.cleanup()
        self.target_dir.cleanup()

    def test_copies_content_verbatim_and_keeps_the_original_id(self):
        result = import_bundle(self.bundle, self.target_dir.name)
        self.assertEqual(result, {"added": 1, "already_present": 0, "total": 1})
        target = Store(self.target_dir.name)
        self.assertEqual([row["id"] for row in target.datasets()], [self.dataset_id])
        self.assertEqual(target.dataset(self.dataset_id), self.source.dataset(self.dataset_id))

    def test_import_is_idempotent(self):
        import_bundle(self.bundle, self.target_dir.name)
        result = import_bundle(self.bundle, self.target_dir.name)
        self.assertEqual(result, {"added": 0, "already_present": 1, "total": 1})
        self.assertEqual(len(Store(self.target_dir.name).datasets()), 1)

    def test_refuses_content_that_no_longer_matches_its_id(self):
        tampered = copy.deepcopy(self.bundle)
        tampered["datasets"][0]["content"]["source"] = "edited after collection"
        with self.assertRaisesRegex(ValueError, "does not hash back"):
            import_bundle(tampered, self.target_dir.name)
        self.assertEqual(Store(self.target_dir.name).datasets(), [])


if __name__ == "__main__":
    unittest.main()
