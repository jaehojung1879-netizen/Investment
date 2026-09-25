"""Decoding `alotMatter.json`'s `se`/`stock_knd` into a dividend AMOUNT
lineage, from live-observed values only -- never guessed, never dated."""
from __future__ import annotations

from pipeline import kr_dividend_amount_lineage as DAL


def _row(rcept_no, receipt_date, category, stock_kind, thstrm, frmtrm=None,
        lwfr=None, bsns_year=None, ticker="000030"):
    return {
        "id": f"x:{rcept_no}:{category}:{stock_kind}", "ticker": ticker,
        "corpCode": "00123", "corpName": "x", "receiptNo": rcept_no,
        "receiptDate": receipt_date, "categoryRaw": category, "stockKindRaw": stock_kind,
        "currentPeriodRaw": thstrm, "priorPeriodRaw": frmtrm, "priorPriorPeriodRaw": lwfr,
        "decisionDate": None, "recordDate": None, "exDate": None, "effectiveDate": None,
        "lastTradingDate": None, "paymentDate": None,
        "endpointConfidence": "CONFIRMED_LIVE_2026_09_25", "source": "DART:alotMatter",
        "collectedAt": "2026-09-25T00:00:00Z", "bsnsYear": bsns_year,
    }


# --------------------------------------------------------------------------- #
# parse_amount
# --------------------------------------------------------------------------- #
def test_a_dash_is_not_stated_never_zero():
    assert DAL.parse_amount("-") is None
    assert DAL.parse_amount("") is None
    assert DAL.parse_amount(None) is None


def test_comma_grouped_numbers_parse_with_sign_preserved():
    assert DAL.parse_amount("1,059,157") == 1059157.0
    assert DAL.parse_amount("-537,688") == -537688.0
    assert DAL.parse_amount("500") == 500.0


# --------------------------------------------------------------------------- #
# decode_row -- every live-observed value decodes, nothing else does
# --------------------------------------------------------------------------- #
def test_every_live_observed_se_value_decodes():
    for raw, metric in DAL.KNOWN_SE_RAW_VALUES.items():
        row = _row("20200101000001", "2020-01-01", raw, "보통주", "100")
        decoded = DAL.decode_row(row)
        assert decoded["metric"] == metric


def test_every_live_observed_stock_kind_value_decodes():
    for raw, cls in DAL.KNOWN_STOCK_KIND_RAW_VALUES.items():
        row = _row("20200101000001", "2020-01-01", "주당 현금배당금(원)", raw, "100")
        decoded = DAL.decode_row(row)
        assert decoded["shareClass"] == cls


def test_an_unknown_category_is_never_guessed():
    row = _row("20200101000001", "2020-01-01", "완전히 새로운 항목", "보통주", "100")
    decoded = DAL.decode_row(row)
    assert decoded["metric"] is None


def test_an_unknown_stock_kind_is_never_guessed():
    row = _row("20200101000001", "2020-01-01", "주당 현금배당금(원)", "새로운 종류", "100")
    decoded = DAL.decode_row(row)
    assert decoded["shareClass"] is None


def test_jong_ryu_ju_sik_is_not_folded_into_preferred():
    # 종류주식 ("class stock") is a distinct Korean Commercial Act term, not
    # a synonym for 우선주 (preferred) -- kept as its own class.
    row = _row("20200101000001", "2020-01-01", "주당 현금배당금(원)", "종류주식", "100")
    decoded = DAL.decode_row(row)
    assert decoded["shareClass"] == DAL.OTHER_CLASS_SHARE


def test_a_dash_stock_kind_is_unspecified_never_assumed_common():
    row = _row("20200101000001", "2020-01-01", "(연결)당기순이익(백만원)", "-", "1000")
    decoded = DAL.decode_row(row)
    assert decoded["shareClass"] == DAL.UNSPECIFIED_CLASS


