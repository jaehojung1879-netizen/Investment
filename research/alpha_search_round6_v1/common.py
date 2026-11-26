"""Shared statistics for the round-6 batch (see PREREGISTRATION.md): block bootstrap with a one-sided p, Holm, judgement."""
from __future__ import annotations

import numpy as np

B = 4000
SEED = 20261116
MDD_BAND = 1.10


def boot(v, block, draws=B, seed=SEED):
    """Moving-block bootstrap of the mean: 95% percentile interval and one-sided p for mean <= 0."""
    v = np.asarray(v, float)
    n = len(v)
    out = {"n": int(n), "mean": float(v.mean()) if n else None,
           "sd": float(v.std(ddof=1)) if n > 1 else None,
           "ir": float(v.mean() / v.std(ddof=1)) if n > 1 and v.std(ddof=1) > 0 else None,
           "winRate": float((v > 0).mean()) if n else None, "blockWeeks": int(block), "independentBlocks": round(n / block, 1)}
    if n < 2 * block:
        out.update(ci=None, pOneSided=None, note="FEWER_THAN_TWO_BLOCKS")
        return out
    rng = np.random.default_rng(seed)
    starts = np.arange(n - block + 1)
    k = int(np.ceil(n / block))
    means = np.empty(draws)
    for i in range(draws):
        s = rng.choice(starts, size=k)
        idx = (s[:, None] + np.arange(block)[None, :]).ravel()[:n]
        means[i] = v[idx].mean()
    out.update(ci=[float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))],
               pOneSided=float((1 + (means <= 0).sum()) / (draws + 1)))
    if out["independentBlocks"] < 5:
        out["note"] = "FEWER_THAN_FIVE_INDEPENDENT_BLOCKS_DESCRIPTIVE_ONLY"
    return out


def holm(ps: dict) -> dict:
    """Holm step-down adjusted p-values; a missing p is a p = 1 slot."""
    items = sorted(((p if p is not None else 1.0), k) for k, p in ps.items())
    m, run, out = len(items), 0.0, {}
    for i, (p, k) in enumerate(items):
        run = max(run, min(1.0, (m - i) * p))
        out[k] = run
    return out


def judge(c: dict, p_holm: float) -> dict:
    """c: {'full': mean, 'halves': [m1, m2], 'l26Excess', 'l26Mdd', 'etfMdd', 'exSemiLed' (KR only or None)}."""
    checks = {
        "fullPositive": c["full"] is not None and c["full"] > 0,
        "significantAfterHolm": p_holm < 0.05,
        "bothHalvesPositive": all(h is not None and h > 0 for h in c["halves"]),
        "l26ExcessPositive": c["l26Excess"] is not None and c["l26Excess"] > 0,
        "l26DrawdownWithinBand": c["l26Mdd"] is not None and c["l26Mdd"] >= MDD_BAND * c["etfMdd"],
    }
    if c.get("exSemiLed", "NA") != "NA":
        checks["exSemiLedPositive"] = c["exSemiLed"] is not None and c["exSemiLed"] > 0
    rest = [v for k, v in checks.items() if k != "significantAfterHolm"]
    verdict = ("ALPHA_CANDIDATE" if all(checks.values()) else "DIRECTIONAL_ONLY" if all(rest) else "NOT_SUPPORTED")
    return {"checks": checks, "holmP": p_holm, "verdict": verdict}
