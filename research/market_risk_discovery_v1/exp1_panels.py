"""Experiment 1 rows from the Stage 1 inputs (reused unchanged through `panels`) plus the preserved FRED VIX/VIX3M.

`mode="presence"` replaces every credit and VIX VALUE by 0.0 where it is defined, so the sample structure can be
measured without any signal value meeting a label. `mode="signal"` keeps the values and drops every label (y and
episode are None). Only the experiment-1 harness asks for `mode="real"`.
"""
from __future__ import annotations

import numpy as np

from . import baseline_census as B
from . import exp1_inputs as I
from . import panels as P

MAX_STALE_DAYS = 5


def credit_z() -> dict[str, float]:
    """Continuous companion of the P1 flag: the same as-of 3-month change, z-scored on the expanding history of all
    strictly earlier defined changes (>= 12), never thresholded."""
    credit = B.credit_series()
    keys = sorted(credit)
    vals = [credit[k] for k in keys]
    ch = [None if i < P.WIDEN_LAG or vals[i] is None or vals[i - P.WIDEN_LAG] is None else vals[i] - vals[i - P.WIDEN_LAG]
          for i in range(len(keys))]
    out = {}
    for i, k in enumerate(keys):
        hist = [c for c in ch[:i] if c is not None]
        if ch[i] is None or len(hist) < P.MIN_HISTORY:
            continue
        sd = float(np.std(hist, ddof=1))
        if sd > 0:
            out[k] = (ch[i] - float(np.mean(hist))) / sd
    return out


def close_on_or_before(series: dict[str, float], date: str) -> float | None:
    """Close at the decision date, or the latest close within MAX_STALE_DAYS before it; never a later one."""
    import datetime as dt
    d = dt.date.fromisoformat(date)
    for k in range(MAX_STALE_DAYS + 1):
        v = series.get((d - dt.timedelta(days=k)).isoformat())
        if v is not None:
            return v
    return None


def rows(mode: str) -> dict:
    if mode not in ("presence", "signal", "real"):
        raise ValueError(mode)
    price, events = P.price_side(), P.event_side()
    dates = price["dates"]
    me = P.month_end_index(dates)
    flag = dict(P.credit_side())
    cz = credit_z()
    vix, vxv = I.load("VIXCLS"), I.load("VXVCLS")
    out = []
    for m, k in sorted(me.items(), key=lambda x: x[1]):
        d = dates[k]
        if d < P.FIRST_DECISION or events["active"][k] or price["fast"][k] != 0:
            continue
        v, v3 = close_on_or_before(vix, d), close_on_or_before(vxv, d)
        feat = {"flag": flag.get(m), "credit_z": cz.get(m), "vix": None if v is None else v / 100.0,
                "vix_slope": None if (v is None or v3 is None) else v / v3 - 1.0}
        if mode == "presence":
            feat = {f: (None if x is None else 0.0) for f, x in feat.items()}
        labelled = mode != "signal"
        out.append({"idx": k, "date": d, "gap": price["gap"][k], "vol": price["vol"][k], **feat,
                    "y": events["y"][k] if labelled else None, "episode": events["episode"][k] if labelled else None})
    from . import stage2_design as D  # noqa: PLC0415
    return {"rows": out, "refits": D.refit_points([(dates[k], k) for k in sorted(me.values())]),
            "starts": events["starts"]}
