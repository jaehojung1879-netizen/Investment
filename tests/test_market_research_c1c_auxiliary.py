"""C1 auxiliary synthetic contrasts, with no historical outcomes or verdict authority."""
from copy import deepcopy
import math

import numpy as np
import pandas as pd
import pytest

from pipeline import market_research_c1c as C
from pipeline import market_research_c1c_contract as V
from pipeline import market_research_c1c_decisions as Q
from pipeline import market_research_c1c_diagnostics as D
from tests.test_market_research_c1c_input_readouts import inputs


@pytest.mark.parametrize("market", ["KR", "US"])
def test_every_c1_policy_cell_is_replayed_on_identical_funded_calendar(market):
    kw = inputs(market)
    original = deepcopy(kw)
    result = Q.synthetic_from_inputs(**kw)
    auxiliary = result["auxiliaryC1Diagnostics"]
    contrasts = result["auxiliaryC1VsC0"]
    assert set(auxiliary) == {k for k in V.cell_ids() if k.startswith("C1/")}
    assert set(contrasts) == set(auxiliary)
    panel = result["panel"]
    prices = kw["close"].loc[kw["plan"].executionDate.iloc[0]:]
    for key, report in auxiliary.items():
        assert report["cellId"] == key
        assert report["comparisonBasis"] == result["diagnostics"][key.replace("C1/", "C0/", 1)]["comparisonBasis"]
        selected = [row["cells"][key]["target"] for row in panel]
        replay = C.replay(prices, kw["plan"], selected, kw["cash_returns"], market,
                          kw["basis"], kw["stress"], evidence_class=C.SYNTHETIC)
        expected_growth = np.log(replay.nav.iloc[-1]) * 252 / (len(replay) - 1)
        assert report["summaries"]["candidate"]["netAnnualLogGrowth"] == pytest.approx(expected_growth)
        contrast = contrasts[key]
        assert contrast["status"] == "SYNTHETIC_DESCRIPTIVE_EFFECT_SIZES_ONLY"
        assert contrast["comparedWith"] == key.replace("C1/", "C0/", 1)
        assert not contrast["sourceAdmitted"] and not contrast["promotionAllowed"]
        assert not contrast["economicMaterialityRegistered"] and not contrast["inferenceEstablished"]
        a = report["summaries"]["candidate"]
        b = result["diagnostics"][contrast["comparedWith"]]["summaries"]["candidate"]
        assert contrast["effects"]["netCagrDifferencePp"] == pytest.approx(
            100 * (math.expm1(a["netAnnualLogGrowth"]) - math.expm1(b["netAnnualLogGrowth"])))
        assert contrast["effects"]["fundedDrawdownImprovementPp"] == pytest.approx(
            100 * (a["fundedMaxDrawdown"] - b["fundedMaxDrawdown"]))
        assert contrast["effects"]["dailyCvarReductionPp"] == pytest.approx(
            100 * (b["dailyCvar95Loss"] - a["dailyCvar95Loss"]))
    for key in ("close", "cash_returns"):
        assert kw[key].equals(original[key])
    for key in ("states", "plan"):
        assert kw[key].equals(original[key])
    assert kw["support"] == original["support"]
    assert not result["promotionAllowed"] and not result["historicalExecutionEnabled"]


@pytest.mark.parametrize("fault,reason", [
    ("cell", "RECONSTRUCTED_SYNTHETIC_CELL_ID_REQUIRED"),
    ("basis", "COMMON_COMPLETE_COMPARISON_BASIS_REQUIRED"),
    ("exposure", "DIRECT_MEAN_EXPOSURE_MATCH_REQUIRED"),
    ("missing_effect", "COMPLETE_FINITE_COMMON_METRICS_REQUIRED"),
])
def test_auxiliary_contrast_abstains_on_bad_primitive_derived_reports(fault, reason):
    result = Q.synthetic_from_inputs(**inputs())
    all_reports = {**result["diagnostics"], **result["auxiliaryC1Diagnostics"]}
    target = next(k for k in all_reports if k.startswith("C1/"))
    forged = deepcopy(all_reports)
    report = forged[target]
    if fault == "cell":
        report["cellId"] = target.replace("C1/", "C0/", 1)
    elif fault == "basis":
        report["comparisonBasis"]["planSha256"] = "0" * 64
    elif fault == "exposure":
        report["summaries"]["matchedStatic"]["meanIntervalExposure"] = 1.0
        report["summaries"]["candidate"]["meanIntervalExposure"] = .5
    else:
        report["summaries"]["candidate"]["netAnnualLogGrowth"] = float("nan")
    checked = Q._auxiliary_c1_vs_c0(forged, inputs()["support"])[target]
    assert checked["status"] == "INCONCLUSIVE"
    assert reason in checked["reasons"]
    assert checked["effects"] is None
    assert not checked["promotionAllowed"]


