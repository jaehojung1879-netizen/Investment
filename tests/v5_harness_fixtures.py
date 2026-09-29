"""Synthetic KR world for the v5 execution-harness tests. No real price, ledger row or outcome is read.

The features of the LEAKY world carry the realised forward return by construction, purely so that the
PASS path of the plumbing can be exercised. Nothing here says anything about any real signal.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline import alpha_opportunity_v5_execution as X
from pipeline import alpha_opportunity_v5_spec as S5
from pipeline import regional_alpha_features as SOURCES
from pipeline import replay_calendar as RC

BENCH = "069500.KS"
SPEC_SHA = "d0f1aaf50d9629ba2f8a0a9802cd4ebd653018028ee97b2746f9e50703741e75"
DAYS = RC.sessions("2012-01-01", "2027-12-31", "KR")
CALIBRATION = {"critical": 66.57, "tolerance": 1e-12}
_SPEC = None


def sealed_spec():
    global _SPEC
    if _SPEC is None:
        _SPEC = S5.load_sealed(expected_hash=SPEC_SHA)
    return _SPEC


def runtime(cutoff="2022-12-30", depth=None, replicates=5):
    rt = X.build_runtime_spec(sealed_spec())
    rt["dataCutoff"] = cutoff
    rt["minimumConfirmatoryDepth"] = depth or {"21": 30, "126": 60}
    rt["uncertainty"] = {**rt["uncertainty"], "replicates": replicates}
    return rt


def make_world(seed=7, n=14, leak=True, cutoff="2022-12-30", sign=1.0):
    rng = np.random.default_rng(seed)
    idx = DAYS[(DAYS >= "2012-06-01") & (DAYS <= "2023-06-30")]
    tickers = [f"{100000 + i}.KS" for i in range(n)]
    close = {}
    for name in tickers + [BENCH]:
        sigma = 0.008 if name == BENCH else 0.02
        close[name] = 10000 * np.cumprod(1 + rng.normal(0.0004, sigma, len(idx)))
    prices = {name: pd.DataFrame({"Close": c, "Volume": rng.integers(1000, 9000, len(idx)).astype(float)}, index=idx)
              for name, c in close.items()}
    position = {d: i for i, d in enumerate(idx)}
    rows = []
    for date in SOURCES.weekly_grid("2013-01-01", cutoff, "KR"):
        start = int(idx.searchsorted(pd.Timestamp(date), side="right"))
        for t in tickers:
            row = {"date": date, "region": "KR", "ticker": t}
            for name in ("relative126", "logVolumeShock60", "shockPersistence5d", "volumePriceAlignment",
                         "assetGrowthPct", "debtGrowthPct"):
                row[name] = float(rng.normal())
            for name, h in (("acceleration21", 21), ("vol63", 126)):
                noise = float(rng.normal(0, 0.05 if h == 21 else 0.1))
                if leak and start + h < len(idx):
                    fwd = (close[t][start + h] / close[t][start] - 1) - (close[BENCH][start + h] / close[BENCH][start] - 1)
                    row[name] = sign * float(fwd) + noise
                else:
                    row[name] = noise
            rows.append(row)
    return {"frame": pd.DataFrame(rows), "prices": prices, "position": position, "cutoff": cutoff}


def run_world(world, *, mode=X.FORMAL, spec=None, rt=None, guard=None, counters=None, shuffle=False,
              attempt="test", frame_mutator=None):
    spec = spec or sealed_spec()
    rt = rt or runtime(world["cutoff"])
    if guard is None:
        guard = X.IdentityGuard({"constant": lambda: "fixed"})
        guard.freeze()

    def prepare():
        frame = world["frame"].copy()
        if frame_mutator:
            frame = frame_mutator(frame)
        prices = world["prices"]
        if shuffle:
            frame = frame.sample(frac=1.0, random_state=3).reset_index(drop=True)
            prices = {k: prices[k] for k in reversed(list(prices))}
        return X.attach_tradability(frame, prices, rt), prices, {}, []

    return X.run_execution(spec=spec, spec_sha=SPEC_SHA, runtime_spec=rt, prepare=prepare, guard=guard,
                           calibration=CALIBRATION, mode=mode, provenance={"attempt": {"attemptId": attempt}},
                           counters=counters, sessions=DAYS)
