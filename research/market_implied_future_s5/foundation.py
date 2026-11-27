"""S5-A: bounded, offline-first option-index admission and variance diagnostics.

Current-history observations are not historical release-time vintages.
No price returns, outcome evaluation, position generation, or production writes.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from datetime import date, datetime, timezone
from pathlib import Path

# Conservative full-year live-era starts, not exact first publication dates.
# Cboe methodology section 5 lists history start and launch separately.
TERMS = {"VIX9D": 9, "VIX": 30, "VIX3M": 93, "VIX6M": 184, "VIX1Y": 366}
LIVE_FLOOR = {
    "VIX9D": date(2014, 1, 1), "VIX": date(2004, 1, 1),
    "VIX3M": date(2014, 1, 1), "VIX6M": date(2014, 1, 1),
    "VIX1Y": date(2019, 1, 1),
}
CBOE = "https://cdn-api.cboe.com/api/global/us_indices/daily_prices/"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
ANCILLARY_FLOOR = {
    "SKEW": date(2012, 1, 1), "VVIX": date(2013, 1, 1),
    "COR1M": date(2023, 1, 1), "COR3M": date(2022, 1, 1), "DSPX": date(2024, 1, 1),
}
UNITS = {
    **dict.fromkeys(TERMS, "ANNUALIZED_VOL_PERCENT"),
    "SKEW": "TRANSFORMED_SKEW_INDEX_LEVEL", "VVIX": "ANNUALIZED_VIX_VOL_PERCENT",
    "COR1M": "CORRELATION_PERCENT", "COR3M": "CORRELATION_PERCENT",
    "DSPX": "ANNUALIZED_DISPERSION_PERCENT",
}
SOURCES = {
    symbol: {CBOE + f"{symbol}_History.csv": ("DATE", symbol if symbol in {"SKEW", "VVIX", "DSPX"} else "CLOSE")}
    for symbol in UNITS
}
SOURCES["VIX"][FRED + "VIXCLS"] = ("observation_date", "VIXCLS")
SOURCES["VIX3M"][FRED + "VXVCLS"] = ("observation_date", "VXVCLS")
MAX_BYTES = 16 * 1024 * 1024


def _utc(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("AWARE_CLOCK_REQUIRED")
    return result.astimezone(timezone.utc)


def _day(value):
    if "/" in value:
        return datetime.strptime(value, "%m/%d/%Y").date()
    result = date.fromisoformat(value)
    if result.isoformat() != value:
        raise ValueError("INVALID_DATE")
    return result


def _vol(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError("VOL_MUST_BE_NUMERIC")
    if not math.isfinite(value) or value <= 0:
        raise ValueError("VOL_MUST_BE_POSITIVE_FINITE")
    return float(value)


def admit(raw, *, symbol, url, sha256, retrieved_at, as_of):
    """Parse fixed source/date/value schema and preserve explicit missingness."""
    if symbol not in SOURCES or url not in SOURCES[symbol]:
        raise ValueError("UNREGISTERED_SOURCE")
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_BYTES:
        raise ValueError("SOURCE_SIZE_INVALID")
    if hashlib.sha256(raw).hexdigest() != sha256:
        raise ValueError("SOURCE_HASH_MISMATCH")
    observed, clock = _utc(retrieved_at), _utc(as_of)
    if observed > clock:
        raise ValueError("FUTURE_RETRIEVAL")
    date_col, value_col = SOURCES[symbol][url]
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    names = reader.fieldnames or []
    if len(set(names)) != len(names) or not {date_col, value_col} <= set(names):
        raise ValueError("SOURCE_HEADER_INVALID")
    rows, excluded, seen = {}, 0, set()
    for row in reader:
        if None in row or any(x is None for x in row.values()):
            raise ValueError("MALFORMED_ROW")
        day = _day(row[date_col])
        if day in seen or day > observed.date():
            raise ValueError("DUPLICATE_OR_FUTURE_DATE")
        seen.add(day)
        value = row[value_col].strip()
        parsed = None if value in ("", ".") else float(value)
        if parsed is not None:
            if symbol.startswith("COR"):
                if not -100 <= parsed <= 100:
                    raise ValueError("CORRELATION_OUT_OF_RANGE")
            elif not (symbol == "DSPX" and parsed == 0):
                # Preserve the published pre-launch DSPX zero. It is never a term node.
                _vol(parsed)
        floor = LIVE_FLOOR[symbol] if symbol in TERMS else ANCILLARY_FLOOR[symbol]
        if day < floor:
            excluded += 1
            continue
        rows[day.isoformat()] = parsed
    if not rows or not any(v is not None for v in rows.values()):
        raise ValueError("NO_LIVE_ERA_OBSERVATIONS")
    return {
        "symbol": symbol, "url": url, "sha256": sha256,
        "retrievedAtUtc": observed.isoformat(), "unit": UNITS[symbol],
        "evidenceClass": "CURRENT_HISTORY_NOT_VERIFIED_PIT",
        "excludedPreLiveEraRows": excluded, "rows": dict(sorted(rows.items())),
    }


def term_curve(values):
    """Signed adjacent forward variance proxy; no clipping, interpolation or fill.

    VIX-family indices differ in eligible contracts. Negative estimates are
    diagnostics, not proof of an arbitrage and not zero volatility.
    """
    if set(values) - set(TERMS):
        raise ValueError("UNKNOWN_MATURITY")
    vols = {k: _vol(v) for k, v in values.items() if v is not None}
    total = {k: TERMS[k] / 365 * (v / 100) ** 2 for k, v in vols.items()}
    segments = []
    previous, a, wa = None, 0, 0.0
    for symbol, b in TERMS.items():
        wb = total.get(symbol)
        forward = (wb - wa) * 365 / (b - a) if wb is not None and wa is not None else None
        status = "MISSING_ENDPOINT" if forward is None else (
            "NEGATIVE_FORWARD_PROXY" if forward < 0 else "OBSERVED_PROXY"
        )
        segments.append({
            "from": previous, "to": symbol, "startDays": a, "endDays": b,
            "annualizedForwardVariance": forward,
            "annualizedForwardVolPct": 100 * math.sqrt(forward) if forward is not None and forward >= 0 else None,
            "status": status,
        })
        previous, a, wa = symbol, b, wb
    return {
        "annualizedVolPct": vols, "totalVariance": total, "segments": segments,
        "interpretation": "RISK_NEUTRAL_VARIANCE_PROXY_NOT_PHYSICAL_FORECAST",
    }


def census(series):
    """Source availability only, not a count of valid exchange sessions."""
    if set(series) - set(TERMS):
        raise ValueError("UNKNOWN_SERIES")
    valid = {k: {d for d, v in s.items() if v is not None} for k, s in series.items()}
    union = set().union(*valid.values()) if valid else set()
    common = set.intersection(*valid.values()) if set(valid) == set(TERMS) else set()
    negative = dict.fromkeys(TERMS, 0)
    for day in union:
        curve = term_curve({symbol: rows.get(day) for symbol, rows in series.items()})
        for row in curve["segments"]:
            if row["status"] == "NEGATIVE_FORWARD_PROXY":
                negative[row["to"]] += 1
    return {
        "series": {
            k: {"nonmissing": len(valid.get(k, set())),
                "first": min(valid.get(k, set()), default=None),
                "last": max(valid.get(k, set()), default=None),
                "missingOnObservedUnion": len(union - valid.get(k, set()))}
            for k in TERMS
        },
        "observedUnionDays": len(union), "allFiveCommonDays": len(common),
        "firstCommon": min(common, default=None), "lastCommon": max(common, default=None),
        "negativeForwardCounts": negative,
    }


def risk_premium_proxy(implied_vol_pct, expected_realized_variance):
    """Annualized DECIMAL variance units; expected RV must be ex-ante, not ex-post.

    Caller must independently verify forecast timestamp, underlying, horizon,
    sampling clock, and release-time validity. Not an investment signal.
    """
    vol = _vol(implied_vol_pct) / 100
    if isinstance(expected_realized_variance, bool) or not isinstance(expected_realized_variance, (int, float)):
        raise ValueError("EXPECTED_VARIANCE_INVALID")
    if not math.isfinite(expected_realized_variance) or expected_realized_variance < 0:
        raise ValueError("EXPECTED_VARIANCE_INVALID")
    return vol**2 - expected_realized_variance


def state_discount_witness(q, p, discount):
    """Construct different positive SDFs with identical state prices D*q.

    q: risk-neutral probabilities; p: candidate physical probabilities.
    Does not estimate either probability from data.
    """
    if len(p) != len(q) or not p or not math.isfinite(discount) or discount <= 0:
        raise ValueError("INVALID_DISTRIBUTION")
    if any(not math.isfinite(x) or x <= 0 for x in [*p, *q]):
        raise ValueError("INVALID_DISTRIBUTION")
    if not math.isclose(sum(p), 1, abs_tol=1e-12) or not math.isclose(sum(q), 1, abs_tol=1e-12):
        raise ValueError("INVALID_DISTRIBUTION")
    return [discount * qi / pi for qi, pi in zip(q, p)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    clock = datetime.now(timezone.utc).isoformat()
    sources, rows, failures, identifiers = [], {}, {}, set()
    for entry in manifest:
        if entry.get("kind", "index") != "index":
            continue
        symbol = entry["symbol"]
        identifier = (symbol, entry["url"])
        if identifier in identifiers:
            raise ValueError("DUPLICATE_SOURCE")
        identifiers.add(identifier)
        try:
            path = Path(entry["path"])
            if path.stat().st_size > MAX_BYTES:
                raise ValueError("SOURCE_SIZE_INVALID")
            item = admit(path.read_bytes(), symbol=symbol, url=entry["url"], sha256=entry["sha256"],
                         retrieved_at=entry["retrievedAtUtc"], as_of=clock)
            observations = item.pop("rows")
            if symbol in TERMS and (symbol not in rows or entry["url"].startswith(CBOE)):
                rows[symbol] = observations
            sources.append(item)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            failures[" ".join(identifier)] = str(exc)
    result = {
        "schema": "S5_SOURCE_CENSUS_V1", "status": "SOURCE_ONLY",
        "productionEffect": "NONE", "asOfUtc": clock,
        "admittedSources": sources, "failures": failures, "census": census(rows),
        "investmentEvaluationAuthorized": False,
    }
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if set(rows) == set(TERMS) and not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
