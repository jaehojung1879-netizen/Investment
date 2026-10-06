#!/usr/bin/env python3
"""KR alpha discovery tournament v1 runner. `verify` and `readiness` are outcome-free; `execute` refuses before reading any data unless the run is a
workflow_dispatch on merged main that names the exact preserved raw artifact (see pipeline.kr_alpha_tournament_execution).

EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY. Never reruns a sealed study, never contacts a data vendor. A verdict (A-E) exits 0; only an
infrastructure error exits non-zero. A failure BEFORE the durable execution lock spends nothing; a failure AFTER it consumes the one-shot execution,
and the study is never retried.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import kr_alpha_tournament_execution as E  # noqa: E402


def run(mode, *, input_root=None, output=None, root=ROOT, env=None, full_registry=False):
    if mode == "verify":
        report = E.verify(root)
    elif mode == "readiness":
        report = E.readiness_audit(root, full_registry=full_registry)
    elif mode == "execute":
        spec, sha = E.load_spec(root)
        permit = E.authorize_execution(spec, sha, root, env)      # refuse BEFORE any data is read
        if not input_root or not output:
            raise ValueError("EXECUTE_REQUIRES_INPUTS_AND_OUTPUT")
        result = E.execute(input_root, output, spec, sha, permit, root, env)
        return {"studyId": result["studyId"], "verdict": result["verdict"]}
    else:
        raise ValueError("UNREGISTERED_EXECUTION_MODE")
    if output:
        Path(output).mkdir(parents=True, exist_ok=True)
        (Path(output) / (mode + ".json")).write_text(json.dumps(E.json_safe(report), sort_keys=True, indent=2) + "\n")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("verify", "readiness", "execute"), default="verify")
    parser.add_argument("--inputs")
    parser.add_argument("--output")
    parser.add_argument("--full-registry", action="store_true", help="readiness: run the invented world through the FULL 120-configuration registry")
    args = parser.parse_args(argv)
    print(json.dumps(E.json_safe(run(args.mode, input_root=args.inputs, output=args.output, full_registry=args.full_registry)), sort_keys=True))


if __name__ == "__main__":
    main()
