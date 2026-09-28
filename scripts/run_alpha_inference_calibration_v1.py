#!/usr/bin/env python3
"""Run the frozen synthetic Alpha inference calibration v1 protocol."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pipeline.alpha_inference_calibration_v1 import run_calibration


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--spec",
        default="research_specs/alpha-inference-calibration-v1.json",
        help="Frozen synthetic-only calibration protocol.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/alpha-inference-calibration-v1.json",
        help="Result path. The workflow uploads this artifact but never writes signal-history.",
    )
    args = parser.parse_args()

    spec_path = Path(args.spec)
    raw = spec_path.read_bytes()
    spec = json.loads(raw)
    result = run_calibration(spec)
    result["specSha256"] = hashlib.sha256(raw).hexdigest()
    result["specPath"] = str(spec_path)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({
        "contract": result["contract"],
        "primaryStatus": result["primaryStatus"],
        "cells": len(result["cells"]),
        "specSha256": result["specSha256"],
        "output": str(output),
    }, indent=2))

    if result["primaryStatus"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
