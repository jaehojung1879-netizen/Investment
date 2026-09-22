"""Unit tests for the shared point-in-time fundamental-acceleration core
(``pipeline.fundamental_acceleration``), exercised on synthetic
``FundamentalRecord`` fixtures.

The real sealed ledger has zero amendment/restatement cases and zero
non-consecutive-gap cases for the tickers this study touches (measured
directly against ``pit-kr.jsonl``/``pit-us.jsonl``), so those branches are a
defensive-correctness requirement this module's own PIT-semantics contract
demands, and synthetic fixtures are the only way to exercise them.
"""
from __future__ import annotations

import pytest

from pipeline import fundamental_acceleration as FA
from pipeline import pit_data


def _record(ticker, period, available_from, fields, report_date=None):
    return pit_data.FundamentalRecord(
        ticker=ticker,
        report_period=period,
        available_from=available_from,
        report_date=report_date or available_from,
        fields=dict(fields),
    )


def _store(records: dict[str, list[pit_data.FundamentalRecord]]) -> pit_data.FundamentalStore:
    return pit_data.FundamentalStore(records)


# --------------------------------------------------------------------------- #
# Report-period parsing / consecutiveness
# --------------------------------------------------------------------------- #
def test_parse_report_period_us_and_kr():
    assert FA.parse_report_period("2019-Q3", "US") == (2019, 2)
    assert FA.parse_report_period("2019-11014", "KR") == (2019, 2)


def test_parse_report_period_rejects_unknown_code_or_region():
    assert FA.parse_report_period("2019-Q9", "US") is None
    assert FA.parse_report_period("2019-99999", "KR") is None
    assert FA.parse_report_period("2019-Q1", "JP") is None
    assert FA.parse_report_period("garbage", "US") is None
    assert FA.parse_report_period("", "US") is None


def test_is_consecutive_same_year_one_step():
    assert FA.is_consecutive((2019, 0), (2019, 1)) is True
    assert FA.is_consecutive((2019, 1), (2019, 2)) is True


def test_is_consecutive_fiscal_year_rollover():
    assert FA.is_consecutive((2019, 3), (2020, 0)) is True


def test_is_consecutive_rejects_skipped_period():
    assert FA.is_consecutive((2019, 0), (2019, 2)) is False  # Q1 -> Q3, H1 skipped


def test_is_consecutive_rejects_non_rollover_year_jump():
    assert FA.is_consecutive((2019, 1), (2020, 1)) is False


# --------------------------------------------------------------------------- #
# resolve_filing_pair -- PIT visibility, consecutiveness, amendments
# --------------------------------------------------------------------------- #
def test_resolve_no_filing_visible_before_any_availability():
    store = _store({"X": [_record("X", "2019-Q1", "2019-05-01", {"roe": 0.1})]})
    pair = FA.resolve_filing_pair(store, "X", "US", "2019-01-01")
    assert pair.status == FA.NO_FILING_VISIBLE


def test_resolve_no_filing_visible_for_unknown_ticker():
    store = _store({})
    pair = FA.resolve_filing_pair(store, "X", "US", "2019-01-01")
    assert pair.status == FA.NO_FILING_VISIBLE


def test_resolve_no_previous_filing_on_first_ever_filing():
    store = _store({"X": [_record("X", "2019-Q1", "2019-05-01", {"roe": 0.1})]})
    pair = FA.resolve_filing_pair(store, "X", "US", "2019-06-01")
    assert pair.status == FA.NO_PREVIOUS_FILING
    assert pair.current.report_period == "2019-Q1"
    assert pair.previous is None


def test_resolve_ok_on_two_consecutive_visible_filings():
    store = _store({"X": [
        _record("X", "2019-Q1", "2019-05-01", {"roe": 0.10}),
        _record("X", "2019-Q2", "2019-08-01", {"roe": 0.12}),
    ]})
    pair = FA.resolve_filing_pair(store, "X", "US", "2019-09-01")
    assert pair.status == FA.OK
    assert pair.current.report_period == "2019-Q2"
    assert pair.previous.report_period == "2019-Q1"


