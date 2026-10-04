"""KR market risk anatomy v1 — source registry, source-priority rules and the label-free readiness gates.

Pure: no I/O, no network, no price VALUE is read anywhere in this module. Gates are functions of observation DATES (plus, for the vendor
cross-check, a pre-registered equality test on identical dates) and of frozen metadata. Source choice depends only on identity, coverage
and semantics, never on which source produces a nicer result, and it is fixed before any outcome-containing history is inspected.
"""
from __future__ import annotations

import pandas as pd

from . import kr_market_risk_anatomy as M

# ---- the registered sources ----------------------------------------------------------------------------------------------------------------
# vintageClass: MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY = an unrevised exchange/market quote whose availability date is a
# conservative approximation (no release timestamps retained) -> usable, never PIT_EXACT. REVISED_HISTORY = never a predictor.
SOURCES = {
    # --- primary KR market reference candidates (priority order is REFERENCE_PRIORITY) ---
    "KRX_OPENAPI_KOSPI200": {
        "role": "KR_REFERENCE", "vendor": "KRX_OPENAPI", "instrument": "KOSPI 200 price index (official KRX Open API index series)",
        "family": "KOSPI200", "basis": "PRICE_INDEX_LEVEL", "vintageClass": "MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY",
        "fetch": None, "documentedBlocker": "service history starts 2010-01-04 (docs/kr-industry-membership-foundation-v1-openapi.md), so it cannot cover 2007-2009; "
                                            "the KRX data portal answered LOGOUT/400 from Actions (AGENTS.md workflow hygiene)"},
    "YAHOO_KS200": {
        "role": "KR_REFERENCE", "vendor": "YAHOO_CHART", "symbol": "^KS200", "instrument": "KOSPI 200 price index (vendor quote of the official KRX index)",
        "family": "KOSPI200", "basis": "PRICE_INDEX_LEVEL", "unit": "index points", "currency": "KRW",
        "vintageClass": "MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY", "fetch": "yahoo_chart", "field": "close"},
    "FDR_KS200": {
        "role": "KR_REFERENCE", "vendor": "FINANCEDATAREADER", "symbol": "KS200", "instrument": "KOSPI 200 price index (FinanceDataReader route)",
        "family": "KOSPI200", "basis": "PRICE_INDEX_LEVEL", "unit": "index points", "currency": "KRW",
        "vintageClass": "MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY", "fetch": "fdr", "field": "Close"},
    "YAHOO_KS11": {
        "role": "KR_REFERENCE", "vendor": "YAHOO_CHART", "symbol": "^KS11", "instrument": "KOSPI composite price index (a DIFFERENT instrument from KOSPI 200)",
        "family": "KOSPI_COMPOSITE", "basis": "PRICE_INDEX_LEVEL", "unit": "index points", "currency": "KRW",
        "vintageClass": "MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY", "fetch": "yahoo_chart", "field": "close"},
    # --- robustness reference (never eligible as the primary) ---
    "YAHOO_069500": {
        "role": "KR_ROBUSTNESS", "vendor": "YAHOO_CHART", "symbol": "069500.KS", "instrument": "KODEX 200 ETF as-traded close (dividends NOT reinvested)",
        "family": "KODEX200_ETF", "basis": "ETF_AS_TRADED_CLOSE_NOT_TOTAL_RETURN", "unit": "KRW", "currency": "KRW",
        "vintageClass": "MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY", "fetch": "yahoo_chart", "field": "close"},
    # --- US / global market-observed daily series (FRED, H.15 / H.10 / ICE / CBOE) ---
    "FRED_DGS10": {"role": "US_10Y", "vendor": "FRED", "symbol": "DGS10", "instrument": "10-year Treasury constant maturity yield (H.15)", "unit": "percent",
                   "vintageClass": "MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY", "fetch": "fred", "lagClass": "FRED_DAILY_MARKET"},
    "FRED_DGS3MO": {"role": "US_3M", "vendor": "FRED", "symbol": "DGS3MO", "instrument": "3-month Treasury constant maturity yield (H.15)", "unit": "percent",
                    "vintageClass": "MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY", "fetch": "fred", "lagClass": "FRED_DAILY_MARKET"},
    "FRED_DGS2": {"role": "US_2Y", "vendor": "FRED", "symbol": "DGS2", "instrument": "2-year Treasury constant maturity yield (H.15)", "unit": "percent",
                  "vintageClass": "MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY", "fetch": "fred", "lagClass": "FRED_DAILY_MARKET"},
    "FRED_DFF": {"role": "US_POLICY", "vendor": "FRED", "symbol": "DFF", "instrument": "effective federal funds rate", "unit": "percent",
                 "vintageClass": "MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY", "fetch": "fred", "lagClass": "FRED_DAILY_MARKET"},
    "FRED_VIXCLS": {"role": "VIX", "vendor": "FRED", "symbol": "VIXCLS", "instrument": "CBOE VIX close", "unit": "index points",
                    "vintageClass": "MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY", "fetch": "fred", "lagClass": "FRED_DAILY_MARKET"},
    "YAHOO_VIX": {"role": "VIX", "vendor": "YAHOO_CHART", "symbol": "^VIX", "instrument": "CBOE VIX close (Yahoo route)", "unit": "index points",
                  "vintageClass": "MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY", "fetch": "yahoo_chart", "field": "close", "lagClass": "YAHOO_US_DAILY"},
    "FRED_DEXKOUS": {"role": "USDKRW", "vendor": "FRED", "symbol": "DEXKOUS", "instrument": "KRW per USD, H.10 noon New York buying rate", "unit": "KRW per USD",
                     "vintageClass": "MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY", "fetch": "fred", "lagClass": "FRED_H10_WEEKLY"},
    "YAHOO_KRWX": {"role": "USDKRW", "vendor": "YAHOO_CHART", "symbol": "KRW=X", "instrument": "USD/KRW spot quote (Yahoo route)", "unit": "KRW per USD",
                   "vintageClass": "MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY", "fetch": "yahoo_chart", "field": "close", "lagClass": "YAHOO_US_DAILY"},
    "FRED_BAMLH0A0HYM2": {"role": "HY_OAS", "vendor": "FRED", "symbol": "BAMLH0A0HYM2", "instrument": "ICE BofA US high yield option-adjusted spread", "unit": "percent",
                          "vintageClass": "MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY", "fetch": "fred", "lagClass": "FRED_DAILY_MARKET"},
    "FRED_BAMLC0A0CM": {"role": "IG_OAS", "vendor": "FRED", "symbol": "BAMLC0A0CM", "instrument": "ICE BofA US corporate option-adjusted spread", "unit": "percent",
                        "vintageClass": "MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY", "fetch": "fred", "lagClass": "FRED_DAILY_MARKET"},
    # --- inventoried and EXCLUDED as predictors (never acquired as a predictor) ---
    "FRED_NFCI": {"role": "FINANCIAL_CONDITIONS", "vendor": "FRED", "symbol": "NFCI", "vintageClass": "REVISED_HISTORY", "fetch": None,
                  "excluded": "weekly index re-estimated with every release (revised history); no retained vintage evidence in this repository"},
    "FRED_ANFCI": {"role": "FINANCIAL_CONDITIONS", "vendor": "FRED", "symbol": "ANFCI", "vintageClass": "REVISED_HISTORY", "fetch": None,
                   "excluded": "adjusted index re-estimated with every release (revised history)"},
    "ECOS_LEADING_INDEX": {"role": "KR_MACRO", "vendor": "ECOS", "symbol": "901Y067/I16E", "vintageClass": "REVISED_HISTORY", "fetch": None,
                           "excluded": "ECOS is REVISED_HISTORY by the repository contract; not a primary historical predictor"},
    "ECOS_BASE_RATE": {"role": "KR_POLICY", "vendor": "ECOS", "symbol": "722Y001", "vintageClass": "REVISED_HISTORY", "fetch": None,
                       "excluded": "item and cycle unresolved (AMBIGUOUS_SOURCE) and ECOS is REVISED_HISTORY"},
    "ECOS_KTB_3Y": {"role": "KR_RATES", "vendor": "ECOS", "symbol": "817Y002/010200000", "vintageClass": "REVISED_HISTORY", "fetch": None,
                    "excluded": "ECOS is REVISED_HISTORY; a KR term spread also lacks a comparable validated short leg"},
    "FRED_OECD_KR_10Y": {"role": "KR_RATES", "vendor": "FRED_OECD", "symbol": "IRLTLT01KRM156N", "vintageClass": "REVISED_HISTORY", "fetch": None,
                         "excluded": "monthly OECD series; observation date is not publication date; revised history"},
    "FRED_OECD_KR_3M": {"role": "KR_RATES", "vendor": "FRED_OECD", "symbol": "IR3TIB01KRM156N", "vintageClass": "REVISED_HISTORY", "fetch": None,
                        "excluded": "monthly OECD interbank rate, not a Treasury bill yield; revised history"},
    "EXCESS_BOND_PREMIUM": {"role": "CREDIT_PREMIUM", "vendor": "FRB_FEDS_NOTES", "symbol": "EBP", "vintageClass": "NOT_AVAILABLE", "fetch": None,
                            "excluded": "a modern revised series; no historical vintage semantics are defensible, so it is never called PIT exact and is not acquired"},
    "NEAR_TERM_FORWARD_SPREAD": {"role": "SLOW_CURVE", "vendor": "FRB", "symbol": "NTFS", "vintageClass": "NOT_AVAILABLE", "fetch": None,
                                 "excluded": "exact source and construction (forward rate from the fitted Treasury curve) are not verified in this repository"},
    "KR_TERM_SPREAD": {"role": "SLOW_CURVE", "vendor": "DERIVED", "symbol": "KR 10Y-3M", "vintageClass": "NOT_AVAILABLE", "fetch": None,
                       "excluded": "needs exactly comparable KR long and short rate definitions; the only candidates are ECOS or OECD (revised history)"},
}
REFERENCE_PRIORITY = ("KRX_OPENAPI_KOSPI200", "YAHOO_KS200", "FDR_KS200", "YAHOO_KS11")
PRIMARY_FAMILY_ORDER = ("KOSPI200", "KOSPI_COMPOSITE")
ROBUSTNESS_REFERENCE = "YAHOO_069500"
ROLE_PRIORITY = {"VIX": ("FRED_VIXCLS", "YAHOO_VIX"), "USDKRW": ("FRED_DEXKOUS", "YAHOO_KRWX")}
ACQUIRED_IDS = tuple(k for k, v in SOURCES.items() if v.get("fetch"))
EXCLUDED_IDS = tuple(k for k, v in SOURCES.items() if not v.get("fetch") and k != "KRX_OPENAPI_KOSPI200")

