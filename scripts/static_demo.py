"""Record demo-mode API responses and build a read-only static copy of the web UI.

  record: run the app in demo mode and save every successful GET /api/* JSON response.
  build:  export research_service/static from git HEAD and rewrite it for GitHub Pages.

The build reads the UI from git HEAD, so commit any frontend change before building.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO_URL = "https://github.com/paul931130/stance-shift-lab"
BANNER_TEXT = "線上展示版：介面與資料為本機展示模式事先錄製（合成資料、固定回應，非研究結果）；無法新增工作。完整系統請見 GitHub。"
BANNER_STYLE = (
    "position:fixed;top:0;left:0;right:0;z-index:99999;margin:0;padding:6px 12px;"
    "background:#fff3cd;color:#664d03;border-bottom:1px solid #e0c36a;"
    "font:13px/1.4 system-ui,sans-serif;text-align:center"
)


def record(port, data_dir, out):
    os.environ["RESEARCH_DEMO_MODE"] = "true"
    os.environ["RESEARCH_DATA_DIR"] = str(data_dir)
    import sys

    import uvicorn
    from starlette.responses import Response

    sys.path.insert(0, str(ROOT))
    from research_service.app import create_app

    app = create_app()
    responses = {}
    out = Path(out)

    @app.middleware("http")
    async def recorder(request, call_next):
        response = await call_next(request)
        path = request.url.path
        if not (request.method == "GET" and path.startswith("/api/") and 200 <= response.status_code < 300
                and "json" in response.headers.get("content-type", "")):
            return response
        body = b"".join([chunk async for chunk in response.body_iterator])
        try:
            key = path + ("?" + request.url.query if request.url.query else "")
            responses[key] = json.loads(body)
            tmp = out.with_name(out.name + ".tmp")
            tmp.write_text(json.dumps(responses, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, out)
        except ValueError:
            pass
        headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
        return Response(body, status_code=response.status_code, headers=headers)

    uvicorn.run(app, host="127.0.0.1", port=port)


def export_static(dest):
    """Copy research_service/static from git HEAD (not the working tree) into dest."""
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "static.tar"
        subprocess.run(["git", "archive", "HEAD", "research_service/static", "-o", str(archive)], cwd=ROOT, check=True)
        with tarfile.open(archive) as tar:
            tar.extractall(tmp, filter="data")
        shutil.copytree(Path(tmp) / "research_service" / "static", dest, dirs_exist_ok=True)


def rewrite_index(html):
    """Make the server-rooted index.html work from a sub-path and add the demo script and banner."""
    html = re.sub(r'<a\b[^>]*href="/taiwan"[^>]*>.*?</a>\s*', "", html, flags=re.S)
    html = html.replace('"/assets/js/', '"js/').replace('"/assets/', '"')
    html = html.replace('href="/"', 'href="./"')
    html = re.sub(r'(<script\b[^>]*type="module")', '<script src="demo-data.js"></script>\n\\1', html, count=1)
    banner = (
        f'<div id="static-demo-banner" style="{BANNER_STYLE}">{BANNER_TEXT} '
        f'<a href="{REPO_URL}" style="color:inherit;font-weight:600">GitHub</a></div>'
    )
    html, count = re.subn(r"(<body\b[^>]*>)", lambda m: m.group(1) + "\n" + banner, html, count=1)
    if count:
        html = html.replace("</head>", "<style>body{padding-top:38px !important}</style>\n</head>", 1)
    return html


def build(responses, out):
    out = Path(out)
    data = json.loads(Path(responses).read_text(encoding="utf-8"))
    if out.exists():
        shutil.rmtree(out)
    export_static(out)
    for name in ("taiwan.html", "taiwan.css", "js/taiwan.js"):
        (out / name).unlink(missing_ok=True)
    payload = json.dumps({"responses": data}, ensure_ascii=False).replace("</", "<\\/")
    (out / "demo-data.js").write_text(f"globalThis.STATIC_DEMO = {payload};\n", encoding="utf-8")
    index = out / "index.html"
    index.write_text(rewrite_index(index.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"built {out} with {len(data)} recorded responses")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    rec = sub.add_parser("record")
    rec.add_argument("--port", type=int, default=8015)
    rec.add_argument("--data-dir", required=True)
    rec.add_argument("--out", required=True)
    bld = sub.add_parser("build")
    bld.add_argument("--responses", required=True)
    bld.add_argument("--out", default="site/app")
    args = parser.parse_args()
    if args.command == "record":
        record(args.port, args.data_dir, args.out)
    else:
        build(args.responses, args.out)


if __name__ == "__main__":
    main()
