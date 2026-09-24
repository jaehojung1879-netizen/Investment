"""What a stored KR short-selling record has to mean.

Synthetic fixtures only. The network half runs solely in CI via
`scripts/probe_kr_short_selling.py`.
"""
from __future__ import annotations

from pipeline import kr_short_selling as KSS


# --------------------------------------------------------------------------- #
# Regime labelling — the invariant this whole module exists to enforce
# --------------------------------------------------------------------------- #
def test_a_normal_date_is_labelled_normal():
    assert KSS.regime_label("2019-06-01") == KSS.REGIME_NORMAL
    assert KSS.regime_label("2022-01-01") == KSS.REGIME_NORMAL


def test_the_covid_ban_window_is_labelled_and_bounded():
    assert KSS.regime_label("2020-03-16") == KSS.REGIME_BANNED_COVID
    assert KSS.regime_label("2020-12-01") == KSS.REGIME_BANNED_COVID
    assert KSS.regime_label("2021-05-02") == KSS.REGIME_BANNED_COVID
    assert KSS.regime_label("2021-05-03") == KSS.REGIME_NORMAL


def test_the_structural_ban_window_is_labelled_and_bounded():
    assert KSS.regime_label("2023-11-04") == KSS.REGIME_NORMAL
    assert KSS.regime_label("2023-11-05") == KSS.REGIME_BANNED_STRUCTURAL
    assert KSS.regime_label("2025-03-31") == KSS.REGIME_BANNED_STRUCTURAL
    assert KSS.regime_label("2025-04-01") == KSS.REGIME_NORMAL


def test_is_banned_matches_regime_label():
    assert KSS.is_banned("2020-06-01") is True
    assert KSS.is_banned("2022-06-01") is False


def test_banned_dates_reports_only_the_overlap_with_the_requested_range():
    windows = KSS.banned_dates("2023-01-01", "2024-01-01")
    assert len(windows) == 1
    start, end, label = windows[0]
    assert start == "2023-11-05" and end == "2024-01-01"
    assert label == KSS.REGIME_BANNED_STRUCTURAL


def test_banned_dates_is_empty_for_an_all_normal_range():
    assert KSS.banned_dates("2022-01-01", "2022-12-31") == []


# --------------------------------------------------------------------------- #
# Amount parsing
# --------------------------------------------------------------------------- #
def test_parse_amount_shares_the_no_fabricated_zero_rule():
    assert KSS.parse_amount("1,234") == 1234.0
    for blank in ("", "-", None):
        assert KSS.parse_amount(blank) is None


# --------------------------------------------------------------------------- #
# build_trading_record
# --------------------------------------------------------------------------- #
def test_a_trading_row_computes_the_ratio_only_when_both_sides_are_present():
    row = {"CVSRTSELL_TRDVOL": "10,000", "ACC_TRDVOL": "100,000"}
    record, reason = KSS.build_trading_record(
        ticker="005930.KS", date="2019-06-03", row=row, collected_at="x")
    assert reason == ""
    assert record["shortSaleRatio"] == 0.1
    assert record["regimeLabel"] == KSS.REGIME_NORMAL


def test_a_trading_row_with_no_total_volume_leaves_ratio_none_never_a_divide_by_zero():
    row = {"CVSRTSELL_TRDVOL": "10,000", "ACC_TRDVOL": "0"}
    record, _ = KSS.build_trading_record(
        ticker="005930.KS", date="2019-06-03", row=row, collected_at="x")
    assert record["shortSaleRatio"] is None


def test_a_row_inside_a_ban_window_still_gets_a_record_labelled_banned():
    row = {"CVSRTSELL_TRDVOL": "0", "ACC_TRDVOL": "50,000"}
    record, reason = KSS.build_trading_record(
        ticker="005930.KS", date="2024-01-05", row=row, collected_at="x")
    assert reason == ""
    # 2024-01-05 sits inside the structural ban window.
    assert record["regimeLabel"] == KSS.REGIME_BANNED_STRUCTURAL


def test_an_empty_trading_response_is_refused():
    record, reason = KSS.build_trading_record(
        ticker="005930.KS", date="2024-01-05", row={}, collected_at="x")
    assert record is None and reason == "EMPTY_RESPONSE"


# --------------------------------------------------------------------------- #
# build_net_position_record
# --------------------------------------------------------------------------- #
def test_a_net_position_row_uses_the_as_stated_report_date_when_present():
    row = {"RATIO": "0.5", "BAL_QTY": "1,000", "RPT_DD": "20240108"}
    record, reason = KSS.build_net_position_record(
        ticker="005930.KS", date="2024-01-05", row=row, collected_at="x")
    assert reason == ""
    assert record["availableFrom"] == "20240108"
    assert record["availableFromBasis"] == "AS_STATED"


def test_a_net_position_row_falls_back_to_the_documented_lag_when_no_date_is_stated():
    row = {"RATIO": "0.5", "BAL_QTY": "1,000"}
    record, reason = KSS.build_net_position_record(
        ticker="005930.KS", date="2024-01-05", row=row, collected_at="x")
    assert reason == ""
    assert record["availableFrom"] == "2024-01-07"  # +2 documented lag
    assert record["availableFromBasis"] == "ASSUMED_FROM_DOCUMENTED_LAG"


def test_an_empty_net_position_response_is_refused():
    record, reason = KSS.build_net_position_record(
        ticker="005930.KS", date="2024-01-05", row={}, collected_at="x")
    assert record is None and reason == "EMPTY_RESPONSE"


def test_trading_and_net_position_ids_never_collide():
    assert (KSS.trading_record_id("005930.KS", "2024-01-05")
            != KSS.net_position_record_id("005930.KS", "2024-01-05"))
