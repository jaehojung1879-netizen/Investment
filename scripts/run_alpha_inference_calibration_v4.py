#!/usr/bin/env python3
"""Run the frozen synthetic Alpha inference calibration v4 protocol.

Exit codes: 0 for any complete methodological verdict (PASS, FAIL,
DATA_INSUFFICIENT) -- the verdict lives in the artifact and in the printed
summary, never in the process status -- and 1 for INFRASTRUCTURE_ERROR, which
still writes an artifact saying so.  ``--development-smoke`` runs a reduced
budget on a different seed, labels the artifact DEVELOPMENT_ONLY and carries no
verdict authority.
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

from pipeline.alpha_inference_calibration_v4 import CONTRACT, run_calibration  # noqa: E402

DEFAULT_SPEC = "research_specs/alpha-inference-calibration-v4.json"
DEFAULT_OUTPUT = "artifacts/alpha-inference-calibration-v4.json"
# Path components that hold real market data, Alpha results or ledgers.  The
# calibration never needs any of them, so touching one is refused outright.
FORBIDDEN_COMPONENTS = frozenset({
    "ledger", "data", "results", "signal-history", "historical", "benchmarks", "fundamentals",
})


def guard_path(path: Path, role: str) -> Path:
    """Refuse a spec or output path inside any real-data or result location."""
    resolved = path.resolve()
    parts = {part.lower() for part in resolved.parts}
    hit = parts & FORBIDDEN_COMPONENTS
    if hit:
        raise SystemExit(f"REFUSED_{role.upper()}_PATH: {path} touches {sorted(hit)}")
    if role == "spec" and resolved.suffix != ".json":
        raise SystemExit(f"REFUSED_SPEC_PATH: {path} is not a JSON protocol")
    return resolved


def _write(output: Path, payload: dict) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Frozen synthetic-only calendar-time calibration v4 protocol.")
    parser.add_argument("--spec", default=DEFAULT_SPEC, help="Frozen synthetic-only v4 protocol.")
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
    formal_seed = spec.get("seed")
    run_class = "FORMAL"
    if args.development_smoke:
        if args.development_seed == formal_seed:
            raise SystemExit("REFUSED: a development smoke may not reuse the frozen formal seed")
        run_class = "DEVELOPMENT_ONLY"
        spec = {**spec, "seed": args.development_seed, "simulationReplicates": args.development_smoke}

    started = time.time()
    try:
        result = run_calibration(
            spec,
            progress=lambda cell: print(
                f"  {cell['dgp']} H{cell['horizonSessions']} {cell['calendarWeeks']}w: {cell['status']}",
                flush=True,
            ),
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
        "seedUsed": spec["seed"],
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
