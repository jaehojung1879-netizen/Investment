import numpy as np
import pandas as pd

from research.investment_decision_alpha_v1 import kr_semis_case as KC
from research.investment_decision_alpha_v1 import s1_industry_cycle as S1
from research.investment_decision_alpha_v1 import s2_entry_timing as S2


def _members(rows):
    return pd.DataFrame(rows, columns=["ticker", "capexTTM", "capexTTMPrior"]).set_index("ticker")


def test_industry_keys_pool_small_sic3_into_sic2_and_drop_tiny():
    g = _members([("A", 1, 1), ("B", 1, 1), ("C", 1, 1),          # SIC 3674 x3 -> own SIC3 group
                  ("D", 1, 1), ("E", 1, 1),                       # 3651 x2 + 3663 x1 -> pooled SIC2 "36"
                  ("F", 1, 1),
                  ("G", 1, 1), ("H", 0, 1)])                      # 2810 one valid + one invalid -> dropped
    sic = {"A": "3674", "B": "3674", "C": "3674", "D": "3651", "E": "3652", "F": "3663", "G": "2810", "H": "2810"}
    k = S1.industry_keys(g, sic)
    assert set(k[["A", "B", "C"]]) == {"367"}
    assert set(k[["D", "E", "F"]]) == {"2:36"}
    assert "G" not in k.index and "H" not in k.index


def test_entries_only_names_new_versus_previous_book():
    b = {pd.Timestamp("2020-01-03"): {"X": .2, "Y": .2, "SPY": .6},
         pd.Timestamp("2020-01-10"): {"X": .2, "Z": .2, "SPY": .6},
         pd.Timestamp("2020-01-17"): {"Y": .2, "Z": .2, "SPY": .6}}
    e = S2.entries(b, {"SPY"})
    assert e == [(pd.Timestamp("2020-01-03"), "X"), (pd.Timestamp("2020-01-03"), "Y"),
                 (pd.Timestamp("2020-01-10"), "Z"), (pd.Timestamp("2020-01-17"), "Y")]


def _panel(stock, etf):
    idx = pd.bdate_range("2020-01-01", periods=len(stock))
    return pd.DataFrame({"S": stock, "ETF": etf}, index=idx)


def test_wait_equals_buy_now_without_costs_when_nothing_moves_before_the_announcement():
    n = 40
    stock = np.r_[np.full(10, 100.0), np.linspace(100, 130, n - 10)]
    close = _panel(stock, np.full(n, 50.0))
    df = S2.evaluate([(close.index[0], "S", 1)], close, "ETF", {"S": np.array([5])}, lambda *a: 0.0, 30)
    r = df.iloc[0]
    assert r["waited"] and np.isclose(r["P0"], r["P1"]) and np.isclose(r["P1"], r["P1c"])


def test_waiting_misses_the_pre_announcement_rise_and_pays_the_etf_round_trip():
    n = 40
    stock = np.r_[np.full(2, 100.0), np.full(n - 2, 110.0)]     # jumps before the announcement at position 5
    close = _panel(stock, np.full(n, 50.0))
    cost = lambda t, side, d: 0.001                              # noqa: E731
    df = S2.evaluate([(close.index[0], "S", 1)], close, "ETF", {"S": np.array([5])}, cost, 30)
    r = df.iloc[0]
    assert r["P1"] < r["P0"] and r["P1c"] > r["P1"]


def test_no_announcement_within_window_still_waits_until_the_cap():
    # v2 (Codex audit): whether an announcement will arrive is unknown on the entry day, so the buyer waits
    # until the first reaction day or entry + WAIT_MAX, never "knows" to skip the wait.
    close = _panel(np.linspace(100, 120, 200), np.full(200, 50.0))
    df = S2.evaluate([(close.index[0], "S", 1)], close, "ETF", {"S": np.array([150])}, lambda *a: 0.0, 120)
    r = df.iloc[0]
    assert not r["waited"]                     # no announcement before the cap
    expected = close["S"].iloc[1 + 120] / close["S"].iloc[1 + S2.WAIT_MAX] - 1
    assert np.isclose(r["P1"], expected) and r["P1"] < r["P0"]


def test_turning_points_alternate_and_need_the_full_move():
    px = pd.Series([100, 120, 150, 100, 90, 140, 130, 135], index=pd.bdate_range("2020-01-01", periods=8))
    tp = KC.turning_points(px, 0.30)
    # the series start counts as a trough once the price has risen 30% from it
    assert [t["type"] for t in tp] == ["TROUGH", "PEAK", "TROUGH"]
    assert [t["price"] for t in tp] == [100, 150, 90]


def test_trim_moves_only_the_trimmed_name_and_avoids_its_later_fall():
    from research.investment_decision_alpha_v1 import s3_trim as S3
    px = np.array([[100.0, 100.0], [100.0, 100.0], [200.0, 50.0]])
    spy = np.array([10.0, 10.0, 10.0])
    hold = S3.simulate(px, spy, [0.5, 0.5], {})
    trim_loser = S3.simulate(px, spy, [0.5, 0.5], {1: {1: 1.0}})
    trim_winner = S3.simulate(px, spy, [0.5, 0.5], {1: {0: 1.0}})
    assert trim_loser > hold > trim_winner
    assert np.isfinite(trim_loser)


def test_proportional_control_moves_exactly_the_value_the_signal_trim_moved_on_repeated_trims():
    # v2 (Codex audit): after a first trim the untrimmed path's values no longer describe either book
    from research.investment_decision_alpha_v1 import s3_trim as S3
    px = np.array([[100.0, 100.0, 100.0], [130.0, 80.0, 100.0], [160.0, 60.0, 90.0], [150.0, 70.0, 95.0]])
    spy = np.array([10.0, 10.5, 11.0, 11.5])
    w0 = [0.3, 0.3, 0.3]
    trims = {1: {0: 0.5}, 2: {1: 0.5, 2: 0.5}}
    targets = S3.moved_values(px, w0, trims)
    _, got = S3.simulate_value_matched(px, spy, w0, targets)
    for t in targets:
        assert np.isclose(got[t], targets[t], rtol=0, atol=1e-12)
    # the version-1 rule (fractions from the untrimmed path) does not match at the second check
    vals = px[2] * np.asarray(w0) / px[0]
    v1_fraction = (0.5 * vals[1] + 0.5 * vals[2]) / vals.sum()
    units_after_first = (1 - S3.EV.BUY) * np.asarray(w0) / px[0] * (1 - targets[1] / ((1 - S3.EV.BUY) * (np.asarray(w0) / px[0] * px[1]).sum()))
    v1_moved = v1_fraction * float((units_after_first * px[2]).sum())
    assert not np.isclose(v1_moved, targets[2], atol=1e-6)
