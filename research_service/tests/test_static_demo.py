import importlib.util
import json
import re
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "static_demo.py"
spec = importlib.util.spec_from_file_location("static_demo", SCRIPT)
static_demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(static_demo)


def test_build_static_demo(tmp_path):
    responses = tmp_path / "responses.json"
    responses.write_text(json.dumps({"/api/config": {"demo_mode": True}}), encoding="utf-8")
    out = tmp_path / "app"
    static_demo.build(responses, out)

    data = (out / "demo-data.js").read_text(encoding="utf-8")
    assert data.startswith("globalThis.STATIC_DEMO =") and '"/api/config"' in data
    html = (out / "index.html").read_text(encoding="utf-8")
    assert html.index('<script src="demo-data.js"></script>') < html.index('type="module"')
    assert "/static/" not in html
    assert not re.search(r'(?:src|href)="/assets/', html)
    assert 'src="js/app.js"' in html and (out / "js" / "app.js").exists()
    assert "static-demo-banner" in html
