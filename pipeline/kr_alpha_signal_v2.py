"""kr-alpha-signal-v2 — value with business confirmation, ranked within industry (KR). Signal and decision CONTRACT only.

Design: `docs/kr-alpha-signal-v2-design.md`. Opportunity map: `docs/kr-alpha-signal-v2-opportunity-map.md`.

Hypothesis (H2 of the map): a stock that is cheap against its own industry is more likely to out-earn 069500.KS over the next 126 KR sessions
when the business behind the cheap price is profitable, cash-backed and not deteriorating, than when it is cheap because it is deteriorating
(the value trap). The rule below has NO fitted parameter: within-industry percentiles, a tercile cut and three sign conditions at zero.

This module is pure computation over one signal date's cross-section. It reads no file, no price after the signal date and no outcome, and it
publishes no forecast: a forecast exists only once a separately registered and authorized calibration supplies one (`forecasts=` below). Until
then every decision is `NOT_READY` and carries no holdings. Nothing here changes production or is scheduled.
"""
from __future__ import annotations

import hashlib
import math
from collections import defaultdict

import pandas as pd

from . import prospective_receipt_core as CORE

STUDY = "kr-alpha-signal-v2"
DESIGN_VERSION = "kr-alpha-signal-v2-design-1"
REGION = "KR"
BENCHMARK = "069500.KS"
PRIMARY_HORIZON = 126
SECONDARY_HORIZON = 252                    # descriptive only; the calibrated inference engine covers H21 and H126, not H252
EVALUATION_HORIZONS = (PRIMARY_HORIZON, SECONDARY_HORIZON)

# --- input contract: one row per PIT top-120 KRX member on the signal date ------------------------------------------------------------------- #
# Every key a row may carry. Anything else (in particular any forward or outcome column) refuses the cross-section.
ROW_FIELDS = ("ticker", "industry", "isPreferredShare", "priceAsOf", "positiveVolumeSessions20", "medianTradedValue60Krw",
              "fundamentalsAvailableFrom", "bookToMarketProxy", "earningsYieldProxy", "netIncomeToAssets", "ocfToAssets", "ocfImprovementToAssets",
              "relative126", "downsideVol126", "maxDrawdown252")
VALUE_FIELDS = ("bookToMarketProxy", "earningsYieldProxy")
CONFIRMATION_FIELDS = ("netIncomeToAssets", "ocfToAssets", "ocfImprovementToAssets")
CONTROL_FIELDS = ("relative126",)          # baselines and negative controls only; never part of the signal
RISK_FIELDS = ("downsideVol126", "maxDrawdown252")  # recorded risk flags; never part of the signal

# --- frozen design constants (each one is inherited or structural, none is fitted; see the design document §4) ----------------------------- #
TRADABLE_SESSIONS = 20                     # v2's PIT traded-at-all guard: 20 consecutive sessions of positive close and volume
EXPECTED_TRADE_NOTIONAL_KRW = 10_000_000   # config.json kellyPortfolio.transactionCosts.KR.expectedTradeNotionalKrw
MAX_SHARE_OF_MEDIAN_TRADED_VALUE = 0.01    # one order is at most 1% of a day's median traded value
MIN_MEDIAN_TRADED_VALUE_KRW = EXPECTED_TRADE_NOTIONAL_KRW / MAX_SHARE_OF_MEDIAN_TRADED_VALUE
MIN_INDUSTRY_MEMBERS = 5                   # the industry and within-industry anatomies' eligibility floor
CHEAP_PERCENTILE = 2.0 / 3.0               # top within-industry tercile of the value percentile
EXPENSIVE_PERCENTILE = 1.0 / 3.0           # bottom tercile; used only by the negative control
MIN_MEASURED_SHARE = 0.60                  # config.json kellyPortfolio.probabilityCalibration.integrity.minPitCoverage

STATES = ("INELIGIBLE", "MISSING_VALUE_INPUT", "NOT_CHEAP", "CHEAP_CONFIRMED", "CHEAP_UNCONFIRMED", "CHEAP_CONFIRMATION_UNMEASURED")
INELIGIBILITY = ("PREFERRED_SHARE", "PRICE_NOT_ON_SIGNAL_DATE", "NOT_TRADED_EVERY_SESSION_20", "BELOW_LIQUIDITY_FLOOR",
                 "INDUSTRY_UNCLASSIFIED", "INDUSTRY_BELOW_MIN_MEMBERS")

