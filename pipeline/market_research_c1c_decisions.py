"""Proposed descriptive C0-led readout, for invented fixture diagnostics only.

This fixes directions before a future authorized study. Numerical dominance is
not a statistical test, an economic materiality threshold or independent audit.
It neither registers a hypothesis nor authorizes source use, execution or trades.
"""
from __future__ import annotations

import math
from copy import deepcopy
from numbers import Real
from datetime import date

import pandas as pd

from . import market_research_reentry_structure as R

TOLERANCE = 1e-10  # floating equality only; never a fitted economic hurdle
MATCH_TOLERANCE = 1e-12
_METRICS = {"netAnnualLogGrowth": 1, "fundedMaxDrawdown": 1, "dailyCvar95Loss": -1}
_BASIS_KEYS = {"market", "basis", "valuationIntervals", "calendarSha256", "planSha256", "assetSha256", "cashSha256",
               "startDate", "endDate", "costStress", "buyCost", "sellCost", "returnConvention", "cashBasis"}


def decision_policy():
    comparisons = ["REENTRY_MINUS_BASE", "COMBINED_MINUS_HARD_EXIT"]
    direction = "NET_GROWTH_NOT_LOWER_AND_DOWNSIDE_RISK_NOT_WORSE"
    return {"policyId": "C1C_V2_DESCRIPTIVE_DOMINANCE_PROPOSAL_V1",
            "status": "PROPOSED_NOT_REGISTERED_NOT_AUTHORIZED",
            "controlSelection": "C0_PRIMARY_C1_AUXILIARY_NEVER_RESULT_SELECTED",
            "decisionMetrics": dict(_METRICS), "numericalEqualityTolerance": TOLERANCE,
            "improved": "NO_DECISION_METRIC_WORSE_AND_AT_LEAST_ONE_STRICTLY_BETTER_AGAINST_BOTH_FIXED_COMPARATORS",
            "notImproved": "NO_DECISION_METRIC_BETTER_AGAINST_EITHER_FIXED_COMPARATOR",
            "tradeOff": "MIXED_METRIC_DIRECTIONS_OR_DISAGREEING_FIXED_COMPARATORS",
            "inconclusive": "MISSING_INVALID_INCOMPLETE_UNMATURED_OR_UNEQUAL_COMPARISON_BASIS",
            "fixedComparators": ["SAME_FAMILY_C0_BASE", "OWN_MEAN_INTERVAL_EXPOSURE_MATCHED_EX_POST_STATIC"],
            "reentryComparisons": [
                {"family": "C1c-REENTRY-SPEED-ORIGINAL-STRUCTURAL", "pairedComparisons": comparisons[:],
                 "mechanicalDirection": "NO_FASTER_THAN_MATCHED_MEMORYLESS_DESIRED_TARGET",
                 "desiredEconomicDirection": direction,
                 "interpretation": "SLOWER_ONE_RUNG_REENTRY_MAY_AVOID_WHIPSAW_BUT_MISS_REBOUND"},
                {"family": "POST_C1_RESULT_20_SESSION_BREAKOUT_SEPARATE", "pairedComparisons": comparisons[:],
                 "mechanicalDirection": "FASTER_ONLY_WHEN_FAST_1_AND_STRICT_PRIOR_20_CLOSE_BREAKOUT",
                 "desiredEconomicDirection": direction,
                 "interpretation": "POST_OUTCOME_NEW_PRICE_HYPOTHESIS_MAY_RECOVER_REBOUND_BUT_INCREASE_WHIPSAW"}],
            "returnInterpretation": "NET_GEOMETRIC_GROWTH_NOT_ARITHMETIC_SELECTION_ALPHA",
            "tailRiskDefinition": "MAX_ZERO_NEGATIVE_MEAN_OF_WORST_CEIL_5_PERCENT_DAILY_NET_INTERVAL_RETURNS",
            "tailEntryConvention": "FUNDED_ENTRY_IS_IN_CUMULATIVE_RETURN_AND_DRAWDOWN_NOT_A_TIME_INTERVAL",
            "nonDecisionDiagnostics": ["volatility", "turnover", "lossAvoidance", "reboundOpportunityCost", "arithmeticAttribution"],
            "significanceOrPowerEstablished": False, "minimumResearchSupportEstablished": False,
            "ownerAuthorization": False, "promotionAllowed": False}


def _number(value):
    return not isinstance(value, bool) and isinstance(value, Real) and math.isfinite(value)


