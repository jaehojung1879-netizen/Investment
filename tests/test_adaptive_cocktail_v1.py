"""Synthetic tests for research/adaptive_cocktail_v1 (no market data)."""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

HERE = Path(__file__).resolve().parents[1] / "research" / "adaptive_cocktail_v1"
sys.path.insert(0, str(HERE))
_spec = importlib.util.spec_from_file_location("cocktail", HERE / "cocktail.py")
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)


def _px(closes, volumes=None, rf=0.0):
    s = closes.index
    vols = volumes if volumes is not None else pd.DataFrame(1.0, index=s, columns=closes.columns)
    return C.Prices(closes, vols, s, pd.Series(rf, index=s))


def test_visibility_respects_the_calendar_lag():
    obs = pd.Series([1.0, 2.0, 3.0], index=pd.to_datetime(["2020-01-01", "2020-01-06", "2020-01-10"]))
    kr = pd.DatetimeIndex(pd.to_datetime(["2020-01-06", "2020-01-09", "2020-01-10", "2020-01-14"]))
    v = C.visible(obs, kr, 4)
    # D - 4 days: 01-02 -> 1.0; 01-05 -> 1.0; 01-06 -> 2.0; 01-10 -> 3.0
    assert list(v) == [1.0, 1.0, 2.0, 3.0]


def test_future_observation_cannot_change_an_earlier_state():
    kr = pd.bdate_range("2020-01-01", periods=300)
    a = pd.Series(np.random.default_rng(0).normal(size=300), index=kr)
    b = pd.Series(np.random.default_rng(1).normal(size=300), index=kr)
    c1 = C.lagged_rolling_corr(a, b, 126, 8, kr)
    b2 = b.copy()
    b2.iloc[250:] = 99.0                                   # poison the future
    c2 = C.lagged_rolling_corr(a, b2, 126, 8, kr)
    cutoff = kr[250] + pd.Timedelta(days=8)
    keep = kr < cutoff
    assert np.allclose(c1[keep].dropna(), c2[keep].dropna())


def test_engine_is_self_financing_and_charges_cost_on_traded_value():
    s = pd.bdate_range("2021-01-04", periods=6)
    closes = pd.DataFrame({"AAA.KS": [100, 100, 110, 110, 110, 110.0], C.ETF: [100.0] * 6}, index=s)
    px = _px(closes)
    sim = C.simulate(px, {s[1]: {"AAA.KS": 0.4, C.ETF: 0.6}}, s[0], s[-1], record=True)
    buy_rate = C.cost_rate("AAA.KS", "buy", s[1])
    etf_rate = C.cost_rate(C.ETF, "sell", s[1])
    # NAV_post solves N = 1 - 0.4 N b - (1 - 0.6 N) e
    n_post = (1 - etf_rate) / (1 + 0.4 * buy_rate - 0.6 * etf_rate)
    assert sim["nav"].iloc[1] == pytest.approx(n_post, rel=1e-12)
    assert sim["nav"].iloc[-1] == pytest.approx(n_post * (0.4 * 1.1 + 0.6), rel=1e-12)


def test_a_name_that_cannot_trade_keeps_its_units():
    s = pd.bdate_range("2021-01-04", periods=8)
    closes = pd.DataFrame({"AAA.KS": [100.0] * 8, "BBB.KS": [50.0] * 8, C.ETF: [100.0] * 8}, index=s)
    vol = pd.DataFrame(1.0, index=s, columns=closes.columns)
    vol.loc[s[4], "AAA.KS"] = 0.0                          # suspended on the second rebalance
    px = _px(closes, vol)
    sim = C.simulate(px, {s[1]: {"AAA.KS": 0.5, C.ETF: 0.5}, s[4]: {"BBB.KS": 1.0}}, s[0], s[-1], record=True)
    h1, h2 = sim["holdings"]
    assert h2["weights"]["AAA.KS"] == pytest.approx(h1["weights"]["AAA.KS"] * sim["nav"].iloc[1] / sim["nav"].iloc[4], rel=1e-5)   # holdings are recorded to 1e-6
    assert sum(h2["weights"].values()) == pytest.approx(1.0, abs=1e-6)
    assert all(v >= -1e-12 for v in h2["weights"].values())


