"""Synthetic economic/causal checks, never production outcomes."""
from itertools import combinations
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from research.kr_s2_rank_ladder_v1 import run as L


def test_prefix_keeps_frozen_tie_break_and_records_shortfall():
    d = pd.Timestamp("2020-01-03")
    g = pd.DataFrame({"ticker": ["BBB", "AAA", "CCC", "DDD"], "industry": ["X"] * 4,
                      "_q": [True, True, True, False], "b08Confirmed": [1] * 4,
                      L.RC.SCORE: [.8, .8, .6, .99], "_mcap": [2., 1., 3., 4.]})
    original = L.C.sleeve_book("S2_VALUE_CONFIRMED", g)[0]
    base = {"dates": [d], "s2": {d: original}, "eligible": {d: ["AAA", "BBB", "CCC"]}}
    books, random, _, audit, ranked = L.build(SimpleNamespace(by={d: g}), base)
    assert books["N1"][d] == {"AAA": .2, L.M.ETF: .8}
    assert books["N5"][d] == books["N3"][d]
    assert list(ranked.ticker) == ["AAA", "BBB", "CCC"]
    assert audit.loc[audit.requested == 5, "shortfall"].item()
    for k in range(6):
        own = books[f"N{k}"][d]
        for p in range(L.PATHS):
            control = random[f"R{p}_{k}"][d]
            assert control.get(L.M.ETF, 0) == own.get(L.M.ETF, 0)
            assert len(control) == len(own)
            assert sum(control.values()) == pytest.approx(1.)
    base["s2"][d] = {L.M.ETF: 1.}
    with pytest.raises(AssertionError, match="CACHE_DISAGREES"):
        L.build(SimpleNamespace(by={d: g}), base)


def test_linear_expected_control_is_exact_without_replacement():
    returns = np.array([.1, -.2, .4, .05])
    etf, k = .08, 3
    exact = np.mean([.2 * returns[list(z)].sum() + (1 - .2*k) * etf for z in combinations(range(4), k)])
    expected = .2*k*returns.mean() + (1 - .2*k) * etf
    assert exact == pytest.approx(expected)


def test_costed_adjacent_contribution_is_point_two_times_stock_minus_etf():
    e, x = pd.to_datetime(["2024-01-02", "2024-07-02"])
    cl = pd.DataFrame({"AAA": [100., 120.], L.M.ETF: [100., 110.]}, index=[e, x])
    a, etf = L.asset_return(cl, "AAA", e, x), L.asset_return(cl, L.M.ETF, e, x)
    n0 = etf[1]
    n1 = .2*a[1] + .8*etf[1]
    assert n1 - n0 == pytest.approx(.2 * (a[1] - etf[1]))
    assert a[2] > etf[2]  # Korean stock sell tax, ETF exemption
    cl.loc[x, "AAA"] = np.nan
    assert L.asset_return(cl, "AAA", e, x) is None


def test_missing_stat_is_none_and_masked_blocks_keep_original_axis():
    assert L.stats([np.nan] * 10)["mean"] is None
    v = np.arange(120.)
    mask = np.arange(120) % 3 == 0
    result = L.stats(v, mask, block=5)
    assert result["n"] == 40
    assert result["mean"] == pytest.approx(v[mask].mean())
    assert result["ci"] != L.stats(v[mask], block=5)["ci"]


def test_past_only_does_not_use_unmatured_or_same_day_exit(tmp_path):
    dates = pd.date_range("2020-01-03", periods=60, freq="7D")
    # 52 mature rows prefer N1; future rows have huge N5 payoff, still invisible.
    frame = pd.DataFrame({"date": dates, "entry": dates, "exit": dates + pd.Timedelta(days=1), "mainValid": True})
    for k in range(6):
        frame[f"N{k}_net"] = 0. if k != 1 else .1
    frame.loc[52:, "N5_net"] = 100.
    frame.loc[52:, "exit"] = dates[-1] + pd.Timedelta(days=30)
    books = {f"N{k}": {d: {str(k): 1.} for d in dates} for k in range(6)}
    policy = L.past_only({"dates": dates}, {126: frame, 252: frame}, books, tmp_path)
    assert policy[dates[51]] == books["N0"][dates[51]]
    assert policy[dates[52]] == books["N1"][dates[52]]
    assert policy[dates[-1]] == books["N1"][dates[-1]]
