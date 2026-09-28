#!/usr/bin/env python3
"""Run the frozen synthetic Alpha inference calibration v5 protocol.

v5 is a precision-only replication of the closed v4 calibration: the unchanged v4
engine is called with a new seed and a larger replicate budget.  Exit codes: 0 for
any complete methodological verdict (PASS, FAIL, INCONCLUSIVE, DATA_INSUFFICIENT),
1 for INFRASTRUCTURE_ERROR, which still writes an artifact saying so.  A formal run
refuses an altered protocol, seed, budget, scientific configuration or engine file
(reported as INFRASTRUCTURE_ERROR with the reason).  ``--development-smoke`` runs a
reduced budget on a different seed, is labelled DEVELOPMENT_ONLY, carries no
verdict authority and may not reuse the formal seed or any closed protocol's seed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.alpha_inference_calibration_v5 import (  # noqa: E402
    CONTRACT,
    FORMAL_PINS,
    PRIOR_SEEDS,
    run_calibration,
)
from scripts.run_alpha_inference_calibration_v4 import _write, guard_path  # noqa: E402

DEFAULT_SPEC = "research_specs/alpha-inference-calibration-v5.json"
DEFAULT_OUTPUT = "artifacts/alpha-inference-calibration-v5.json"
FROZEN_SEEDS = {FORMAL_PINS["seed"], *PRIOR_SEEDS.values()}


def verify_engine_identity(pins: dict[str, str] | None = None, root: Path = ROOT) -> None:
    """Refuse to run if any file the v4 engine executes differs from its frozen bytes."""
    pins = FORMAL_PINS["engineFiles"] if pins is None else pins
    for relative, expected in pins.items():
        actual = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"ENGINE_FILE_CHANGED: {relative} sha256 {actual} != frozen {expected}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Frozen synthetic-only calibration v5 (precision-only replication of v4).")
    parser.add_argument("--spec", default=DEFAULT_SPEC, help="Frozen synthetic-only v5 protocol.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Result path; never signal-history.")
    parser.add_argument(
        "--development-smoke",
        type=int,
        default=0,
        metavar="REPLICATES",
        help="DEVELOPMENT_ONLY reduced budget on --development-seed; no verdict authority.",
    )
    parser.add_argument("--development-seed", type=int, default=1, help="Seed for --development-smoke only.")
    args = parser.parse_args(argv)

    spec_path = guard_path(Path(args.spec), "spec")
    output = guard_path(Path(args.output), "output")
    raw = spec_path.read_bytes()
    spec_sha = hashlib.sha256(raw).hexdigest()
    spec = json.loads(raw)
    run_class = "FORMAL"
    if args.development_smoke:
        if args.development_seed in FROZEN_SEEDS:
            raise SystemExit("REFUSED: a development smoke may not reuse the formal seed or any closed protocol's seed")
        run_class = "DEVELOPMENT_ONLY"
        spec = {**spec, "seed": args.development_seed, "simulationReplicates": args.development_smoke}

    started = time.time()
    try:
        predecessor_path = guard_path(ROOT / spec["predecessorSpecPath"], "spec")
        predecessor_raw = predecessor_path.read_bytes()
        verify_engine_identity()
        result = run_calibration(
            spec,
            predecessor_spec=json.loads(predecessor_raw),
            predecessor_spec_sha256=hashlib.sha256(predecessor_raw).hexdigest(),
            progress=lambda cell: print(
                f"  {cell['dgp']} H{cell['horizonSessions']} {cell['calendarWeeks']}w: {cell['status']}",
                flush=True,
            ),
            formal=(run_class == "FORMAL"),
        )
    except Exception as exc:  # noqa: BLE001 - every failure must still leave an artifact
        _write(output, {
            "contract": CONTRACT,
            "primaryStatus": "INFRASTRUCTURE_ERROR",
            "runClass": run_class,
            "specSha256": spec_sha,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        })
        print(json.dumps({"primaryStatus": "INFRASTRUCTURE_ERROR", "specSha256": spec_sha, "error": str(exc)}))
        return 1

    result.update({
        "specSha256": spec_sha,
        "specPath": str(Path(args.spec)),
        "runClass": run_class,
        "verdictAuthority": "FROZEN_PROTOCOL" if run_class == "FORMAL" else "NONE_DEVELOPMENT_ONLY",
    })
    # Wall-clock time is printed, never written: identical seeds must give byte-identical artifacts.
    _write(output, result)
    print(json.dumps({
        "elapsedSeconds": round(time.time() - started, 1),
        "contract": result["contract"],
        "runClass": run_class,
        "primaryStatus": result["primaryStatus"],
        "cells": len(result["cells"]),
        "failedCells": len(result["primaryFailures"]),
        "specSha256": spec_sha,
        "output": str(output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
