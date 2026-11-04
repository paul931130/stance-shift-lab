"""Move the private, git-ignored inputs that the next experiments need to another computer.

git clone brings the code, docs and analysis plan. It does not bring the RQ1 source
snapshot (work/ is ignored, and the data must stay private). This tool copies exactly
those files into a folder you carry over (USB drive, shared drive, scp), with SHA-256
sums, and verifies and restores them on the other computer.

    # on this computer
    python scripts/lab_bundle.py pack --out D:/lab-bundle
    # on the lab computer, inside the cloned repo
    python scripts/lab_bundle.py restore --bundle D:/lab-bundle

No credentials are packed. Recreate .env.research on the lab computer by hand.
Standard library only, so it runs before the venv exists.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Repo-relative paths. Required files block the next steps when missing.
REQUIRED = [
    # Source for prepare_experiment_launch.py / run_design_pilot.py (runbook 2026-10-17)
    "work/preformal-20261017/rq1-source-backup.sqlite3",
    # Read-only copy for memory_probe.py (it refuses the original snapshot)
    "work/final-review-20261015/probe-snapshot/research.sqlite3",
]
OPTIONAL = [
    # Reference records of the last offline packaging; useful for comparing hashes
    "work/preformal-20261017/release-manifest.json",
    "work/preformal-20261017/environment-final.json",
]
MANIFEST = "lab-bundle-manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def pack(out: Path) -> int:
    missing = [p for p in REQUIRED if not (ROOT / p).is_file()]
    if missing:
        print("Missing required files:\n  " + "\n  ".join(missing), file=sys.stderr)
        return 1
    for rel in REQUIRED:
        if (ROOT / (rel + "-wal")).exists():
            print(f"{rel} has a -wal file; close the writer and back it up first.", file=sys.stderr)
            return 1
    out.mkdir(parents=True, exist_ok=True)
    files = []
    for rel in REQUIRED + OPTIONAL:
        src = ROOT / rel
        if not src.is_file():
            print(f"skip (optional, not found): {rel}")
            continue
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        print(f"copy {rel} ({src.stat().st_size / 1e6:.0f} MB)")
        shutil.copy2(src, dst)
        files.append({"path": rel, "bytes": src.stat().st_size, "sha256": sha256(src),
                      "required": rel in REQUIRED})
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": git("rev-parse", "HEAD"),
        "git_branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "git_dirty": bool(git("status", "--porcelain")),
        "files": files,
    }
    (out / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nWrote {out / MANIFEST}")
    if manifest["git_dirty"]:
        print("Warning: working tree has uncommitted changes; commit and push before the lab clones.")
    return 0


def restore(bundle: Path, check_only: bool) -> int:
    manifest = json.loads((bundle / MANIFEST).read_text(encoding="utf-8"))
    head = git("rev-parse", "HEAD")
    if manifest["git_commit"] and head and head != manifest["git_commit"]:
        print(f"Note: bundle made at {manifest['git_commit'][:12]}, this checkout is {head[:12]}.")
    bad = 0
    for item in manifest["files"]:
        src = bundle / item["path"]
        if not src.is_file() or sha256(src) != item["sha256"]:
            print(f"FAIL {item['path']} (missing or hash differs)")
            bad += 1
            continue
        dst = ROOT / item["path"]
        if not check_only:
            if dst.exists() and sha256(dst) == item["sha256"]:
                print(f"ok   {item['path']} (already in place)")
                continue
            if dst.exists():
                print(f"FAIL {item['path']}: a different file is already there; move it away first.")
                bad += 1
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        print(f"ok   {item['path']}")
    print("All files verified." if not bad else f"{bad} file(s) failed.")
    return 1 if bad else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("pack", help="copy private inputs into a bundle folder")
    p.add_argument("--out", required=True, type=Path)
    r = sub.add_parser("restore", help="verify a bundle and copy it into this checkout")
    r.add_argument("--bundle", required=True, type=Path)
    r.add_argument("--check-only", action="store_true", help="verify hashes without copying")
    args = parser.parse_args()
    if args.command == "pack":
        return pack(args.out)
    return restore(args.bundle, args.check_only)


if __name__ == "__main__":
    raise SystemExit(main())
