"""alpha-opportunity-model-v4: print readiness; refuse execution unconditionally.

v4 may be sealed `READY_FOR_HISTORICAL_EXECUTION` at the DESIGN level (see
`pipeline/alpha_opportunity_v4_spec.py`'s docstring for why that can be true
while the KR terminal-action source foundation stays `PARTIALLY_REPAIRED`),
but this PR builds no label engine, no training loop and no evaluation
harness. `--execute` therefore fails closed regardless of readiness --
exactly `alpha-opportunity-model-v3`'s own script's discipline: an execution
a preregistration does not yet implement should not exist as a button.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import alpha_opportunity_v4_spec as S  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=S.DEFAULT_SPEC)
    parser.add_argument("--sealed-sha256", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    spec = S.load_sealed(args.spec, expected_hash=args.sealed_sha256)
    if not args.execute:
        print(json.dumps(S.readiness(spec, args.sealed_sha256), sort_keys=True))
        return 0
    raise ValueError("NO_V4_EXECUTION_HARNESS_IN_THIS_PR: a future execution PR must build, "
                     "test and get reviewed the label/training/evaluation harness -- this "
                     "preregistration PR computes no label, fits no model, and reads no return")


if __name__ == "__main__":
    raise SystemExit(main())
