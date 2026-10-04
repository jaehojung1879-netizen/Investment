#!/usr/bin/env python3
"""KR industry opportunity anatomy v1 runner. `verify` and `readiness` are outcome-free; `execute` refuses before reading any data
unless the run is a workflow_dispatch on merged main that names the exact preserved raw artifact over the exact pinned membership
(see pipeline.kr_industry_anatomy_execution).

EXPLORATORY_DEVELOPMENT_ON_PARTIALLY_RECONSTRUCTED_KR_HISTORY. Never reruns a sealed study, never contacts KRX, DART or KIND.
A verdict exits 0; only an infrastructure error exits non-zero. A failure BEFORE the durable execution lock spends nothing; a
failure AFTER it consumes the one-shot execution.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import kr_industry_anatomy_execution as E  # noqa: E402


def run(mode, *, input_root=None, output=None, root=ROOT, env=None):
    if mode == "verify":
        report = E.verify(root, env)
    elif mode == "readiness":
        report = E.readiness_audit(root)
    elif mode == "execute":
        spec, sha = E.load_spec(root)
        permit = E.authorize_execution(spec, sha, root, env)      # refuse BEFORE any data is read
        if not input_root or not output:
            raise ValueError("EXECUTE_REQUIRES_INPUTS_AND_OUTPUT")
        return E.execute(input_root, output, spec, sha, permit, root, env)
    else:
        raise ValueError("UNREGISTERED_EXECUTION_MODE")
    if output:
        Path(output).mkdir(parents=True, exist_ok=True)
        (Path(output) / (mode + ".json")).write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("verify", "readiness", "execute"), default="verify")
    parser.add_argument("--inputs")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    print(json.dumps(run(args.mode, input_root=args.inputs, output=args.output), sort_keys=True))


if __name__ == "__main__":
    main()
