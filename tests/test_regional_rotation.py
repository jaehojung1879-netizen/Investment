"""Walk-forward regional rotation: the weight decided at T must never depend
on anything dated T or later, and the schedule must only change at quarter
boundaries. These are the properties a look-ahead bug would violate silently.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline import historical_outcomes as HO
from pipeline import historical_replay as HR
from pipeline import portfolio_validation as PV
from pipeline import regional_rotation as RR
from pipeline import replay_valuation as RV


def _row(date, end_date, excess, *, weight_ticker="A", region_weight=1.0):
    return {"date": date, "endDate": end_date,
           "grossReturn": 0.01 + excess, "benchmarkReturn": 0.01,
           "grossExcessReturn": excess,
           "weights": {weight_ticker: region_weight}}


# --------------------------------------------------------------------------- #
# trailing_mean_excess
# --------------------------------------------------------------------------- #
def test_trailing_mean_excess_averages_only_matured_rows_in_the_window():
    decisions = [
        _row("2020-01-01", "2020-01-08", 0.02),
        _row("2020-01-08", "2020-01-15", 0.04),
        _row("2020-01-15", "2020-01-22", -0.10),  # outside the trailing window used below
    ]
    result = RR.trailing_mean_excess(decisions, "2020-01-16", lookback_days=10)
    assert result == pytest.approx((0.02 + 0.04) / 2)


def test_trailing_mean_excess_excludes_a_row_maturing_exactly_on_as_of():
    """endDate == as_of has not been observed as of as_of — it is the
    decision about to be made, not evidence for making it."""
    decisions = [_row("2020-01-01", "2020-01-15", 0.02)]
    assert RR.trailing_mean_excess(decisions, "2020-01-15", lookback_days=30) is None


def test_trailing_mean_excess_is_none_with_nothing_matured_yet():
    assert RR.trailing_mean_excess([], "2020-01-15") is None
    old = [_row("2018-01-01", "2018-01-08", 0.02)]
    assert RR.trailing_mean_excess(old, "2020-01-15", lookback_days=30) is None


# --------------------------------------------------------------------------- #
# softmax_weights
# --------------------------------------------------------------------------- #
def test_softmax_weights_sum_to_one_and_are_monotonic_in_score():
    weights = RR.softmax_weights({"US": 0.08, "KR": 0.02}, temperature=0.05, floor=0.15)
    assert weights["US"] + weights["KR"] == pytest.approx(1.0)
    assert weights["US"] > weights["KR"]


def test_softmax_weights_never_falls_below_the_floor():
    weights = RR.softmax_weights({"US": 0.50, "KR": -0.50}, temperature=0.05, floor=0.15)
    assert weights["KR"] == pytest.approx(0.15, abs=1e-6)
    assert weights["US"] + weights["KR"] == pytest.approx(1.0)


def test_softmax_weights_is_even_at_equal_scores():
    weights = RR.softmax_weights({"US": 0.03, "KR": 0.03})
    assert weights["US"] == pytest.approx(0.5)
    assert weights["KR"] == pytest.approx(0.5)


def test_softmax_weights_handles_negative_and_zero_scores_without_error():
    weights = RR.softmax_weights({"US": 0.0, "KR": -0.03})
    assert weights["US"] > weights["KR"]
    assert weights["US"] + weights["KR"] == pytest.approx(1.0)


def test_softmax_weights_holds_the_floor_for_a_region_pushed_under_it_by_the_refill():
    """The share a region RECEIVES is what has to clear the floor, not its raw
    softmax share — and pinning another region is what moves the two apart.

    Raw shares here are about (0.01, 0.31, 0.68). Pinning the 0.01 region at
    0.30 spends more than its raw share, so the survivors are scaled down and
    the 0.31 region — comfortably above the floor before the pass — receives
    0.70 x 0.31/0.99 = 0.219. A loop that re-reads the raw share cannot see
    that, because the raw share never changes.
    """
    weights = RR.softmax_weights({"A": -0.211, "B": -0.0393, "C": 0.0},
                                 temperature=0.05, floor=0.30)
    assert min(weights.values()) >= 0.30 - 1e-12
    assert sum(weights.values()) == pytest.approx(1.0)
    assert weights["C"] > weights["B"]  # ordering survives the water-fill


@pytest.mark.parametrize("seed", range(25))
def test_softmax_weights_holds_the_floor_on_any_score_vector(seed):
    rng = np.random.default_rng(seed)
    count = int(rng.integers(2, 6))
    floor = float(rng.uniform(0.0, 1.0 / count))
    scores = {f"R{i}": float(rng.uniform(-1.0, 1.0)) for i in range(count)}
    weights = RR.softmax_weights(scores, temperature=0.05, floor=floor)
    assert sum(weights.values()) == pytest.approx(1.0)
    assert min(weights.values()) >= floor - 1e-12


def test_softmax_weights_two_region_split_is_exactly_the_frozen_v1_assignment():
    """`regional-rotation-v1` freezes two regions and nothing else, so the
    water-fill must be a no-op there: with one region pinned the other takes
    exactly `1 - floor`, and with neither pinned the raw softmax shares stand
    unchanged. A floor fix that moved these would be a model change.
    """
    pinned = RR.softmax_weights({"US": 1000.0, "KR": -1000.0},
                                temperature=RR.DEFAULT_TEMPERATURE, floor=RR.DEFAULT_FLOOR)
    assert pinned["KR"] == RR.DEFAULT_FLOOR
    assert pinned["US"] == 1.0 - RR.DEFAULT_FLOOR
    scores = {"US": 0.08, "KR": 0.02}
    assert (RR.softmax_weights(scores, temperature=0.05, floor=RR.DEFAULT_FLOOR)
            == RR.softmax_weights(scores, temperature=0.05, floor=0.0))


def test_softmax_weights_refuses_an_unreachable_floor():
    with pytest.raises(ValueError):
        RR.softmax_weights({"A": 0.0, "B": 0.0, "C": 0.0}, floor=0.4)


def test_softmax_weights_single_region_is_trivially_whole():
    assert RR.softmax_weights({"US": -0.5}) == {"US": 1.0}


# --------------------------------------------------------------------------- #
# quarterly_decision_dates
# --------------------------------------------------------------------------- #
def test_quarterly_decision_dates_picks_the_first_real_date_per_quarter():
    dates = ["2020-01-06", "2020-01-13", "2020-04-06", "2020-04-13", "2020-07-06"]
    assert RR.quarterly_decision_dates(dates) == ["2020-01-06", "2020-04-06", "2020-07-06"]


def test_quarterly_decision_dates_never_invents_a_calendar_date():
    """No 2020-01-01 in the input (a holiday) -> none in the output."""
    dates = ["2020-01-06", "2020-01-13"]
    assert "2020-01-01" not in RR.quarterly_decision_dates(dates)


# --------------------------------------------------------------------------- #
# regional_weight_schedule — the look-ahead property
# --------------------------------------------------------------------------- #
def _weekly_dates(start_year, start_month, start_day, n, step_days=7):
    import pandas as pd
    stamp = pd.Timestamp(f"{start_year}-{start_month:02d}-{start_day:02d}")
    return [(stamp + pd.Timedelta(days=step_days * i)).strftime("%Y-%m-%d") for i in range(n)]


def _decisions_from_excess(dates, excesses):
    rows = []
    for i in range(len(dates) - 1):
        rows.append(_row(dates[i], dates[i + 1], excesses[i]))
    return rows


def test_cold_start_is_equal_weight_not_a_guess():
    dates = _weekly_dates(2020, 1, 6, 3)
    decisions = {"US": _decisions_from_excess(dates, [0.05, 0.05]),
                "KR": _decisions_from_excess(dates, [-0.05, -0.05])}
    schedule = RR.regional_weight_schedule(decisions)
    first = schedule[0]
    assert first["weights"]["US"] == pytest.approx(0.5)
    assert first["weights"]["KR"] == pytest.approx(0.5)


def test_a_later_decisions_return_never_changes_an_earlier_weight():
    """The look-ahead check: mutate a FUTURE excess return and confirm every
    schedule entry dated before it is byte-for-byte unchanged."""
    dates = _weekly_dates(2020, 1, 6, 60)
    baseline_excess = [0.01 if i % 3 else 0.06 for i in range(len(dates) - 1)]
    decisions_a = {"US": _decisions_from_excess(dates, baseline_excess),
                  "KR": _decisions_from_excess(dates, [-x for x in baseline_excess])}
    schedule_a = RR.regional_weight_schedule(decisions_a, lookback_days=252)

    mutated_excess = list(baseline_excess)
    mutated_excess[-1] = 0.99  # a wild swing on the very last (latest) decision
    decisions_b = {"US": _decisions_from_excess(dates, mutated_excess),
                  "KR": _decisions_from_excess(dates, [-x for x in mutated_excess])}
    schedule_b = RR.regional_weight_schedule(decisions_b, lookback_days=252)

    last_date_before_mutation = dates[-2]
    for a, b in zip(schedule_a, schedule_b):
        assert a["date"] == b["date"]
        if a["date"] < last_date_before_mutation:
            assert a["weights"] == b["weights"], (
                f"schedule entry {a['date']} changed after mutating a later decision")


def test_the_schedule_only_re_decides_at_quarter_boundaries():
    dates = _weekly_dates(2020, 1, 6, 20)
    excess = [0.01] * (len(dates) - 1)
    decisions = {"US": _decisions_from_excess(dates, excess),
                "KR": _decisions_from_excess(dates, excess)}
    schedule = RR.regional_weight_schedule(decisions)
    schedule_dates = [row["date"] for row in schedule]
    quarters = {(__import__("pandas").Timestamp(d).year, __import__("pandas").Timestamp(d).quarter)
               for d in schedule_dates}
    assert len(quarters) == len(schedule_dates), "one entry per quarter, not per rebalance date"


# --------------------------------------------------------------------------- #
# apply_schedule
# --------------------------------------------------------------------------- #
def test_apply_schedule_blends_returns_by_the_active_weight():
    us = [_row("2020-01-06", "2020-01-13", 0.05, weight_ticker="AAPL")]
    kr = [_row("2020-01-06", "2020-01-13", -0.03, weight_ticker="005930.KS")]
    schedule = [{"date": "2020-01-06", "weights": {"US": 0.7, "KR": 0.3}}]
    blended = RR.apply_schedule({"US": us, "KR": kr}, schedule)
    assert len(blended) == 1
    row = blended[0]
    assert row["grossReturn"] == pytest.approx(0.7 * (0.01 + 0.05) + 0.3 * (0.01 - 0.03))
    assert row["weights"] == {"AAPL": pytest.approx(0.7), "005930.KS": pytest.approx(0.3)}
    assert row["regionByTicker"] == {"AAPL": "US", "005930.KS": "KR"}


def test_apply_schedule_uses_the_weight_decided_at_or_before_the_date_never_after():
    us = [_row("2020-01-06", "2020-01-13", 0.10, weight_ticker="A"),
         _row("2020-04-06", "2020-04-13", 0.10, weight_ticker="A")]
    kr = [_row("2020-01-06", "2020-01-13", -0.10, weight_ticker="B"),
         _row("2020-04-06", "2020-04-13", -0.10, weight_ticker="B")]
    schedule = [{"date": "2020-01-06", "weights": {"US": 1.0, "KR": 0.0}},
               {"date": "2020-04-06", "weights": {"US": 0.0, "KR": 1.0}}]
    blended = RR.apply_schedule({"US": us, "KR": kr}, schedule)
    jan_row = next(r for r in blended if r["date"] == "2020-01-06")
    apr_row = next(r for r in blended if r["date"] == "2020-04-06")
    assert jan_row["grossReturn"] == pytest.approx(0.11)   # 100% US
    assert apr_row["grossReturn"] == pytest.approx(-0.09)  # 100% KR


def test_apply_schedule_emits_nothing_before_the_first_decision():
    us = [_row("2019-06-01", "2019-06-08", 0.02, weight_ticker="A")]
    kr = [_row("2019-06-01", "2019-06-08", 0.02, weight_ticker="B")]
    schedule = [{"date": "2020-01-06", "weights": {"US": 0.5, "KR": 0.5}}]
    assert RR.apply_schedule({"US": us, "KR": kr}, schedule) == []


def test_apply_schedule_drops_a_block_with_mismatched_end_dates():
    us = [_row("2020-01-06", "2020-01-13", 0.02, weight_ticker="A")]
    kr = [_row("2020-01-06", "2020-01-20", 0.02, weight_ticker="B")]  # different horizon
    schedule = [{"date": "2020-01-06", "weights": {"US": 0.5, "KR": 0.5}}]
    assert RR.apply_schedule({"US": us, "KR": kr}, schedule) == []


def test_apply_schedule_omits_when_one_region_is_missing_that_date():
    us = [_row("2020-01-06", "2020-01-13", 0.10, weight_ticker="A")]
    # KR has no row on this date at all (e.g. a holiday mismatch).
    schedule = [{"date": "2020-01-06", "weights": {"US": 0.5, "KR": 0.5}}]
    blended = RR.apply_schedule({"US": us, "KR": []}, schedule)
    assert blended == []  # Unknown KR sleeve must never become a 100% US portfolio.


# --------------------------------------------------------------------------- #
# End to end: the blended output is a valid _path_metrics input
# --------------------------------------------------------------------------- #
def test_blended_rows_score_through_the_existing_path_metrics_machinery():
    dates = _weekly_dates(2020, 1, 6, 30)
    us_excess = [0.01] * (len(dates) - 1)
    kr_excess = [0.005] * (len(dates) - 1)
    us = _decisions_from_excess(dates, us_excess)
    kr = _decisions_from_excess(dates, kr_excess)
    for row in us:
        row["weights"] = {"AAPL": 1.0}
    for row in kr:
        row["weights"] = {"005930.KS": 1.0}
    schedule = RR.regional_weight_schedule({"US": us, "KR": kr})
    blended = RR.apply_schedule({"US": us, "KR": kr}, schedule)
    assert blended, "the fixture must produce at least one blended block"
    metrics = PV._path_metrics(blended, horizon=7, cfg_pf={})
    assert metrics["available"] is True
    assert metrics["cagrPct"] is not None


# --------------------------------------------------------------------------- #
# End to end, for real: two real single-region replays through
# `portfolio_validation.portfolio_replay`'s own `headlineRows`, not a
# hand-built fixture — this is the exact chain
# `scripts/run_regional_rotation_replay.py` runs against `replay-v16`'s
# frozen inputs, checked here against synthetic data this session CAN run.
# --------------------------------------------------------------------------- #
def _synthetic_frame(seed, periods=900, start="2015-01-01"):
    rng = np.random.default_rng(seed)
    index = pd.bdate_range(start, periods=periods)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.014, periods)))
    return pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99,
                         "Close": close, "Volume": rng.lognormal(14, 0.4, periods)},
                        index=index)


def _region_champion_headline_rows(region, tickers, prices, universe, valuation):
    replay = HR.run_replay(
        prices, {region: tickers}, benchmarks={"US": "SPY", "KR": "KS200"},
        cfg_lt={"minFactorSleeves": 1, "minFinancialCoverage": 0.0},
        start="2018-01-05", end="2018-04-30", frequency="W", model_version="test")
    signals, diagnostics = replay["signals"], replay["diagnostics"]
    bench_closes = {"SPY": prices["SPY"]["Close"], "KS200": prices["KS200"]["Close"]}
    outcomes = HO.compute_outcomes(signals, prices, bench_closes)
    portfolio = PV.portfolio_replay(signals, outcomes, cfg_lt={"minFactorSleeves": 1},
                                    cfg_pf={}, diagnostics=diagnostics, valuation=valuation)
    return portfolio["headlineRows"].get(PV.CHAMPION) or []


def test_real_single_region_replays_blend_through_the_full_runner_chain():
    # Small and short on purpose — this test's job is to check the WIRING
    # (does a real `portfolio_replay` output actually flow through
    # `regional_rotation`), not to produce a meaningful backtest. Below 5
    # names the research pool is too thin to select from at all (signals=0);
    # 6 names and 4 months is the smallest fixture that still clears every
    # gate and matures real headline blocks, keeping this well under the
    # cost of `scripts/run_replay.py`'s own decade-long run.
    prices = {f"T{i:02d}": _synthetic_frame(200 + i) for i in range(6)}
    prices.update({f"K{i:02d}": _synthetic_frame(300 + i) for i in range(6)})
    prices["SPY"] = _synthetic_frame(999)
    prices["KS200"] = _synthetic_frame(998)
    universe = {"US": [t for t in prices if t.startswith("T")],
               "KR": [t for t in prices if t.startswith("K")]}

    days = pd.bdate_range("2015-01-01", periods=900)
    fx = pd.Series(1200.0, index=days)
    rates = [{"date": "2015-01-01", "annualRatePct": 3.0}]
    valuation = RV.ValuationData(prices, {"US": "SPY", "KR": "KS200"}, fx, rates,
                                 through="2018-04-30")

    us_rows = _region_champion_headline_rows("US", universe["US"], prices, universe, valuation)
    kr_rows = _region_champion_headline_rows("KR", universe["KR"], prices, universe, valuation)
    assert us_rows and kr_rows, (
        "the fixture must actually produce matured CHAMPION headline rows for "
        "both regions, or this test is not exercising the real chain")
    for row in us_rows + kr_rows:
        for key in ("date", "endDate", "grossReturn", "benchmarkReturn", "weights",
                   "regionByTicker", "top1", "top3"):
            assert key in row, f"headlineRows lost {key!r} — regional_rotation reads it"

    schedule = RR.regional_weight_schedule({"US": us_rows, "KR": kr_rows})
    blended = RR.apply_schedule({"US": us_rows, "KR": kr_rows}, schedule)
    assert blended, "real headline rows from both regions must produce blended blocks"
    metrics = PV._path_metrics(blended, PV.HEADLINE_HORIZON, {})
    assert metrics["available"] is True
    assert metrics["cagrPct"] is not None
