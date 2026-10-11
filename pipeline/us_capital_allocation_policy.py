"""us-capital-allocation-alpha-v1 — the registered design and the deterministic 0-5 name candidate rule. Research only.

Nothing in this module reads a price, a return, a label or a model. A candidate is a record of what was knowable on the
signal date: index membership, sector label, whether a price existed, the age of the latest report, and the
shareholder-distribution feature snapshot PR #220 derives. Every number below is either inherited from an existing
repository setting (named beside it) or a round economic threshold stated before any outcome existed. None was
chosen, adjusted or checked against a return, and none may be changed under this study id: a change is a new study.

THE RULE IN ONE PARAGRAPH. A name is a candidate when its cash distributions (common dividends plus common repurchases,
trailing twelve months) grew by at least 10% over the prior year, the newly committed amount is at least 2% of its
operating cash flow, and the whole distribution is covered by positive operating cash flow. Candidates are ranked by
the newly committed amount as a share of operating cash flow, two per sector at most, five in all, 15% each. The rest
of the book is the residual asset, SPY, exactly as in the official weekly policy. When nothing qualifies the book is 100%
SPY and a receipt says so.

WHAT IT CANNOT SAY. The hypothesis includes "without excessive share dilution". The store carries a period-end share
count on 1.8% of filings, so dilution cannot be tested and is recorded as UNVERIFIED on every receipt. It is not a gate and
a result is a statement about distribution growth supported by cash flow, not about dilution-adjusted growth.
"""
from __future__ import annotations

import hashlib
import json

from . import benchmark_alpha as BA
from . import us_shareholder_distribution as U

STUDY_ID = "us-capital-allocation-alpha-v1"
POLICY_VERSION = "US_CAPITAL_ALLOCATION_SELECTION_V1"
REGISTRATION_VERSION = 1
NAMESPACE = "RESEARCH_US_CAPITAL_ALLOCATION_ALPHA_V1"

HORIZON_SESSIONS = 126                       # config historicalReplay.horizonDays; the weekly policy's edge horizon
OFFICIAL_BENCHMARK, ALTERNATIVE_BENCHMARK, RESIDUAL_ASSET = "SPY", "QQQ", "SPY"

# Inherited, not tuned. See `registration()["inheritedFrom"]` for the file each comes from.
MAX_NAMES = 5                                # weekly-passive-first-v1 rule 6
SLOT_WEIGHT = 0.15                           # config longterm.maxNameWeight
MAX_NAMES_PER_SECTOR = 2                     # config longterm.maxSectorWeight 0.30 / maxNameWeight 0.15
MAX_REPORT_AGE_DAYS = 180                    # us_shareholder_distribution STALE_REPORT_PERIOD_OVER_180_DAYS
MIN_PRIOR_SESSIONS, MAX_PRICE_AGE_DAYS = 272, 10   # regional_alpha_features.build_matrix eligibility

# Stated before any outcome existed, as round economic magnitudes. "Material" = a tenth more cash than a year ago AND at
# least a fiftieth of the year's operating cash flow newly committed (so a tiny base cannot qualify on a large percentage).
MIN_DISTRIBUTION_GROWTH = 0.10
MIN_INCREMENTAL_OVER_OCF = 0.02
MAX_DISTRIBUTION_TO_OCF = 1.0                # covered by operating cash flow: no payout funded from outside operations
EXCLUDED_SECTORS = ("Financials", "Real Estate")   # OCF semantics differ; REIT payouts are mandated, not a policy signal
DILUTION_STATUS = "UNVERIFIED_SOURCE_BLOCKED"

# The study's own readiness floor on the weekly cross-section. A cross-section in which fewer names than this have a
# measured distribution record cannot support "the best five" and is published as BLOCKED with no per-name signal.
MIN_MEASURED_NAMES = 40

