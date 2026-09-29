"""alpha-opportunity-model-v5 verifier and execution gate. Outcome-free.

`--verify-only` loads the sealed preregistration and checks every frozen identity
(spec digest, dependency closure, v1-v4 seals, inherited values, KR accounting
snapshot pin, calibrated-inference pin) and, on request, the snapshot and the raw
inputs against their pinned git objects. It reads accounting shards and raw input
blobs only: no price return, label, score or Alpha artifact.

`--execute` verifies first and then REFUSES: the reviewed execution harness is a
separate, later change that must not alter this sealed closure. There is no
Alpha-v5 result and none can be produced from this file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import alpha_opportunity_v5_spec as S  # noqa: E402
from pipeline import kr_repaired_accounting_snapshot as K  # noqa: E402


def blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def verify_snapshot_from_git(spec) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        dirs = K.materialize_from_git(ROOT, Path(tmp), spec["inputs"]["krAccounting"]["sourceCommit"])
        manifest = K.build_manifest(dirs["merged"], dirs["canonical"], dirs["xbrl"], ROOT)
        regen = K.regenerate_and_compare(dirs["canonical"], dirs["xbrl"], dirs["merged"], ROOT)
    pin = spec["inputs"]["krAccounting"]
    if manifest["snapshotContentSha256"] != pin["snapshotContentSha256"]:
        raise ValueError("SNAPSHOT_CONTENT_CHANGED")
    if manifest["candidateIdentitySha256"] != pin["candidateIdentitySha256"] or manifest["recordCount"] != pin["recordCount"]:
        raise ValueError("SNAPSHOT_IDENTITY_CHANGED")
    if not (regen["byteIdentical"] and regen["shardSetEqual"] and regen["mergeReportEqual"]):
        raise ValueError("SNAPSHOT_REGENERATION_DIFFERS")
    return {"snapshotContentSha256": manifest["snapshotContentSha256"], "recordCount": manifest["recordCount"],
            "regenerationByteIdentical": True}


def verify_raw_inputs_from_git(spec) -> dict:
    """Blob identity of every sealed raw input at the pinned signal-history commit. Reads no row."""
    raw = spec["inputs"]["sealedRaw"]
    commit = raw["signalHistoryCommit"]
    checked = 0
    for rel, sha in sorted(raw["gitBlobSha1"].items()):
        data = subprocess.check_output(["git", "show", f"{commit}:{rel}"], cwd=ROOT)
        if blob_sha1(data) != sha:
            raise ValueError("INPUT_SNAPSHOT_CHANGED: " + rel)
        checked += 1
    return {"signalHistoryCommit": commit, "blobsVerified": checked}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--spec", type=Path, default=S.DEFAULT_SPEC)
    p.add_argument("--sealed-sha256", required=True)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--verify-only", action="store_true")
    mode.add_argument("--execute", action="store_true")
    p.add_argument("--verify-snapshot-from-git", action="store_true")
    p.add_argument("--verify-raw-inputs-from-git", action="store_true")
    args = p.parse_args(argv)
    spec = S.load_sealed(args.spec, expected_hash=args.sealed_sha256)
    report = {"study": S.STUDY, "specSha256": args.sealed_sha256, "status": spec["preregistrationStatus"],
              "regions": spec["regions"], "outcomeAccess": "NONE", "sealedIdentity": "VERIFIED"}
    if args.verify_snapshot_from_git:
        report["snapshot"] = verify_snapshot_from_git(spec)
    if args.verify_raw_inputs_from_git:
        report["rawInputs"] = verify_raw_inputs_from_git(spec)
    print(json.dumps(report, sort_keys=True))
    if args.execute:
        S.require_execution(spec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
