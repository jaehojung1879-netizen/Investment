"""Parse S&P 500 additions/deletions, announcement time and effective date from releases.

Reads data/spdji_bodies.jsonl (release text only). For every 'A (EXCH: X) will replace
B (EXCH: Y) in the S&P 500' clause, records the added and removed tickers, the release
timestamp (US Eastern, first public availability) and the effective-date phrase found in
the same paragraph. Clauses that cannot be parsed are listed, never dropped silently.
No price or return is read.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys

TICK = re.compile(r"\((?:NYSE|NASD|NASDAQ|NYSE Arca|NYSE MKT|NYSE American|Cboe BZX|BATS|CBOE)\s*:\s*([A-Z][A-Z0-9.\-]*)\s*\)")
REPLACE = re.compile(r"will replace")
TARGET = re.compile(r"\s*(?:,? ?respectively,? ?)?in the S&P 500\b(?! ESG)")
LEFT_CUT = re.compile(
    r"(in the S&P (?:MidCap 400|SmallCap 600|500|100)[^,;]*[,;]|;|following changes[^:]*:|"
    r"(?<!Inc)(?<!Corp)(?<!Co)(?<!Ltd)(?<!plc)(?<!Cos)(?<!Bros)(?<!Hldgs)(?<![A-Z])\. (?=[A-Z]))"
)
EFF = re.compile(
    r"(prior to the open(?:ing)? of trading|after the close of trading|effective)\D{0,40}?"
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan\.?|Feb\.?|Mar\.?|Apr\.?|Jun\.?|Jul\.?|Aug\.?|Sep\.?|Sept\.?|Oct\.?|Nov\.?|Dec\.?)\s+(\d{1,2})",
    re.I,
)
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def eff_date(par: str, start: int, released: dt.datetime, body: str = ""):
    after = EFF.search(par, start)
    m = after or EFF.search(par) or (EFF.search(body) if body else None)
    if not m:
        return None, None
    mon = MONTHS[m.group(2)[:3].lower()]
    day = int(m.group(3))
    year = released.year + (1 if mon < released.month - 6 else 0)
    try:
        d = dt.date(year, mon, day)
    except ValueError:
        return None, None
    timing = "AFTER_CLOSE" if "close" in m.group(1).lower() else "BEFORE_OPEN"
    return d, timing


TABLE_DATE = re.compile(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.? (\d{1,2}), (\d{4})$")


def table_rows(body: str) -> list[dict]:
    """Summary table: Effective Date / Index Name / Action / Company Name / Ticker / GICS Sector."""
    lines = body.split("\n")
    out = []
    for i, line in enumerate(lines):
        if line.strip() != "GICS Sector" or i < 5 or lines[i - 1].strip() != "Ticker":
            continue
        j = i + 1
        while j + 5 < len(lines) + 1 and j + 4 < len(lines):
            m = TABLE_DATE.match(lines[j].strip())
            if not m:
                break
            idx, action, ticker = lines[j + 1].strip(), lines[j + 2].strip(), lines[j + 4].strip()
            mon = MONTHS[m.group(1)[:3].lower()]
            out.append({"effectiveDate": dt.date(int(m.group(3)), mon, int(m.group(2))).isoformat(),
                        "index": idx, "action": action, "ticker": ticker})
            j += 6
    return out


def main() -> None:
    src, out = sys.argv[1], sys.argv[2]
    events, unparsed = [], []
    for line in open(src, encoding="utf-8"):
        r = json.loads(line)
        if "body" not in r:
            unparsed.append({"url": r["url"], "reason": "FETCH_ERROR"})
            continue
        released = dt.datetime.fromisoformat(r["releasedEt"])
        trows = [t for t in table_rows(r["body"]) if t["index"] == "S&P 500"]
        if trows:
            by_date = {}
            for t in trows:
                g = by_date.setdefault(t["effectiveDate"], {"added": [], "removed": []})
                (g["added"] if t["action"].startswith("Add") else g["removed"]).append(t["ticker"])
            for d, g in by_date.items():
                events.append({"url": r["url"], "releasedEt": r["releasedEt"], "added": g["added"],
                               "removed": g["removed"], "effectiveDate": d, "timing": "BEFORE_OPEN",
                               "parsedFrom": "SUMMARY_TABLE"})
            continue
        for par in r["body"].split("\n"):
            if "S&P 500" not in par:
                continue
            for m in REPLACE.finditer(par):
                tgt = TARGET.match(par, m.end() + 0)
                right_end = None
                # right side: tickers between 'will replace' and the next 'in the S&P ...'
                nxt = re.search(r"in the S&P (MidCap 400|SmallCap 600|500|100)\b", par[m.end():])
                if not nxt:
                    continue
                if nxt.group(1) != "500":
                    continue
                right_end = m.end() + nxt.start()
                right = TICK.findall(par[m.end():right_end])
                left_txt = par[:m.start()]
                cuts = list(LEFT_CUT.finditer(left_txt))
                left_txt = left_txt[cuts[-1].end():] if cuts else left_txt
                left = TICK.findall(left_txt)
                d, timing = eff_date(par, right_end, released, r["body"])
                rec = {"url": r["url"], "releasedEt": r["releasedEt"], "added": left, "removed": right,
                       "effectiveDate": d.isoformat() if d else None, "timing": timing,
                       "clause": par[max(0, m.start() - 200): right_end + 160][:500], "parsedFrom": "CLAUSE"}
                if not left or not right or d is None:
                    unparsed.append({**rec, "reason": "INCOMPLETE_CLAUSE"})
                else:
                    events.append(rec)
                _ = tgt
    json.dump({"events": events, "unparsed": unparsed}, open(out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("events", len(events), "unparsed", len(unparsed))


if __name__ == "__main__":
    main()
