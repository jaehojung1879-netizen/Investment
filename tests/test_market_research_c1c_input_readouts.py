"""B2 regressions: invented primitives, never real sources or outcomes."""
from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from pipeline import market_research_c1c as C
from pipeline import market_research_c1c_contract as V
from pipeline import market_research_c1c_decisions as Q
from scripts.check_market_research import fixture
from tests.test_market_research_c1c_decisions import report, summary, support


def inputs(market="KR"):
    close, plan, states = fixture(market)
    plan = plan.iloc[:5].copy()
    close = close.loc[:plan.executionDate.iloc[-1]].copy()
    states = states.loc[plan.decisionDate].copy()
    cash = pd.Series(0.0, index=close.index)
    n = len(close.loc[plan.executionDate.iloc[0]:]) - 1
    return dict(close=close, states=states, plan=plan, cash_returns=cash, market=market,
                basis="ETF_CASH_ECONOMIC", stress=1, evidence_class=C.SYNTHETIC,
                support={"windowMatured": True, "intendedIntervals": n, "observedIntervals": n})


@pytest.mark.parametrize("mutation", ["passive_static", "cell_relabel", "resigned_summary"])
def test_caller_reports_cannot_authorize_even_a_numerical_verdict(mutation):
    a, b = report(summary(.06, -.09, .019)), report()
    if mutation == "passive_static":
        a["summaries"]["matchedStatic"]["meanIntervalExposure"] = 1.0
        a["exposureMatch"].update(candidateMeanIntervalExposure=.73, staticMeanIntervalExposure=.73)
    if mutation == "cell_relabel":
        a["cellId"] = a["cellId"].replace("/BASE", "/COMBINED")
    if mutation == "resigned_summary":
        a["reportSha256"] = C.digest(a)
    a["arithmeticAttribution"] = {"timingCovariance": 999.0, "sourceAdmitted": True}
    out = Q.synthetic_readout(a, b, support=support())
    assert out["verdict"] == "INCONCLUSIVE"
    assert "UNVERIFIED_REPORT_MAPPING_REQUIRES_PRIMITIVE_RECONSTRUCTION" in out["reasons"]
    assert all(out[k]["verdict"] == "INCONCLUSIVE" for k in ("againstC0Base", "againstEqualExposureStatic"))
    assert not out["sourceAdmitted"] and not out["promotionAllowed"]
    assert out["arithmeticAttribution"] is None


def test_eight_base_copies_cannot_be_relabelled_as_policy_cells():
    reports = {k: dict(deepcopy(report()), cellId=k) for k in V.cell_ids() if k.startswith("C0/")}
    out = Q.synthetic_reentry_contrasts(reports, support=support())
    assert len(out) == 4
    assert all(r["verdict"] == "INCONCLUSIVE" for r in out.values())
    assert all(r["onlyChangedAxis"] is None and r["hardExitMatched"] is None for r in out.values())


@pytest.mark.parametrize("market", ["KR", "US"])
def test_primitive_entry_derives_every_c0_cell_and_replays_actual_targets(market):
    kw = inputs(market)
    before = deepcopy(kw)
    out = Q.synthetic_from_inputs(**kw)
    assert out["inputAuthority"] == "RECOMPUTED_INVENTED_PRIMITIVES_NOT_SOURCE_ADMISSION"
    assert set(out["diagnostics"]) == {k for k in V.cell_ids() if k.startswith("C0/")}
    assert len(out["readouts"]) == 6 and len(out["reentryContrasts"]) == 4
    panel = V.panel_targets(kw["close"], kw["states"], kw["plan"], market)
    assert out["panel"] == panel
    prices = kw["close"].loc[kw["plan"].executionDate.iloc[0]:]
    for cell, r in out["diagnostics"].items():
        selected = [row["cells"][cell]["target"] for row in panel]
        path = C.replay(prices, kw["plan"], selected, kw["cash_returns"], market,
                        kw["basis"], 1, evidence_class=C.SYNTHETIC)
        expected = np.log(path.nav.iloc[-1]) * 252 / (len(path) - 1)
        assert r["summaries"]["candidate"]["netAnnualLogGrowth"] == pytest.approx(expected)
        assert r["summaries"]["candidate"]["meanIntervalExposure"] == pytest.approx(
            r["summaries"]["matchedStatic"]["meanIntervalExposure"], abs=1e-12)
    for key in ("close", "cash_returns"):
        pd.testing.assert_series_equal(kw[key], before[key])
    for key in ("states", "plan"):
        pd.testing.assert_frame_equal(kw[key], before[key])
    assert kw["support"] == before["support"]
    assert not out["sourceAdmitted"] and not out["historicalExecutionEnabled"]
    assert all(not r["promotionAllowed"] for r in out["readouts"].values())


@pytest.mark.parametrize("field", ["selected", "reports", "cell_id", "exposureMatch"])
def test_primitive_entry_does_not_accept_derived_authority(field):
    with pytest.raises(TypeError, match="unexpected keyword"):
        Q.synthetic_from_inputs(**inputs(), **{field: {}})


def test_actual_history_refused_before_any_reconstruction(monkeypatch):
    kw = inputs(); kw["evidence_class"] = "ACTUAL_HISTORY"
    def forbidden(*args, **kwargs):
        raise AssertionError("must not reconstruct history")
    monkeypatch.setattr(V, "panel_targets", forbidden)
    with pytest.raises(ValueError, match="SYNTHETIC"):
        Q.synthetic_from_inputs(**kw)


def test_late_state_publication_cannot_get_a_policy_readout():
    kw = inputs()
    kw["states"].loc[kw["states"].index[0], "slowKnownAt"] = "2030-01-01T00:00:00Z"
    with pytest.raises(ValueError, match="STATE_NOT_KNOWN"):
        Q.synthetic_from_inputs(**kw)


def test_unmatured_support_never_generates_a_definite_readout():
    kw = inputs(); kw["support"]["windowMatured"] = False
    out = Q.synthetic_from_inputs(**kw)
    assert all(r["verdict"] == "INCONCLUSIVE" for r in out["readouts"].values())
    assert all(r["verdict"] == "INCONCLUSIVE" for r in out["reentryContrasts"].values())


@pytest.mark.parametrize("episodes", [None, {}, "", 0])
def test_primitive_entry_preserves_fixed_episode_input_validation(episodes):
    with pytest.raises(ValueError, match="FIXED_EPISODE_SEQUENCE"):
        Q.synthetic_from_inputs(**inputs(), episodes=episodes)
