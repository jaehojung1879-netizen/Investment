"""Reproduce source-only calendar, term-curve and power diagnostics from receipts."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median

import exchange_calendars as xc
from scipy.optimize import brentq
from scipy.stats import nct, t

from .acquire import ROOT
from .foundation import ANCILLARY_FLOOR, CBOE, LIVE_FLOOR, MAX_BYTES, SOURCES, TERMS, UNITS, _day, _utc, admit, term_curve
from .futures import FUTURES_URL, MONTHLY_CONTRACTS, parse_contract


def bytes_from_receipt(root, row, clock, *, limit=MAX_BYTES):
    path = root / Path(row["path"]).name
    size = path.stat().st_size
    if not 0 < size <= limit or size != row["bytes"]:
        raise ValueError("RECEIPT_SIZE_MISMATCH")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != row["sha256"]:
        raise ValueError("RECEIPT_HASH_MISMATCH")
    if _utc(row["retrievedAtUtc"]) > clock:
        raise ValueError("FUTURE_RECEIPT")
    return raw


def coverage(observations, sessions, lo, hi):
    reference = {d for d in sessions if lo <= d <= hi}
    present = {d for d, value in observations.items() if lo <= d <= hi and value is not None}
    return {
        "nonmissingOnReference": len(reference & present), "referenceSessions": len(reference),
        "nonmissingOffReference": len(present - reference),
        "absentOnReference": len(reference - observations.keys()),
        "explicitMissingOnReference": sum(d in observations and observations[d] is None for d in reference),
        "firstOnReference": min(reference & present, default=None),
        "lastOnReference": max(reference & present, default=None),
    }


def spaced_windows(windows, cutoff):
    """Largest disjoint fixed-length calendar/trading windows, ignoring dependence."""
    last_end, count = date.min, 0
    for start, end in sorted(windows, key=lambda window: window[1]):
        if start >= last_end and end <= cutoff:
            count += 1
            last_end = end
    return count


def optimistic_power(n, standardized_effect):
    if n < 2:
        return None
    critical = t.ppf(.975, n - 1)
    shift = standardized_effect * n**.5
    return float(nct.sf(critical, n - 1, -shift) + nct.sf(critical, n - 1, shift))


def power_row(n):
    mde = None
    if n >= 2:
        upper = (3 * t.ppf(.975, n - 1) + 5) / n**.5
        mde = brentq(lambda d: optimistic_power(n, d) - .8, 0, upper)
    return {"potentialDisjointWindows": n, "mdeSdFor80PctPower": mde,
            "powerAt0_30Sd": optimistic_power(n, .30), "powerAt0_50Sd": optimistic_power(n, .50)}


def build(root, cutoff, clock):
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    attempts = json.loads((root / "attempts.json").read_text(encoding="utf-8"))
    if not manifest or cutoff > clock.date():
        raise ValueError("EMPTY_MANIFEST_OR_FUTURE_CUTOFF")
    calendar = xc.get_calendar("XNYS", start="2003-12-01", end=cutoff + timedelta(days=7))
    sessions = [s.date() for s in calendar.sessions_in_range("2004-01-01", cutoff) if
                calendar.session_close(s).to_pydatetime() <= clock]
    if not sessions or sessions[-1] != cutoff:
        raise ValueError("CUTOFF_MUST_BE_A_COMPLETED_XNYS_SESSION")
    items, series, futures, seen = [], {}, {}, set()
    for row in manifest:
        symbol, url, kind = row["symbol"], row["url"], row["kind"]
        if (symbol, url, kind) in seen:
            raise ValueError("DUPLICATE_RECEIPT")
        seen.add((symbol, url, kind))
        raw = bytes_from_receipt(root, row, clock)
        meta = {key: value for key, value in row.items() if key != "path"}
        if kind == "index":
            data = admit(raw, symbol=symbol, url=url, sha256=row["sha256"],
                         retrieved_at=row["retrievedAtUtc"], as_of=clock.isoformat())
            source = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
            date_field, _ = SOURCES[symbol][url]
            days = [_day(r[date_field]) for r in source]
            observations = {date.fromisoformat(day): v for day, v in data["rows"].items()}
            floor = (LIVE_FLOOR | ANCILLARY_FLOOR)[symbol]
            series[symbol, url] = observations
            items.append({**meta, "unit": UNITS[symbol], "rawHeader": source.fieldnames,
                          "rawRows": len(days), "rawFirst": min(days), "rawLast": max(days),
                          "rawRowsAfterCutoff": sum(d > cutoff for d in days), "floor": floor,
                          "excludedPreFloorRows": data["excludedPreLiveEraRows"],
                          **coverage(observations, sessions, floor, cutoff)})
        elif kind == "futures" and url == FUTURES_URL + f"VX_{symbol}.csv":
            values = parse_contract(raw, symbol, row["retrievedAtUtc"])
            futures[symbol] = values
            end = date.fromisoformat(symbol)
            items.append({**meta, "unit": {"settlement_index_points": "INDEX_POINTS",
                                         "total_volume_contracts": "CONTRACTS", "open_interest_contracts": "CONTRACTS"},
                          "rawRows": len(values), "rawFirst": min(values), "rawLast": max(values),
                          "rawRowsAfterCutoff": sum(d > cutoff for d in values),
                          "expirationRowInSnapshot": end <= cutoff and end in values,
                          "fieldsBeforeExpiry": {
                              field: coverage({d: v[field] for d, v in values.items()}, sessions,
                                              min(values), min(cutoff, end - timedelta(days=1)))
                              for field in next(iter(values.values()))}})
        else:
            raise ValueError("UNREGISTERED_RECEIPT")
    accepted = {(r["symbol"], r["url"], r["kind"]) for r in attempts["attempts"]
                if r["status"] == "ADMITTED_CURRENT_HISTORY"}
    if accepted != seen:
        raise ValueError("ATTEMPTS_RECEIPT_MISMATCH")
    for row in attempts["attempts"]:
        row.pop("nonmissing", None)  # Old acquisition receipts predate calendar-aware source counts.

    primary = {s: series.get((s, CBOE + f"{s}_History.csv"), {}) for s in TERMS}
    curves = {day: term_curve({s: rows.get(day) for s, rows in primary.items()}) for day in sessions
              if any(rows.get(day) is not None for rows in primary.values())}
    complete = [d for d, curve in curves.items() if len(curve["totalVariance"]) == len(TERMS)]
    complete_set = set(complete)
    paired, segments = {}, {}
    for index, symbol in enumerate(TERMS):
        forwards = [curve["segments"][index]["annualizedForwardVariance"] for curve in curves.values()]
        totals = [curves[d]["totalVariance"][symbol] for d in complete]
        segment = [v for v in forwards if v is not None]
        segments[symbol] = {"endpointObserved": len(segment), "negativeSigned": sum(v < 0 for v in segment),
                            "medianAnnualizedForwardDecimalVariance": median(segment) if segment else None,
                            "medianTotalDecimalVarianceOnCompleteDates": median(totals) if totals else None}
        alternates = [v for (s, url), v in series.items() if s == symbol and not url.startswith(CBOE)]
        if alternates:
            errors = [abs(primary[symbol][d] - alt[d]) for alt in alternates for d in sessions
                      if primary[symbol].get(d) is not None and alt.get(d) is not None]
            paired[symbol] = {
                "samePublisherLineage": True, "overlap": len(errors), "exactMatch": sum(e == 0 for e in errors),
                "withinHalfHundredthVolPoint": sum(e <= .005 + 1e-10 for e in errors), "maxAbsVolPoints": max(errors, default=None),
            }
    common_floor = max(LIVE_FLOOR.values())
    q_windows = {str(h): power_row(spaced_windows(
        ((d, d + timedelta(days=h)) for d in complete), cutoff)) for h in TERMS.values()}
    etf_windows = {str(h): power_row(spaced_windows(
        ((d, sessions[i + h]) for i, d in enumerate(sessions[:-h]) if d in complete_set), cutoff)) for h in (126, 252)}
    pair_dates = {d for d in sessions if primary["VIX"].get(d) is not None and primary["VIX3M"].get(d) is not None}
    pair_power = {}
    for start in (date(2014, 10, 6), date(2025, 2, 10)):
        origins = sorted(d for d in pair_dates if d >= start)
        n = spaced_windows(((d, d + timedelta(days=93)) for d in origins), cutoff)
        pair_power[start.isoformat()] = {"pairedReferenceDates": len(origins), **power_row(n)}
    active = [sum(expiry > d.isoformat() and values.get(d, {}).get("settlement_index_points") is not None
                  for expiry, values in futures.items()) for d in sessions]
    result = {
        "status": "AUTHOR_VALIDATION_ONLY", "evidenceClass": "CURRENT_HISTORY_NOT_VERIFIED_PIT",
        "cutoffUsReferenceSession": cutoff, "exchangeCalendar": {"name": "XNYS", "version": xc.__version__,
        "purpose": "U.S. equity reference dates only; not verified as each publisher's calendar or release clock"},
        "attempts": attempts, "receipts": items, "fredReconciliation": paired,
        "completeTermReferenceDates": len(complete), "commonFloorReferenceSessions": sum(d >= common_floor for d in sessions),
        "firstComplete": min(complete, default=None), "lastComplete": max(complete, default=None),
        "segments": segments, "sampleAndPower": {
            "confirmedIndependentOutcomeCount": 0,
            "independenceOfPotentialWindows": "UNVERIFIED; excludes training, regime dependence and multiplicity",
            "calendarDayWholeHorizon": q_windows, "equitySessionHorizon": etf_windows,
            "twoNode93CalendarDaysByMethodStart": pair_power,
            "optimisticNFor80PctPower": {str(effect): next(n for n in range(2, 1000) if optimistic_power(n, effect) >= .8)
                                        for effect in (.30, .50)},
        },
        "futures": {"plannedStandardContracts": len(MONTHLY_CONTRACTS), "admittedContracts": len(futures),
                    "referenceDaysWithAtLeast2PreExpirySettles": sum(n >= 2 for n in active),
                    "referenceDaysWithAtLeast3PreExpirySettles": sum(n >= 3 for n in active),
                    "preExpirySettlesOnCutoff": active[-1]},
    }
    return result, curves


def encode(payload):
    return json.dumps(payload, indent=2, allow_nan=False, default=lambda d: d.isoformat()) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--cutoff", type=date.fromisoformat, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--private-curves", type=Path)
    args = parser.parse_args()
    if args.private_curves and args.private_curves.resolve().is_relative_to(ROOT):
        parser.error("private daily curves must remain outside the repository")
    result, curves = build(args.raw_dir, args.cutoff, datetime.now(timezone.utc))
    args.report.write_text(encode(result), encoding="utf-8")
    if args.private_curves:
        args.private_curves.write_text(encode({d.isoformat(): curve for d, curve in curves.items()}), encoding="utf-8")
    return 0 if result["completeTermReferenceDates"] and result["attempts"]["admitted"] == result["attempts"]["requested"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