# --- portfolio policy (layer C, separate from the signal) ----------------------------------------------------------------------------------- #
MAX_HOLDINGS = 5
SLOT_WEIGHT = 1.0 / MAX_HOLDINGS           # an unused slot is NOT redistributed: it goes to the declared fallback
MAX_NAMES_PER_INDUSTRY = 2                 # config.json kellyPortfolio.selection.maxNamesPerSector
SE_MULTIPLE = 1.0                          # switch_hurdle.SE_MULTIPLE (dynamic_breadth inherits the same unit)
FALLBACKS = ("PASSIVE_BENCHMARK", "CASH")  # separate policies, never silently equated; the receipt names which one is in force
PRIMARY_FALLBACK = "PASSIVE_BENCHMARK"
STOCK_COSTS_BPS = {"buy": 5 + 12 / 2, "sell": 5 + 20 + 12 / 2}  # config.json KR: commission 5, spread 12 (half per side), sell tax 20
PASSIVE_LEG_COSTS_BPS = {"buy": 15.0, "sell": 15.0}  # the 069500.KS leg; an assumption, stated as one (tournament v1 design §2)

REFUSALS = ("ROW_FIELD_NOT_IN_INPUT_CONTRACT", "FUNDAMENTALS_AVAILABLE_AFTER_SIGNAL_DATE", "PRICE_AFTER_SIGNAL_DATE", "DUPLICATE_TICKER")


def design_constants():
    """Every constant above, for the receipt's design digest. A change to any of them changes the digest."""
    return {"study": STUDY, "designVersion": DESIGN_VERSION, "region": REGION, "benchmark": BENCHMARK, "evaluationHorizons": list(EVALUATION_HORIZONS),
            "rowFields": list(ROW_FIELDS), "valueFields": list(VALUE_FIELDS), "confirmationFields": list(CONFIRMATION_FIELDS),
            "controlFields": list(CONTROL_FIELDS), "riskFields": list(RISK_FIELDS), "tradableSessions": TRADABLE_SESSIONS,
            "minMedianTradedValueKrw": MIN_MEDIAN_TRADED_VALUE_KRW, "maxShareOfMedianTradedValue": MAX_SHARE_OF_MEDIAN_TRADED_VALUE,
            "minIndustryMembers": MIN_INDUSTRY_MEMBERS, "cheapPercentile": CHEAP_PERCENTILE, "expensivePercentile": EXPENSIVE_PERCENTILE,
            "minMeasuredShare": MIN_MEASURED_SHARE, "maxHoldings": MAX_HOLDINGS, "slotWeight": SLOT_WEIGHT, "maxNamesPerIndustry": MAX_NAMES_PER_INDUSTRY,
            "seMultiple": SE_MULTIPLE, "fallbacks": list(FALLBACKS), "primaryFallback": PRIMARY_FALLBACK, "stockCostsBps": STOCK_COSTS_BPS,
            "passiveLegCostsBps": PASSIVE_LEG_COSTS_BPS, "expectedTradeNotionalKrw": EXPECTED_TRADE_NOTIONAL_KRW}


def design_digest():
    return hashlib.sha256(CORE.canonical(design_constants())).hexdigest()


# --------------------------------------------------------------------------- #
# Signal
# --------------------------------------------------------------------------- #
def _num(value):
    return float(value) if CORE.finite(value) else None


def _validate_rows(rows, signal_date):
    day = pd.Timestamp(signal_date).normalize()
    seen = set()
    for row in rows:
        extra = sorted(set(row) - set(ROW_FIELDS))
        if extra:
            raise ValueError("ROW_FIELD_NOT_IN_INPUT_CONTRACT: " + ",".join(extra))
        CORE.scan_for_outcome_keys(row)
        if row["ticker"] in seen:
            raise ValueError("DUPLICATE_TICKER: " + row["ticker"])
        seen.add(row["ticker"])
        if row.get("priceAsOf") is not None and pd.Timestamp(row["priceAsOf"]).normalize() > day:
            raise ValueError("PRICE_AFTER_SIGNAL_DATE: " + row["ticker"])
        if row.get("fundamentalsAvailableFrom") is not None and pd.Timestamp(row["fundamentalsAvailableFrom"]).normalize() > day:
            raise ValueError("FUNDAMENTALS_AVAILABLE_AFTER_SIGNAL_DATE: " + row["ticker"])