def _metrics(values):
    if not isinstance(values, dict) or any(not _number(values.get(k)) for k in _METRICS):
        return False
    return -1 < values["fundedMaxDrawdown"] <= 0 and 0 <= values["dailyCvar95Loss"] < 1


def _basis_valid(value):
    if not isinstance(value, dict) or set(value) != _BASIS_KEYS:
        return False
    if (not isinstance(value["market"], str) or value["market"] not in ("KR", "US")
            or not isinstance(value["basis"], str) or value["basis"] not in ("C1_PRIMARY_REPLICA", "ETF_CASH_ECONOMIC")
            or not isinstance(value["cashBasis"], str)):
        return False
    for key in ("calendarSha256", "planSha256", "assetSha256", "cashSha256"):
        sha = value[key]
        if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            return False
    try:
        start, end = (date.fromisoformat(value[k]) for k in ("startDate", "endDate"))
    except (TypeError, ValueError):
        return False
    if str(start) != value["startDate"] or str(end) != value["endDate"] or start >= end:
        return False
    economic = value["basis"] == "ETF_CASH_ECONOMIC"
    convention = ("FUNDED_NET_ETF_TR_SAME_CLOSE_WITH_LIQUIDATION" if economic else
                  "NONINVESTABLE_PRICE_INDEX_UNFUNDED_START_NO_LIQUIDATION")
    cash = ({"KR_ZERO_RATE_OPPORTUNITY_COST_SCENARIO", "KR_UNVERIFIED_DAILY_RATE_SENSITIVITY_SCENARIO"} if value["market"] == "KR"
            else {"US_UNSPECIFIED_SYNTHETIC_CASH_SCENARIO", "US_SYNTHETIC_DTB3_PRIOR_KNOWN_ACT360"}) if economic else {"ZERO_CASH_NONINVESTABLE_INDEX_DIAGNOSTIC"}
    return (type(value["valuationIntervals"]) is int and value["valuationIntervals"] >= 2
            and type(value["costStress"]) is int and value["costStress"] in (0, 1, 2, 3)
            and all(_number(value[k]) and 0 <= value[k] < 1 for k in ("buyCost", "sellCost"))
            and value["returnConvention"] == convention and value["cashBasis"] in cash)


def _summaries(report):
    value = report.get("summaries")
    return value if isinstance(value, dict) else {}


def _compare(candidate, comparator):
    if not _metrics(candidate) or not _metrics(comparator):
        return {"verdict": "INCONCLUSIVE", "reason": "FINITE_POSSIBLE_COMPLETE_METRICS_REQUIRED"}
    signed = {k: direction * (candidate[k] - comparator[k]) for k, direction in _METRICS.items()}
    better = [k for k, v in signed.items() if v > TOLERANCE]
    worse = [k for k, v in signed.items() if v < -TOLERANCE]
    verdict = "TRADE_OFF" if better and worse else "IMPROVED" if better else "NOT_IMPROVED"
    return {"verdict": verdict, "signedImprovement": signed, "betterMetrics": better, "worseMetrics": worse}


def _equivalent(candidate, control, support, *, control_arm="BASE"):
    reasons = []
    def cell(value):
        return value.split("/") if isinstance(value, str) else []
    identity, baseline = cell(candidate.get("cellId")), cell(control.get("cellId"))
    if (len(identity) != 3 or identity[0] != "C0" or identity[1] not in (R.STRUCTURAL_HYPOTHESIS, R.BREAKOUT_HYPOTHESIS)
            or identity[2] not in ("BASE", "HARD_EXIT", "REENTRY", "COMBINED")
            or baseline != ["C0", *identity[1:2], control_arm]):
        reasons.append("FIXED_SAME_FAMILY_C0_BASE_REQUIRED")
    a, b = candidate.get("comparisonBasis"), control.get("comparisonBasis")
    if not _basis_valid(a) or not _basis_valid(b) or a != b:
        reasons.append("COMPARISON_BASIS_MISMATCH")
    else:
        n = a["valuationIntervals"]
        if (type(n) is not int or n < 2 or not isinstance(support, dict)
                or support.get("windowMatured") is not True
                or type(support.get("intendedIntervals")) is not int
                or type(support.get("observedIntervals")) is not int
                or support.get("intendedIntervals") != n or support.get("observedIntervals") != n):
            reasons.append("MATURE_COMPLETE_INTENDED_WINDOW_REQUIRED")
        summaries = [_summaries(candidate).get(k, {}) for k in ("candidate", "matchedStatic")]
        summaries.append(_summaries(control).get("candidate", {}))
        if any(not isinstance(s, dict) or type(s.get("valuationIntervals")) is not int or s.get("valuationIntervals") != n for s in summaries):
            reasons.append("SUMMARY_WINDOW_MISMATCH")
    match = candidate.get("exposureMatch", {})
    if (not isinstance(match, dict) or match.get("matched") is not True
            or not _number(match.get("residual")) or abs(match["residual"]) > MATCH_TOLERANCE
            or match.get("tolerance") != MATCH_TOLERANCE):
        reasons.append("FIXED_EXPOSURE_MATCH_NOT_ESTABLISHED")
    return reasons


