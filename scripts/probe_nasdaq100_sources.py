"""Which sources can rebuild Nasdaq-100 membership as it was knowable, and can
an independent vendor corroborate the sealed SPY/QQQ total-return basis?

    python scripts/probe_nasdaq100_sources.py --output probe-output.json

Bounded by construction: a fixed list of URLs, ONE attempt each, no retry, no
credential, no pagination beyond the fixed Wikipedia year-start revisions, and
nothing written anywhere but ``--output``. The full result is also printed as
one JSON line so it survives in the job log.

Candidates (each judged on depth, publication/effective dates, inclusion AND
exclusion completeness, identity, licence, reproducibility, cost, Actions
reachability and survivorship):

* nasdaq-current-list   api.nasdaq.com current constituents (today only)
* nasdaq-methodology    official NDX methodology PDF
* nasdaq-annual-doc     official annual-evaluation PDF
* globenewswire-search  official press releases ("Annual Changes to the Nasdaq-100 Index")
* invesco-holdings      QQQ daily holdings file (today only)
* sec-nport-index       QQQ (CIK 1067839) N-PORT filing index; SEC was refused from Actions before
* wikipedia-revisions   the public "Nasdaq-100" article as it stood on each 1 January,
                        each revision timestamped and content-hashed (non-authoritative)
* nasdaq-price-history  api.nasdaq.com raw daily closes and dividends for QQQ and SPY
                        (an independent vendor for the basis check)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

TIMEOUT = 25
WIKI_UA = "InvestmentResearchProbe/1.0 (https://github.com/jaehojung1879-netizen/investment; research probe)"
BROWSER_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0 Safari/537.36")
NASDAQ_HEADERS = {"User-Agent": BROWSER_UA, "Accept": "application/json, text/plain, */*",
                  "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"}
WIKI_API = "https://en.wikipedia.org/w/api.php"
YEARS = range(2013, 2027)
PRICE_START, PRICE_END = "2011-01-01", "2026-09-14"

STATIC = [
    ("nasdaq-current-list", "https://api.nasdaq.com/api/quote/list-type/nasdaq100", NASDAQ_HEADERS),
    ("nasdaq-methodology", "https://indexes.nasdaqomx.com/docs/Methodology_NDX.pdf", {"User-Agent": BROWSER_UA}),
    ("nasdaq-annual-doc", "https://indexes.nasdaqomx.com/docs/NDX100_AnnualEvaluation.pdf", {"User-Agent": BROWSER_UA}),
    ("globenewswire-search",
     "https://www.globenewswire.com/search/keyword/" + urllib.parse.quote("Annual Changes to the Nasdaq-100 Index"),
     {"User-Agent": BROWSER_UA}),
    ("invesco-holdings",
     "https://www.invesco.com/us/financial-products/etfs/holdings/main/holdings/0?audienceType=Investor&action=download&ticker=QQQ",
     {"User-Agent": BROWSER_UA}),
    ("sec-nport-index",
     "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001067839&type=NPORT-P&dateb=&owner=include&count=40",
     {"User-Agent": "InvestmentResearchProbe research@example.invalid"}),
]


def get(url: str, headers: dict) -> dict:
    request = urllib.request.Request(url, headers=headers)
    started = datetime.now(timezone.utc)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = response.read()
            status, ctype = response.status, response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        body, status, ctype = exc.read() or b"", exc.code, exc.headers.get("Content-Type", "")
    except Exception as exc:  # network refusal is a measurement, not a crash
        return {"url": url, "status": None, "error": f"{type(exc).__name__}: {exc}"[:300],
                "fetchedAt": started.isoformat(timespec="seconds"), "_body": b""}
    return {"url": url, "status": status, "contentType": ctype[:80], "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "fetchedAt": started.isoformat(timespec="seconds"), "_body": body}


def public(row: dict) -> dict:
    return {k: v for k, v in row.items() if not k.startswith("_")}


def text_signals(body: bytes) -> dict:
    text = body[:400000].decode("utf-8", "replace")
    return {"mentionsNasdaq100": bool(re.search(r"Nasdaq-100|NASDAQ-100", text)),
            "mentionsAnnualChanges": len(re.findall(r"Annual Changes to the Nasdaq-100", text, re.I)),
            "looksLikeLogin": bool(re.search(r"sign in|log in|subscribe", text[:20000], re.I)),
            "head": re.sub(r"\s+", " ", text[:160])}


TICKER_CELL = re.compile(r"^\s*\{?\{?(?:[A-Za-z]+\|)?([A-Z]{1,5}(?:\.[A-Z])?)\}?\}?\s*$")


def tickers_from_wikitext(wikitext: str) -> list[str]:
    """Tickers in the components table: the first all-caps 1-5 letter cell of a row.

    Deliberately simple and reported with its own counts, because the article's
    table layout changed over the years; a parse that finds ~100 names is
    plausible, one that finds 20 or 400 is reported as such, not trusted.
    """
    section = wikitext
    match = re.search(r"==\s*(Current )?[Cc]omponents\s*==(.*?)(\n==[^=])", wikitext, re.S)
    if match:
        section = match.group(2)
    found = []
    for row in section.split("\n|-"):
        cells = re.split(r"\|\||\n\|", row)
        for cell in cells:
            cell = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", cell)
            cell = re.sub(r"<[^>]+>", "", cell).strip().strip("|").strip()
            m = TICKER_CELL.match(cell)
            if m and m.group(1) not in {"NASDAQ", "GICS", "ICB", "NYSE", "USD"}:
                found.append(m.group(1))
                break
    return sorted(set(found))


def wikipedia() -> dict:
    out = {"license": "CC BY-SA 4.0", "authority": "NON_AUTHORITATIVE_PUBLIC_EDIT_HISTORY",
           "snapshots": []}
    for year in YEARS:
        stamp = f"{year}-01-01T00:00:00Z"
        query = WIKI_API + "?" + urllib.parse.urlencode({
            "action": "query", "prop": "revisions", "titles": "Nasdaq-100", "rvlimit": 1,
            "rvstart": stamp, "rvdir": "older", "rvprop": "ids|timestamp|content|sha1",
            "rvslots": "main", "format": "json", "formatversion": 2})
        row = get(query, {"User-Agent": WIKI_UA})
        snap = {"asOfRequested": stamp, **public(row)}
        try:
            page = json.loads(row["_body"])["query"]["pages"][0]
            rev = page["revisions"][0]
            content = rev["slots"]["main"]["content"]
            tickers = tickers_from_wikitext(content)
            snap.update({"revid": rev["revid"], "revisionTimestamp": rev["timestamp"],
                         "contentSha256": hashlib.sha256(content.encode()).hexdigest(),
                         "parsedTickers": tickers, "parsedTickerCount": len(tickers),
                         "hasChangesSection": bool(re.search(r"==\s*[^=\n]*[Cc]hanges", content))})
        except Exception as exc:
            snap["parseError"] = f"{type(exc).__name__}: {exc}"[:200]
        out["snapshots"].append(snap)
        if snap.get("status") is None:
            break                                   # host unreachable: do not hammer it
    return out


def _num(text: str) -> float | None:
    try:
        return float(str(text).replace("$", "").replace(",", "").strip())
    except ValueError:
        return None


def nasdaq_prices(symbol: str) -> dict:
    hist = get(f"https://api.nasdaq.com/api/quote/{symbol}/historical?assetclass=etf"
               f"&fromdate={PRICE_START}&todate={PRICE_END}&limit=9999", NASDAQ_HEADERS)
    divs = get(f"https://api.nasdaq.com/api/quote/{symbol}/dividends?assetclass=etf", NASDAQ_HEADERS)
    out = {"history": public(hist), "dividends": public(divs)}
    closes, events = {}, []
    try:
        rows = json.loads(hist["_body"])["data"]["tradesTable"]["rows"]
        for r in rows:
            d = datetime.strptime(r["date"], "%m/%d/%Y").strftime("%Y-%m-%d")
            closes[d] = _num(r["close"])
    except Exception as exc:
        out["historyParseError"] = f"{type(exc).__name__}: {exc}"[:200]
    try:
        rows = json.loads(divs["_body"])["data"]["dividends"]["rows"]
        for r in rows:
            ex = r.get("exOrEffDate")
            if ex and ex != "N/A":
                events.append({"exDate": datetime.strptime(ex, "%m/%d/%Y").strftime("%Y-%m-%d"),
                               "amount": _num(r.get("amount")), "type": r.get("type"),
                               "paymentDate": r.get("paymentDate"), "declarationDate": r.get("declarationDate")})
    except Exception as exc:
        out["dividendsParseError"] = f"{type(exc).__name__}: {exc}"[:200]
    events = sorted((e for e in events if e["exDate"] >= PRICE_START),
                    key=lambda e: (e["exDate"], str(e["amount"])))
    dates = sorted(closes)
    keep = set()
    month_end = {}
    for d in dates:
        month_end[d[:7]] = d
    keep.update(month_end.values())
    for e in events:
        pos = next((i for i, d in enumerate(dates) if d >= e["exDate"]), None)
        if pos is not None:
            keep.update(dates[max(pos - 1, 0):pos + 1])
    out.update({"sessions": len(dates), "firstSession": dates[0] if dates else None,
                "lastSession": dates[-1] if dates else None,
                "allClosesSha256": hashlib.sha256(json.dumps(closes, sort_keys=True).encode()).hexdigest(),
                "sampledCloses": {d: closes[d] for d in sorted(keep)},
                "distributions": events})
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    result = {"schema": "NASDAQ100_SOURCE_PROBE_V1",
              "startedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "bounded": "fixed URL list, one attempt each, no credentials",
              "sources": {}}
    for name, url, headers in STATIC:
        row = get(url, headers)
        result["sources"][name] = {**public(row), **(text_signals(row["_body"]) if row["_body"] else {})}
        if name == "nasdaq-current-list" and row["_body"]:
            try:
                rows = json.loads(row["_body"])["data"]["data"]["rows"]
                result["sources"][name]["currentSymbols"] = sorted(r["symbol"] for r in rows)
            except Exception as exc:
                result["sources"][name]["parseError"] = f"{type(exc).__name__}: {exc}"[:200]
    result["sources"]["wikipedia-revisions"] = wikipedia()
    result["sources"]["nasdaq-price-history"] = {s: nasdaq_prices(s) for s in ("QQQ", "SPY")}
    result["finishedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = json.dumps(result, sort_keys=True, separators=(",", ":"))
    with open(args.output, "w") as handle:
        handle.write(payload + "\n")
    print("PROBE_RESULT_SHA256 " + hashlib.sha256(payload.encode()).hexdigest())
    print("PROBE_RESULT_JSON " + payload)
    for name, row in result["sources"].items():
        if "status" in row:
            print(f"{name}: status={row.get('status')} bytes={row.get('bytes')} err={row.get('error')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
