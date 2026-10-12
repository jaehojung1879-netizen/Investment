"""Run the frozen US H63 supplemental inference calibration (150-244 names per date; synthetic only, reads no market data).

    python scripts/run_us_h63_supplemental_calibration.py --write-protocol     # once, BEFORE any replicate; commit the file
    python scripts/run_us_h63_supplemental_calibration.py --workers 4          # the expensive run (tens of minutes)
    python scripts/run_us_h63_supplemental_calibration.py --smoke 3            # DEVELOPMENT_ONLY wiring check, never a result

Replicates are seeded by SeedSequence([seed, dgp index, weeks, replicate]); the result does not depend on the worker count. The run
refuses a dirty pipeline/scripts tree, a protocol that does not equal `build_protocol()`, any change to the parent calibration, and
an existing result file. It is deliberately not part of routine CI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import scipy

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import us_h63_inference_calibration as U            # noqa: E402
from pipeline import us_h63_supplemental_calibration as S         # noqa: E402


def canonical(obj) -> str:
    return json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT).decode().strip()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output", type=Path, default=S.RESULT_PATH)
    parser.add_argument("--smoke", type=int, help="DEVELOPMENT_ONLY replicate count; output is labelled and never a result")
    parser.add_argument("--write-protocol", action="store_true", help="write the frozen protocol file (refuses to overwrite)")
    args = parser.parse_args(argv)

    if args.write_protocol:
        if S.PROTOCOL_PATH.exists():
            raise SystemExit("PROTOCOL_ALREADY_WRITTEN")
        S.PROTOCOL_PATH.write_text(canonical(S.build_protocol()))
        print("wrote", S.PROTOCOL_PATH, hashlib.sha256(S.PROTOCOL_PATH.read_bytes()).hexdigest())
        return 0

    raw = S.PROTOCOL_PATH.read_bytes()
    supplement = json.loads(raw)
    if json.loads(canonical(S.build_protocol())) != supplement:
        raise SystemExit("PROTOCOL_DIFFERS_FROM_BUILD")
    protocol = S.effective_protocol(supplement)
    if not args.smoke:
        if args.output.exists():
            raise SystemExit("RESULT_ALREADY_EXISTS")
        dirty = git("status", "--porcelain", "--", "pipeline", "scripts", "docs/us-readiness")
        if dirty:
            raise SystemExit("DIRTY_TREE_REFUSED:\n" + dirty)

    if args.smoke:
        protocol = {**protocol, "seed": 1}      # a development seed: no smoke replicate ever draws a formal stream
    reps = args.smoke or int(protocol["replicates"])
    geo_reps = min(S.GEOMETRY_CHECK_REPLICATES, reps) if args.smoke else S.GEOMETRY_CHECK_REPLICATES
    weeks_list = protocol["sampleLengths"]["weeks"]
    expected = len(protocol["dgps"]) * len(weeks_list)
    started, cells = time.time(), []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for i, dgp in enumerate(protocol["dgps"]):
            for weeks in weeks_list:
                jobs = [(protocol, i, weeks, r) for r in range(reps)]
                records = list(pool.map(S.replicate_job, jobs, chunksize=max(1, len(jobs) // 64)))
                geometry = list(pool.map(S.geometry_job, [(protocol, i, weeks, k) for k in range(geo_reps)]))
                cell = S.build_cell(protocol, i, weeks, records, geometry)
                cells.append(cell)
                print("%-34s %4d  CT_SN %-12s names %.1f  %6.0fs" % (dgp["name"], weeks, cell["primaryState"],
                                                                      cell["geometry"]["meanAvailableNames"], time.time() - started), flush=True)

    result = {
        "contract": S.CONTRACT, "evidenceClass": "SYNTHETIC_INFERENCE_CALIBRATION_NOT_INVESTMENT_PERFORMANCE",
        "developmentOnly": bool(args.smoke), "readsRealData": False,
        "protocolSha256": hashlib.sha256(raw).hexdigest(), "parent": supplement["parent"],
        "replicates": reps, "seed": protocol["seed"], "primaryMethod": U.PRIMARY_METHOD,
        "codeCommit": git("rev-parse", "HEAD"),
        "codeSha256": {f: S.sha256_file(ROOT / f) for f in ("pipeline/us_h63_supplemental_calibration.py",
                                                            "scripts/run_us_h63_supplemental_calibration.py",
                                                            "pipeline/us_h63_inference_calibration.py")},
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
                        "platform": platform.platform(), "note": "results are independent of the worker count; a different "
                        "numpy/scipy build could change last-bit values and is recorded here for that reason"},
        "verdict": S.verdict(cells, expected) if not args.smoke else {"supplementStatus": "DEVELOPMENT_SMOKE_NOT_A_RESULT"},
        "cells": cells,
    }
    out = args.output if not args.smoke else args.output.with_name("us-h63-inference-calibration-v1-supplement-SMOKE.json")
    out.write_text(canonical(result))
    print("SUPPLEMENT:", result["verdict"]["supplementStatus"], "->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
