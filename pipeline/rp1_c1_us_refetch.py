"""Storage v2: bounded, exact analysis bytes; transient raw acquisition only.

No return/state/portfolio is computed. Original bytes and canonical inputs have
SEPARATE digests. Re-fetch can prove equality, never guarantee availability.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from fractions import Fraction
import hashlib
from itertools import zip_longest
import json
from pathlib import Path

import pandas as pd

from . import kr_market_risk_source_parse as P
from . import rp1_c1_us_exposure as U
from . import rp1_c1_us_sources as S

VERSION = "RP1_C1_HASH_REFETCH_V2"
CODE_FILES = ("requirements.txt", "pipeline/rp1_c1_us_refetch.py", "pipeline/rp1_c1_us_sources.py", "pipeline/kr_market_risk_source_parse.py",
              "scripts/acquire_rp1_c1_us_sources.py", "scripts/acquire_kr_market_risk_sources.py", "pipeline/winner_inflection_execution.py",
              "pipeline/price_adjustment.py", "pipeline/us_dual_benchmark_data.py", "pipeline/replay_calendar.py", "pipeline/prospective_receipt_core.py")
SCOPES = ("PRIMARY", "VENDOR_ECONOMIC", "CASH_ECONOMIC")


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def contract():
    return {"version": VERSION, "startInclusive": U.GRID_START, "endInclusive": U.ANALYSIS_END,
            "admissionVersion": "SCOPED_PRIMARY_VENDOR_AND_CASH_ECONOMIC_V1",
            "cashInput": "exact native close, identity, dates and all actions; adjclose excluded ONLY from the separately versioned cash economic input",
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


def bounded_chart(raw, sid, *, include_adj=True):
    doc = json.loads(raw, parse_float=Decimal)
    result = doc["chart"]["result"][0]
    meta = result["meta"]
    offset = int(meta.get("gmtoffset", 0))
    stamps = result.get("timestamp") or []
    close = result["indicators"]["quote"][0].get("close") or []
    adj = ((result["indicators"].get("adjclose") or [{}])[0]).get("adjclose") or []
    if len(stamps) != len(close) or (sid == "YAHOO_SPY" and include_adj and len(adj) != len(stamps)):
        raise ValueError("INCOMPLETE_VENDOR_ARRAYS:" + sid)
    keep = [(i, local_day(t, offset)) for i, t in enumerate(stamps) if inside(local_day(t, offset))]
    context = {"meta": {k: meta.get(k) for k in ("symbol", "currency", "instrumentType", "exchangeTimezoneName")},
               "timestamp": [noon(day) for _, day in keep], "indicators": {"quote": [{"close": [number(close[i]) for i, _ in keep]}]}}
    context["meta"]["gmtoffset"] = 0
    if sid == "YAHOO_SPY" and include_adj:
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


def build(raw_dir, only=None, *, cash_only=False):
    """Derive bytes in memory; no numeric result is returned to a log/manifest."""
    raw_dir = Path(raw_dir)
    original = json.loads((raw_dir / "audit.json").read_bytes())
    files, audit = {"normalization.json": encoded(contract())}, {"kind": VERSION, "studyId": U.STUDY, "sources": {}}
    for sid in S.ACQUIRED_IDS:
        if only is not None and sid not in only:
            continue
        if original.get("sources", {}).get(sid, {}).get("status") != "ACQUIRED":
            if sid in S.PRIMARY_IDS:
                raise ValueError("SOURCE_NOT_ACQUIRED:" + sid)
            continue
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
            raw = (base / "raw_chart.json").read_bytes()
            if sid == "YAHOO_SPY":
                files[sid + "/cash_input.json"] = bounded_chart(raw, sid, include_adj=False)
                if cash_only:
                    continue  # even an absent/malformed legacy adjclose array is not a cash-definition input
            try:
                primary = bounded_chart(raw, sid)
            except ValueError:
                if sid != "YAHOO_SPY":
                    raise
                primary = files[sid + "/cash_input.json"]  # absent adjclose cannot disable PRIMARY or valid native cash inputs
            files[sid + "/raw_chart.json"] = primary
            rows, dropped, identity = P.parse_yahoo_chart(primary, "close", True)
            if sid == "YAHOO_SPY":
                rows, dropped = S.parse_yahoo_adjclose(primary)
        files[sid + "/normalized.csv"] = P.normalized_csv(rows)
        audit["sources"][sid] = {"status": "ACQUIRED" if rows else "EMPTY", "identity": identity,
            "identityOk": bool(S.identity_ok(sid, identity)), **P.metadata_audit(rows, dropped, len(rows) + dropped)}
        files[sid + "/audit.json"] = encoded(audit["sources"][sid])
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


def scoped_fingerprints(snapshot, scope):
    if scope not in SCOPES:
        raise ValueError("UNKNOWN_INPUT_SCOPE")
    snapshot = Path(snapshot)
    ids = S.PRIMARY_IDS if scope == "PRIMARY" else ("YAHOO_SPY", "FRED_DTB3")
    files = build(snapshot.parent, only=ids, cash_only=scope == "CASH_ECONOMIC")
    selected = {name: data for name, data in files.items() if name != "audit.json" and
                (not name.startswith("YAHOO_SPY/") or
                 (name == "YAHOO_SPY/cash_input.json" if scope == "CASH_ECONOMIC" else name != "YAHOO_SPY/cash_input.json"))}
    if any(not (snapshot / n).is_file() or (snapshot / n).read_bytes() != b for n, b in selected.items()):
        raise ValueError("PREPARED_SCOPED_INPUT_DIFFERS_FROM_SOURCE:" + scope)
    return {n: sha(b) for n, b in selected.items()}


def _changes(left, right):
    """Dates/counts/hashes only. Values remain in memory, never in the report."""
    changed = [(a[0] if a else b[0]) for a, b in zip_longest(left, right) if a != b]
    return {"firstRows": len(left), "secondRows": len(right), "changedCells": len(changed),
            "firstChangedDate": min(changed) if changed else None, "lastChangedDate": max(changed) if changed else None,
            "firstSha256": sha(encoded(left)), "secondSha256": sha(encoded(right))}


def _spy_fields(raw):
    # Inspect vendor values BEFORE canonicalization; Decimal comparisons are exact.
    result = json.loads(raw, parse_float=Decimal)["chart"]["result"][0]
    offset = int(result["meta"].get("gmtoffset", 0))
    stamps = result["timestamp"]
    keep = [(i, local_day(t, offset)) for i, t in enumerate(stamps) if inside(local_day(t, offset))]
    close = result["indicators"]["quote"][0]["close"]
    adj = result["indicators"]["adjclose"][0]["adjclose"]
    fields = {"dates": [(d, d) for _, d in keep], "timestamp": [(d, str(stamps[i])) for i, d in keep],
              "close": [(d, number(close[i])) for i, d in keep], "adjclose": [(d, number(adj[i])) for i, d in keep]}
    canonical = json.loads(bounded_chart(raw, "YAHOO_SPY"))["chart"]["result"][0]
    for kind, events in canonical.get("events", {}).items():
        fields["actions." + kind] = sorted((local_day(r["date"], 0), encoded({k: v for k, v in r.items() if k != "date"}).decode())
                                                 for r in events.values())
    return fields, result["meta"]


def compare_acquisitions(first, second):
    """Input-quality diagnosis, NOT an outcome/strategy evaluation or a bypass.

    Exact cross-products test whether adjacent input ratios changed, without
    computing/publishing any return series, state, exposure or portfolio.
    A vendor adjclose revision remains BLOCKED even if it is a constant scale.
    """
    first, second = Path(first), Path(second)
    hashes = [fingerprints(p) for p in (first, second)]
    differences = sorted(k for k in set(hashes[0]) | set(hashes[1]) if hashes[0].get(k) != hashes[1].get(k))
    raw = [(p.parent / "YAHOO_SPY/raw_chart.json").read_bytes() for p in (first, second)]
    fields, metas = zip(*[_spy_fields(r) for r in raw])
    comparisons = {k: _changes(fields[0].get(k, []), fields[1].get(k, [])) for k in sorted(set(fields[0]) | set(fields[1]))}
    # Fractions avoid Decimal context rounding AND floating point tolerances.
    ratios = {"comparedPairs": 0, "changedPairs": 0, "uncomparablePairs": 0, "firstChangedDate": None, "lastChangedDate": None}
    if fields[0]["dates"] == fields[1]["dates"]:
        a, b = fields[0]["adjclose"], fields[1]["adjclose"]
        changed = []
        for i in range(1, len(a)):
            if a[i][0] < U.EVALUATION_START:
                continue
            values = [a[i][1], b[i - 1][1], b[i][1], a[i - 1][1]]
            if any(v is None or not Decimal(v).is_finite() or Decimal(v) <= 0 for v in values):
                ratios["uncomparablePairs"] += 1
                continue
            ratios["comparedPairs"] += 1
            if Fraction(values[0]) * Fraction(values[1]) != Fraction(values[2]) * Fraction(values[3]):
                changed.append(a[i][0])
        ratios.update(changedPairs=len(changed), firstChangedDate=min(changed) if changed else None, lastChangedDate=max(changed) if changed else None)
    else:
        ratios = {"status": "UNRESOLVED_DIFFERENT_DATES"}
    audits = [json.loads((p.parent / "audit.json").read_bytes())["sources"]["YAHOO_SPY"] for p in (first, second)]
    identities = [{k: m.get(k) for k in ("symbol", "currency", "instrumentType", "exchangeTimezoneName")} for m in metas]
    identity_keys = set(identities[0])
    deterministic = all(build(p.parent) == build(p.parent) for p in (first, second))
    economic = any(v["changedCells"] for k, v in comparisons.items() if k != "timestamp")
    causes = []
    if comparisons["adjclose"]["changedCells"]:
        causes.append("YAHOO_VENDOR_ADJCLOSE_VALUE_DRIFT")
    if any(v["changedCells"] for k, v in comparisons.items() if k not in ("adjclose", "timestamp")) or identities[0] != identities[1]:
        causes.append("OTHER_VENDOR_ECONOMIC_OR_IDENTITY_DRIFT")
    if differences and not economic and identities[0] == identities[1]:
        causes.append("NON_ECONOMIC_OR_OTHER_SOURCE_DIFFERENCE_REQUIRES_REVIEW")
    return {"status": "BLOCKED_HASH_MISMATCH" if differences else "EXACT_BOUNDED_INPUT_MATCH", "causeCodes": causes,
            "analysisFiles": {"first": hashes[0], "second": hashes[1]}, "changedFiles": differences,
            "spy": {"requestBounds": contract()["requestBounds"], "sameRequestHash": audits[0].get("requestSha256") == audits[1].get("requestSha256")
                        if all(a.get("requestSha256") for a in audits) else None,
                    "sameHost": audits[0].get("host") == audits[1].get("host"), "identitySame": identities[0] == identities[1],
                    "observedPeriods": [{"firstDate": f["dates"][0][0], "lastDate": f["dates"][-1][0]} for f in fields],
                    "fields": comparisons, "adjacentAdjustedInputRatioEquality": ratios,
                    "otherMetadataKeysChanged": sorted(k for k in set(metas[0]) | set(metas[1]) if k not in identity_keys and metas[0].get(k) != metas[1].get(k)),
                    "normalizationDeterministic": deterministic,
                    "riskStateReferenceChanged": any(k.startswith("YAHOO_GSPC/") for k in differences),
                    "riskStateReusedMacroInputs": "SEALED_KR_BYTES_NOT_REACQUIRED",
                    "impact": "SPY adjclose is the investable return leg, not the risk-state input; changed adjacent ratios are economically relevant inputs"},
            "sourceArtifacts": 0, "lockClaims": 0, "strategyOutcomes": 0}


def admission_report(first, second, first_execution):
    """Retain the original failed comparison; independently admit the NEW cash definition and PRIMARY."""
    from . import rp1_c1_us_exposure_spec as SP
    first, second = Path(first), Path(second)
    try:
        legacy = compare_acquisitions(first, second)
    except (ValueError, OSError, KeyError, IndexError):
        legacy = {"status": "UNRESOLVED_VENDOR_DIAGNOSTIC_UNAVAILABLE"}
    scopes = {}
    for scope in SCOPES:
        a, b = scoped_fingerprints(first, scope), scoped_fingerprints(second, scope)
        changed = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
        scopes[scope] = {"status": "BLOCKED_HASH_MISMATCH" if changed else "MATCHED", "changedFiles": changed,
                         "first": a, "second": b}
    cash = [SP.cash_economic_gates(p, SP.snapshot_audit(p), first_execution) for p in (first, second)]
    ready = scopes["PRIMARY"]["status"] == "MATCHED" and scopes["CASH_ECONOMIC"]["status"] == "MATCHED" \
        and all(c["status"] == "CASH_ECONOMIC_READY" for c in cash)
    return {"status": "EXACT_SCOPED_INPUT_MATCH" if ready else "SCOPED_INPUT_NOT_READY", "scopes": scopes,
            "legacyVendorComparison": legacy, "cashEconomicReadiness": cash,
            "originalScientificSha256": SP.ORIGINAL_SCIENTIFIC_SHA256, "cashEconomicSpec": SP.cash_economic_spec(),
            "sourceArtifacts": 0, "lockClaims": 0, "strategyOutcomes": 0}
