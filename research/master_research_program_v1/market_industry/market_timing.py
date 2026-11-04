"""Exact LEVEL / TIMING decomposition of an exposure overlay against its ETF. Pure: no I/O, no data, no fit.

Per period t (here: one weekly execution-to-execution interval) an overlay holds exposure x_t in the equity ETF and 1 - x_t in the
cash asset, so

    R_overlay,t = x_t R_E,t + (1 - x_t) R_F,t,          R_overlay,t - R_E,t = (x_t - 1)(R_E,t - R_F,t).

With xbar = mean(x_t) and e_t = R_E,t - R_F,t:

    LEVEL  = (xbar - 1) * mean(e_t)                       -- what a CONSTANT exposure xbar would have earned against the ETF
    TIMING = mean((x_t - xbar) * e_t)                     -- what MOVING the exposure earned at the same average exposure
    mean(R_overlay,t - R_E,t) = LEVEL + TIMING            -- an identity, asserted on every call

(A) risk reduction by holding less equity on average is the LEVEL term and the drawdown of the exposure-matched static control
(constant xbar); (B) value added by dynamic allocation is the TIMING term = mean(R_overlay,t - R_static,t) and the drawdown of the
overlay against that same static control. A lower drawdown than the ETF is NOT evidence of (B) unless it beats the static control.

Costs of exposure changes are a separate, explicit term: COST_t = stress * (buy * max(dx_t, 0) + sell * max(-dx_t, 0)), the first
period's build uncharged (the sealed `kr_market_risk_model.replay_path` convention), so mean(net overlay - ETF) = LEVEL + TIMING - COST.
The static control pays nothing after its build. Within-period drift of a held exposure is not modelled here; a recorder that replays
the drifting path reports the difference as a residual rather than folding it into TIMING.

`exposure_at` is the no-look-ahead accessor: only states dated <= t are ever read. Multipliers come from the sealed
`kr_market_risk_model` by import (`multiplier`, `candidate_targets`), never restated.
"""
from __future__ import annotations

import bisect
import math
from datetime import date, datetime

import numpy as np

IDENTITY_TOLERANCE = 1e-12


def _array(values, name):
    arr = np.asarray(values, dtype=float)
    if arr.ndim != 1 or arr.size == 0:
        raise ValueError("EMPTY_OR_NOT_1D: " + name)
    if not np.all(np.isfinite(arr)):
        raise ValueError("NON_FINITE: " + name)
    return arr


def overlay_returns(x, r_e, r_f):
    x, r_e, r_f = _array(x, "x"), _array(r_e, "r_e"), _array(r_f, "r_f")
    if not (x.size == r_e.size == r_f.size):
        raise ValueError("LENGTH_MISMATCH")
    return x * r_e + (1.0 - x) * r_f


def exposure_change_costs(x, buy_cost, sell_cost, stress=1.0):
    """Per-period cost fraction of moving the exposure to x_t from x_{t-1}; period 0 (the build) is uncharged."""
    x = _array(x, "x")
    dx = np.diff(x, prepend=x[0])
    return stress * (buy_cost * np.clip(dx, 0.0, None) + sell_cost * np.clip(-dx, 0.0, None))


def nav(returns):
    return np.cumprod(1.0 + _array(returns, "returns"))


def max_drawdown(returns):
    """Most negative peak-to-trough of the NAV path (start NAV 1 counts as a peak); 0.0 for a path that never falls."""
    path = np.concatenate([[1.0], nav(returns)])
    peak = np.maximum.accumulate(path)
    return float(np.min(path / peak - 1.0))


def newey_west_mean(series, lag):
    """Mean, Bartlett-kernel HAC standard error at an explicit lag (in observations of this series), and n."""
    z = _array(series, "series")
    n = z.size
    lag = int(lag)
    if lag < 0:
        raise ValueError("NEGATIVE_LAG")
    mu = float(z.mean())
    c = z - mu
    lr = float(c @ c) / n
    for k in range(1, min(lag, n - 1) + 1):
        lr += 2.0 * (1.0 - k / (lag + 1.0)) * float(c[k:] @ c[:-k]) / n
    se = math.sqrt(max(lr, 0.0) / n) if n > 1 else None
    return {"mean": mu, "se": se, "n": n, "lag": lag}


