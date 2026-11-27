"""Collect KODEX ETF PDF (portfolio deposit file) snapshots from the issuer's public API.

Source: Samsung Asset Management public KODEX site (robots.txt: `allow: /`).
Endpoint: https://www.samsungfund.com/api/v1/kodex/product-pdf/{fId}.do?gijunYMD=YYYY.MM.DD
Each response is the creation/redemption basket for one CU on the stated base date.

Stores, per (fId, requested date): the date the server answered for, the SHA-256 of
the exact response bytes, and the security rows (code, name, shares per CU, value per
CU, weight). No price after the base date and no return is read or derived here.
Usage: python collect_kodex_pdf.py <fId> <start YYYY-MM-DD> <end YYYY-MM-DD> <out.jsonl> [review] [sleep]
The optional 'review' mode requests only the Wednesday before the second-Thursday expiry and the following
Monday of each June and December (2 calls per regular review), and [sleep] sets the
pause between requests in seconds (default 1.0). The issuer moved this API behind a
Cloudflare challenge after about 550 requests on 2026-11-26; never solve or bypass it.
Dates: the first Friday of every month (bounds unscheduled changes to about one month)
plus Wednesday, Thursday, Friday and the following Monday of the week of the second
Thursday of June and December (the KOSPI 200 / KOSDAQ 150 regular reviews take effect
the session after that derivatives expiry). Successfully collected request dates are skipped
(append-only); an error row is kept as a record and the date is retried on a later run.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sys
import time
import urllib.request

API = "https://www.samsungfund.com/api/v1/kodex/product-pdf/{fid}.do?gijunYMD={d}"
UA = "Mozilla/5.0 (research; low-rate)"


def schedule(start: dt.date, end: dt.date) -> list[dt.date]:
    out = set()
    d = start
    while d <= end:
        if d.weekday() == 4 and d.day <= 7:
            out.add(d)
        if d.month in (6, 12) and d.weekday() == 3 and 8 <= d.day <= 14:
            for k in (-1, 0, 1, 4):
                x = d + dt.timedelta(days=k)
                if start <= x <= end:
                    out.add(x)
        d += dt.timedelta(days=1)
    return sorted(out)


def review_schedule(start: dt.date, end: dt.date) -> list[dt.date]:
    out = []
    for y in range(start.year, end.year + 1):
        for mth in (6, 12):
            d = dt.date(y, mth, 8)
            while d.weekday() != 3:
                d += dt.timedelta(days=1)
            for x in (d - dt.timedelta(days=1), d + dt.timedelta(days=4)):
                if start <= x <= end:
                    out.append(x)
    return out


def fetch(fid: str, d: dt.date) -> tuple[bytes, dict]:
    url = API.format(fid=fid, d=d.strftime("%Y.%m.%d"))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
    return body, json.loads(body)


def main() -> None:
    fid, s, e, out = sys.argv[1], *sys.argv[2:5]
    mode = sys.argv[5] if len(sys.argv) > 5 else "full"
    pause = float(sys.argv[6]) if len(sys.argv) > 6 else 1.0
    start, end = dt.date.fromisoformat(s), dt.date.fromisoformat(e)
    done = set()
    if os.path.exists(out):
        with open(out, encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                if "error" not in rec:
                    done.add(rec["requested"])
    with open(out, "a", encoding="utf-8") as fh:
        dates = review_schedule(start, end) if mode == "review" else schedule(start, end)
        for d in dates:
            key = d.isoformat()
            if key in done:
                continue
            try:
                body, j = fetch(fid, d)
            except Exception as exc:  # noqa: BLE001 - recorded, never retried in a loop
                err = repr(exc)
                fh.write(json.dumps({"fId": fid, "requested": key, "error": err}) + "\n")
                if "429" in err:
                    # a throttle or bot challenge is an access control: stop, do not retry
                    print("STOPPED_ON_429", key)
                    return
                time.sleep(pause)
                continue
            p = j.get("pdf") or {}
            rows = [
                [r.get("itmNo"), r.get("secNm"), r.get("applyQ"), r.get("evalA"), r.get("ratio")]
                for r in (p.get("list") or [])
            ]
            rec = {
                "fId": fid,
                "requested": key,
                "answeredFor": p.get("gijunYMD"),
                "totalCnt": p.get("totalCnt"),
                "sha256": hashlib.sha256(body).hexdigest(),
                "bytes": len(body),
                "fetchedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "rows": rows,
            }
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            time.sleep(pause)


if __name__ == "__main__":
    main()
