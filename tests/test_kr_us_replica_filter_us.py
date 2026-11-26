import numpy as np
import pandas as pd
import pytest

from research.kr_us_replica_filter_v1 import us


def test_spy_bridge_changes_one_book_condition_at_a_time():
    base = {"AAPL": .25, "MSFT": .10, "A": .15, "B": .25, "E": .25}
    disclosed = {"AAPL": .12, "MSFT": .18, "A": .20, "B": .30, "D": .10}
    sectors = {"AAPL": "Tech", "MSFT": "Tech", "A": "Tech", "B": "Financial",
               "D": "Financial", "E": "Financial"}
    r = pd.Series({"AAPL": .20, "MSFT": .50, "A": .15, "B": -.10, "E": .12, "D": -.05})
    b = us.bridge_books(base, disclosed, sectors)
    assert set(b["BC"]) == {"AAPL", "MSFT", "A", "B"}
    assert set(b["LS"]) == (set(b["BC"]) | {"D"})
    assert all(sum(w.values()) == pytest.approx(1.) for w in b.values())
    assert b["MC"]["AAPL"]/b["MC"]["MSFT"] == pytest.approx(.25/.10)
    assert b["MC"]["AAPL"]+b["MC"]["MSFT"] == pytest.approx(.30/.80)
    assert b["MSector"]["AAPL"]+b["MSector"]["MSFT"]+b["MSector"]["A"] == pytest.approx(.50/.80)
    a = us.bridge_values(r, .22, b)
    assert a["proxyNetExcess"] == pytest.approx(sum(a[c] for c in us.COMPONENTS))
    assert a["sectorAndMegaWeight"] == pytest.approx(a["sectorWeightOnly"]+a["megaWithinSectorWeight"])


def test_strict_endpoints_stay_missing_and_timing_uses_sessions():
    index = pd.bdate_range("2026-01-02", periods=7)
    prices = pd.DataFrame({"A": [1., 2., 4., np.nan, 16., 32., 64.],
                           "ETF": [1., 2., 3., 4., 5., 6., 7.]}, index=index)
    r, e = us.endpoint_returns(prices, index[[0, 1, 5]], 2)
    assert e.loc[index[0], "entry"] == index[1] and e.loc[index[0], "exit"] == index[3]
    assert np.isnan(r.loc[index[0], "A"])
    assert np.isnan(us.weighted(r.loc[index[0]], {"A": .3, "ETF": .7}))
    assert r.loc[index[1], "A"] == pytest.approx(16./4.-1)
    assert pd.isna(e.loc[index[5], "exit"]) and r.loc[index[5]].isna().all()


def test_identical_endpoint_costs_are_affine_in_excess():
    gross = pd.Series({"A": .20, "B": -.15})
    w = {"A": .25, "B": .75}
    gross_gap = us.weighted(gross, w)-.02
    net_gap = us.weighted(us.ev.net(gross), w)-us.ev.net(.02)
    assert net_gap == pytest.approx(us.NET_FACTOR*gross_gap)
