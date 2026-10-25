"""Outcome-free null calibration diagnostic for the Industry Alpha bootstrap.

Synthetic month-level loss-differential proxies ONLY. No Git, historical prices,
returns, issuers, industry member data, or authorized outcome-reading path.
The registered evaluator/study constants are imported but NEVER modified.

This approximates dependence caused by overlapping H126/H252 labels. It is not
a full end-to-end calibration of paired OOF model fitting or multiple testing,
and it cannot authorize a change to a frozen hypothesis/specification.
"""
from __future__ import annotations

import argparse
import json
import math

import numpy as np

from . import evaluate as E
from . import study as S

NOMINAL_ALPHA = 0.05
DEFAULT_GRID = tuple((n, overlap, ar) for overlap in (1, 6, 12)
                     for ar in (0.0, 0.5) for n in (48, 96, 144))


def _synthetic_null(rng, n, overlap, ar):
    """Zero-mean monthly MA(overlap-1) proxy, optionally with AR(1) shocks.

    The burn-in avoids an arbitrary first-month initialization. This procedure
    never consumes a real security or market series.
    """
    innovations = rng.standard_normal(n + overlap + 250)
    if ar:
        shocks = np.empty_like(innovations)
        shocks[0] = innovations[0]
        for t in range(1, len(shocks)):
            shocks[t] = ar * shocks[t - 1] + innovations[t]
    else:
        shocks = innovations
    return np.convolve(shocks, np.ones(overlap), mode="valid")[-n:]


def _wilson(count, total, z=1.96):
    """Approximate 95% Wilson binomial interval, not a calibration guarantee."""
    p = count / total
    den = 1.0 + z * z / total
    center = (p + z * z / (2.0 * total)) / den
    half = z * math.sqrt(p * (1.0 - p) / total + z * z / (4.0 * total * total)) / den
    return [max(0.0, center - half), min(1.0, center + half)]


def calibrate(*, replications=300, draws=399, seed=20261025, grid=DEFAULT_GRID):
    """Audit unchanged moving_block_bootstrap_p on zero-edge synthetic proxies.

    Every condition gets a distinct deterministic RNG stream. Test index draws
    use the same registered blockSignals and seed semantics as the evaluator.
    The result is diagnostic only: failure to show inflation is NOT a PASS.
    """
    if not isinstance(replications, int) or isinstance(replications, bool) or replications < 2:
        raise ValueError("INVALID_REPLICATIONS")
    if not isinstance(draws, int) or isinstance(draws, bool) or draws < 19:
        raise ValueError("INVALID_BOOTSTRAP_DRAWS")
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ValueError("INVALID_SEED")
    rows = []
    for i, (n, overlap, ar) in enumerate(grid):
        if not isinstance(n, int) or n < 2 or not isinstance(overlap, int) or not 1 <= overlap <= n:
            raise ValueError("INVALID_GRID_LENGTH")
        if not isinstance(ar, (int, float)) or isinstance(ar, bool) or not math.isfinite(ar) or abs(ar) >= 1:
            raise ValueError("INVALID_GRID_AUTOCORRELATION")
        rng = np.random.default_rng(seed + i * 100003)
        rejects = 0
        for _ in range(replications):
            d = _synthetic_null(rng, n, overlap, ar)
            p = E.moving_block_bootstrap_p(d, block=S.BOOTSTRAP["blockSignals"],
                                           draws=draws, seed=S.BOOTSTRAP["seed"])
            rejects += p <= NOMINAL_ALPHA
        interval = _wilson(rejects, replications)
        rows.append({"nMonthly": n, "overlapInnovations": overlap, "ar1": ar,
                     "replications": replications, "rejections": rejects,
                     "falsePositiveRate": rejects / replications,
                     "wilson95": interval,
                     "diagnosis": "ANTI_CONSERVATIVE" if interval[0] > NOMINAL_ALPHA
                                  else "INSUFFICIENT_TO_ESTABLISH_CALIBRATION"})
    return {"schema": "INDUSTRY_NULL_BOOTSTRAP_DIAGNOSTIC_V1",
            "scope": "SYNTHETIC_LOSS_DIFFERENTIAL_PROXY_ONLY",
            "registeredAlgorithmUnchanged": True,
            "historicalOutcomesRead": 0, "newHistoricalStudyExecuted": False,
            "status": "DIAGNOSTIC_NOT_VALIDATION",
            "nominalAlpha": NOMINAL_ALPHA, "bootstrapBlockSignals": S.BOOTSTRAP["blockSignals"],
            "bootstrapSeed": S.BOOTSTRAP["seed"], "draws": draws, "simulationSeed": seed,
            "warnings": ["Rolling synthetic returns are a dependence stress approximation, not actual paired OOF loss errors.",
                         "Overlapping labels, missing cohorts, yearly refits, and Holm family need a full end-to-end calibration.",
                         "No null-cell pass authorizes shorter support, a new bootstrap method, or historical outcomes."],
            "cells": rows}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--replications", type=int, default=300)
    p.add_argument("--draws", type=int, default=399)
    p.add_argument("--seed", type=int, default=20261025)
    args = p.parse_args(argv)
    print(json.dumps(calibrate(replications=args.replications, draws=args.draws, seed=args.seed),
                     indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
