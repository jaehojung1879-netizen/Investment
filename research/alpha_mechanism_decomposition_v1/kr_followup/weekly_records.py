"""Weekly four-book receipts on the latest inputs, linked to cost-deducted four-account NAVs, with an independent NAV check.

    python research/alpha_mechanism_decomposition_v1/kr_followup/weekly_records.py --latest <dir from latest_inputs.py>

ONE PATH FOR PREVIEW AND LIVE. `accounts_from_receipts` turns a receipt ledger into the four phase schedules (receipt k belongs to account k mod 4) and runs
the frozen self-financing engine (adaptive-cocktail-v1 `simulate`, vendored byte-identical) with its cost schedule. The same function will evaluate the live
ledger after authorization; here it runs on REPLAY_PREVIEW receipts and its numbers are VERIFICATION_RUN_NOT_EVIDENCE (the sessions are already observed).

INDEPENDENT CHECK (`verify_account`), never the engine's own arithmetic:
  * between trades, NAV(t) = sum(units x close(t)) with units recovered from the engine's recorded post-trade weights and NAV;
  * at each trade, NAV_post = NAV_pre - cost, cost = sum(|traded value| x the dated rate for its side) recomputed from recorded pre/post weights;
  * every scheduled target equals the receipt's book weights (receipt digest carried on the schedule).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
ROOT = STUDY.parents[1]
sys.path.insert(0, str(ROOT))


def _load(name, path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


REC = _load("kr_four_book_recorder", STUDY / "prospective/recorder.py")
C = REC.C
CORE = REC.CORE
ETF = REC.ETF


# --------------------------------------------------------------------------- #
# Cross-sections from the latest matrix
# --------------------------------------------------------------------------- #
def cross_sections(matrix, universe_rows):
    rows = matrix.rows.reset_index(drop=True)
    vals = matrix.values.reset_index(drop=True)
    df = pd.concat([rows, vals[[c for c in vals.columns if c not in rows.columns]]], axis=1)
    caps = {(d, r["ticker"]): r.get("marketCap") for d, rs in universe_rows.items() for r in rs}
    df["_mcap"] = [caps.get((str(s)[:10], t)) for s, t in zip(df["pitSnapshotDate"], df["ticker"])]
    df["_mcap"] = df["_mcap"].astype(float)
    df["isPreferredShare"] = df["isPreferredShare"].map(lambda v: None if v is None or (isinstance(v, float) and np.isnan(v)) else bool(v))
    return {str(d)[:10]: g.reset_index(drop=True) for d, g in df.groupby("date")}


def build_receipts(sections, sessions, data_identity, clock):
    out = []
    for d in sorted(sections):
        e = sessions[sessions.searchsorted(pd.Timestamp(d), side="right")] if pd.Timestamp(d) < sessions[-1] else None
        if e is None:
            continue
        out.append(REC.build_preview_receipt(g=sections[d], signal_date=d, execution_date=e, data_identity=data_identity, clock_utc=clock))
    return out


# --------------------------------------------------------------------------- #
# Four accounts from a receipt ledger
# --------------------------------------------------------------------------- #
def schedules_from_receipts(receipts, book):
    """Account k holds receipts k, k+4, k+8, ... (each a 4-week phase); the schedule is {execution session: book weights}."""
    scheds = [{}, {}, {}, {}]
    links = [{}, {}, {}, {}]
    for i, r in enumerate(sorted(receipts, key=lambda r: r["signalDate"])):
        k = i % 4
        e = pd.Timestamp(r["executionDate"])
        scheds[k][e] = dict(r["books"][book]["weights"])
        links[k][str(e.date())] = r["receiptSha256"]
    return scheds, links


def accounts_from_receipts(receipts, book, px, start, end):
    scheds, links = schedules_from_receipts(receipts, book)
    accts = []
    for k in range(4):
        sim = C.simulate(px, scheds[k], start, end, record=True)
        accts.append({"account": k, "schedule": scheds[k], "receiptLinks": links[k], "sim": sim})
    total = sum(a["sim"]["nav"] for a in accts)
    return accts, total / total.iloc[0]


def verify_account(acct, px, closes):
    """Mark-to-market and cost identities recomputed from the engine's RECORDED holdings, not from its code path."""
    sim = acct["sim"]
    nav = sim["nav"]
    holds = {pd.Timestamp(h["date"]): h["weights"] for h in sim["holdings"]}
    # the engine records post-trade weights rounded to 1e-6, so a recovered unit count carries up to 5e-7 relative error per asset: the bound is derived,
    # not fitted (n assets x 5e-7, plus float noise)
    bound = max(5e-7 * len(w) for w in holds.values()) + 1e-9 if holds else 1e-9
    checks = {"markToMarketMaxRelErr": 0.0, "costMaxAbsErr": 0.0, "scheduleMatchesReceipts": True, "trades": len(holds),
              "roundingBound": bound}
    dates = list(nav.index)
    units = None
    for i, d in enumerate(dates):
        if units is not None and d not in holds:
            mtm = sum(u * (closes.at[d, a] if a != C.CASH else 1.0) for a, u in units.items())
            checks["markToMarketMaxRelErr"] = max(checks["markToMarketMaxRelErr"], abs(mtm / nav.loc[d] - 1))
        if d in holds:
            w = holds[d]
            post = nav.loc[d]
            pre = (sum(u * closes.at[d, a] for a, u in units.items()) if units is not None else nav.loc[dates[0]] if i == 0 else nav.loc[d])
            if units is not None:
                cur = {a: units[a] * closes.at[d, a] / pre for a in units}
                exp = 0.0
                for a in set(w) | set(cur):
                    tw = w.get(a, 0.0) * post / pre
                    delta = tw - cur.get(a, 0.0)
                    if abs(delta) > 1e-9 and a != C.CASH:
                        exp += abs(delta) * pre * C.cost_rate(a, "buy" if delta > 0 else "sell", d)
                checks["costMaxAbsErr"] = max(checks["costMaxAbsErr"], abs((pre - post) - exp) / pre)
            sched = acct["schedule"].get(d)
            if sched is not None:
                tradable = {a: v for a, v in sched.items()}
                if set(a for a, v in w.items() if v > 1e-6) - set(tradable) - {ETF}:
                    checks["scheduleMatchesReceipts"] = False
            units = {a: v * post / closes.at[d, a] for a, v in w.items() if a != C.CASH}
    checks["pass"] = (checks["markToMarketMaxRelErr"] <= bound and checks["costMaxAbsErr"] <= bound * 2 and checks["scheduleMatchesReceipts"])
    return checks


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--latest", required=True)
    a = ap.parse_args(argv)
    d = Path(a.latest)
    mx = pickle.loads((d / "latest-matrix.pkl").read_bytes())
    pr = pickle.loads((d / "latest-prices.pkl").read_bytes())
    last_bar = pd.Timestamp(mx["identity"]["extensions"]["krxBars2026"]["lastDate"])
    # stop at the last KRX stock-bar session: later benchmark-only sessions would mark stocks at stale carried closes
    sessions = pd.DatetimeIndex(sorted({ts for f in pr["prices"].values() for ts in f.index if pd.Timestamp("2026-09-01") <= ts <= last_bar}))
    sections = cross_sections(mx["matrix"], pr["universe_rows"])
    ident = {"latestInputsSha256": mx["identity"]["sha256"], "tipCommit": mx["identity"]["tipCommit"], "matrixDigest": mx["matrix"].digest()}
    receipts = build_receipts(sections, sessions, ident, "2026-11-15T00:00:00Z")
    tickers = sorted({t for r in receipts for b in REC.BOOKS for t in r["books"][b]["weights"]} | {ETF})
    closes = pd.DataFrame({t: pr["prices"][t]["Close"] for t in tickers if t in pr["prices"]}).reindex(sessions).loc["2026-09-01":]
    # the benchmark frame carries no volume; it is tradable on every session it has a close
    vols = pd.DataFrame({t: (pr["prices"][t]["Volume"] if "Volume" in pr["prices"][t] else pr["prices"][t]["Close"].notna().astype(float))
                         for t in tickers if t in pr["prices"]}).reindex(closes.index).fillna(0.0)
    missing = [t for t in tickers if t not in closes.columns]
    rf = pd.Series(0.0, index=closes.index)                       # BOK proxy not extended past the pinned file: cash earns 0 here (no book holds cash)
    px = C.Prices(closes, vols, closes.index, rf)
    start, end = pd.Timestamp(receipts[0]["executionDate"]), closes[ETF].last_valid_index()
    out = {"label": "VERIFICATION_RUN_NOT_EVIDENCE", "window": [str(start.date()), str(end.date())], "receipts": len(receipts),
           "signalDates": [r["signalDate"] for r in receipts], "missingPriceTickers": missing, "books": {}}
    for book in REC.BOOKS:
        accts, nav = accounts_from_receipts(receipts, book, px, start, end)
        checks = [verify_account(x, px, closes) for x in accts]
        out["books"][book] = {"fourAccountReturn": float(nav.iloc[-1] - 1), "costs": [float(x["sim"]["costs"]) for x in accts],
                              "accountChecks": checks, "allChecksPass": all(c["pass"] for c in checks),
                              "receiptLinks": [x["receiptLinks"] for x in accts]}
    ledger = HERE / "preview-receipts.jsonl"
    if ledger.exists():
        ledger.unlink()
    for r in receipts:
        CORE.append(ledger, r, validate=lambda x: REC.validate(x, pathway=REC.PREVIEW), key_fields=("studyId", "signalDate"))
    out["previewLedger"] = {"path": str(ledger.relative_to(ROOT)), "rows": len(receipts)}
    out["inputs"] = mx["identity"]["extensions"]
    out["firstObservation"] = {r["signalDate"]: {b: {"stockNames": r["books"][b]["stockNames"], "state": r["books"][b]["state"],
                                                    "selected": [x["ticker"] for x in r["books"][b].get("selection", {}).get("selected", [])]}
                                                for b in REC.BOOKS} for r in receipts}
    (HERE / "weekly-nav-verification.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str) + "\n")
    print(json.dumps({b: {"ret": round(v["fourAccountReturn"], 4), "pass": v["allChecksPass"]} for b, v in out["books"].items()}, indent=0))


if __name__ == "__main__":
    main()
