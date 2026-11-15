"""US fixed-weight stock cocktail from the existing #343 signals — first table.

    python -m research.us_selection_value_v1.cocktail --private <dir outside git> --out research/us_selection_value_v1/results

Sleeves (frozen evaluate.score / evaluate.book): PRICE TOP5, SECTOR_MOMENTUM_BASKET, WITHIN_SECTOR_VALUE TOP5, CASH_PROFITABILITY TOP5.
COCKTAIL = 25% of capital per sleeve, each sleeve equal-weight across its own names; a ticker held by several sleeves gets the SUM of
its sleeve weights (one position, one trade). A sleeve with no name on a date puts its 25% in SPY (investable-in-advance rule).
COCKTAIL_CONFIRMED = the same with the price sleeve replaced by PRICE_CONFIRMED TOP5 (business confirmation on the price part only).
Costs: pipeline.benchmark_alpha.REALISTIC_COSTS['US'] (8.0 bp buy, 8.3 bp sell) on the COMBINED target, so overlap is not paid twice;
SPY and QQQ pay the same round trip. A held name without an exit close leaves the cohort UNRESOLVED (no substitute).

Samples (same signal dates wherever they overlap):
  FULL_ORIGINAL    original sample, every matured cohort (2014-02 ..)
  RESTORED         departed issuers restored from audited source A (restore_departed.py); cohorts exiting <= 2018-02-27,
                   compared date-by-date with ORIGINAL on the same dates
  EXIT_BY_2022     original sample, cohorts whose exit session is <= 2022-12-30
  ENTRY_FROM_2023  original sample, cohorts whose entry session is >= 2023-01-03
Ledgers: L4 / L26 / L52 staggered accounts (pipeline.us_decision_pilot.simulate), each account holding 4 / 26 / 52 weeks.
Diagnostics per cohort: company-merged effective number of names (1 / sum w^2, tickers sharing a filing CIK merged), weight in the
cap-proxy Top 10 of all priced members, largest sector weight, weight in names held by two or more sleeves.
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pipeline import us_decision_pilot as UP  # noqa: E402
from research.us_selection_value_v1 import evaluate as EV  # noqa: E402
from research.us_selection_value_v1 import followup as FU  # noqa: E402
from research.us_selection_value_v1 import restored_compare as RCMP  # noqa: E402

SLEEVES = {"COCKTAIL": ("PRICE", "SECTOR_MOMENTUM_BASKET", "WITHIN_SECTOR_VALUE", "CASH_PROFITABILITY"),
           "COCKTAIL_CONFIRMED": ("PRICE_CONFIRMED", "SECTOR_MOMENTUM_BASKET", "WITHIN_SECTOR_VALUE", "CASH_PROFITABILITY")}
SINGLES = ("PRICE", "PRICE_CONFIRMED", "SECTOR_MOMENTUM_BASKET", "WITHIN_SECTOR_VALUE", "CASH_PROFITABILITY")
EXIT_2022 = pd.Timestamp("2022-12-30")
ENTRY_2023 = pd.Timestamp("2023-01-03")


def sleeve_names(x, s):
    return EV.book(x, s, "TOP5")


def book(x, strat):
    """{ticker: weight}, plus the sleeve membership of each ticker."""
    if strat in SINGLES:
        names = sleeve_names(x, strat)
        return ({t: 1 / len(names) for t in names} if names else {"SPY": 1.0}), {t: {strat} for t in names}
    w, member = defaultdict(float), defaultdict(set)
    for s in SLEEVES[strat]:
        names = sleeve_names(x, s)
        if not names:
            w["SPY"] += 0.25
            continue
        for t in names:
            w[t] += 0.25 / len(names)
            member[t].add(s)
    return dict(w), dict(member)


def cohort(close, qqq, x, strat, d, H, end=None):
    pos = close.index.get_loc(d)
    if pos + 1 + H >= len(close):
        return None
    e, z = close.index[pos + 1], close.index[pos + 1 + H]
    if end is not None and z > end:
        return None
    w, member = book(x, strat)
    r = close.loc[z, list(w)] / close.loc[e, list(w)] - 1
    if r.isna().any():
        return {"unresolved": sorted(r.index[r.isna()])}
    g = float((r * pd.Series(w)).sum())
    return {"entry": e, "exit": z, "net": EV.net(g), "gross": g, "spy": EV.net(float(close["SPY"].loc[z] / close["SPY"].loc[e] - 1)),
            "qqq": EV.net(float(qqq.loc[z] / qqq.loc[e] - 1)), "w": w, "member": member}


def diagnostics(w, member, x, top10, cik):
    comp = defaultdict(float)
    for t, v in w.items():
        comp[cik.get(t, t)] += v
    sec = defaultdict(float)
    for t, v in w.items():
        sec[x.at[t, "sector"] if t in x.index else "SPY"] += v
    return {"effectiveNames": 1 / sum(v * v for v in comp.values()), "top10Weight": sum(v for t, v in w.items() if t in top10),
            "largestSector": max(sec.items(), key=lambda kv: kv[1])[0], "largestSectorWeight": max(sec.values()),
            "multiSleeveWeight": sum(v for t, v in w.items() if len(member.get(t, ())) >= 2)}


def stats(ex, H):
    ex = np.asarray(ex, float)
    return {"n": int(len(ex)), "mean": float(ex.mean()), "ci": FU.ci(ex.tolist(), H), "sd": float(ex.std(ddof=1)) if len(ex) > 1 else None,
            "ir": float(ex.mean() / ex.std(ddof=1)) if len(ex) > 1 and ex.std(ddof=1) > 0 else None, "winRate": float((ex > 0).mean())}


def generic_ledger(close, secs, strat, every, start, end):
    days = [d for d in sorted(secs) if start <= d <= end]
    prices = close.loc[days[0]:end]
    accounts = []
    for k in range(every):
        orders = {prices.index[1]: {"SPY": 1.0}}
        for d in days[k::every]:
            pos = close.index.get_loc(d)
            if pos + 1 < len(close) and close.index[pos + 1] in prices.index and close.index[pos + 1] >= prices.index[1]:
                orders[close.index[pos + 1]] = book(secs[d], strat)[0]
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
    ap.add_argument("--out", required=True)
    ap.add_argument("--skip-ledgers", action="store_true", help="fixed holding and diagnostics only -> cocktail-fixed.json")
    a = ap.parse_args(argv)
    P, OUT = Path(a.private), Path(a.out)
    close, _, qqq, _ = EV.load(P)
    rp = pickle.load(open(P / "restored.pkl", "rb"))["panel"]
    restored_set = set(rp.columns) - set(close.columns)
    close_aug = pd.concat([close, rp[sorted(restored_set)]], axis=1)
    feats = pd.read_pickle(P / "features.pkl")
    orig = RCMP.sections_of(feats)
    rest = RCMP.sections_of(pd.read_pickle(P / "features-restored.pkl"))
    raw = pickle.load(open(P / "filings.pkl", "rb"))["raw"]
    cik = {t: rs[-1].get("cik") for t, rs in raw.items() if rs}
    capped = feats[feats["identity"].isin(["MEMBERSHIP_CIK", "PIT_SINGLE_CIK"])].copy()
    capped["marketCap"] = pd.to_numeric(capped["marketCap"], errors="coerce")
    top10 = {pd.Timestamp(d): set(g.dropna(subset=["marketCap"]).sort_values("marketCap", ascending=False).head(10)["ticker"]) for d, g in capped.groupby("date")}
    strats = ("COCKTAIL", "COCKTAIL_CONFIRMED") + SINGLES
    out = {"studyId": "us-selection-value-v1", "label": "FIXED_WEIGHT_COCKTAIL_FIRST_TABLE_EXPLORATORY", "fixed": {}, "diagnostics": {}, "ledgers": {}}
    for H in (126, 252):
        rows = defaultdict(dict)
        unres = defaultdict(int)
        diag = []
        for d, x in orig.items():
            for s in strats:
                c = cohort(close_aug, qqq, x, s, d, H)
                if c is None:
                    continue
                if "unresolved" in c:
                    unres[f"ORIGINAL|{s}"] += 1
                    continue
                rows[("ORIGINAL", d)][s] = c
                if s == "COCKTAIL":
                    diag.append({"date": d, **diagnostics(c["w"], c["member"], x, top10.get(d, set()), cik)})
        for d, x in rest.items():
            for s in strats:
                c = cohort(close_aug, qqq, x, s, d, H, RCMP.WINDOW_END)
                if c is None:
                    continue
                if "unresolved" in c:
                    unres[f"RESTORED|{s}"] += 1
                    continue
                rows[("RESTORED", d)][s] = c
        cell = {"unresolved": dict(unres), "blockWeeks": FU.spec_block(H)}
        rdates = sorted(d for (lab, d), v in rows.items() if lab == "RESTORED" and len(v) == len(strats))
        samples = {
            "FULL_ORIGINAL": sorted(d for (lab, d), v in rows.items() if lab == "ORIGINAL" and len(v) == len(strats)),
            "ORIGINAL_ON_RESTORED_DATES": [d for d in rdates if len(rows.get(("ORIGINAL", d), {})) == len(strats)],
            "RESTORED": rdates}
        samples["EXIT_BY_2022"] = [d for d in samples["FULL_ORIGINAL"] if rows[("ORIGINAL", d)]["COCKTAIL"]["exit"] <= EXIT_2022]
        samples["ENTRY_FROM_2023"] = [d for d in samples["FULL_ORIGINAL"] if rows[("ORIGINAL", d)]["COCKTAIL"]["entry"] >= ENTRY_2023]
        samples["RESTORED"] = [d for d in samples["RESTORED"] if d in samples["ORIGINAL_ON_RESTORED_DATES"]]
        for name, ds in samples.items():
            lab = "RESTORED" if name == "RESTORED" else "ORIGINAL"
            if not ds:
                continue
            R = {s: [rows[(lab, d)][s] for d in ds] for s in strats}
            c = {"cohorts": len(ds), "first": str(ds[0].date()), "last": str(ds[-1].date()),
                 "independentBlocks": round(len(ds) / FU.spec_block(H), 1)}
            for s in strats:
                c[s] = {"vsSPY": stats([x["net"] - x["spy"] for x in R[s]], H), "vsQQQ": stats([x["net"] - x["qqq"] for x in R[s]], H)["mean"],
                        "meanNet": float(np.mean([x["net"] for x in R[s]])), "meanGross": float(np.mean([x["gross"] for x in R[s]]))}
            c["SPY_meanNet"] = float(np.mean([x["spy"] for x in R["COCKTAIL"]]))
            c["QQQ_meanNet"] = float(np.mean([x["qqq"] for x in R["COCKTAIL"]]))
            c["confirmationIncrement"] = stats([a_["net"] - b_["net"] for a_, b_ in zip(R["COCKTAIL_CONFIRMED"], R["COCKTAIL"])], H)
            sleeves = SLEEVES["COCKTAIL"]
            ex = np.array([[x["net"] - x["spy"] for x in R[s]] for s in sleeves])
            c["mixing"] = {"averageSleeveExcess": float(ex.mean()), "averageSleeveIr": float(np.mean([c[s]["vsSPY"]["ir"] for s in sleeves])),
                           "cocktailIr": c["COCKTAIL"]["vsSPY"]["ir"], "averageSleeveSd": float(np.mean(ex.std(axis=1, ddof=1))),
                           "cocktailSd": c["COCKTAIL"]["vsSPY"]["sd"],
                           "sleeveExcessCorrelation": pd.DataFrame(ex.T, columns=sleeves).corr().round(3).to_dict()}
            cell[name] = c
        dg = pd.DataFrame(diag)
        if not dg.empty:
            dg["entry"] = [rows[("ORIGINAL", d)]["COCKTAIL"]["entry"] for d in dg["date"]]
            dg["exit"] = [rows[("ORIGINAL", d)]["COCKTAIL"]["exit"] for d in dg["date"]]
            out["diagnostics"][str(H)] = {
                w: {"effectiveNames": float(g["effectiveNames"].mean()), "top10Weight": float(g["top10Weight"].mean()),
                    "largestSectorWeight": float(g["largestSectorWeight"].mean()), "multiSleeveWeight": float(g["multiSleeveWeight"].mean()),
                    "largestSectorMostOften": g["largestSector"].value_counts().head(3).to_dict()}
                for w, g in (("FULL", dg), ("EXIT_BY_2022", dg[dg["exit"] <= EXIT_2022]), ("ENTRY_FROM_2023", dg[dg["entry"] >= ENTRY_2023])) if len(g)}
        out["fixed"][str(H)] = cell
        print(H, {n: (round(c["COCKTAIL"]["vsSPY"]["mean"], 4), round(c["COCKTAIL_CONFIRMED"]["vsSPY"]["mean"], 4)) for n, c in cell.items() if isinstance(c, dict) and "COCKTAIL" in c}, flush=True)
    if a.skip_ledgers:
        (OUT / "cocktail-fixed.json").write_text(json.dumps(out, indent=1, sort_keys=True, default=str) + "\n")
        return
    full_start, full_end = min(orig), close.index[-1]
    for every in (4, 26, 52):
        for s in ("COCKTAIL", "COCKTAIL_CONFIRMED", "PRICE", "SECTOR_MOMENTUM_BASKET", "WITHIN_SECTOR_VALUE", "CASH_PROFITABILITY"):
            out["ledgers"][f"ORIGINAL|{s}|L{every}|FULL"] = generic_ledger(close_aug, orig, s, every, full_start, full_end)
            out["ledgers"][f"ORIGINAL|{s}|L{every}|TO_2022"] = generic_ledger(close_aug, orig, s, every, full_start, EXIT_2022)
            out["ledgers"][f"ORIGINAL|{s}|L{every}|RESTORED_WINDOW"] = generic_ledger(close_aug, orig, s, every, full_start, RCMP.WINDOW_END)
            out["ledgers"][f"RESTORED|{s}|L{every}|RESTORED_WINDOW"] = generic_ledger(close_aug, rest, s, every, full_start, RCMP.WINDOW_END)
        print("ledger", every, {k: round(v.get("excess", np.nan), 4) for k, v in out["ledgers"].items() if f"L{every}|" in k and "COCKTAIL" in k}, flush=True)
    (OUT / "cocktail.json").write_text(json.dumps(out, indent=1, sort_keys=True, default=str) + "\n")


if __name__ == "__main__":
    main()