# --------------------------------------------------------------------------- #
# dividend_amount_lineage_for_ticker
# --------------------------------------------------------------------------- #
def test_only_cash_dps_and_stock_dps_enter_the_amount_lineage():
    rows = [
        _row("20200301000001", "2020-03-01", "주당 현금배당금(원)", "보통주", "500", bsns_year=2019),
        _row("20200301000001", "2020-03-01", "현금배당수익률(%)", "보통주", "2.5", bsns_year=2019),
        _row("20200301000001", "2020-03-01", "(연결)당기순이익(백만원)", "-", "10000", bsns_year=2019),
    ]
    lineage = DAL.dividend_amount_lineage_for_ticker(rows)
    assert len(lineage["entries"]) == 1
    assert lineage["entries"][0]["metric"] == DAL.CASH_DPS
    assert lineage["entries"][0]["value"] == 500.0


def test_a_dash_current_period_produces_no_entry_never_a_fabricated_zero():
    rows = [_row("20200301000001", "2020-03-01", "주당 현금배당금(원)", "보통주", "-", bsns_year=2019)]
    lineage = DAL.dividend_amount_lineage_for_ticker(rows)
    assert lineage["entries"] == []


def test_common_and_preferred_entries_are_kept_separate():
    rows = [
        _row("20200301000001", "2020-03-01", "주당 현금배당금(원)", "보통주", "500", bsns_year=2019),
        _row("20200301000001", "2020-03-01", "주당 현금배당금(원)", "우선주", "550", bsns_year=2019),
    ]
    lineage = DAL.dividend_amount_lineage_for_ticker(rows)
    assert len(lineage["entries"]) == 2
    by_class = {e["shareClass"]: e["value"] for e in lineage["entries"]}
    assert by_class[DAL.COMMON] == 500.0
    assert by_class[DAL.PREFERRED] == 550.0


def test_every_entry_cites_its_own_receipt():
    rows = [_row("20200301000001", "2020-03-01", "주당 현금배당금(원)", "보통주", "500", bsns_year=2019)]
    entry = DAL.dividend_amount_lineage_for_ticker(rows)["entries"][0]
    assert entry["sourceReceiptNumber"] == "20200301000001"
    assert entry["sourceReceiptDate"] == "2020-03-01"


def test_self_consistency_agrees_when_two_filings_state_the_same_figure():
    rows = [
        _row("20200301000001", "2020-03-01", "주당 현금배당금(원)", "보통주", "500", bsns_year=2019),
        _row("20210301000001", "2021-03-01", "주당 현금배당금(원)", "보통주", "600",
             frmtrm="500", bsns_year=2020),
    ]
    lineage = DAL.dividend_amount_lineage_for_ticker(rows)
    assert lineage["selfConsistencyDisagreements"] == 0
    assert len(lineage["selfConsistency"]) == 1
    assert lineage["selfConsistency"][0]["agrees"] is True


def test_self_consistency_flags_a_real_disagreement_never_silently_resolved():
    rows = [
        _row("20200301000001", "2020-03-01", "주당 현금배당금(원)", "보통주", "500", bsns_year=2019),
        _row("20210301000001", "2021-03-01", "주당 현금배당금(원)", "보통주", "600",
             frmtrm="450", bsns_year=2020),
    ]
    lineage = DAL.dividend_amount_lineage_for_ticker(rows)
    assert lineage["selfConsistencyDisagreements"] == 1
    assert lineage["selfConsistency"][0]["agrees"] is False
    assert lineage["selfConsistency"][0]["primaryValue"] == 500.0
    assert lineage["selfConsistency"][0]["laterFilingPriorPeriodValue"] == 450.0


def test_no_date_role_other_than_receipt_is_ever_produced():
    rows = [_row("20200301000001", "2020-03-01", "주당 현금배당금(원)", "보통주", "500", bsns_year=2019)]
    entry = DAL.dividend_amount_lineage_for_ticker(rows)["entries"][0]
    for forbidden in ("exDate", "recordDate", "decisionDate", "paymentDate"):
        assert forbidden not in entry


