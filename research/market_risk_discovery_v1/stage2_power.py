"""Stage 2 power and size of the frozen P1 design. NO real credit value and NO real price feature meets any label.

What is real here: the sample STRUCTURE only -- which month-ends are FAST-normal risk-set decisions, their labels and
episode ids (all published in Stage 1), and the FAST state of every month-end (price side). What is synthetic:

* gap and vol: iid N(0, 1) noise, so M1 carries no information (the power below is therefore an UPPER bound with
  respect to M1 absorbing part of the credit information).
* the credit flag: top 20% of a latent Gaussian AR(1) with phi = 0.8 (matches the real flag's lag-1 autocorrelation
  0.55 at a 20% rate, signal-only statistics), shifted up by GAMMA_FAST in months where FAST != 0 so that the flag is
  rarer in FAST-normal months (real: about 10%), and by DELTA in the 126 sessions before each episode start (the
  planted effect). DELTA = 0 is the size check.

For each DELTA, the full frozen primary pipeline (walk-forward, rotation null, block bootstrap, leave-one-episode-out,
verdict) runs on every replication; reported are the rejection rate of the rotation test, the rate of the
EXPLORATORY_INCREMENTAL_SUPPORT verdict, and the effect size in interpretable units (relative risk of a positive label
given the flag among evaluation rows, and the per-episode hit probability), all from the synthetic worlds.

    python -m research.market_risk_discovery_v1.stage2_power [--reps 200]
"""
from __future__ import annotations

import argparse
import json
import functools
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from . import panels as P
from . import stage2_design as D

HERE = Path(__file__).resolve().parent
PHI, RATE = 0.8, 0.20
TARGET_NORMAL_RATE = 0.10
DELTAS = (0.0, 0.5, 1.0, 1.5, 2.5)
SEED = 20261124


@functools.lru_cache(maxsize=1)
def structure() -> dict:
    c = P.common_rows("presence")
    price = P.price_side()
    seq_idx = [i for i, _ in c["flagSequence"]]
    fast = np.array([price["fast"][i] for i in seq_idx])
    starts = np.array(sorted(c["starts"].values()))
    pre = np.array([bool(np.any((starts > i) & (starts - i <= D.HORIZON))) for i in seq_idx])
    return {"common": c, "seqIdx": seq_idx, "fastNonNormal": fast != 0, "preWindow": pre}


def synthetic_flags(rng, n, fast_non_normal, pre, gamma, delta):
    e = rng.normal(size=n)
    z = np.empty(n)
    z[0] = e[0]
    for t in range(1, n):
        z[t] = PHI * z[t - 1] + np.sqrt(1 - PHI ** 2) * e[t]
    z = z + gamma * fast_non_normal + delta * pre
    return (z > np.quantile(z, 1 - RATE)).astype(float)


def calibrate_gamma(s, rng) -> float:
    rows = s["common"]["rows"]
    seq = s["seqIdx"]
    where = {i: j for j, i in enumerate(seq)}
    common = np.array([where[r.idx] for r in rows])
    best = None
    for g in np.arange(0.0, 2.01, 0.05):
        rates = [synthetic_flags(rng, len(seq), s["fastNonNormal"], s["preWindow"], g, 0.0)[common].mean() for _ in range(200)]
        err = abs(np.mean(rates) - TARGET_NORMAL_RATE)
        if best is None or err < best[1]:
            best = (float(g), err, float(np.mean(rates)))
    return best


def one(args):
    delta, gamma, seed = args
    s = structure()
    c = s["common"]
    rng = np.random.default_rng(seed)
    flags = synthetic_flags(rng, len(s["seqIdx"]), s["fastNonNormal"], s["preWindow"], gamma, delta)
    fmap = dict(zip(s["seqIdx"], flags))
    rows = [D.Row(r.idx, r.date, float(rng.normal()), float(rng.normal()), float(fmap[r.idx]), r.y, r.episode)
            for r in c["rows"]]
    p = D.Panel(rows)
    refits = D.refit_points(c["monthEnds"])
    seq = list(zip(s["seqIdx"], flags))
    res = D.primary(p, refits, seq)
    y, preds = res["y"], res["preds"]
    dser = D.brier(preds["M1"], y) - D.brier(preds["M2"], y)
    ev = D.evaluation_mask(p, res["structure"]["start"])
    boot = D.block_bootstrap_ci(dser)
    loeo = D.leave_one_episode_out(dser, p.episode[ev], y)
    v = D.verdict(res["dBrier"], res["rotationP"], loeo)
    f = p.X[ev, 2]
    rr = (y[f == 1].mean() / y[f == 0].mean()) if (f == 1).any() and (f == 0).any() and y[f == 0].mean() > 0 else None
    hits = D.event_metrics(p, res["structure"]["start"], p.X[:, 2], c["starts"])
    return {"dBrier": res["dBrier"], "p": res["rotationP"], "verdict": v, "rr": rr, "bootLoPositive": boot["lo"] > 0,
            "loeoAllPositive": all(x > 0 for x in loeo.values()),
            "hitShare": hits["hits"] / hits["evaluationEpisodes"], "flagRateEval": float(f.mean())}


def run(reps: int, workers: int = 4) -> dict:
    s = structure()
    gamma, err, normal_rate = calibrate_gamma(s, np.random.default_rng(SEED))
    out = {"design": "stage2_design.primary + bootstrap + LOEO + verdict, synthetic credit and price features",
           "phi": PHI, "flagRate": RATE, "gammaFast": gamma, "flagRateInCommonSampleAtDelta0": normal_rate,
           "reps": reps, "seed": SEED, "byDelta": {}}
    jobs = [(d, gamma, SEED + 1000 * k + r) for k, d in enumerate(DELTAS) for r in range(reps)]
    with ProcessPoolExecutor(workers) as pool:
        res = list(pool.map(one, jobs, chunksize=4))
    for k, d in enumerate(DELTAS):
        chunk = res[k * reps:(k + 1) * reps]
        rr = [x["rr"] for x in chunk if x["rr"] is not None]
        out["byDelta"][str(d)] = {
            "rotationRejectRate": float(np.mean([x["p"] <= D.ALPHA for x in chunk])),
            "supportVerdictRate": float(np.mean([x["verdict"] == "EXPLORATORY_INCREMENTAL_SUPPORT" for x in chunk])),
            "positiveDBrierRate": float(np.mean([x["dBrier"] > 0 for x in chunk])),
            "bootstrapLowerBoundPositiveRate": float(np.mean([x["bootLoPositive"] for x in chunk])),
            "leaveOneEpisodeOutAllPositiveRate": float(np.mean([x["loeoAllPositive"] for x in chunk])),
            "rotationAndLoeoRate": float(np.mean([x["p"] <= D.ALPHA and x["loeoAllPositive"] for x in chunk])),
            "rotationAndBootstrapRate": float(np.mean([x["p"] <= D.ALPHA and x["bootLoPositive"] for x in chunk])),
            "medianRelativeRisk": float(np.median(rr)) if rr else None,
            "relativeRiskIQR": [float(np.quantile(rr, 0.25)), float(np.quantile(rr, 0.75))] if rr else None,
            "meanEpisodeHitShare": float(np.mean([x["hitShare"] for x in chunk])),
            "meanEvalFlagRate": float(np.mean([x["flagRateEval"] for x in chunk])),
            "medianDBrier": float(np.median([x["dBrier"] for x in chunk]))}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=200)
    a = ap.parse_args()
    out = run(a.reps)
    (HERE / "evidence" / "stage2-power.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
