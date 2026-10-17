#!/usr/bin/env python3
"""WP4d of rp1-c1-us-exposure-ladder-replication-v1: probe | freeze-check | freeze-manifest | verify-snapshot | dry-run | authorization-draft | execute.

Only `execute` can compute US strategy outcomes, and only after the owner's authorization, the readiness and equivalence gates and the durable lock (see
`pipeline/rp1_c1_us_execution.py`). Every other mode is outcome-free. Bounded analysis directories are reacquired inside a runner, outside the repository;
their bytes are never printed.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import rp1_c1_us_execution as X  # noqa: E402
from pipeline import rp1_c1_us_exposure_spec as SP  # noqa: E402


def emit(document, path=None):
    text = json.dumps(document, indent=2, sort_keys=True, default=str) + "\n"
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text)
    print(text)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["probe", "freeze-check", "freeze-manifest", "verify-snapshot", "dry-run", "authorization-draft", "execute",
                                         "freeze-preview", "authorization-check", "encode-for-log"])
    parser.add_argument("--snapshot")
    parser.add_argument("--output")
    parser.add_argument("--run-id")
    parser.add_argument("--commit")
    parser.add_argument("--owner", default="")
    parser.add_argument("--authorization-sha256", default="")
    parser.add_argument("--file")
    args = parser.parse_args(argv)
    try:
        if args.mode == "probe":
            out = X.probe(ROOT, args.snapshot)
            emit(out, args.output)
            return 0
        if args.mode == "freeze-check":
            if (ROOT / X.AUTHORIZATION_PATH).exists():
                raise X.Refused("AN_AUTHORIZATION_IS_COMMITTED_WITHDRAW_IT_BEFORE_A_NEW_FREEZE")
            out = SP.readiness_audit(ROOT, snapshot_dir=args.snapshot)
            emit({k: out.get(k) for k in ("decision", "blockers", "checks", "determinable", "decisionDates", "snapshotIdentity", "counters")}, args.output)
            return 0 if out["decision"] == SP.DECISION_READY else 2
        if args.mode in ("freeze-manifest", "freeze-preview"):
            manifest = X.freeze_manifest(ROOT, args.snapshot, run_id=args.run_id, commit_sha=args.commit)
            if args.mode == "freeze-preview":
                emit(manifest, args.output)
                return 0
            for old in SP.freeze_manifest_paths(ROOT):
                (ROOT / old).unlink()
            path = ROOT / X.freeze_manifest_path(args.run_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
            print(X.freeze_manifest_path(args.run_id))
            return 0
        if args.mode == "verify-snapshot":
            if not args.snapshot:
                raise X.Refused("SNAPSHOT_DIRECTORY_REQUIRED_FOR_HASH_VERIFICATION")
            spec, _ = SP.load_spec(ROOT)
            pinned = SP.verify_us_snapshot(spec, ROOT, args.snapshot)
            scopes = {}
            for scope in X.R.SCOPES:
                try:
                    scopes[scope] = "MATCHED" if SP.verify_us_snapshot(spec, ROOT, args.snapshot, scope) else "NOT_FROZEN"
                except (ValueError, OSError, KeyError):
                    scopes[scope] = "BLOCKED_HASH_MISMATCH"
            cross = SP.cross_check_status(args.snapshot, SP.snapshot_audit(args.snapshot))
            emit({"status": "MATCHES_THE_FROZEN_PRIMARY" if pinned else "NOT_FROZEN", "scopes": scopes,
                  "referenceCrossCheck": cross,
                  "files": len(SP.snapshot_files(args.snapshot)), "cashEconomicScientificSha256": spec["cashEconomicSpec"]["scientificSha256"]})
            return 0 if pinned and cross["status"] == "CONSISTENT" else 2
        if args.mode == "dry-run":
            out = X.dry_run(args.output or "dry-run", ROOT, args.snapshot)
            emit(out)
            return 0
        if args.mode == "authorization-draft":
            emit(X.authorization_draft(ROOT, args.owner), args.output)
            return 0
        if args.mode == "authorization-check":
            permit = X.authorize(ROOT, os.environ, args.authorization_sha256)
            emit({"status": "OWNER_AUTHORIZATION_VERIFIED_NO_LOCK", "specSha256": permit.specSha256})
            return 0
        if args.mode == "execute":
            emit(X.execute(args.output or "run", ROOT, args.snapshot, os.environ, args.authorization_sha256))
            return 0
        raw = Path(args.file).read_bytes()
        print("BEGIN " + Path(args.file).name + " gzip+base64")
        print(base64.b64encode(gzip.compress(raw, mtime=0)).decode())
        print("END " + Path(args.file).name)
        return 0
    except (ValueError, OSError, KeyError) as error:
        print("REFUSED_BEFORE_THE_LOCK: " + (str(error) if isinstance(error, X.Refused) else "INPUT_VERIFICATION_FAILED:" + type(error).__name__))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
