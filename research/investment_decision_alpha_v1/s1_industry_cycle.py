"""S1 (PREREGISTRATION.md section 1): US industry capex cycle - late-boom avoidance and capacity-cut recovery.

    python -m research.investment_decision_alpha_v1.s1_industry_cycle --private <dir with us/{close,features,filings}.pkl> --out <results dir>

`--private` must point at the #353-corrected copy written by `lineage_353_354` (marketCap of the 943 verified rows replaced).
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from research.alpha_search_round6_v1 import common as CM
from research.alpha_search_round6_v1 import us as R6
from research.us_selection_value_v1 import evaluate as EV
from research.us_selection_value_v1 import restored_compare as RCMP

HERE = Path(__file__).resolve().parent
AI_LED = pd.Timestamp("2023-01-01")
HS = (126, 252)
RANDOM_DRAWS, RANDOM_SEED = 200, 20261121
MIN_MEMBERS = 3


def boot(v, H, two=False):
    r = CM.boot(v, max(1, int(round(H / 5))))
    if two and r.get("pOneSided") is not None:
        p = r["pOneSided"]
        r["pTwoSided"] = min(1.0, 2 * min(p, 1 - p + 1 / (CM.B + 1)))
    return r


def sic_map(path: Path) -> dict:
    s = pd.read_csv(path, dtype=str).fillna("")
    s = s[s["sic"].str.fullmatch(r"\d{3,4}")]
    return {r.ticker: r.sic.zfill(4) for r in s.itertuples()}


def industry_keys(g: pd.DataFrame, sic: dict) -> pd.Series:
    """SIC3 where it has >= 3 capex-valid members, else SIC2 pooled over the small SIC3 groups, else dropped."""
    code = g.index.map(lambda t: sic.get(t))
    g = g.assign(sic4=code).dropna(subset=["sic4"])
    valid = (g["capexTTM"].abs() > 0) & (g["capexTTMPrior"].abs() > 0)
    s3 = g["sic4"].str[:3]
    n3 = valid.groupby(s3).sum()
    key = s3.where(s3.map(n3) >= MIN_MEMBERS, "2:" + g["sic4"].str[:2])
    small = key.str.startswith("2:")
    n2 = valid[small].groupby(key[small]).sum()
    key = key.where(~small | key.map(n2).fillna(0).ge(MIN_MEMBERS))
    return key.where(~small | key.notna()).dropna()


def states(feats: pd.DataFrame, sic: dict) -> dict:
    out = {}
    for d, g in feats.groupby("date"):
        g = g[g["identity"].isin(["MEMBERSHIP_CIK", "PIT_SINGLE_CIK"])].set_index("ticker")
        for c in ("capexTTM", "capexTTMPrior", "revenueTTM", "revenueTTMPrior", "marketCap", "momentum252", "operatingProfitabilityToAssets"):
            g[c] = pd.to_numeric(g[c], errors="coerce")
        g = g[g["marketCap"] > 0]
        key = industry_keys(g, sic)
        g = g.loc[key.index].assign(ind=key)
        rows = {}
        for k, m in g.groupby("ind"):
            cv = m[(m["capexTTM"].abs() > 0) & (m["capexTTMPrior"].abs() > 0)]
            rv = m[(m["revenueTTM"] > 0) & (m["revenueTTMPrior"] > 0)]
            w = m["marketCap"] / m["marketCap"].sum()
            rows[k] = {"capexG": cv["capexTTM"].abs().sum() / cv["capexTTMPrior"].abs().sum() - 1 if len(cv) >= MIN_MEMBERS else np.nan,
                       "revG": rv["revenueTTM"].sum() / rv["revenueTTMPrior"].sum() - 1 if len(rv) >= MIN_MEMBERS else np.nan,
                       "mom": float((w * m["momentum252"]).sum()), "prof": float(m["operatingProfitabilityToAssets"].median()),
                       "n": len(m), "sector": m["sector"].mode().iloc[0], "members": list(m.index),
                       "caps": m["marketCap"].to_dict()}
        if not rows:
            continue
        s = pd.DataFrame(rows).T
        s = s[s["capexG"].notna()]
        if len(s) < 9:
            continue
        for c in ("capexG", "revG", "mom", "prof"):
            s[c] = s[c].astype(float)
        s["capexQ"] = pd.qcut(s["capexG"].rank(method="first"), 3, labels=False)
        s["momQ"] = pd.qcut(s["mom"].rank(method="first"), 3, labels=False)
        s["BOOM"] = (s["capexQ"] == 2) & (s["momQ"] == 2)
        s["CUT"] = s["capexQ"] == 0
        out[pd.Timestamp(d)] = s
    return out


def industry_returns(close, st, H):
    rows = []
    idx = close.index
    for d, s in st.items():
        pos = idx.get_loc(d)
        if pos + 1 + H >= len(idx):
            continue
        e, z = idx[pos + 1], idx[pos + 1 + H]
        spy = float(close.at[z, "SPY"] / close.at[e, "SPY"] - 1)
        for k, r in s.iterrows():
            names = [t for t in r["members"] if t in close.columns]
            px = close.loc[[e, z], names]
            rr = (px.iloc[1] / px.iloc[0] - 1).dropna()
            w = pd.Series(r["caps"]).reindex(rr.index)
            if rr.empty or w.sum() <= 0:
                continue
            rows.append({"date": d, "ind": k, "sector": r["sector"], "excess": float((rr * w).sum() / w.sum()) - spy,
                         "missingCapShare": 1 - float(w.sum() / sum(r["caps"].values())),
                         "capexQ": int(r["capexQ"]), "momQ": int(r["momQ"]), "BOOM": bool(r["BOOM"]), "CUT": bool(r["CUT"]),
                         "year": d.year})
    return pd.DataFrame(rows)


def spread(df, a, b, H):
    """Per-date mean of group a minus group b (equal weight over industries), then block bootstrap over dates."""
    g = df.groupby("date")
    s = pd.DataFrame({"a": g.apply(lambda x: x.loc[a(x), "excess"].mean()), "b": g.apply(lambda x: x.loc[b(x), "excess"].mean())}).dropna()
    v = s["a"] - s["b"]
    out = {"all": boot(v.values, H), "aMean": float(s["a"].mean()), "bMean": float(s["b"].mean()), "dates": int(len(v))}
    out["BEFORE_2023"] = boot(v[v.index < AI_LED].values, H)
    out["FROM_2023"] = boot(v[v.index >= AI_LED].values, H)
    yearly = v.groupby(v.index.year).mean()
    best = int(yearly.idxmax())
    out["dropBestYear"] = {"year": best, **boot(v[v.index.year != best].values, H)}
    out["byYear"] = {int(k): float(x) for k, x in yearly.items()}
    return out, v


def within_sector(df, H):
    d = df.copy()
    d["excess"] = d["excess"] - d.groupby(["date", "sector"])["excess"].transform("mean")
    d = d[d.groupby(["date", "sector"])["ind"].transform("count") >= 2]
    return spread(d, lambda x: x["capexQ"] == 0, lambda x: x["capexQ"] == 2, H)[0]


def profit_change(st):
    """IC-A: change of an industry's median operating profitability over the next 52 weekly dates, same key."""
    dates = sorted(st)
    rows = []
    for i, d in enumerate(dates):
        if i + 52 >= len(dates):
            break
        later = st[dates[i + 52]]
        s = st[d]
        common = s.index.intersection(later.index)
        for k in common:
            rows.append({"date": d, "capexQ": int(s.at[k, "capexQ"]), "dProf": float(later.at[k, "prof"] - s.at[k, "prof"]),
                         "dRevG": float(later.at[k, "revG"] - s.at[k, "revG"]) if pd.notna(later.at[k, "revG"]) and pd.notna(s.at[k, "revG"]) else np.nan})
    df = pd.DataFrame(rows)
    out = {}
    for col in ("dProf", "dRevG"):
        g = df.dropna(subset=[col]).groupby("date")
        s = pd.DataFrame({"top": g.apply(lambda x: x.loc[x.capexQ == 2, col].mean()), "bot": g.apply(lambda x: x.loc[x.capexQ == 0, col].mean())}).dropna()
        v = s["top"] - s["bot"]
        out[col] = {"all": boot(v.values, 252, two=True), "topMean": float(s["top"].mean()), "botMean": float(s["bot"].mean()),
                    "BEFORE_2023": boot(v[v.index < AI_LED].values, 252, two=True),
                    "FROM_2023": boot(v[v.index >= AI_LED].values, 252, two=True)}
    return out


