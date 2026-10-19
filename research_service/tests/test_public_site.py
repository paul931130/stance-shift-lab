"""Publication checks must catch private-only links and stale generated UI."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


@unittest.skipUnless((SCRIPTS / "check_public_site.py").exists(), "needs repository publication scripts")
class PublicSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.object(sys, "path", [str(SCRIPTS), *sys.path]):
            spec = importlib.util.spec_from_file_location("check_public_site", SCRIPTS / "check_public_site.py")
            cls.checker = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.checker)

    def test_private_local_file_does_not_satisfy_a_public_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("[private](private.md) [web](https://example.com)", encoding="utf-8")
            (root / "private.md").write_text("not published", encoding="utf-8")
            errors = self.checker.broken_links(root, {"README.md"})
            self.assertEqual(len(errors), 1)
            self.assertIn("private.md", errors[0])

    def test_public_subpath_links_queries_and_anchors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "site" / "app").mkdir(parents=True)
            (root / "site/index.html").write_text('<a href="app/?tab=runs#result">demo</a>', encoding="utf-8")
            (root / "site/app/index.html").write_text('<a href="../#results">back</a>', encoding="utf-8")
            self.assertEqual(self.checker.broken_links(root, {"site/index.html", "site/app/index.html"}), [])

    def test_sync_updates_stale_assets_and_preserves_recorded_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "research_service/static").mkdir(parents=True)
            (root / "site/app").mkdir(parents=True)
            source = root / "research_service/static/index.html"
            source.write_text('<html><body><script type="module" src="/assets/js/app.js"></script></body></html>', encoding="utf-8")
            data = root / "site/app/demo-data.js"
            data.write_bytes(b"synthetic recording must stay identical\r\n")
            tracked = {"research_service/static/index.html", "site/app/index.html", "site/app/demo-data.js"}
            self.assertTrue(self.checker.stale_demo(root, tracked))
            self.assertEqual(self.checker.stale_demo(root, tracked, sync=True), [])
            self.assertEqual(self.checker.stale_demo(root, tracked), [])
            self.assertEqual(data.read_bytes(), b"synthetic recording must stay identical\r\n")
            source.write_text("<html><body>new UI</body></html>", encoding="utf-8")
            self.assertTrue(self.checker.stale_demo(root, tracked))


if __name__ == "__main__":
    unittest.main()
