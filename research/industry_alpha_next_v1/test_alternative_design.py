"""The alternative design's construction on invented data; no market data is read."""
import json

import numpy as np
import pandas as pd
import pytest

from . import alternative_design as A
from . import inference_calibration as C

SCREEN = json.loads((C.HERE / "alternative-design-screen.json").read_text())


def test_matched_monthly_ic_reproduces_the_frozen_kappa():
    w = C.load_protocol()["world"]
    for h in (126, 252):
        ic21 = A.matched_monthly_ic(0.10, h, w["plantedRho"])
        assert C.effect_kappa(ic21, 21, 0.01, w["plantedRho"]) == pytest.approx(C.effect_kappa(0.10, h, 0.01, w["plantedRho"]))
    assert A.matched_monthly_ic(0, 126, 0.95) == 0.0


def test_centred_rank_weights_are_dollar_neutral_with_gross_one():
    w = A.centred_rank_weights(np.array([3.0, 1.0, 2.0, 5.0]))
    assert w.sum() == pytest.approx(0) and np.abs(w).sum() == pytest.approx(1) and w[3] > w[2] > w[1]


def test_residual_signal_is_orthogonal_to_momentum_within_the_date():
    rng = np.random.default_rng(0)
    g = pd.DataFrame({"x": rng.normal(size=12), "REL_MOM_126": rng.normal(size=12)})
    g["x"] += 2 * g["REL_MOM_126"]
    res = A.residual_signal(g, "x", ["REL_MOM_126"])
    assert abs(np.corrcoef(res, g["REL_MOM_126"])[0, 1]) < 1e-9


def _frame(months=24, industries=10, signal=0.0, seed=1):
    rng = np.random.default_rng(seed)
    dates = [str(d.date()) for d in pd.date_range("2015-01-31", periods=months, freq="ME")]
    rows = []
    for d in dates:
        x = rng.normal(size=industries)
        for i in range(industries):
            rows.append({"date": d, "industry": f"G{i}", "S": x[i], "REL_MOM_126": rng.normal(),
                         "cwRelative": signal * x[i] + rng.normal(), "cwStatus": "MATURED"})
    return pd.DataFrame(rows)


def test_every_month_enters_the_calendar_time_series_once_and_no_fit_is_used():
    x = A.calendar_time_series(_frame(), "S", ["REL_MOM_126"], 6)
    assert len(x) == 24 - 5
    planted = A.calendar_time_series(_frame(months=120, signal=0.5), "S", ["REL_MOM_126"], 1)
    assert A.tests(planted)["nwReject"]


def test_a_future_return_cannot_change_an_earlier_month():
    f = _frame()
    base = A.calendar_time_series(f, "S", ["REL_MOM_126"], 6)
    g = f.copy()
    g.loc[g["date"] == g["date"].max(), "cwRelative"] = 1e6
    moved = A.calendar_time_series(g, "S", ["REL_MOM_126"], 6)
    assert np.allclose(base[:-1], moved[:-1]) and base[-1] != moved[-1]


def test_committed_screen_is_synthetic_and_labelled_as_a_screen():
    assert SCREEN["historicalOutcomesRead"] == 0
    assert SCREEN["evidenceClass"] == "SYNTHETIC_DESIGN_SCREEN_NOT_A_FORMAL_CALIBRATION"
    assert len(SCREEN["cells"]) == 12 and all(c["replicates"] == 400 for c in SCREEN["cells"].values())
