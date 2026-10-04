"""KR market risk anatomy v2 — corrected SOURCE ADMISSIBILITY rules (historical admissibility, session-based quality, analysis end).

Pure: no network, no price VALUE is read. Every function here is a function of observation DATES, of the XKRX session calendar and of frozen metadata.

v1 stopped at PRIMARY_REFERENCE_NOT_SELECTED because two source-QA rules were mis-specified, neither of which is an investment result:
  1. LIVE OPERATIONAL FRESHNESS (is the series within 10 days of the wall clock?) was applied as a gate on HISTORICAL ADMISSIBILITY. A historical
     anatomy over a fixed window does not need a series that is current today; it needs identity, calendar coverage and continuity over its window.
  2. The invalid-row gate divided by RAW vendor rows, so rows that are not expected XKRX sessions (weekends, holidays, vendor placeholders,
     duplicated calendar rows) were counted in the denominator and, when unparseable, in the numerator. The denominator is the set of EXPECTED XKRX
     SESSIONS in the frozen window; a vendor row on a non-session is reported separately and never counts for or against a source.
v2 separates the concepts. It does not loosen any coverage, continuity or identity threshold: those are v1's, imported rather than re-declared.
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pandas as pd

from . import kr_market_risk_anatomy as M
from . import kr_market_risk_sources as S

STUDY = "kr-market-risk-anatomy-v2"
PREDECESSOR = M.STUDY
SCIENTIFIC_STATUS = M.SCIENTIFIC_STATUS

# ---- frozen v2 rules ----------------------------------------------------------------------------------------------------------------
# Inherited unchanged from v1 (imported, so the two studies cannot silently diverge on a threshold):
CORE_WINDOWS = S.CORE_WINDOWS
REFERENCE_FIRST_DATE_NO_LATER_THAN = S.REFERENCE_FIRST_DATE_NO_LATER_THAN
REFERENCE_SESSION_COVERAGE = S.REFERENCE_SESSION_COVERAGE
REFERENCE_FULL_RANGE_COVERAGE = S.REFERENCE_FULL_RANGE_COVERAGE
REFERENCE_MAX_CONSECUTIVE_MISSING = S.REFERENCE_MAX_CONSECUTIVE_MISSING
# The session-based quality limit reuses v1's numeric 0.005; what changes is the DENOMINATOR (expected XKRX sessions, not raw vendor rows).
MAX_BAD_SESSION_SHARE = S.REFERENCE_MAX_DROPPED_SHARE
# New in v2: the window over which the session-based quality share is measured, equal to v1's full-range coverage window start.
QUALITY_WINDOW_START = "2006-01-01"
# Live operational freshness: the v1 number, kept as an INFORMATIONAL live-use record only. It is never a historical gate in v2.
LIVE_FRESHNESS_DAYS = S.REFERENCE_FRESHNESS_DAYS
# KOSPI 200 routes in outcome-blind priority order. v1 listed YAHOO_KS200 before FDR_KS200; the order of two candidates, one of which retained a single
# row, cannot change which one passes, and the v2 order follows the task's stated priority (official, then the retained FDR series).
REFERENCE_PRIORITY = ("KRX_OPENAPI_KOSPI200", "FDR_KS200", "YAHOO_KS200", "YAHOO_KS11")
PRIMARY_FAMILY_ORDER = S.PRIMARY_FAMILY_ORDER

HISTORICAL_RULES = {
    "historicalReferenceAdmissibility": "identity + documented-blocker + duplicate-date + first-date + core-window session coverage + full-range session coverage + "
                                        "longest missing run + session-based bad-share limit; NO wall-clock freshness test",
    "liveOperationalFreshness": "informational record for a future live deployment question; never a gate for historical anatomy; the result is never described as live-ready",
    "qualityDenominator": "expected XKRX sessions in [QUALITY_WINDOW_START, analysisEnd]",
    "badSession": "an expected XKRX session with no valid (finite, positive) row; split into MISSING (no vendor row) and INVALID (vendor rows exist, none valid)",
    "notCountedAgainstSource": ["non-session vendor rows (weekends, holidays, placeholders)", "duplicate raw rows beyond the first for a date"],
    "duplicateDatesInUsedSeries": "fail closed (DUPLICATE_DATES_IN_USED_SERIES): a duplicate in the normalized series cannot be resolved without reading values",
    "analysisEnd": "latest valid date of the selected primary reference that is an expected completed XKRX session; no forward fill, no synthesized session, "
                   "no freshness requirement; sessions after a candidate's own last date are neither missing nor invalid",
    "noSplice": "one vendor route supplies the whole reference series; no KOSPI 200 + KOSPI composite splice, no FDR + Yahoo splice, no interpolation, no forward fill",
    "familySwitch": "KOSPI composite is considered only when no KOSPI 200 route passes; never on outcomes",
}


# ---- date-only access to the raw retained bytes ------------------------------------------------------------------------------------------
def raw_row_dates(source_id, root):
    """Every vendor row's DATE (duplicates kept), from the retained raw bytes. Only the date field is extracted; no value is parsed or used.
    Returns None when the source has no retained raw bytes of a supported kind."""
    entry = S.SOURCES[source_id]
    base = Path(root) / "data/kr-market-risk-anatomy-v1/sources" / source_id
    fetch = entry.get("fetch")
    if fetch == "fdr":
        path = base / "raw_fdr.csv"
        if not path.exists():
            return None
        reader = csv.reader(io.StringIO(path.read_text(encoding="utf-8")))
        header = next(reader)
        col = header.index("Date")
        return [row[col][:10] for row in reader if row]
    if fetch == "yahoo_chart":
        path = base / "raw_chart.json"
        if not path.exists():
            return None
        result = json.loads(path.read_text())["chart"]["result"][0]
        offset = int(result.get("meta", {}).get("gmtoffset", 0))
        stamps = result.get("timestamp") or []
        return [(pd.Timestamp(0, unit="s") + pd.Timedelta(seconds=int(ts) + offset)).strftime("%Y-%m-%d") for ts in stamps]
    return None


# ---- session-based quality ----------------------------------------------------------------------------------------------------------------
def classify_rows(raw_dates, valid_dates, sessions, start, end):
    """Session-based accounting over [start, end] (all dates only).

    expectedSessions: XKRX sessions in the window. validSessions: expected sessions with a valid row. missingSessions: expected sessions with NO vendor row.
    invalidExpectedSessions: expected sessions whose vendor rows exist and none is valid. nonSessionRows: vendor rows in the window on a date that is not an
    expected session (reported, never counted against the source). duplicateRawRows: surplus raw rows for a date (reported separately).
    duplicateValidDates: duplicate dates in the VALID series (fail closed elsewhere)."""
    window = pd.DatetimeIndex(sessions)
    window = window[(window >= pd.Timestamp(start)) & (window <= pd.Timestamp(end))]
    expected = set(window)
    valid_idx = pd.DatetimeIndex(valid_dates)
    valid = set(valid_idx)
    raw = pd.DatetimeIndex(pd.to_datetime(list(raw_dates))) if raw_dates is not None else None
    in_window = (lambda ix: ix[(ix >= pd.Timestamp(start)) & (ix <= pd.Timestamp(end))])
    out = {"windowStart": str(pd.Timestamp(start).date()), "windowEnd": str(pd.Timestamp(end).date()), "expectedSessions": len(expected),
           "validSessions": sum(d in valid for d in window), "duplicateValidDates": int(valid_idx.duplicated().sum())}
    bad = [d for d in window if d not in valid]
    if raw is None:
        out.update(missingSessions=None, invalidExpectedSessions=None, nonSessionRows=None, duplicateRawRows=None, badSessions=len(bad), rawDatesAvailable=False)
    else:
        raw_set = set(raw)
        raw_win = in_window(raw)
        out.update(missingSessions=sum(d not in raw_set for d in bad), invalidExpectedSessions=sum(d in raw_set for d in bad),
                   nonSessionRows=int(sum(d not in expected for d in raw_win)), duplicateRawRows=int(raw_win.duplicated().sum()), badSessions=len(bad),
                   rawDatesAvailable=True)
    out["badSessionShare"] = (len(bad) / len(expected)) if expected else None
    return out


def analysis_end(valid_dates, sessions, acquired_on):
    """The deterministic analysis end: the latest valid date that is an expected, COMPLETED (strictly before acquisition day) XKRX session in the source.
    Never extended, never forward-filled; depends on the retained source's own dates and the calendar only."""
    days = set(pd.DatetimeIndex(sessions))
    cutoff = pd.Timestamp(acquired_on)
    usable = [d for d in pd.DatetimeIndex(valid_dates) if d in days and d < cutoff]
    return max(usable) if usable else None