# ---- frozen readiness thresholds -------------------------------------------------------------------------------------------------------
CORE_WINDOWS = {"GFC_2007_2009": ("2007-01-01", "2009-12-31"), "COVID_2019H2_2020": ("2019-07-01", "2020-12-31")}
REFERENCE_FIRST_DATE_NO_LATER_THAN = "2005-12-31"      # >= 252 sessions of warm-up before 2007
REFERENCE_SESSION_COVERAGE = 0.99
REFERENCE_FULL_RANGE_COVERAGE = 0.98
REFERENCE_MAX_CONSECUTIVE_MISSING = 5
REFERENCE_MAX_DROPPED_SHARE = 0.005
REFERENCE_FRESHNESS_DAYS = 10
FAMILY_SLOW_COVERAGE = 0.95
FAMILY_TRANSITION_COVERAGE = 0.95
FAMILY_FAST_COVERAGE = 0.99
TRANSITION_GATE_PREFIXES = ("trans_hy_", "trans_ig_", "trans_vix_", "trans_usdkrw_")   # market-stress features; policy-only easing flags are tabulated, not a gate
VENDOR_CONFLICT_REL_TOLERANCE = 0.005
VENDOR_CONFLICT_MAX_SHARE = 0.01
VENDOR_CONFLICT_MIN_COMMON_DATES = 250


