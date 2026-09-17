"""Walk-forward regional rotation: the weight decided at T must never depend
on anything dated T or later, and the schedule must only change at quarter
boundaries. These are the properties a look-ahead bug would violate silently.
"""
from __future__ import annotations

import pytest

from pipeline import portfolio_validation as PV
from pipeline import regional_rotation as RR


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


def test_apply_schedule_renormalizes_when_one_region_is_missing_that_date():
    us = [_row("2020-01-06", "2020-01-13", 0.10, weight_ticker="A")]
    # KR has no row on this date at all (e.g. a holiday mismatch).
    schedule = [{"date": "2020-01-06", "weights": {"US": 0.5, "KR": 0.5}}]
    blended = RR.apply_schedule({"US": us, "KR": []}, schedule)
    assert len(blended) == 1
    assert blended[0]["grossReturn"] == pytest.approx(0.11)  # US alone, renormalized to 100%
    assert blended[0]["regionalWeights"] == {"US": pytest.approx(1.0)}


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
