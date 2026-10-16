"""rp1-c1-us-exposure-ladder-replication-v1 — source registry, parsing and the outcome-free data-quality gates.

No return, drawdown, episode, state or forward quantity is computed here. The gates read observation DATES (and, for the one pre-registered vendor
cross-check, index LEVELS on identical dates to test that two routes quote the same instrument), never a return.

Three of the C1 inputs are reused, not re-acquired: the exact FRED_VIXCLS, FRED_DGS10 and FRED_DGS3MO bytes that `kr-market-risk-anatomy-v1`
retained and the sealed `kr-market-risk-model-v1` pinned. Every threshold is the sealed KR source contract's (`kr_market_risk_sources`), applied
on the XNYS calendar instead of XKRX.
"""
from __future__ import annotations

import json

import pandas as pd

from . import kr_market_risk_anatomy as M
from . import kr_market_risk_source_parse as P
from . import kr_market_risk_sources as S
from . import replay_calendar as RC

SNAPSHOT_DIR = "data/rp1-c1-us-exposure/sources"
KR_SNAPSHOT_DIR = "data/kr-market-risk-anatomy-v1/sources"
KR_SPEC_PATH = "research_specs/kr-market-risk-model-v1.json"

REUSED = {"vix": "FRED_VIXCLS", "us10y": "FRED_DGS10", "us3m": "FRED_DGS3MO"}   # bytes pinned by the sealed KR spec

SOURCES = {
    "YAHOO_GSPC": {"role": "US_REFERENCE", "vendor": "YAHOO_CHART", "symbol": "^GSPC", "instrument": "S&P 500 price index (vendor quote)",
                   "basis": "PRICE_INDEX_LEVEL", "unit": "index points", "currency": "USD", "fetch": "yahoo_chart", "field": "close",
                   "vintageClass": "MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY",
                   "use": "the PRIMARY reading's asset and the FAST layer input, exactly as FDR_KS200 was for KR"},
    "FRED_SP500": {"role": "US_REFERENCE_CROSSCHECK", "vendor": "FRED", "symbol": "SP500", "instrument": "S&P 500 price index (FRED, licensed short history)",
                   "basis": "PRICE_INDEX_LEVEL", "unit": "index points", "fetch": "fred", "positive": True,
                   "vintageClass": "MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY",
                   "use": "instrument-identity cross-check of YAHOO_GSPC on identical dates only; never an input to a state or a path"},
    "YAHOO_SPY": {"role": "US_TOTAL_RETURN_ASSET", "vendor": "YAHOO_CHART", "symbol": "SPY", "instrument": "SPDR S&P 500 ETF Trust",
                  "basis": "VENDOR_ADJUSTED_CLOSE_TOTAL_RETURN_UNVERIFIED", "unit": "USD", "currency": "USD", "fetch": "yahoo_chart", "field": "adjclose",
                  "vintageClass": "MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY",
                  "use": "the ECONOMIC reading's asset; the raw chart (close, adjclose, dividends) is retained for the post-lock basis diagnostic"},
    "FRED_DTB3": {"role": "US_CASH", "vendor": "FRED", "symbol": "DTB3", "instrument": "3-month Treasury bill secondary market rate, discount basis",
                  "basis": "PERCENT_PER_YEAR_DISCOUNT_BASIS", "unit": "percent", "fetch": "fred", "positive": False, "lagClass": "FRED_DAILY_MARKET",
                  "vintageClass": "MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY",
                  "use": "the ECONOMIC reading's cash rate on the de-risked share; never a state input"},
}
ACQUIRED_IDS = tuple(SOURCES)