def identity_ok(entry, identity):
    """Identity of a retained source against its registry entry, from the vendor's own identity block. Yahoo: the symbol must equal the registered
    symbol, and the currency is compared ONLY when the registry declares one. FRED: the series id. FDR serves no identity block, so its identity rests
    on the registered symbol alone (stated, not hidden). The audit written at acquisition time evaluated Yahoo currency even when none was declared and
    so flagged YAHOO_VIX and YAHOO_KRWX; that recorded flag is kept as it was and readiness uses this function on the retained identity block."""
    fetch = entry.get("fetch")
    if fetch == "yahoo_chart":
        return identity.get("symbol") == entry["symbol"] and (entry.get("currency") is None or identity.get("currency") == entry["currency"])
    if fetch == "fred":
        return identity.get("id") == entry["symbol"]
    return fetch == "fdr"


def lag_days(source_id):
    entry = SOURCES[source_id]
    return M.LAG_CALENDAR_DAYS["KR_INDEX_CLOSE" if entry["role"].startswith("KR_") else entry["lagClass"]]


def validate_registry():
    for sid, entry in SOURCES.items():
        M.classify_source(entry)
        if entry.get("fetch") and entry["vintageClass"] not in M.PREDICTOR_ELIGIBLE_CLASSES:
            raise ValueError("ACQUIRED_SOURCE_IS_NOT_A_PREDICTOR_CLASS: " + sid)
    if set(REFERENCE_PRIORITY) - set(SOURCES) or ROBUSTNESS_REFERENCE in REFERENCE_PRIORITY:
        raise ValueError("REFERENCE_REGISTRY_INCONSISTENT")
    return True