# --------------------------------------------------------------------------- IC-4 behaviour test on the BASE book
def w20(names):
    b = {t: 0.2 for t in names}
    if len(names) < 5:
        b["SPY"] = b.get("SPY", 0) + 1 - 0.2 * len(names)
    return b


def boom_members(st, d):
    s = st.get(d)
    if s is None:
        return None
    return {t for m in s.loc[s["BOOM"], "members"] for t in m}


def books(secs, st):
    base, excl, kdrop, cand = {}, {}, {}, {}
    for d, x in secs.items():
        bm = boom_members(st, d)
        if bm is None:
            continue
        base[d] = w20(EV.book(x, "PRICE_CONFIRMED", "TOP5"))
        y = x.copy()
        hit = y.index.isin(list(bm)) & y["PRICE_CONFIRMED"].notna()
        y.loc[hit, "PRICE_CONFIRMED"] = np.nan
        excl[d] = w20(EV.book(y, "PRICE_CONFIRMED", "TOP5"))
        kdrop[d] = int(hit.sum())
        cand[d] = sorted(x.index[x["PRICE_CONFIRMED"].notna()])
    return base, excl, kdrop, cand


def random_books(secs, kdrop, cand, draw):
    rng = np.random.default_rng([RANDOM_SEED, draw])
    out = {}
    for d in sorted(kdrop):
        x = secs[d]
        drop = rng.choice(cand[d], size=min(kdrop[d], len(cand[d])), replace=False) if kdrop[d] else []
        y = x.copy()
        y.loc[y.index.isin(list(drop)), "PRICE_CONFIRMED"] = np.nan
        out[d] = w20(EV.book(y, "PRICE_CONFIRMED", "TOP5"))
    return out


