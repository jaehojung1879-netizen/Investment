import numpy as np
import pandas as pd
import pytest

from pipeline.us_decision_pilot import simulate
from research.kr_us_exposure_preserving_v1.engine import distance, exposure, redistribute
from research.kr_us_exposure_preserving_v1.nav import us_account


def test_funding_preserves_each_bucket_when_capacity_exists():
    base = {"A": .25, "B": .20, "M": .35, "C": .20}
    groups = {"A": "tech", "B": "tech", "M": "tech", "C": "energy", "D": "energy"}
    stock = {"A": .05, "M": .05, "D": .10}
    result, donor, deficit = redistribute(base, stock, groups, {"M"})
    assert deficit == 0
    assert sum(donor.values()) == pytest.approx(.2)
    assert sum(result.values()) == pytest.approx(1)
    before, after = exposure(base, groups, {"M"}), exposure(result, groups, {"M"})
    assert distance(before[0], after[0]) < 1e-12
    assert before[1] == pytest.approx(after[1])
    assert result["D"] == pytest.approx(.10)
    assert result["A"] < .30  # some of A's baseline weight is a donor


def test_funding_keeps_budget_with_absent_cell():
    base = {"A": .6, "B": .4}
    groups = {"A": "tech", "B": "energy", "M": "tech"}
    aligned, donor, deficit = redistribute(base, {"M": .2}, groups, {"M"})
    assert deficit == pytest.approx(.2)
    assert donor == pytest.approx({"A": .12, "B": .08})
    assert aligned == pytest.approx({"A": .48, "B": .32, "M": .2})


def test_fast_nav_matches_original_holds_cash_and_final_rebalance():
    days = pd.date_range("2024-01-01", periods=14)
    prices = pd.DataFrame({"A": np.linspace(20., 24., len(days)), "SPY": np.linspace(120., 116., len(days))}, index=days)
    orders = {days[1]: {"SPY": 1.}, days[3]: {"SPY": .4, "A": .4}, days[-1]: {"A": 1.}}
    out, _ = us_account(prices, orders)
    expected = simulate(prices, orders)
    assert np.allclose(out, expected[out.columns], atol=1e-13, rtol=1e-13)
    prices.loc[days[6], "A"] = np.nan
    with pytest.raises(ValueError, match="UNRESOLVED_HELD_OBSERVATION"):
        us_account(prices, orders)
