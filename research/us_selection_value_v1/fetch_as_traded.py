"""Yahoo split events + split-adjusted (NOT dividend-adjusted) closes, to rebuild as-traded prices for market cap and value yields.

    python -m research.us_selection_value_v1.fetch_as_traded --tickers <file> --out <private dir outside git>

Raw responses stay outside git (vendor terms). Only the per-ticker summary (served/failed, split count, sha256) is published.
Feature code reads ONLY the as-traded close on or before each signal date; the later rows in a response are never read by it.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import time
import urllib.request
from pathlib import Path

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{t}?period1=1293840000&period2=1789000000&interval=1d&events=split"
UA = "Mozilla/5.0 (research audit)"


def fetch(ticker, out: Path, pause=0.35):
    path = out / (ticker + ".json.gz")
    if path.exists():
        return json.loads(gzip.decompress(path.read_bytes()))["status"]
    sym = ticker.replace(".", "-")
    try:
        req = urllib.request.Request(URL.format(t=sym), headers={"User-Agent": UA})
        raw = urllib.request.urlopen(req, timeout=40).read()
        d = json.loads(raw)["chart"]["result"][0]
        q = d["indicators"]["quote"][0]
        rows = [[ts, c] for ts, c in zip(d.get("timestamp", []), q.get("close", [])) if c is not None]
        splits = sorted(((int(s["date"]), float(s["numerator"]), float(s["denominator"])) for s in (d.get("events") or {}).get("splits", {}).values()))
        rec = {"status": "SERVED", "ticker": ticker, "symbol": sym, "rows": rows, "splits": splits,
               "currency": d["meta"].get("currency"), "sha256": hashlib.sha256(raw).hexdigest()}
    except Exception as e:  # noqa: BLE001
        rec = {"status": "FAILED", "ticker": ticker, "error": repr(e)[:200]}
    path.write_bytes(gzip.compress(json.dumps(rec).encode()))
    time.sleep(pause)
    return rec["status"]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tickers = [t.strip() for t in Path(a.tickers).read_text().split() if t.strip()]
    stats = {}
    for i, t in enumerate(tickers):
        stats[t] = fetch(t, out)
        if i % 50 == 0:
            print(i, t, stats[t], flush=True)
    print(json.dumps({"served": sum(v == "SERVED" for v in stats.values()), "failed": sorted(t for t, v in stats.items() if v != "SERVED")}))


if __name__ == "__main__":
    main()
