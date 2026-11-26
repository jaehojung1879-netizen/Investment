"""Korea — did K2 pick its switch dates, or would a fixed ETF mix have done the same? (PREREGISTRATION.md section B)

    python -m research.followup_round8_v1.kr_switch --scratch <dir used by analyze.py> [--stage fixed|ledgers|all]

K2, S2, costs, OCI-corrected closes and the multi-account engine are reused unchanged from alpha_search_round6_v1.kr /
s2_decomposition / sg1_random_control. The gate history before 2018 is computed with the same function over the 2013+ decision dates.
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
from research.alpha_search_round6_v1 import common as CM  # noqa: E402
from research.alpha_search_round6_v1 import kr as K6  # noqa: E402

KD, RC, A, M = K6.KD, K6.RC, K6.A, K6.M
EVAL_START = pd.Timestamp("2018-01-01")
SPLIT_2022 = pd.Timestamp("2022-01-01")
BOOKS = ("ETF", "S2", "K2", "MIX_PRE", "MIX_EXP", "MIX_HINDSIGHT")
INCREMENTS = {"K2_minus_MIX_EXP": ("K2", "MIX_EXP"), "K2_minus_MIX_PRE": ("K2", "MIX_PRE"),
              "K2_minus_MIX_HINDSIGHT": ("K2", "MIX_HINDSIGHT"), "K2_minus_S2": ("K2", "S2"), "MIX_EXP_minus_S2": ("MIX_EXP", "S2")}
OUT = Path(__file__).resolve().parent / "results"


def mix(m, s2):
    out = defaultdict(float)
    out[M.ETF] += m
    for t, w in s2.items():
        out[t] += (1 - m) * w
    return dict(out)


def etf_weight(b):
    return float(b.get(M.ETF, 0.0))


def gate_history(I2, ctx2):
    """Gate value on every 2013+ decision date (same function as round 6, prior lookup over the 2013+ dates)."""
    alld = sorted(ctx2.by)
    return {d: K6.cap_over_equal(I2, ctx2, alld, d) for d in alld}


def forward_cap_minus_equal(I2, ctx2, d, e, x):
    """POST-HOC label only: realised cap-weighted minus equal-weighted top-120 return over the holding window [e, x]."""
    cl = I2["closes"]
    w, _ = KD.proxy_weights(ctx2.by[d])
    r = cl.loc[x, w.index] / cl.loc[e, w.index] - 1
    r = r[np.isfinite(r)]
    ww = w[r.index] / w[r.index].sum()
    return float((ww * r).sum() - r.mean())


def build(I2, ctx2, base):
    books6, state6 = K6.build_books(I2, ctx2, base)
    hist = gate_history(I2, ctx2)
    hd = sorted(hist)
    pre = [hist[d] > 0 for d in hd if d < EVAL_START and hist[d] is not None]
    m_pre = float(np.mean(pre))
    dates = base["dates"]
    m_exp = {}
    for d in dates:
        past = [hist[x] > 0 for x in hd if x < d and hist[x] is not None]
        m_exp[d] = float(np.mean(past))
    defined = [d for d in dates if state6[d]["capMinusEqual126"] is not None]
    e_k2 = np.mean([etf_weight(books6["K2_CAP_OVER_EQUAL_GATE"][d]) for d in defined])
    e_s2 = np.mean([etf_weight(base["s2"][d]) for d in defined])
    m_h = float((e_k2 - e_s2) / (1 - e_s2))
    books = {"ETF": books6["ETF"], "S2": books6["S2"], "K2": books6["K2_CAP_OVER_EQUAL_GATE"],
             "MIX_PRE": {d: mix(m_pre, base["s2"][d]) for d in dates}, "MIX_EXP": {d: mix(m_exp[d], base["s2"][d]) for d in dates},
             "MIX_HINDSIGHT": {d: mix(m_h, base["s2"][d]) for d in dates}}
    meta = {"mPre": m_pre, "preWeeks": len(pre), "mExpRange": [min(m_exp.values()), max(m_exp.values())],
            "mHindsight": m_h, "meanEtfExposureK2Defined": float(e_k2), "meanEtfExposureS2Defined": float(e_s2),
            "meanEtfExposureMixExpDefined": float(np.mean([etf_weight(books["MIX_EXP"][d]) for d in defined])),
            "meanEtfExposureMixPreDefined": float(np.mean([etf_weight(books["MIX_PRE"][d]) for d in defined])),
            "firstGateDefined": str(defined[0].date()), "gateDefinedDates": len(defined), "allDates": len(dates),
            "gateHistoryFrom": str(min(d for d in hd if hist[d] is not None).date())}
    return books, state6, meta


def stage_fixed(I2, ctx2, base, books, state6):
    lead = KD.leadership(I2, ctx2, base)
    out = {}
    for H in (126, 252):
        rows = []
        for d in base["dates"]:
            cs = {k: KD.cohort(I2, ctx2, base, b[d], d, H) for k, b in books.items()}
            if any(v is None or "unresolved" in v for v in cs.values()):
                continue
            months = pd.period_range(cs["S2"]["entry"], cs["S2"]["exit"], freq="M")
            labs = {KD.month_of(lead, pd.Timestamp(p.end_time.date())) for p in months}
            st = state6[d]
            rows.append({"date": d, "defined": st["capMinusEqual126"] is not None, "gateOn": bool(st["gateOn"]),
                         "touchesSemiLed": "SEMI_LED" in labs,
                         "postHocLeadPersisted": forward_cap_minus_equal(I2, ctx2, d, cs["S2"]["entry"], cs["S2"]["exit"]) > 0,
                         **{f"{k}_net": v["net"] for k, v in cs.items()}, **{f"{k}_cost": v["cost"] for k, v in cs.items()}})
        df = pd.DataFrame(rows)
        g = df[df["defined"]]
        block = int(round(H / 5))
        samples = {"GATE_DEFINED": g, "ORIGINAL": df,
                   "GD_TOUCHES_SEMI_LED": g[g["touchesSemiLed"]], "GD_EX_SEMI_LED": g[~g["touchesSemiLed"]],
                   "GD_TO_2021": g[g["date"] < SPLIT_2022], "GD_FROM_2022": g[g["date"] >= SPLIT_2022],
                   "GD_GATE_ON_AT_SIGNAL": g[g["gateOn"]], "GD_GATE_OFF_AT_SIGNAL": g[~g["gateOn"]],
                   "POSTHOC_LEAD_PERSISTED": g[g["postHocLeadPersisted"]], "POSTHOC_LEAD_REVERSED": g[~g["postHocLeadPersisted"]]}
        cell = {}
        for nm, s in samples.items():
            if s.empty:
                continue
            e = s["ETF_net"]
            row = {"cohorts": int(len(s)), "first": str(s["date"].iloc[0].date()), "last": str(s["date"].iloc[-1].date())}
            row["vsETF"] = {k: CM.boot((s[f"{k}_net"] - e).tolist(), block) for k in BOOKS if k != "ETF"}
            row["increments"] = {n: CM.boot((s[f"{a}_net"] - s[f"{b}_net"]).tolist(), block) for n, (a, b) in INCREMENTS.items()}
            row["meanCost"] = {k: float(s[f"{k}_cost"].mean()) for k in BOOKS}
            cell[nm] = row
        out[str(H)] = cell
        # independent switch episodes (gate state runs of >= 4 weeks over defined dates), 6-month cohorts started inside each
        if H == 126:
            spells, cur = [], None
            for d in [x for x in base["dates"] if state6[x]["capMinusEqual126"] is not None]:
                on = bool(state6[d]["gateOn"])
                if cur is None or cur["on"] != on:
                    cur = {"on": on, "from": d, "to": d, "weeks": 0}
                    spells.append(cur)
                cur["to"] = d
                cur["weeks"] += 1
            ep = []
            for sp in spells:
                if sp["weeks"] < 4:
                    continue
                x = g[(g["date"] >= sp["from"]) & (g["date"] <= sp["to"])]
                if x.empty:
                    continue
                diff = float((x["K2_net"] - x["MIX_EXP_net"]).mean())
                ep.append({"gate": "ON_ETF" if sp["on"] else "OFF_S2", "from": str(sp["from"].date()), "to": str(sp["to"].date()),
                           "weeks": sp["weeks"], "cohorts": int(len(x)), "k2MinusMixExp": diff, "k2MinusEtf": float((x["K2_net"] - x["ETF_net"]).mean()),
                           "win": diff > 0})
            out["episodes"] = {"list": ep, "summary": {lab: {"episodes": sum(1 for e_ in ep if e_["gate"] == lab),
                                                             "wins": sum(1 for e_ in ep if e_["gate"] == lab and e_["win"])}
                                                       for lab in ("ON_ETF", "OFF_S2")}}
        print("KR fixed", H, {n: {k: round(v["mean"] * 100, 2) for k, v in c["increments"].items()} for n, c in cell.items() if n in ("GATE_DEFINED", "ORIGINAL")}, flush=True)
    full = out["126"]["GATE_DEFINED"]
    adj = CM.holm({k: full["increments"][k]["pOneSided"] for k in ("K2_minus_MIX_EXP", "K2_minus_MIX_PRE")})
    out["judgement"] = {}
    for k in ("K2_minus_MIX_EXP", "K2_minus_MIX_PRE"):
        halves = [out["126"][s]["increments"][k]["mean"] for s in ("GD_TO_2021", "GD_FROM_2022")]
        rest = full["increments"][k]["mean"] > 0 and all(h > 0 for h in halves)
        out["judgement"][k] = {"mean": full["increments"][k]["mean"], "pOneSided": full["increments"][k]["pOneSided"], "holmP": adj[k],
                               "halves": halves, "verdict": "TIMING_EFFECT_SUPPORTED" if rest and adj[k] < 0.05 else "DIRECTIONAL_ONLY" if rest else "NOT_SUPPORTED"}
    return out


def stage_ledgers(I2, ctx2, base, books, gd_start):
    dates, sess = base["dates"], I2["sessions"]
    etf = pd.Series(ctx2.px.etf, index=sess)
    start = M.next_session(sess, dates[0])
    gd_exec = M.next_session(sess, gd_start)
    end = I2["closes"][M.ETF].last_valid_index()
    out = {}
    for every in (26, 52):
        for name in BOOKS:
            b = books[name]
            scheds = [A.books_to_schedule({d: b[d] for d in dates[k::every]}, sess) for k in range(every)]
            res = A.multi_account(ctx2.px, scheds, start, end, I2["rf"], etf, 1.0)
            for lab, st in (("ORIGINAL", start), ("GATE_DEFINED", gd_exec), ("FROM_2022", K6.EVAL_2022)):
                w = RC.window(res["nav"], etf, start=st)
                w.update(oneWayTurnoverPerYear=res["oneWayTurnoverPerYear"], costPerYear=res["costPerYear"])
                out[f"L{every}|{lab}|{name}"] = w
            v = out[f"L{every}|GATE_DEFINED|{name}"]
            print("KR ledger", every, name, round(v["cagr"] * 100, 2), round(v["excess"] * 100, 2), round(v["mdd"] * 100, 1), flush=True)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", required=True)
    ap.add_argument("--stage", choices=("fixed", "ledgers", "all"), default="all")
    a = ap.parse_args(argv)
    I2, ctx2, base = RC.setup(a.scratch)
    books, state6, meta = build(I2, ctx2, base)
    print("meta", meta, flush=True)
    res = {"studyId": "followup-round8-v1", "market": "KR", "label": "FOLLOW_UP_CHECK_ON_OUTCOME_EXPOSED_HISTORY", "mix": meta}
    if a.stage in ("fixed", "all"):
        res["fixed"] = stage_fixed(I2, ctx2, base, books, state6)
        (OUT / "kr-switch-fixed.json").write_text(json.dumps(res, indent=1, sort_keys=True, default=str) + "\n")
    if a.stage in ("ledgers", "all"):
        led = stage_ledgers(I2, ctx2, base, books, pd.Timestamp(meta["firstGateDefined"]))
        (OUT / "kr-switch-ledgers.json").write_text(json.dumps({"mix": meta, "ledgers": led}, indent=1, sort_keys=True, default=str) + "\n")


if __name__ == "__main__":
    main()
