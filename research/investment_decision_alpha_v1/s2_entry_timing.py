"""S2 (PREREGISTRATION.md section 2): buy now, or wait for the next earnings announcement? Same name, same weight, same end date.

    python -m research.investment_decision_alpha_v1.s2_entry_timing --market us --private <#353-corrected dir> --events <dir with us-events.pkl>
    python -m research.investment_decision_alpha_v1.s2_entry_timing --market kr --private <dir with data/> --events <dir with kr-events.pkl>

A purchase event is a name that enters a book at decision date d (absent from the previous decision date's book).
P0 buys at the close of the session after d. P1 parks the same money in the ETF and buys at the close of the first
announcement reaction day after entry (US: 8-K Item 2.02 reaction session; KR: session after the preliminary-earnings
receipt date). P2 waits five more sessions. P1c parks in cash. Every policy is valued at T = entry + H sessions.
Version 2 (2026-11-22, Codex audit): version 1 decided whether to wait by looking up whether an announcement would
occur within the next 63 sessions, which a buyer cannot know on the entry day. Version 2 always waits: the purchase
happens at the first reaction day after entry or at entry + 63 sessions, whichever comes first (P2 adds five sessions
only when an announcement arrived). Version 1 outputs are kept unchanged and marked INVALIDATED.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.alpha_search_round6_v1 import common as CM
from research.kr_us_earnings_expectations_v1 import analysis as AN

HERE = Path(__file__).resolve().parent
AI_LED = pd.Timestamp("2023-01-01")
HS = (126, 252)
WAIT_MAX = 63


def boot(v, H, two=True):
    r = CM.boot(v, max(1, int(round(H / 5))))
    if two and r.get("pOneSided") is not None:
        p = r["pOneSided"]
        r["pTwoSided"] = min(1.0, 2 * min(p, 1 - p + 1 / (CM.B + 1)))
    return r


def entries(book: dict, skip: set) -> list[tuple]:
    out, prev = [], set()
    for d in sorted(book):
        cur = {t for t, w in book[d].items() if w > 0 and t not in skip}
        out += [(d, t) for t in sorted(cur - prev)]
        prev = cur
    return out


def reaction_days(ev: pd.DataFrame, sess: pd.DatetimeIndex, market: str) -> dict:
    out = {}
    for t, g in ev.dropna(subset=["announceEffective"]).groupby("ticker"):
        days = []
        for a in pd.to_datetime(g["announceEffective"]).unique():
            i = sess.searchsorted(pd.Timestamp(a), side="left")
            if market == "kr":
                i += 1  # receipt date known only to the day; the reaction window is -1..+1, so buy after day +1
            if i < len(sess):
                days.append(i)
        out[t] = np.array(sorted(set(days)))
    return out


def evaluate(events, close, etf, react, cost, H):
    sess = close.index
    arr = close.to_numpy()
    col = {t: i for i, t in enumerate(close.columns)}
    ej = col[etf]
    rows = []
    for d, t, ent_pos in events:
        if t not in col:
            continue
        z = ent_pos + H
        if z >= len(sess):
            continue
        j = col[t]
        s0, sz = arr[ent_pos, j], arr[z, j]
        if not (np.isfinite(s0) and np.isfinite(sz)):
            rows.append({"date": d, "ticker": t, "unresolved": True})
            continue
        r = react.get(t, np.array([], int))
        nxt = r[r > ent_pos]
        announced = bool(len(nxt)) and nxt[0] - ent_pos <= WAIT_MAX
        b1 = int(nxt[0]) if announced else ent_pos + WAIT_MAX          # v2: the cap is a rule, not a forecast
        cb, cs = cost(t, "buy", sess[ent_pos]), cost(t, "sell", sess[z])
        eb = cost(etf, "buy", sess[ent_pos])
        p0 = (1 - cb) * (sz / s0) * (1 - cs) - 1
        rec = {"date": d, "ticker": t, "unresolved": False, "waited": announced, "P0": p0}
        for name, b in (("P1", b1), ("P2", b1 + 5 if announced else b1)):
            if b is None or b >= z:
                rec[name], rec[name + "c"] = p0, p0
                continue
            sb, fb, f0 = arr[b, j], arr[b, ej], arr[ent_pos, ej]
            if not (np.isfinite(sb) and np.isfinite(fb) and np.isfinite(f0)):
                rec[name], rec[name + "c"] = np.nan, np.nan
                continue
            stock_leg = (1 - cost(t, "buy", sess[b])) * (sz / sb) * (1 - cs)
            rec[name] = (1 - eb) * (fb / f0) * (1 - cost(etf, "sell", sess[b])) * stock_leg - 1
            rec[name + "c"] = stock_leg - 1
        # pre-entry 21-session run-up of the name, for the chase split (auxiliary)
        pre = arr[ent_pos, j] / arr[max(0, ent_pos - 21), j] - 1 if ent_pos >= 21 else np.nan
        rec["runup21"] = pre
        rows.append(rec)
    return pd.DataFrame(rows)


def summarise(df, H):
    ok = df[~df["unresolved"]].dropna(subset=["P0", "P1"])
    out = {"events": int(len(df)), "unresolved": int(df["unresolved"].sum()), "waitedShare": float(ok["waited"].mean()),
           "eventsPerYear": float(len(ok) / max(1e-9, (ok["date"].max() - ok["date"].min()).days / 365.25))}
    for name in ("P1", "P2", "P1c"):
        diff = (ok[name] - ok["P0"]).groupby(ok["date"]).mean().sort_index()
        cell = {"all": boot(diff.values, H), "BEFORE_2023": boot(diff[diff.index < AI_LED].values, H),
                "FROM_2023": boot(diff[diff.index >= AI_LED].values, H)}
        w = ok[ok["waited"]]
        dw = (w[name] - w["P0"]).groupby(w["date"]).mean().sort_index()
        cell["waitedOnly"] = boot(dw.values, H)
        med = ok["runup21"].median()
        for lab, m in (("runupHigh", ok["runup21"] > med), ("runupLow", ok["runup21"] <= med)):
            s = (ok.loc[m, name] - ok.loc[m, "P0"]).groupby(ok.loc[m, "date"]).mean().sort_index()
            cell[lab] = boot(s.values, H)
        out[name] = cell
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("us", "kr"), required=True)
    ap.add_argument("--private", required=True)
    ap.add_argument("--events", required=True)
    ap.add_argument("--out", default=str(HERE / "results"))
    a = ap.parse_args(argv)
    P = Path(a.private)
    ev = pd.read_pickle(Path(a.events) / f"{a.market}-events.pkl")
    if a.market == "us":
        from research.us_selection_value_v1 import evaluate as EV
        mk = AN.US(P)
        books, _ = AN.books_us(mk, ev)
        close, etf, skip = mk.close, "SPY", {"SPY"}

        def cost(t, side, day):
            return EV.BUY if side == "buy" else EV.SELL
        use = {"BASE": books["BASE"], "U1": books["U1"], "SUE_TOP": books["SUE_TOP"]}

        def entry_pos(d):
            return close.index.get_loc(d) + 1
    else:
        mk = AN.KR(P)
        books, _ = AN.books_kr(mk, ev)
        M, C = mk.M, mk.KD.C
        close, etf, skip = mk.close.loc[mk.sess.intersection(mk.close.index)], M.ETF, {M.ETF, M.CASH}

        def cost(t, side, day):
            return C.cost_rate(t, side, day)
        use = {"S2": books["S2"]}

        def entry_pos(d):
            return close.index.get_loc(M.next_session(mk.sess, d))
    react = reaction_days(ev, close.index, a.market)
    res = {"studyId": "investment-decision-alpha-v1/S2", "version": 2, "supersedes": f"s2-entry-timing-{a.market}.json (INVALIDATED: future announcement lookup)", "market": a.market.upper(), "label": "EXPLORATORY_ON_OUTCOME_EXPOSED_HISTORY",
           "tickersWithAnnouncements": len(react)}
    frames = {}
    for bname, bk in use.items():
        evs = [(d, t, entry_pos(d)) for d, t in entries(bk, skip)]
        for H in HS:
            df = evaluate(evs, close, etf, react, cost, H)
            frames[(bname, H)] = df
            res[f"{bname}|{H}"] = summarise(df, H)
            c = res[f"{bname}|{H}"]["P1"]["all"]
            print(a.market, bname, H, "events", len(df), "waited", round(res[f"{bname}|{H}"]["waitedShare"], 3),
                  "D1", round(c["mean"] * 100, 3), c.get("ci"), flush=True)
    out = Path(a.out)
    (out / f"s2-entry-timing-{a.market}-v2.json").write_text(json.dumps(res, indent=1, sort_keys=True, default=str) + "\n")
    pd.to_pickle(frames, P / f"s2-frames-{a.market}-v2.pkl")


if __name__ == "__main__":
    main()
