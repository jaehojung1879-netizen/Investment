"""rp1-c1-us-exposure-ladder-replication-v1 — source registry, parsing and the outcome-free data-quality gates.

No return, drawdown, episode, state or forward quantity is computed here. Original gates read observation DATES (and, for the one pre-registered vendor
cross-check, index LEVELS on identical dates to test that two routes quote the same instrument). The separate cash definition validates native price/action sanity and units, never a return.

Three of the C1 inputs are reused, not re-acquired: the exact FRED_VIXCLS, FRED_DGS10 and FRED_DGS3MO bytes that `kr-market-risk-anatomy-v1`
retained and the sealed `kr-market-risk-model-v1` pinned. Every threshold is the sealed KR source contract's (`kr_market_risk_sources`), applied
on the XNYS calendar instead of XKRX.

STORAGE. None of the four newly acquired sources is committed to this public repository. Three are licensed data whose terms do not permit
redistribution (S&P 500 index values via Yahoo and FRED; SPY via Yahoo); keeping DTB3 (public domain) in the same snapshot keeps one storage rule.
The raw bytes live only in runner temporary storage and are discarded; git carries bounded analysis hashes and audit-only raw hashes. No raw artifact is uploaded.
"""
from __future__ import annotations

import json
import math

import pandas as pd

from . import kr_market_risk_anatomy as M
from . import kr_market_risk_source_parse as P
from . import kr_market_risk_sources as S
from . import replay_calendar as RC

KR_SNAPSHOT_DIR = "data/kr-market-risk-anatomy-v1/sources"
KR_SPEC_PATH = "research_specs/kr-market-risk-model-v1.json"

REUSED = {"vix": "FRED_VIXCLS", "us10y": "FRED_DGS10", "us3m": "FRED_DGS3MO"}   # bytes pinned by the sealed KR spec

# Where the newly acquired bytes may live. A summary of each provider's published terms as this study reads them, NOT legal advice; anything unclear
# is treated as restricted. A restricted byte never enters git, a log or any source artifact; derived aggregate statistics may be published.
STORAGE = "HASH_PINNED_REFETCH_RUNNER_TEMP_ONLY"
SOURCE_RIGHTS = {
    "YAHOO_GSPC": {"class": "RESTRICTED_NO_REDISTRIBUTION", "owner": "S&P Dow Jones Indices (index); Yahoo (delivery)",
                   "basis": "Yahoo's terms limit use to personal, non-commercial purposes and prohibit redistribution; the index values are S&P's"},
    "FRED_SP500": {"class": "RESTRICTED_NO_REDISTRIBUTION", "owner": "S&P Dow Jones Indices LLC",
                   "basis": "FRED marks the series as copyrighted by S&P Dow Jones Indices and prohibits reproduction without S&P's permission; FRED serves only "
                            "about the last ten years"},
    "YAHOO_SPY": {"class": "RESTRICTED_NO_REDISTRIBUTION", "owner": "Yahoo (delivery)", "basis": "Yahoo's terms (as YAHOO_GSPC)"},
    "FRED_DTB3": {"class": "PUBLIC_DOMAIN_CITATION_REQUESTED", "owner": "Board of Governors of the Federal Reserve System (H.15)",
                  "basis": "FRED marks H.15 rates public domain with citation requested; also kept only in runner temporary storage so one storage rule applies"},
}
REUSED_RIGHTS = {
    "FRED_VIXCLS": "Cboe-copyrighted series ALREADY committed by the sealed kr-market-risk-anatomy-v1 snapshot before this storage rule; reused in place, "
                   "never copied again, never edited (it is a sealed byte)",
    "FRED_DGS10": "public domain (H.15), committed by the sealed KR snapshot", "FRED_DGS3MO": "public domain (H.15), committed by the sealed KR snapshot"}