def live_operational_freshness(last_date, as_of, limit_days=LIVE_FRESHNESS_DAYS):
    """INFORMATIONAL: whether a source is fresh enough for a live/current production signal. Never used to admit or refuse a historical reference."""
    stale = int((pd.Timestamp(as_of) - pd.Timestamp(last_date)).days)
    return {"staleDays": stale, "limitDays": limit_days, "meetsLiveFreshness": stale <= limit_days,
            "role": "FUTURE_LIVE_DEPLOYMENT_QUESTION_NOT_A_HISTORICAL_GATE", "liveReady": False}


# ---- historical admissibility -------------------------------------------------------------------------------------------------------------
def historical_eligibility(source_id, view, raw_dates, sessions, acquired_on):
    """v2 admissibility of one reference candidate for the HISTORICAL study. Returns (eligible, reasons, metrics). No wall-clock freshness reason exists."""
    entry = S.SOURCES[source_id]
    if entry.get("documentedBlocker"):
        return False, ["DOCUMENTED_BLOCKER: " + entry["documentedBlocker"]], {}
    if view is None or view.get("status") != "ACQUIRED":
        return False, ["NOT_ACQUIRED"], {}
    dates = pd.DatetimeIndex(view["dates"])
    if len(dates) == 0:
        return False, ["NO_VALID_ROWS"], {}
    end = analysis_end(dates, sessions, acquired_on)
    if end is None:
        return False, ["NO_COMPLETED_SESSION_IN_SOURCE"], {}
    reasons = []
    if not view.get("identityOk", False):
        reasons.append("IDENTITY_CHECK_FAILED")
    if dates.duplicated().any():
        reasons.append("DUPLICATE_DATES_IN_USED_SERIES")
    if dates.min() > pd.Timestamp(REFERENCE_FIRST_DATE_NO_LATER_THAN):
        reasons.append("HISTORY_STARTS_AFTER_" + REFERENCE_FIRST_DATE_NO_LATER_THAN)
    window_dates = dates[dates <= end]
    quality = classify_rows(raw_dates, window_dates, sessions, QUALITY_WINDOW_START, end)
    if quality["badSessionShare"] is None or quality["badSessionShare"] > MAX_BAD_SESSION_SHARE:
        reasons.append("TOO_MANY_BAD_EXPECTED_SESSIONS")
    for name, (a, b) in CORE_WINDOWS.items():
        cov = M.session_coverage(window_dates, sessions, a, min(b, str(end.date())))
        if cov is None or cov < REFERENCE_SESSION_COVERAGE or pd.Timestamp(b) > end:
            reasons.append(f"COVERAGE_BELOW_{REFERENCE_SESSION_COVERAGE}_IN_{name}")
    full = M.session_coverage(window_dates, sessions, QUALITY_WINDOW_START, str(end.date()))
    if full is None or full < REFERENCE_FULL_RANGE_COVERAGE:
        reasons.append("FULL_RANGE_COVERAGE_BELOW_THRESHOLD")
    run = S.max_consecutive_missing(window_dates, sessions, QUALITY_WINDOW_START, str(end.date()))
    if run > REFERENCE_MAX_CONSECUTIVE_MISSING:
        reasons.append("MISSING_RUN_TOO_LONG")
    metrics = {"firstDate": str(dates.min().date()), "lastDate": str(dates.max().date()), "analysisEnd": str(end.date()), "quality": quality,
               "fullRangeCoverage": full, "longestMissingRun": run,
               "sessionCoverage": {k: M.session_coverage(window_dates, sessions, a, b) for k, (a, b) in CORE_WINDOWS.items()},
               "liveOperationalFreshness": live_operational_freshness(dates.max(), acquired_on)}
    return not reasons, reasons, metrics