# ---- gates (inherited values; the US-specific choice is only WHICH window they apply to) ----------------------------------------------------
SESSION_COVERAGE = S.REFERENCE_SESSION_COVERAGE          # 0.99
FULL_RANGE_COVERAGE = S.REFERENCE_FULL_RANGE_COVERAGE    # 0.98
MAX_CONSECUTIVE_MISSING = S.REFERENCE_MAX_CONSECUTIVE_MISSING
MAX_DROPPED_SHARE = S.REFERENCE_MAX_DROPPED_SHARE
CORE_WINDOWS = {"DOTCOM_2000_2002": ("2000-01-01", "2002-12-31"), **S.CORE_WINDOWS}
WARMUP_SESSIONS = 200 + 1                                # FAST needs 201 closes ending at the first decision date
FAST_STATE_WINDOW = 201


def lag_days(source_id):
    if source_id in REUSED.values():
        return S.lag_days(source_id)
    entry = SOURCES[source_id]
    return M.LAG_CALENDAR_DAYS[entry["lagClass"]] if "lagClass" in entry else M.LAG_CALENDAR_DAYS["YAHOO_US_DAILY"]


# =======================================================================================================================================
# Parsing (raw vendor bytes -> rows); no value is summarised
# =======================================================================================================================================
def parse_yahoo_adjclose(raw):
    """Yahoo chart JSON -> ([(exchange-local date, adjclose)], dropped). Null or non-positive values are dropped and counted, never filled."""
    document = json.loads(raw)
    result = document["chart"]["result"][0]
    offset = int(result.get("meta", {}).get("gmtoffset", 0))
    stamps = result.get("timestamp") or []
    adj = ((result.get("indicators", {}).get("adjclose") or [{}])[0]).get("adjclose") or []
    rows, dropped = [], 0
    for ts, value in zip(stamps, adj):
        v = P._finite(value)
        if v is None or v <= 0:
            dropped += 1
            continue
        rows.append((pd.Timestamp(int(ts) + offset, unit="s").strftime("%Y-%m-%d"), v))
    return rows, dropped


def yahoo_dividend_dates(raw):
    """Ex-dividend dates present in the chart's events block (dates only; the amounts stay in the raw bytes until the post-lock diagnostic)."""
    result = json.loads(raw)["chart"]["result"][0]
    offset = int(result.get("meta", {}).get("gmtoffset", 0))
    events = (result.get("events") or {}).get("dividends") or {}
    return sorted(pd.Timestamp(int(e["date"]) + offset, unit="s").strftime("%Y-%m-%d") for e in events.values())


def identity_ok(source_id, identity):
    entry = SOURCES[source_id]
    if entry["vendor"] == "YAHOO_CHART":
        return identity.get("symbol") == entry["symbol"] and identity.get("currency") == entry.get("currency") \
            and identity.get("exchangeTimezoneName") == "America/New_York"
    return identity.get("id") == entry["symbol"]


# =======================================================================================================================================
# Outcome-free gates (dates only)
# =======================================================================================================================================
def xnys_sessions(start, end):
    return RC.sessions(start, end, "US")


def coverage_gate(dates, start, end, sessions=None):
    """Share of XNYS sessions in [start, end] observed, the longest run of missing sessions, and the missing dates themselves."""
    days = xnys_sessions(start, end) if sessions is None else sessions[(sessions >= pd.Timestamp(start)) & (sessions <= pd.Timestamp(end))]
    have = set(pd.DatetimeIndex(dates))
    missing = [d for d in days if d not in have]
    return {"start": start, "end": end, "sessions": int(len(days)), "observed": int(len(days) - len(missing)),
            "coverage": (1.0 - len(missing) / len(days)) if len(days) else None,
            "maxConsecutiveMissing": S.max_consecutive_missing(dates, days, start, end), "missing": [str(d.date()) for d in missing[:50]],
            "missingCount": len(missing)}


def off_calendar(dates, start, end):
    """Observation dates that are not XNYS sessions (reported; never used as a session)."""
    days = set(xnys_sessions(start, end))
    return [str(d.date()) for d in pd.DatetimeIndex(dates) if pd.Timestamp(start) <= d <= pd.Timestamp(end) and d not in days]


