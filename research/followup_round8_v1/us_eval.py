"""US — disclosure beyond size and sector (PREREGISTRATION.md A2-A4), on the original (O), same-sample corrected (C1) and fully corrected (C2)
signal inputs built by us_audit.py.

    python -m research.followup_round8_v1.us_eval --private <dir> --out research/followup_round8_v1/results [--skip-ledgers]
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.active_fund_disclosure_v1 import evaluate_us as E  # noqa: E402
from research.alpha_search_round6_v1 import common as CM  # noqa: E402
from research.alpha_search_round6_v1 import us as R6  # noqa: E402
from research.us_selection_value_v1 import evaluate as EV  # noqa: E402
from research.us_selection_value_v1 import followup as FU  # noqa: E402
from research.us_selection_value_v1 import restored_compare as RCMP  # noqa: E402

MEGA = ("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "AVGO", "TSLA")
SEL = ("BASE", "CAP", "OW", "OW_RESID")
REFS = ("COCKTAIL", "U1")
PAIRS = {"OW_minus_BASE": ("OW", "BASE"), "CAP_minus_BASE": ("CAP", "BASE"), "P1_OW_minus_CAP": ("OW", "CAP"),
         "P2_OW_RESID_minus_BASE": ("OW_RESID", "BASE"), "OW_RESID_minus_CAP": ("OW_RESID", "CAP")}
MATCHED = {"OW_vs_ctrl": ("OW", "OW_CTRL"), "OW_RESID_vs_ctrl": ("OW_RESID", "OW_RESID_CTRL"), "BASE_vs_ctrl": ("BASE", "BASE_CTRL"),
           "CAP_vs_ctrl": ("CAP", "CAP_CTRL")}
OUT_DIR = Path(__file__).resolve().parent / "results"


def picks(x, ow):
    x = x.copy()
    x["OW"] = ow.reindex(x.index).fillna(0.0)
    cap = x["marketCap"].astype(float).rank(pct=True, method="average") >= 0.5
    owp = x["OW"].rank(pct=True, method="average") >= 0.5
    resid = x.groupby(["sector", "capTercile"])["OW"].rank(pct=True, method="average") >= 0.5
    p = {"BASE": EV.book(x, "PRICE_CONFIRMED", "TOP5"), "CAP": EV.book(E.masked(x, cap), "PRICE_CONFIRMED", "TOP5"),
         "OW": EV.book(E.masked(x, owp), "PRICE_CONFIRMED", "TOP5"), "OW_RESID": EV.book(E.masked(x, resid), "PRICE_CONFIRMED", "TOP5")}
    ctrl = {f"{k}_CTRL": (E.matched(x, v) if v else []) for k, v in p.items()}
    return x, p, ctrl


def cohort(close, qqq, w, d, H):
    pos = close.index.get_loc(d)
    if pos + 1 + H >= len(close):
        return None
    e, z = close.index[pos + 1], close.index[pos + 1 + H]
    r = close.loc[z, list(w)] / close.loc[e, list(w)] - 1
    if r.isna().any():
        return {"unresolved": True}
    ws = pd.Series(w)
    g = float((r * ws).sum())
    return {"entry": e, "net": EV.net(g), "mega": float((r * ws)[[t for t in ws.index if t in MEGA]].sum()),
            "megaWeight": float(ws[[t for t in ws.index if t in MEGA]].sum()),
            "spy": EV.net(float(close["SPY"].loc[z] / close["SPY"].loc[e] - 1)), "qqq": EV.net(float(qqq.loc[z] / qqq.loc[e] - 1))}


def run_variant(name, meta, active, secs, close, qqq):
    rows, books, avail = {126: [], 252: []}, {k: {} for k in SEL + tuple(f"{s}_CTRL" for s in SEL) + REFS}, []
    for d in sorted(secs):
        x0 = secs[d]
        ow, n = E.ow_breadth(meta, active, d, x0.index)
        if ow is None:
            continue
        x, p, ctrl = picks(x0, ow)
        coc = R6.sleeve_book(x, R6.EQUAL)
        b = {k: E.eq(v) for k, v in p.items()}
        b.update({k: (E.eq(v) if v is not None else None) for k, v in ctrl.items()})
        b["COCKTAIL"], b["U1"] = coc, R6.top5_neutral(x, coc)[0]
        logcap = np.log(x["marketCap"].astype(float))
        avail.append({"date": d, "nFunds": n, **{f"{k}_matched": v is not None for k, v in ctrl.items()},
                      **{f"{k}_n": len(v) for k, v in p.items()}, **{f"{k}_logCap": float(logcap[v].mean()) if v else np.nan for k, v in p.items()},
                      **{f"{k}_overlapBASE": len(set(v) & set(p["BASE"])) for k, v in p.items()}})
        for k, v in b.items():
            if v is not None:
                books[k][d] = v
        for H in (126, 252):
            cs = {k: (cohort(close, qqq, v, d, H) if v is not None else None) for k, v in b.items()}
            if cs["BASE"] is None or any(c is not None and "unresolved" in c for c in cs.values()):
                continue
            row = {"date": d, "entry": cs["BASE"]["entry"], "spy": cs["BASE"]["spy"], "qqq": cs["BASE"]["qqq"]}
            for k, c in cs.items():
                row[f"{k}_net"] = c["net"] if c else np.nan
                row[f"{k}_mega"] = c["mega"] if c else np.nan
                row[f"{k}_megaW"] = c["megaWeight"] if c else np.nan
            rows[H].append(row)
    return {H: pd.DataFrame(v) for H, v in rows.items()}, books, pd.DataFrame(avail)


def summarise(df, H):
    block = FU.spec_block(H)
    out = {}
    for nm, s in {"FULL": df, "BEFORE_2023": df[df["entry"] < E.AI_LED], "AI_LED_FROM_2023": df[df["entry"] >= E.AI_LED]}.items():
        if s.empty:
            continue
        c = {"cohorts": int(len(s)), "first": str(s["date"].iloc[0].date()), "last": str(s["date"].iloc[-1].date())}
        c["vsSPY"] = {k: CM.boot((s[f"{k}_net"] - s["spy"]).dropna().tolist(), block) for k in SEL + REFS}
        c["vsQQQ"] = {k: float((s[f"{k}_net"] - s["qqq"]).mean()) for k in SEL + REFS}
        c["pairs"] = {p: CM.boot((s[f"{a}_net"] - s[f"{b}_net"]).tolist(), block) for p, (a, b) in PAIRS.items()}
        m = s.dropna(subset=["OW_CTRL_net", "BASE_CTRL_net"])
        c["matchedSample"] = {"cohorts": int(len(m)), "shareOfCohorts": float(len(m) / len(s))}
        c["matched"] = {p: CM.boot((m[f"{a}_net"] - m[f"{b}_net"]).tolist(), block) for p, (a, b) in MATCHED.items()
                        if m[f"{b}_net"].notna().all()}
        c["matched"]["P3_OW_net_of_ctrl_minus_BASE_net_of_ctrl"] = CM.boot(
            ((m["OW_net"] - m["OW_CTRL_net"]) - (m["BASE_net"] - m["BASE_CTRL_net"])).tolist(), block)
        mr = s.dropna(subset=["OW_RESID_CTRL_net", "BASE_CTRL_net"])
        c["matched"]["OW_RESID_net_of_ctrl_minus_BASE_net_of_ctrl"] = CM.boot(
            ((mr["OW_RESID_net"] - mr["OW_RESID_CTRL_net"]) - (mr["BASE_net"] - mr["BASE_CTRL_net"])).tolist(), block)
        c["megaTech"] = {k: {"meanWeight": float(s[f"{k}_megaW"].mean()), "meanGrossContribution": float(s[f"{k}_mega"].mean())} for k in SEL + REFS}
        c["megaTech"]["OW_minus_CAP_contributionDiff"] = float((s["OW_mega"] - s["CAP_mega"]).mean())
        c["megaTech"]["OW_minus_BASE_contributionDiff"] = float((s["OW_mega"] - s["BASE_mega"]).mean())
        c["megaTech"]["OW_RESID_minus_BASE_contributionDiff"] = float((s["OW_RESID_mega"] - s["BASE_mega"]).mean())
        out[nm] = c
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", required=True)
    ap.add_argument("--out", default=str(OUT_DIR))
    ap.add_argument("--skip-ledgers", action="store_true")
    a = ap.parse_args(argv)
    P, OUT = Path(a.private), Path(a.out)
    R = P / "nport" / "round8"
    close, feats, qqq, _ = EV.load(P / "us")
    secs = RCMP.sections_of(feats)
    variants = {"O": E.filing_active(P), "C1": pickle.load(open(R / "C1.pkl", "rb")), "C2": pickle.load(open(R / "C2.pkl", "rb"))}
    res = {"label": "FOLLOW_UP_CHECK_ON_OUTCOME_EXPOSED_HISTORY", "megaTechList": MEGA, "variants": {}, "commonDate": {}}
    frames, allbooks = {}, {}
    for name, (meta, active) in variants.items():
        rows, books, avail = run_variant(name, meta, active, secs, close, qqq)
        frames[name], allbooks[name] = rows, books
        avail.to_parquet(R / f"avail-{name}.parquet", index=False)
        res["variants"][name] = {
            "signalDates": int(len(avail)), "first": str(avail["date"].min().date()), "last": str(avail["date"].max().date()),
            "matchedDateShare": {k: float(avail[f"{k}_CTRL_matched"].mean()) for k in SEL},
            "meanNames": {k: float(avail[f"{k}_n"].mean()) for k in SEL}, "meanLogCap": {k: float(avail[f"{k}_logCap"].mean()) for k in SEL},
            "meanOverlapWithBASE": {k: float(avail[f"{k}_overlapBASE"].mean()) for k in SEL},
            "fixed": {str(H): summarise(rows[H], H) for H in (126, 252)}}
        v = res["variants"][name]["fixed"]["126"]["FULL"]
        print(name, {p: round(q["mean"] * 100, 2) for p, q in v["pairs"].items()},
              round(v["matched"]["P3_OW_net_of_ctrl_minus_BASE_net_of_ctrl"]["mean"] * 100, 2), flush=True)
    # common-date decomposition: value effect (C1 - O) and sample effect (C2 - C1)
    for H in (126, 252):
        o, c1, c2 = (frames[k][H].set_index("date") for k in ("O", "C1", "C2"))
        cell = {}
        for lab, (a_, b_) in {"C1_minus_O": (c1, o), "C2_minus_C1": (c2, c1), "C2_minus_O": (c2, o)}.items():
            common = a_.index.intersection(b_.index)
            cell[lab] = {"commonDates": int(len(common))}
            for p, (x1, x0) in {"OW_minus_BASE": ("OW", "BASE"), "P1_OW_minus_CAP": ("OW", "CAP"), "P2_OW_RESID_minus_BASE": ("OW_RESID", "BASE")}.items():
                ia = (a_.loc[common, f"{x1}_net"] - a_.loc[common, f"{x0}_net"])
                ib = (b_.loc[common, f"{x1}_net"] - b_.loc[common, f"{x0}_net"])
                cell[lab][p] = {"first": float(ia.mean()), "second": float(ib.mean()), "change": CM.boot((ia - ib).tolist(), FU.spec_block(H))}
        res["commonDate"][str(H)] = cell
    c2 = res["variants"]["C2"]["fixed"]["126"]
    ps = {"P1_OW_minus_CAP": c2["FULL"]["pairs"]["P1_OW_minus_CAP"], "P2_OW_RESID_minus_BASE": c2["FULL"]["pairs"]["P2_OW_RESID_minus_BASE"],
          "P3_matched_net": c2["FULL"]["matched"]["P3_OW_net_of_ctrl_minus_BASE_net_of_ctrl"]}
    adj = CM.holm({k: v["pOneSided"] for k, v in ps.items()})
    jd = {}
    for k, v in ps.items():
        src = (lambda s: c2[s]["pairs"][k]) if k != "P3_matched_net" else (lambda s: c2[s]["matched"]["P3_OW_net_of_ctrl_minus_BASE_net_of_ctrl"])
        halves = [src(s)["mean"] for s in ("BEFORE_2023", "AI_LED_FROM_2023")]
        rest = v["mean"] > 0 and all(h > 0 for h in halves)
        jd[k] = {"mean": v["mean"], "ci": v["ci"], "pOneSided": v["pOneSided"], "holmP": adj[k], "halves": halves,
                 "verdict": "SUPPORTED" if rest and adj[k] < 0.05 else "DIRECTIONAL_ONLY" if rest else "NOT_SUPPORTED"}
    res["judgement"] = {"claims": jd, "disclosureBeyondSizeSector": any(jd[k]["verdict"] == "SUPPORTED" for k in ("P2_OW_RESID_minus_BASE", "P3_matched_net"))}
    (OUT / "us-eval.json").write_text(json.dumps(res, indent=1, sort_keys=True, default=str) + "\n")
    print(json.dumps(res["judgement"], indent=1, default=str), flush=True)
    if a.skip_ledgers:
        return
    led = {}
    books = allbooks["C2"]
    start = min(books["BASE"])
    for every in (26, 52):
        for k in ("BASE", "CAP", "OW", "OW_RESID", "OW_CTRL", "COCKTAIL", "U1"):
            led[f"L{every}|{k}"] = R6.ledger_w(close, books[k], every, start, close.index[-1])
            v = led[f"L{every}|{k}"]
            print("ledger", every, k, round(v.get("excess", np.nan) * 100, 2), round(v.get("mdd", np.nan) * 100, 1), flush=True)
    res["ledgersC2"] = led
    rows = []
    for k in ("BASE", "CAP", "OW", "OW_RESID", "COCKTAIL", "U1"):
        v = led.get(f"L26|{k}", {})
        beat = res["variants"]["C2"]["fixed"]["126"]["FULL"]["vsSPY"][k]
        rows.append((k, beat["ci"] is not None and beat["ci"][0] > 0 and v.get("excess", -1) > 0))
    res["judgement"]["beatSpy"] = dict(rows)
    (OUT / "us-eval.json").write_text(json.dumps(res, indent=1, sort_keys=True, default=str) + "\n")


if __name__ == "__main__":
    main()
