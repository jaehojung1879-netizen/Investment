"""Invented diagnostics only; no source reader or historical outcome access."""
from copy import deepcopy

import pytest

from pipeline import market_research_c1c_decisions as Q


def summary(ret=.05, dd=-.10, tail=.02):
    return {"netAnnualLogGrowth": ret, "fundedMaxDrawdown": dd,
            "dailyCvar95Loss": tail, "valuationIntervals": 126}


def report(values=None, static=None):
    return {"evidenceClass": "SYNTHETIC_FIXTURE", "market": "KR", "basis": "ETF_CASH_ECONOMIC",
            "cellId": "C0/C1c-REENTRY-SPEED-ORIGINAL-STRUCTURAL/BASE",
            "comparisonBasis": {"market": "KR", "basis": "ETF_CASH_ECONOMIC", "valuationIntervals": 126,
                "calendarSha256": "1" * 64, "assetSha256": "2" * 64, "cashSha256": "3" * 64,
                "startDate": "2030-01-02", "endDate": "2030-07-02", "costStress": 1,
                "buyCost": .00055, "sellCost": .00055,
                "returnConvention": "FUNDED_NET_ETF_TR_SAME_CLOSE_WITH_LIQUIDATION",
                "cashBasis": "KR_ZERO_RATE_OPPORTUNITY_COST_SCENARIO"},
            "exposureMatch": {"matched": True, "residual": 0., "tolerance": 1e-12},
            "summaries": {"candidate": summary() if values is None else values,
                          "matchedStatic": summary() if static is None else static}}


def support(**kw):
    return dict(windowMatured=True, intendedIntervals=126, observedIntervals=126, **kw)


@pytest.mark.parametrize("candidate, verdict", [
    (summary(.06, -.09, .019), "IMPROVED"),
    (summary(.05, -.10, .02), "NOT_IMPROVED"),
    (summary(.04, -.11, .03), "NOT_IMPROVED"),
    (summary(.06, -.11, .019), "TRADE_OFF"),
    (summary(.04, -.09, .019), "TRADE_OFF"),
])
def test_fixed_direction_rule_does_not_select_one_favorable_metric(candidate, verdict):
    out = Q.synthetic_readout(report(candidate), report(), support=support())
    assert out["verdict"] == verdict
    assert out["againstC0Base"]["verdict"] == verdict
    assert out["againstEqualExposureStatic"]["verdict"] == verdict
    assert not out["statisticalAlphaEstablished"] and not out["promotionAllowed"]
    assert not out["ownerAuthorization"] and not out["minimumResearchSupportEstablished"]


def test_beating_c0_without_beating_equal_exposure_static_is_not_improved():
    out = Q.synthetic_readout(report(summary(.06), static=summary(.07)), report(), support=support())
    assert out["againstC0Base"]["verdict"] == "IMPROVED"
    assert out["againstEqualExposureStatic"]["verdict"] == "NOT_IMPROVED"
    assert out["verdict"] == "TRADE_OFF"
    assert out["staticComparatorMeaning"].startswith("EX_POST")


@pytest.mark.parametrize("fault", ["missing", "nan", "inf", "bool", "negative_tail", "positive_drawdown"])
def test_missing_or_impossible_measurements_abstain(fault):
    candidate = summary()
    if fault == "missing": candidate.pop("dailyCvar95Loss")
    if fault == "nan": candidate["netAnnualLogGrowth"] = float("nan")
    if fault == "inf": candidate["dailyCvar95Loss"] = float("inf")
    if fault == "bool": candidate["fundedMaxDrawdown"] = True
    if fault == "negative_tail": candidate["dailyCvar95Loss"] = -.01
    if fault == "positive_drawdown": candidate["fundedMaxDrawdown"] = .01
    assert Q.synthetic_readout(report(candidate), report(), support=support())["verdict"] == "INCONCLUSIVE"


@pytest.mark.parametrize("key", ["calendarSha256", "assetSha256", "cashSha256", "startDate", "endDate", "costStress", "buyCost", "cashBasis", "returnConvention"])
def test_comparison_basis_cannot_change_between_candidate_and_control(key):
    control = report(); control["comparisonBasis"][key] = "DIFFERENT"
    out = Q.synthetic_readout(report(), control, support=support())
    assert out["verdict"] == "INCONCLUSIVE" and "COMPARISON_BASIS_MISMATCH" in out["reasons"]


@pytest.mark.parametrize("field, value", [("windowMatured", False), ("intendedIntervals", 127),
                                          ("observedIntervals", 125), ("intendedIntervals", True)])
def test_unmatured_or_incomplete_cohort_does_not_read_as_failure(field, value):
    s = support(); s[field] = value
    assert Q.synthetic_readout(report(), report(), support=s)["verdict"] == "INCONCLUSIVE"


def test_numerical_equality_tolerance_is_fixed_and_not_an_economic_threshold():
    small = summary(.05 + 1e-12)
    assert Q.synthetic_readout(report(small), report(), support=support())["verdict"] == "NOT_IMPROVED"
    assert Q.decision_policy()["numericalEqualityTolerance"] == 1e-10
    assert Q.decision_policy()["status"] == "PROPOSED_NOT_REGISTERED_NOT_AUTHORIZED"


def test_foreign_evidence_and_forged_static_match_do_not_get_verdict():
    r = report(); r["evidenceClass"] = "ACTUAL_HISTORY"
    with pytest.raises(ValueError, match="SYNTHETIC"):
        Q.synthetic_readout(r, report(), support=support())
    for changed in ({"matched": False}, {"residual": .1}, {"tolerance": 1.}, {"matched": 1}):
        r = report(); r["exposureMatch"].update(changed)
        assert Q.synthetic_readout(r, report(), support=support())["verdict"] == "INCONCLUSIVE"


