"""Explicit full input audit; has no scientific execution action."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.kr_alpha_atlas_integrity_audit import audited_preflight  # noqa: E402
from pipeline.kr_alpha_atlas_phase_c.contract import ROOT  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-main", required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    report = audited_preflight(ROOT, args.work, args.expected_main)
    print(json.dumps({"status": report["status"], "matrixDigest": report["actualMatrixDigest"],
                      "elapsedSeconds": report["elapsedSeconds"], "counters": report["counters"]}))


if __name__ == "__main__":
    main()
