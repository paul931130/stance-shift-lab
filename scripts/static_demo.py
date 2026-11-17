"""Record demo-mode API responses and build a read-only static copy of the web UI.

  record: run the app in demo mode and save the last GET /api/* JSON response per URL plus a timed timeline of every /api/* JSON response.
  build:  copy research_service/static from the working tree and rewrite it for GitHub Pages.

The build uses the working tree, including uncommitted frontend changes.
"""
import argparse
import json
import os
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO_URL = "https://github.com/paul931130/stance-shift-lab"
BANNER_TEXT = "研究台介面預覽：合成錄製資料與固定回應，非研究結果，無法新增分析。想分析自己的股票，請建立私人雲端研究台。"
BANNER_STYLE = (
    "margin:0;padding:6px 12px;"
    "background:#fff3cd;color:#664d03;border-bottom:1px solid #e0c36a;"
    "font:13px/1.4 system-ui,sans-serif;text-align:center"
)

SITENAV_STYLE = "html{scrollbar-gutter:stable}\n.sitenav{position:sticky;top:0;z-index:100;display:flex;align-items:center;gap:0 18px;height:48px;padding:0 24px;margin:0;background:rgba(10,13,19,.88);backdrop-filter:blur(12px);border-bottom:1px solid rgba(236,230,216,.16);font:400 13px/20px \"Noto Sans TC\",\"PingFang TC\",\"Microsoft JhengHei\",system-ui,sans-serif;box-sizing:border-box}\n.sitenav a{color:rgba(236,230,216,.66);text-decoration:none;border-bottom:2px solid transparent;padding:2px 0;white-space:nowrap}\n.sitenav a:hover{color:#ece6d8}\n.sitenav .sitenav-brand{font:700 12px/20px \"JetBrains Mono\",Consolas,monospace;letter-spacing:.14em;color:#ece6d8;margin-right:6px;width:144px;flex:none}\n.sitenav a[aria-current=page]{color:#ece6d8;border-bottom-color:#d4f250;font-weight:700}\n:root[data-theme=light] .sitenav{background:rgba(250,247,240,.92);border-bottom-color:rgba(18,22,29,.18)}\n:root[data-theme=light] .sitenav a{color:rgba(18,22,29,.72)}\n:root[data-theme=light] .sitenav .sitenav-brand,:root[data-theme=light] .sitenav a:hover,:root[data-theme=light] .sitenav a[aria-current=page]{color:#12161d}\n:root[data-theme=light] .sitenav a[aria-current=page]{border-bottom-color:#5d7400}\n@view-transition{navigation:auto}\n.sitenav{view-transition-name:sitenav}\n::view-transition-old(root),::view-transition-new(root){animation-duration:180ms;animation-timing-function:ease}\n@media(prefers-reduced-motion:reduce){@view-transition{navigation:none}::view-transition-group(*),::view-transition-old(*),::view-transition-new(*){animation:none!important}}\nhtml,body{background:#06080c;color:#ece6d8;color-scheme:dark}\n:root[data-theme=light],:root[data-theme=light] body{background:#f2ede2;color:#12161d;color-scheme:light}\n.sitenav~.topbar{top:48px}"


def sitenav(prefix, current):
    """Same labels and order on every public page; prefix is the relative path to the site root."""
    links = [("首頁", prefix), ("研究計畫", prefix + "meeting/"), ("研究故事", prefix + "rq1/"), ("案例回放", prefix + "demo/"),
             ("研究台預覽", prefix + "app/"), ("研究報告", prefix + "sources/application-meeting-20261020_v11.pdf"),
             ("GitHub", REPO_URL)]
    items = "".join(
        f'<a href="{href}"' + (' aria-current="page"' if label == current else "") + f">{label}</a>"
        for label, href in links)
    return (f'<nav class="sitenav" aria-label="網站導覽">'
            f'<a class="sitenav-brand" href="{prefix}">STANCE SHIFT LAB</a>{items}</nav>')


def record(port, data_dir, out, model_delay=0.0):
    os.environ["RESEARCH_DEMO_MODE"] = "true"
    os.environ["RESEARCH_DATA_DIR"] = str(data_dir)
    import sys
    import time

    import uvicorn
    from starlette.responses import Response

    sys.path.insert(0, str(ROOT))
    from research_service import demo

    if model_delay > 0:
        original_model = demo.demo_model

        def slow_demo_model(*args, **kwargs):
            time.sleep(model_delay)
            return original_model(*args, **kwargs)

        # create_app() imports demo_model from this module at call time, so patch it first.
        demo.demo_model = slow_demo_model

    from research_service.app import create_app

    app = create_app()
    responses, timeline = {}, []
    started = time.monotonic()
    out = Path(out)

    @app.middleware("http")
    async def recorder(request, call_next):
        response = await call_next(request)
        path = request.url.path
        if not (path.startswith("/api/") and 200 <= response.status_code < 300
                and "json" in response.headers.get("content-type", "")):
            return response
        body = b"".join([chunk async for chunk in response.body_iterator])
        try:
            parsed = json.loads(body)
            key = path + ("?" + request.url.query if request.url.query else "")
            if request.method == "GET":
                responses[key] = parsed
            timeline.append({"t": round(time.monotonic() - started, 2), "method": request.method,
                             "key": key, "response": parsed})
            tmp = out.with_name(out.name + ".tmp")
            tmp.write_text(json.dumps({"responses": responses, "timeline": timeline}, ensure_ascii=False),
                           encoding="utf-8")
            os.replace(tmp, out)
        except ValueError:
            pass
        headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
        return Response(body, status_code=response.status_code, headers=headers)

    uvicorn.run(app, host="127.0.0.1", port=port)


