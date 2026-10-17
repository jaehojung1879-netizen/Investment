#!/usr/bin/env python3
"""Acquire the rp1-c1 US source set as immutable raw vendor bytes plus a dates-only metadata audit.

Needs network access to query1/2.finance.yahoo.com and api.stlouisfed.org and a FRED_API_KEY. It reuses the transport functions of the sealed KR
acquisition script (`scripts/acquire_kr_market_risk_sources.py`, loaded read-only, never edited) and the sealed KR parsers. It computes no return,
drawdown, state, episode or result table and never prints a price, rate or level. The three FRED series the KR study already retained (VIXCLS, DGS10,
DGS3MO) are NOT re-acquired: the C1 spec pins their sealed bytes. An ACQUIRED source is immutable; a later run retries only a source that is not
ACQUIRED, at most MAX_ATTEMPTS times, and never substitutes a different instrument or splices two vendors.

The output directory must lie OUTSIDE the repository: three of the four sources are licensed data that may not be redistributed, so their bytes never
enter git (`rp1_c1_us_sources.STORAGE`). Inside Actions the freeze job encrypts the directory into one artifact; git carries only its manifest.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import kr_market_risk_source_parse as P  # noqa: E402
from pipeline import rp1_c1_us_sources as SRC  # noqa: E402

MAX_ATTEMPTS = 3


def kr_transport():
    """The sealed KR acquisition script's `get` / `fetch_fred` / `fetch_yahoo`, imported from its file without modifying it."""
    path = ROOT / "scripts" / "acquire_kr_market_risk_sources.py"
    spec = importlib.util.spec_from_file_location("kr_market_risk_acquisition", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def acquire_one(sid, key, today, out, transport):
    entry = SRC.SOURCES[sid]
    record = {"id": sid, "symbol": entry["symbol"], "vendor": entry["vendor"], "instrument": entry["instrument"], "basis": entry["basis"],
              "unit": entry.get("unit"), "vintageClass": entry["vintageClass"], "rights": SRC.SOURCE_RIGHTS[sid]["class"],
              "fetchedAtUtc": datetime.now(timezone.utc).isoformat(), "status": "FAILED"}
    try:
        got = transport.fetch_fred(entry, key, today) if entry["fetch"] == "fred" else transport.fetch_yahoo(entry, today)
    except Exception as error:  # a transport failure is recorded, never hidden or retried into another instrument
        record["error"] = type(error).__name__ + ": " + str(error)[:200]
        return record
    record.update(httpStatus=got["status"], host=got["host"], error=got["error"])
    main_name = "observations.json" if entry["fetch"] == "fred" else "chart.json"
    raw_main = got["raw"].get(main_name)
    if not raw_main:
        return record
    identity, extra = {}, {}
    if entry["fetch"] == "fred":
        rows, dropped = P.parse_fred_observations(raw_main, entry.get("positive", False))
        total = len(json.loads(raw_main).get("observations", []))
        if got["raw"].get("series.json"):
            identity = P.fred_identity(got["raw"]["series.json"])
    elif entry["field"] == "adjclose":
        _, _, identity = P.parse_yahoo_chart(raw_main, "close", True)
        rows, dropped = SRC.parse_yahoo_adjclose(raw_main)
        total = len(rows) + dropped
        extra["dividendEventDates"] = len(SRC.yahoo_dividend_dates(raw_main))
    else:
        rows, dropped, identity = P.parse_yahoo_chart(raw_main, entry["field"], True)
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
    record.update(status="ACQUIRED" if rows else "EMPTY", identity=identity, identityOk=bool(SRC.identity_ok(sid, identity)), files=files,
                  **P.metadata_audit(rows, dropped, total), **extra)
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="a directory OUTSIDE the repository")
    parser.add_argument("--only", nargs="*")
    args = parser.parse_args(argv)
    import os
    key = os.environ.get("FRED_API_KEY", "")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = Path(args.output).resolve()
    if out == ROOT or ROOT in out.parents:
        raise SystemExit("REFUSED: the snapshot must be written outside the repository (licensed bytes never enter git)")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "audit.json"
    audit = json.loads(path.read_text()) if path.exists() else {
        "studyId": "rp1-c1-us-exposure-ladder-replication-v1", "kind": "SOURCE_SNAPSHOT_IDENTITY_AUDIT_NO_OUTCOMES", "acquiredOn": today, "sources": {},
        "reusedFromKrSealedSnapshot": {k: v for k, v in SRC.REUSED.items()},
        "statements": ["Raw vendor bytes are retained unchanged.", "No return, drawdown, state, episode or forward quantity was computed.",
                       "Rows that could not be parsed to a finite (or, for prices, positive) value were dropped and counted, never filled.",
                       "VIXCLS, DGS10 and DGS3MO are the sealed KR snapshot's bytes and were not re-acquired.",
                       "Licensed bytes in this directory are never committed, logged or uploaded unencrypted.",
                       "An ACQUIRED source is immutable; only a source that is not ACQUIRED may be retried, at most %d times." % MAX_ATTEMPTS]}
    transport = kr_transport()
    changed = False
    for sid in SRC.ACQUIRED_IDS:
        if args.only and sid not in args.only:
            continue
        previous = audit["sources"].get(sid)
        if previous and (previous["status"] == "ACQUIRED" or previous.get("attempts", 1) >= MAX_ATTEMPTS):
            continue
        record = acquire_one(sid, key, today, out, transport)
        record["attempts"] = (previous.get("attempts", 1) + 1) if previous else 1
        audit["sources"][sid] = record
        changed = True
        print(sid, record["status"], record.get("httpStatus"), record.get("firstDate"), record.get("lastDate"), "rows", record.get("validRows"))
    if changed:
        path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    failed = [sid for sid, r in audit["sources"].items() if r["status"] != "ACQUIRED"]
    print("acquired", len(audit["sources"]) - len(failed), "failed", failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
