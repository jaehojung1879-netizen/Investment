"""Full Drawdown Atlas of SPY total return, 1993-2026: forward outcomes by the drawdown state on the entry day.

ENTRY CONDITIONS use only information available at the close of day t:
  depth      = TR_t / max(TR_s, s <= t) - 1, bucketed 0-5, 5-10, 10-15, 15-20, 20-30, 30+ %
  duration   = sessions since that running peak (FAST <= 63 sessions, SLOW > 63)
  stabilised = the running low since the peak was set >= 21 sessions ago (no new low in the last 21 sessions)
  credit     = as-of BAA - GS10 of the latest month-end decision <= t, above / at-or-below its expanding median
  vix        = VIX close at t above / at-or-below its expanding median (VIX from 1990)
OUTCOMES (never used as conditions): forward total return over 21/63/126/252 sessions, probability of a loss, the
lowest return relative to t within the horizon ("further minimum"), and sessions until the pre-t peak is regained
(censored when not regained by the last session).

Two views, never pooled as evidence:
  all-days   every eligible session (heavily overlapping; counts are not independent)
  episodes   one observation per drawdown spell and bucket: the FIRST day the spell enters that bucket. A spell runs
             from a running peak until that peak is regained (the Stage 1 'full recovery' rule).
Each cell reports the number of distinct spells behind it. No p-values, no thresholds fitted, no strategy.

    python -m research.track_b_pilot.atlas
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from research.market_risk_discovery_v1 import baseline_census as B
from research.market_risk_discovery_v1 import exp1_inputs as I
from research.market_risk_discovery_v1 import label_census as L

HERE = Path(__file__).resolve().parent
BUCKETS = ((0.00, 0.05), (0.05, 0.10), (0.10, 0.15), (0.15, 0.20), (0.20, 0.30), (0.30, 1.01))
HORIZONS = (21, 63, 126, 252)
FAST_SESSIONS, STABLE_SESSIONS = 63, 21


def label(b) -> str:
    return f"{int(b[0] * 100)}-{int(b[1] * 100)}%" if b[1] <= 1 else f"{int(b[0] * 100)}%+"


def state() -> dict:
    dates, tr = L.load_tr()
    n = len(tr)
    peak = np.maximum.accumulate(tr)
    dd = tr / peak - 1
    peak_idx = np.zeros(n, dtype=int)
    low_idx = np.zeros(n, dtype=int)
    spell = np.full(n, -1)
    sid = -1
    for t in range(n):
        if tr[t] >= peak[t]:
            peak_idx[t], low_idx[t] = t, t
        else:
            peak_idx[t] = peak_idx[t - 1]
            low_idx[t] = t if tr[t] <= tr[low_idx[t - 1]] else low_idx[t - 1]
            if dd[t - 1] == 0 or spell[t - 1] == -1:
                sid += 1
            spell[t] = sid
    # recovery: sessions until TR regains peak[t]
    rec = np.full(n, -1)
    nxt = n
    for t in range(n - 1, -1, -1):
        if tr[t] >= peak[t]:
            nxt = t
            rec[t] = 0
        else:
            rec[t] = (nxt - t) if nxt < n else -1
    credit = B.credit_series()
    months = sorted(credit)
    cvals = {}
    for m in months:
        hist = [credit[k] for k in months if k <= m and credit[k] is not None]
        cvals[m] = None if credit[m] is None or len(hist) < 12 else credit[m] > float(np.median(hist))
    vix = I.load("VIXCLS")
    vser = [vix.get(d) for d in dates]
    vhigh, hist = [], []
    for v in vser:
        vhigh.append(None if v is None or len(hist) < 252 else v > float(np.median(hist)))
        if v is not None:
            hist.append(v)
    credit_high = []
    for d in dates:
        prev = [m for m in months if m < d[:7]]
        credit_high.append(cvals.get(prev[-1]) if prev else None)   # latest completed month-end decision
    return {"dates": dates, "tr": tr, "dd": dd, "since_peak": np.arange(n) - peak_idx,
            "since_low": np.arange(n) - low_idx, "spell": spell, "rec": rec,
            "credit_high": credit_high, "vix_high": vhigh}


def outcomes(s: dict, idx: np.ndarray) -> dict:
    tr, n = s["tr"], len(s["tr"])
    out = {"n": int(len(idx)), "spells": int(len({int(s["spell"][i]) for i in idx if s["spell"][i] >= 0}))}
    for h in HORIZONS:
        ok = idx[idx + h < n]
        if not len(ok):
            out[str(h)] = None
            continue
        fwd = tr[ok + h] / tr[ok] - 1
        mins = np.array([tr[i + 1:i + h + 1].min() / tr[i] - 1 for i in ok])
        out[str(h)] = {"n": int(len(ok)), "meanReturn": float(fwd.mean()), "medianReturn": float(np.median(fwd)),
                       "lossProbability": float((fwd < 0).mean()), "medianFurtherMin": float(np.median(mins)),
                       "p10FurtherMin": float(np.quantile(mins, 0.10))}
    r = s["rec"][idx]
    done = r[r >= 0]
    out["recovery"] = {"medianSessions": float(np.median(done)) if len(done) else None,
                       "p90Sessions": float(np.quantile(done, 0.9)) if len(done) else None,
                       "censoredShare": float((r < 0).mean())}
    return out


def in_bucket(s, b):
    d = -s["dd"]
    return (d >= b[0]) & (d < b[1])


def first_entries(s: dict, mask: np.ndarray) -> np.ndarray:
    seen, out = set(), []
    for i in np.where(mask)[0]:
        key = int(s["spell"][i])
        if key < 0:                      # depth 0 at a new peak: not part of a spell
            continue
        if key not in seen:
            seen.add(key)
            out.append(i)
    return np.array(out, dtype=int)


def rolling_high_events(s: dict, window: int = 252, fall: float = -0.10, rearm: float = -0.05) -> list[dict]:
    """Alternative, PIT event definition: first close at or below -10% from the trailing 252-session high; re-armed
    only after the same measure recovers above -5%. Used to show which declines the full-recovery rule absorbs."""
    tr, out, armed = s["tr"], [], True
    for t in range(len(tr)):
        hi = tr[max(0, t - window + 1):t + 1].max()
        x = tr[t] / hi - 1
        if armed and x <= fall:
            out.append({"date": s["dates"][t], "spell": int(s["spell"][t]), "fullRecoveryDepth": float(s["dd"][t])})
            armed = False
        elif not armed and x > rearm:
            armed = True
    return out


def spells_table(s: dict, events: list[dict]) -> list[dict]:
    rows = []
    for k in sorted({int(x) for x in s["spell"] if x >= 0}):
        ix = np.where(s["spell"] == k)[0]
        low = ix[np.argmin(s["dd"][ix])]
        depth = float(s["dd"][low])
        if depth > -0.10:
            continue
        inside = [e["date"] for e in events if e["spell"] == k]
        rows.append({"start": s["dates"][ix[0]], "low": s["dates"][low], "maxDepth": depth,
                     "recovered": s["dates"][ix[-1] + 1] if ix[-1] + 1 < len(s["tr"]) else None,
                     "sessions": int(len(ix)), "rollingHighEventsInside": inside,
                     "absorbedEvents": max(0, len(inside) - 1)})
    return rows


def build() -> dict:
    s = state()
    n = len(s["tr"])
    every = np.arange(n)
    out = {"study": "full-drawdown-atlas", "source": "SPY total return (Stage 1 ledger), raw close + SSGA distributions",
           "window": [s["dates"][0], s["dates"][-1]], "sessions": n,
           "evidenceClass": "DESCRIPTIVE_ON_EXPOSED_HISTORY", "noPValues": True, "noStrategy": True,
           "unconditional": outcomes(s, every), "depth": {}, "depthBySpeed": {}, "depthByStabilisation": {},
           "depthByCredit": {}, "depthByVix": {}}
    events = rolling_high_events(s)
    out["rollingHighEvents"] = {"definition": "first close <= -10% from trailing 252-session high, re-armed above -5%",
                                "count": len(events), "events": events}
    out["spellsAtLeast10pct"] = spells_table(s, events)
    for b in BUCKETS:
        m = in_bucket(s, b)
        key = label(b)
        out["depth"][key] = {"allDays": outcomes(s, np.where(m)[0]), "firstEntryPerSpell": outcomes(s, first_entries(s, m))}
        sp = s["since_peak"]
        out["depthBySpeed"][key] = {f"fast<= {FAST_SESSIONS}": outcomes(s, np.where(m & (sp <= FAST_SESSIONS))[0]),
                                    f"slow> {FAST_SESSIONS}": outcomes(s, np.where(m & (sp > FAST_SESSIONS))[0])}
        st = s["since_low"] >= STABLE_SESSIONS
        out["depthByStabilisation"][key] = {"stabilised": outcomes(s, np.where(m & st & (s["dd"] < 0))[0]),
                                            "newLowWithin21": outcomes(s, np.where(m & ~st)[0])}
        for name, flag in (("depthByCredit", "credit_high"), ("depthByVix", "vix_high")):
            f = np.array([x is True for x in s[flag]])
            g = np.array([x is False for x in s[flag]])
            out[name][key] = {"aboveExpandingMedian": outcomes(s, np.where(m & f)[0]),
                              "atOrBelow": outcomes(s, np.where(m & g)[0])}
    return out


def main() -> int:
    out = build()
    (HERE / "drawdown-atlas.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print("ok", out["window"], out["sessions"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
