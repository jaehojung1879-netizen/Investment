"""Re-verify every SHA-256 file pin the PR #343-#369 stacks commit, against the bytes in this checkout.

    python research/research_integration_audit_20261124/check_pins.py [--json]

Reads only committed files. It runs no study, reads no price, outcome or private input, and writes nothing.

A pin is any (path, 64-hex digest) pair in one of the JSON files listed in evidence/pin-audit.json ("sources"):
a ``{"path": ..., "sha256": ...}`` object, or a key that looks like a file path whose value is a digest. A path is
resolved against the repository root, then against each parent directory of the JSON file that names it, and
``/workspace/Investment/`` is read as the repository root. A path found nowhere in git (a private scratch file, a
receipt kept outside the repository) is counted as unresolved and is never treated as a pass or a failure.

The run fails when a mismatch appears that evidence/pin-audit.json does not classify, or when a classified
mismatch disappears (its explanation would then be stale).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
AUDIT = HERE / "evidence" / "pin-audit.json"
HEX = re.compile(r"^[0-9a-f]{64}$")
DIGEST_KEYS = ("sha256", "sha", "digest", "hash", "fileSha256", "contentSha256")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pins(node, out: list) -> None:
    if isinstance(node, dict):
        if isinstance(node.get("path"), str):
            for key in DIGEST_KEYS:
                value = node.get(key)
                if isinstance(value, str) and HEX.match(value):
                    out.append((node["path"], value))
        for key, value in node.items():
            if isinstance(value, str) and HEX.match(value) and ("/" in key or "." in key):
                out.append((key, value))
            else:
                _pins(value, out)
    elif isinstance(node, list):
        for value in node:
            _pins(value, out)


def _resolve(source: str, path: str) -> Path | None:
    path = path.replace("/workspace/Investment/", "")
    parts = source.split("/")
    for prefix in [""] + ["/".join(parts[:k]) for k in range(len(parts) - 1, 0, -1)]:
        candidate = ROOT / prefix / path if prefix else ROOT / path
        if candidate.is_file():
            return candidate
    return None


def scan(sources: list[str]) -> dict:
    verified, unresolved, mismatches = 0, 0, []
    for source in sources:
        data = json.loads((ROOT / source).read_text())
        found: list = []
        _pins(data, found)
        for path, digest in found:
            target = _resolve(source, path)
            if target is None:
                unresolved += 1
            elif _sha(target) == digest:
                verified += 1
            else:
                mismatches.append({"source": source, "path": str(target.relative_to(ROOT)), "pinned": digest,
                                   "actual": _sha(target)})
    return {"verified": verified, "unresolved": unresolved, "mismatches": mismatches}


def check() -> dict:
    audit = json.loads(AUDIT.read_text())
    result = scan(audit["sources"])
    known = {(m["source"], m["path"], m["pinned"], m["actual"]) for m in audit["classifiedMismatches"]}
    seen = {(m["source"], m["path"], m["pinned"], m["actual"]) for m in result["mismatches"]}
    result["unclassified"] = sorted(seen - known)
    result["stale"] = sorted(known - seen)
    result["ok"] = not result["unclassified"] and not result["stale"]
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    result = check()
    if args.json:
        print(json.dumps(result, indent=1))
    else:
        print(f"verified {result['verified']} unresolved {result['unresolved']} mismatches {len(result['mismatches'])}"
              f" unclassified {len(result['unclassified'])} stale {len(result['stale'])}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
