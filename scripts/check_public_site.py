"""Check published local links and keep the recorded demo UI in sync.

Run with --sync to refresh UI assets without changing the recorded demo data.
Only tracked files are inspected, so private local drafts cannot satisfy links.
"""
import argparse
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from static_demo import rewrite_index

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DEMO_ASSETS = {"taiwan.html", "taiwan.css", "js/taiwan.js"}


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.targets = []

    def handle_starttag(self, tag, attrs):
        self.targets.extend(value for key, value in attrs if key in ("href", "src") and value)


def tracked_files(root):
    output = subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
    return {name for name in output.decode("utf-8").split("\0") if name}


def broken_links(root, tracked):
    errors = []
    for name in sorted(tracked):
        if not (name.endswith(".md") or name.startswith("site/") and name.endswith(".html")):
            continue
        content = (root / name).read_text(encoding="utf-8")
        if name.endswith(".md"):
            # Ignore fenced examples; inspect ordinary Markdown links and images.
            content = re.sub(r"```.*?```", "", content, flags=re.S)
            targets = re.findall(r"\]\(<?([^\s)>]+)>?(?:\s+\"[^\"]*\")?\)", content)
        else:
            parser = Links()
            parser.feed(content)
            targets = parser.targets
        for target in targets:
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            path = unquote(parsed.path)
            resolved = (root / name).parent / path
            try:
                relative = resolved.resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                errors.append(f"{name}: link escapes repository: {target}")
                continue
            if relative not in tracked and relative.rstrip("/") + "/index.html" not in tracked:
                errors.append(f"{name}: missing tracked target: {target}")
    return errors


def stale_demo(root, tracked, sync=False):
    errors = []
    prefix = "research_service/static/"
    expected = set()
    for name in sorted(tracked):
        if not name.startswith(prefix):
            continue
        relative = name[len(prefix):]
        if relative in EXCLUDED_DEMO_ASSETS:
            continue
        destination = "site/app/" + relative
        expected.add(destination)
        source = (root / name).read_bytes()
        if relative == "index.html":
            source = rewrite_index(source.decode("utf-8").replace("\r\n", "\n")).encode("utf-8")
        actual = (root / destination).read_bytes() if (root / destination).exists() else None
        # Git checkouts may use CRLF on Windows; compare normalized text assets.
        if actual is not None:
            actual = actual.replace(b"\r\n", b"\n")
        if actual != source.replace(b"\r\n", b"\n"):
            if sync:
                (root / destination).parent.mkdir(parents=True, exist_ok=True)
                (root / destination).write_bytes(source)
            else:
                errors.append(f"{destination}: stale demo asset; run python scripts/check_public_site.py --sync")
    for name in sorted(tracked):
        if name.startswith("site/app/") and name not in expected and name != "site/app/demo-data.js":
            # Deliberately require manual review before removing stale published files.
            errors.append(f"{name}: unexpected demo asset; remove it or add its source")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sync", action="store_true")
    args = parser.parse_args()
    tracked = tracked_files(ROOT)
    errors = stale_demo(ROOT, tracked, args.sync) + broken_links(ROOT, tracked)
    for error in errors:
        print(error)
    if errors:
        return 1
    print("Public links and recorded demo UI are up to date (recorded data unchanged).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
