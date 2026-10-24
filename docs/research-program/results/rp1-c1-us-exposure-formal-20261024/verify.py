#!/usr/bin/env python3
"""Read-only verification of the exact one-shot C1 Actions artifact payloads."""
from __future__ import annotations
import base64
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HASHES = {
    "execution-started.json": "0a999b082fcf0cda69bc1bcee35ee423e8b4dd49dda08ae6ac1d475c0aab05df",
    "manifest.json": "2022efbfdd65a54f1c57879ef85f06ddb7845af55853c5e899d8784230b69994",
    "report.md": "ade771b6837ff0d93e282d997c320f0809fc4f05916e178bd19e234619df5f45",
    "result.json": "910215317eedcaf45f293dc056749688f9400cd00f95102b565d265f552e3938",
    "validation.json": "7ca6bd5b53b456f7e5ae874e1f1281c9071a292608013585d3c017fda3257437",
}
AUTHORIZATION = "cf53d08c70216ea02321688a07a53ba9b4f9dfc1cf47a2e3591d49a4890aba48"
SPEC = "4106709c48690a230e6ee07c782a5ea2d3374b3e8780bf31ecbdad97b0a00127"

def require(condition: bool, what: str) -> None:
    """An explicit check: unlike `assert`, it is not removed by `python -O` / PYTHONOPTIMIZE."""
    if not condition:
        raise ValueError("ARCHIVE_INVARIANT_FAILED: " + what)

def decoded(name: str) -> bytes:
    content = (ROOT / "payload" / (name + ".gz.b64")).read_text(encoding="ascii").strip()
    raw = gzip.decompress(base64.b64decode(content, validate=True))
    actual = hashlib.sha256(raw).hexdigest()
    if actual != HASHES[name]:
        raise ValueError(f"{name}: SHA mismatch {actual}")
    return raw

def verify() -> dict:
    raw = {name: decoded(name) for name in HASHES}
    result = json.loads(raw["result.json"])
    manifest = json.loads(raw["manifest.json"])
    marker = json.loads(raw["execution-started.json"])
    validation = json.loads(raw["validation.json"])
    require(manifest["files"] == {k: HASHES[k] for k in HASHES if k not in ("manifest.json",)}, 'manifest per-file hashes')
    require(result["authorizationSha256"] == marker["authorizationSha256"] == manifest["authorizationSha256"] == AUTHORIZATION, 'authorization identity')
    require(result["specSha256"] == marker["specSha256"] == manifest["specSha256"] == SPEC, 'frozen spec identity')
    require(result["lockedMainSha"] == marker["lockedMainSha"] == "591f182955ab85bc527ddedc41c2d77d1fd24eaa", 'locked main commit')
    require(marker["usValueReadsBeforeThisMarker"] == 0, 'no US value read before the marker')
    require(manifest["counters"] == {"evaluations": 2, "lockClaims": 1, "markerWrites": 1, "usValueReads": 2, "validations": 2},
            "execution counters")
    require(validation["checks"] == 160 and validation["mismatchCount"] == 0 and validation["status"] == "CONSISTENT", 'independent validation')
    require(result["interpretation"]["reading"] == "REPLICATED_CONTROL_RETAINED", 'frozen interpretation')
    require(result["interpretation"]["nominated"] is None, 'no nominated candidate')
    require(result["interpretation"]["decisionStatus"] == "NO_CANDIDATE_NOMINATED_CONTROL_RETAINED", 'frozen decision')
    require(result["scientificStatus"] == "FROZEN_RULE_REPLICATION_ON_PUBLICLY_KNOWN_US_HISTORY", 'scientific status')
    return {"status": "VERIFIED_EXACT_ARTIFACT_BYTES", "files": len(raw),
            "independentChecks": validation["checks"],
            "resultDecision": result["interpretation"]["decisionStatus"],
            "interpretation": result["interpretation"]["reading"]}

if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
