"""Fetch the raw inputs of us-macro-cocktail-v1 and freeze them by SHA-256.

Research-only. Writes under research/us_macro_cocktail_v1/data/raw/ and nothing
else. Every response is stored exactly as served (gzip of the raw bytes), and the
manifest records URL, fetch time, byte size and SHA-256 of the uncompressed body,
so the study can be re-run from the frozen bytes without touching the network.

Sources
- Yahoo Finance chart API v8 (daily, events=div,split): ETF closes (split-adjusted,
  NOT dividend-adjusted), vendor adjclose, and dated cash distributions / splits.
- FRED fredgraph.csv: current-vintage daily market series (yields, VIX, FX).

Usage: python research/us_macro_cocktail_v1/fetch_data.py [--only SPY,DGS10]
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "data" / "raw"
MANIFEST = HERE / "data" / "manifest.json"
UA = "Mozilla/5.0 (research fetch; us-macro-cocktail-v1)"

YAHOO = ["SPY", "QQQ", "IEF", "TLT", "SHY", "BIL", "GLD", "UUP", "KRW=X"]
FRED = ["DGS10", "DGS2", "DGS3MO", "DTB3", "T10YIE", "DFII10", "VIXCLS", "DEXKOUS",
        "DTWEXBGS", "SP500", "NASDAQ100"]


def _get(url: str, attempts: int = 7) -> bytes:
    last = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read()
            if not body:
                raise ValueError("EMPTY_BODY")
            return body
        except Exception as exc:  # network flakiness through the egress proxy
            last = exc
            time.sleep(min(15 * (i + 1), 90))
            if "query2.finance" in url:
                url = url.replace("query2.finance", "query1.finance")
            elif "query1.finance" in url:
                url = url.replace("query1.finance", "query2.finance")
    raise RuntimeError(f"FETCH_FAILED {url}: {last!r}")


def yahoo_url(symbol: str, end: int) -> str:
    return ("https://query2.finance.yahoo.com/v8/finance/chart/" + urllib.request.quote(symbol)
            + f"?period1=0&period2={end}&interval=1d&events=div%2Csplit&includeAdjustedClose=true")


def fred_url(series: str) -> str:
    return f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--end", default=dt.date.today().isoformat(),
                    help="last calendar date requested from Yahoo (exclusive bound is end+1)")
    args = ap.parse_args()
    only = {s for s in args.only.split(",") if s}
    end = int(dt.datetime.fromisoformat(args.end).replace(tzinfo=dt.timezone.utc).timestamp()) + 86400
    RAW.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"files": {}}
    jobs = [("yahoo", s, yahoo_url(s, end), f"yahoo_{s.replace('=', '_')}.json.gz") for s in YAHOO]
    jobs += [("fred", s, fred_url(s), f"fred_{s}.csv.gz") for s in FRED]
    for source, symbol, url, name in jobs:
        if only and symbol not in only:
            continue
        body = _get(url)
        if source == "yahoo":
            payload = json.loads(body)
            if payload.get("chart", {}).get("error"):
                raise RuntimeError(f"YAHOO_ERROR {symbol}: {payload['chart']['error']}")
        (RAW / name).write_bytes(gzip.compress(body, mtime=0))
        manifest["files"][name] = {
            "source": source, "symbol": symbol, "url": url,
            "fetchedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
        }
        manifest["files"] = dict(sorted(manifest["files"].items()))
        MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        print(f"{name}: {len(body)} bytes")
        time.sleep(8.0)


if __name__ == "__main__":
    main()