def test_terminal_write_off_and_last_close_alternative():
    s = pd.bdate_range("2021-01-04", periods=20)
    a = pd.Series(100.0, index=s)
    a.iloc[5:] = np.nan
    closes = pd.DataFrame({"AAA.KS": a, C.ETF: 100.0}, index=s)
    px = _px(closes)
    sched = {s[1]: {"AAA.KS": 0.2, C.ETF: 0.8}}
    lo = C.simulate(px, sched, s[0], s[-1])
    hi = C.simulate(px, sched, s[0], s[-1], terminal_mode="LAST")
    assert lo["terminalHits"] and lo["nav"].iloc[-1] == pytest.approx(0.8 * hi["nav"].iloc[-1], rel=1e-3)


def test_cash_accrues_the_rate():
    s = pd.bdate_range("2021-01-04", periods=4)
    closes = pd.DataFrame({C.ETF: [100.0] * 4}, index=s)
    px = _px(closes, rf=0.001)
    sim = C.simulate(px, {s[0]: {C.CASH: 1.0}}, s[0], s[-1])
    post = sim["nav"].iloc[0]
    assert sim["nav"].iloc[-1] == pytest.approx(post * 1.001 ** 3, rel=1e-12)


def test_combined_book_nets_overlapping_names():
    books = {"S1_INDUSTRY_MOMENTUM": {"AAA.KS": 0.2, "BBB.KS": 0.8}, "S3_FOUR_FACTOR": {"AAA.KS": 0.2, C.ETF: 0.8}, "S0_ETF": {C.ETF: 1.0}}
    out = C.combine(books, {"S1_INDUSTRY_MOMENTUM": 0.5, "S3_FOUR_FACTOR": 0.25, "S0_ETF": 0.25})
    assert out["AAA.KS"] == pytest.approx(0.15) and out[C.ETF] == pytest.approx(0.45) and sum(out.values()) == pytest.approx(1.0)


def test_learned_weights_default_to_etf_when_uncertain():
    w, edges = C.learned_weights({"S1_INDUSTRY_MOMENTUM": 0.02}, {"S1_INDUSTRY_MOMENTUM": 0.05}, 0.004)
    assert w == {"S0_ETF": 1.0} and edges == {}
    w, _ = C.learned_weights({"S1_INDUSTRY_MOMENTUM": 0.08}, {"S1_INDUSTRY_MOMENTUM": 0.005}, 0.004)
    assert 0.99 <= w["S1_INDUSTRY_MOMENTUM"] <= 1.0


def test_ridge_standard_error_shrinks_with_more_data():
    rng = np.random.default_rng(2)
    X = rng.normal(size=(400, 3))
    y = X @ np.array([0.5, 0.0, 0.0]) + rng.normal(size=400)
    _, se_big = C.ridge_fit_predict(X, y, np.array([1.0, 0, 0]))
    _, se_small = C.ridge_fit_predict(X[:40], y[:40], np.array([1.0, 0, 0]))
    assert se_big < se_small


def test_newey_west_and_by_adjustment():
    rng = np.random.default_rng(4)
    x = rng.normal(size=200)
    y = 0.5 * x + rng.normal(size=200)
    res = C.newey_west_slope(x, y, 3)
    assert res["slope"] == pytest.approx(0.5, abs=0.2) and res["p"] < 0.01
    adj = C.by_adjust([0.01, 0.02, 0.5])
    assert all(a >= p for a, p in zip(adj, [0.01, 0.02, 0.5])) and max(adj) <= 1.0


def test_config_freezes_choice_set_without_the_rejected_xgb():
    cfg = json.loads((HERE / "config.json").read_text())
    assert "SX_XGB_SENSITIVITY" not in cfg["sleeves"]["choiceSet"]
    assert "S4_RISK_MANAGED_ETF" not in cfg["sleeves"]["choiceSet"]
    assert cfg["timing"]["lagCalendarDays"]["FRED_DAILY_MARKET"] == 4 and cfg["timing"]["lagCalendarDays"]["FRED_H10_WEEKLY"] == 8
    assert math.isclose(len(C.ALL_STATES), 19)
