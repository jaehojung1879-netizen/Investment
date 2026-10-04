"""KR market risk anatomy v1 — source parsing and metadata audit (identity, bytes, dates, units, missingness ONLY).

This module turns raw vendor bytes into (date, value) rows and summarises them. It computes no return, no drawdown, no episode, no forward
quantity and no table of results: after the pre-source freeze that is not permitted, and a static test pins it. A row that cannot be parsed to
a finite value is DROPPED AND COUNTED, never filled; duplicates are kept and counted, never silently removed.
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import math


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def _finite(value):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def parse_fred_observations(raw, positive_required=False):
    """FRED `series/observations` JSON -> ([(date, value)], dropped). '.' and other non-numeric values are dropped and counted."""
    document = json.loads(raw)
    rows, dropped = [], 0
    for obs in document.get("observations", []):
        v = _finite(obs.get("value"))
        if v is None or (positive_required and v <= 0):
            dropped += 1
            continue
        rows.append((obs["date"], v))
    return rows, dropped


def parse_yahoo_chart(raw, field="close", positive_required=True):
    """Yahoo `v8/finance/chart` JSON -> ([(date, value)], dropped, identity). The date is the exchange-local calendar date of the bar
    (timestamp + gmtoffset). Null or non-positive values are dropped and counted."""
    document = json.loads(raw)
    result = document["chart"]["result"][0]
    meta = result.get("meta", {})
    stamps = result.get("timestamp") or []
    values = result["indicators"]["quote"][0].get(field) or []
    offset = int(meta.get("gmtoffset", 0))
    rows, dropped = [], 0
    for ts, value in zip(stamps, values):
        v = _finite(value)
        if v is None or (positive_required and v <= 0):
            dropped += 1
            continue
        rows.append(((datetime.fromtimestamp(0, timezone.utc) + timedelta(seconds=int(ts) + offset)).strftime("%Y-%m-%d"), v))
    identity = {k: meta.get(k) for k in ("symbol", "instrumentType", "currency", "exchangeName", "fullExchangeName", "exchangeTimezoneName", "timezone", "firstTradeDate",
                                         "regularMarketTime", "dataGranularity", "range") if k in meta}
    return rows, dropped, identity


def parse_fdr_csv(raw, field="Close", positive_required=True):
    """FinanceDataReader frame serialised with the `Date` index column -> ([(date, value)], dropped)."""
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8")))
    rows, dropped = [], 0
    for rec in reader:
        v = _finite(rec.get(field))
        if v is None or (positive_required and v <= 0):
            dropped += 1
            continue
        rows.append((rec["Date"][:10], v))
    return rows, dropped


def normalized_csv(rows):
    """Deterministic (date,value) CSV: source order preserved, duplicates kept, no cleaning."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["date", "value"])
    for date, value in rows:
        writer.writerow([date, repr(float(value))])
    return buffer.getvalue().encode()


def read_normalized(data):
    """Inverse of `normalized_csv`: [(date, value)]."""
    return [(r["date"], float(r["value"])) for r in csv.DictReader(io.StringIO(data.decode("utf-8")))]


def metadata_audit(rows, dropped, total_rows_raw):
    """Dates-and-counts only: row counts, first/last date, duplicate dates, per-year row counts. No value is summarised."""
    dates = [d for d, _ in rows]
    years = {}
    for d in dates:
        years[d[:4]] = years.get(d[:4], 0) + 1
    return {"rawRows": int(total_rows_raw), "validRows": len(rows), "droppedRows": int(dropped), "firstDate": min(dates) if dates else None,
            "lastDate": max(dates) if dates else None, "duplicateDates": len(dates) - len(set(dates)), "rowsByYear": dict(sorted(years.items())),
            "datesSorted": dates == sorted(dates)}


def fred_identity(raw):
    """FRED `series` metadata JSON -> the identity fields retained verbatim (no interpretation)."""
    s = json.loads(raw)["seriess"][0]
    return {k: s.get(k) for k in ("id", "title", "units", "units_short", "frequency", "frequency_short", "seasonal_adjustment_short", "observation_start",
                                  "observation_end", "last_updated", "popularity", "notes")}
