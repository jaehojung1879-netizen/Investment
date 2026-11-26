"""POST-HOC DESCRIPTIVE diagnostics, written AFTER results/result.json existed. Not preregistered; no verdict.

    python -m research.industry_alpha_discovery_v1.posthoc --private <dir with prices/>

They read the same inputs with the same engine and only decompose what the registered run already showed:
  1. timing vs average exposure: each tilt strategy against a STATIC tilt equal to its own average sleeve weight
     (the MVMA-v1 lesson: a CAGR gap can be mostly an exposure gap);
  2. H2 by sub-period (2013-07..2019-12 / 2020-01..2026-11) and by name (Samsung, SK Hynix, KODEX 반도체);
  3. ON/OFF mean excess by calendar year for H1 and H2 (where it worked and where it failed).
None of this can promote, rescue or refute a registered claim. results/result.json is never touched.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from research.industry_alpha_discovery_v1 import engine as E
from research.industry_alpha_discovery_v1 import execute as X
from research.industry_alpha_discovery_v1 import signals as SG

HERE = Path(__file__).resolve().parent
LABEL = "POST_HOC_DESCRIPTIVE_NOT_PREREGISTERED"


def sleeve_path(mkt, names, entry_idx, targets, start):
    """NAV and daily sleeve weight when the sleeve is reset to `targets[k]` at every decision `entry_idx[k]`
    (costs as in the engine). With a constant target this is a fixed-exposure comparator."""
    tgt = dict(zip(entry_idx, targets))
    cols = [mkt.bench] + list(names)
    px = mkt.close[cols].iloc[start:].to_numpy(float)
    rets = px[1:] / px[:-1] - 1
    w = [1.0] + [0.0] * len(names)
    nav, navs, sleeve = 1.0, [1.0], []
    dates = mkt.sessions[start:]
    for t in range(len(dates)):
        gi = start + t
        if gi in tgt:
            target = [1 - tgt[gi]] + [tgt[gi] / len(names)] * len(names)
            delta = [a - b for a, b in zip(target, w)]
            nav *= 1 - (E.etf_cost(delta[0]) + sum(E.stock_cost(x, dates[t]) for x in delta[1:]))
            w = target
            navs[-1] = nav
        if t < len(rets):
            g = [wi * (1 + r) for wi, r in zip(w, rets[t])]
            tot = sum(g)
            nav *= tot
            w = [x / tot for x in g]
            navs.append(nav)
            sleeve.append(sum(w[1:]))
    return pd.Series(navs, index=dates), float(sum(sleeve) / len(sleeve))


def static_vs_timing(mkt, names, df, rules, tilt):
    """Timed tilt (reset to 30% / 0% at every decision) against a FIXED tilt equal to its share-ON x 30%, reset at
    the same decision dates. Also the realised average sleeve weight of the registered drifting paths."""
    d = df.dropna(subset=["entryIdx"])
    start = int(d["entryIdx"].min())
    idx = d["entryIdx"].astype(int).tolist()
    out = {}
    drift = E.tilt_path(mkt, names, pd.DataFrame({"entryIdx": [start], "on": [True]}), tilt, start=start)
    _, b1w = sleeve_path(mkt, names, [start], [tilt], start)
    out["B1_registered_drifting"] = {"cagr": E.path_stats(drift["nav"])["cagr"]}
    for k, on in rules.items():
        flags = on.loc[d.index].fillna(False).astype(bool).tolist()
        timed, tw = sleeve_path(mkt, names, idx, [tilt if f else 0.0 for f in flags], start)
        share = sum(flags) / len(flags)
        fixed, fw = sleeve_path(mkt, names, idx, [tilt * share] * len(idx), start)
        a, b = E.path_stats(timed), E.path_stats(fixed)
        diff = (timed.pct_change() - fixed.pct_change()).dropna()
        out[k] = {"shareOfDecisionsOn": share, "timedResetCagr": a["cagr"], "fixedSameAverageTiltCagr": b["cagr"],
                  "timingEffectCagr": a["cagr"] - b["cagr"], "timingEffectArithAnnual": float(diff.mean() * 252),
                  "timedAvgSleeveWeight": tw, "fixedAvgSleeveWeight": fw, "timedMdd": a["mdd"], "fixedMdd": b["mdd"]}
    return out


def by_year(df, col):
    d = df.dropna(subset=[col, "ON"]).copy()
    d["year"] = pd.to_datetime(d["published"]).dt.year
    g = d.groupby(["year", "ON"])[col].agg(["mean", "count"]).unstack("ON")
    return {int(y): {"onMean": None if pd.isna(r.get(("mean", 1))) else float(r[("mean", 1)]),
                     "offMean": None if pd.isna(r.get(("mean", 0))) else float(r[("mean", 0)]),
                     "nOn": 0 if pd.isna(r.get(("count", 1))) else int(r[("count", 1)]),
                     "nOff": 0 if pd.isna(r.get(("count", 0))) else int(r[("count", 0)])} for y, r in g.iterrows()}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", required=True)
    a = ap.parse_args(argv)
    mkt = X.load_market(Path(a.private))
    d = HERE / "data"
    motie = pd.read_csv(d / "motie-items-by-release.csv")
    motie["published"] = pd.to_datetime(motie["published"])
    flash = pd.read_csv(d / "customs-flash-items.csv")
    semi = X.P["baskets"]["SEMI"]
    out = {"label": LABEL}

    m = X.monthly_frame(mkt, motie, "SEMI")
    out["H2timingVsExposure"] = static_vs_timing(
        mkt, semi, m, {"P": m["mom126"] > 0, "X": m["g3"].astype(float) > 0, "A": m["accel"].astype(float) > 0,
                       "AP": (m["accel"].astype(float) > 0) & (m["mom126"] > 0)}, .30)
    sp = X.spacing(m["entryIdx"].astype(int).tolist())
    halves = {"2013-07..2019-12": m["published"] < pd.Timestamp("2020-01-01"),
              "2020-01..2026-11": m["published"] >= pd.Timestamp("2020-01-01")}
    out["H2subperiods"] = {k: {f"H{H}": X.test(m[msk], f"xs{H}", "ON", ["mom126"], H, sp) for H in (21, 63, 126)}
                           for k, msk in halves.items()}
    names = {}
    for label, nm in (("samsungOnly", ["005930.KS"]), ("hynixOnly", ["000660.KS"]), ("kodexSemi", ["091160.KS"])):
        e = X.add_outcomes(mkt, m[["entryIdx", "ON", "published"]].copy(), nm, "s_")
        e["mom126"] = [X.momentum(mkt, nm, int(i), 126) for i in e["entryIdx"]]
        names[label] = {f"H{H}": X.test(e, f"s_xs{H}", "ON", ["mom126"], H, sp) for H in (21, 63, 126)}
    out["H2byName"] = names
    out["H2byYear21"] = by_year(m, "xs21")
    out["H2byYear126"] = by_year(m, "xs126")

    ev = SG.flash_surprises(flash, SG.monthly_signals(motie, "SEMI"))
    ev["entryIdx"] = [mkt.entry_session(p) for p in ev["published"]]
    ev = ev.dropna(subset=["entryIdx"]).reset_index(drop=True)
    ev["ON"] = (ev["surprise"] > 0).astype(int)
    ev["mom63"] = [X.momentum(mkt, semi, int(i), 63) for i in ev["entryIdx"]]
    ev = X.add_outcomes(mkt, ev, semi)
    out["H1timingVsExposure"] = static_vs_timing(
        mkt, semi, ev, {"P": ev["mom63"] > 0, "X": ev["yoy"] > 0, "S": ev["surprise"] > 0,
                        "SP": (ev["surprise"] > 0) & (ev["mom63"] > 0)}, .30)
    out["H1byYear21"] = by_year(ev, "xs21")
    out["H1byYear126"] = by_year(ev, "xs126")
    # how many H1 126-session windows were entirely inside 2024-2026 (the memory up-cycle)
    out["H1windowsAfter2024"] = int((pd.to_datetime(ev["published"]) >= pd.Timestamp("2024-01-01")).sum())
    (HERE / "results" / "posthoc.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float) + "\n")
    print(json.dumps({k: v for k, v in out.items() if "timing" in k.lower() or "Year" in k}, indent=1, default=float)[:5000])


if __name__ == "__main__":
    main()
