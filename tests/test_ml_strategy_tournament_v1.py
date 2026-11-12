"""Synthetic tests for research/ml_strategy_tournament_v1 (no market data)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

HERE = Path(__file__).resolve().parents[1] / "research" / "ml_strategy_tournament_v1"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    import sys
    sys.path.insert(0, str(HERE))
    spec.loader.exec_module(mod)
    return mod


T = _load("tournament")


def _sessions(n=400, start="2020-01-01"):
    return pd.bdate_range(start, periods=n)


def test_config_counts_match_the_frozen_grid():
    grid = T.grid()
    ml = [g for g in grid if g["family"] != "RULE"]
    assert len(ml) == 141 and len(grid) == 148
    assert len({g["id"] for g in grid}) == len(grid)
    assert len(T.grid_h252()) == 18 + 24


def test_label_enters_after_the_signal_session_and_withholds_a_terminated_exit():
    s = _sessions(20)
    close = pd.Series(np.arange(1, 21, dtype=float), index=s)
    bench = pd.Series(10.0, index=s)
    ex, exd = T.forward_excess(close, bench, s, 3)
    # signal at s[0]: entry s[1] (close 2), exit s[4] (close 5)
    assert ex.iloc[0] == pytest.approx(5 / 2 - 1)
    assert exd.iloc[0] == s[4]
    close2 = close.copy()
    close2.iloc[10:] = np.nan                       # terminated after s[9]
    ex2, exd2 = T.forward_excess(close2, bench, s, 3)
    assert np.isnan(ex2.iloc[7]) and exd2.iloc[7] == s[11]
    assert np.isnan(ex.iloc[-1]) and pd.isna(exd.iloc[-1])


def test_fold_split_never_trains_on_a_label_that_exits_inside_the_fold():
    d = pd.to_datetime(["2019-06-01", "2019-12-20", "2020-01-03", "2020-02-07"])
    df = pd.DataFrame({"date": d, "y126": [0.1, 0.2, 0.3, 0.4],
                       "exit126": pd.to_datetime(["2019-12-01", "2020-06-01", "2020-07-01", "2020-08-01"])})
    train, test = T.fold_split(df, 2020, 126)
    assert list(train.index) == [0]
    assert (train["exit126"] < test["date"].min()).all()


def _frame(dates, n=30, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for i, d in enumerate(dates):
        for j in range(n):
            rows.append({"date": d, "ticker": f"T{j:02d}", "_q": True, "_s": float(j), "y126": (j - n / 2) / 100 + rng.normal(0, .001),
                         "exit126": d + pd.Timedelta(days=10)})
    return pd.DataFrame(rows)


def test_calibration_gate_cannot_see_a_label_that_has_not_matured():
    dates = list(pd.date_range("2020-01-03", periods=30, freq="7D"))
    df = _frame(dates)
    decision = dates[20]
    calib, exits = T.calibration_table(df, "_s", 126)
    w1, _ = T.decide(df[df["date"] == decision], "_s", calib, exits, decision, 126)
    poisoned = df.copy()
    late = poisoned["exit126"] >= decision
    poisoned.loc[late, "y126"] = -poisoned.loc[late, "y126"] * 50   # future labels inverted
    calib2, exits2 = T.calibration_table(poisoned, "_s", 126)
    w2, _ = T.decide(poisoned[poisoned["date"] == decision], "_s", calib2, exits2, decision, 126)
    assert w1 == w2 and len(w1) == 5


def test_no_name_passes_when_the_past_top_bucket_lost_money():
    dates = list(pd.date_range("2020-01-03", periods=30, freq="7D"))
    df = _frame(dates)
    df["y126"] = -df["y126"]
    calib, exits = T.calibration_table(df, "_s", 126)
    w, info = T.decide(df[df["date"] == dates[25]], "_s", calib, exits, dates[25], 126)
    assert w == {} and info["picked"] == 0


def _book(close_a, bench, vol_a=None):
    s = close_a.index
    prices = {"AAA.KS": pd.DataFrame({"Close": close_a, "Volume": vol_a if vol_a is not None else pd.Series(1.0, index=s)}),
              T.BENCH: pd.DataFrame({"Close": bench, "Volume": pd.Series(1.0, index=s)})}
    return T.PriceBook(prices, ["AAA.KS", T.BENCH], s, bench)


def test_nav_matches_a_hand_computation_with_costs():
    s = _sessions(10)
    a = pd.Series([100, 100, 110, 121, 121, 121, 121, 121, 121, 121], index=s, dtype=float)
    b = pd.Series([100, 100, 100, 100, 100, 100, 100, 100, 100, 100], index=s, dtype=float)
    book = _book(a, b)
    sim = T.simulate(book, {s[1]: {"AAA.KS": 0.2}, s[4]: {}}, s[0], s[-1], record=True)
    buy = 0.2 * T.stock_cost_bps(s[1], "buy") / 1e4 + 0.2 * T.etf_cost_bps() / 1e4
    nav1 = 1 - buy
    stock = 0.2 * nav1 * 1.21
    etf = 0.8 * nav1
    nav3 = stock + etf
    w = stock / nav3
    sell = w * T.stock_cost_bps(s[4], "sell") / 1e4 + w * T.etf_cost_bps() / 1e4
    assert sim["nav"].iloc[-1] == pytest.approx(nav3 * (1 - sell), rel=1e-12)
    # contributions add up to the NAV path (one-day returns)
    r = sim["nav"].pct_change().fillna(0)
    total = sum(sim["contrib"].values())
    no_trade = [i for i, d in enumerate(s) if d not in (s[1], s[4])]
    assert np.allclose(r.iloc[no_trade], total[no_trade], atol=1e-12)


def test_suspended_name_cannot_be_sold_and_terminal_bounds_bracket():
    s = _sessions(30)
    a = pd.Series(100.0, index=s)
    a.iloc[3:6] = 120.0
    a.iloc[6:] = np.nan                                  # last close s[5], terminated
    vol = pd.Series(1.0, index=s)
    vol.iloc[4:6] = 0.0                                  # suspended before delisting
    b = pd.Series(100.0, index=s)
    book = _book(a, b, vol)
    assert "AAA.KS" in book.terminal
    sched = {s[1]: {"AAA.KS": 0.2}, s[4]: {}}            # sell attempt during suspension
    lo = T.simulate(book, sched, s[0], s[-1], "ZERO", record=True)
    hi = T.simulate(book, sched, s[0], s[-1], "LAST")
    assert lo["trades"][-1]["date"] == str(s[1].date())  # no sell executed on s[4]
    assert lo["nav"].iloc[-1] < 0.85 < hi["nav"].iloc[-1]
    assert lo["terminalHits"] and lo["terminalHits"][0][1] == "AAA.KS"


def test_independent_nav_from_recorded_holdings_reproduces_the_engine():
    rng = np.random.default_rng(3)
    s = _sessions(120)
    a = pd.Series(100 * np.cumprod(1 + rng.normal(0, .02, len(s))), index=s)
    b = pd.Series(100 * np.cumprod(1 + rng.normal(0, .01, len(s))), index=s)
    book = _book(a, b)
    sched = {s[i]: ({"AAA.KS": 0.2} if (i // 20) % 2 == 0 else {}) for i in range(1, 120, 20)}
    sim = T.simulate(book, sched, s[0], s[-1], record=True)
    # independent: weights drift with prices between trades, costs from recorded trades
    nav, w_a, w_e = 1.0, 0.0, 1.0
    trades = {}
    for t in sim["trades"]:
        trades.setdefault(t["date"], []).append(t)
    for i, d in enumerate(s):
        if i:
            ra, rb = a.iloc[i] / a.iloc[i - 1] - 1, b.iloc[i] / b.iloc[i - 1] - 1
            va, ve = w_a * nav * (1 + ra), w_e * nav * (1 + rb)
            nav = va + ve
            w_a, w_e = va / nav, ve / nav
        for t in trades.get(str(d.date()), []):
            dw = t["toWeight"] - w_a          # recorded fromWeight is rounded; the live weight is exact
            cost = abs(dw) * (T.stock_cost_bps(d, t["side"]) + T.etf_cost_bps()) / 1e4
            nav *= 1 - cost
            w_a, w_e = t["toWeight"], 1 - t["toWeight"]
    assert nav == pytest.approx(sim["nav"].iloc[-1], rel=1e-10)


def test_bok_rate_is_the_latest_announced_rate():
    s = pd.to_datetime(["2020-01-02", "2020-03-16", "2020-03-17", "2020-06-01"])
    ev = [{"date": "2019-10-16", "annualRatePct": 1.25}, {"date": "2020-03-17", "annualRatePct": 0.75}]
    r = T.bok_rate_series(pd.DatetimeIndex(s), ev)
    assert list(r) == [1.25, 1.25, 0.75, 0.75]


def test_results_carry_the_exploratory_label_when_present():
    for p in (HERE / "results").glob("*.json"):
        doc = json.loads(p.read_text())
        if isinstance(doc, dict) and "evidenceClass" in doc:
            assert doc["evidenceClass"] == "EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY"


def test_vectorised_spearman_matches_scipy():
    from scipy.stats import spearmanr
    rng = np.random.default_rng(5)
    rows = []
    for d in pd.date_range("2020-01-03", periods=4, freq="7D"):
        x = rng.normal(size=40)
        y = x * 0.3 + rng.normal(size=40)
        x[3] = x[4]                                   # a tie
        rows += [{"date": d, "s": a, "y": b} for a, b in zip(x, y)]
    f = pd.DataFrame(rows)
    got = T.spearman_by_date(f, "s", "y")
    for d, g in f.groupby("date"):
        assert got[d] == pytest.approx(spearmanr(g["s"], g["y"]).statistic, abs=1e-12)


def test_a_name_that_cannot_be_sold_shrinks_new_buys_instead_of_levering_the_book():
    s = _sessions(12)
    a = pd.Series(100.0, index=s)
    b = pd.Series(100.0, index=s)
    vol = pd.Series(1.0, index=s)
    vol.iloc[5:8] = 0.0                                           # AAA suspended on the second rebalance
    s2 = pd.Series(50.0, index=s)
    prices = {"AAA.KS": pd.DataFrame({"Close": a, "Volume": vol}), "BBB.KS": pd.DataFrame({"Close": s2, "Volume": 1.0}),
              "CCC.KS": pd.DataFrame({"Close": s2, "Volume": 1.0}), T.BENCH: pd.DataFrame({"Close": b, "Volume": 1.0})}
    book = T.PriceBook(prices, ["AAA.KS", "BBB.KS", "CCC.KS", T.BENCH], s, b)
    sched = {s[1]: {"AAA.KS": 0.6}, s[6]: {"BBB.KS": 0.5, "CCC.KS": 0.5}}
    sim = T.simulate(book, sched, s[0], s[-1], record=True)
    last = sim["holdings"][-1]
    assert last["weights"]["AAA.KS"] == pytest.approx(0.6, abs=1e-3)
    assert sum(last["weights"].values()) <= 1 + 1e-9 and last["etf"] >= -1e-9
    assert last["weights"]["BBB.KS"] == pytest.approx(0.2, abs=1e-3)
