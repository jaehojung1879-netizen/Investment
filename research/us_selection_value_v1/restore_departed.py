"""Departed S&P 500 issuers restored from the public source Codex already audited, byte-verified, kept outside git.

    python -m research.us_selection_value_v1.restore_departed --private <dir outside git>

Source: teddykoker/survivorship-free-spy @ 0bcc715e (docs/us-readiness/us-departed-public-price-recovery-v1.json, source A).
Only identifiers that audit counted in QUALIFIED coverage for source A, not on identity hold, and with NO replay-v16 panel are
used; a ticker the replay already prices is never spliced. Each file must reproduce the SHA-256 the audit recorded, else it is
refused. Source A is back-adjusted OHLCV (WIKI first, Yahoo fallback) and ends at the earlier of delisting and 2018-02-27.
Terminal consideration is NOT known for any of these: a held name whose series ends before the cohort exit leaves that cohort
UNRESOLVED (no zero, no last price, no replacement).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import pickle
import time
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "docs/us-readiness/us-departed-public-price-recovery-v1.json"


def qualified(close_columns):
    d = json.loads(AUDIT.read_text())
    acq = {(x["ticker"], x["source"]): x for x in d["acquisition"] if x["status"] == 200}
    out = []
    for inv in d["inventory"]:
        t = inv["auditIdentifier"]
        ok = [s for s in inv["candidateSources"] if s["countedInQualifiedCoverage"] and s["source"] == "A"]
        if ok and (t, "A") in acq and not inv.get("identityHold") and t not in close_columns:
            out.append({"ticker": t, "url": acq[(t, "A")]["url"], "sha256": acq[(t, "A")]["sha256"],
                        "membershipIntervals": inv.get("membershipIntervals"), "historicalCiks": inv.get("historicalCiksWhereReported")})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", required=True)
    a = ap.parse_args(argv)
    P = Path(a.private)
    close = pickle.load(open(P / "close.pkl", "rb"))["close"]
    todo = qualified(set(close.columns))
    store = P / "sourceA"
    store.mkdir(exist_ok=True)
    frames, receipts = {}, []
    for x in todo:
        f = store / (x["ticker"] + ".csv")
        if not f.exists():
            raw = urllib.request.urlopen(urllib.request.Request(x["url"], headers={"User-Agent": "research audit"}), timeout=40).read()
            f.write_bytes(raw)
            time.sleep(0.2)
        raw = f.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        ok = sha == x["sha256"]
        receipts.append({"ticker": x["ticker"], "sha256": sha, "matchesAudit": ok})
        if not ok:
            continue
        df = pd.read_csv(io.BytesIO(raw))
        df.columns = [c.lower() for c in df.columns]
        s = pd.Series(df["close"].astype(float).values, index=pd.to_datetime(df["date"]))
        frames[x["ticker"]] = s[~s.index.duplicated()].sort_index()
    panel = pd.DataFrame(frames).reindex(close.index)
    pickle.dump({"panel": panel, "receipts": receipts, "meta": {x["ticker"]: x for x in todo}}, open(P / "restored.pkl", "wb"))
    print(json.dumps({"requested": len(todo), "verified": sum(r["matchesAudit"] for r in receipts),
                      "refused": [r["ticker"] for r in receipts if not r["matchesAudit"]]}))


if __name__ == "__main__":
    main()