GATES = ("NOT_PRICED_OR_STALE_PRICE", "SECTOR_UNKNOWN", "SECTOR_EXCLUDED", "REPORT_ABSENT_OR_STALE",
         "FEATURES_NOT_MEASURED", "DISTRIBUTION_INCREASE_NOT_MATERIAL", "DISTRIBUTION_NOT_COVERED_BY_OPERATING_CASH_FLOW")
MEASURED_FEATURES = ("totalCashDistributionTTM", "totalCashDistributionChangeYoY", "operatingCashFlowTTM", "distributionToOCF")
STATES_USABLE = ("VALID", "REPORTED_ZERO")
DECISION_STATES = ("BLOCKED", "NO_ELIGIBLE_OPPORTUNITY", "CANDIDATE_PORTFOLIO")


def costs_bps() -> dict:
    """Round-trip cost per unit weight, from the dated table the official weekly policy already uses (US, no dated change)."""
    us = BA.REALISTIC_COSTS["US"]
    round_trip = 2 * float(us["commissionBps"]) + float(us["spreadBps"]) + float(us["sellTaxBps"])
    return {"source": "pipeline/benchmark_alpha.py REALISTIC_COSTS['US']",
            "commissionBpsPerSide": float(us["commissionBps"]), "fullSpreadBps": float(us["spreadBps"]),
            "sellTaxBps": float(us["sellTaxBps"]), "stockRoundTripBps": round(round_trip, 6),
            "etfRoundTripBps": round(round_trip, 6),
            "switchBpsPerUnitStockWeight": round(2 * round_trip, 6),
            "convention": "weekly-passive-first-v1 switchCost: round trip of the stock plus round trip of the ETF leg it displaces"}


