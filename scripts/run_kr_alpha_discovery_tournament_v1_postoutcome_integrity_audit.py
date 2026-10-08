#!/usr/bin/env python3
"""kr-alpha-discovery-tournament-v1 post-outcome integrity audit (POST_OUTCOME_FORENSIC_DIAGNOSTIC; never an execution).

  --mode scan  --replay-root DIR   model-free price-gap / terminal-window scan from the hash-verified replay-v16 panels and PIT membership
  --mode full  --inputs DIR        read-only reconstruction of the frozen process on the exact preserved raw-input artifact (Actions only),
                                   reproduction gate against the sealed result, then first-failure attribution per incomplete path

Neither mode claims or reads a lock as authorisation, writes a marker, or touches the sealed result.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import kr_alpha_tournament_postoutcome_integrity_audit as A  # noqa: E402


def _write(path, document):
    if Path(path).resolve() == (ROOT / A.FORMAL["resultPath"]).resolve():
        raise ValueError("REFUSING_TO_WRITE_THE_SEALED_RESULT")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(document, sort_keys=True, indent=1, ensure_ascii=False) + "\n")


def status_of(document):
    """The one-line status printed after the document is written. Lazy on purpose: a full document carries `reproduction.status` and no
    `evidenceClass`, a scan document the reverse, and `dict.get(key, default)` evaluates its default eagerly, so
    `document.get("reproduction", {}).get("status", document["evidenceClass"])` raised KeyError on every full run, after the file was written."""
    return (document.get("reproduction") or {}).get("status") or document.get("evidenceClass") or "UNKNOWN"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("scan", "full"), required=True)
    parser.add_argument("--replay-root")
    parser.add_argument("--inputs")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    A.verify_sealed_result(ROOT)
    if args.mode == "scan":
        if not args.replay_root:
            raise SystemExit("SCAN_REQUIRES_REPLAY_ROOT")
        document = A.model_free_scan(args.replay_root, ROOT)
    else:
        if not args.inputs:
            raise SystemExit("FULL_REQUIRES_INPUTS")
        document = A.reconstruct(args.inputs, ROOT)
    _write(args.output, document)
    print(json.dumps({"auditId": A.AUDIT_ID, "mode": args.mode, "status": status_of(document)}, sort_keys=True))


if __name__ == "__main__":
    main()
