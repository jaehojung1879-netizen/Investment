"""Past-only aggregate equity budget. Receives no stock identifiers or rankings."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import replay_calendar as RC


def state_at(benchmark, date):
    days = RC.sessions("2013-01-01", date, "KR")[-201:]
    if benchmark is None or "Close" not in benchmark or len(days) < 201:
        return {"status": "DATA_INSUFFICIENT", "riskMultiplier": None}
    close = pd.to_numeric(benchmark.Close.reindex(days), errors="coerce")
    if not np.isfinite(close.to_numpy()).all() or (close <= 0).any():
        return {"status": "DATA_INSUFFICIENT", "riskMultiplier": None}
    trend_adverse = bool(close.iloc[-1] < close.iloc[-200:].mean())
    vol = float(close.pct_change(fill_method=None).tail(63).std(ddof=1) * np.sqrt(252))
    # 25% annual risk budget ceiling is an ex-ante risk convention, no regime fit.
    vol_adverse = vol > .25
    count = int(trend_adverse) + int(vol_adverse)
    return {"status": "READY", "trendAdverse": trend_adverse, "benchmarkVol63": vol,
            "volAdverse": bool(vol_adverse), "riskMultiplier": (1.0, .7, .4)[count],
            "availableThrough": date}