def _summary_readout(candidate_report, c0_base_report, *, support, rejection=None):
    """Internal arithmetic over reconstructed reports, not report authentication.

    Both arguments must be generated on the same complete invented valuation
    window. Counts establish fixture completeness only. Weekly support, independent
    blocks, uncertainty, multiplicity and a genuine cash/ETF source remain separate
    requirements for any future scientific conclusion. No real-data mode exists.
    """
    if any(not isinstance(r, dict) or r.get("evidenceClass") != "SYNTHETIC_FIXTURE"
           for r in (candidate_report, c0_base_report)):
        raise ValueError("SYNTHETIC_READOUT_ONLY")
    reasons = _equivalent(candidate_report, c0_base_report, support)
    if rejection:
        reasons.append(rejection)
    first = second = {"verdict": "INCONCLUSIVE"}
    if not reasons:
        metrics = _summaries(candidate_report)
        first = _compare(metrics.get("candidate"), _summaries(c0_base_report).get("candidate"))
        second = _compare(metrics.get("candidate"), metrics.get("matchedStatic"))
    pair = (first["verdict"], second["verdict"])
    verdict = ("INCONCLUSIVE" if "INCONCLUSIVE" in pair else
               "IMPROVED" if pair == ("IMPROVED", "IMPROVED") else
               "NOT_IMPROVED" if pair == ("NOT_IMPROVED", "NOT_IMPROVED") else "TRADE_OFF")
    return {"verdict": verdict, "reasons": reasons, "againstC0Base": first,
            "againstEqualExposureStatic": second, "policy": decision_policy(),
            "status": "SYNTHETIC_DESCRIPTIVE_ONLY_PROPOSED_POLICY", "primaryControl": "C0",
            "staticComparatorMeaning": "EX_POST_FULL_PATH_MEAN_EXPOSURE_MATCH_NOT_A_TRADABLE_FORECAST",
            "interpretation": "RISK_RETURN_DOMINANCE_NOT_STATISTICAL_ALPHA_OR_ARITHMETIC_SELECTION",
            "arithmeticAttribution": None if rejection else candidate_report.get("arithmeticAttribution"),
            "statisticalAlphaEstablished": False, "minimumResearchSupportEstablished": False,
            "ownerAuthorization": False, "sourceAdmitted": False, "promotionAllowed": False}


def _summary_reentry_contrasts(reports, *, support, rejection=None):
    """Internal arithmetic over the complete reconstructed C0 report set."""
    families = (R.STRUCTURAL_HYPOTHESIS, R.BREAKOUT_HYPOTHESIS)
    expected = {f"C0/{family}/{arm}" for family in families for arm in ("BASE", "HARD_EXIT", "REENTRY", "COMBINED")}
    if not isinstance(reports, dict) or set(reports) != expected:
        raise ValueError("COMPLETE_EIGHT_C0_CELL_DIAGNOSTICS_REQUIRED")
    if any(not isinstance(r, dict) or r.get("evidenceClass") != "SYNTHETIC_FIXTURE"
           or r.get("cellId") != key for key, r in reports.items()):
        raise ValueError("SYNTHETIC_SAME_IDENTITY_REPORTS_REQUIRED")
    result = {}
    for family in families:
        for changed, baseline in (("REENTRY", "BASE"), ("COMBINED", "HARD_EXIT")):
            a, b = (reports[f"C0/{family}/{arm}"] for arm in (changed, baseline))
            reasons = _equivalent(a, b, support, control_arm=baseline)
            if rejection:
                reasons.append(rejection)
            comparison = ({"verdict": "INCONCLUSIVE"} if reasons else
                          _compare(_summaries(a).get("candidate"), _summaries(b).get("candidate")))
            result[f"C0/{family}/{changed}_MINUS_{baseline}"] = {
                **comparison, "reasons": reasons, "onlyChangedAxis": None if rejection else "REENTRY_RULE",
                "hardExitMatched": None if rejection else baseline == "HARD_EXIT", "controlRole": "C0_PRIMARY",
                "direction": "NET_GROWTH_NOT_LOWER_AND_DOWNSIDE_RISK_NOT_WORSE",
                "statisticalAlphaEstablished": False, "nominationAllowed": False}
    return result


