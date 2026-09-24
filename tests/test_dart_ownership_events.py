"""What a stored DART ownership-event record has to mean.

Synthetic fixtures only. The network half runs solely in CI via
`scripts/probe_dart_ownership_events.py`.
"""
from __future__ import annotations

from pipeline import dart_ownership_events as DOE


def _row(**overrides):
    base = {"rcept_no": "20230515000123", "rcept_dt": "20230515",
            "corp_code": "00126380", "corp_name": "삼성전자",
            "report_tp": "변동", "repror": "국민연금공단",
            "stkqy": "1,000,000", "stkqy_irds": "-50,000",
            "stkrt": "4.80", "stkrt_irds": "-0.24"}
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# receipt_date is reused, not reimplemented
# --------------------------------------------------------------------------- #
def test_receipt_date_is_the_same_function_dart_fundamentals_exports():
    from pipeline import dart_fundamentals as DF
    assert DOE.receipt_date is DF.receipt_date


# --------------------------------------------------------------------------- #
# build_event
# --------------------------------------------------------------------------- #
def test_a_normal_row_becomes_a_record_keyed_by_receipt_no():
    event, reason = DOE.build_event(_row(), ticker="005930.KS", collected_at="2026-09-24T00:00:00Z")
    assert reason == ""
    assert event["id"] == "dart-ownership:20230515000123"
    assert event["availableFrom"] == "2023-05-15"
    assert event["reportType"] == DOE.REPORT_TYPE_CHANGE
    assert event["reportTypeRaw"] == "변동"
    assert event["holdingPctAfter"] == 4.80
    assert event["holdingPctChange"] == -0.24
    assert event["holdingPctBefore"] is None, "never invented from stkrt - stkrt_irds"


def test_a_new_holder_maps_to_the_new_holder_type():
    event, _ = DOE.build_event(_row(report_tp="신규", stkrt_irds="5.10"),
                               ticker="005930.KS", collected_at="2026-09-24T00:00:00Z")
    assert event["reportType"] == DOE.REPORT_TYPE_NEW


def test_an_unrecognised_report_tp_passes_through_raw_and_maps_to_none():
    """An unseen third value is never silently forced into NEW or CHANGE."""
    event, _ = DOE.build_event(_row(report_tp="종국"), ticker="005930.KS",
                               collected_at="2026-09-24T00:00:00Z")
    assert event["reportType"] is None
    assert event["reportTypeRaw"] == "종국"


def test_no_receipt_number_is_refused_not_stored():
    event, reason = DOE.build_event(_row(rcept_no=None), ticker="005930.KS",
                                    collected_at="2026-09-24T00:00:00Z")
    assert event is None and reason == "NO_RECEIPT_NO"


def test_an_unparseable_receipt_number_is_refused():
    event, reason = DOE.build_event(_row(rcept_no="not-a-number"), ticker="005930.KS",
                                    collected_at="2026-09-24T00:00:00Z")
    assert event is None and reason == "NO_RECEIPT_DATE"


# --------------------------------------------------------------------------- #
# direction_of_change
# --------------------------------------------------------------------------- #
def test_direction_of_change_reads_the_sign_and_the_threshold_crossing():
    assert DOE.direction_of_change(1.0, 6.0) == "INCREASE"
    assert DOE.direction_of_change(-1.0, 6.0) == "DECREASE"
    assert DOE.direction_of_change(-1.0, 4.0) == "EXIT_BELOW_THRESHOLD"
    assert DOE.direction_of_change(None, 4.0) is None
    assert DOE.direction_of_change(0.0, 6.0) is None


# --------------------------------------------------------------------------- #
# amendment_flags
# --------------------------------------------------------------------------- #
def test_the_first_event_for_a_filer_pair_is_unmarked_and_later_ones_are():
    events = [
        DOE.build_event(_row(rcept_no="20200101000001", stkrt="10.0"),
                        ticker="005930.KS", collected_at="x")[0],
        DOE.build_event(_row(rcept_no="20210101000002", stkrt="9.0"),
                        ticker="005930.KS", collected_at="x")[0],
    ]
    flagged = DOE.amendment_flags(events)
    by_receipt = {e["receiptNo"]: e for e in flagged}
    assert by_receipt["20200101000001"]["amendmentFlag"] is False
    assert by_receipt["20210101000002"]["amendmentFlag"] is True


def test_two_different_filers_on_the_same_ticker_are_independent():
    events = [
        DOE.build_event(_row(rcept_no="20200101000001", repror="A"),
                        ticker="005930.KS", collected_at="x")[0],
        DOE.build_event(_row(rcept_no="20200101000002", repror="B"),
                        ticker="005930.KS", collected_at="x")[0],
    ]
    flagged = DOE.amendment_flags(events)
    assert all(e["amendmentFlag"] is False for e in flagged)


# --------------------------------------------------------------------------- #
# record_year / shard_path
# --------------------------------------------------------------------------- #
def test_record_year_comes_from_availablefrom_not_reportdate():
    event, _ = DOE.build_event(_row(), ticker="005930.KS", collected_at="x")
    assert DOE.record_year(event) == 2023


def test_record_year_is_none_when_unreadable():
    assert DOE.record_year({"availableFrom": None}) is None
