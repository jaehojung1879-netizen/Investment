"""Replay the isolated 069500 benchmark audit from hash-identified snapshots."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.kr_alpha_atlas_benchmark_audit import run  # noqa: E402
from pipeline.kr_alpha_atlas_phase_c.contract import ROOT, canonical  # noqa: E402
from pipeline.kr_model_raw_snapshot import immutable_bytes  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(ROOT, args.sources)
    immutable_bytes(args.output, canonical(report) + b"\n")
    print(json.dumps({"status": report["status"], "annualComparisons": report["benchmarkOnlyAnnualComparisons"],
                      "scope": report["scope"], "benchmarkGate": report["benchmarkIntegrityUnchanged"]["claimGate"]}))


if __name__ == "__main__":
    main()
