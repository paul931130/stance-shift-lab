"""Build the installable-app files for the public site (site/).

Writes three things:

* site/assets/app/icon-192.png, icon-512.png, icon-maskable-512.png
  (drawn here in pure Python, no image library needed)
* site/manifest.webmanifest
* site/sw.js, a service worker that stores every page and asset of the site
  in the browser on first visit, so pages open instantly and also offline.

The service worker's cache name contains a hash of all cached files, so any
change to the site produces a new worker that replaces the old cache. Re-run
after changing anything under site/:

    python scripts/build_site_app.py           # write the files
    python scripts/build_site_app.py --check   # exit 1 if sw.js is stale
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import struct
import subprocess
import sys
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
APP = SITE / "assets" / "app"
NAME = "多代理人辯論機制應用於投資決策"
SHORT = "Stance Shift"
BG = (6, 8, 12)
BULL = (255, 107, 61)
BEAR = (63, 200, 255)
# The report PDF is cached when first opened, not on install; everything else
# (including the 5.7 MB demo recording the workspace preview needs) is cached
# up front so every page also opens offline.
LAZY = {"sources/application-meeting-20261020_v11.pdf"}
SKIP_PREFIX = ("story/",)          # unrelated local checkout, never published
SKIP_SUFFIX = (".tex",)


# ───────── icons ─────────
def _png(size: int, pixels: bytearray) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    rows = b"".join(b"\x00" + bytes(pixels[y * size * 3:(y + 1) * size * 3]) for y in range(size))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def draw_icon(size: int, art: float) -> bytes:
    """Two streams (bull, bear) that cross in the middle: the deck's flow field.

    `art` is the share of the canvas the artwork uses (smaller for maskable)."""
    px = bytearray(BG * size * size)
    half = art / 2
    width = 0.085 * art            # stroke width relative to the canvas
    ss = 3                         # supersampling per axis
    for y in range(size):
        for x in range(size):
            acc = [0.0, 0.0, 0.0]
            for sy in range(ss):
                for sx in range(ss):
                    u = (x + (sx + .5) / ss) / size
                    v = (y + (sy + .5) / ss) / size
                    col = BG
                    if .5 - half <= u <= .5 + half:
                        t = (u - (.5 - half)) / art            # 0..1 across the artwork
                        amp = .17 * art
                        # each stream swaps sides once, like the D arm
                        y_bull = .5 - amp * math.cos(math.pi * t)
                        y_bear = .5 + amp * math.cos(math.pi * t)
                        slope = amp * math.pi * math.sin(math.pi * t) / art
                        norm = math.sqrt(1 + slope * slope)
                        if abs(v - y_bear) / norm < width / 2:
                            col = BEAR
                        if abs(v - y_bull) / norm < width / 2:
                            col = BULL
                    for i in range(3):
                        acc[i] += col[i]
            o = (y * size + x) * 3
            n = ss * ss
            px[o:o + 3] = bytes(int(round(c / n)) for c in acc)
    return _png(size, px)


# ───────── manifest and service worker ─────────
def manifest() -> str:
    return json.dumps({
        "name": NAME,
        "short_name": SHORT,
        "description": "多代理人辯論機制應用於投資決策：研究計畫、RQ1 結果、案例回放與研究台預覽。",
        "lang": "zh-Hant-TW",
        "start_url": "./",
        "scope": "./",
        "id": "/stance-shift-lab/",
        "display": "standalone",
        "display_override": ["window-controls-overlay", "standalone"],
        "background_color": "#06080c",
        "theme_color": "#06080c",
        "icons": [
            {"src": "assets/app/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "assets/app/icon-512.png", "sizes": "512x512", "type": "image/png"},
            {"src": "assets/app/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
        "shortcuts": [
            {"name": "研究計畫", "url": "meeting/"},
            {"name": "研究故事", "url": "rq1/"},
            {"name": "案例回放", "url": "demo/"},
            {"name": "研究台預覽", "url": "app/"},
        ],
    }, ensure_ascii=False, indent=2) + "\n"


def site_files() -> list[str]:
    """Published files: tracked by git (plus new files about to be added) under site/."""
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "site"],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    files = []
    for path in sorted(set(out)):
        rel = path[len("site/"):]
        if rel.startswith(SKIP_PREFIX) or rel.endswith(SKIP_SUFFIX) or rel == "sw.js":
            continue
        if (SITE / rel).is_file():
            files.append(rel)
    return files


def _norm(data: bytes) -> bytes:
    """Text files may be checked out with CRLF on Windows and LF elsewhere;
    hash and compare them with LF so every checkout gets the same result."""
    return data if bytes(1) in data else data.replace(b"\r\n", b"\n")


def service_worker(files: list[str]) -> str:
    digest = hashlib.sha256()
    for rel in files:
        digest.update(rel.encode())
        digest.update(_norm((SITE / rel).read_bytes()))
    version = digest.hexdigest()[:12]
    eager = []
    for rel in files:
        if rel in LAZY:
            continue
        # pages are cached under their directory URL, which is how links point to them
        eager.append("./" if rel == "index.html" else "./" + rel[:-len("index.html")] if rel.endswith("/index.html") else "./" + rel)
    return SW_TEMPLATE.replace("__VERSION__", version).replace("__FILES__", json.dumps(eager, ensure_ascii=False, indent=1))


SW_TEMPLATE = """// Generated by scripts/build_site_app.py; do not edit.
// Caches the whole site on first visit so pages open instantly and offline.
const CACHE = 'ssl-__VERSION__';
const FILES = __FILES__;

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(c => c.addAll(FILES.map(u => new Request(u, { cache: 'reload' })))).then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k.startsWith('ssl-') && k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// Serve from the cache at once and refresh it in the background
// (stale-while-revalidate). A new deploy changes CACHE, so the next visit
// installs a new worker with fresh files.
self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== location.origin || !url.pathname.startsWith(new URL(self.registration.scope).pathname)) return;
  if (url.pathname.endsWith('.pdf')) return;            // let the browser's PDF viewer stream it
  if (req.mode === 'navigate' && url.pathname.endsWith('/index.html')) {
    url.pathname = url.pathname.slice(0, -'index.html'.length);
  }
  const key = req.mode === 'navigate' ? new Request(url.origin + url.pathname) : req;
  event.respondWith(caches.open(CACHE).then(async cache => {
    const hit = await cache.match(key, { ignoreSearch: req.mode === 'navigate' });
    const fresh = fetch(req, { cache: 'no-cache' }).then(async res => {
      if (res.ok && res.type === 'basic') {
        try { await cache.put(key, res.clone()); }
        catch (error) { console.warn('Cache update failed:', error); }
      }
      return res;
    }).catch(() => hit || new Response(
      '<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><title>離線</title><p>目前離線，此頁尚未快取。</p><a href="./">返回首頁</a></html>',
      { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
    ));
    if (hit) { event.waitUntil(fresh); return hit; }
    return fresh;
  }));
});
"""


def build() -> dict[pathlib.Path, bytes]:
    out = {
        SITE / "manifest.webmanifest": manifest().encode("utf-8"),
    }
    icons = {
        APP / "icon-192.png": (192, .62),
        APP / "icon-512.png": (512, .62),
        APP / "icon-maskable-512.png": (512, .5),
    }
    for path, (size, art) in icons.items():
        out[path] = path.read_bytes() if path.exists() else draw_icon(size, art)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="exit 1 if sw.js or the manifest is out of date")
    args = ap.parse_args()
    files = build()
    if not args.check:
        APP.mkdir(parents=True, exist_ok=True)
        for path, data in files.items():
            path.write_bytes(data)
    sw = service_worker(site_files()).encode("utf-8")
    target = SITE / "sw.js"
    if args.check:
        stale = [p for p, d in {**files, target: sw}.items() if not p.exists() or _norm(p.read_bytes()) != _norm(d)]
        for p in stale:
            print(f"{p.relative_to(ROOT)}: out of date; run python scripts/build_site_app.py", file=sys.stderr)
        return 1 if stale else 0
    target.write_bytes(sw)
    print(f"wrote manifest, icons and sw.js ({sw.decode().count(chr(10))} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
