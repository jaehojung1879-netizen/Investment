#!/usr/bin/env python3
"""Acquire the frozen source set of kr-market-risk-anatomy-v1 as immutable raw bytes plus a metadata audit.

Runs only inside the source workflow (network and keys). It verifies identity, bytes, hashes, date coverage, missingness, timestamps and units and
writes them down. It NEVER computes a return, a drawdown, an episode, a forward quantity or a result table, never prints a price value, and never
changes the scientific design frozen in research_specs/kr-market-risk-anatomy-v1-design.json. A failed source is recorded as failed, with its HTTP
status and message (no credential), never retried into a different instrument.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import kr_market_risk_source_parse as P  # noqa: E402
from pipeline import kr_market_risk_sources as S  # noqa: E402

OUT = ROOT / "data" / "kr-market-risk-anatomy-v1" / "sources"
USER_AGENT = "Mozilla/5.0 (compatible; kr-market-risk-anatomy-v1 source audit)"
FRED = "https://api.stlouisfed.org/fred/"
YAHOO_HOSTS = ("https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com")
START = "1990-01-01"
POSITIVE_PRICE_SOURCES = {"KR_REFERENCE", "KR_ROBUSTNESS", "VIX", "USDKRW"}


def get(url, headers=None, attempts=3, pause=2.0):
    last = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers=headers or {"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.status, response.read(), None
        except urllib.error.HTTPError as error:
            last = (error.code, b"", "HTTP " + str(error.code))
            if error.code in (400, 401, 403, 404):
                break
        except Exception as error:  # network refusals are recorded, never hidden
            last = (0, b"", type(error).__name__)
        time.sleep(pause * (attempt + 1))
    return last


def fetch_fred(entry, key, today):
    series = urllib.parse.quote(entry["symbol"])
    base = {"series_id": entry["symbol"], "api_key": key, "file_type": "json"}
    meta_status, meta_raw, meta_err = get(FRED + "series?" + urllib.parse.urlencode(base))
    obs_status, obs_raw, obs_err = get(FRED + "series/observations?" + urllib.parse.urlencode({**base, "observation_start": START, "observation_end": today}))
    del series
    return {"raw": {"observations.json": obs_raw, "series.json": meta_raw}, "status": {"observations": obs_status, "series": meta_status},
            "error": obs_err or meta_err, "host": "api.stlouisfed.org"}


def fetch_yahoo(entry, today):
    symbol = urllib.parse.quote(entry["symbol"], safe="")
    end = int(datetime.now(timezone.utc).timestamp())
    for host in YAHOO_HOSTS:
        url = f"{host}/v8/finance/chart/{symbol}?period1=0&period2={end}&interval=1d&events=div%2Csplit&includePrePost=false"
        status, raw, error = get(url)
        if status == 200 and raw:
            return {"raw": {"chart.json": raw}, "status": {"chart": status}, "error": None, "host": host.split("//")[1]}
    return {"raw": {}, "status": {"chart": status}, "error": error, "host": None}


def fetch_fdr(entry, today):
    import FinanceDataReader as fdr
    frame = fdr.DataReader(entry["symbol"], START, today)
    raw = frame.to_csv(index_label="Date").encode()
    return {"raw": {"fdr.csv": raw}, "status": {"fdr": 200}, "error": None, "host": "FinanceDataReader " + fdr.__version__}


def acquire_one(sid, entry, key, today, out):
    record = {"id": sid, "symbol": entry["symbol"], "vendor": entry["vendor"], "instrument": entry["instrument"], "basis": entry.get("basis"),
              "unit": entry.get("unit"), "vintageClass": entry["vintageClass"], "fetchedAtUtc": datetime.now(timezone.utc).isoformat(), "status": "FAILED"}
    try:
        got = {"fred": lambda: fetch_fred(entry, key, today), "yahoo_chart": lambda: fetch_yahoo(entry, today), "fdr": lambda: fetch_fdr(entry, today)}[entry["fetch"]]()
    except Exception as error:  # an import or transport failure is a recorded failure
        record["error"] = type(error).__name__ + ": " + str(error)[:200]
        return record
    record.update(httpStatus=got["status"], host=got["host"], error=got["error"])
    primary = {"fred": "observations.json", "yahoo_chart": "chart.json", "fdr": "fdr.csv"}[entry["fetch"]]
    raw_main = got["raw"].get(primary)
    if not raw_main:
        return record
    positive = entry["role"] in POSITIVE_PRICE_SOURCES
    identity = {}
    if entry["fetch"] == "fred":
        rows, dropped = P.parse_fred_observations(raw_main, positive)
        total = len(json.loads(raw_main).get("observations", []))
        if got["raw"].get("series.json"):
            identity = P.fred_identity(got["raw"]["series.json"])
    elif entry["fetch"] == "yahoo_chart":
        rows, dropped, identity = P.parse_yahoo_chart(raw_main, entry.get("field", "close"), positive)
        total = len(rows) + dropped
    else:
        rows, dropped = P.parse_fdr_csv(raw_main, entry.get("field", "Close"), positive)
        total = len(rows) + dropped
    directory = Path(out) / sid
    directory.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, data in got["raw"].items():
        if data:
            (directory / ("raw_" + name)).write_bytes(data)
            files["raw_" + name] = P.sha256(data)
    normalized = P.normalized_csv(rows)
    (directory / "normalized.csv").write_bytes(normalized)
    files["normalized.csv"] = P.sha256(normalized)
    declared = {"yahoo_chart": identity.get("symbol") == entry["symbol"] and identity.get("currency") in (entry.get("currency"), None),
                "fred": identity.get("id") == entry["symbol"], "fdr": True}[entry["fetch"]]
    record.update(status="ACQUIRED" if rows else "EMPTY", identity=identity, identityOk=bool(declared), files=files, **P.metadata_audit(rows, dropped, total))
    return record


MAX_ATTEMPTS = 3


def main(argv=None):
    """First run acquires every registered source. A later run RETRIES only sources that are not ACQUIRED (a transport or identity repair), at most
    MAX_ATTEMPTS times each; an ACQUIRED source is immutable and is never fetched again."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--only", nargs="*")
    args = parser.parse_args(argv)
    out = Path(args.output)
    key = os.environ.get("FRED_API_KEY", "")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "audit.json"
    audit = json.loads(path.read_text()) if path.exists() else {
        "studyId": "kr-market-risk-anatomy-v1", "kind": "SOURCE_SNAPSHOT_IDENTITY_AUDIT_NO_OUTCOMES", "acquiredOn": today, "sources": {},
        "statements": ["Raw vendor bytes are retained unchanged.", "No return, drawdown, episode or forward quantity was computed.",
                       "Rows that could not be parsed to a finite value were dropped and counted, never filled; duplicate dates were kept and counted.",
                       "An ACQUIRED source is immutable; only a source that is not ACQUIRED may be retried, at most %d times." % MAX_ATTEMPTS]}
    changed = False
    for sid in S.ACQUIRED_IDS:
        if args.only and sid not in args.only:
            continue
        previous = audit["sources"].get(sid)
        if previous and (previous["status"] == "ACQUIRED" or previous.get("attempts", 1) >= MAX_ATTEMPTS):
            continue
        record = acquire_one(sid, S.SOURCES[sid], key, today, out)
        record["attempts"] = (previous.get("attempts", 1) + 1) if previous else 1
        audit["sources"][sid] = record
        changed = True
        print(sid, record["status"], record.get("firstDate"), record.get("lastDate"), record.get("validRows"), record.get("error"))
        time.sleep(1.0)
    if changed or not path.exists():
        path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
