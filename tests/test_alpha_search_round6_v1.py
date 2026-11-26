import numpy as np
import pandas as pd

from research.alpha_search_round6_v1 import common as CM
from research.alpha_search_round6_v1 import us as U


def test_holm_steps_down_and_treats_missing_as_one():
    adj = CM.holm({"a": 0.01, "b": 0.04, "c": None})
    assert adj["a"] == 0.03 and adj["b"] == 0.08 and adj["c"] == 1.0


def test_boot_p_is_small_for_a_clearly_positive_series_and_never_zero():
    r = CM.boot([0.01] * 200, 25, draws=500)
    assert r["pOneSided"] == 1 / 501 and r["ci"][0] > 0
    assert CM.boot([0.01] * 30, 25)["pOneSided"] is None


def test_judge_needs_every_check_and_separates_significance():
    c = {"full": 0.01, "halves": [0.01, 0.02], "l26Excess": 0.01, "l26Mdd": -0.30, "etfMdd": -0.30, "exSemiLed": "NA"}
    assert CM.judge(c, 0.01)["verdict"] == "ALPHA_CANDIDATE"
    assert CM.judge(c, 0.20)["verdict"] == "DIRECTIONAL_ONLY"
    assert CM.judge({**c, "l26Mdd": -0.34}, 0.01)["verdict"] == "NOT_SUPPORTED"      # deeper than 1.10 x ETF
    assert CM.judge({**c, "halves": [-0.01, 0.02]}, 0.01)["verdict"] == "NOT_SUPPORTED"


def test_top5_neutral_keeps_capital_and_adds_the_index_share_of_the_largest_names():
    x = pd.DataFrame({"marketCap": [50, 20, 10, 8, 6, 4, 2]}, index=list("ABCDEFG"))
    w, s = U.top5_neutral(x, {"G": 0.5, "SPY": 0.5})
    assert abs(sum(w.values()) - 1) < 1e-12
    assert abs(s - 94 / 100) < 1e-12
    assert abs(w["A"] - 0.5) < 1e-12 and abs(w["G"] - 0.5 * 0.06) < 1e-12


def test_sector_dispersion_ignores_sectors_with_fewer_than_three_names():
    x = pd.DataFrame({"sector": ["a"] * 3 + ["b"] * 3 + ["c"] * 2, "momentum252": [0.1] * 3 + [0.3] * 3 + [9.0] * 2})
    assert abs(U.dispersion(x) - float(np.std([0.1, 0.3], ddof=1))) < 1e-12