def test_stock_dps_is_included_alongside_cash_dps():
    rows = [_row("20200301000001", "2020-03-01", "주당 주식배당(주)", "보통주", "0.1", bsns_year=2019)]
    lineage = DAL.dividend_amount_lineage_for_ticker(rows)
    assert lineage["entries"][0]["metric"] == DAL.STOCK_DPS


# --------------------------------------------------------------------------- #
# cross_validate_against_yahoo_by_fiscal_year -- amount agreement, not a
# date-role claim
# --------------------------------------------------------------------------- #
def _cash_dps_entry(fiscal_year, value, receipt_no="r1", receipt_date="2020-03-01"):
    return {"fiscalYear": fiscal_year, "shareClass": DAL.COMMON, "metric": DAL.CASH_DPS,
           "value": value, "sourceReceiptNumber": receipt_no, "sourceReceiptDate": receipt_date}


def test_exact_match_when_a_real_yahoo_event_falls_in_the_fiscal_year_window():
    # Mirrors the real measured case: 000100.KS FY2015 CASH_DPS 2000.0
    # against a real Yahoo event dated 2015-12-29 of 2000.00004.
    entries = [_cash_dps_entry(2015, 2000.0)]
    yahoo = [{"date": "2015-12-29", "amountPerShare": 2000.0000383290744}]
    rows = DAL.cross_validate_against_yahoo_by_fiscal_year(entries, yahoo)
    assert rows[0]["status"] == DAL.EXACT_MATCH


def test_no_yahoo_event_in_window_is_its_own_status_never_a_silent_pass():
    entries = [_cash_dps_entry(2015, 2000.0)]
    rows = DAL.cross_validate_against_yahoo_by_fiscal_year(entries, [])
    assert rows[0]["status"] == DAL.NO_YAHOO_EVENT_IN_WINDOW
    assert rows[0]["yahooWindowSum"] is None


def test_amount_mismatch_beyond_tolerance_is_flagged_not_averaged_away():
    entries = [_cash_dps_entry(2015, 2000.0)]
    yahoo = [{"date": "2015-12-29", "amountPerShare": 1000.0}]
    rows = DAL.cross_validate_against_yahoo_by_fiscal_year(entries, yahoo)
    assert rows[0]["status"] == DAL.AMOUNT_MISMATCH


def test_multiple_yahoo_events_in_window_are_summed_not_only_the_first():
    entries = [_cash_dps_entry(2021, 1200.0)]
    yahoo = [{"date": "2021-12-15", "amountPerShare": 600.0},
            {"date": "2022-03-15", "amountPerShare": 600.0}]
    rows = DAL.cross_validate_against_yahoo_by_fiscal_year(entries, yahoo)
    assert rows[0]["yahooEventsInWindow"] == 2
    assert rows[0]["yahooWindowSum"] == 1200.0
    assert rows[0]["status"] == DAL.EXACT_MATCH


def test_an_event_outside_the_window_is_never_counted():
    entries = [_cash_dps_entry(2015, 2000.0)]
    yahoo = [{"date": "2014-01-01", "amountPerShare": 2000.0}]
    rows = DAL.cross_validate_against_yahoo_by_fiscal_year(entries, yahoo)
    assert rows[0]["status"] == DAL.NO_YAHOO_EVENT_IN_WINDOW


def test_preferred_class_entries_are_never_cross_validated_against_yahoo():
    entries = [{"fiscalYear": 2015, "shareClass": DAL.PREFERRED, "metric": DAL.CASH_DPS,
               "value": 2050.0, "sourceReceiptNumber": "r1", "sourceReceiptDate": "2016-03-30"}]
    yahoo = [{"date": "2015-12-29", "amountPerShare": 2050.0}]
    rows = DAL.cross_validate_against_yahoo_by_fiscal_year(entries, yahoo)
    assert rows == []


def test_every_entry_cites_its_own_receipt_in_the_cross_validation_row():
    entries = [_cash_dps_entry(2015, 2000.0, receipt_no="20160330001687")]
    rows = DAL.cross_validate_against_yahoo_by_fiscal_year(entries, [])
    assert rows[0]["sourceReceiptNumber"] == "20160330001687"
