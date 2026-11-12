"""Read exact local Git bytes and report observation gates, without recording.

python -m research.master_integration_preflight_v1.preflight --source-ref FULL_SHA
Missing partial-clone objects fail explicitly; acquisition is a separate step.
No scores, positions, prices, outcomes, production writes or activation API.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from pipeline import prospective_receipt_core as C
from .adapters import inspect_operational_receipt

SOURCE_PATHS = {
    "champion": "ledger/research-strategies/current-champion-decisions-v1/latest.json",
    "weekly": "ledger/weekly-decisions/latest.json",
    "weeklyReceipts": "ledger/weekly-decisions/receipts.jsonl",
    "productionStore": "ledger/research-strategies/entry-state-shadow-ledger-v1/decisions.jsonl",
}
MAX_BYTES = 8 * 1024 * 1024


def _git(repo, *args):
    run = subprocess.run(["git", "--no-replace-objects", "-c", "remote.origin.promisor=false",
                          "-C", str(repo), *args], capture_output=True, check=False, timeout=30,
                         env={**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0"})
    if run.returncode:
        raise ValueError("LOCAL_SOURCE_OBJECT_UNAVAILABLE")
    return run.stdout


def read_source(repo, commit, path):
    if not C.is_git_sha(commit) or path not in SOURCE_PATHS.values():
        raise ValueError("EXACT_SOURCE_AND_ALLOWLIST_PATH_REQUIRED")
    if _git(repo, "cat-file", "-t", commit).strip() != b"commit":
        raise ValueError("SOURCE_IS_NOT_COMMIT")
    tree = _git(repo, "ls-tree", commit, "--", path).decode().strip()
    if not tree:
        return None, {"path": path, "commit": commit, "status": "ABSENT_IN_COMMIT"}
    meta, listed_path = tree.split("\t")
    mode, kind, blob = meta.split()
    if listed_path != path or mode != "100644" or kind != "blob":
        raise ValueError("ORDINARY_SOURCE_BLOB_REQUIRED")
    size = int(_git(repo, "cat-file", "-s", blob))
    if size > MAX_BYTES:
        raise ValueError("SOURCE_BYTE_BUDGET_EXCEEDED")
    raw = _git(repo, "cat-file", "blob", blob)
    if len(raw) != size:
        raise ValueError("SOURCE_BYTE_COUNT_MISMATCH")
    return raw, {"path": path, "commit": commit, "blob": blob, "bytes": size,
                 "sha256": hashlib.sha256(raw).hexdigest(), "status": "VERIFIED_LOCAL_BYTES"}


def strict_object(raw):
    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise ValueError("DUPLICATE_SOURCE_KEY")
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=pairs)
    C.canonical(value)  # Also refuses NaN, Infinity and exponent overflow.
    if not isinstance(value, dict):
        raise ValueError("SOURCE_OBJECT_REQUIRED")
    return value


def inspect_snapshot(repo, commit):
    """Negative gates only; even a coherent pair is not an admitted decision."""
    sources, bodies, blockers, verified, rejected = {}, {}, [], [], []
    for key, path in SOURCE_PATHS.items():
        try:
            raw, receipt = read_source(repo, commit, path)
            sources[key] = receipt
            if key == "weeklyReceipts":
                if raw is None:
                    blockers.append("MISSING_OPERATIONAL_RECEIPTS")
                else:
                    for index, line in enumerate(raw.splitlines(), start=1):
                        if not line.strip():
                            continue
                        sha = hashlib.sha256(line).hexdigest()
                        try:
                            verified.append(inspect_operational_receipt(line, expected_sha256=sha))
                        except (ValueError, TypeError, KeyError, AttributeError) as exc:
                            rejected.append({"line":index,"sha256":sha,"reason":str(exc)})
                    if rejected:
                        blockers.append("HISTORICAL_OPERATIONAL_RECEIPT_REQUIRES_REVIEW_NOT_REWRITE")
            elif key != "productionStore":
                if raw is None:
                    blockers.append("MISSING_" + key.upper())
                else:
                    bodies[key] = strict_object(raw)
            elif raw is not None:
                # Never count arbitrary stored bytes as a verified live receipt.
                blockers.append("EXISTING_PRODUCTION_STORE_REQUIRES_OPERATIONAL_CODEC_AUDIT")
        except (ValueError, TypeError, KeyError, AttributeError, OSError, subprocess.TimeoutExpired):
            sources[key] = {"path": path, "commit": commit, "status": "SOURCE_UNAVAILABLE_OR_INVALID"}
            blockers.append("INVALID_" + key.upper())
    dates = {k: body.get("generatedAt") for k, body in bodies.items()}
    coherent = False
    if len(dates) == 2:
        try:
            coherent = C.utc(dates["champion"]) == C.utc(dates["weekly"])
            if not coherent:
                blockers.append("DIFFERENT_GENERATION_CANNOT_PAIR")
        except (ValueError, TypeError):
            blockers.append("PUBLICATION_GENERATION_UNVERIFIED")
    blockers += ["OWNER_PRODUCTION_RELEASE_NOT_AUTHORIZED_BY_THIS_PREFLIGHT",
                 "OPERATIONAL_RECEIPT_CODEC_AND_FINAL_SESSION_ADMISSION_REQUIRED",
                 "NO_QUALIFIED_P1_P5_INPUT_REGISTRY",
                 "SOURCE_RIGHTS_PIT_AND_SHAREHOLDER_RETURN_ADMISSION_REQUIRED"]
    absent = sources.get("productionStore", {}).get("status") == "ABSENT_IN_COMMIT"
    return {"schema": "MASTER_RESEARCH_OBSERVATION_PREFLIGHT_V1", "status": "BLOCKED",
            "contractStatus": "PREPARED", "sourceCommit": commit,
            "observedAtUtc": C.system_utc_now().isoformat(), "sources": sources,
            "generationTimes": dates, "sameGeneration": coherent,
            "verifiedStoredWeeklyReceipts": verified,
            "rejectedStoredWeeklyReceipts": rejected,
            "productionStoreStatus": "ABSENT" if absent else "NOT_CERTIFIED",
            "firstRealReceiptVerified": False if absent else None,
            "blockers": sorted(set(blockers)),
            "activationEnabled": False, "productionWrites": 0,
            "receiptWrites": 0, "priceReads": 0, "performance": None,
            "interpretation": "Byte verification and negative gates only; no operational or investment admission."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-ref", required=True)
    args = parser.parse_args()
    if not C.is_git_sha(args.source_ref):
        parser.error("EXACT_40_CHARACTER_SOURCE_SHA_REQUIRED")
    print(json.dumps(inspect_snapshot(Path(__file__).resolve().parents[2], args.source_ref),
                     ensure_ascii=False, indent=2))
    return 0  # Successful inspection can correctly report BLOCKED.


if __name__ == "__main__":
    raise SystemExit(main())