def test_auxiliary_refuses_incomplete_population_and_unmatured_support():
    result = Q.synthetic_from_inputs(**inputs())
    reports = {**result["diagnostics"], **result["auxiliaryC1Diagnostics"]}
    with pytest.raises(ValueError, match="COMPLETE_SIXTEEN"):
        Q._auxiliary_c1_vs_c0(dict(list(reports.items())[:-1]), inputs()["support"])
    kw = inputs()
    kw["support"]["windowMatured"] = False
    result = Q.synthetic_from_inputs(**kw)
    assert all(value["status"] == "INCONCLUSIVE" and value["effects"] is None
               for value in result["auxiliaryC1VsC0"].values())


def test_no_actual_market_history_accepted_for_auxiliary():
    kw = inputs()
    kw["evidence_class"] = "ACTUAL_HISTORY"
    with pytest.raises(ValueError, match="SYNTHETIC"):
        Q.synthetic_from_inputs(**kw)


@pytest.mark.parametrize('market,basis,stress', [
    ('KR', 'ETF_CASH_ECONOMIC', 1), ('US', 'ETF_CASH_ECONOMIC', 3),
    ('KR', 'C1_PRIMARY_REPLICA', 2),
])
def test_all_sixteen_reports_receive_reconstructed_targets_not_submitted_summaries(monkeypatch, market, basis, stress):
    kw = inputs(market)
    kw.update(basis=basis, stress=stress)
    original = D.synthetic_diagnostics
    calls = {}
    def spy(close, plan, selected, *args, **kwargs):
        calls[kwargs['cell_id']] = list(selected)
        return original(close, plan, selected, *args, **kwargs)
    monkeypatch.setattr(D, 'synthetic_diagnostics', spy)
    result = Q.synthetic_from_inputs(**kw)
    assert set(calls) == set(V.cell_ids())
    for cell, targets in calls.items():
        assert targets == [row['cells'][cell]['target'] for row in result['panel']]
    assert len(result['auxiliaryC1VsC0']) == 8
    assert all(r['verdict'] == 'DESCRIPTIVE_SIGN_ONLY' for r in result['readouts'].values())
    assert not result['historicalExecutionEnabled'] and not result['sourceAdmitted']


def test_cagr_pp_conversion_and_downside_signs_use_distinct_units():
    result = Q.synthetic_from_inputs(**inputs())
    reports = {**result['diagnostics'], **result['auxiliaryC1Diagnostics']}
    c1 = next(k for k in reports if k.startswith('C1/'))
    a = reports[c1]['summaries']['candidate']
    b = reports[c1.replace('C1/', 'C0/', 1)]['summaries']['candidate']
    a.update(netAnnualLogGrowth=math.log1p(.12), fundedMaxDrawdown=-.08, dailyCvar95Loss=.01)
    b.update(netAnnualLogGrowth=math.log1p(.10), fundedMaxDrawdown=-.10, dailyCvar95Loss=.02)
    effects = Q._auxiliary_c1_vs_c0(reports, inputs()['support'])[c1]['effects']
    assert effects['netCagrDifferencePp'] == pytest.approx(2.0)
    assert effects['netCagrDifferencePp'] != pytest.approx(100 * (math.log1p(.12) - math.log1p(.10)))
    assert effects['fundedDrawdownImprovementPp'] == pytest.approx(2.0)
    assert effects['dailyCvarReductionPp'] == pytest.approx(1.0)


def test_existing_reproduction_cli_exposes_the_eight_reconstructed_auxiliaries():
    from scripts import check_market_research as CLI
    result = CLI.synthetic_v2('KR')
    expected = {k for k in V.cell_ids() if k.startswith('C1/')}
    assert set(result['auxiliaryC1Diagnostics']) == set(result['auxiliaryC1VsC0']) == expected
    assert len(result['allCellsBasesCosts']) == 16 * 2 * 3
    assert len(result['c0FixedDescriptiveReadouts']) == 6
    assert all(x['verdict'] == 'DESCRIPTIVE_SIGN_ONLY' for x in result['c0FixedDescriptiveReadouts'].values())
    assert all(x['status'] == 'SYNTHETIC_DESCRIPTIVE_EFFECT_SIZES_ONLY' for x in result['auxiliaryC1VsC0'].values())
    assert result['sourceAdmitted'] is False and result['historicalOutcomeExecutions'] == 0


