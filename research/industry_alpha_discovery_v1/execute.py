"""Stage C: the single registered exploratory execution of H1-H3.

    python -m research.industry_alpha_discovery_v1.execute --private <dir with prices/>

Refuses to run unless authorization.json exists, names the sealed protocol SHA-256 and the hash of every input and
code file it covers, and results/ holds no earlier result. Writes results/result.json and results/tables.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from research.industry_alpha_discovery_v1 import engine as E
from research.industry_alpha_discovery_v1 import signals as SG

HERE = Path(__file__).resolve().parent
P = json.loads((HERE / "protocol.json").read_text())
H_ALL = P["horizonsSessions"]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def check_authorization():
    auth = json.loads((HERE / "authorization.json").read_text())
    if sha(HERE / "protocol.json") != auth["protocolSha256"]:
        raise SystemExit("PROTOCOL_CHANGED")
    for rel, h in {**auth["codeSha256"], **auth["inputSha256"]}.items():
        if sha(HERE.parents[1] / rel) != h:
            raise SystemExit(f"FILE_CHANGED {rel}")
    if (HERE / "results" / "result.json").exists():
        raise SystemExit("ALREADY_EXECUTED: a second run is forbidden by the protocol")
    return auth


def load_market(private: Path) -> E.Market:
    frames = {}
    for t in json.loads((HERE / "data" / "price-manifest.json").read_text()):
        p = private / "prices" / f"{t.replace('^', '_')}.csv"
        df = pd.read_csv(p, parse_dates=["date"]).set_index("date")
        frames[t] = df["adjclose"]
    closes = pd.DataFrame(frames)
    closes = closes[closes.index >= pd.Timestamp(P["calendar"]["start"]) - pd.Timedelta(days=400)]
    closes = closes[closes.index <= pd.Timestamp(P["calendar"]["dataCutoff"])]
    return E.Market(closes)


def momentum(mkt: E.Market, names, i: int, n: int):
    return None if i - n - 1 < 0 else mkt.excess(names, i - n - 1, i - 1)


def spacing(idx: list[int]) -> float:
    d = np.diff(sorted(idx))
    return float(np.median(d)) if len(d) else float("nan")


def test(df: pd.DataFrame, ycol: str, on: str, controls: list[str], H: int, sp: float) -> dict:
    d = df.dropna(subset=[ycol, on] + controls)
    lags = int(math.ceil(H / sp)) if sp and sp > 0 else 1
    n_on, n_off = int(d[on].sum()), int((1 - d[on]).sum())
    base = {"n": len(d), "nOn": n_on, "nOff": n_off, "horizon": H, "medianSpacingSessions": sp,
            "independentObs": float(min(len(d), len(d) * sp / H)) if len(d) else 0.0}
    if len(d) < 24 or n_on < 8 or n_off < 8:
        return base | {"status": "NOT_ESTIMABLE"}
    r = E.ols_hac(d[ycol].to_numpy(), d[[on] + controls].to_numpy(float), lags)
    r0 = E.ols_hac(d[ycol].to_numpy(), d[[on]].to_numpy(float), lags)
    bb = E.block_bootstrap_diff(d[ycol].to_numpy(), d[on].astype(bool).to_numpy(), lags + 1)
    return base | {"status": "ESTIMATED", "coefOn": r["coef"][1], "seOn": r["se"][1], "pOn": r["p"][1], "ciOn": r["ci95"][1],
                   "controls": controls, "lags": lags, "coefOnNoControls": r0["coef"][1], "pOnNoControls": r0["p"][1],
                   "meanOn": float(d.loc[d[on] == 1, ycol].mean()), "meanOff": float(d.loc[d[on] == 0, ycol].mean()),
                   "blockBootstrapOnMinusOff": bb}


def add_outcomes(mkt: E.Market, df: pd.DataFrame, names, prefix="") -> pd.DataFrame:
    for H in H_ALL:
        df[f"{prefix}xs{H}"] = [None if i is None else mkt.excess(names, int(i), int(i) + H) for i in df["entryIdx"]]
        df[f"{prefix}abs{H}"] = [None if i is None else mkt.absolute(names, int(i), int(i) + H) for i in df["entryIdx"]]
    return df


def strategies(mkt: E.Market, names, df: pd.DataFrame, rules: dict[str, pd.Series], tilt: float) -> dict:
    d = df.dropna(subset=["entryIdx"]).copy()
    start = int(d["entryIdx"].min())
    out = {}
    b0 = E.tilt_path(mkt, names, pd.DataFrame({"entryIdx": [start], "on": [False]}), tilt, start=start)
    s0 = E.path_stats(b0["nav"])
    out["B0"] = s0 | {"turnover": 0.0, "shareOn": 0.0}
    for k, on in rules.items():
        dec = pd.DataFrame({"entryIdx": d["entryIdx"].astype(int), "on": on.loc[d.index].fillna(False).astype(bool)})
        pth = E.tilt_path(mkt, names, dec, tilt, start=start)
        st = E.path_stats(pth["nav"])
        out[k] = st | {"turnover": pth["turnover"], "shareOn": pth["shareOn"], "cagrMinusB0": st["cagr"] - s0["cagr"],
                       "_nav": pth["nav"]}
    for k in list(out):
        if k not in ("B0", "P") and "P" in out and "_nav" in out[k]:
            diff = (out[k]["_nav"].pct_change() - out["P"]["_nav"].pct_change()).dropna()
            out[k]["annualisedDailyDiffVsP"] = float(diff.mean() * 252)
            # 63-session block bootstrap of the annualised mean daily difference vs P
            x = diff.to_numpy()
            rng = np.random.default_rng(20261122)
            b = 63
            draws = []
            for _ in range(2000):
                idx = np.concatenate([np.arange(s, s + b) for s in rng.integers(0, len(x) - b, math.ceil(len(x) / b))])[:len(x)]
                draws.append(x[idx].mean() * 252)
            out[k]["vsPci95"] = [float(np.quantile(draws, .025)), float(np.quantile(draws, .975))]
    for k in out:
        out[k].pop("_nav", None)
    return out


# ---------------------------------------------------------------- H1
def run_h1(mkt: E.Market, flash: pd.DataFrame, monthly: pd.DataFrame) -> dict:
    ev = SG.flash_surprises(flash, monthly)
    semi = P["baskets"]["SEMI"]
    ev["entryIdx"] = [mkt.entry_session(p) for p in ev["published"]]
    ev["entryIdxSameDay"] = [mkt.entry_session(p, same_day=True) for p in ev["published"]]
    ev = ev.dropna(subset=["entryIdx"]).reset_index(drop=True)
    ev["ON"] = (ev["surprise"] > 0).astype(int)
    ev["LVL"] = (ev["yoy"] > 0).astype(int)
    ev["mom63"] = [momentum(mkt, semi, int(i), 63) for i in ev["entryIdx"]]
    ev = add_outcomes(mkt, ev, semi)
    pub_idx = ev["entryIdxSameDay"].astype(int)
    ev["announceXs"] = [mkt.excess(semi, i - 1, i) if mkt.sessions[i] == pd.Timestamp(p) else None
                        for i, p in zip(pub_idx, ev["published"])]
    sp = spacing(ev["entryIdx"].astype(int).tolist())
    res = {"events": len(ev), "families": ev["family"].value_counts().to_dict(),
           "firstEvent": str(ev["published"].min().date()), "lastEvent": str(ev["published"].max().date()),
           "medianSpacingSessions": sp, "surpriseSummary": ev["surprise"].describe().to_dict(),
           "shareSurprisePositive": float(ev["ON"].mean())}
    ctrl = ["mom63", "LVL"]
    res["tests"] = {f"H{H}": test(ev, f"xs{H}", "ON", ctrl, H, sp) for H in H_ALL}
    res["absoluteMeans"] = {f"H{H}": {"on": float(ev.loc[ev.ON == 1, f"abs{H}"].astype(float).mean()),
                                      "off": float(ev.loc[ev.ON == 0, f"abs{H}"].astype(float).mean()),
                                      "all": float(ev[f"abs{H}"].astype(float).mean())} for H in H_ALL}
    a = ev.dropna(subset=["announceXs"])
    res["announcementReaction"] = {"n": len(a), "slopeOnSurprise": E.ols_hac(a["announceXs"].to_numpy(float),
                                   a[["surprise"]].to_numpy(float), 1) if len(a) > 10 else None,
                                   "meanOn": float(a.loc[a.ON == 1, "announceXs"].mean()),
                                   "meanOff": float(a.loc[a.ON == 0, "announceXs"].mean())}
    rules = {"B1": pd.Series(True, index=ev.index), "P": ev["mom63"] > 0, "X": ev["yoy"] > 0, "S": ev["surprise"] > 0,
             "SP": (ev["surprise"] > 0) & (ev["mom63"] > 0)}
    res["strategies"] = strategies(mkt, semi, ev, rules, P["H1"]["strategies"]["tilt"])
    sens = {}
    for label, names in (("samsungOnly", ["005930.KS"]), ("hynixOnly", ["000660.KS"]), ("kodexSemi", ["091160.KS"])):
        e2 = add_outcomes(mkt, ev[["entryIdx", "ON", "LVL", "surprise"]].copy(), names, "s_")
        e2["mom63"] = [momentum(mkt, names, int(i), 63) for i in e2["entryIdx"]]
        sens[label] = {f"H{H}": test(e2, f"s_xs{H}", "ON", ctrl, H, sp) for H in (21, 126)}
    e3 = ev.copy()
    e3["entryIdx"] = e3["entryIdxSameDay"]
    e3 = add_outcomes(mkt, e3, semi, "sd_")
    sens["sameDayEntry"] = {f"H{H}": test(e3, f"sd_xs{H}", "ON", ctrl, H, sp) for H in (21, 126)}
    wd = ev.dropna(subset=["workingDaysPrior", "workingDaysCurrent"]).copy()
    wd["adj"] = (1 + wd["yoy"]) * wd["workingDaysPrior"].astype(float) / wd["workingDaysCurrent"].astype(float) - 1
    wd["ON"] = ((wd["adj"] - wd["priorYoy"]) > 0).astype(int)
    sens["workingDayAdjusted"] = {f"H{H}": test(wd, f"xs{H}", "ON", ctrl, H, spacing(wd["entryIdx"].astype(int).tolist()))
                                  for H in (21, 126)}
    for fam in ("FLASH10", "FLASH20"):
        f = ev[ev.family == fam]
        sens[fam] = {f"H{H}": test(f, f"xs{H}", "ON", ctrl, H, spacing(f["entryIdx"].astype(int).tolist())) for H in (21, 126)}
    res["sensitivities"] = sens
    res["eventTable"] = [{k: (str(v.date()) if isinstance(v, pd.Timestamp) else (None if v is None or (isinstance(v, float)
                         and math.isnan(v)) else v)) for k, v in r.items()}
                         for r in ev[["family", "refMonth", "published", "yoy", "priorSource", "priorYoy", "surprise",
                                      "mom63", "announceXs", "xs21", "xs126"]].to_dict("records")]
    return res


# ---------------------------------------------------------------- H2
def monthly_frame(mkt: E.Market, motie: pd.DataFrame, industry: str) -> pd.DataFrame:
    names = P["baskets"][industry]
    m = SG.monthly_signals(motie, industry)
    m["entryIdx"] = [mkt.entry_session(p) for p in m["published"]]
    m = m.dropna(subset=["entryIdx"]).reset_index(drop=True)
    m["ON"] = [None if a is None or (isinstance(a, float) and math.isnan(a)) else int(a > 0) for a in m["accel"]]
    m["mom126"] = [momentum(mkt, names, int(i), 126) for i in m["entryIdx"]]
    m["pre21"] = [momentum(mkt, names, int(i), 21) for i in m["entryIdx"]]
    m["pre63"] = [momentum(mkt, names, int(i), 63) for i in m["entryIdx"]]
    return add_outcomes(mkt, m, names)


def run_h2(mkt: E.Market, motie: pd.DataFrame, quarters: pd.DataFrame) -> dict:
    out = {}
    m = monthly_frame(mkt, motie, "SEMI")
    sp = spacing(m["entryIdx"].astype(int).tolist())
    ok = m.dropna(subset=["ON"])
    out["SEMI"] = {"releases": len(m), "withAccel": len(ok), "first": str(ok["published"].min().date()),
                   "last": str(ok["published"].max().date()), "shareAccelPositive": float(ok["ON"].mean()),
                   "medianSpacingSessions": sp,
                   "tests": {f"H{H}": test(m, f"xs{H}", "ON", ["mom126"], H, sp) for H in H_ALL},
                   "absoluteMeans": {f"H{H}": {"on": float(ok.loc[ok.ON == 1, f"abs{H}"].astype(float).mean()),
                                               "off": float(ok.loc[ok.ON == 0, f"abs{H}"].astype(float).mean())}
                                     for H in (126, 252)}}
    rules = {"B1": pd.Series(True, index=m.index), "P": m["mom126"] > 0, "X": m["g3"].astype(float) > 0,
             "A": m["accel"].astype(float) > 0, "AP": (m["accel"].astype(float) > 0) & (m["mom126"] > 0)}
    out["SEMI"]["strategies"] = strategies(mkt, P["baskets"]["SEMI"], m, rules, P["H2"]["strategies"]["tilt"])
    # priced-in diagnostic: monthly change in G3 vs the excess return over the 21/63 sessions before publication
    d = m.dropna(subset=["g3"]).copy()
    d["dg3"] = d["g3"].astype(float).diff()
    pr = {}
    for w in ("pre21", "pre63"):
        x = d.dropna(subset=["dg3", w])
        if len(x) > 10:
            pr[w] = {"n": len(x), "r2": float(np.corrcoef(x["dg3"], x[w].astype(float))[0, 1] ** 2)}
    out["SEMI"]["pricedInDiagnostic"] = pr
    # revisions
    rv = SG.revision_flips(motie, "SEMI")
    out["SEMI"]["revisions"] = {
        "g3Compared": int(rv["g3SignFlip"].notna().sum()), "g3SignFlips": int(rv["g3SignFlip"].fillna(False).sum()),
        "accelCompared": int(rv["accelSignFlip"].notna().sum()),
        "accelSignFlips": int(rv["accelSignFlip"].fillna(False).sum()),
        "flipMonths": rv.loc[rv["accelSignFlip"].fillna(False).astype(bool), "refMonth"].tolist()}
    # earnings link (descriptive)
    q = quarters.copy()
    q["available"] = pd.to_datetime(q["available"])
    tot = q.groupby(["fyear", "q"]).agg(op=("opIncomeTTM", "sum"), n=("opIncomeTTM", "count"),
                                        available=("available", "max")).reset_index()
    tot = tot[tot["n"] == 2].sort_values(["fyear", "q"])
    tot["opYoy"] = tot["op"] / tot["op"].shift(4) - 1
    tot["qEnd"] = [f"{y}-{3 * k:02d}" for y, k in zip(tot["fyear"], tot["q"])]
    link = m.merge(tot[["qEnd", "opYoy", "available"]], left_on="refMonth", right_on="qEnd").dropna(subset=["g3", "opYoy"])
    link["opYoyNext"] = link["opYoy"].shift(-1)
    lk = {"n": len(link)}
    if len(link) > 8:
        lk["corrG3_opYoySameQuarter"] = float(np.corrcoef(link["g3"].astype(float), link["opYoy"])[0, 1])
        x = link.dropna(subset=["opYoyNext", "accel"])
        lk["corrAccel_opYoyNextQuarter"] = float(np.corrcoef(x["accel"].astype(float), x["opYoyNext"])[0, 1])
        lk["exportReleaseLeadDaysMedian"] = float((link["available"] - pd.to_datetime(link["published"])).dt.days.median())
    out["SEMI"]["earningsLink"] = lk
    out["SEMI"]["monthTable"] = [{k: (str(v.date()) if isinstance(v, pd.Timestamp) else (None if v is None or (
        isinstance(v, float) and math.isnan(v)) else v)) for k, v in r.items()}
        for r in m[["refMonth", "published", "g3", "accel", "ON", "mom126", "xs126", "xs252"]].to_dict("records")]
    for ind in ("AUTO", "PETRO", "SHIP"):
        mm = monthly_frame(mkt, motie, ind)
        s2 = spacing(mm["entryIdx"].astype(int).tolist())
        out[ind] = {"releases": len(mm), "withAccel": int(mm["ON"].notna().sum()),
                    "tests": {f"H{H}": test(mm, f"xs{H}", "ON", ["mom126"], H, s2) for H in (21, 63, 126, 252)}}
    return out


# ---------------------------------------------------------------- H3
def run_h3(mkt: E.Market, iip: pd.DataFrame) -> dict:
    s = iip[iip["industry"] == "SEMI"].dropna(subset=["shipmentYoy", "inventoryYoy"]).copy()
    out = {"parsedMonths": len(s), "gateMinMonths": 60}
    if len(s) < 60:
        out["status"] = "NOT_ESTIMABLE_DATA_GATE"
        return out
    s["published"] = pd.to_datetime(s["published"])
    s["entryIdx"] = [mkt.entry_session(p) for p in s["published"]]
    s = s.dropna(subset=["entryIdx"]).sort_values("published").reset_index(drop=True)
    s["isi"] = s["shipmentYoy"].astype(float) - s["inventoryYoy"].astype(float)
    s["ON"] = (s["isi"] > 0).astype(int)
    names = P["baskets"]["SEMI"]
    s["mom126"] = [momentum(mkt, names, int(i), 126) for i in s["entryIdx"]]
    s = add_outcomes(mkt, s, names)
    sp = spacing(s["entryIdx"].astype(int).tolist())

    def state(r):
        if r.shipmentYoy > 0 and r.inventoryYoy < 0:
            return "NORMALIZING"
        if r.productionYoy is not None and r.productionYoy > 0 and r.inventoryYoy > 0:
            return "SUPPLY_EXPANSION"
        if r.shipmentYoy <= 0 and r.inventoryYoy > 0:
            return "DEMAND_WEAKENING"
        return "OTHER"
    s["state"] = [state(r) for r in s.itertuples()]
    out |= {"status": "ESTIMATED", "first": str(s["published"].min().date()), "last": str(s["published"].max().date()),
            "layouts": s["layout"].value_counts().to_dict(),
            "tests": {f"H{H}": test(s, f"xs{H}", "ON", ["mom126"], H, sp) for H in H_ALL},
            "byState": {st: {"n": int((s.state == st).sum()),
                             "meanXs126": float(s.loc[s.state == st, "xs126"].astype(float).mean()),
                             "meanXs252": float(s.loc[s.state == st, "xs252"].astype(float).mean())}
                        for st in s["state"].unique()}}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", required=True)
    a = ap.parse_args(argv)
    auth = check_authorization()
    mkt = load_market(Path(a.private))
    d = HERE / "data"
    motie = pd.read_csv(d / "motie-items-by-release.csv")
    motie["published"] = pd.to_datetime(motie["published"])
    flash = pd.read_csv(d / "customs-flash-items.csv")
    iip = pd.read_csv(d / "iip-industry-yoy.csv")
    quarters = pd.read_csv(HERE.parent / "investment_decision_alpha_v1" / "results" / "kr-semis-case-quarters.csv")
    monthly = SG.monthly_signals(motie, "SEMI")
    res = {"studyId": P["studyId"], "evidenceClass": P["evidenceClass"], "authorizationId": auth["authorizationId"],
           "protocolSha256": auth["protocolSha256"],
           "sessions": {"first": str(mkt.sessions[0].date()), "last": str(mkt.sessions[-1].date())},
           "H1": run_h1(mkt, flash, monthly), "H2": run_h2(mkt, motie, quarters), "H3": run_h3(mkt, iip)}
    prim = {"H1-21": res["H1"]["tests"]["H21"], "H1-126": res["H1"]["tests"]["H126"],
            "H2-126": res["H2"]["SEMI"]["tests"]["H126"], "H2-252": res["H2"]["SEMI"]["tests"]["H252"]}
    sec = {"H2X-AUTO-126": res["H2"]["AUTO"]["tests"]["H126"], "H2X-PETRO-126": res["H2"]["PETRO"]["tests"]["H126"],
           "H2X-SHIP-126": res["H2"]["SHIP"]["tests"]["H126"]}
    if res["H3"].get("status") == "ESTIMATED":
        sec |= {"H3-SEMI-126": res["H3"]["tests"]["H126"], "H3-SEMI-252": res["H3"]["tests"]["H252"]}
    verdict = {}
    for fam, tests in (("primary", prim), ("secondary", sec)):
        pv = {k: (t["pOn"] if t.get("status") == "ESTIMATED" else 1.0) for k, t in tests.items()}
        adj = E.holm(pv)
        verdict[fam] = {k: {"coefOn": t.get("coefOn"), "ciOn": t.get("ciOn"), "p": pv[k], "holmP": adj[k],
                            "status": t.get("status"),
                            "supported": bool(t.get("status") == "ESTIMATED" and adj[k] < 0.05 and t["coefOn"] > 0)}
                        for k, t in tests.items()}
    res["verdict"] = verdict
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n")
    print(json.dumps(verdict, ensure_ascii=False, indent=1, default=float))


if __name__ == "__main__":
    main()