# =======================================================================================================================================
# Primary reference selection (identity, coverage, semantics only)
# =======================================================================================================================================
def max_consecutive_missing(dates, sessions, start, end):
    window = pd.DatetimeIndex(sessions)
    window = window[(window >= pd.Timestamp(start)) & (window <= pd.Timestamp(end))]
    have, run, worst = set(pd.DatetimeIndex(dates)), 0, 0
    for d in window:
        run = 0 if d in have else run + 1
        worst = max(worst, run)
    return worst


def reference_eligibility(source_id, audit, sessions, acquired_on):
    """Frozen identity/coverage/semantics tests for one reference candidate. `audit` = {'status', 'dates' (valid observation dates),
    'dropped' (non-finite or non-positive rows removed), 'rows', 'identityOk'}. Returns (eligible, reasons); values are never read."""
    reasons = []
    entry = SOURCES[source_id]
    if entry.get("documentedBlocker"):
        return False, ["DOCUMENTED_BLOCKER: " + entry["documentedBlocker"]]
    if audit is None or audit.get("status") != "ACQUIRED":
        return False, ["NOT_ACQUIRED"]
    dates = pd.DatetimeIndex(audit["dates"])
    if len(dates) == 0:
        return False, ["NO_VALID_ROWS"]
    if not audit.get("identityOk", False):
        reasons.append("IDENTITY_CHECK_FAILED")
    if dates.duplicated().any():
        reasons.append("DUPLICATE_DATES")
    if dates.min() > pd.Timestamp(REFERENCE_FIRST_DATE_NO_LATER_THAN):
        reasons.append("HISTORY_STARTS_AFTER_" + REFERENCE_FIRST_DATE_NO_LATER_THAN)
    if dates.max() < pd.Timestamp(acquired_on) - pd.Timedelta(days=REFERENCE_FRESHNESS_DAYS):
        reasons.append("STALE_LAST_DATE")
    rows = max(int(audit.get("rows", len(dates))), 1)
    if audit.get("dropped", 0) / rows > REFERENCE_MAX_DROPPED_SHARE:
        reasons.append("TOO_MANY_INVALID_ROWS")
    for name, (a, b) in CORE_WINDOWS.items():
        cov = M.session_coverage(dates, sessions, a, b)
        if cov is None or cov < REFERENCE_SESSION_COVERAGE:
            reasons.append(f"COVERAGE_BELOW_{REFERENCE_SESSION_COVERAGE}_IN_{name}")
    full = M.session_coverage(dates, sessions, "2006-01-01", str(dates.max().date()))
    if full is None or full < REFERENCE_FULL_RANGE_COVERAGE:
        reasons.append("FULL_RANGE_COVERAGE_BELOW_THRESHOLD")
    if max_consecutive_missing(dates, sessions, "2006-01-01", str(dates.max().date())) > REFERENCE_MAX_CONSECUTIVE_MISSING:
        reasons.append("MISSING_RUN_TOO_LONG")
    return not reasons, reasons


def vendor_cross_check(values_a, values_b):
    """Instrument-identity cross-check of two routes to the SAME index on their common dates: share of common dates whose relative difference
    exceeds the frozen tolerance. Reads values only to test equality of identical dates; computes no return, drawdown or episode."""
    a, b = pd.Series(values_a, dtype=float), pd.Series(values_b, dtype=float)
    common = a.index.intersection(b.index)
    if len(common) < VENDOR_CONFLICT_MIN_COMMON_DATES:
        return {"commonDates": int(len(common)), "status": "INSUFFICIENT_OVERLAP", "conflictShare": None}
    rel = (a.loc[common] / b.loc[common] - 1.0).abs()
    share = float((rel > VENDOR_CONFLICT_REL_TOLERANCE).mean())
    return {"commonDates": int(len(common)), "conflictShare": share, "status": "CONFLICT" if share > VENDOR_CONFLICT_MAX_SHARE else "CONSISTENT"}


