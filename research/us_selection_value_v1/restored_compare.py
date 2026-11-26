"""Price Top 5 vs price+business-confirmation Top 5 on the ORIGINAL and the RESTORED (departed issuers added) sample.

    python -m research.us_selection_value_v1.restored_compare --private <dir outside git> --out research/us_selection_value_v1/results

Rules are the frozen ones (evaluate.score / evaluate.book TOP5: five names, at most two per sector, equal weight, 8.0/8.3 bp).
Selection reads only signal-date information; a restored name enters a book only through the same scoring, and a cohort whose
held name has no exit close (source A ends at its delisting or 2018-02-27) is UNRESOLVED for that book: it is never refilled.

WINDOW. Source A ends 2018-02-27, so the comparison is limited to cohorts whose EXIT session is on or before that day
(H126: signals 2014-02 .. ~2017-08; H252: signals 2014-02 .. ~2017-02). Both samples are read on exactly the same signal dates.

LEDGERS. Besides fixed holding, the frozen self-financing simulator (pipeline.us_decision_pilot.simulate) runs
  L4   4 accounts, each trades every 4th weekly signal (existing 4-week book, comparison)
  L26  26 accounts, each trades every 26 weeks and holds ~6 months; buy dates staggered weekly
  L52  52 accounts, every 52 weeks, ~12 months
on the original sample over 2014-02 .. 2026-09, and on both samples over the restored window. Accounts start in SPY and switch at
their first own signal; NAVs are averaged with equal capital. A held name without a quote makes that ledger NOT_ESTIMABLE (no
stitching), and the date and ticker are reported.
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pipeline import us_decision_pilot as UP  # noqa: E402
from research.us_selection_value_v1 import evaluate as EV  # noqa: E402
from research.us_selection_value_v1 import followup as FU  # noqa: E402

WINDOW_END = pd.Timestamp("2018-02-27")
STRATS = ("PRICE", "PRICE_CONFIRMED")


def sections_of(feats):
    out = {}
    for d, g in feats.groupby("date"):
        x = EV.common(g)
        if len(x) >= 30:
            out[pd.Timestamp(d)] = EV.score(x)
    return out


def cohorts(close, qqq, secs, restored_set, H, end):
    rows = {}
    for d, x in secs.items():
        pos = close.index.get_loc(d)
        if pos + 1 + H >= len(close):
            continue
        e, z = close.index[pos + 1], close.index[pos + 1 + H]
        if end is not None and z > end:
            continue
        r = close.loc[z] / close.loc[e] - 1
        spy = EV.net(float(close["SPY"].loc[z] / close["SPY"].loc[e] - 1))
        qq = EV.net(float(qqq.loc[z] / qqq.loc[e] - 1))
        for s in STRATS:
            names = EV.book(x, s, "TOP5")
            rr = r.reindex(names)
            miss = [t for t in names if not np.isfinite(rr.get(t, np.nan))]
            rows[(d, s)] = {"names": names, "restoredHeld": [t for t in names if t in restored_set], "unresolved": miss,
                            "net": None if miss else EV.net(float(rr.mean())), "spy": spy, "qqq": qq, "entry": e, "exit": z}
    return rows


def ledger(close, secs, strat, every, start, end):
    days = [d for d in sorted(secs) if start <= d <= end]
    prices = close.loc[days[0]:end]
    accounts = []
    for k in range(every):
        orders = {prices.index[1]: {"SPY": 1.0}}
        for d in days[k::every]:
            pos = close.index.get_loc(d)
            if pos + 1 < len(close) and close.index[pos + 1] in prices.index and close.index[pos + 1] >= prices.index[1]:
                names = EV.book(secs[d], strat, "TOP5")
                orders[close.index[pos + 1]] = {t: 1 / len(names) for t in names}
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
    cost = sum(a["costInitialCapital"] for a in accounts) / every
    turn = sum(a["twoWayTurnover"] for a in accounts) / every
    return {"start": str(nav.index[0].date()), "end": str(nav.index[-1].date()), "cagr": float(nav.iloc[-1] ** (1 / yrs) - 1),
            "spyCagr": float(spy.iloc[-1] ** (1 / yrs) - 1), "excess": float(nav.iloc[-1] ** (1 / yrs) - spy.iloc[-1] ** (1 / yrs)),
            "trackingError": float(act.std() * np.sqrt(252)), "infoRatio": float(act.mean() * 252 / (act.std() * np.sqrt(252))),
            "mdd": float((nav / nav.cummax() - 1).min()), "spyMdd": float((spy / spy.cummax() - 1).min()),
            "costPerYear": float(cost.sum() / yrs), "oneWayTurnoverPerYear": float(turn.sum() / 2 / yrs)}


def summary(vals, H):
    v = [x for x in vals if x is not None]
    return {"n": len(v), "mean": float(np.mean(v)) if v else None, "ci": FU.ci(v, H) if v else None}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    P, OUT = Path(a.private), Path(a.out)
    close, _, qqq, _ = EV.load(P)
    rp = pickle.load(open(P / "restored.pkl", "rb"))
    panel = rp["panel"]
    restored_set = set(panel.columns) - set(close.columns)
    close_aug = pd.concat([close, panel[sorted(restored_set)]], axis=1)
    orig = sections_of(pd.read_pickle(P / "features.pkl"))
    rest = sections_of(pd.read_pickle(P / "features-restored.pkl"))
    common_dates = sorted(set(orig) & set(rest))
    orig = {d: orig[d] for d in common_dates}
    rest = {d: rest[d] for d in common_dates}
    out = {"studyId": "us-selection-value-v1", "label": "RESTORED_SAMPLE_COMPARISON_EXPLORATORY", "windowEnd": str(WINDOW_END.date()),
           "restoredTickers": len(restored_set), "sourceReceipts": {"verified": sum(r["matchesAudit"] for r in rp["receipts"]), "of": len(rp["receipts"])},
           "restoredInCommonUniverse": {}, "fixed": {}, "ledgers": {}}
    yr = Counter()
    for d, x in rest.items():
        if d <= WINDOW_END:
            yr[str(d.year)] += int(x.index.isin(restored_set).sum())
    out["restoredInCommonUniverse"] = {y: round(v / sum(1 for d in rest if str(d.year) == y), 1) for y, v in sorted(yr.items())}
    for H in (126, 252):
        co_o = cohorts(close_aug, qqq, orig, restored_set, H, WINDOW_END)
        co_r = cohorts(close_aug, qqq, rest, restored_set, H, WINDOW_END)
        dates = sorted({d for d, _ in co_o})
        unres = Counter()
        cell = {}
        for s in STRATS:
            for lab, co in (("original", co_o), ("restored", co_r)):
                for d in dates:
                    if co[(d, s)]["unresolved"]:
                        unres[f"{lab}|{s}|" + ("RESTORED_NAME_SERIES_ENDS_BEFORE_EXIT" if set(co[(d, s)]["unresolved"]) & restored_set else "OTHER")] += 1
        ok = [d for d in dates if all(co[(d, s)]["net"] is not None for co in (co_o, co_r) for s in STRATS)]
        cell["signalDates"] = len(dates)
        cell["pairedResolvedDates"] = len(ok)
        cell["firstLast"] = [str(ok[0].date()), str(ok[-1].date())] if ok else None
        cell["blockWeeks"] = FU.spec_block(H)
        cell["unresolvedCohorts"] = dict(unres)
        cell["datesWhereRestoredBookDiffers"] = {s: sum(1 for d in ok if co_o[(d, s)]["names"] != co_r[(d, s)]["names"]) for s in STRATS}
        cell["restoredNamesHeld"] = {s: sum(len(co_r[(d, s)]["restoredHeld"]) for d in ok) for s in STRATS}
        for lab, co in (("original", co_o), ("restored", co_r)):
            for s in STRATS:
                cell[f"{lab}|{s}|vsSPY"] = summary([co[(d, s)]["net"] - co[(d, s)]["spy"] for d in ok], H)
                cell[f"{lab}|{s}|vsQQQ"] = summary([co[(d, s)]["net"] - co[(d, s)]["qqq"] for d in ok], H)
            cell[f"{lab}|INCREMENT_CONFIRMED_MINUS_PRICE"] = summary([co[(d, "PRICE_CONFIRMED")]["net"] - co[(d, "PRICE")]["net"] for d in ok], H)
        for s in STRATS:
            cell[f"RESTORED_MINUS_ORIGINAL|{s}"] = summary([co_r[(d, s)]["net"] - co_o[(d, s)]["net"] for d in ok], H)
        # the restored sample's resolved-only reading (dates where the original is resolved but the restored is not are dropped above)
        for s in STRATS:
            rr = [co_r[(d, s)]["net"] - co_r[(d, s)]["spy"] for d in dates if co_r[(d, s)]["net"] is not None]
            cell[f"restoredResolvedOnly|{s}|vsSPY"] = summary(rr, H)
        out["fixed"][str(H)] = cell
        print(H, cell["pairedResolvedDates"], {k: v for k, v in cell.items() if "INCREMENT" in k}, flush=True)
    # ledgers
    full_start, full_end = min(orig), close.index[-1]
    win_end = WINDOW_END
    for every in (4, 26, 52):
        for s in STRATS:
            out["ledgers"][f"original|{s}|L{every}|FULL"] = ledger(close_aug, orig, s, every, full_start, full_end)
            out["ledgers"][f"original|{s}|L{every}|RESTORED_WINDOW"] = ledger(close_aug, orig, s, every, full_start, win_end)
            out["ledgers"][f"restored|{s}|L{every}|RESTORED_WINDOW"] = ledger(close_aug, rest, s, every, full_start, win_end)
            print("ledger", every, s, {k: (v.get("excess"), v.get("status")) for k, v in out["ledgers"].items() if f"L{every}" in k and s in k}, flush=True)
    (OUT / "restored-compare.json").write_text(json.dumps(out, indent=1, sort_keys=True, default=str) + "\n")


if __name__ == "__main__":
    main()
