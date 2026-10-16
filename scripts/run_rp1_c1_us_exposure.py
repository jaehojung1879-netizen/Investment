#!/usr/bin/env python3
"""Outcome-free modes of rp1-c1-us-exposure-ladder-replication-v1: verify | readiness | design-readiness | equivalence.

There is no execute mode here: the formal one-shot run is WP4d, a separate change. `equivalence --write` refreshes the committed equivalence record."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import rp1_c1_us_exposure_spec as SP  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["verify", "readiness", "design-readiness", "equivalence"])
    parser.add_argument("--write", action="store_true", help="equivalence only: write the committed record")
    args = parser.parse_args(argv)
    if args.mode == "verify":
        out = SP.verify(ROOT)
    elif args.mode == "readiness":
        out = SP.readiness_audit(ROOT)
    elif args.mode == "design-readiness":
        out = SP.readiness_audit(ROOT, assume_complete_reference=True)
    else:
        out = SP.equivalence_audit(ROOT)
        if args.write:
            path = ROOT / SP.EQUIVALENCE_PATH
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(json.dumps(out, indent=2, sort_keys=True, default=str))
    if args.mode == "equivalence":
        return 0 if out["status"] == "EXACT" else 1
    if args.mode == "verify":
        return 0
    return 0 if out["decision"] in (SP.DECISION_READY, SP.DESIGN_PASSED) else 2


if __name__ == "__main__":
    raise SystemExit(main())