def _ineligibility(row, day):
    reasons = []
    if row.get("isPreferredShare") is not False:
        reasons.append("PREFERRED_SHARE")      # unknown is not common: whole-entity book over one issue's cap is distorted for preferreds
    if row.get("priceAsOf") is None or pd.Timestamp(row["priceAsOf"]).normalize() != day:
        reasons.append("PRICE_NOT_ON_SIGNAL_DATE")
    if not (isinstance(row.get("positiveVolumeSessions20"), int) and row["positiveVolumeSessions20"] >= TRADABLE_SESSIONS):
        reasons.append("NOT_TRADED_EVERY_SESSION_20")
    traded = _num(row.get("medianTradedValue60Krw"))
    if traded is None or traded < MIN_MEDIAN_TRADED_VALUE_KRW:
        reasons.append("BELOW_LIQUIDITY_FLOOR")
    if not row.get("industry"):
        reasons.append("INDUSTRY_UNCLASSIFIED")
    return reasons


def _percentiles(values):
    """Mid-rank percentile in (0, 1) among the finite values of one group; ties share the mean rank; missing stays None."""
    present = sorted((v, t) for t, v in values.items() if v is not None)
    n = len(present)
    out = {t: None for t in values}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and present[j + 1][0] == present[i][0]:
            j += 1
        rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            out[present[k][1]] = (rank - 0.5) / n
        i = j + 1
    return out


def _confirmation(row):
    values = [_num(row.get(f)) for f in CONFIRMATION_FIELDS]
    if any(v is None for v in values):
        return None, {f: v is not None for f, v in zip(CONFIRMATION_FIELDS, values)}
    return all(v > 0 for v in values), {f: v > 0 for f, v in zip(CONFIRMATION_FIELDS, values)}


def cross_section(rows, signal_date):
    """Per-name signal records for one signal date. Pure: same rows, same answer, in any input order.

    Ranks use the signal-date cross-section of ELIGIBLE names in the same industry only, so no other date and no outcome can move a rank. A name
    whose industry holds fewer than MIN_INDUSTRY_MEMBERS eligible names is INELIGIBLE, never ranked against the whole market instead."""
    _validate_rows(rows, signal_date)
    day = pd.Timestamp(signal_date).normalize()
    records = {}
    for row in rows:
        records[row["ticker"]] = {"ticker": row["ticker"], "industry": row.get("industry"), "ineligibility": _ineligibility(row, day),
                                  "industryMembers": None, "valuePercentile": None, "valueComponents": None, "confirmationFlags": None,
                                  "momentumPercentileControl": None, "riskFlags": None, "medianTradedValue60Krw": _num(row.get("medianTradedValue60Krw"))}
    members = defaultdict(list)
    for row in rows:
        if not records[row["ticker"]]["ineligibility"]:
            members[row["industry"]].append(row)
    for industry, group in members.items():
        if len(group) < MIN_INDUSTRY_MEMBERS:
            for row in group:
                records[row["ticker"]]["ineligibility"].append("INDUSTRY_BELOW_MIN_MEMBERS")
    by_ticker = {row["ticker"]: row for row in rows}
    for industry, group in members.items():
        group = [r for r in group if not records[r["ticker"]]["ineligibility"]]
        if not group:
            continue
        pct = {f: _percentiles({r["ticker"]: _num(r.get(f)) for r in group}) for f in VALUE_FIELDS + CONTROL_FIELDS}
        for r in group:
            t = r["ticker"]
            parts = [pct[f][t] for f in VALUE_FIELDS]
            value = math.fsum(parts) / len(parts) if all(p is not None for p in parts) else None
            _, flags = _confirmation(r)
            records[t].update({"industryMembers": len(group), "valuePercentile": value,
                               "valueComponents": {f: pct[f][t] for f in VALUE_FIELDS},
                               "confirmationFlags": flags, "momentumPercentileControl": pct["relative126"][t],
                               "riskFlags": {f: _num(r.get(f)) for f in RISK_FIELDS},
                               "medianTradedValue60Krw": _num(r.get("medianTradedValue60Krw"))})
    for t, rec in records.items():
        if rec["ineligibility"]:
            rec["state"] = "INELIGIBLE"
            continue
        row = by_ticker[t]
        if rec["valuePercentile"] is None:
            rec["state"] = "MISSING_VALUE_INPUT"
        elif rec["valuePercentile"] < CHEAP_PERCENTILE:
            rec["state"] = "NOT_CHEAP"
        else:
            confirmed, _ = _confirmation(row)
            rec["state"] = ("CHEAP_CONFIRMATION_UNMEASURED" if confirmed is None
                            else "CHEAP_CONFIRMED" if confirmed else "CHEAP_UNCONFIRMED")
    return [records[t] for t in sorted(records)]