def _auxiliary_c1_vs_c0(reports, support):
    """Paired C1-minus-C0 fixture effect sizes; never an economic verdict.

    This private function only consumes complete primitive-reconstructed reports.
    Each family/arm is compared to the same family/arm under C0 on an identical
    funded valuation calendar. The signs are informational, not selection rules.
    """
    from . import market_research_c1c_contract as V

    if not isinstance(reports, dict) or set(reports) != set(V.cell_ids()):
        raise ValueError("COMPLETE_SIXTEEN_CELL_POPULATION_REQUIRED")
    result = {}
    for family in V.FAMILIES:
        for arm in V.ARMS:
            c1_key, c0_key = f"C1/{family}/{arm}", f"C0/{family}/{arm}"
            c1, c0 = reports[c1_key], reports[c0_key]
            reasons = []
            if (c1.get("evidenceClass") != "SYNTHETIC_FIXTURE"
                    or c0.get("evidenceClass") != "SYNTHETIC_FIXTURE"
                    or c1.get("cellId") != c1_key or c0.get("cellId") != c0_key):
                reasons.append("RECONSTRUCTED_SYNTHETIC_CELL_ID_REQUIRED")
            b1, b0 = c1.get("comparisonBasis"), c0.get("comparisonBasis")
            if not _basis_valid(b1) or b1 != b0:
                reasons.append("COMMON_COMPLETE_COMPARISON_BASIS_REQUIRED")
            else:
                n = b1["valuationIntervals"]
                if (not isinstance(support, dict) or support.get("windowMatured") is not True
                        or type(support.get("intendedIntervals")) is not int
                        or type(support.get("observedIntervals")) is not int
                        or support["intendedIntervals"] != n or support["observedIntervals"] != n):
                    reasons.append("MATURE_COMPLETE_INTENDED_WINDOW_REQUIRED")
            s1, s0 = _summaries(c1), _summaries(c0)
            a, b = s1.get("candidate"), s0.get("candidate")
            if (not _metrics(a) or not _metrics(b)
                    or not isinstance(b1, dict)
                    or any(type(s.get("valuationIntervals")) is not int
                           or s["valuationIntervals"] != b1.get("valuationIntervals")
                           for s in (a or {}, b or {}))):
                reasons.append("COMPLETE_FINITE_COMMON_METRICS_REQUIRED")
            for report in (c1, c0):
                summaries = _summaries(report)
                candidate, static = summaries.get("candidate", {}), summaries.get("matchedStatic", {})
                v = candidate.get("meanIntervalExposure") if isinstance(candidate, dict) else None
                w = static.get("meanIntervalExposure") if isinstance(static, dict) else None
                if (not _number(v) or not _number(w) or not 0 <= v <= 1
                        or not 0 <= w <= 1 or abs(v - w) > MATCH_TOLERANCE):
                    reasons.append("DIRECT_MEAN_EXPOSURE_MATCH_REQUIRED")
                    break
            deltas = None
            if not reasons:
                try:
                    deltas = {
                        "netCagrDifferencePp": 100 * (math.expm1(a["netAnnualLogGrowth"]) - math.expm1(b["netAnnualLogGrowth"])),
                        "fundedDrawdownImprovementPp": 100 * (a["fundedMaxDrawdown"] - b["fundedMaxDrawdown"]),
                        "dailyCvarReductionPp": 100 * (b["dailyCvar95Loss"] - a["dailyCvar95Loss"]),
                        "meanIntervalExposureDifference": a["meanIntervalExposure"] - b["meanIntervalExposure"],
                    }
                except (OverflowError, ValueError):
                    deltas = None
                if deltas is None or not all(_number(v) for v in deltas.values()):
                    reasons.append("FINITE_ECONOMIC_EFFECT_SIZE_REQUIRED")
                    deltas = None
            result[c1_key] = {
                "status": "INCONCLUSIVE" if reasons else "SYNTHETIC_DESCRIPTIVE_EFFECT_SIZES_ONLY",
                "comparedWith": c0_key, "reasons": reasons, "effects": deltas,
                "positiveEffectsConvention": "POSITIVE_CAGR_DRAWDOWN_CVAR_VALUES_FAVOR_C1_NOT_A_VERDICT",
                "role": "C1_AUXILIARY_C0_PRIMARY", "economicMaterialityRegistered": False,
                "inferenceEstablished": False, "sourceAdmitted": False, "promotionAllowed": False,
            }
    return result


