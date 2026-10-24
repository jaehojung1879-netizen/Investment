"""Audit invariants on invented quote paths; no old study execution."""

import pytest
from .audit import endpoint, immutable_originals, check_metrics
from .. import run as R


def test_split_endpoint_preserves_units_but_does_not_invent_halt_marks():
    result = endpoint(
        [100.0, 100.0, 11.0], [1.0, 0.0, 1.0], ["A", "B", "C"], entry="A", exit_day="C", split_events=[("C", 10)]
    )
    assert result["grossEndpointReturn"] == pytest.approx(0.1)
    assert result["zeroVolumeMarks"] == 1 and result["dailyRiskAvailable"] is False


def test_missing_terminal_or_executable_endpoint_cannot_be_substituted():
    with pytest.raises(ValueError, match="NONEXECUTABLE"):
        endpoint([100.0, 100.0], [1.0, 0.0], ["A", "B"], entry="A", exit_day="B")


def test_unvalued_right_blocks_only_crossing_interval():
    with pytest.raises(ValueError, match="UNVALUED_RIGHT"):
        endpoint([100.0, 110.0, 120.0], [1.0, 1.0, 1.0], ["A", "B", "C"], entry="A", exit_day="C", barred_dates=["B"])
    result = endpoint(
        [100.0, 110.0, 120.0], [1.0, 1.0, 1.0], ["A", "B", "C"], entry="B", exit_day="C", barred_dates=["A"]
    )
    assert result["grossEndpointReturn"] == pytest.approx(120 / 110 - 1)


def test_parent_only_demerger_factor_cannot_be_used_as_split_wealth():
    with pytest.raises(ValueError, match="UNREVIEWED_DISTRIBUTION"):
        endpoint([100.0, 120.0], [1.0, 1.0], ["A", "B"], entry="A", exit_day="B", split_events=[("B", 0.90028)])


def test_original_results_and_all_completed_navs_reconcile():
    assert immutable_originals() == 50
    assert len(check_metrics()) == 30


def test_frozen_executable_uses_dated_tax_and_etf_has_no_stock_tax():
    assert R.tax_bps("2019-05-31") == 30
    assert R.tax_bps("2019-06-03") == 25
    assert R.cost("2019-06-03", stock=True, sell=True) == pytest.approx(0.00365)
    assert R.cost("2019-06-03", stock=False, sell=True) == pytest.approx(0.00115)
