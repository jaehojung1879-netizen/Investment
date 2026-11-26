"""Resolve screened share-unit jumps against the original single-class SEC context."""
from __future__ import annotations

import argparse
import concurrent.futures
import gzip
import html
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError

import pandas as pd

from research.kr_us_public_buys_v1 import wat_sources

HERE = Path(__file__).resolve().parent
SEC = "https://www.sec.gov"


def source_url(index_blob):
    for row in re.findall(rb"<tr\b[^>]*>(.*?)</tr>", index_blob, flags=re.S|re.I):
        if b"iXBRL" in row and re.search(rb">10-[QK]<", row):
            href = re.search(rb'href="([^"]+)"', row).group(1).decode()
            return SEC + html.unescape(href).removeprefix("/ix?doc=")
    for row in re.findall(rb"<tr\b[^>]*>(.*?)</tr>", index_blob, flags=re.S|re.I):
        if b"EX-101.INS" in row or b"XBRL INSTANCE DOCUMENT" in row:
            href = re.search(rb'href="([^"]+\.xml)"', row).group(1).decode()
            return SEC + html.unescape(href)
    raise ValueError("SEC raw cover context unavailable")


def primary_url(index_blob):
    for row in re.findall(rb"<tr\b[^>]*>(.*?)</tr>", index_blob, flags=re.S|re.I):
        if re.search(rb">1</td>", row) and re.search(rb">10-[QK]</td>", row):
            href = re.search(rb'href="([^"]+)"', row).group(1).decode()
            return SEC + html.unescape(href).removeprefix("/ix?doc=")
    raise ValueError("SEC index primary document is unavailable")


def less_markup(blob):
    string = blob.decode("utf-8", errors="replace")
    visible = re.sub(r"<(ix:header|script|style)\b[^>]*>.*?</\1>", " ", string,
                     flags=re.S|re.I)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", visible)))


