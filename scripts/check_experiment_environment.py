"""Record local Python/dependency compatibility without contacting models."""
import argparse
from importlib import metadata
import json
from pathlib import Path
import platform
import sys
import tomllib

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research_service.launch_package import file_hash
from research_service.run_manifest import source_fingerprint


def inspect_environment(root):
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    dependencies = {}
    for spec in project["dependencies"]:
        name, expected = spec.split("==", 1)
        try:
            installed = metadata.version(name)
        except metadata.PackageNotFoundError:
            installed = None
        dependencies[name] = {"expected": expected, "installed": installed, "match": installed == expected}
    python_ok = sys.version_info >= (3, 12)
    return {"schema": "stance-shift-runtime-check/v1",
            "python": platform.python_version(), "python_compatible": python_ok,
            "platform": platform.platform(), "dependencies": dependencies,
            "environment_compatible": python_ok and all(item["match"] for item in dependencies.values()),
            "pyproject_sha256": file_hash(root / "pyproject.toml"), "source": source_fingerprint(root),
            "formal_launch_ready": False,
            "note": "Local compatibility only. No model, GPU image, pilot, or registration is qualified."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = inspect_environment(Path(__file__).resolve().parents[1])
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({"environment_compatible": result["environment_compatible"], "formal_launch_ready": False}))
    return 0 if result["environment_compatible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
