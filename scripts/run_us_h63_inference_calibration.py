"""Run the frozen US H63 inference calibration (synthetic only; reads no market data).

    python scripts/run_us_h63_inference_calibration.py [--workers 4] [--output PATH]
    python scripts/run_us_h63_inference_calibration.py --smoke 20      # DEVELOPMENT_ONLY: fewer replicates, never a result

Every replicate is seeded by SeedSequence([seed, dgp index, weeks, replicate(, effect index)]), so the result does not depend on
the worker count or on scheduling. The protocol file must carry status FROZEN_BEFORE_ANY_REPLICATE.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import alpha_inference_mc_decision as mc     # noqa: E402
from pipeline import us_h63_inference_calibration as U      # noqa: E402

PROTOCOL = ROOT / "docs/us-readiness/us-h63-inference-calibration-v1-protocol.json"
OUTPUT = ROOT / "docs/us-readiness/us-h63-inference-calibration-v1-result.json"


def _job(args):
    protocol, dgp_index, weeks, rep, effect_index, effect, interim = args
    geometry, dgp = U.resolve_dgp(protocol, protocol["dgps"][dgp_index])
    key = (int(protocol["seed"]), dgp_index, weeks, rep) + ((effect_index,) if effect_index is not None else ())
    return U.replicate_intervals(geometry, dgp, weeks=weeks, seed_key=key, methods_cfg=protocol["methods"],
                                 effect_annual=effect, interim_weeks=interim)


def _run(pool, jobs):
    return list(pool.map(_job, jobs, chunksize=max(1, len(jobs) // 64)))


def _mean_ci(values):
    a = np.array([v for v in values if v is not None], dtype=float)
    if len(a) < 2:
        return None
    se = a.std(ddof=1) / np.sqrt(len(a))
    return {"mean": float(a.mean()), "mc95": [float(a.mean() - 1.96 * se), float(a.mean() + 1.96 * se)], "n": int(len(a))}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--smoke", type=int, help="DEVELOPMENT_ONLY replicate count; output is labelled and never a result")
    args = parser.parse_args(argv)
    raw = PROTOCOL.read_bytes()
    protocol = json.loads(raw)
    if protocol.get("status") != "FROZEN_BEFORE_ANY_REPLICATE" or protocol.get("contract") != U.CONTRACT:
        raise SystemExit("PROTOCOL_NOT_FROZEN")
    reps = args.smoke or int(protocol["replicates"])
    power_reps = args.smoke or int(protocol["power"]["replicates"])
    acceptance, mc_cfg = protocol["acceptance"], protocol["monteCarloDecision"]
    count = int(mc_cfg["failSideDecisionCount"])
    started = time.time()
    cells, power, futility = [], [], []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for i, dgp in enumerate(protocol["dgps"]):
            for weeks in protocol["sampleLengths"]["weeks"]:
                interim = 130 if weeks == 260 else None
                records = _run(pool, [(protocol, i, weeks, r, None, 0.0, interim) for r in range(reps)])
                decisions = {m: U.decide(records, m, 0.0, acceptance, mc_cfg, count) for m in U.METHODS}
                cell = {"dgp": dgp["name"], "gating": bool(dgp["gating"]), "weeks": weeks,
                        "primaryState": decisions[U.PRIMARY_METHOD]["state"],
                        "methods": decisions,
                        "nullEstimate": _mean_ci([r["_estimate"] for r in records]),
                        "meanDefinedDateFraction": float(np.mean([r["_definedFraction"] for r in records])),
                        "meanWithinReplicateSdOfS": float(np.mean([r["_sdOfS"] for r in records if r["_sdOfS"] is not None]))}
                if interim:
                    cell["futilityStopUnderNull"] = float(np.mean([(r["_interimEstimate"] is not None and r["_interimEstimate"] <= 0)
                                                                   for r in records]))
                cells.append(cell)
                print("%-26s %4d  CT_SN %-12s %6.0fs" % (dgp["name"], weeks, cell["primaryState"], time.time() - started), flush=True)
        names = [d["name"] for d in protocol["dgps"]]
        for name in protocol["power"]["dgps"]:
            i = names.index(name)
            for weeks in protocol["power"]["weeks"]:
                for e_idx, effect in enumerate(protocol["power"]["effectsAnnual"]):
                    interim = 130 if weeks == 260 else None
                    records = _run(pool, [(protocol, i, weeks, r, e_idx, effect, interim) for r in range(power_reps)])
                    row = {"dgp": name, "weeks": weeks, "effectAnnual": effect,
                           "realisedThetaPerH63": _mean_ci([r["_effectTheta"] for r in records])}
                    for m in U.METHODS:
                        rows = [r[m] for r in records if r[m] is not None]
                        k = sum(1 for r in rows if r["lower"] > 0)
                        row[m] = {"power": k / len(rows) if rows else None, "n": len(rows),
                                  "cp95": [mc.clopper_pearson_lower(k, len(rows), 0.025), mc.clopper_pearson_upper(k, len(rows), 0.025)]}
                    power.append(row)
                    if interim:
                        stop = [r["_interimEstimate"] is not None and r["_interimEstimate"] <= 0 for r in records]
                        success = [r[U.PRIMARY_METHOD] is not None and r[U.PRIMARY_METHOD]["lower"] > 0 for r in records]
                        futility.append({"dgp": name, "effectAnnual": effect,
                                         "pStopAtInterim": float(np.mean(stop)),
                                         "powerIgnoringFutility": float(np.mean(success)),
                                         "powerWithNonBindingStopFollowed": float(np.mean([s and not t for s, t in zip(success, stop)]))})
                    print("power %-18s %4d %.2f %6.0fs" % (name, weeks, effect, time.time() - started), flush=True)

    gating = [c for c in cells if c["gating"]]
    required = [c for c in gating if c["weeks"] in (260, 700)]
    p3 = "PASS" if required and all(c["primaryState"] == mc.PASS for c in required) else "BLOCKED"
    at130 = [c for c in gating if c["weeks"] == 130]
    result = {
        "contract": U.CONTRACT, "evidenceClass": "SYNTHETIC_INFERENCE_CALIBRATION_NOT_INVESTMENT_PERFORMANCE",
        "developmentOnly": bool(args.smoke), "protocolSha256": hashlib.sha256(raw).hexdigest(),
        "replicates": reps, "powerReplicates": power_reps,
        "p3Status": p3 if not args.smoke else "DEVELOPMENT_SMOKE_NOT_A_RESULT",
        "primaryMethod": U.PRIMARY_METHOD,
        "intervalQuotableAt130Weeks": bool(at130) and all(c["primaryState"] == mc.PASS for c in at130),
        "cells": cells, "power": power, "futilityOperatingCharacteristics": futility,
        "readsRealData": False,
    }
    out = args.output if not args.smoke or args.output != OUTPUT else args.output.with_name("us-h63-inference-calibration-v1-SMOKE.json")
    out.write_text(json.dumps(result, indent=1, sort_keys=True, allow_nan=False) + "\n")
    print("P3:", result["p3Status"], "->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
