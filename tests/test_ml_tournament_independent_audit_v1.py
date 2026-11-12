"""Counterexamples against the frozen submission. No real model fitting."""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "audited_tournament", ROOT / "research/ml_strategy_tournament_v1/tournament.py"
)
T = importlib.util.module_from_spec(spec)
spec.loader.exec_module(T)


def test_future_missingness_changes_feature_membership():
    past = pd.DataFrame({"A01_return1d": [np.nan] * 10})
    future = pd.DataFrame({"A01_return1d": [1.0] * 10})
    before, _ = T.feature_layers(past)
    after, _ = T.feature_layers(pd.concat([past, future]))
    assert before["company"] == []
    assert after["company"] == ["A01_return1d"]


def test_locked_stock_units_change_without_an_executable_trade():
    days = pd.bdate_range("2020-01-01", periods=12)
    prices = {
        t: pd.DataFrame({"Close": 100.0, "Volume": 1.0}, index=days)
        for t in [T.BENCH, "AAA.KS", "BBB.KS"]
    }
    prices["AAA.KS"].loc[days[1], "Volume"] = 0.0
    book = T.PriceBook(prices, list(prices), days, prices[T.BENCH]["Close"])
    out = T.simulate(book, {days[0]: {"AAA.KS": .5}, days[1]: {"BBB.KS": .5}},
                     days[0], days[-1], record=True)
    q_before = out["holdings"][0]["weights"]["AAA.KS"] * out["nav"].iloc[0] / 100
    q_after = out["holdings"][1]["weights"]["AAA.KS"] * out["nav"].iloc[1] / 100
    assert q_after < q_before  # cost is silently charged to the untradable shares
    assert not any(t["ticker"] == "AAA.KS" and t["date"] == str(days[1].date())
                   for t in out["trades"])


def test_recorded_cost_weights_are_not_self_financing_trade_notionals():
    days = pd.bdate_range("2020-01-01", periods=12)
    p = {t: pd.DataFrame({"Close": 100., "Volume": 1.}, index=days)
         for t in [T.BENCH, "AAA.KS"]}
    book = T.PriceBook(p, list(p), days, p[T.BENCH]["Close"])
    out = T.simulate(book, {days[0]: {"AAA.KS": 1.}}, days[0], days[-1], record=True)
    charged = 1 - out["nav"].iloc[0]
    exact_fee = out["nav"].iloc[0] * .00055 + .00025
    assert charged - exact_fee == pytest.approx(4.4e-7)


@pytest.mark.parametrize("h", [126, 252])
def test_horizon_calendar_and_strict_maturity(h):
    days = pd.bdate_range("2018-01-01", periods=800)
    c = pd.Series(np.arange(1., 801.), index=days)
    b = pd.Series(100., index=days)
    label, exit_date = T.forward_excess(c, b, days, h)
    assert exit_date.iloc[0] == days[h + 1]
    assert label.iloc[0] == pytest.approx(c.iloc[h + 1] / c.iloc[1] - 1)
    df = pd.DataFrame({"date": days, f"y{h}": label, f"exit{h}": exit_date})
    train, test = T.fold_split(df, 2020, h)
    assert (train[f"exit{h}"] < test["date"].min()).all()


def test_terminal_last_price_is_not_a_valid_upper_bound_on_consideration():
    # A merger can pay more than the last quote: zero/last are scenarios, not bounds.
    last_close, cash_consideration = 100., 120.
    assert cash_consideration > last_close


def test_independent_cash_calculator_conserves_actual_notionals():
    import sys
    audit = ROOT / 'research/ml_strategy_tournament_independent_audit_v1'
    sys.path.insert(0, str(audit))
    from check_cash import exact_replay
    days = pd.bdate_range('2016-01-11', periods=12)
    c = pd.DataFrame({T.BENCH: 100., 'AAA.KS': [100.] + [110.] * 11}, index=days)
    v = pd.DataFrame(1., index=days, columns=c.columns)
    nav, residual = exact_replay(c, v, [{'date': '2016-01-11', 'weights': {'AAA.KS': 1.}, 'etf': 0.}])
    # Sell 1 ETF notional at 2.5bp; buy net stock notional at 5.5bp.
    initial_net = (1 - .00025) / (1 + .00055)
    assert nav.iloc[0] == pytest.approx(initial_net)
    assert nav.iloc[-1] == pytest.approx(initial_net * 1.1)
    assert residual < 1e-13