def registration() -> dict:
    """The complete machine-readable registration. The committed spec file is generated from, and tested against, this."""
    return {
        "studyId": STUDY_ID, "registrationVersion": REGISTRATION_VERSION, "policyVersion": POLICY_VERSION, "namespace": NAMESPACE,
        "benchmarks": {"official": OFFICIAL_BENCHMARK, "alternative": ALTERNATIVE_BENCHMARK, "residual": RESIDUAL_ASSET},
        "status": "REGISTERED_PENDING_OWNER_APPROVAL", "authorization": None, "scheduledPublication": "NOT_STARTED",
        "evidenceClass": "PROSPECTIVE_PAPER_RESEARCH_CANDIDATE", "productionEffect": "NONE", "promotionEligible": False,
        "hypothesis": {
            "economic": ("A company that materially increases its shareholder cash distributions, with the increase supported by operating "
                         "cash flow and without excessive share dilution, may carry information about its next 126-session return relative "
                         "to a passive index that is not already in its price momentum, value or quality."),
            "primaryHorizonSessions": HORIZON_SESSIONS,
            "primaryClaim": ("The predeclared policy P1_STOCKS, net of switching costs, earns more than BOTH passive SPY and passive QQQ over 126 "
                             "sessions, on the same signal weeks and the same selected names."),
            "notClaimed": ["dilution-adjusted distribution growth (not testable from the store)", "any 21-session claim (descriptive only)",
                           "stock selection skill from a benchmark change (SPY to QQQ moves levels, not ranks)"],
        },
        "universe": {"membership": "S&P 500, latest membership snapshot strictly earlier than the signal date",
                     "membershipSource": "research_specs/alpha-opportunity-model-v1-us-membership.json.gz (datasets/s-and-p-500-companies)",
                     "signalDate": "last completed US session of each calendar week",
                     "identity": "a symbol whose price panel or fundamentals belong to a different issuer is IDENTITY_AMBIGUOUS and excluded",
                     "survivorship": "departed members stay in the cross-section while they were members; a name that stops trading while held "
                                     "has no outcome until a terminal consideration is cited (never a last price, never zero)"},
        "features": {"version": U.FEATURE_VERSION, "required": list(MEASURED_FEATURES),
                     "derived": {"incrementalDistributionOverOCF":
                                 "(D - D/(1+g)) / OCF = distributionToOCF * g / (1+g), D = totalCashDistributionTTM, g = totalCashDistributionChangeYoY"},
                     "dilution": {"status": DILUTION_STATUS, "gate": False,
                                  "reason": "period-end share count is present on 1.8% of stored filings; sharesOutstandingChangeYoY is BLOCKED"}},
        "gates": [
            {"order": 1, "id": GATES[0], "rule": "a positive close exists at or before the signal date, at most %d calendar days old, with at least %d prior sessions" % (MAX_PRICE_AGE_DAYS, MIN_PRIOR_SESSIONS)},
            {"order": 2, "id": GATES[1], "rule": "the sector label published in the membership snapshot (or an earlier one) is one of the eleven sector names"},
            {"order": 3, "id": GATES[2], "rule": "sector not in %s" % (list(EXCLUDED_SECTORS),)},
            {"order": 4, "id": GATES[3], "rule": "a filing is visible before the signal date and its report period ended at most %d days before it" % MAX_REPORT_AGE_DAYS},
            {"order": 5, "id": GATES[4], "rule": "%s all have a usable measurement and operatingCashFlowTTM > 0" % (list(MEASURED_FEATURES),)},
            {"order": 6, "id": GATES[5], "rule": "totalCashDistributionChangeYoY >= %.2f and incrementalDistributionOverOCF >= %.2f" % (MIN_DISTRIBUTION_GROWTH, MIN_INCREMENTAL_OVER_OCF)},
            {"order": 7, "id": GATES[6], "rule": "distributionToOCF <= %.1f" % MAX_DISTRIBUTION_TO_OCF}],
        "selection": {"rank": "incrementalDistributionOverOCF descending, ties by ticker ascending", "maxNames": MAX_NAMES,
                      "maxNamesPerSector": MAX_NAMES_PER_SECTOR, "slotWeight": SLOT_WEIGHT, "residualAsset": RESIDUAL_ASSET,
                      "residualWeight": "1 - slotWeight * names", "cash": "none", "retentionCredit": "none", "optimizedParameters": []},
        "alternatives": {"P0_SPY": "100% SPY", "P0_QQQ": "100% QQQ",
                         "P1_STOCKS": "0-5 selected names at 15% each plus the residual asset SPY (the official weekly policy's own construction)"},
        "inheritedFrom": {"maxNames": "docs/weekly-decision/weekly-passive-first-v1.json rule 6", "slotWeight": "config.json longterm.maxNameWeight",
                          "maxNamesPerSector": "config.json longterm.maxSectorWeight / maxNameWeight", "reportAgeDays": "pipeline/us_shareholder_distribution.py",
                          "priceEligibility": "pipeline/regional_alpha_features.py build_matrix", "horizon": "config.json historicalReplay.horizonDays",
                          "costs": "pipeline/benchmark_alpha.py REALISTIC_COSTS", "maturityGate": "config.json kellyPortfolio.activation and historicalReplay.minOrderingEffectiveDates"},
        "costs": costs_bps(),
        "coverage": {"minMeasuredNamesPerWeek": MIN_MEASURED_NAMES,
                     "belowFloor": "BLOCKED: identities and counts only, no per-name signal, no weights",
                     "setBy": "the weekly coverage audit (outcome-blind), after which no return was read"},
        "execution": {"signal": "close of the signal session", "entry": "close of the next US session (execution session 0)",
                      "exit": "close of the %dth US session after the execution session" % HORIZON_SESSIONS,
                      "returnBasis": "as-traded forward total return (price_adjustment.to_total_return); gross of withholding tax"},
        "inference": {
            "unit": "signal week", "overlap": "consecutive weekly horizons share 121 of 126 sessions",
            "method": "moving-block bootstrap of the weekly mean, block length 26 weeks (one horizon), 10000 replicates, one-sided 95%",
            "seed": 20261011, "blockWeeks": 26, "replicates": 10000, "confidence": 0.95,
            "blockedWeeks": "a BLOCKED week held no names, so the book was 100% residual SPY; it is evaluated as exactly that (excess vs SPY zero), never dropped",
            "statistics": {"theta_SPY": "mean over matured weeks of net(P1) - R(SPY)", "theta_QQQ": "mean over matured weeks of net(P1) - R(QQQ)",
                           "identity": "theta_QQQ = theta_SPY - mean(R(QQQ) - R(SPY)) exactly; the spread is reported, never re-ranked"}},
        "maturityGate": {"minMaturedSignals": 100, "minPaperDays": 252, "minIndependentWindows": 12,
                         "independentWindows": "floor(matured signal weeks / 26)",
                         "meaning": "no SUCCESS or FAILURE may be declared before this; earlier statistics are descriptive"},
        "verdicts": {
            "NOT_YET_EVALUABLE": "maturity gate not met",
            "SUCCESS": "gate met AND lower bound of theta_SPY > 0 AND lower bound of theta_QQQ > 0 AND no unresolved terminal outcome AND the policy held at least one name in at least 10% of matured weeks",
            "FAILURE": "gate met AND the one-sided 95% upper bound of theta_SPY < 0 OR of theta_QQQ < 0 (the policy is worse than a passive alternative it would replace)",
            "INCONCLUSIVE": "gate met and neither SUCCESS nor FAILURE, or any matured portfolio outcome unresolved",
            "multiplicity": ("one primary claim, tested as an intersection of two one-sided tests; each at 5%, both must pass, so the family-wise size "
                             "is at most 5% and no correction applies. Secondary diagnostics are Holm-adjusted among themselves and carry no verdict power."),
            "singleLook": "the first verdict at the gate is the verdict; later updates are continuation reports and cannot reverse it"},
        "secondary": ["decomposition: selection contribution vs SPY and passive growth spread QQQ-SPY",
                      "growth loading: regression of the weekly SPY excess on the QQQ-SPY spread (intercept = growth-adjusted selection)",
                      "selection null: random names from the gate-passing set and from the eligible set, same count and sector cap",
                      "incremental cross-sectional rank information beyond price and quality ranks (benchmark invariant)",
                      "H21 descriptive diagnostics"],
        "failureConditions": [
            "coverage below the weekly floor on a signal date (BLOCKED receipt, never a filled value)",
            "any registered parameter changes after approval (a new study id is required)",
            "an unresolved terminal outcome among matured receipts (verdict withheld)",
            "benchmark data integrity not PASS for SPY or QQQ (headline withheld)",
            "the feature version or digest rule differs from US_SHAREHOLDER_DISTRIBUTION_V1 (receipts refused)"],
        "namespaceSeparation": {"officialWeeklyDecisions": "ledger/weekly-decisions/ (untouched)",
                                "receipts": "ledger/research/us-capital-allocation-alpha-v1/receipts.jsonl",
                                "outcomes": "ledger/research/us-capital-allocation-alpha-v1/outcomes.jsonl"},
    }


