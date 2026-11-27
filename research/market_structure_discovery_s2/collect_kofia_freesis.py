"""Collect KOFIA FreeSIS market-level daily statistics (public, no login).

Endpoint: POST https://freesis.kofia.or.kr/meta/getMetaDataList.do (JSON).
STATSCU0100000060BO: 증시자금 추이 (investor deposits, margin receivables, forced-sale
  amounts on receivables) — column meaning is recorded in the README from the FreeSIS
  screen, not inferred from values.
STATSCU0100000070BO: 신용공여 잔고 추이 (margin loan / stock loan balances).
Stores the exact response bytes' SHA-256 and the rows. Market-level only; no stock price
or return is read.
Usage: python collect_kofia_freesis.py <stat_code> <YYYYMMDD start> <YYYYMMDD end> <out.json>
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import urllib.request

URL = "https://freesis.kofia.or.kr/meta/getMetaDataList.do"


def main() -> None:
    code, start, end, out = sys.argv[1:5]
    payload = {"dmSearch": {"tmpV40": "1000000", "tmpV41": "1", "tmpV1": "D",
                            "tmpV45": start, "tmpV46": end, "OBJ_NM": code}}
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "Mozilla/5.0 (research)"})
    with urllib.request.urlopen(req, timeout=120) as r:
        body = r.read()
    j = json.loads(body)
    rec = {"statCode": code, "request": payload, "sha256": hashlib.sha256(body).hexdigest(),
           "bytes": len(body), "fetchedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "unit": j.get("unit"), "rows": j.get("ds1")}
    json.dump(rec, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    rows = rec["rows"] or []
    print(code, len(rows), rows[-1] if rows else None, rows[0] if rows else None)


if __name__ == "__main__":
    main()
