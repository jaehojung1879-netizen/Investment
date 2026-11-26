"""Panels for the Stage 2 / Stage 3 P1 comparison, built from the Stage 1 preserved inputs only.

Three sides are built separately and joined only in `common_rows`:

* price side (signal): SPY split-adjusted raw close -> FAST state, gap to the 200-session mean, 63-session realised vol.
* credit side (signal): ALFRED as-of month-end BAA - GS10 -> WIDEN_3M_ABOVE_EXPANDING_P80, exactly Stage 1's rule.
* event side (label): SPY total return -> risk set, 126-session first-passage label, episode id (Stage 1's rule).

`flag_mode` decides what the credit side hands to the join:

* "presence"  every defined flag is replaced by 0.0. Used by Stage 2 readiness: the structure of the sample (which rows
               exist, which episodes they belong to) can be measured without any credit VALUE meeting any label.
* "real"      the real flag. Only the Stage 3 harness, after authorization, may ask for it together with labels.
"""
from __future__ import annotations

import numpy as np

from . import baseline_census as B
from . import label_census as L
from .stage2_design import Row

P80, MIN_HISTORY, WIDEN_LAG = 0.8, 12, 3
FIRST_DECISION = "1997-01-31"


def price_side() -> dict:
    dates, close = B.raw_close()
    ret = np.diff(np.log(close), prepend=np.nan)
    gap, vol = [None] * len(close), [None] * len(close)
    for t in range(199, len(close)):
        gap[t] = float(close[t] / close[t - 199:t + 1].mean() - 1.0)
        vol[t] = float(np.std(ret[t - 62:t + 1], ddof=1) * np.sqrt(252))
    return {"dates": dates, "fast": B.fast_state(close), "gap": gap, "vol": vol}


def credit_side() -> list[tuple[str, float]]:
    """(decision month, flag) for every month whose flag is defined. Identical arithmetic to Stage 1's
    `candidate_credit_flags['WIDEN_3M_ABOVE_EXPANDING_P80']`: as-of spread per decision month, 3-month change of the
    as-of values, flag = change > linear-interpolated 80th percentile of all strictly earlier defined changes, at least
    12 of them. Undefined (missing leg, month mismatch, too little history) is dropped, never filled."""
    credit = B.credit_series()
    keys = sorted(credit)
    vals = [credit[k] for k in keys]

    def change(i):
        if i < WIDEN_LAG or vals[i] is None or vals[i - WIDEN_LAG] is None:
            return None
        return vals[i] - vals[i - WIDEN_LAG]

    out = []
    for i, k in enumerate(keys):
        v = B._above_expanding(i, change, P80, MIN_HISTORY)
        if v is not None:
            out.append((k, 1.0 if v else 0.0))
    return out


def event_side() -> dict:
    dates, tr = L.load_tr()
    eps, active = L.episodes(dates, tr)
    y = L.labels(dates, active, eps)
    starts = {e["start"]: k for k, d in enumerate(dates) for e in eps if e["start"] == d}
    episode = [None] * len(dates)
    sidx = sorted(starts.values())
    for t in range(len(dates)):
        if y[t] == 1:
            episode[t] = dates[next(k for k in sidx if t < k <= t + L.HORIZON)]
    return {"dates": dates, "active": active, "y": y, "episode": episode, "starts": starts, "episodes": eps}


def month_end_index(dates: list[str]) -> dict[str, int]:
    return {dates[k][:7]: k for k in L.month_ends(dates)}


def common_rows(flag_mode: str) -> dict:
    if flag_mode not in ("presence", "real"):
        raise ValueError(flag_mode)
    price, events = price_side(), event_side()
    if price["dates"] != events["dates"]:
        raise RuntimeError("PRICE_AND_TOTAL_RETURN_CALENDARS_DIFFER")
    dates = price["dates"]
    me = month_end_index(dates)
    flags = {m: (0.0 if flag_mode == "presence" else v) for m, v in credit_side()}
    sequence = [(me[m], v) for m, v in sorted(flags.items()) if m in me]
    rows = []
    for m, k in sorted(me.items(), key=lambda x: x[1]):
        if dates[k] < FIRST_DECISION or events["active"][k] or price["fast"][k] != 0 or m not in flags:
            continue
        rows.append(Row(idx=k, date=dates[k], gap=price["gap"][k], vol=price["vol"][k], flag=flags[m],
                        y=events["y"][k], episode=events["episode"][k]))
    month_end_sessions = [(dates[k], k) for k in sorted(me.values())]
    return {"rows": rows, "flagSequence": sequence, "monthEnds": month_end_sessions, "starts": events["starts"],
            "episodes": events["episodes"], "lastSession": dates[-1]}