# Metadata the vendor must state for a source to count as the registered instrument (identity only; no value is read). Case-insensitive.
EXPECTED_IDENTITY = {"YAHOO_GSPC": {"instrumentType": "INDEX"}, "YAHOO_SPY": {"instrumentType": "ETF"},
                     "FRED_SP500": {"unitsContains": "index", "frequencyStartsWith": "daily"},
                     "FRED_DTB3": {"unitsContains": "percent", "frequencyStartsWith": "daily"}}

# Full-day XNYS closures inside the window that a vendor could wrongly quote. They must not be XNYS sessions in the calendar package (tested), and a
# reference row on one is reported in `offCalendarDates` (it is never used as a session).
KNOWN_XNYS_CLOSURES = ("1994-04-27", "2001-09-11", "2001-09-12", "2001-09-13", "2001-09-14", "2004-06-11", "2007-01-02", "2012-10-29", "2012-10-30",
                       "2018-12-05", "2025-01-09")

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
PRIMARY_IDS = ("YAHOO_GSPC", "FRED_SP500")
CASH_BASIS = "RECONSTRUCTED_AS_TRADED_CASH_REINVEST_EX_CLOSE_V1"

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
    entry, expected = SOURCES[source_id], EXPECTED_IDENTITY[source_id]
    if entry["vendor"] == "YAHOO_CHART":
        return identity.get("symbol") == entry["symbol"] and identity.get("currency") == entry.get("currency") \
            and identity.get("exchangeTimezoneName") == "America/New_York" \
            and str(identity.get("instrumentType") or "").upper() == expected["instrumentType"]
    return identity.get("id") == entry["symbol"] and expected["unitsContains"] in str(identity.get("units") or "").lower() \
        and str(identity.get("frequency") or "").lower().startswith(expected["frequencyStartsWith"])


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


def yahoo_split_dates(raw):
    """Split event dates in the chart's events block (dates only)."""
    result = json.loads(raw)["chart"]["result"][0]
    offset = int(result.get("meta", {}).get("gmtoffset", 0))
    events = (result.get("events") or {}).get("splits") or {}
    return sorted(pd.Timestamp(int(e["date"]) + offset, unit="s").strftime("%Y-%m-%d") for e in events.values())


def corporate_action_gate(raw_chart, asset_dates, first_execution, analysis_end):
    """Dates-only check of the economic asset's corporate-action calendar: every dividend event inside the window falls on an XNYS session the asset
    quotes, and no split is reported (a split inside a back-adjusted series would need its own audit). Reports events per year. The cash amounts,
    the closes and the adjusted closes are NOT read here; the basis reconciliation (adjusted return against close plus dividend) is the frozen
    post-lock diagnostic."""
    dividends = [d for d in yahoo_dividend_dates(raw_chart) if first_execution <= d <= analysis_end]
    splits = yahoo_split_dates(raw_chart)
    sessions = set(xnys_sessions(first_execution, analysis_end))
    quoted = set(pd.DatetimeIndex(asset_dates))
    off = [d for d in dividends if pd.Timestamp(d) not in sessions or pd.Timestamp(d) not in quoted]
    per_year = {}
    for d in dividends:
        per_year[d[:4]] = per_year.get(d[:4], 0) + 1
    reasons = (["DIVIDEND_EVENT_NOT_ON_A_QUOTED_XNYS_SESSION"] if off else []) + (["SPLIT_EVENT_REPORTED"] if splits else []) \
        + (["NO_DIVIDEND_EVENT_IN_THE_WINDOW"] if not dividends else [])
    return not reasons, reasons, {"dividendEvents": len(dividends), "dividendEventsByYear": dict(sorted(per_year.items())), "offSessionEvents": off[:20],
                                  "splitEvents": splits}


def calendar_closure_check(reference_dates):
    """The registered full-day XNYS closures: none may be a calendar session; any reference row on one is listed (it would be off-calendar)."""
    closures = pd.DatetimeIndex(KNOWN_XNYS_CLOSURES)
    sessions = set(xnys_sessions(str(closures.min().date()), str(closures.max().date())))
    quoted = set(pd.DatetimeIndex(reference_dates))
    return {"closuresThatAreSessions": [str(d.date()) for d in closures if d in sessions],
            "referenceRowsOnClosures": [str(d.date()) for d in closures if d in quoted]}


