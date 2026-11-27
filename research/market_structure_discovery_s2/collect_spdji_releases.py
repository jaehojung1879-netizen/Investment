"""Collect the S&P Dow Jones Indices press-release listing from PR Newswire.

Source: https://www.prnewswire.com/news/s%26p-dow-jones-indices/ (public listing).
Each listing row carries the release URL, headline and the release timestamp in US
Eastern time, which is the first public availability of an index-change announcement.
Writes one JSON line per listing page with the SHA-256 of the exact bytes, and one line
per release. No price or return is read.
Usage: python collect_spdji_releases.py <max_page> <out_pages.jsonl> <out_releases.jsonl>
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re
import sys
import time
import urllib.request

BASE = "https://www.prnewswire.com/news/s%26p-dow-jones-indices/?page={p}&pagesize=100"
UA = "Mozilla/5.0 (research; low-rate)"
ROW = re.compile(
    r'<a class="newsreleaseconsolidatelink[^"]*" href="([^"]+)"[^>]*>(.*?)</a>', re.S
)
STAMP = re.compile(r"<small>([A-Z][a-z]{2} \d{2}, \d{4}, \d{2}:\d{2} ET)</small>")


def main() -> None:
    max_page, out_pages, out_rel = int(sys.argv[1]), sys.argv[2], sys.argv[3]
    seen = set()
    with open(out_pages, "w", encoding="utf-8") as fp, open(out_rel, "w", encoding="utf-8") as fr:
        for p in range(1, max_page + 1):
            req = urllib.request.Request(BASE.format(p=p), headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                body = r.read()
            s = body.decode("utf-8", "replace")
            n = 0
            for m in ROW.finditer(s):
                inner = m.group(2)
                st = STAMP.search(inner)
                text = " ".join(html.unescape(re.sub("<[^>]+>", " ", inner)).split())
                if not st or m.group(1) in seen:
                    continue
                seen.add(m.group(1))
                stamp = dt.datetime.strptime(st.group(1), "%b %d, %Y, %H:%M ET")
                title = text.replace(st.group(1), "", 1).strip()
                fr.write(json.dumps({"url": "https://www.prnewswire.com" + m.group(1),
                                     "releasedEt": stamp.isoformat(timespec="minutes"),
                                     "text": title[:600]}, ensure_ascii=False) + "\n")
                n += 1
            fp.write(json.dumps({"page": p, "sha256": hashlib.sha256(body).hexdigest(),
                                 "bytes": len(body), "rows": n,
                                 "fetchedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}) + "\n")
            if n == 0:
                break
            time.sleep(1.0)


if __name__ == "__main__":
    main()
