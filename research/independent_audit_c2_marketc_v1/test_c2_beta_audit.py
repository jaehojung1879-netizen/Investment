import json

import numpy as np
import pytest

from research.independent_audit_c2_marketc_v1 import c2_beta_audit as A


def _src(beta=0.6, alpha=5.0):
    p = [0.1, -6.6, -0.1, 10.2, 27.1, -17.3, 14.4, 35.5, 3.0, -24.2, 24.8, -9.4, 94.2, 74.4]
    rows = [{"year": str(2013 + i), "c2ReturnPct": alpha + beta * x, "passiveReturnPct": x,
             "isWindowBookendYear": i in (0, 13)} for i, x in enumerate(p)]
    return {"publishedCalendarContext": {"rows": rows, "allYears": {"DOWN": {"wins": 5}}},
            "observed": {"C2": {"averageBenchmarkWeightPct": 40.0, "annualizedCostDragPct": 1.5}},
            "exposureBound": {"absoluteBetaUpperBound": 0.76},
            "costBounds": [{"multiplier": 3, "edgeUpperPp": -1.47}]}


def test_recovers_beta_and_jensen_alpha_exactly_on_noiseless_rows():
    out = A.audit(_src(beta=0.6, alpha=5.0), rf=2.0)
    f = out["annualRowRegression_C2_on_069500"]["ALL_14_ROWS"]
    assert f["beta"] == pytest.approx(0.6)
    assert f["intercept"] == pytest.approx(5.0)
    assert f["jensenAlphaPpPerYear"] == pytest.approx(5.0 - 0.4 * 2.0)
    assert out["c2StockLegBetaImplied"]["stockLegBetaIfEtfBetaIsOne"] == pytest.approx((0.6 - 0.4) / 0.6)


def test_unit_beta_zero_alpha_gives_no_down_year_mechanics():
    out = A.audit(_src(beta=1.0, alpha=0.0), rf=2.0)
    assert np.allclose(out["downYearReading"]["mechanicalExcessFromBetaAloneInDownYearsPp"], 0.0)


def test_committed_audit_matches_pinned_source():
    committed = json.loads(A.OUT.read_text())
    try:
        src, digest = A.load_source()
    except Exception:  # shallow CI clone may not hold the #286 commit
        pytest.skip("PR #286 commit not present in this clone")
    assert digest == committed["source"]["sha256"]
    fresh = A.audit(src, committed["riskFreeProxy"]["meanPctPerYear2013_2026"])
    for name, fit in committed["annualRowRegression_C2_on_069500"].items():
        assert fresh["annualRowRegression_C2_on_069500"][name] == pytest.approx(fit)
