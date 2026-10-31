"""POST-HOC mechanism diagnostic for the frozen inference calibration. Synthetic only; DEVELOPMENT seed.

Written AFTER the formal calibration result was read, to explain one feature of it: the registered bootstrap that the
proxy diagnostic (`null_calibration.py`, zero-mean MA series) found anti-conservative reads close to nominal size at
KR/H126 end to end, and is conservative at the 25-year length. The candidate explanation is that under the null the
alternative model's two extra columns cost out-of-fold accuracy, so the paired loss differential has a NEGATIVE mean
and a one-sided test of "alternative better" sits below its least-favourable null. This module measures that: the
mean and t-ratio of d under the null, and the registered test's rejection rate on each replicate's d shifted by the
CELL's mean loss differential (the cross-replicate average, an estimate of the population null mean), i.e. on a
series whose true mean is zero, as in the proxy's setting. That is the BOUNDARY of the one-sided null E[d] <= 0, which
the frozen protocol's no-information nulls never reach; the same shifted series is handed to every candidate, and
to a one-sided t on its test-year means (each year is one refit fold), with the share of variance those means carry.
The shift removes the overfitting penalty's MEAN but keeps its time structure; a genuine zero-gain alternative could
differ, so the boundary readings are an approximation.

It changes nothing in the frozen protocol, its result or its verdicts, and uses only the development seed.
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from . import evaluate as E
from . import inference_calibration as C

DGPS = ("N1_GAUSS_CONST", "N2_T4_VOL_REGIME")


def _one(args):
    protocol, dgp, length, horizon, replicate, seed = args
    rng = np.random.default_rng(np.random.SeedSequence([seed, 1000 + horizon, 0 if length == "KR" else 1,
                                                        DGPS.index(dgp), replicate]))
    frame, sessions = C.simulate_world(rng, protocol["dgps"][dgp], protocol["world"], horizon,
                                       protocol["lengths"][length]["firstSignalMonth"])
    base, alt = E.h1_columns(C.TESTED_BLOCK)
    pop, _ = E.admit(frame, "cwRelative", "cwStatus")
    pb, _ = E.oof_predictions(pop, base, "cwRelative", sessions, horizon)
    pa, _ = E.oof_predictions(pop, alt, "cwRelative", sessions, horizon)
    series = E.loss_differential(pop, "cwRelative", pb, pa)
    d = series.to_numpy(float)
    se = float(np.sqrt(C.bartlett_lrv(d, horizon // C.SESSIONS_PER_MONTH) / len(d)))
    return {"mean": float(d.mean()), "hacT": float(d.mean() / se) if se > 0 else 0.0,
            "rejectAsIs": E.moving_block_bootstrap_p(d) <= 0.05, "d": d.tolist(),
            "testYear": [str(x)[:4] for x in series.index]}


def fold_structure(d, years):
    """Share of the series' variance carried by its test-year (refit fold) means, and a one-sided t on those means."""
    from scipy import stats
    frame = np.asarray(d, float)
    keys = np.asarray(years)
    means = {y: frame[keys == y].mean() for y in dict.fromkeys(keys)}
    fitted = np.array([means[y] for y in keys])
    g = np.array(list(means.values()))
    share = float(np.var(fitted) / np.var(frame)) if np.var(frame) > 0 else 0.0
    if len(g) < 2 or g.std(ddof=1) == 0:
        return share, False, len(g)
    t = g.mean() / (g.std(ddof=1) / np.sqrt(len(g)))
    return share, bool(stats.t.sf(t, len(g) - 1) <= 0.05), len(g)


def _cell(protocol, dgp, length, horizon, replicates, seed, workers):
    jobs = [(protocol, dgp, length, horizon, r, seed) for r in range(replicates)]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        rows = list(ex.map(_one, jobs))
    means = np.array([r["mean"] for r in rows])
    mu = float(means.mean())
    shifted = [E.moving_block_bootstrap_p(np.asarray(r["d"]) - mu) <= 0.05 for r in rows]
    boundary = [C.decisions(np.asarray(r["d"]) - mu, protocol, horizon) for r in rows]
    folds = [fold_structure(np.asarray(r["d"]) - mu, r["testYear"]) for r in rows]
    return {"replicates": replicates, "dgp": dgp,
            "meanOfMeanLossDifferential": mu,
            "shareOfReplicatesWithNegativeMean": float((means < 0).mean()),
            "medianHacT": float(np.median([r["hacT"] for r in rows])),
            "registeredRejectionAsIs": float(np.mean([r["rejectAsIs"] for r in rows])),
            "registeredRejectionOnZeroTrueMeanSeries": float(np.mean(shifted)),
            "testYears": int(np.median([f[2] for f in folds])),
            "varianceShareOfTestYearMeans": float(np.mean([f[0] for f in folds])),
            "boundaryNullRejectionTestYearClusterT": float(np.mean([f[1] for f in folds])),
            "boundaryNullRejectionByCandidate": {c: float(np.mean([b[c]["reject"]["0.05"] for b in boundary]))
                                                 for c in C.CANDIDATES}}


def run(replicates=400, workers=4):
    protocol = C.load_protocol(formal=True)
    seed = protocol["seeds"]["development"]
    out = {}
    for dgp in DGPS:
        for length in ("KR", "LONG"):
            for horizon in (126, 252):
                out[f"{dgp}_{length}_H{horizon}"] = _cell(protocol, dgp, length, horizon, replicates, seed, workers)
    return {"schema": "INDUSTRY_INFERENCE_MECHANISM_DIAGNOSTIC_V1",
            "evidenceClass": "POST_HOC_SYNTHETIC_MECHANISM_DIAGNOSTIC_DEVELOPMENT_SEED",
            "writtenAfterFormalResultWasRead": True, "changesFrozenVerdict": False,
            "historicalOutcomesRead": 0, "seed": seed, "cells": out}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--replicates", type=int, default=400)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--output")
    args = ap.parse_args(argv)
    text = json.dumps(run(args.replicates, args.workers), indent=1, sort_keys=True)
    if args.output:
        with open(args.output, "w") as fh:
            fh.write(text + "\n")
    else:
        sys.stdout.write(text + "\n")


if __name__ == "__main__":
    main()