def test_resolve_not_consecutive_on_skipped_period():
    store = _store({"X": [
        _record("X", "2019-Q1", "2019-05-01", {"roe": 0.10}),
        _record("X", "2019-Q3", "2019-11-01", {"roe": 0.15}),
    ]})
    pair = FA.resolve_filing_pair(store, "X", "US", "2019-12-01")
    assert pair.status == FA.NOT_CONSECUTIVE
    assert pair.current.report_period == "2019-Q3"
    assert pair.previous.report_period == "2019-Q1"


def test_resolve_fiscal_year_rollover_is_consecutive():
    store = _store({"X": [
        _record("X", "2018-FY", "2019-02-01", {"roe": 0.10}),
        _record("X", "2019-Q1", "2019-05-01", {"roe": 0.11}),
    ]})
    pair = FA.resolve_filing_pair(store, "X", "US", "2019-06-01")
    assert pair.status == FA.OK


def test_resolve_ignores_future_filing_not_yet_visible():
    store = _store({"X": [
        _record("X", "2019-Q1", "2019-05-01", {"roe": 0.10}),
        _record("X", "2019-Q2", "2019-08-01", {"roe": 0.12}),
    ]})
    # As-of date is BEFORE Q2 becomes visible: only Q1 is visible, so this is
    # a NO_PREVIOUS_FILING read, never a leak of the future Q2 filing.
    pair = FA.resolve_filing_pair(store, "X", "US", "2019-06-01")
    assert pair.status == FA.NO_PREVIOUS_FILING
    assert pair.current.report_period == "2019-Q1"


def test_resolve_amended_filing_uses_latest_visible_restatement():
    store = _store({"X": [
        _record("X", "2019-Q1", "2019-05-01", {"roe": 0.10}),
        _record("X", "2019-Q2", "2019-08-01", {"roe": 0.12}),
        # A restatement of Q1, filed and visible later, with a different value.
        _record("X", "2019-Q1", "2019-09-01", {"roe": 0.30}),
    ]})
    pair = FA.resolve_filing_pair(store, "X", "US", "2019-10-01")
    assert pair.status == FA.OK
    assert pair.current.report_period == "2019-Q2"
    assert pair.previous.report_period == "2019-Q1"
    assert pair.previous.fields["roe"] == 0.30  # the restated value, not the original 0.10


def test_resolve_amendment_not_yet_visible_is_not_used():
    store = _store({"X": [
        _record("X", "2019-Q1", "2019-05-01", {"roe": 0.10}),
        _record("X", "2019-Q2", "2019-08-01", {"roe": 0.12}),
        _record("X", "2019-Q1", "2019-09-01", {"roe": 0.30}),  # restatement, not yet visible
    ]})
    pair = FA.resolve_filing_pair(store, "X", "US", "2019-08-15")
    assert pair.status == FA.OK
    assert pair.previous.fields["roe"] == 0.10  # original value, restatement invisible


def test_resolve_unparseable_period_when_only_code_is_unrecognised():
    store = _store({"X": [_record("X", "2019-Q9", "2019-05-01", {"roe": 0.1})]})
    pair = FA.resolve_filing_pair(store, "X", "US", "2019-06-01")
    assert pair.status == FA.UNPARSEABLE_PERIOD


def test_resolve_kr_report_codes():
    store = _store({"005930.KS": [
        _record("005930.KS", "2019-11013", "2019-05-15", {"roe": 0.08}),
        _record("005930.KS", "2019-11012", "2019-08-14", {"roe": 0.09}),
    ]})
    pair = FA.resolve_filing_pair(store, "005930.KS", "KR", "2019-09-01")
    assert pair.status == FA.OK
    assert pair.current.report_period == "2019-11012"
    assert pair.previous.report_period == "2019-11013"


