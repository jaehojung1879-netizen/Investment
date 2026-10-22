#!/usr/bin/env python3
"""Track B synthetic recorder and read-only readiness. LIVE is disabled."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import rp1_b_state_recording as B


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("record-live")
    record = sub.add_parser("record-synthetic")
    record.add_argument("--input", required=True, type=Path)
    record.add_argument("--ledger", required=True, type=Path)
    record.add_argument("--checkpoint", required=True, type=Path)
    record.add_argument("--merged-at", required=True)
    record.add_argument("--now", required=True)
    verify = sub.add_parser("validate-synthetic")
    verify.add_argument("--ledger", required=True, type=Path)
    verify.add_argument("--checkpoint", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "status":
            result = B.activation_status()
        elif args.command == "record-live":
            B.record_live()
        else:
            pin = json.loads(args.checkpoint.read_text())
            if args.command == "validate-synthetic":
                result = B.verify_synthetic_ledger(args.ledger, expected_checkpoint=pin)
            else:
                source = json.loads(args.input.read_text())
                receipt = B.build_synthetic_receipt(source, merged_at_utc=args.merged_at, now_utc=args.now)
                pin = B.append_synthetic(args.ledger, receipt, source=source, expected_checkpoint=pin)
                result = {"status": "SYNTHETIC_APPENDED", "checkpoint": pin}
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
