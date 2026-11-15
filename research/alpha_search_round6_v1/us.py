"""Round 6 — US: U1 TOP5_CAP_NEUTRAL, U2 CAP_OVER_EQUAL_GATE, U3 SECTOR_DISPERSION_TILT on the fixed 25% cocktail
(definitions in PREREGISTRATION.md).

    python -m research.alpha_search_round6_v1.us --private <dir outside git>

Reuses the frozen evaluate.score / evaluate.book sleeves, evaluate.net costs on the combined target, and
us_decision_pilot.simulate for staggered ledgers. Original sample only (the restored sample's ledgers are not estimable, #346).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pipeline import us_decision_pilot as UP  # noqa: E402
from research.alpha_search_round6_v1 import common as CM  # noqa: E402
from research.us_selection_value_v1 import cocktail as CK  # noqa: E402
from research.us_selection_value_v1 import evaluate as EV  # noqa: E402
from research.us_selection_value_v1 import followup as FU  # noqa: E402
from research.us_selection_value_v1 import restored_compare as RCMP  # noqa: E402

K = 5
LOOKBACK = 126
DISP_WINDOW, DISP_MIN = 156, 52
OUT = Path(__file__).resolve().parent / "results"
SLV = CK.SLEEVES["COCKTAIL"]
EQUAL = {s: 0.25 for s in SLV}
TILT = {s: (0.5 if s == "SECTOR_MOMENTUM_BASKET" else 1 / 6) for s in SLV}


def sleeve_book(x, wts):
    w = defaultdict(float)
    for s, a in wts.items():
        names = CK.sleeve_names(x, s)
        if not names:
            w["SPY"] += a
            continue
        for t in names:
            w[t] += a / len(names)
    return dict(w)


def top5_neutral(x, parent):
    cap = x["marketCap"].astype(float)
    top = cap.sort_values(ascending=False).head(K)
    s = float(top.sum() / cap.sum())
    out = defaultdict(float)
    for t, v in parent.items():
        out[t] += (1 - s) * v
    for t, v in (top / cap.sum()).items():
        out[t] += float(v)
    return dict(out), s


def cap_over_equal(close, secs, keys, d):
    pos = close.index.get_loc(d)
    if pos < LOOKBACK:
        return None
    t0 = close.index[pos - LOOKBACK]
    prior = [k for k in keys if k <= t0]
    if not prior:
        return None
    x0 = secs[prior[-1]]
    names = [t for t in x0.index if t in close.columns]
    r = close.loc[d, names] / close.loc[t0, names] - 1
    r = r[np.isfinite(r)]
    if r.empty:
        return None
    w = x0.loc[r.index, "marketCap"].astype(float)
    w = w / w.sum()
    return float((w * r).sum() - r.mean())


def dispersion(x):
    g = x.groupby("sector")["momentum252"]
    m = g.mean()[g.size() >= 3]
    return float(m.std(ddof=1)) if len(m) >= 2 else None


def build(close, secs):
    keys = sorted(secs)
    books = {k: {} for k in ("COCKTAIL", "U1_TOP5_CAP_NEUTRAL", "U2_CAP_OVER_EQUAL_GATE", "U3_SECTOR_DISPERSION_TILT")}
    state, disp_hist = {}, []
    for d in keys:
        x = secs[d]
        parent = sleeve_book(x, EQUAL)
        u1, s = top5_neutral(x, parent)
        gap = cap_over_equal(close, secs, keys, d)
        on = gap is not None and gap > 0
        disp = dispersion(x)
        past = [v for v in disp_hist[-DISP_WINDOW:] if v is not None]
        tilt = disp is not None and len(past) >= DISP_MIN and disp >= float(np.median(past))
        disp_hist.append(disp)
        books["COCKTAIL"][d] = parent
        books["U1_TOP5_CAP_NEUTRAL"][d] = u1
        books["U2_CAP_OVER_EQUAL_GATE"][d] = {"SPY": 1.0} if on else parent
        books["U3_SECTOR_DISPERSION_TILT"][d] = sleeve_book(x, TILT) if tilt else parent
        state[d] = {"top5Share": s, "capMinusEqual126": gap, "gateOn": on, "dispersion": disp, "tiltOn": tilt}
    return books, state


def cohort_w(close, qqq, w, d, H):
    pos = close.index.get_loc(d)
    if pos + 1 + H >= len(close):
        return None
    e, z = close.index[pos + 1], close.index[pos + 1 + H]
    r = close.loc[z, list(w)] / close.loc[e, list(w)] - 1
    if r.isna().any():
        return {"unresolved": sorted(r.index[r.isna()])}
    g = float((r * pd.Series(w)).sum())
    return {"entry": e, "exit": z, "net": EV.net(g), "spy": EV.net(float(close["SPY"].loc[z] / close["SPY"].loc[e] - 1)),
            "qqq": EV.net(float(qqq.loc[z] / qqq.loc[e] - 1))}


def ledger_w(close, books, every, start, end):
    days = [d for d in sorted(books) if start <= d <= end]
    prices = close.loc[days[0]:end]
    accounts = []
    for k in range(every):
        orders = {prices.index[1]: {"SPY": 1.0}}
        for d in days[k::every]:
            pos = close.index.get_loc(d)
            if pos + 1 < len(close) and close.index[pos + 1] in prices.index and close.index[pos + 1] >= prices.index[1]:
                orders[close.index[pos + 1]] = books[d]
        cols = sorted({t for w in orders.values() for t in w})
        try:
            accounts.append(UP.simulate(prices[cols], orders))
        except ValueError as e:
            return {"status": "NOT_ESTIMABLE", "reason": str(e)}
    nav = sum(a["nav"] for a in accounts) / every
    spy = prices["SPY"] / prices["SPY"].iloc[0]
    r, rs = nav.pct_change().dropna(), spy.pct_change().dropna()
    act = r - rs.reindex(r.index)
    yrs = len(r) / 252
    return {"start": str(nav.index[0].date()), "end": str(nav.index[-1].date()), "cagr": float(nav.iloc[-1] ** (1 / yrs) - 1),
            "spyCagr": float(spy.iloc[-1] ** (1 / yrs) - 1), "excess": float(nav.iloc[-1] ** (1 / yrs) - spy.iloc[-1] ** (1 / yrs)),
            "trackingError": float(act.std() * np.sqrt(252)), "infoRatio": float(act.mean() * 252 / (act.std() * np.sqrt(252))),
            "mdd": float((nav / nav.cummax() - 1).min()), "spyMdd": float((spy / spy.cummax() - 1).min()),
            "costPerYear": float(sum(a["costInitialCapital"] for a in accounts).sum() / every / yrs),
            "oneWayTurnoverPerYear": float(sum(a["twoWayTurnover"] for a in accounts).sum() / every / 2 / yrs)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", required=True)
    a = ap.parse_args(argv)
    P = Path(a.private)
    close, feats, qqq, _ = EV.load(P)
    secs = RCMP.sections_of(feats)
    books, state = build(close, secs)
    st = pd.DataFrame(state).T.apply(pd.to_numeric, errors="coerce")
    names = list(books)
    res = {"studyId": "alpha-search-round6-v1", "market": "US", "label": "EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_HISTORY",
           "signalDates": [str(min(secs).date()), str(max(secs).date()), len(secs)],
           "state": {"top5ShareMean": float(st["top5Share"].astype(float).mean()), "gateOnShare": float(st["gateOn"].astype(float).mean()),
                     "tiltOnShare": float(st["tiltOn"].astype(float).mean()),
                     "gateOnShareByYear": st.groupby(pd.to_datetime(st.index).year)["gateOn"].mean().round(3).to_dict(),
                     "tiltOnShareByYear": st.groupby(pd.to_datetime(st.index).year)["tiltOn"].mean().round(3).to_dict()},
           "fixed": {}, "ledgers": {}}
    for H in (126, 252):
        rows, unres = [], []
        for d in sorted(secs):
            cs = {k: cohort_w(close, qqq, books[k][d], d, H) for k in names}
            if any(v is None for v in cs.values()):
                continue
            if any("unresolved" in v for v in cs.values()):
                unres.append({"date": str(d.date()), **{k: v["unresolved"] for k, v in cs.items() if "unresolved" in v}})
                continue
            rows.append({"date": d, "entry": cs["COCKTAIL"]["entry"], "exit": cs["COCKTAIL"]["exit"], "spy": cs["COCKTAIL"]["spy"],
                         "qqq": cs["COCKTAIL"]["qqq"], **{f"{k}_net": v["net"] for k, v in cs.items()}})
        df = pd.DataFrame(rows)
        block = FU.spec_block(H)
        samples = {"FULL": df, "EXIT_BY_2022": df[df["exit"] <= CK.EXIT_2022], "ENTRY_FROM_2023": df[df["entry"] >= CK.ENTRY_2023]}
        cell = {"unresolvedCohorts": unres}
        for nm, s in samples.items():
            row = {"cohorts": int(len(s)), "first": str(s["date"].iloc[0].date()), "last": str(s["date"].iloc[-1].date()), "SPY_meanNet": float(s["spy"].mean())}
            for k in names:
                row[k] = {"vsSPY": CM.boot((s[f"{k}_net"] - s["spy"]).tolist(), block), "vsQQQ": float((s[f"{k}_net"] - s["qqq"]).mean())}
                if k != "COCKTAIL":
                    row[k]["vsParentCocktail"] = CM.boot((s[f"{k}_net"] - s["COCKTAIL_net"]).tolist(), block)
            cell[nm] = row
        res["fixed"][str(H)] = cell
        print("US fixed", H, {n: {k: round(c[k]["vsSPY"]["mean"] * 100, 2) for k in names} for n, c in cell.items() if isinstance(c, dict) and "COCKTAIL" in c}, flush=True)
    (OUT / "us.json").write_text(json.dumps(res, indent=1, sort_keys=True, default=str) + "\n")
    start, end = min(secs), close.index[-1]
    for every in (26, 52):
        for k in names:
            res["ledgers"][f"L{every}|FULL|{k}"] = ledger_w(close, books[k], every, start, end)
            res["ledgers"][f"L{every}|TO_2022|{k}"] = ledger_w(close, books[k], every, start, CK.EXIT_2022)
            v = res["ledgers"][f"L{every}|FULL|{k}"]
            print("US ledger", every, k, round(v.get("excess", np.nan) * 100, 2), round(v.get("mdd", np.nan) * 100, 1), flush=True)
    (OUT / "us.json").write_text(json.dumps(res, indent=1, sort_keys=True, default=str) + "\n")


if __name__ == "__main__":
    main()
