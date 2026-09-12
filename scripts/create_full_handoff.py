from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path


CHUNK_SIZE = 8 * 1024 * 1024
PROGRESS_BYTES = 512 * 1024 * 1024
EXCLUDED_RELATIVE_PATHS = {".env.research"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def collect_paths(root: Path, output: Path) -> tuple[list[Path], list[Path]]:
    files: list[Path] = []
    directories: list[Path] = []
    output_candidates = {output.resolve(strict=False), output.with_suffix(output.suffix + ".partial").resolve(strict=False)}
    for current, dir_names, file_names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        dir_names.sort(key=str.casefold)
        file_names.sort(key=str.casefold)
        for name in dir_names:
            directories.append(current_path / name)
        for name in file_names:
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if relative in EXCLUDED_RELATIVE_PATHS:
                continue
            if path.resolve(strict=False) in output_candidates:
                continue
            files.append(path)
    return files, directories


def add_file(
    archive: zipfile.ZipFile,
    root: Path,
    path: Path,
    prefix: str,
) -> dict[str, object]:
    relative = path.relative_to(root).as_posix()
    archive_name = f"{prefix}/{relative}"
    before = path.stat()
    info = zipfile.ZipInfo.from_file(path, archive_name)
    info.compress_type = zipfile.ZIP_DEFLATED
    digest = hashlib.sha256()
    copied = 0
    with path.open("rb") as source, archive.open(info, "w", force_zip64=True) as destination:
        while chunk := source.read(CHUNK_SIZE):
            destination.write(chunk)
            digest.update(chunk)
            copied += len(chunk)
    after = path.stat()
    if copied != before.st_size or after.st_size != before.st_size or after.st_mtime_ns != before.st_mtime_ns:
        raise RuntimeError(f"File changed while packaging: {relative}")
    return {
        "path": relative,
        "bytes": copied,
        "sha256": digest.hexdigest(),
        "modified_ns": before.st_mtime_ns,
    }


def build(root: Path, output: Path, compress_level: int) -> dict[str, object]:
    root = root.resolve(strict=True)
    output = output.resolve(strict=False)
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_suffix(output.suffix + ".partial")
    if partial.exists():
        partial.unlink()

    files, directories = collect_paths(root, output)
    total_bytes = sum(path.stat().st_size for path in files)
    prefix = root.name
    manifest_files: list[dict[str, object]] = []
    processed = 0
    next_progress = PROGRESS_BYTES
    started = time.monotonic()

    print(
        json.dumps(
            {
                "status": "starting",
                "root": str(root),
                "output": str(output),
                "files": len(files),
                "source_bytes": total_bytes,
                "excluded": sorted(EXCLUDED_RELATIVE_PATHS),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    try:
        with zipfile.ZipFile(
            partial,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=compress_level,
            allowZip64=True,
        ) as archive:
            for directory in directories:
                if any(parent.is_symlink() for parent in [directory, *directory.parents] if parent != root.parent):
                    continue
                relative = directory.relative_to(root).as_posix().rstrip("/")
                if relative:
                    info = zipfile.ZipInfo.from_file(directory, f"{prefix}/{relative}/")
                    archive.writestr(info, b"")

            for index, path in enumerate(files, start=1):
                item = add_file(archive, root, path, prefix)
                manifest_files.append(item)
                processed += int(item["bytes"])
                if processed >= next_progress or index == len(files):
                    elapsed = max(time.monotonic() - started, 0.001)
                    print(
                        json.dumps(
                            {
                                "status": "progress",
                                "files_done": index,
                                "files_total": len(files),
                                "bytes_done": processed,
                                "bytes_total": total_bytes,
                                "percent": round(processed * 100 / total_bytes, 2) if total_bytes else 100.0,
                                "mib_per_second": round(processed / 1024 / 1024 / elapsed, 2),
                                "current": item["path"],
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
                    while next_progress <= processed:
                        next_progress += PROGRESS_BYTES

            readme = (
                "This is the private full-folder handoff archive for Stance Shift Research v3-0912.1.\n"
                "It includes project data, filtered and raw news files, Git metadata, dependencies, caches,\n"
                "release artifacts, and the latest restorable database backup present in deliverables/.\n\n"
                "The active .env.research file is intentionally excluded because it contains live API keys.\n"
                "Run .\\research.ps1 setup on the receiving machine to enter replacement credentials.\n"
                "Do not publish this archive: included datasets and research outputs may have redistribution limits.\n"
            )
            archive.writestr(f"{prefix}/FULL_HANDOFF_README.txt", readme.encode("utf-8"))
            manifest = {
                "schema": "stance-shift-full-handoff/v1",
                "version": "v3-0912.1",
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "root_name": prefix,
                "source_bytes": total_bytes,
                "file_count": len(manifest_files),
                "excluded": [
                    {
                        "path": ".env.research",
                        "reason": "contains active API credentials; replace through research.ps1 setup",
                    }
                ],
                "database_note": (
                    "Docker volume data is represented by deliverables/"
                    "stance-shift-backtest-v3-0912.1-private-data-backup.zip."
                ),
                "files": manifest_files,
            }
            archive.writestr(
                f"{prefix}/FULL_HANDOFF_MANIFEST.json",
                json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
            )
        partial.replace(output)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise

    result = {
        "status": "complete",
        "archive": str(output),
        "bytes": output.stat().st_size,
        "sha256": sha256_file(output),
        "source_bytes": total_bytes,
        "files": len(manifest_files),
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a private full-folder Stance Shift handoff ZIP.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compress-level", type=int, default=1, choices=range(0, 10))
    args = parser.parse_args()
    build(args.root, args.output, args.compress_level)
    return 0


if __name__ == "__main__":
    sys.exit(main())