def legible_cover_value(primary, fact):
    """Match formatted text on the cover, separate from the machine XBRL quantity."""
    opening_text = less_markup(primary)[:13000]
    as_tagged = fact["shares"]
    possibilities = [as_tagged, *(as_tagged//s for s in (1000, 1000000) if as_tagged % s == 0)]
    matches = set()
    for n in possibilities:
        for text in (f"{n:,}", str(n)):
            pattern = rf"(?<![0-9.,]){text}(?![0-9.,])"
            if re.search(pattern, opening_text):
                matches.add(n)
    if len(matches) != 1:
        return None
    return matches.pop()


def capture(url, cache_path, fetch):
    if cache_path.is_file():
        return gzip.decompress(cache_path.read_bytes())
    if not fetch:
        raise FileNotFoundError(cache_path)
    raw = wat_sources.sec_get(url)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(gzip.compress(raw, compresslevel=3, mtime=0))
    return raw


def review_group(item, cache, fetch):
    (ticker, cik, acc), group = item
    cik = int(cik)
    folder = f"/Archives/edgar/data/{cik}/{acc.replace('-', '')}"
    index_url = SEC + f"{folder}/{acc}-index.htm"
    info = {"ticker": ticker, "cik": cik, "sourceId": acc, "indexURL": index_url}
    confirmed = []
    try:
        index = capture(index_url, cache/f"{acc}-index.html.gz", fetch)
        url = source_url(index)
        body = capture(url, cache/f"{acc}-cover.html.gz", fetch)
        try:
            facts = wat_sources.cover_shares(body)
        except (KeyError, ValueError) as exc:
            return confirmed, {**info, "status": "UNRESOLVED_FILING_XML", "reason": str(exc)}
        stamp = wat_sources.acceptance(index)
        info.update(sourceURL=url, indexSha256=wat_sources.sha(index), bodySha256=wat_sources.sha(body),
                    acceptedET=stamp.isoformat(), facts=facts)
        if ticker == "EIX" and acc == "0000827052-20-000026":
            cover = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body.decode())))
            assert "Edison International 362,570,075 shares" in cover
            assert "Southern California Edison Company 434,888,104 shares" in cover
            assert [f["shares"] for f in facts] == [362_570_075_000_000, 434_888_104_000_000]
            return confirmed, {**info, "status": "TAG_SCALE_CONTRADICTS_LEGIBLE_COVER",
                               "legibleParentCommonShares": 362_570_075,
                               "legibleSubsidiaryCommonShares": 434_888_104,
                               "candidateDates": len(group)}
        if len(facts) != 1 or facts[0]["contextDimensions"] or int(facts[0]["shareCik"]) != cik:
            return confirmed, {**info, "status": "ISSUER_SHARE_CLASS_NOT_UNIQUE"}
        fact = facts[0]
        filing_url = primary_url(index)
        primary = body if filing_url == url else capture(filing_url, cache/f"{acc}-primary.html.gz", fetch)
        readable = legible_cover_value(primary, fact)
        info.update(primaryURL=filing_url, primarySha256=wat_sources.sha(primary),
                    legibleCoverQuantity=readable)
        if readable is None:
            return confirmed, {**info, "status": "RAW_QUANTITY_NOT_FOUND_UNIQUELY_IN_COVER_TEXT",
                               "candidateDates": len(group)}
        factor = fact["shares"]/readable
        if factor != 1:
            info["primaryTextVsReportedTagScaleFactor"] = factor
        passed = 0
        for r in group.itertuples(index=False):
            cutoff = wat_sources.decision_close(r.date)
            if stamp >= cutoff or r.candidateShares != fact["shares"] or r.shareAsOf != fact["shareAsOf"]:
                continue
            true_vs_old = readable/r.previousShares
            if not any(.8*scale <= true_vs_old <= 1.2*scale for scale in (1e-6, 1e-3, 1e3, 1e6)):
                continue
            confirmed.append({"date": r.date, "ticker": ticker, "correctedMarketCap": r.rawAsTradedPrice*readable,
                              "sourceId": acc, "case": "SEC_COVER_VERIFIED_SHARE_MAGNITUDE",
                              "previousMarketCap": r.previousMarketCap, "previousShares": r.previousShares,
                              "confirmedActualShares": readable, "rawAsTradedPrice": r.rawAsTradedPrice,
                              "shareAsOf": fact["shareAsOf"], "acceptedET": stamp.isoformat(), "sourceURL": filing_url})
            passed += 1
        status = "CONFIRMED" if passed else "NO_MAGNITUDE_ERROR_AFTER_READABLE_COVER" if factor != 1 else "SEC_CONTEXT_MISMATCH"
        return confirmed, {**info, "status": status,
                           "appliedDates": passed, "candidateDates": len(group)}
    except (HTTPError, URLError, FileNotFoundError, ValueError, AttributeError) as exc:
        # Prices, weights, and other source candidates remain usable.
        return confirmed, {**info, "status": "UNRESOLVED_OFFICIAL_SOURCE", "reason": str(exc)}
    finally:
        if fetch:
            time.sleep(.45)


def run(screen, cache, fetch=False):
    audit, confirmed = [], []
    groups = screen.groupby(["ticker", "sourceCik", "sourceId"], sort=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for rows, review in pool.map(lambda item: review_group(item, cache, fetch), groups):
            audit.append(review)
            confirmed.extend(rows)
    return pd.DataFrame(confirmed), audit


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, default=Path("/workspace/wat-sec-inputs/official-contexts"))
    ap.add_argument("--out", type=Path, default=HERE/"results/WAT")
    ap.add_argument("--fetch", action="store_true")
    a = ap.parse_args(argv)
    screen = pd.read_csv(a.out/"sec-fact-screen.csv", parse_dates=["date"])
    confirmed, audit = run(screen, a.cache, a.fetch)
    columns = ["date", "ticker", "correctedMarketCap", "sourceId", "case", "previousMarketCap",
               "previousShares", "confirmedActualShares", "rawAsTradedPrice", "shareAsOf", "acceptedET", "sourceURL"]
    confirmed.reindex(columns=columns).to_csv(a.out/"verified-non-wat-caps.csv", index=False)
    (a.out/"sec-context-verification-receipts.json").write_text(json.dumps(audit, indent=2)+"\n")
    print("Screened accession/symbol groups", len(audit), "confirmed cap rows", len(confirmed))


if __name__ == "__main__":
    main()