def select_primary_reference(views, raw_by_source, sessions, acquired_on):
    """Outcome-blind rule: walk the KOSPI 200 routes in REFERENCE_PRIORITY and take the first that passes every v2 test; only if no KOSPI 200 route passes
    may the KOSPI composite be chosen, and the record says so. One vendor route is the whole series (no splice)."""
    evaluated, chosen = {}, None
    for family in PRIMARY_FAMILY_ORDER:
        for sid in REFERENCE_PRIORITY:
            if S.SOURCES[sid]["family"] != family:
                continue
            ok, reasons, metrics = historical_eligibility(sid, views.get(sid), raw_by_source.get(sid), sessions, acquired_on)
            evaluated[sid] = {"eligible": ok, "reasons": reasons, "metrics": metrics}
            if ok and chosen is None:
                chosen = sid
        if chosen is not None:
            break
    if chosen is None:
        return {"decision": "NO_ELIGIBLE_PRIMARY_REFERENCE", "primary": None, "evaluated": evaluated}
    end = pd.Timestamp(evaluated[chosen]["metrics"]["analysisEnd"])
    return {"decision": "PRIMARY_REFERENCE_SELECTED", "primary": chosen, "family": S.SOURCES[chosen]["family"], "basis": S.SOURCES[chosen]["basis"],
            "instrument": S.SOURCES[chosen]["instrument"], "composite": S.SOURCES[chosen]["family"] != "KOSPI200", "analysisEnd": str(end.date()),
            "spliced": False, "evaluated": evaluated, "robustnessReference": S.ROBUSTNESS_REFERENCE}