def select_primary_reference(audits, sessions, acquired_on, cross_checks=None):
    """The preregistered rule: walk the KOSPI 200 routes in REFERENCE_PRIORITY and take the first that passes every test; only if no KOSPI 200
    route passes may the KOSPI COMPOSITE route be chosen, and the decision says so explicitly. A vendor conflict against another route of
    the same index blocks the choice. No splice, no substitution on result quality. Returns the decision record."""
    cross_checks = cross_checks or {}
    evaluated, chosen = {}, None
    for family in PRIMARY_FAMILY_ORDER:
        for sid in REFERENCE_PRIORITY:
            if SOURCES[sid]["family"] != family:
                continue
            ok, reasons = reference_eligibility(sid, audits.get(sid), sessions, acquired_on)
            conflicts = [k for k, v in cross_checks.items() if sid in k and v.get("status") == "CONFLICT"]
            if ok and conflicts:
                ok, reasons = False, ["VENDOR_CONFLICT:" + ",".join(conflicts)]
            evaluated[sid] = {"eligible": ok, "reasons": reasons}
            if ok and chosen is None:
                chosen = sid
        if chosen is not None:
            break
    if chosen is None:
        return {"decision": "NO_ELIGIBLE_PRIMARY_REFERENCE", "primary": None, "evaluated": evaluated}
    return {"decision": "PRIMARY_REFERENCE_SELECTED", "primary": chosen, "family": SOURCES[chosen]["family"], "basis": SOURCES[chosen]["basis"],
            "instrument": SOURCES[chosen]["instrument"], "composite": SOURCES[chosen]["family"] != "KOSPI200", "evaluated": evaluated,
            "robustnessReference": ROBUSTNESS_REFERENCE}


def select_role_source(role, audits, sessions, grid_dates, window="GFC_2007_2009"):
    """For roles with a registered secondary (VIX, USDKRW): the primary route unless it fails the weekly known-coverage gate in the core window;
    then the secondary. Never both (no splice). Returns (source_id or None, coverage by route)."""
    cov = {}
    for sid in ROLE_PRIORITY[role]:
        audit = audits.get(sid)
        if not audit or audit.get("status") != "ACQUIRED":
            cov[sid] = None
            continue
        cov[sid] = known_coverage(audit["dates"], sid, sessions, grid_dates, window)
    for sid in ROLE_PRIORITY[role]:
        if cov[sid] is not None and cov[sid] >= FAMILY_TRANSITION_COVERAGE:
            return sid, cov
    return None, cov


# =======================================================================================================================================
# Label-free coverage on cadence grids (dates only)
# =======================================================================================================================================
def known_coverage(obs_dates, source_id, sessions, grid_dates, window):
    """Share of grid dates (inside the window) on which the source has a KNOWN, non-stale observation under its frozen lag. Values are dummies."""
    days = pd.DatetimeIndex(sessions)
    obs = pd.Series(1.0, index=pd.DatetimeIndex(obs_dates))
    stale = M.FRED_DAILY_STALE_DAYS
    known, _ = M.known_on_sessions(obs, days, lag_days(source_id), stale)
    a, b = CORE_WINDOWS[window]
    grid = pd.DatetimeIndex(grid_dates)
    grid = grid[(grid >= pd.Timestamp(a)) & (grid <= pd.Timestamp(b))]
    return float(known.reindex(grid).notna().mean()) if len(grid) else None


def spread_dates(dates_a, dates_b):
    """A derived spread exists only on dates where BOTH legs exist."""
    return pd.DatetimeIndex(dates_a).intersection(pd.DatetimeIndex(dates_b))


def family_feature_sources(selected):
    """Which registered features each source supports, given the selected role sources. Pure bookkeeping for the coverage tables."""
    vix, krw = selected.get("VIX"), selected.get("USDKRW")
    return {
        "slow_us_10y3m_flatness": ("FRED_DGS10", "FRED_DGS3MO"), "slow_us_10y2y_flatness": ("FRED_DGS10", "FRED_DGS2"),
        "slow_inversion_duration_10y3m": ("FRED_DGS10", "FRED_DGS3MO"), "slow_resteepening_flag_10y3m": ("FRED_DGS10", "FRED_DGS3MO"),
        "slow_fed_funds_level": ("FRED_DFF",), "slow_fed_funds_change_126": ("FRED_DFF",),
        "trans_hy_oas_level": ("FRED_BAMLH0A0HYM2",), "trans_hy_oas_change_21": ("FRED_BAMLH0A0HYM2",), "trans_hy_oas_change_63": ("FRED_BAMLH0A0HYM2",),
        "trans_ig_oas_level": ("FRED_BAMLC0A0CM",), "trans_ig_oas_change_63": ("FRED_BAMLC0A0CM",),
        "trans_vix_level": (vix,), "trans_vix_change_21": (vix,), "trans_vix_change_63": (vix,),
        "trans_usdkrw_change_63": (krw,), "trans_usdkrw_realized_vol_21": (krw,),
        "trans_easing_flag": ("FRED_DFF",), "trans_benign_easing_flag": ("FRED_DFF", "FRED_DGS10", "FRED_DGS3MO", "FRED_BAMLH0A0HYM2"),
        "trans_easing_after_inversion_flag": ("FRED_DFF", "FRED_DGS10", "FRED_DGS3MO"),
        "trans_post_vulnerability_stress_easing_hy_flag": ("FRED_DFF", "FRED_DGS10", "FRED_DGS3MO", "FRED_BAMLH0A0HYM2"),
        "trans_post_vulnerability_stress_easing_vix_flag": ("FRED_DFF", "FRED_DGS10", "FRED_DGS3MO", vix),
    }