def cash_components(raw_chart, *, basis="SPLIT_ADJUSTED_DIVIDEND_UNADJUSTED"):
    """Validate native SPY inputs, not returns. No snapping, filling or split inference.

    Yahoo's amount is declared USD per share under this vendor convention;
    this is not independent issuer certification of that convention.
    """
    from .us_dual_benchmark_data import BASIS_RAW, DoubleCountRefused
    if basis != BASIS_RAW:
        raise DoubleCountRefused("CASH_REINVESTMENT_REQUIRES_DIVIDEND_UNADJUSTED_NATIVE_CLOSE")
    result = json.loads(raw_chart)["chart"]["result"][0]
    rows, dropped, identity = P.parse_yahoo_chart(raw_chart, "close", True)
    if not identity_ok("YAHOO_SPY", identity):
        raise ValueError("SPY_IDENTITY_OR_USD_SHARE_UNIT_UNRESOLVED")
    if dropped or len(rows) != len(result.get("timestamp") or []) or not rows:
        raise ValueError("NONPOSITIVE_OR_MISSING_NATIVE_CLOSE")
    close = pd.Series([v for _, v in rows], index=pd.to_datetime([d for d, _ in rows]), dtype=float)
    if not close.index.is_unique or not close.index.is_monotonic_increasing:
        raise ValueError("DUPLICATE_OR_UNORDERED_NATIVE_SESSIONS")
    if not close.index.equals(xnys_sessions(str(close.index[0].date()), str(close.index[-1].date()))):
        raise ValueError("MISSING_OR_OFF_CALENDAR_NATIVE_SESSION")
    events = result.get("events") or {}
    if events.get("splits"):
        raise ValueError("SPLIT_PRESENT_SHARE_UNIT_REQUIRES_SEPARATE_RECONCILIATION")
    if any(k != "dividends" and v for k, v in events.items()):
        raise ValueError("UNSUPPORTED_CORPORATE_ACTION")
    offset = int(result["meta"].get("gmtoffset", 0))
    dividends, seen = [], set()
    for entry in (events.get("dividends") or {}).values():
        day = pd.Timestamp(int(entry["date"]) + offset, unit="s").normalize()
        if day in seen:
            raise ValueError("DUPLICATE_DIVIDEND_EVENT")
        seen.add(day)
        if day not in close.index or close.index.get_loc(day) == 0:
            raise ValueError("DIVIDEND_WITHOUT_NATIVE_PREVIOUS_SESSION")
        amount = float(entry["amount"])
        if entry.get("currency", "USD") != "USD" or not math.isfinite(amount) or not 0 < amount < close.iloc[close.index.get_loc(day) - 1]:
            raise ValueError("DIVIDEND_AMOUNT_OR_USD_PER_SHARE_UNIT_INVALID")
        dividends.append((str(day.date()), amount, 1.0))
    if not dividends:
        raise ValueError("SPY_DIVIDEND_CHAIN_ABSENT")
    return close, dividends


def cash_input_gate(raw_chart, first_execution, analysis_end):
    try:
        close, events = cash_components(raw_chart)
        missing = coverage_gate(close.index, first_execution, analysis_end)["missingCount"]
        if missing:
            raise ValueError("CASH_ASSET_SESSION_MISSING")
        return {"status": "CASH_INPUT_READY", "reasons": [], "sessions": len(close), "firstDate": str(close.index[0].date()),
                "lastDate": str(close.index[-1].date()), "dividendEvents": len(events), "splitEvents": 0,
                "unit": "VENDOR_DECLARED_USD_PER_SHARE_NO_SPLITS", "independentlyIssuerVerified": False}
    except (ValueError, KeyError, TypeError, IndexError) as error:
        reason = str(error) if isinstance(error, ValueError) and str(error).isupper() else "CASH_INPUT_SCHEMA_INVALID"
        return {"status": "CASH_INPUT_UNRESOLVED", "reasons": [reason]}
