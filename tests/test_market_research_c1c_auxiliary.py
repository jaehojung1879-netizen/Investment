"""C1 auxiliary synthetic contrasts, with no historical outcomes or verdict authority."""
from copy import deepcopy
import math

import numpy as np
import pytest

from pipeline import market_research_c1c as C
from pipeline import market_research_c1c_contract as V
from pipeline import market_research_c1c_decisions as Q
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
