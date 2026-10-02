#!/usr/bin/env python3
"""KR Top120 regime review v1 runner. `verify` is outcome-free; `execute` refuses before reading any data unless the run is a
workflow_dispatch on merged main that names the exact preserved raw artifact over the exact sealed anatomy result
(see pipeline.kr_top120_regime_review_execution).

EXPLORATORY_POST_OUTCOME_REGIME_DIAGNOSTIC. This runner never reruns kr-factor-anatomy-v1, never invokes any sealed
execute path and never contacts KRX. A verdict (including DATA_INSUFFICIENT) exits 0; only an infrastructure error exits
non-zero, and it is written as an attempt record that does not close the study.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import kr_top120_regime_review_execution as E  # noqa: E402


def run(mode, *, input_root=None, output=None, root=ROOT, env=None):
    if mode == "verify":
        report = E.verify(root, env)
        if output:
            Path(output).mkdir(parents=True, exist_ok=True)
            (Path(output) / "verify.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
        return report
    if mode != "execute":
        raise ValueError("UNREGISTERED_EXECUTION_MODE")
    spec, sha = E.load_spec(root)
    # Refuse BEFORE any data is read.
    permit = E.authorize_execution(spec, sha, root, env)
    if not input_root or not output:
        raise ValueError("EXECUTE_REQUIRES_INPUTS_AND_OUTPUT")
    return E.execute(input_root, output, spec, sha, permit, root)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("verify", "execute"), default="verify")
    parser.add_argument("--inputs")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    print(json.dumps(run(args.mode, input_root=args.inputs, output=args.output), sort_keys=True))


if __name__ == "__main__":
    main()
