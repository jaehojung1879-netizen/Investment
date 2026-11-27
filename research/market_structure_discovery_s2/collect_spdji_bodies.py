"""Fetch the body text of S&P DJI index-change releases selected from the listing.

Selection (made from headlines only, before any body is read): the headline or snippet
names the S&P 500, or reads 'Announces Change(s) to U.S. Index'. Stores the release
text paragraphs and the SHA-256 of the full page bytes. No price or return is read.
Usage: python collect_spdji_bodies.py <releases.jsonl> <out.jsonl>
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.request

UA = "Mozilla/5.0 (research; low-rate)"
SEL = re.compile(r"S&P 500|Announces Changes? to U\.S\. Ind", re.I)
SKIP = re.compile(r"Case-Shiller|Dividend|ESG|Shariah|Bond|VIX|Futures|Climate|Kalshi|collaborat", re.I)


def body_text(s: str) -> str:
    m = re.search(r'<section class="release-body[^"]*"[^>]*>(.*?)</section>', s, re.S)
    chunk = m.group(1) if m else s
    paras = re.findall(r"<(p|td|li)[^>]*>(.*?)</\1>", chunk, re.S)
    out = []
    for _tag, p in paras:
        t = " ".join(html.unescape(re.sub("<[^>]+>", " ", p)).split())
        if t:
            out.append(t)
    return "\n".join(out)


def main() -> None:
    src, out = sys.argv[1], sys.argv[2]
    done = set()
    if os.path.exists(out):
        done = {json.loads(line)["url"] for line in open(out, encoding="utf-8")}
    rows = [json.loads(line) for line in open(src, encoding="utf-8")]
    with open(out, "a", encoding="utf-8") as fh:
        for r in rows:
            if r["url"] in done or not SEL.search(r["text"]) or SKIP.search(r["text"][:120]):
                continue
            try:
                req = urllib.request.Request(r["url"], headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=40) as resp:
                    b = resp.read()
                rec = {**r, "sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b),
                       "body": body_text(b.decode("utf-8", "replace"))[:20000]}
            except Exception as exc:  # noqa: BLE001 - recorded
                rec = {**r, "error": repr(exc)}
            rec["fetchedAtUtc"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            time.sleep(0.8)


if __name__ == "__main__":
    main()
