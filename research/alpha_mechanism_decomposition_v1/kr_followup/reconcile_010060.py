"""010060.KS (OCI -> OCI Holdings + new OCI 456040.KS) corporate-action reconciliation, from exchange data already in the repository.

    python research/alpha_mechanism_decomposition_v1/kr_followup/reconcile_010060.py

Sources (read by git object at the pinned signal-history commit, never fetched):
  KRX daily bars  ledger/prices/kr/krx-prices-2023.jsonl.gz      as-traded OHLCV + listed shares (exchange data)
  replay-v16      price/2023-04, price/2023-05 objects           the conditional total-return close every study used
The split ratio is read from the exchange's own listed-share counts: the old 23,849,371 shares become 16,412,642 (010060) + 7,436,729 (456040), and the
two sum EXACTLY to the old count. DART's split filing was not read (no DART key in this environment); the ratio is therefore EXCHANGE_SHARE_COUNT_DERIVED
and is labelled so. No price is adjusted in any sealed input; this file is a measurement.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
COMMIT = "4ea107ed0cde289f0a049a65ff13d2441a786710"
OLD, NEW = "010060.KS", "456040.KS"


def blob(path):
    return subprocess.check_output(["git", "cat-file", "blob", f"{COMMIT}:{path}"], cwd=ROOT)


def blob_sha1(path):
    return subprocess.check_output(["git", "rev-parse", f"{COMMIT}:{path}"], cwd=ROOT).decode().strip()


def bars():
    path = "ledger/prices/kr/krx-prices-2023.jsonl.gz"
    rows = [json.loads(x) for x in gzip.decompress(blob(path)).decode().splitlines()]
    return {(r["ticker"], r["date"]): r for r in rows if r["ticker"] in (OLD, NEW)}, {"path": path, "gitBlobSha1": blob_sha1(path)}


def replay_closes():
    m = json.loads(blob("ledger/historical/replay-v16/inputs.json"))
    out, refs = {}, []
    for comp in ("price/2023-04", "price/2023-05", "price/2023-06"):
        for ref in m["components"][comp]:
            raw = gzip.decompress(blob(f"ledger/replay-inputs/objects/{ref}.json.gz"))
            if hashlib.sha256(raw).hexdigest() != ref:
                raise ValueError("REPLAY_OBJECT_HASH_MISMATCH")
            refs.append(ref)
            for r in json.loads(raw):
                if r.get("ticker") == OLD:
                    out[r["date"]] = (r["Close"], r["Volume"])
    return out, {"manifestSha256": m["sha256"], "objects": refs}


def reconcile():
    b, bar_id = bars()
    rp, rp_id = replay_closes()
    days = sorted(d for (t, d) in b if t == OLD and "2023-04-20" <= d <= "2023-06-05")
    halted = [d for d in days if b[(OLD, d)]["volume"] == 0]
    last_trade = max(d for d in days if d < halted[0])
    relist = min(d for d in days if d > halted[-1])
    pre, post_old, post_new = b[(OLD, last_trade)], b[(OLD, relist)], b[(NEW, relist)]
    old_sh, hold_sh, new_sh = pre["listedShares"], post_old["listedShares"], post_new["listedShares"]
    if abs(hold_sh + new_sh - old_sh) > 0.5:
        raise ValueError("SHARE_COUNTS_DO_NOT_SUM: the split cannot be read from exchange counts")
    r_hold, r_new = hold_sh / old_sh, new_sh / old_sh
    econ = (r_hold * post_old["close"] + r_new * post_new["close"]) / pre["close"] - 1
    econ_open = (r_hold * post_old["open"] + r_new * post_new["open"]) / pre["close"] - 1
    replay = rp[relist][0] / rp[last_trade][0] - 1
    as_traded_old = post_old["close"] / pre["close"] - 1
    factor_price = (rp[last_trade][0] / pre["close"]) / (rp[relist][0] / post_old["close"])
    factor_volume = (rp[last_trade][1] / pre["volume"]) / (rp[relist][1] / post_old["volume"])
    return {
        "security": OLD, "successors": {OLD: "OCI Holdings (surviving, after the split)", NEW: "OCI (new, split off)"},
        "status": "RECONCILED_FROM_EXCHANGE_SHARE_COUNTS",
        "ratioSource": "EXCHANGE_SHARE_COUNT_DERIVED (KRX listed shares before and after; their sum equals the old count exactly). DART split filing not read: no key here",
        "sources": {"krxBars": bar_id, "replay": rp_id, "signalHistoryCommit": COMMIT},
        "timeline": {"lastTradeBeforeHalt": last_trade, "haltedSessions": len(halted), "haltFirst": halted[0], "haltLast": halted[-1], "relisting": relist},
        "shares": {"oldListed": old_sh, "survivingListedAfter": hold_sh, "newListed": new_sh, "survivingPerOld": r_hold, "newPerOld": r_new},
        "prices": {"lastCloseBeforeHalt": pre["close"], "relistingClose": {OLD: post_old["close"], NEW: post_new["close"]},
                   "relistingOpen": {OLD: post_old["open"], NEW: post_new["open"]}},
        "holderReturnLastTradeToRelistingClose": {"economicBothSecurities": econ, "economicAtRelistingOpen": econ_open,
                                                  "replayV16Conditional": replay, "asTradedSurvivingOnly": as_traded_old,
                                                  "replayMinusEconomic": replay - econ},
        "vendorAdjustmentImpliedByReplay": {"priceFactorOnPreEventHistory": factor_price, "volumeFactorOnPreEventHistory": factor_volume,
                                            "reading": "the replay vendor treated the split-off like a share split (pre-event prices x%.4f, volumes x%.4f) "
                                                       "instead of crediting the 456040 shares; the holder return across the event is overstated" % (factor_price, factor_volume)},
    }


def study_impact(rec, legs_csv=None):
    """Which decomposition legs held 010060.KS across the event, and the first-order book effect weight x (replay - economic)."""
    import pandas as pd
    legs_csv = legs_csv or (HERE.parent / "mechanism-attribution.csv")
    L = pd.read_csv(legs_csv, usecols=["policy", "phase", "execution", "periodEnd", "asset", "weight"], low_memory=False)
    t = rec["timeline"]
    # held INTO the halt: a book cannot sell during the halt, so the frozen engine carries these units to the relisting session
    hit = L[(L["asset"] == OLD) & (L["execution"] <= t["lastTradeBeforeHalt"]) & (L["periodEnd"] >= t["haltFirst"])]
    gap = rec["holderReturnLastTradeToRelistingClose"]["replayMinusEconomic"]
    rows = [{"policy": r.policy, "phase": int(r.phase), "execution": r.execution, "periodEnd": r.periodEnd, "weight": float(r.weight),
             "periodReturnOverstatement": float(r.weight) * gap} for r in hit.itertuples()]
    note = ("legs that held the name into the halt; the frozen engine LOCKED those units through every rebalance inside the halt and released them "
            "at the relisting session (engine residual events in source-readiness.json), so each book bore weight x (replay - economic) across the event")
    return {"heldAcrossTheEvent": rows, "note": note}


def main():
    rec = reconcile()
    rec["studyImpact"] = study_impact(rec)
    out = HERE / "010060-corporate-action-reconciliation.json"
    out.write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n")
    h = rec["holderReturnLastTradeToRelistingClose"]
    print(json.dumps({"economic": round(h["economicBothSecurities"], 6), "replay": round(h["replayV16Conditional"], 6), "gap": round(h["replayMinusEconomic"], 6),
                      "legs": len(rec["studyImpact"]["heldAcrossTheEvent"])}))


if __name__ == "__main__":
    main()