def export_static(dest):
    """Copy the current frontend working tree into dest."""
    shutil.copytree(ROOT / "research_service" / "static", dest, dirs_exist_ok=True)


def rewrite_index(html):
    """Make the server-rooted index.html work from a sub-path and add the demo script and banner."""
    html = re.sub(r'<a\b[^>]*href="/taiwan"[^>]*>.*?</a>\s*', "", html, flags=re.S)
    html = html.replace('"/assets/js/', '"js/').replace('"/assets/', '"')
    html = html.replace('href="/"', 'href="./"')
    # Pages has no API server; do not leave a download pointing at a 404.
    html = re.sub(r'<a\b[^>]*href="/api/template"[^>]*>.*?</a>',
                  '<span>格式範本下載請使用完整研究台。</span>', html, flags=re.S)
    html = re.sub(r'(<script\b[^>]*type="module")', '<script src="demo-data.js" defer></script>\n\\1', html, count=1)
    # Set the saved theme before stylesheets can paint the default theme.
    head_init = "<script>try{if(localStorage.getItem('ssl-theme')==='light')document.documentElement.dataset.theme='light';}catch(e){}</script>\n<link rel=\"manifest\" href=\"../manifest.webmanifest\">\n<meta name=\"theme-color\" content=\"#06080c\">\n<link rel=\"icon\" type=\"image/png\" sizes=\"192x192\" href=\"../assets/app/icon-192.png\">\n<link rel=\"preload\" href=\"../assets/fonts/noto-sans-tc-400-0.woff2\" as=\"font\" type=\"font/woff2\" crossorigin>\n<link rel=\"stylesheet\" href=\"../assets/fonts/fonts.css\">"
    html = re.sub(r"(?=<(?:link|style)\b)", lambda _: head_init + "\n" + f"<style>{SITENAV_STYLE}</style>\n", html, count=1)
    banner = (
        f'<div id="static-demo-banner" style="{BANNER_STYLE}">{BANNER_TEXT} '
        f'<a href="{REPO_URL}/blob/main/docs/cloud-start.md" style="color:inherit;font-weight:600">建立雲端研究台</a> · '
        '<a href="../demo/" style="color:inherit;font-weight:600">播放真實案例</a></div>'
    )
    html = re.sub(r"(<body\b[^>]*>)", lambda m: m.group(1) + "\n" + sitenav("../", "研究台預覽") + "\n" + banner, html, count=1)
    # Register the site's service worker so this page also opens offline.
    html = html.replace("</body>", "<script>if('serviceWorker' in navigator)addEventListener('load',function(){"
                        "navigator.serviceWorker.register('../sw.js',{scope:'../'}).catch(function(){});});</script>\n</body>", 1)
    return html


def build(responses, out):
    out = Path(out)
    data = json.loads(Path(responses).read_text(encoding="utf-8"))
    if not isinstance(data.get("responses"), dict):  # legacy file: a plain dict of responses
        data = {"responses": data, "timeline": []}
    data.setdefault("timeline", [])
    if out.exists():
        shutil.rmtree(out)
    export_static(out)
    for name in ("taiwan.html", "taiwan.css", "js/taiwan.js"):
        (out / name).unlink(missing_ok=True)
    payload = json.dumps({"responses": data["responses"], "timeline": data["timeline"]}, ensure_ascii=False).replace("</", "<\\/")
    (out / "demo-data.js").write_text(f"globalThis.STATIC_DEMO = {payload};\n", encoding="utf-8")
    index = out / "index.html"
    index.write_text(rewrite_index(index.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"built {out} with {len(data["responses"])} recorded responses and {len(data["timeline"])} timeline entries")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    rec = sub.add_parser("record")
    rec.add_argument("--port", type=int, default=8015)
    rec.add_argument("--data-dir", required=True)
    rec.add_argument("--out", required=True)
    rec.add_argument("--model-delay", type=float, default=0.0, help="seconds each demo model call sleeps")
    bld = sub.add_parser("build")
    bld.add_argument("--responses", required=True)
    bld.add_argument("--out", default="site/app")
    args = parser.parse_args()
    if args.command == "record":
        record(args.port, args.data_dir, args.out, args.model_delay)
    else:
        build(args.responses, args.out)


if __name__ == "__main__":
    main()
