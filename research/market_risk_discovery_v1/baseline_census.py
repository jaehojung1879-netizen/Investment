"""Stage 1 baseline census: how much of P1's risk set the existing trend/volatility model leaves "normal", and how
often a credit flag would be on. The CREDIT SIGNAL IS NEVER RELATED TO ANY LABEL here.

* FAST (inherited unchanged from the sealed KR market-risk model, as replicated for the US in rp1-c1): count of
  {close < 200-session mean, 63-session realised volatility (annualised) > 25%}. FAST = 0 is "baseline normal".
  Computed on SPY split-adjusted raw close.
* Label x FAST (baseline only): which of the 7 episodes had at least one risk-set month-end with FAST = 0 inside the
  126 sessions before the start, and the FAST = 0 share of labelled months. This measures the EXISTING model's
  coverage, which P1's effective sample depends on; it reads no credit value.
* Credit (signal only, no label): BAA - GS10 from the ALFRED as-of ledgers (vintage the day before each decision;
  missing when the legs disagree on month). Reported: availability by date, and the alarm share of the MVMA-v1 frozen
  CREDIT_STRESS rule over FAST-normal risk-set months -- a budget figure for the power calculation, not a test.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np

from research.market_valuation_macro_overlay_v1 import features as F

from . import label_census as L

HERE = Path(__file__).resolve().parent


def fast_state(close: np.ndarray) -> list[int | None]:
    out = []
    ret = np.diff(np.log(close), prepend=np.nan)
    for t in range(len(close)):
        if t < 199:
            out.append(None)
            continue
        below = close[t] < close[t - 199:t + 1].mean()
        vol = float(np.std(ret[t - 62:t + 1], ddof=1) * np.sqrt(252))
        out.append(int(below) + int(vol > 0.25))
    return out


def raw_close() -> tuple[list[str], np.ndarray]:
    import datetime as dt
    import gzip
    chart = json.loads(gzip.decompress((HERE / "data/raw/yahoo-SPY-chart-20261110.json.gz").read_bytes()))["chart"]["result"][0]
    day = lambda ts: dt.datetime.fromtimestamp(ts, dt.timezone.utc).date().isoformat()  # noqa: E731
    pairs = sorted((day(t), c) for t, c in zip(chart["timestamp"], chart["indicators"]["quote"][0]["close"]) if c is not None)
    return [d for d, _ in pairs], np.array([c for _, c in pairs])


def credit_series() -> dict[str, float | None]:
    b = {r["decisionDate"]: r for r in csv.DictReader((HERE / "data/alfred-BAA-asof-month-ends.csv").open())}
    g = {r["decisionDate"]: r for r in csv.DictReader((HERE / "data/alfred-GS10-asof-month-ends.csv").open())}
    out = {}
    for d in sorted(b):
        ok = b[d]["value"] and g[d]["value"] and b[d]["observationDate"][:7] == g[d]["observationDate"][:7]
        out[d[:7]] = float(b[d]["value"]) - float(g[d]["value"]) if ok else None
    return out


def build() -> dict:
    dates, tr = L.load_tr()
    rdates, close = raw_close()
    assert rdates == dates
    fast = fast_state(close)
    eps, active = L.episodes(dates, tr)
    y = L.labels(dates, active, eps)
    me = L.month_ends(dates)
    pos = {d: k for k, d in enumerate(dates)}

    episodes = []
    for e in eps:
        s = pos[e["start"]]
        window = [k for k in me if s - L.HORIZON <= k < s and not active[k]]
        normal = [dates[k] for k in window if fast[k] == 0]
        episodes.append({"start": e["start"], "riskMonthEndsInWindow": len(window),
                         "fastNormalMonthEnds": normal, "eligibleForP1": bool(normal)})

    risk_me = [k for k in me if not active[k] and dates[k] >= "1997-01-31"]
    labelled = [k for k in risk_me if y[k] is not None]
    fast_normal = [k for k in labelled if fast[k] == 0]

    credit = credit_series()
    months = [dates[k][:7] for k in risk_me]
    series = [credit.get(m) for m in sorted(credit)]
    keys = sorted(credit)
    stress = {keys[i]: F.credit_stress(series, i) for i in range(len(keys))}
    budget_months = [dates[k][:7] for k in risk_me if fast[k] == 0 and stress.get(dates[k][:7]) is not None]
    return {
        "stage": "STAGE_1_BASELINE_CENSUS", "creditLabelReads": 0,
        "fastDefinition": "count of {SPY close < 200-session mean, 63-session realised vol > 25% annualised}",
        "riskSetMonthEnds1997": len(risk_me), "labelled": len(labelled), "labelledPositive": sum(y[k] == 1 for k in labelled),
        "labelledFastNormal": len(fast_normal), "labelledFastNormalPositive": sum(y[k] == 1 for k in fast_normal),
        "episodes": episodes, "eligibleEpisodes": sum(e["eligibleForP1"] for e in episodes),
        "credit": {"firstMonth": next(m for m in keys if credit[m] is not None), "lastMonth": keys[-1],
                   "missingMonths": [m for m in keys if credit[m] is None],
                   "mvmaCreditStressFirstDefined": next((m for m in keys if stress[m] is not None), None),
                   "fastNormalRiskMonthsWithStressDefined": len(budget_months),
                   "alarmShareAmongThem": (float(np.mean([stress[m] for m in budget_months])) if budget_months else None)},
        "riskMonthsCovered": len(months),
    }


def main() -> int:
    report = build()
    (HERE / "evidence" / "baseline-census.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps(report, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())


def candidate_credit_flags(min_history: int = 12) -> dict:
    """Availability and alarm share of candidate credit-change flags over FAST-normal risk-set month-ends 1997+.
    Signal-only: no label is read. Used to pick a definition by budget and coverage, never by outcome."""
    dates, tr = L.load_tr()
    _, close = raw_close()
    fast = fast_state(close)
    eps, active = L.episodes(dates, tr)
    me = [k for k in L.month_ends(dates) if not active[k] and dates[k] >= "1997-01-31" and fast[k] == 0]
    credit = credit_series()
    keys = sorted(credit)
    vals = [credit[k] for k in keys]
    idx = {k: i for i, k in enumerate(keys)}

    def change(i, lag):
        if i < lag or vals[i] is None or vals[i - lag] is None:
            return None
        return vals[i] - vals[i - lag]

    flags = {
        "WIDEN_3M_GT0": lambda i: (lambda c: None if c is None else c > 0)(change(i, 3)),
        "WIDEN_6M_GT0": lambda i: (lambda c: None if c is None else c > 0)(change(i, 6)),
        "WIDEN_3M_ABOVE_EXPANDING_P80": lambda i: _above_expanding(i, lambda j: change(j, 3), 0.8, min_history),
        "MVMA_CREDIT_STRESS": lambda i: F.credit_stress(vals, i),
    }
    out = {}
    for name, fn in flags.items():
        state = {dates[k][:7]: fn(idx[dates[k][:7]]) for k in me if dates[k][:7] in idx}
        defined = [m for m, v in state.items() if v is not None]
        out[name] = {"firstDefined": min(defined) if defined else None, "definedMonths": len(defined),
                     "fastNormalRiskMonths": len(state),
                     "alarmShare": float(np.mean([state[m] for m in defined])) if defined else None}
    return out


def _above_expanding(i, value, q, min_history):
    cur = value(i)
    hist = [v for v in (value(j) for j in range(i)) if v is not None]
    if cur is None or len(hist) < min_history:
        return None
    return cur > float(np.quantile(hist, q))