# --------------------------------------------------------------------------- #
# compute_deltas
# --------------------------------------------------------------------------- #
def test_compute_deltas_basic():
    current = _record("X", "2019-Q2", "2019-08-01",
                       {"roe": 0.12, "operatingMargin": 0.20, "profitMargin": 0.10,
                        "earningsGrowth": 0.05, "debtToEquity": 0.5})
    previous = _record("X", "2019-Q1", "2019-05-01",
                        {"roe": 0.10, "operatingMargin": 0.18, "profitMargin": 0.08,
                         "earningsGrowth": 0.03, "debtToEquity": 0.6})
    deltas = FA.compute_deltas(current, previous)
    assert deltas["roe"] == pytest.approx(0.02)
    assert deltas["operatingMargin"] == pytest.approx(0.02)
    assert deltas["profitMargin"] == pytest.approx(0.02)
    assert deltas["earningsGrowth"] == pytest.approx(0.02)
    assert deltas["debtToEquity"] == pytest.approx(-0.1)


def test_compute_deltas_missing_field_on_either_leg_is_none_never_zero():
    current = _record("X", "2019-Q2", "2019-08-01", {"roe": 0.12})
    previous = _record("X", "2019-Q1", "2019-05-01", {"operatingMargin": 0.18})
    deltas = FA.compute_deltas(current, previous)
    assert deltas["roe"] is None  # previous lacks roe
    assert deltas["operatingMargin"] is None  # current lacks operatingMargin
    assert deltas["profitMargin"] is None


# --------------------------------------------------------------------------- #
# acceleration_reading -- full combined behaviour
# --------------------------------------------------------------------------- #
def test_acceleration_reading_ok_with_sufficient_primary_fields():
    store = _store({"X": [
        _record("X", "2019-Q1", "2019-05-01",
                {"roe": 0.10, "operatingMargin": 0.18, "profitMargin": 0.08}),
        _record("X", "2019-Q2", "2019-08-01",
                {"roe": 0.12, "operatingMargin": 0.20, "profitMargin": 0.10}),
    ]})
    reading = FA.acceleration_reading(store, "X", "US", "2019-09-01")
    assert reading["status"] == FA.OK
    assert reading["primaryFieldsPresent"] == 3
    assert reading["dataSufficient"] is True
    assert reading["deltas"]["roe"] == pytest.approx(0.02)
    assert reading["currentReportPeriod"] == "2019-Q2"
    assert reading["previousReportPeriod"] == "2019-Q1"


def test_acceleration_reading_insufficient_primary_fields_below_minimum():
    store = _store({"X": [
        _record("X", "2019-Q1", "2019-05-01", {"roe": 0.10}),
        _record("X", "2019-Q2", "2019-08-01", {"roe": 0.12}),
    ]})
    reading = FA.acceleration_reading(store, "X", "US", "2019-09-01")
    assert reading["status"] == FA.OK
    assert reading["primaryFieldsPresent"] == 1
    assert reading["dataSufficient"] is False


def test_acceleration_reading_not_consecutive_has_empty_deltas():
    store = _store({"X": [
        _record("X", "2019-Q1", "2019-05-01", {"roe": 0.10}),
        _record("X", "2019-Q3", "2019-11-01", {"roe": 0.15}),
    ]})
    reading = FA.acceleration_reading(store, "X", "US", "2019-12-01")
    assert reading["status"] == FA.NOT_CONSECUTIVE
    assert all(v is None for v in reading["deltas"].values())
    assert reading["dataSufficient"] is False


def test_acceleration_reading_no_filing_visible_has_empty_deltas():
    store = _store({})
    reading = FA.acceleration_reading(store, "X", "US", "2019-12-01")
    assert reading["status"] == FA.NO_FILING_VISIBLE
    assert all(v is None for v in reading["deltas"].values())


def test_acceleration_reading_future_filing_never_leaks():
    # A filing dated far in the future must never influence a reading taken
    # long before it becomes visible.
    store = _store({"X": [
        _record("X", "2019-Q1", "2019-05-01", {"roe": 0.10, "operatingMargin": 0.1,
                                                "profitMargin": 0.1}),
        _record("X", "2030-Q1", "2030-05-01", {"roe": 99.0, "operatingMargin": 99.0,
                                                "profitMargin": 99.0}),
    ]})
    reading = FA.acceleration_reading(store, "X", "US", "2019-09-01")
    assert reading["status"] == FA.NO_PREVIOUS_FILING
    assert reading["currentReportPeriod"] == "2019-Q1"
    assert all(v is None for v in reading["deltas"].values())