def coverage(records):
    """Measured shares among eligible names. A share is published with its denominator (AGENTS.md v2.11)."""
    eligible = [r for r in records if r["state"] != "INELIGIBLE"]
    cheap = [r for r in eligible if r["state"].startswith("CHEAP_")]
    counts = {s: sum(1 for r in records if r["state"] == s) for s in STATES}
    value_measured = sum(1 for r in eligible if r["state"] != "MISSING_VALUE_INPUT")
    confirmation_measured = sum(1 for r in cheap if r["state"] != "CHEAP_CONFIRMATION_UNMEASURED")
    return {"universe": len(records), "eligible": len(eligible), "stateCounts": counts,
            "valueMeasured": value_measured, "valueMeasuredShare": value_measured / len(eligible) if eligible else None,
            "cheap": len(cheap), "confirmationMeasured": confirmation_measured,
            "confirmationMeasuredShare": confirmation_measured / len(cheap) if cheap else None}


def readiness(records):
    """READY only when value and confirmation are each measured on at least MIN_MEASURED_SHARE of their denominators. None is not a pass."""
    c = coverage(records)
    reasons = []
    if not c["eligible"]:
        reasons.append("NO_ELIGIBLE_NAME")
    if c["valueMeasuredShare"] is None or c["valueMeasuredShare"] < MIN_MEASURED_SHARE:
        reasons.append("VALUE_COVERAGE_BELOW_FLOOR")
    if c["confirmationMeasuredShare"] is None or c["confirmationMeasuredShare"] < MIN_MEASURED_SHARE:
        reasons.append("CONFIRMATION_COVERAGE_BELOW_FLOOR")
    return {"ready": not reasons, "reasons": reasons, "coverage": c}


# --------------------------------------------------------------------------- #
# Decision (portfolio policy, layer C). Needs an authorized forecast; without one there is nothing to decide.
# --------------------------------------------------------------------------- #
def round_trip_cost(fallback):
    stock = (STOCK_COSTS_BPS["buy"] + STOCK_COSTS_BPS["sell"]) / 10000.0
    passive = (PASSIVE_LEG_COSTS_BPS["buy"] + PASSIVE_LEG_COSTS_BPS["sell"]) / 10000.0 if fallback == "PASSIVE_BENCHMARK" else 0.0
    return stock + passive


def validate_forecasts(forecasts, records, signal_date):
    """A forecast block from an authorized calibration. Every number finite, every SE positive, contributions additive, and nothing trained on a
    label that had not matured by the signal date."""
    day = pd.Timestamp(signal_date).normalize()
    for key in ("modelId", "modelSha256", "trainingCutoff", "trainingTargetLastExitDate", "calibrationStatus", "names"):
        if key not in forecasts:
            raise ValueError("FORECAST_FIELD_MISSING: " + key)
    if not CORE.is_sha256(forecasts["modelSha256"]):
        raise ValueError("FORECAST_MODEL_IDENTITY_REQUIRED")
    if not pd.Timestamp(forecasts["trainingCutoff"]) < day or not pd.Timestamp(forecasts["trainingTargetLastExitDate"]) < day:
        raise ValueError("FORECAST_TRAINED_ON_INFORMATION_NOT_AVAILABLE_AT_THE_SIGNAL_DATE")
    if forecasts["calibrationStatus"] != "CALIBRATED":
        raise ValueError("FORECAST_NOT_CALIBRATED")
    CORE.scan_for_outcome_keys(forecasts)
    known = {r["ticker"]: r for r in records}
    for t, f in forecasts["names"].items():
        if t not in known or known[t]["state"] == "INELIGIBLE":
            raise ValueError("FORECAST_FOR_AN_INELIGIBLE_OR_UNKNOWN_NAME: " + t)
        if not CORE.finite(f.get("expectedExcessReturn")) or not CORE.finite(f.get("standardError")) or f["standardError"] <= 0:
            raise ValueError("FORECAST_NOT_FINITE: " + t)
        parts = f.get("contributions") or {}
        if not parts or not all(CORE.finite(v) for v in parts.values()) or abs(math.fsum(parts.values()) - f["expectedExcessReturn"]) > 1e-9:
            raise ValueError("FORECAST_CONTRIBUTIONS_NOT_ADDITIVE: " + t)
    return True


