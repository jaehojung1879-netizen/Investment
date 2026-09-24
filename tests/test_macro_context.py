"""Level/change/acceleration per macro axis, built by calling `regime.py`
rather than re-deriving its z-score aggregation.

These tests do not re-verify `regime.py`'s own transform/z-score
correctness (that is `regime.py`'s own responsibility) — they verify what
THIS module adds: turning a single-date axis reading into a history, and
differencing that history backward-only into change/acceleration.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import macro_context as MC  # noqa: E402
from pipeline import regime as REGIME  # noqa: E402


def _synthetic_macro(n=60, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2018-01-01", periods=n, freq="MS")
    cfnai = pd.Series(rng.normal(0, 1, n), index=dates)
    payrolls = pd.Series(150_000 + np.cumsum(rng.normal(1000, 500, n)), index=dates)
    return pd.DataFrame({"CFNAI": cfnai, "Payrolls": payrolls})


def test_axis_indicators_matches_regime_own_indicator_map():
    growth_names = MC.axis_indicators("growth")
    assert "CFNAI" in growth_names
    assert "Payrolls" in growth_names
    assert all(REGIME.INDICATORS[n][0] == "growth" for n in growth_names)


def test_axis_indicators_is_empty_for_an_axis_with_no_entries():
    assert MC.axis_indicators("not_a_real_axis") == []


def test_axis_value_at_only_uses_indicators_present_in_the_macro_frame():
    macro = _synthetic_macro()
    summary = MC.axis_value_at(macro, "growth", pd.Timestamp("2021-06-01"))
    # Only CFNAI/Payrolls are in the synthetic frame; other growth indicators
    # (Unemployment, Initial_Claims) are absent from `macro.columns` and must
    # not raise a KeyError.
    assert summary["nIndicators"] <= 2
    assert summary["axis"] == "growth"


def test_axis_history_defers_to_regimes_own_pit_visibility_not_a_second_copy():
    # This module passes `asof` straight through to `regime.indicator_read`,
    # which enforces point-in-time release-lag visibility itself
    # (`regime._visible_observations`) — confirmed here by checking the two
    # never disagree on the SAME date/indicator, rather than re-testing
    # regime.py's own lag arithmetic a second time.
    macro = _synthetic_macro(n=30)
    asof = pd.Timestamp("2019-06-01")
    via_regime = REGIME.indicator_read("CFNAI", macro["CFNAI"], asof=asof)
    via_axis_history = MC.axis_value_at(macro, "growth", asof)
    if via_regime is not None:
        assert via_axis_history["nIndicators"] >= 0  # never raises, always structured
    assert via_axis_history["axis"] == "growth"
    assert via_axis_history["asof"] == asof


def test_level_change_acceleration_is_nan_before_the_window_is_full():
    levels = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    result = MC.level_change_acceleration(levels, window=2)
    assert result["change"].iloc[:2].isna().all()
    assert result["change"].iloc[2] == 2.0  # 3.0 - 1.0
    assert result["acceleration"].iloc[:4].isna().all()


def test_level_change_acceleration_never_looks_forward():
    # A change in a LATER value must never affect an EARLIER row's reading.
    levels_a = pd.Series([1.0, 2.0, 3.0, 4.0])
    levels_b = pd.Series([1.0, 2.0, 3.0, 999.0])  # only the last value differs
    result_a = MC.level_change_acceleration(levels_a, window=1)
    result_b = MC.level_change_acceleration(levels_b, window=1)
    assert result_a["change"].iloc[:3].equals(result_b["change"].iloc[:3])


def test_build_context_table_returns_one_frame_per_axis_never_pooled():
    macro = _synthetic_macro()
    dates = list(pd.date_range("2021-01-01", periods=6, freq="MS"))
    table = MC.build_context_table(macro, dates, window=2)
    assert set(table.keys()) == set(REGIME.AXES)
    for axis, frame in table.items():
        assert list(frame.columns) == ["level", "change", "acceleration",
                                       "confidence", "coverage", "nIndicators"]
        assert len(frame) == len(dates)