@pytest.mark.parametrize("market", ["KR", "US"])
@pytest.mark.parametrize("direction", [1, -1])
def test_actual_policy_divergence_in_ascending_and_descending_invented_prices(market, direction):
    """C0=.7 and C1=1.0 when FAST=1 has no SLOW/TRANSITION confirmation."""
    kw = inputs(market)
    n = len(kw["close"])
    kw["close"] = pd.Series(100 * np.exp(direction * .002 * np.arange(n)), index=kw["close"].index)
    kw["states"]["slow"] = 0
    kw["states"]["transition"] = 0
    kw["states"]["fast"] = 1
    kw["stress"] = 0
    output = Q.synthetic_from_inputs(**kw)
    family = V.FAMILIES[0]
    c0_key = f"C0/{family}/BASE"
    c1_key = f"C1/{family}/BASE"
    assert [row["cells"][c0_key]["target"] for row in output["panel"]] == [.7] * len(kw["plan"])
    assert [row["cells"][c1_key]["target"] for row in output["panel"]] == [1.] * len(kw["plan"])
    contrast = output["auxiliaryC1VsC0"][c1_key]
    assert contrast["status"] == "SYNTHETIC_DESCRIPTIVE_EFFECT_SIZES_ONLY"
    assert contrast["effects"]["netCagrDifferencePp"] * direction > 0.01
    assert contrast["effects"]["meanIntervalExposureDifference"] > 0
    if direction < 0:
        assert contrast["effects"]["fundedDrawdownImprovementPp"] < 0
        assert contrast["effects"]["dailyCvarReductionPp"] < 0
    assert "NOT_CAUSAL_TIMING_ALPHA" in contrast["matchedStaticContextMeaning"]
    assert not contrast["promotionAllowed"]


@pytest.mark.parametrize("market", ["KR", "US"])
def test_nonzero_effect_signs_against_independent_hand_calculated_constants(market):
    """Check pp conversion and directions with constants independent of the implementation."""
    kw = inputs(market)
    output = Q.synthetic_from_inputs(**kw)
    reports = deepcopy({**output["diagnostics"], **output["auxiliaryC1Diagnostics"]})
    family = V.FAMILIES[0]
    c0 = reports[f"C0/{family}/BASE"]["summaries"]
    c1 = reports[f"C1/{family}/BASE"]["summaries"]
    for name, candidate, static, exposure in (
        ("C0", (1.08, -.30, .08), (1.07, -.28, .075), .6),
        ("C1", (1.05, -.20, .05), (1.04, -.19, .04), .4),
    ):
        pair = c0 if name == "C0" else c1
        for title, metrics in (("candidate", candidate), ("matchedStatic", static)):
            r = pair[title]
            r["netAnnualLogGrowth"] = math.log(metrics[0])
            r["fundedMaxDrawdown"] = metrics[1]
            r["dailyCvar95Loss"] = metrics[2]
            r["meanIntervalExposure"] = exposure
    item = Q._auxiliary_c1_vs_c0(reports, kw["support"])[f"C1/{family}/BASE"]
    assert item["status"] == "SYNTHETIC_DESCRIPTIVE_EFFECT_SIZES_ONLY"
    actual = item["effects"]
    assert actual["netCagrDifferencePp"] == pytest.approx(-3.0, abs=1e-10)
    assert actual["fundedDrawdownImprovementPp"] == pytest.approx(10.0, abs=1e-10)
    assert actual["dailyCvarReductionPp"] == pytest.approx(3.0, abs=1e-10)
    assert actual["meanIntervalExposureDifference"] == pytest.approx(-.2, abs=1e-12)
    stat = item["ownMatchedStaticExcessDifferencesPp"]
    assert stat["netCagrExcessDifferencePp"] == pytest.approx(0.0, abs=1e-10)
    assert stat["fundedDrawdownExcessDifferencePp"] == pytest.approx(1.0, abs=1e-10)
    assert stat["dailyCvarReductionExcessDifferencePp"] == pytest.approx(-.5, abs=1e-10)
    assert not item["economicMaterialityRegistered"] and not item["inferenceEstablished"]


def test_static_metric_tampering_does_not_allow_adjusted_context():
    result = Q.synthetic_from_inputs(**inputs())
    reports = deepcopy({**result["diagnostics"], **result["auxiliaryC1Diagnostics"]})
    key = next(k for k in reports if k.startswith("C1/"))
    reports[key]["summaries"]["matchedStatic"]["dailyCvar95Loss"] = float("nan")
    output = Q._auxiliary_c1_vs_c0(reports, inputs()["support"])[key]
    assert "COMPLETE_FINITE_MATCHED_STATIC_METRICS_REQUIRED" in output["reasons"]
    assert output["effects"] is None
    assert output["ownMatchedStaticExcessDifferencesPp"] is None
    assert output["status"] == "INCONCLUSIVE"