def core_gates(audits, selected_reference, selected_roles, sessions, acquired_on):
    """The preregistered CORE_LONG_HISTORY readiness gates, computed from observation dates only. Each gate is True/False with its measured
    coverage; the decision is READY only when every gate holds. Missing candidate features are NOT gate failures (each gets a coverage table);
    EXTENDED_KR_INTERNALS is not part of this decision."""
    days = pd.DatetimeIndex(sessions)
    gates, tables = {}, {}
    ref_id = selected_reference.get("primary")
    gates["PRIMARY_REFERENCE_SELECTED"] = {"pass": ref_id is not None, "detail": selected_reference.get("decision")}
    if ref_id is None:
        return {"gates": gates, "coverage": tables, "decision": "DATA_BLOCKED_BEFORE_MARKET_RISK_ANATOMY",
                "blockers": ["PRIMARY_REFERENCE_NOT_SELECTED"]}
    ref_dates = pd.DatetimeIndex(audits[ref_id]["dates"])
    month_ends, week_ends = M.period_end_dates(days, "M"), M.period_end_dates(days, "W")
    feature_sources = family_feature_sources(selected_roles)
    for window, (a, b) in CORE_WINDOWS.items():
        ref_cov = M.session_coverage(ref_dates, days, a, b)
        gates[f"REFERENCE_{window}"] = {"pass": ref_cov is not None and ref_cov >= REFERENCE_SESSION_COVERAGE, "coverage": ref_cov}
        fast_start = ref_dates[min(M.ANNUALISATION, len(ref_dates) - 1)] if len(ref_dates) else None
        gates[f"FAST_{window}"] = {"pass": bool(fast_start is not None and fast_start <= pd.Timestamp(a) and ref_cov is not None and ref_cov >= FAMILY_FAST_COVERAGE),
                                   "coverage": ref_cov, "firstSessionWithFullFeatureWarmup": str(fast_start.date()) if fast_start is not None else None}
        for family, grid, threshold in (("SLOW", month_ends, FAMILY_SLOW_COVERAGE), ("TRANSITION", week_ends, FAMILY_TRANSITION_COVERAGE)):
            best = {}
            for feat, ids in feature_sources.items():
                if M.FEATURES[feat][0] != ("SLOW_VULNERABILITY" if family == "SLOW" else "TRANSITION_FINANCIAL_STRESS") or any(i is None for i in ids):
                    continue
                if family == "TRANSITION" and not feat.startswith(TRANSITION_GATE_PREFIXES):
                    continue
                if any(i not in audits or audits[i].get("status") != "ACQUIRED" for i in ids):
                    best[feat] = None
                    continue
                dates = pd.DatetimeIndex(audits[ids[0]]["dates"])
                for other in ids[1:]:
                    dates = spread_dates(dates, audits[other]["dates"])
                best[feat] = known_coverage(dates, ids[0], days, grid, window)
            tables[f"{family}_{window}"] = best
            ok = any(v is not None and v >= threshold for v in best.values())
            gates[f"{family}_{window}"] = {"pass": ok, "bestCoverage": max([v for v in best.values() if v is not None], default=None)}
    blockers = [k for k, v in gates.items() if not v["pass"]]
    return {"gates": gates, "coverage": tables, "blockers": blockers,
            "decision": "READY_FOR_MARKET_RISK_ANATOMY_EXECUTION" if not blockers else "DATA_BLOCKED_BEFORE_MARKET_RISK_ANATOMY"}