def decide(records, *, signal_date, forecasts=None, previous_holdings=(), fallback=PRIMARY_FALLBACK):
    """The 0-5 name decision. Returns {"status", "weights", "fallbackWeight", "fallback", "candidates", "reasons"}.

    * no forecast -> NOT_READY, no weights (a signal state is not an expected return);
    * coverage below the floor -> BLOCKED, no weights;
    * otherwise a CHEAP_CONFIRMED name enters only if  mu - round-trip cost - SE_MULTIPLE * se > 0, an incumbent that is still CHEAP_CONFIRMED is
      kept while  mu - SE_MULTIPLE * se > 0 (its entry cost is already paid), at most MAX_NAMES_PER_INDUSTRY per industry and MAX_HOLDINGS in all,
      each at SLOT_WEIGHT; every unused slot goes to the declared fallback. Zero names is a valid answer (NO_ELIGIBLE_OPPORTUNITY)."""
    if fallback not in FALLBACKS:
        raise ValueError("UNKNOWN_FALLBACK")
    ready = readiness(records)
    if not ready["ready"]:
        return {"status": "BLOCKED", "weights": None, "fallbackWeight": None, "fallback": fallback, "candidates": [], "reasons": ready["reasons"]}
    if forecasts is None:
        return {"status": "NOT_READY", "weights": None, "fallbackWeight": None, "fallback": fallback, "candidates": [],
                "reasons": ["NO_AUTHORIZED_CALIBRATED_FORECAST"]}
    validate_forecasts(forecasts, records, signal_date)
    cost = round_trip_cost(fallback)
    incumbents = set(previous_holdings)
    candidates = []
    for r in records:
        f = forecasts["names"].get(r["ticker"])
        if r["state"] != "CHEAP_CONFIRMED" or f is None:
            continue
        capacity_ok = (r.get("medianTradedValue60Krw") or 0) * MAX_SHARE_OF_MEDIAN_TRADED_VALUE >= EXPECTED_TRADE_NOTIONAL_KRW
        incumbent = r["ticker"] in incumbents
        hurdle = 0.0 if incumbent else cost
        margin = f["expectedExcessReturn"] - hurdle - SE_MULTIPLE * f["standardError"]
        candidates.append({"ticker": r["ticker"], "industry": r["industry"], "incumbent": incumbent, "expectedExcessReturn": f["expectedExcessReturn"],
                           "standardError": f["standardError"], "hurdle": hurdle, "margin": margin, "capacityOk": capacity_ok,
                           "clears": margin > 0 and capacity_ok})
    chosen, per_industry = [], defaultdict(int)
    for c in sorted((c for c in candidates if c["clears"]), key=lambda c: (-c["margin"], c["ticker"])):
        if len(chosen) < MAX_HOLDINGS and per_industry[c["industry"]] < MAX_NAMES_PER_INDUSTRY:
            chosen.append(c["ticker"])
            per_industry[c["industry"]] += 1
    weights = {t: SLOT_WEIGHT for t in sorted(chosen)}
    return {"status": "CANDIDATE_PORTFOLIO" if chosen else "NO_ELIGIBLE_OPPORTUNITY", "weights": weights,
            "fallbackWeight": 1.0 - math.fsum(weights.values()), "fallback": fallback,
            "candidates": sorted(candidates, key=lambda c: c["ticker"]), "reasons": [] if chosen else ["NO_NAME_CLEARS_COST_AND_UNCERTAINTY"]}
