#!/usr/bin/env python3
"""KR market risk anatomy v2 runner. `verify` and `readiness` are outcome-free; `execute` refuses before reading any value unless the run is a
workflow_dispatch on merged main whose committed spec, frozen design and source snapshot match their pins (see pipeline.kr_market_risk_anatomy_v2_execution).

EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY. v2 corrects source admissibility only and reads the bytes retained by v1; v1 stays blocked. Never reruns a sealed study, never contacts a data vendor. A verdict exits 0; only an infrastructure
error exits non-zero. A failure BEFORE the durable execution lock spends nothing; a failure AFTER it consumes the one-shot execution.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import kr_market_risk_anatomy_v2_execution as E  # noqa: E402


def run(mode, *, inputs=None, output=None, root=ROOT, env=None):
    if mode == "verify":
        report = E.verify(root, env)
    elif mode == "readiness":
        report = E.readiness_audit(root)
    elif mode == "execute":
        spec, sha = E.load_spec(root)
        permit = E.authorize_execution(spec, sha, root, env)      # refuse BEFORE any value is read
        if not output:
            raise ValueError("EXECUTE_REQUIRES_OUTPUT")
        return E.execute(output, spec, sha, permit, root, env, input_root=inputs, extended_builder=E.extended_internals)
    else:
        raise ValueError("UNREGISTERED_EXECUTION_MODE")
    if output:
        Path(output).mkdir(parents=True, exist_ok=True)
        (Path(output) / (mode + ".json")).write_text(json.dumps(report, sort_keys=True, indent=2, default=str) + "\n")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("verify", "readiness", "execute"), default="verify")
    parser.add_argument("--inputs")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    print(json.dumps(run(args.mode, inputs=args.inputs, output=args.output), sort_keys=True, default=str))


if __name__ == "__main__":
    main()