def design_digest() -> str:
    return hashlib.sha256(json.dumps(registration(), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


# --------------------------------------------------------------------------- #
# The candidate rule
# --------------------------------------------------------------------------- #
def incremental_over_ocf(distribution_to_ocf, growth):
    """Newly committed distribution as a share of operating cash flow. growth > -1 is guaranteed by a positive prior base."""
    return distribution_to_ocf * growth / (1.0 + growth)


def _usable(features, name):
    feature = features.get(name) or {}
    return feature.get("value") is not None and feature.get("state") in STATES_USABLE


def evaluate(candidate: dict) -> dict:
    """First failing gate (in registered order) or a pass with its score. Pure; no I/O."""
    out = {"ticker": candidate["ticker"], "sector": candidate.get("sector"), "gate": None, "score": None}
    if not candidate.get("priceOk"):
        out["gate"] = GATES[0]
    elif candidate.get("sector") in (None, "UNCLASSIFIED"):
        out["gate"] = GATES[1]
    elif candidate["sector"] in EXCLUDED_SECTORS:
        out["gate"] = GATES[2]
    elif candidate.get("reportAgeDays") is None or candidate["reportAgeDays"] > MAX_REPORT_AGE_DAYS:
        out["gate"] = GATES[3]
    else:
        features = candidate.get("features") or {}
        ocf = (features.get("operatingCashFlowTTM") or {}).get("value")
        if not all(_usable(features, n) for n in MEASURED_FEATURES) or ocf is None or ocf <= 0:
            out["gate"] = GATES[4]
        else:
            growth = features["totalCashDistributionChangeYoY"]["value"]
            ratio = features["distributionToOCF"]["value"]
            # Growth is tested BEFORE the score is formed: a distribution that fell to zero has growth -1 and 1+g = 0, and no
            # score is defined for a name that is not increasing its payout.
            if growth < MIN_DISTRIBUTION_GROWTH:
                out["gate"] = GATES[5]
            else:
                out["score"] = incremental_over_ocf(ratio, growth)
                if out["score"] < MIN_INCREMENTAL_OVER_OCF:
                    out["gate"] = GATES[5]
                elif ratio > MAX_DISTRIBUTION_TO_OCF:
                    out["gate"] = GATES[6]
    return out


def funnel(evaluations) -> dict:
    counts = {g: 0 for g in GATES}
    passed = 0
    for e in evaluations:
        if e["gate"]:
            counts[e["gate"]] += 1
        else:
            passed += 1
    return {"evaluated": len(evaluations), "failedAt": counts, "passed": passed,
            "measured": sum(1 for e in evaluations if e["gate"] in (None, GATES[5], GATES[6]))}


def select(evaluations, *, max_names=MAX_NAMES, per_sector=MAX_NAMES_PER_SECTOR, min_measured=MIN_MEASURED_NAMES) -> dict:
    """The decision for one signal date. Deterministic: depends on the evaluations only, never on input order."""
    stages = funnel(evaluations)
    if stages["measured"] < min_measured:
        return {"status": "BLOCKED", "reasons": ["MEASURED_NAMES_BELOW_FLOOR:%d<%d" % (stages["measured"], min_measured)],
                "weights": None, "fallbackWeight": None, "selected": [], "passers": [], "skippedForSectorCap": [], "funnel": stages}
    passers = sorted((e for e in evaluations if e["gate"] is None), key=lambda e: (-e["score"], e["ticker"]))
    chosen, skipped, by_sector = [], [], {}
    for e in passers:
        if len(chosen) >= max_names:
            break
        if by_sector.get(e["sector"], 0) >= per_sector:
            skipped.append(e["ticker"])
            continue
        chosen.append(e)
        by_sector[e["sector"]] = by_sector.get(e["sector"], 0) + 1
    weights = {e["ticker"]: SLOT_WEIGHT for e in chosen}
    status = "CANDIDATE_PORTFOLIO" if chosen else "NO_ELIGIBLE_OPPORTUNITY"
    return {"status": status, "reasons": [] if chosen else ["NO_NAME_PASSED_EVERY_GATE"], "weights": dict(sorted(weights.items())),
            "fallbackWeight": round(1.0 - SLOT_WEIGHT * len(chosen), 12),
            "selected": [{"ticker": e["ticker"], "sector": e["sector"], "score": e["score"]} for e in chosen],
            "passers": [{"ticker": e["ticker"], "sector": e["sector"], "score": e["score"]} for e in passers],
            "skippedForSectorCap": skipped, "funnel": stages}


def candidate_from_snapshot(snapshot, *, sector, price_ok, report_age_days, ticker=None) -> dict:
    """Adapter from a PR #220 FeatureSnapshot. Only the four measured features and their states are carried."""
    return {"ticker": ticker or snapshot.ticker, "sector": sector, "priceOk": bool(price_ok), "reportAgeDays": report_age_days,
            "features": {n: {"value": snapshot.features[n].value, "state": snapshot.features[n].state.value} for n in MEASURED_FEATURES}}
