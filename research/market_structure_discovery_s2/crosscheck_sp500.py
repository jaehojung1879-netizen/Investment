"""Cross-check parsed S&P 500 additions against Wikipedia's current-constituent 'Date added'.

Wikipedia (raw wikitext, hashed in data/) lists each current member's date added. For
current members added after the first PR Newswire release in the listing, the share whose
addition we parsed within 3 days of that date measures the parse/listing coverage. This is
survivor-only (current members) and is reported as such. No price or return is read.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))


def main() -> None:
    wiki = open(os.path.join(HERE, "data", "wikipedia_sp500_raw.wiki"), encoding="utf-8").read()
    table = wiki.split('id="constituents"', 1)[1].split("|}", 1)[0]
    rows = []
    for block in table.split("\n|-")[1:]:
        m = re.search(r"\{\{(?:Nyse|Nasdaq|Cboe|BATS)Symbol\|([A-Z.\-]+)\}\}", block, re.I)
        d = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", block)
        if m and d:
            rows.append((m.group(1).replace(".", "-") if False else m.group(1), d.group(1)))
    led = json.load(open(os.path.join(HERE, "results", "institutional-event-ledger.json"), encoding="utf-8"))
    adds = {}
    for r in led["sp500"]["rows"]:
        if r["action"] == "ADD":
            adds.setdefault(r["ticker"], []).append(r["effectiveDate"])
    first = min(r["effectiveDate"] for r in led["sp500"]["rows"])
    cand = [(t, d) for t, d in rows if first <= d <= "2026-11-26"]
    hit, miss = [], []
    for t, d in cand:
        ok = any(abs((dt.date.fromisoformat(x) - dt.date.fromisoformat(d)).days) <= 3 for x in adds.get(t, []))
        (hit if ok else miss).append({"ticker": t, "wikiDateAdded": d, "parsed": adds.get(t)})
    by_year = {}
    for t, d in cand:
        y = d[:4]
        by_year.setdefault(y, [0, 0])
        by_year[y][1] += 1
    for h in hit:
        by_year[h["wikiDateAdded"][:4]][0] += 1
    out = {"currentMembers": len(rows), "addedSinceFirstListingDate": len(cand), "matchedWithin3Days": len(hit),
           "coveragePct": round(100 * len(hit) / len(cand), 1) if cand else None,
           "byYear": {y: {"matched": a, "of": b} for y, (a, b) in sorted(by_year.items())},
           "unmatched": miss}
    json.dump(out, open(os.path.join(HERE, "results", "sp500-coverage-crosscheck.json"), "w"), indent=1)
    print({k: v for k, v in out.items() if k != "unmatched"})


if __name__ == "__main__":
    main()
