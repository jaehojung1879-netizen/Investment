#!/usr/bin/env python3
"""rp1-inference-calibration-v1 (Track A / WP1): build | verify | formal | smoke | reproduce | encode-for-log.

`formal` runs the frozen protocol once (synthetic only) and writes the result under artifacts/. `reproduce` re-runs a fixed subset of
cells with the formal seed and requires byte-identical cells against a committed result. `smoke` is DEVELOPMENT_ONLY: another seed, at most
50 replicates, no verdict, never committed. No mode reads market data.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import rp1_inference_calibration as W  # noqa: E402

DEFAULT_OUTPUT = "artifacts/rp1-inference-calibration-v1-result.json"
REPRODUCTION_UNITS = (("252", 78), ("126", 78))     # cheap cells re-run for every DGP to prove the committed bytes are reproducible


def canonical(document):
    return json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n"


def environment():
    import numpy
    import scipy
    return {"python": platform.python_version(), "numpy": numpy.__version__, "scipy": scipy.__version__}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["build", "verify", "formal", "smoke", "reproduce", "encode-for-log"])
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--replicates", type=int, default=20)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--file")
    args = parser.parse_args(argv)

    if args.mode == "build":
        if (ROOT / W.RESULT_PATH).exists():
            raise SystemExit("REFUSED: a result is committed; the protocol is closed")
        spec = W.build_spec(ROOT)
        path = ROOT / W.SPEC_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(spec, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        path.write_text(text)
        path.with_suffix(".sha256").write_text(hashlib.sha256(text.encode()).hexdigest() + "\n")
        print(hashlib.sha256(text.encode()).hexdigest())
        return 0

    spec, sha = W.load_spec(ROOT)
    if args.mode == "verify":
        print(json.dumps({"studyId": W.STUDY, "specSha256": sha, "claims": spec["claims"], "cells": spec["cells"]["horizons"],
                          "failSideDecisionCount": spec["monteCarloDecision"]["failSideDecisionCount"], "seed": spec["seed"],
                          "simulationReplicates": spec["simulationReplicates"], "outcomeFree": True}, indent=2))
        return 0

    if args.mode == "encode-for-log":
        raw = Path(args.file).read_bytes()
        print("SHA256 " + hashlib.sha256(raw).hexdigest() + " BYTES " + str(len(raw)))
        encoded = base64.b64encode(gzip.compress(raw, mtime=0)).decode()
        print("BEGIN gzip+base64")
        for i in range(0, len(encoded), 4000):
            print(encoded[i:i + 4000])
        print("END gzip+base64")
        return 0

    if args.mode == "smoke":
        if args.seed in W.PRIOR_SEEDS.values() or args.seed == W.SEED or args.replicates > 50:
            raise SystemExit("REFUSED: a smoke may not use the formal or a closed seed and runs at most 50 replicates")
        result = W.run_calibration({**spec, "seed": args.seed}, workers=args.workers, replicates=args.replicates)
        print(json.dumps({"runClass": "DEVELOPMENT_ONLY_NO_VERDICT", "cells": len(result["cells"]), "seed": args.seed,
                          "replicates": args.replicates}, indent=2))
        return 0

    if args.mode == "reproduce":
        committed = json.loads((ROOT / W.RESULT_PATH).read_text())
        if committed["specSha256"] != sha:
            raise SystemExit("REPRODUCTION_REFUSED: the committed result is not this spec's")
        index = {(c["dgp"], str(c["horizonSessions"]), c["calendarWeeks"]): c for c in committed["result"]["cells"]}
        bad = []
        for d, dgp in enumerate(spec["dgps"]):
            for horizon, weeks in REPRODUCTION_UNITS:
                cell = W.run_cell(spec, d, int(horizon), weeks)
                if json.dumps(cell, sort_keys=True) != json.dumps(index[(dgp["name"], horizon, weeks)], sort_keys=True):
                    bad.append(f"{dgp['name']} H{horizon} {weeks}w")
        print(json.dumps({"reproduced": not bad, "mismatches": bad, "cellsChecked": len(spec["dgps"]) * len(REPRODUCTION_UNITS)}, indent=2))
        return 0 if not bad else 1

    started = time.time()
    try:
        result = W.run_calibration(spec, workers=args.workers, progress=lambda c: print(
            f"{c['dgp']} H{c['horizonSessions']} {c['calendarWeeks']}w {c['status']}", flush=True))
        document = {"studyId": W.STUDY, "runClass": "FORMAL", "specSha256": sha, "seed": spec["seed"],
                    "simulationReplicates": spec["simulationReplicates"], "environment": environment(),
                    "wallSeconds": None, "result": result}
    except Exception as error:  # an infrastructure failure is a recorded state, never a verdict
        document = {"studyId": W.STUDY, "runClass": "FORMAL", "specSha256": sha, "result": {"primaryStatus": "INFRASTRUCTURE_ERROR"},
                    "error": type(error).__name__ + ": " + str(error)[:400]}
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    timing = {"wallSeconds": round(time.time() - started, 1)}
    output.write_text(canonical({k: v for k, v in document.items() if k != "wallSeconds"}))
    (output.with_suffix(".timing.json")).write_text(json.dumps(timing) + "\n")
    status = document["result"]["primaryStatus"]
    print("PRIMARY_STATUS", status, "CLAIMS", json.dumps({k: v["verdict"] for k, v in document["result"].get("claims", {}).items()}))
    return 1 if status == "INFRASTRUCTURE_ERROR" else 0


if __name__ == "__main__":
    raise SystemExit(main())