def decompose(x, r_e, r_f, buy_cost=0.0, sell_cost=0.0, stress=1.0):
    """The exact decomposition plus the exposure-matched static control and both drawdowns. Raises if the identity fails."""
    x, r_e, r_f = _array(x, "x"), _array(r_e, "r_e"), _array(r_f, "r_f")
    r_ov = overlay_returns(x, r_e, r_f)
    xbar = float(x.mean())
    e = r_e - r_f
    level = (xbar - 1.0) * float(e.mean())
    timing_terms = (x - xbar) * e
    timing = float(timing_terms.mean())
    active = float((r_ov - r_e).mean())
    if abs(active - (level + timing)) > IDENTITY_TOLERANCE * max(1.0, abs(active)):
        raise AssertionError("DECOMPOSITION_IDENTITY_FAILED")
    r_static = xbar * r_e + (1.0 - xbar) * r_f
    if abs(float((r_ov - r_static).mean()) - timing) > IDENTITY_TOLERANCE * max(1.0, abs(timing)):
        raise AssertionError("STATIC_CONTROL_IDENTITY_FAILED")
    cost = exposure_change_costs(x, buy_cost, sell_cost, stress)
    r_net = r_ov - cost
    return {
        "periods": int(x.size), "averageExposure": xbar, "exposureChanges": int(np.count_nonzero(np.diff(x))),
        "meanActiveGross": active, "level": level, "timing": timing, "meanCost": float(cost.mean()),
        "timingNetOfCost": timing - float(cost.mean()), "meanActiveNet": float((r_net - r_e).mean()),
        "timingSeries": timing_terms, "netTimingSeries": timing_terms - cost,
        "maxDrawdown": {"etf": max_drawdown(r_e), "overlayGross": max_drawdown(r_ov), "overlayNet": max_drawdown(r_net),
                        "staticControl": max_drawdown(r_static)},
        "stress": stress,
    }


def classify_reading(timing_lower, timing_upper, mdd_overlay, mdd_static, mdd_etf, level):
    """Which of (A) and (B) a reading supports. Drawdowns are negative numbers; a higher number is a shallower drawdown."""
    if timing_lower > 0:
        return "B_TIMING_SUPPORTED"
    if timing_upper < 0:
        return "TIMING_NEGATIVE"
    if mdd_static > mdd_etf and level < 0 and not mdd_overlay > mdd_static:
        return "A_ONLY_LEVEL_RISK_REDUCTION"
    return "NO_TIMING_EVIDENCE_INTERVAL_CONTAINS_ZERO"


def _key(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def exposure_at(states, t):
    """The exposure of the latest state dated <= t, or None. `states` is an iterable of (date, exposure). A state dated after t is
    never read, so appending future states cannot change any past answer. Duplicate dates are refused."""
    rows = sorted((_key(d), float(v)) for d, v in states)
    days = [d for d, _ in rows]
    if len(set(days)) != len(days):
        raise ValueError("DUPLICATE_STATE_DATE")
    i = bisect.bisect_right(days, _key(t))
    return rows[i - 1][1] if i else None


def exposure_path(states, period_starts):
    """x_t for each period start, each read with `exposure_at` (None where no state is yet known)."""
    return [exposure_at(states, t) for t in period_starts]


def sealed_multiplier(candidate, slow, transition, fast):
    """The sealed KR market risk model multiplier (C0..C3), by import; None when the missing layers could change it."""
    from pipeline import kr_market_risk_model as K
    return K.multiplier(candidate, slow, transition, fast)


def sealed_mapping_table(candidate):
    from pipeline import kr_market_risk_model as K
    return K.mapping_table(candidate)
