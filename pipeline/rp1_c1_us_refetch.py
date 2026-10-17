"""Storage v2: bounded, exact analysis bytes; transient raw acquisition only.

No return/state/portfolio is computed. Original bytes and canonical inputs have
SEPARATE digests. Re-fetch can prove equality, never guarantee availability.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path

import pandas as pd

from . import kr_market_risk_source_parse as P
from . import rp1_c1_us_exposure as U
from . import rp1_c1_us_sources as S

VERSION = "RP1_C1_HASH_REFETCH_V2"
CODE_FILES = ("requirements.txt", "pipeline/rp1_c1_us_refetch.py", "pipeline/rp1_c1_us_sources.py", "pipeline/kr_market_risk_source_parse.py",
              "scripts/acquire_rp1_c1_us_sources.py", "scripts/acquire_kr_market_risk_sources.py")


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def contract():
    return {"version": VERSION, "startInclusive": U.GRID_START, "endInclusive": U.ANALYSIS_END,
            "requestBounds": {"yahooStartUtc": U.GRID_START,
                              "yahooEndExclusiveUtc": str((pd.Timestamp(U.ANALYSIS_END) + pd.Timedelta(days=1)).date()),
                              "fredObservationEndInclusive": U.ANALYSIS_END},
            "calendar": "retain vendor dates, including off-calendar dates; no fill/sort/dedup/splice",
            "numbers": "exact decimal strings in bounded vendor context; existing parser float64 repr in normalized.csv; no rounding or rebasing",
            "dates": "exchange-local vendor bar date (timestamp + gmtoffset), canonical UTC noon; FRED observation date",
            "yahooFields": ["close", "SPY adjclose", "all corporate-action types and fields within the bounded dates"],
            "fredFields": ["date", "value", "id", "units", "frequency", "seasonal_adjustment_short"],
            "excluded": ["fetch time", "HTTP envelope", "current quote metadata", "outside-window rows/actions", "unused OHLCV"],
            "afterEnd": "append-only data excluded; revisions to ANY bounded input, including adjusted close, refuse even if caused by a later action"}


def code_pins(root):
    return {rel: sha((Path(root) / rel).read_bytes()) for rel in CODE_FILES}


def number(value):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("INVALID_BOOLEAN_SOURCE_NUMBER")
    try:
        d = Decimal(str(value))
    except InvalidOperation:
        return str(value)  # preserve an invalid token; the existing parser counts its exclusion
    # Decimal.normalize uses the active context and can round long numbers.
    # Fixed-point formatting + stripping only redundant fractional zeros does not.
    if not d.is_finite():
        return str(value)
    text = format(d, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def inside(day):
    return U.GRID_START <= day <= U.ANALYSIS_END


def local_day(stamp, offset):
    return (pd.Timestamp(int(stamp) + offset, unit="s")).strftime("%Y-%m-%d")


def noon(day):
    return int((pd.Timestamp(day) + pd.Timedelta(hours=12)).timestamp())


def bounded_chart(raw, sid):
    doc = json.loads(raw, parse_float=Decimal)
    result = doc["chart"]["result"][0]
    meta = result["meta"]
    offset = int(meta.get("gmtoffset", 0))
    stamps = result.get("timestamp") or []
    close = result["indicators"]["quote"][0].get("close") or []
    adj = ((result["indicators"].get("adjclose") or [{}])[0]).get("adjclose") or []
    if len(stamps) != len(close) or (sid == "YAHOO_SPY" and len(adj) != len(stamps)):
        raise ValueError("INCOMPLETE_VENDOR_ARRAYS:" + sid)
    keep = [(i, local_day(t, offset)) for i, t in enumerate(stamps) if inside(local_day(t, offset))]
    context = {"meta": {k: meta.get(k) for k in ("symbol", "currency", "instrumentType", "exchangeTimezoneName")},
               "timestamp": [noon(day) for _, day in keep], "indicators": {"quote": [{"close": [number(close[i]) for i, _ in keep]}]}}
    context["meta"]["gmtoffset"] = 0
    if sid == "YAHOO_SPY":
        context["indicators"]["adjclose"] = [{"adjclose": [number(adj[i]) for i, _ in keep]}]
    events = {}
    for kind, records in (result.get("events") or {}).items():
        selected = {}
        for key, record in records.items():
            day = local_day(record["date"], offset)
            if inside(day):
                selected[key] = {k: noon(day) if k == "date" else number(v) if isinstance(v, (int, Decimal, float)) else v
                                 for k, v in record.items()}
        if selected:
            events[kind] = selected
    if events:
        context["events"] = events
    return encoded({"chart": {"result": [context]}})


def build(raw_dir):
    """Derive bytes in memory; no numeric result is returned to a log/manifest."""
    raw_dir = Path(raw_dir)
    original = json.loads((raw_dir / "audit.json").read_bytes())
    files, audit = {"normalization.json": encoded(contract())}, {"kind": VERSION, "studyId": U.STUDY, "sources": {}}
    for sid in S.ACQUIRED_IDS:
        if original.get("sources", {}).get(sid, {}).get("status") != "ACQUIRED":
            raise ValueError("SOURCE_NOT_ACQUIRED:" + sid)
        base = raw_dir / sid
        if S.SOURCES[sid]["fetch"] == "fred":
            document = json.loads((base / "raw_observations.json").read_bytes())
            observations = [{"date": o["date"], "value": number(o["value"])} for o in document.get("observations", []) if inside(o["date"])]
            primary = encoded({"observations": observations})
            series = json.loads((base / "raw_series.json").read_bytes())["seriess"][0]
            identity = {k: series.get(k) for k in ("id", "units", "frequency", "seasonal_adjustment_short")}
            files[sid + "/raw_series.json"] = encoded({"seriess": [identity]})
            files[sid + "/raw_observations.json"] = primary
            rows, dropped = P.parse_fred_observations(primary, S.SOURCES[sid].get("positive", False))
        else:
            primary = bounded_chart((base / "raw_chart.json").read_bytes(), sid)
            files[sid + "/raw_chart.json"] = primary
            rows, dropped, identity = P.parse_yahoo_chart(primary, "close", True)
            if sid == "YAHOO_SPY":
                rows, dropped = S.parse_yahoo_adjclose(primary)
        files[sid + "/normalized.csv"] = P.normalized_csv(rows)
        audit["sources"][sid] = {"status": "ACQUIRED" if rows else "EMPTY", "identity": identity,
            "identityOk": bool(S.identity_ok(sid, identity)), **P.metadata_audit(rows, dropped, len(rows) + dropped)}
    files["audit.json"] = encoded(audit)
    return files


def prepare(raw_dir):
    """Write bounded inputs OUTSIDE git. Existing different bytes are refused."""
    raw_dir = Path(raw_dir)
    target = raw_dir / "analysis"
    files = build(raw_dir)
    for name, data in files.items():
        path = target / name
        if path.exists() and path.read_bytes() != data:
            raise ValueError("EXISTING_ANALYSIS_INPUT_DIFFERS:" + name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return target


def fingerprints(snapshot):
    """Hash bytes only. Re-derive to reject stale/tampered prepared inputs too."""
    snapshot = Path(snapshot)
    expected = build(snapshot.parent)
    actual = {p.relative_to(snapshot).as_posix(): sha(p.read_bytes()) for p in snapshot.rglob("*") if p.is_file()}
    wanted = {name: sha(data) for name, data in expected.items()}
    if actual != wanted:
        raise ValueError("PREPARED_INPUT_DIFFERS_FROM_BOUNDED_SOURCE")
    return wanted


def provenance(snapshot):
    base = Path(snapshot).parent
    return {p.relative_to(base).as_posix(): sha(p.read_bytes()) for p in sorted(base.glob("*/raw_*.json")) if p.is_file()}
