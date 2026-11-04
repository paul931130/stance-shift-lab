"""Check a remote (lab) Ollama endpoint before any RQ2/RQ3 run.

Run on this computer after opening the SSH tunnel to the lab machine:

    ssh -N -L 11435:127.0.0.1:11434 <account>@<lab host>
    python scripts/check_lab_ollama.py --base http://127.0.0.1:11435
    python scripts/check_lab_ollama.py --base http://127.0.0.1:11435 --generate --output work/lab-ollama-check.json

It reads /api/version, /api/tags and /api/ps, reports each model's full weight
digest, and compares qwen3:32b with the RQ1 weights. --generate sends one tiny
request per model (loads it on the lab GPU; no paid service). Nothing else is
called, no job or registration is created, and no credential is sent or stored.
Standard library only.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

MODEL_A = "qwen3:32b"
MODEL_B = "gemma3:27b"
# Weights used for RQ1 (protocol b1da80ee…, 180 cases). A different digest is a different model.
RQ1_QWEN_DIGEST = "030ee887880fc378860c2dd35101da424377520441ae4bfe7be6deff8ade7840"


def call(base, path, body=None, timeout=30):
    data = None if body is None else json.dumps(body).encode()
    request = Request(base + path, data=data, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default="http://127.0.0.1:11435", help="Ollama URL as seen from this computer")
    parser.add_argument("--generate", action="store_true", help="send one tiny request per model")
    parser.add_argument("--timeout", type=int, default=900, help="seconds for each --generate request (cold load)")
    parser.add_argument("--output", type=Path, help="write the result as JSON (new file only)")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    result = {"checked_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "base": base,
              "models": {}, "problems": []}
    try:
        result["ollama_version"] = call(base, "/api/version").get("version")
        tags = call(base, "/api/tags").get("models", [])
    except (URLError, OSError, ValueError) as error:
        print(f"Cannot reach {base}: {error}\nIs the SSH tunnel open, and is Ollama running on the lab machine?")
        return 2
    by_name = {item.get("name"): item for item in tags}
    for name in (MODEL_A, MODEL_B):
        item = by_name.get(name) or by_name.get(name + ":latest")
        if not item:
            result["problems"].append(f"{name} is not pulled on the lab machine (ollama pull {name})")
            continue
        details = item.get("details", {})
        result["models"][name] = {"digest": item.get("digest"), "size": item.get("size"),
                                  "quantization": details.get("quantization_level"),
                                  "parameter_size": details.get("parameter_size"),
                                  "modified_at": item.get("modified_at")}
    qwen = result["models"].get(MODEL_A)
    if qwen:
        qwen["same_weights_as_rq1"] = qwen["digest"] == RQ1_QWEN_DIGEST
        if not qwen["same_weights_as_rq1"]:
            result["problems"].append(
                "qwen3:32b digest differs from RQ1 (030ee887…). RQ2/RQ3 rerun their own AA/C baselines, "
                "so this is allowed, but RQ1 numbers cannot be reused as a baseline; record it in the registration.")
    if args.generate:
        for name in result["models"]:
            started = time.monotonic()
            body = {"model": name, "stream": False,
                    "messages": [{"role": "user", "content": "Reply with the word OK."}],
                    "options": {"num_ctx": 8192, "temperature": 0, "seed": 905}}
            if name == MODEL_A:
                body["think"] = False  # same as the research calls
            try:
                reply = call(base, "/api/chat", body, timeout=args.timeout)
                result["models"][name]["generate"] = {"ok": bool(reply.get("message", {}).get("content")),
                                                      "seconds": round(time.monotonic() - started, 1),
                                                      "eval_count": reply.get("eval_count")}
            except (URLError, OSError, ValueError) as error:
                result["models"][name]["generate"] = {"ok": False, "error": str(error)[:200]}
                result["problems"].append(f"{name} did not answer a tiny request: {error}")
        try:
            result["loaded"] = [{"name": m.get("name"), "size_vram": m.get("size_vram")}
                                for m in call(base, "/api/ps").get("models", [])]
            if len(result["loaded"]) < len(result["models"]):
                result["problems"].append("Not all models stay loaded together; set OLLAMA_MAX_LOADED_MODELS=2 "
                                          "on the lab machine, or every A/B switch reloads ~20 GB")
        except (URLError, OSError, ValueError):
            pass
    text = json.dumps(result, indent=2, ensure_ascii=False)
    print(text)
    if args.output:
        if args.output.exists():
            print(f"{args.output} exists; choose a new name", file=sys.stderr)
            return 1
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print("\nOK" if not result["problems"] else f"\n{len(result['problems'])} problem(s) listed above.")
    return 0 if not result["problems"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