def cohort_series(close, qqq, bk, H):
    s = {}
    for d, w in bk.items():
        c = R6.cohort_w(close, qqq, w, d, H)
        if c is None or "unresolved" in c:
            continue
        s[d] = c["net"] - c["spy"]
    return pd.Series(s).sort_index()


def behaviour(close, qqq, secs, st):
    base, excl, kdrop, cand = books(secs, st)
    out = {"datesWithBoomCandidates": int(sum(v > 0 for v in kdrop.values())), "dates": len(kdrop),
           "meanDroppedCandidates": float(np.mean(list(kdrop.values()))),
           "bookChangedDates": int(sum(set(base[d]) != set(excl[d]) for d in base))}
    for H in HS:
        sb, se = cohort_series(close, qqq, base, H), cohort_series(close, qqq, excl, H)
        idx = sb.index.intersection(se.index)
        diff = (se - sb).reindex(idx)
        cell = {"exclMinusBase": boot(diff.values, H), "baseVsSpy": boot(sb.reindex(idx).values, H), "exclVsSpy": boot(se.reindex(idx).values, H),
                "BEFORE_2023": boot(diff[diff.index < AI_LED].values, H), "FROM_2023": boot(diff[diff.index >= AI_LED].values, H)}
        draws = []
        for k in range(RANDOM_DRAWS):
            sr = cohort_series(close, qqq, random_books(secs, kdrop, cand, k), H).reindex(idx)
            draws.append(float((sr - sb.reindex(idx)).mean()))
        draws = np.array(draws)
        cell["randomDropMinusBase"] = {"mean": float(draws.mean()), "p05": float(np.quantile(draws, .05)), "p95": float(np.quantile(draws, .95)),
                                       "exclPercentile": float((draws < diff.mean()).mean())}
        out[str(H)] = cell
        print("IC-4", H, round(diff.mean() * 100, 3), cell["randomDropMinusBase"], flush=True)
    for every in (26,):
        start = min(base)
        out[f"L{every}"] = {"BASE": R6.ledger_w(close, base, every, start, close.index[-1]),
                            "BOOM_EXCLUDED": R6.ledger_w(close, excl, every, start, close.index[-1])}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", required=True)
    ap.add_argument("--out", default=str(HERE / "results"))
    ap.add_argument("--sic", default=str(HERE / "inputs" / "us-sic.csv"))
    a = ap.parse_args(argv)
    P, OUT = Path(a.private), Path(a.out)
    close, feats, qqq, _ = EV.load(P / "us")
    feats["date"] = pd.to_datetime(feats["date"])
    sic = sic_map(Path(a.sic))
    st = states(feats, sic)
    print("states", len(st), "median industries", int(np.median([len(s) for s in st.values()])), flush=True)
    res = {"studyId": "investment-decision-alpha-v1/S1", "label": "EXPLORATORY_ON_OUTCOME_EXPOSED_HISTORY",
           "industryDefinition": "SEC SIC current assignment (not dated), SIC3 with SIC2 pooling, >=3 capex-valid members",
           "coverage": {"tickersWithSic": len(sic), "featureTickers": int(feats["ticker"].nunique()),
                        "datesWithState": len(st), "industriesPerDate": {"median": float(np.median([len(s) for s in st.values()])),
                                                                         "min": int(min(len(s) for s in st.values()))},
                        "boomIndustriesPerDate": float(np.mean([s["BOOM"].sum() for s in st.values()])),
                        "sic2Pooled": float(np.mean([s.index.str.startswith("2:").mean() for s in st.values()]))}}
    res["IC_A"] = profit_change(st)
    for H in HS:
        df = industry_returns(close, st, H)
        cell = {"industryDates": int(len(df)), "meanMissingCapShare": float(df["missingCapShare"].mean())}
        cell["IC_1"], v1 = spread(df, lambda x: x["capexQ"] == 0, lambda x: x["capexQ"] == 2, H)
        cell["IC_2"], _ = spread(df, lambda x: ~x["BOOM"], lambda x: x["BOOM"], H)
        cell["IC_3"] = within_sector(df, H)
        cell["CUT_LOWMOM_vsRest"], _ = spread(df, lambda x: x["CUT"] & (x["momQ"] == 0), lambda x: ~(x["CUT"] & (x["momQ"] == 0)), H)
        cell["exInfoTech_IC_1"], _ = spread(df[df["sector"] != "Information Technology"], lambda x: x["capexQ"] == 0, lambda x: x["capexQ"] == 2, H)
        cell["exInfoTech_IC_2"], _ = spread(df[df["sector"] != "Information Technology"], lambda x: ~x["BOOM"], lambda x: x["BOOM"], H)
        cell["boomShareBySector"] = {k: int(v) for k, v in Counter(df.loc[df["BOOM"], "sector"]).most_common()}
        res[str(H)] = cell
        df.to_pickle(P / f"s1-industry-returns-{H}.pkl")
        print(H, "IC1", round(cell["IC_1"]["all"]["mean"] * 100, 2), cell["IC_1"]["all"].get("ci"),
              "IC2", round(cell["IC_2"]["all"]["mean"] * 100, 2), cell["IC_2"]["all"].get("ci"), flush=True)
    semi = []
    for d, s in st.items():
        for k in [k for k in s.index if k.startswith("367")]:
            semi.append({"date": str(d.date()), "ind": k, "capexG": float(s.at[k, "capexG"]), "revG": float(s.at[k, "revG"]) if pd.notna(s.at[k, "revG"]) else None,
                         "mom": float(s.at[k, "mom"]), "BOOM": bool(s.at[k, "BOOM"]), "capexQ": int(s.at[k, "capexQ"]), "n": int(s.at[k, "n"])})
    pd.DataFrame(semi).to_csv(OUT / "s1-semiconductor-367-state.csv", index=False)
    (OUT / "s1-industry-cycle.json").write_text(json.dumps(res, indent=1, sort_keys=True, default=str) + "\n")
    secs = RCMP.sections_of(feats)
    res["IC_4"] = behaviour(close, qqq, secs, st)
    (OUT / "s1-industry-cycle.json").write_text(json.dumps(res, indent=1, sort_keys=True, default=str) + "\n")
    print("done", flush=True)


if __name__ == "__main__":
    main()