_UNVERIFIED = "UNVERIFIED_REPORT_MAPPING_REQUIRES_PRIMITIVE_RECONSTRUCTION"


def synthetic_readout(candidate_report, c0_base_report, *, support):
    """Legacy summary input abstains: caller metrics/identity are not evidence.

    Use synthetic_from_inputs to reconstruct targets, paths and comparators.
    Re-signing a submitted summary cannot make its assertions authoritative.
    """
    return _summary_readout(candidate_report, c0_base_report, support=support, rejection=_UNVERIFIED)


def synthetic_reentry_contrasts(reports, *, support):
    """Legacy report mappings cannot establish the one-axis policy contrast."""
    return _summary_reentry_contrasts(reports, support=support, rejection=_UNVERIFIED)


def synthetic_from_inputs(close, states, plan, cash_returns, market, basis, stress, *,
                          evidence_class, support, cash_basis=None, episodes=()):
    """Reconstruct all fixed C0 policy cells from complete invented primitives.

    No submitted target, cell label, metric, exposure-match flag or report digest
    participates in a verdict. State domains/publication times and prior-close
    breakout semantics are checked by the existing policy engine. The same
    replay regenerates candidate, passive and full-path exposure-matched static
    comparators, then internal arithmetic compares the fixed policy cells.

    This establishes fixture consistency only. Caller-invented states are not
    source-authenticated market states; no source, historical execution,
    statistical support, economic materiality or promotion is authorized here.
    """
    from . import market_research_c1c as C
    from . import market_research_c1c_contract as V
    from . import market_research_c1c_diagnostics as D

    if evidence_class != C.SYNTHETIC:
        raise ValueError("SYNTHETIC_PRIMITIVE_READOUT_ONLY")
    if (not isinstance(close, pd.Series) or not isinstance(cash_returns, pd.Series)
            or not isinstance(states, pd.DataFrame) or not isinstance(plan, pd.DataFrame)):
        raise ValueError("INVENTED_PRIMITIVE_TYPES_REQUIRED")
    close, states, plan, cash = (v.copy(deep=True) for v in (close, states, plan, cash_returns))
    if isinstance(episodes, (str, bytes, dict)):
        raise ValueError("FIXED_EPISODE_SEQUENCE_REQUIRED")
    try:
        episodes = deepcopy(tuple(episodes))
    except TypeError as exc:
        raise ValueError("FIXED_EPISODE_SEQUENCE_REQUIRED") from exc
    support = deepcopy(support)
    panel = V.panel_targets(close, states, plan, market)
    prices = close.loc[plan.executionDate.iloc[0]:]
    reports = {}
    for cell in V.cell_ids():
        selected = [row["cells"][cell]["target"] for row in panel]
        reports[cell] = D.synthetic_diagnostics(prices, plan, selected, cash, market, basis, stress,
            evidence_class=C.SYNTHETIC, cell_id=cell, cash_basis=cash_basis, episodes=episodes)
    primary = {key: value for key, value in reports.items() if key.startswith("C0/")}
    auxiliary = {key: value for key, value in reports.items() if key.startswith("C1/")}
    readouts = {cell: _summary_readout(r, primary[cell.rsplit("/", 1)[0] + "/BASE"], support=support)
                for cell, r in primary.items() if not cell.endswith("/BASE")}
    return {"inputAuthority": "RECOMPUTED_INVENTED_PRIMITIVES_NOT_SOURCE_ADMISSION",
            "evidenceClass": C.SYNTHETIC, "panel": panel, "diagnostics": primary,
            "readouts": readouts, "reentryContrasts": _summary_reentry_contrasts(primary, support=support),
            "auxiliaryC1Diagnostics": auxiliary,
            "auxiliaryC1VsC0": _auxiliary_c1_vs_c0(reports, support),
            "stateProvenance": "CALLER_INVENTED_STATES_NOT_AUTHENTICATED_MARKET_SIGNALS",
            "sourceAdmitted": False, "historicalExecutionEnabled": False, "promotionAllowed": False}