def test_family_directions_cannot_turn_slow_structural_reentry_into_breakout():
    p = Q.decision_policy()
    structural, breakout = p["reentryComparisons"]
    assert structural["mechanicalDirection"] == "NO_FASTER_THAN_MATCHED_MEMORYLESS_DESIRED_TARGET"
    assert breakout["mechanicalDirection"] == "FASTER_ONLY_WHEN_FAST_1_AND_STRICT_PRIOR_20_CLOSE_BREAKOUT"
    assert structural["pairedComparisons"] == breakout["pairedComparisons"] == ["REENTRY_MINUS_BASE", "COMBINED_MINUS_HARD_EXIT"]
    assert all(x["desiredEconomicDirection"] == "NET_GROWTH_NOT_LOWER_AND_DOWNSIDE_RISK_NOT_WORSE" for x in p["reentryComparisons"])
    assert p["controlSelection"] == "C0_PRIMARY_C1_AUXILIARY_NEVER_RESULT_SELECTED"


def test_inputs_are_immutable():
    a, b, s = report(), report(), support()
    original = deepcopy((a, b, s))
    Q.synthetic_readout(a, b, support=s)
    assert (a, b, s) == original


@pytest.mark.parametrize("field, value", [("costStress", True), ("valuationIntervals", 126.),
                                          ("assetSha256", "x" * 64), ("buyCost", float("nan"))])
def test_both_basis_contracts_are_validated_not_only_dict_equality(field, value):
    a, b = report(), report(); b["comparisonBasis"][field] = value
    assert Q.synthetic_readout(a, b, support=support())["verdict"] == "INCONCLUSIVE"


def test_diagnostic_replay_supplies_bound_complete_metrics_and_cash_semantics():
    from tests.test_market_research_c1c_diagnostics import fixture
    from pipeline import market_research_c1c as C
    from pipeline import market_research_c1c_diagnostics as D
    close, plan, cash = fixture("KR")
    targets = [.7] * len(plan)
    r = D.synthetic_diagnostics(close, plan, targets, cash, "KR", "ETF_CASH_ECONOMIC", 1, evidence_class=C.SYNTHETIC,
                                cell_id="C0/C1c-REENTRY-SPEED-ORIGINAL-STRUCTURAL/BASE")
    n = len(close) - 1
    out = Q.synthetic_readout(r, r, support={"windowMatured": True, "intendedIntervals": n, "observedIntervals": n})
    assert out["verdict"] == "NOT_IMPROVED"
    assert r["comparisonBasis"]["cashBasis"] == "KR_ZERO_RATE_OPPORTUNITY_COST_SCENARIO"
    assert r["summaries"]["candidate"]["dailyCvar95Loss"] >= 0
    assert not r["cashInterpretation"]["zeroCashIsActualShortRate"]
    cash[:] = .0001
    with pytest.raises(ValueError, match="CASH_BASIS"):
        D.synthetic_diagnostics(close, plan, targets, cash, "KR", "ETF_CASH_ECONOMIC", 1, evidence_class=C.SYNTHETIC)
    r = D.synthetic_diagnostics(close, plan, targets, cash, "KR", "ETF_CASH_ECONOMIC", 1,
                               evidence_class=C.SYNTHETIC, cash_basis="KR_UNVERIFIED_DAILY_RATE_SENSITIVITY_SCENARIO")
    assert not r["cashInterpretation"]["sourceAdmitted"]
    with pytest.raises(ValueError, match="CASH_BASIS"):
        D.synthetic_diagnostics(close, plan, targets, cash, "KR", "ETF_CASH_ECONOMIC", 1,
                               evidence_class=C.SYNTHETIC, cash_basis="US_SYNTHETIC_DTB3_PRIOR_KNOWN_ACT360")


@pytest.mark.parametrize("cell_id", [None, "C1/C1c-REENTRY-SPEED-ORIGINAL-STRUCTURAL/BASE",
                                     "C0/POST_C1_RESULT_20_SESSION_BREAKOUT_SEPARATE/BASE",
                                     "C0/C1c-REENTRY-SPEED-ORIGINAL-STRUCTURAL/REENTRY"])
def test_control_identity_family_and_c0_role_are_fixed(cell_id):
    a, b = report(), report(); b["cellId"] = cell_id
    assert Q.synthetic_readout(a, b, support=support())["verdict"] == "INCONCLUSIVE"


def test_reentry_contrasts_change_only_one_axis_and_preserve_both_families():
    from pipeline import market_research_reentry_structure as R
    reports = {}
    for family in (R.STRUCTURAL_HYPOTHESIS, R.BREAKOUT_HYPOTHESIS):
        for arm, value in (("BASE", .05), ("HARD_EXIT", .08), ("REENTRY", .06), ("COMBINED", .07)):
            key = f"C0/{family}/{arm}"
            reports[key] = report(summary(value)); reports[key]["cellId"] = key
    out = Q.synthetic_reentry_contrasts(reports, support=support())
    assert len(out) == 4
    for key, item in out.items():
        assert item["onlyChangedAxis"] == "REENTRY_RULE" and not item["nominationAllowed"]
        assert item["verdict"] == ("IMPROVED" if key.endswith("REENTRY_MINUS_BASE") else "NOT_IMPROVED")
    partial = dict(reports); partial.pop(next(iter(partial)))
    with pytest.raises(ValueError, match="COMPLETE_EIGHT"):
        Q.synthetic_reentry_contrasts(partial, support=support())
    first = next(iter(reports)); reports[first]["cellId"] = "C1/forged/BASE"
    with pytest.raises(ValueError, match="SAME_IDENTITY"):
        Q.synthetic_reentry_contrasts(reports, support=support())
