"""alpha-opportunity-model-v3: print readiness; refuse execution while blocked.

v3 is sealed as BLOCKED_BY_DATA_INTEGRITY (see
docs/results/alpha-opportunity-model-v3-survivorship-audit.json). `--execute`
fails closed on the sealed status BEFORE any input path is read or any label
could be constructed. There is deliberately no v3 execution harness and no v3
workflow: an execution that the preregistration forbids should not exist as a
button.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import alpha_opportunity_v3_spec as S  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=S.DEFAULT_SPEC)
    parser.add_argument("--sealed-sha256", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--reviewed", action="store_true")
    args = parser.parse_args(argv)
    spec = S.load_sealed(args.spec, expected_hash=args.sealed_sha256)
    if not args.execute:
        print(json.dumps(S.readiness(spec, args.sealed_sha256), sort_keys=True))
        return 0
    S.require_execution(spec, reviewed=args.reviewed, branch=os.environ.get("GITHUB_REF"))
    raise ValueError("NO_V3_EXECUTION_HARNESS: a READY design requires a new reviewed version")


if __name__ == "__main__":
    raise SystemExit(main())
