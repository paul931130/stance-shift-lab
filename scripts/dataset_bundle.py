"""Move datasets between research databases while keeping their content-hash IDs.

A dataset ID is ``digest`` of its whole stored content, so re-uploading through
``POST /api/datasets/import`` (which drops ``_collection``) would change the ID
and break the link from jobs and preregistrations.  This tool instead copies the
stored content verbatim and writes it through ``Store.add_dataset``.

  export  read datasets of one ticker from a running service into a bundle file
  import  write a bundle into a research data directory (idempotent)

Both steps refuse any dataset whose content does not hash back to its ID.

The image does not ship this script, so to import into a container copy in both
files first::

  docker cp scripts/dataset_bundle.py <name>:/tmp/ && docker cp bundle.json <name>:/tmp/
  docker exec -e PYTHONPATH=/app <name> python /tmp/dataset_bundle.py import /tmp/bundle.json --data-dir /data
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path


def _digest(content):
    from research_service.data import digest
    return digest(content)


def _get(url):
    with urllib.request.urlopen(url, timeout=120) as response:
        return json.load(response)


def export_bundle(base_url, ticker):
    base = base_url.rstrip("/")
    rows = [row for row in _get(base + "/api/datasets") if row.get("ticker") == ticker]
    items = []
    for row in rows:
        content = _get(f"{base}/api/datasets/{row['id']}")
        if _digest(content) != row["id"]:
            raise ValueError(f"dataset {row['id'][:12]} does not hash back to its ID; refusing to export")
        items.append({"id": row["id"], "created_at": row.get("created_at"), "content": content})
    items.sort(key=lambda item: item["created_at"] or "")
    return {"ticker": ticker, "source": base, "count": len(items), "datasets": items}


def import_bundle(bundle, data_dir):
    from research_service.storage import Store
    store = Store(data_dir)
    existing = {row["id"] for row in store.datasets()}
    added, skipped = 0, 0
    for item in bundle["datasets"]:
        if _digest(item["content"]) != item["id"]:
            raise ValueError(f"dataset {item['id'][:12]} does not hash back to its ID; refusing to import")
    for item in bundle["datasets"]:
        if item["id"] in existing:
            skipped += 1
            continue
        if store.add_dataset(item["content"]) != item["id"]:
            raise RuntimeError(f"stored ID differs from bundle ID for {item['id'][:12]}")
        added += 1
    return {"added": added, "already_present": skipped, "total": len(bundle["datasets"])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export")
    export.add_argument("ticker")
    export.add_argument("output")
    export.add_argument("--base-url", default="http://127.0.0.1:8000")
    load = commands.add_parser("import")
    load.add_argument("bundle")
    load.add_argument("--data-dir", default=os.getenv("RESEARCH_DATA_DIR", "research-data"))
    args = parser.parse_args(argv)
    if args.command == "export":
        bundle = export_bundle(args.base_url, args.ticker.upper())
        Path(args.output).write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
        print(f"exported {bundle['count']} {bundle['ticker']} datasets to {args.output}")
        return 0
    result = import_bundle(json.loads(Path(args.bundle).read_text(encoding="utf-8")), args.data_dir)
    print(f"imported: {result['added']} new, {result['already_present']} already present, {result['total']} in bundle")
    return 0


if __name__ == "__main__":
    sys.exit(main())
