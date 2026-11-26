"""Round 6 — Korea: K1 TOP5_CAP_NEUTRAL and K2 CAP_OVER_EQUAL_GATE on the original S2 (definitions in PREREGISTRATION.md).

    python -m research.alpha_search_round6_v1.kr --scratch <dir used by analyze.py> [--stage fixed|ledgers|all]

Reuses s2_decomposition / sg1_random_control (S2 books, OCI-corrected closes, frozen costs, frozen multi-account engine).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.alpha_search_round6_v1 import common as CM  # noqa: E402

KDIR = ROOT / "research/alpha_mechanism_decomposition_v1/kr_followup"


def _load(name, path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


KD = _load("kr_s2_decomposition", KDIR / "s2_decomposition.py")
RC, A, M, C = KD.RC, KD.A, KD.M, KD.C
K = 5
LOOKBACK = 126
EVAL_2022 = pd.Timestamp("2022-01-11")
OUT = Path(__file__).resolve().parent / "results"


def top5_neutral(g, parent):
    w, _ = KD.proxy_weights(g)
    top = w.sort_values(ascending=False).head(K)
    s = float(top.sum())
    out = defaultdict(float)
    for t, v in parent.items():
        out[t] += (1 - s) * v
    for t, v in top.items():
        out[t] += float(v)
    return dict(out), s


def cap_over_equal(I2, ctx2, dates, d):
    cl, sess = I2["closes"], I2["sessions"]
    i = int(sess.searchsorted(d, side="right")) - 1
    if i < LOOKBACK:
        return None
    t0 = sess[i - LOOKBACK]
    prior = [x for x in dates if x <= t0]
    if not prior:
        return None
    w, _ = KD.proxy_weights(ctx2.by[prior[-1]])
    r = cl.loc[sess[i], w.index] / cl.loc[t0, w.index] - 1
    r = r[np.isfinite(r)]
    if r.empty:
        return None
    ww = w[r.index] / w[r.index].sum()
    return float((ww * r).sum() - r.mean())


def build_books(I2, ctx2, base):
    dates = base["dates"]
    books = {"ETF": {}, "S2": {}, "K1_TOP5_CAP_NEUTRAL": {}, "K2_CAP_OVER_EQUAL_GATE": {}}
    state = {}
    for d in dates:
        s2 = base["s2"][d]
        k1, s = top5_neutral(ctx2.by[d], s2)
        gap = cap_over_equal(I2, ctx2, dates, d)
        on = gap is not None and gap > 0
        books["ETF"][d] = {M.ETF: 1.0}
        books["S2"][d] = s2
        books["K1_TOP5_CAP_NEUTRAL"][d] = k1
        books["K2_CAP_OVER_EQUAL_GATE"][d] = {M.ETF: 1.0} if on else s2
        state[d] = {"top5Share": s, "capMinusEqual126": gap, "gateOn": on}
    return books, state


def stage_fixed(I2, ctx2, base, books, state):
    lead = KD.leadership(I2, ctx2, base)
    out = {}
    for H in (126, 252):
        rows, unres = [], []
        for d in base["dates"]:
            cs = {k: KD.cohort(I2, ctx2, base, b[d], d, H) for k, b in books.items()}
            if any(v is None for v in cs.values()):
                continue
            if any("unresolved" in v for v in cs.values()):
                unres.append({"date": str(d.date()), **{k: v["unresolved"] for k, v in cs.items() if "unresolved" in v}})
                continue
            months = pd.period_range(cs["S2"]["entry"], cs["S2"]["exit"], freq="M")
            labs = {KD.month_of(lead, pd.Timestamp(p.end_time.date())) for p in months}
            rows.append({"date": d, "touchesSemiLed": "SEMI_LED" in labs, "gateOn": state[d]["gateOn"],
                         **{f"{k}_net": v["net"] for k, v in cs.items()}, **{f"{k}_cost": v["cost"] for k, v in cs.items()}})
        df = pd.DataFrame(rows)
        block = int(round(H / 5))
        samples = {"FULL": df, "TO_2021": df[df["date"] < pd.Timestamp("2022-01-01")], "FROM_2022": df[df["date"] >= pd.Timestamp("2022-01-01")],
                   "EX_SEMI_LED": df[~df["touchesSemiLed"]]}
        cell = {"unresolvedCohorts": unres, "gateOnShare": float(df["gateOn"].mean())}
        for name, s in samples.items():
            e = s["ETF_net"]
            row = {"cohorts": int(len(s)), "first": str(s["date"].iloc[0].date()), "last": str(s["date"].iloc[-1].date()), "ETF_meanNet": float(e.mean())}
            for k in ("S2", "K1_TOP5_CAP_NEUTRAL", "K2_CAP_OVER_EQUAL_GATE"):
                row[k] = {"vsETF": CM.boot((s[f"{k}_net"] - e).tolist(), block), "meanCost": float(s[f"{k}_cost"].mean())}
                if k != "S2":
                    row[k]["vsParentS2"] = CM.boot((s[f"{k}_net"] - s["S2_net"]).tolist(), block)
            cell[name] = row
        out[str(H)] = cell
        print("KR fixed", H, {n: {k: round(c[k]["vsETF"]["mean"] * 100, 2) for k in ("S2", "K1_TOP5_CAP_NEUTRAL", "K2_CAP_OVER_EQUAL_GATE")}
                              for n, c in cell.items() if isinstance(c, dict) and "S2" in c}, flush=True)
    return out


def stage_ledgers(I2, ctx2, base, books):
    dates, sess = base["dates"], I2["sessions"]
    etf = pd.Series(ctx2.px.etf, index=sess)
    start = M.next_session(sess, dates[0])
    end = I2["closes"][M.ETF].last_valid_index()
    out = {"start": str(start.date())}
    for every in (26, 52):
        for name, b in books.items():
            scheds = [A.books_to_schedule({d: b[d] for d in dates[k::every]}, sess) for k in range(every)]
            res = A.multi_account(ctx2.px, scheds, start, end, I2["rf"], etf, 1.0)
            for lab, st in (("FULL", start), ("FROM_2022", EVAL_2022)):
                w = RC.window(res["nav"], etf, start=st)
                w.update(oneWayTurnoverPerYear=res["oneWayTurnoverPerYear"], costPerYear=res["costPerYear"])
                out[f"L{every}|{lab}|{name}"] = w
            print("KR ledger", every, name, round(out[f"L{every}|FULL|{name}"]["excess"] * 100, 2), round(out[f"L{every}|FULL|{name}"]["mdd"] * 100, 1), flush=True)
    return out


def stage_spells(I2, ctx2, base, books, state):
    """Gate-off / gate-on spells over the dates where the gate is defined, and S2 - ETF 6-month net by gate state (section 1.3)."""
    st = pd.DataFrame(state).T
    st.index = pd.to_datetime(st.index)
    defined = st["capMinusEqual126"].notna()
    on = st["gateOn"].astype(bool)
    spells = []
    for d in st.index[defined]:
        if not spells or spells[-1][0] != bool(on[d]):
            spells.append([bool(on[d]), d, d, 0])
        spells[-1][2] = d
        spells[-1][3] += 1
    rows = []
    for d in base["dates"]:
        s2 = KD.cohort(I2, ctx2, base, books["S2"][d], d, 126)
        e = KD.cohort(I2, ctx2, base, {M.ETF: 1.0}, d, 126)
        if s2 and e and "unresolved" not in s2:
            rows.append({"date": d, "on": bool(on[d]), "defined": bool(defined[d]), "x": s2["net"] - e["net"]})
    df = pd.DataFrame(rows)
    groups = {"GATE_OFF_S2_HELD": df[df["defined"] & ~df["on"]], "GATE_ON_ETF_HELD": df[df["on"]], "UNDEFINED_S2_HELD": df[~df["defined"]]}
    out = {"byState": {k: {"cohorts": int(len(g)), "s2MinusEtf126": float(g["x"].mean()), "winRate": float((g["x"] > 0).mean())} for k, g in groups.items()},
           "gateOffSpells": [], "gateOnSpells": [[str(a.date()), str(b.date()), n] for v, a, b, n in spells if v]}
    for v, a, b, n in spells:
        if not v:
            g = df[(df["date"] >= a) & (df["date"] <= b)]
            out["gateOffSpells"].append({"from": str(a.date()), "to": str(b.date()), "weeks": n,
                                         "s2MinusEtf126": float(g["x"].mean()) if len(g) else None})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True)
    ap.add_argument("--stage", choices=("fixed", "ledgers", "spells", "all"), default="all")
    a = ap.parse_args(argv)
    I2, ctx2, base = RC.setup(a.scratch)
    books, state = build_books(I2, ctx2, base)
    st = pd.DataFrame(state).T.apply(pd.to_numeric, errors="coerce")
    res = {"studyId": "alpha-search-round6-v1", "market": "KR", "label": "EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_HISTORY",
           "signalDates": [str(base["dates"][0].date()), str(base["dates"][-1].date()), len(base["dates"])],
           "state": {"top5ShareMean": float(st["top5Share"].astype(float).mean()), "gateOnShare": float(st["gateOn"].astype(float).mean()),
                     "gateDefinedShare": float(st["capMinusEqual126"].notna().mean()),
                     "gateOnShareByYear": st.groupby(pd.to_datetime(st.index).year)["gateOn"].mean().round(3).to_dict()}}
    if a.stage in ("fixed", "all"):
        res["fixed"] = stage_fixed(I2, ctx2, base, books, state)
        (OUT / "kr-fixed.json").write_text(json.dumps(res, indent=1, sort_keys=True, default=str) + "\n")
    if a.stage in ("spells", "all"):
        (OUT / "kr-gate-spells.json").write_text(json.dumps(stage_spells(I2, ctx2, base, books, state), indent=1, sort_keys=True) + "\n")
    if a.stage in ("ledgers", "all"):
        led = stage_ledgers(I2, ctx2, base, books)
        (OUT / "kr-ledgers.json").write_text(json.dumps({**{k: v for k, v in res.items() if k != "fixed"}, "ledgers": led}, indent=1, sort_keys=True, default=str) + "\n")


if __name__ == "__main__":
    main()