def reference_gate(audit, first_decision, analysis_end):
    """The primary reference must quote every XNYS session from FAST warm-up to the analysis end (the replay refuses a missing session), meet the
    inherited coverage and missing-run limits, pass identity, and carry no duplicate dates."""
    reasons, out = [], {}
    if audit is None or audit.get("status") != "ACQUIRED":
        return False, ["NOT_ACQUIRED"], out
    dates = pd.DatetimeIndex(audit["dates"])
    if not audit.get("identityOk"):
        reasons.append("IDENTITY_CHECK_FAILED")
    if dates.duplicated().any():
        reasons.append("DUPLICATE_DATES")
    if audit.get("dropped", 0) / max(int(audit.get("rows", len(dates))), 1) > MAX_DROPPED_SHARE:
        reasons.append("TOO_MANY_INVALID_ROWS")
    sessions = xnys_sessions("1990-01-01", analysis_end)
    first_pos = sessions.get_indexer([pd.Timestamp(first_decision)])[0]
    if first_pos < 0:
        reasons.append("FIRST_DECISION_NOT_AN_XNYS_SESSION")
        return False, reasons, out
    warm_start = sessions[max(first_pos - (WARMUP_SESSIONS - 1), 0)]
    out["evaluationWindow"] = coverage_gate(dates, str(warm_start.date()), analysis_end, sessions)
    if out["evaluationWindow"]["missingCount"]:
        reasons.append("REFERENCE_SESSION_MISSING_IN_THE_EVALUATION_WINDOW")
    for name, (a, b) in CORE_WINDOWS.items():
        cov = M.session_coverage(dates, sessions, a, b)
        out[name] = cov
        if cov is None or cov < SESSION_COVERAGE:
            reasons.append(f"COVERAGE_BELOW_{SESSION_COVERAGE}_IN_{name}")
    out["offCalendarDates"] = off_calendar(dates, str(warm_start.date()), analysis_end)
    if dates.max() < pd.Timestamp(analysis_end):
        reasons.append("HISTORY_ENDS_BEFORE_THE_ANALYSIS_END")
    return not reasons, reasons, out


def asset_gate(audit, first_execution, analysis_end):
    """The economic reading's asset must quote every evaluation session; otherwise the economic reading is UNRESOLVED (the primary reading is not
    affected)."""
    if audit is None or audit.get("status") != "ACQUIRED":
        return False, ["NOT_ACQUIRED"], {}
    dates = pd.DatetimeIndex(audit["dates"])
    reasons = [] if audit.get("identityOk") else ["IDENTITY_CHECK_FAILED"]
    if dates.duplicated().any():
        reasons.append("DUPLICATE_DATES")
    cov = coverage_gate(dates, first_execution, analysis_end)
    if cov["missingCount"]:
        reasons.append("ASSET_SESSION_MISSING_IN_THE_EVALUATION_WINDOW")
    return not reasons, reasons, {"evaluationWindow": cov}


def cash_gate(dates, first_execution, analysis_end, source_id="FRED_DTB3"):
    """Every evaluation session needs a KNOWN, non-stale cash rate under the frozen lag; otherwise the economic reading is UNRESOLVED."""
    sessions = xnys_sessions(first_execution, analysis_end)
    known, _ = M.known_on_sessions(pd.Series(1.0, index=pd.DatetimeIndex(dates)), sessions, lag_days(source_id), M.FRED_DAILY_STALE_DAYS)
    unknown = [str(d.date()) for d, v in known.items() if not pd.notna(v)]
    return (not unknown), (["CASH_RATE_UNKNOWN_ON_AN_EVALUATION_SESSION"] if unknown else []), {"sessions": int(len(sessions)), "unknown": unknown[:50],
                                                                                                "unknownCount": len(unknown)}


def cross_check(values_a, values_b):
    """The inherited instrument-identity test on identical dates (S.vendor_cross_check). Reads two index LEVELS per common date to test equality;
    computes no return."""
    return S.vendor_cross_check(values_a, values_b)
