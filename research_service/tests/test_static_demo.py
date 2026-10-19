import importlib.util
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "static_demo.py"


@unittest.skipUnless(SCRIPT.exists() and (ROOT / ".git").exists() and shutil.which("git"),
                     "needs a git checkout with scripts/static_demo.py (not present in the Docker image)")
class StaticDemoBuildTests(unittest.TestCase):
    def test_build_static_demo(self):
        spec = importlib.util.spec_from_file_location("static_demo", SCRIPT)
        static_demo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(static_demo)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            responses = tmp_path / "responses.json"
            responses.write_text(json.dumps({"/api/config": {"demo_mode": True}}), encoding="utf-8")
            out = tmp_path / "app"
            static_demo.build(responses, out)

            data = (out / "demo-data.js").read_text(encoding="utf-8")
            self.assertTrue(data.startswith("globalThis.STATIC_DEMO ="))
            self.assertIn('"/api/config"', data)
            html = (out / "index.html").read_text(encoding="utf-8")
            self.assertLess(html.index('<script src="demo-data.js"></script>'), html.index('type="module"'))
            self.assertNotIn("/static/", html)
            self.assertIsNone(re.search(r'(?:src|href)="/assets/', html))
            self.assertIn('src="js/app.js"', html)
            self.assertTrue((out / "js" / "app.js").exists())
            self.assertIn("static-demo-banner", html)


if __name__ == "__main__":
    unittest.main()
