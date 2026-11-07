"""Verify existing replay input bytes in Git without unpacking economic rows.

This checks preservation/availability, not dividend completeness, PIT status or
an execution outcome. Only the immutable input manifest and content-addressed
input objects are permitted; no signals/outcomes file can be selected.
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
from pathlib import Path
import subprocess

from pipeline import replay_inputs

from .source_audit import canonical_digest, digest, SourceError

LEDGER_COMMIT = "4b6f8b7137521a148d9cd2c9e3c2fdfdcb5ae71a"
MANIFEST_ID = "f0781292f508a123c234ded6d28aa8e84a0dc3cc29500e14989dc0b68f53b4d2"
MANIFEST_BYTES_SHA256 = "d60ff99710baaf1417cb23d0b007e2d11766e7d76eb03c0d877e0d2495a929cd"


def verify_input_object(compressed: bytes, expected: str) -> None:
    """Bound decompression and hash bytes; never parse a price/outcome row."""
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as source:
            raw = source.read(32 * 1024 * 1024 + 1)
    except (OSError, EOFError) as exc:
        raise SourceError("FROZEN_INPUT_INVALID_GZIP") from exc
    if len(raw) > 32 * 1024 * 1024:
        raise SourceError("FROZEN_INPUT_EXPANSION_LIMIT")
    if digest(raw) != expected:
        raise SourceError("FROZEN_INPUT_OBJECT_DIGEST_MISMATCH")


def audit(repo: Path) -> dict:
    command = ["git", "--no-replace-objects", "-c", "remote.origin.promisor=false", "cat-file"]
    manifest_path = f"ledger/historical/replay-v16/input-manifests/{MANIFEST_ID}.json"
    raw = subprocess.run(command + ["blob", f"{LEDGER_COMMIT}:{manifest_path}"],
                         cwd=repo, check=True, capture_output=True, timeout=30).stdout
    if digest(raw) != MANIFEST_BYTES_SHA256:
        raise SourceError("FROZEN_MANIFEST_BYTES_CHANGED")
    manifest = json.loads(raw)
    if replay_inputs.digest({k: v for k, v in manifest.items() if k != "sha256"}) != MANIFEST_ID:
        raise SourceError("FROZEN_MANIFEST_CONTENT_HASH_MISMATCH")
    for name, refs in manifest["components"].items():
        if replay_inputs.digest(refs) != manifest["componentHashes"][name]:
            raise SourceError("FROZEN_COMPONENT_REFERENCE_HASH_MISMATCH")
    refs = sorted({ref for items in manifest["components"].values() for ref in items})
    if any(len(ref) != 64 or any(c not in "0123456789abcdef" for c in ref) for ref in refs):
        raise SourceError("INVALID_FROZEN_OBJECT_REFERENCE")
    names = [f"{LEDGER_COMMIT}:ledger/replay-inputs/objects/{ref}.json.gz" for ref in refs]
    info = subprocess.run(command + ["--batch-check"], input=("\n".join(names) + "\n").encode(),
                          cwd=repo, capture_output=True, check=True, timeout=60).stdout.splitlines()
    if len(info) != len(refs):
        raise SourceError("GIT_OBJECT_CHECK_TRUNCATED")
    missing = [ref for ref, line in zip(refs, info) if line.endswith(b" missing")]
    if missing:
        return {"status": "SOURCE_OBJECTS_UNAVAILABLE", "missing": missing,
                "requestedObjects": len(refs), "outcomeExecutionAuthorized": False}
    sizes = [int(line.split()[2]) for line in info]
    if max(sizes) > 8 * 1024 * 1024 or sum(sizes) > 128 * 1024 * 1024:
        raise SourceError("EXPLICIT_INPUT_AUDIT_BYTE_BUDGET_EXCEEDED")
    receipts = []
    with subprocess.Popen(command + ["--batch"], cwd=repo, stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
        try:
            for ref, name in zip(refs, names):
                process.stdin.write((name + "\n").encode())
                process.stdin.flush()
                blob, kind, size = process.stdout.readline().split()
                if kind != b"blob":
                    raise SourceError("FROZEN_INPUT_NOT_A_GIT_BLOB")
                compressed = process.stdout.read(int(size))
                if len(compressed) != int(size) or process.stdout.read(1) != b"\n":
                    raise SourceError("GIT_OBJECT_STREAM_TRUNCATED")
                # Deliberately do not parse any price, financial or outcome row.
                verify_input_object(compressed, ref)
                receipts.append({"contentSha256": ref, "gitBlob": blob.decode(),
                                 "compressedSha256": digest(compressed), "bytes": len(compressed)})
            process.stdin.close()
            if process.wait(timeout=30) != 0:
                raise SourceError("GIT_OBJECT_STREAM_FAILED")
        except BaseException:
            process.kill()
            raise
    return {"status": "EXISTING_INPUT_BYTES_VERIFIED", "ledgerCommit": LEDGER_COMMIT,
            "manifestId": MANIFEST_ID, "manifestBytesSha256": digest(raw),
            "componentReferenceListsVerified": len(manifest["components"]),
            "uniqueObjectsVerified": len(receipts), "compressedBytes": sum(sizes),
            "objectReceiptsSha256": canonical_digest(receipts),
            "economicRowsParsed": 0, "historicalOutcomesComputed": 0,
            "dividendCompletenessCertified": False, "historicalVintageCertified": False,
            "outcomeExecutionAuthorized": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.repo)
    with args.out.open("x") as output:
        output.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
