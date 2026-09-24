"""What a stored DART ownership-event record has to mean.

Synthetic fixtures only. The network half runs solely in CI via
`scripts/probe_dart_ownership_events.py`.
"""
from __future__ import annotations

from pipeline import dart_ownership_events as DOE


def _row(**overrides):
    """Shaped after the real live probe response (GitHub Actions run
    35964461327, 2026-09-24): report_tp is "일반" or "약식" in real data,
    never the guessed "신규"/"변동" this fixture used before that probe ran.
    """
    base = {"rcept_no": "20230515000123", "rcept_dt": "20230515",
            "corp_code": "00126380", "corp_name": "삼성전자",
            "report_tp": "일반", "repror": "국민연금공단",
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
    assert event["holdingPctAfter"] == 4.80
    assert event["holdingPctChange"] == -0.24
    assert event["holdingPctBefore"] is None, "never invented from stkrt - stkrt_irds"


def test_report_tp_ilban_is_preserved_raw_and_not_translated():
    """'일반' is a real, confirmed value — never mapped to a guessed enum."""
    event, _ = DOE.build_event(_row(report_tp="일반"), ticker="005930.KS",
                               collected_at="2026-09-24T00:00:00Z")
    assert event["reportTypeRaw"] == "일반"
    assert event["reportType"] is None, "known raw value, deliberately not translated"


def test_report_tp_yaksik_is_preserved_raw_and_not_translated():
    """'약식' is a real, confirmed value — never mapped to a guessed enum."""
    event, _ = DOE.build_event(_row(report_tp="약식"), ticker="005930.KS",
                               collected_at="2026-09-24T00:00:00Z")
    assert event["reportTypeRaw"] == "약식"
    assert event["reportType"] is None, "known raw value, deliberately not translated"


def test_the_disproven_guessed_values_are_no_longer_mapped_to_anything():
    """'신규'/'변동' never appeared in the live probe; they get no special
    treatment and are handled exactly like any other unrecognised raw string.
    """
    event, _ = DOE.build_event(_row(report_tp="신규"), ticker="005930.KS",
                               collected_at="2026-09-24T00:00:00Z")
    assert event["reportType"] is None
    assert event["reportTypeRaw"] == "신규"


def test_an_unrecognised_report_tp_passes_through_raw_and_maps_to_none():
    """A genuinely unseen value is never silently forced into a guessed enum."""
    event, _ = DOE.build_event(_row(report_tp="종국"), ticker="005930.KS",
                               collected_at="2026-09-24T00:00:00Z")
    assert event["reportType"] is None
    assert event["reportTypeRaw"] == "종국"


def test_missing_report_tp_is_none_not_an_empty_string():
    event, _ = DOE.build_event(_row(report_tp=None), ticker="005930.KS",
                               collected_at="2026-09-24T00:00:00Z")
    assert event["reportType"] is None
    assert event["reportTypeRaw"] is None


def test_missing_optional_field_does_not_crash_and_reads_as_none():
    """stkqy_irds (change in shares) can be absent on a row; the event is
    still built, with that field None rather than a fabricated value."""
    row = _row()
    del row["stkqy_irds"]
    event, reason = DOE.build_event(row, ticker="005930.KS", collected_at="x")
    assert reason == ""
    assert event["shareCountChange"] is None
    assert event["shareCountAfter"] is not None, "the field that WAS present is unaffected"


def test_zero_change_is_a_real_zero_not_a_missing_value():
    event, _ = DOE.build_event(_row(stkrt_irds="0.00", stkqy_irds="0"),
                               ticker="005930.KS", collected_at="x")
    assert event["holdingPctChange"] == 0.0
    assert event["shareCountChange"] == 0.0
    assert event["changeDirection"] is None, "zero is neither increase nor decrease"


def test_a_malformed_row_with_unparseable_numbers_still_builds_with_nones():
    event, reason = DOE.build_event(
        _row(stkrt="not-a-number", stkqy="also-not-a-number"),
        ticker="005930.KS", collected_at="x")
    assert reason == ""
    assert event["holdingPctAfter"] is None
    assert event["shareCountAfter"] is None


def test_a_row_missing_everything_but_a_receipt_number_still_refuses_gracefully():
    event, reason = DOE.build_event({"rcept_no": "20230515000123"},
                                    ticker="005930.KS", collected_at="x")
    assert reason == ""
    assert event["reportTypeRaw"] is None
    assert event["filerName"] is None


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


def test_duplicate_receipt_number_is_not_deduplicated_by_amendment_flags():
    """amendment_flags never drops or merges rows — that is a caller's own
    dedup policy to decide, not something this function imposes silently."""
    events = [
        DOE.build_event(_row(rcept_no="20200101000001", stkrt="10.0"),
                        ticker="005930.KS", collected_at="x")[0],
        DOE.build_event(_row(rcept_no="20200101000001", stkrt="10.0"),
                        ticker="005930.KS", collected_at="x")[0],
    ]
    flagged = DOE.amendment_flags(events)
    assert len(flagged) == 2
    assert sum(1 for e in flagged if e["amendmentFlag"]) == 1, (
        "the second identical receipt is still treated as 'an earlier one exists'")


def test_amendment_flags_orders_by_availablefrom_not_input_order():
    """Chronological ordering comes from availableFrom, regardless of the
    order build_event results are handed in."""
    later = DOE.build_event(_row(rcept_no="20220101000002", stkrt="8.0"),
                            ticker="005930.KS", collected_at="x")[0]
    earlier = DOE.build_event(_row(rcept_no="20200101000001", stkrt="10.0"),
                              ticker="005930.KS", collected_at="x")[0]
    flagged = DOE.amendment_flags([later, earlier])
    by_receipt = {e["receiptNo"]: e for e in flagged}
    assert by_receipt["20200101000001"]["amendmentFlag"] is False
    assert by_receipt["20220101000002"]["amendmentFlag"] is True


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
