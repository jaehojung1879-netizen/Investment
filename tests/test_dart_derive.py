"""Turning filings into factor inputs, where the silent errors live.

Every assertion here is a number that would come out wrong without erroring:
a quarter read as a year, a nine-month cash flow annualised, a ROE on negative
equity, a growth rate comparing a quarter with a year. The column semantics
these are built on were measured from 2,927 real filings and 84 companies, not
assumed.
"""
from __future__ import annotations

import pytest

from pipeline import dart_derive as D


# When each report actually reaches the reader, from the probe's 2023 samples:
# the quarterlies 45 days after period end, the annual one the following March.
# The fixture uses real dates because the contract checks the ordering — a
# filing cannot have been readable before the period it reports on ended.
RECEIPT = {"11013": (0, "05-15"), "11012": (0, "08-14"),
           "11014": (0, "11-14"), "11011": (1, "03-15")}


def _filing(year, code, **accounts):
    """One stored filing. `accounts` maps name -> (statement, amounts dict)."""
    offset, day = RECEIPT[code]
    return {
        "ticker": "005930.KS", "fiscalYear": year, "reportCode": code,
        "availableFrom": f"{year + offset}-{day}", "currency": "KRW",
        # The provenance the collector attaches and the contract requires.
        # A fixture missing it passes the derivation and is rejected by the
        # store — which is exactly the failure these tests exist to catch.
        "source": "DART:fnlttSinglAcntAll:CFS", "fsDiv": "CFS",
        "collectedAt": "2026-09-01T00:00:00Z",
        "accounts": {name: {"statement": stmt, "amounts": amounts}
                     for name, (stmt, amounts) in accounts.items()},
    }


# --------------------------------------------------------------------------- #
# The column semantics — measured, and different per statement
# --------------------------------------------------------------------------- #
def test_a_quarterly_income_figure_comes_from_the_cumulative_column():
    """`thstrm_amount` on a Q3 report is that quarter alone.

    Reading it as the period-to-date is one quarter treated as three.
    """
    q3 = _filing(2023, "11014", 매출액=("IS", {"thstrm_amount": 300.0,
                                            "thstrm_add_amount": 900.0}))
    assert D.cumulative_amount(q3, "매출액") == 900.0


def test_an_annual_income_figure_comes_from_the_period_column():
    """The annual report states no cumulative column — measured at 0.0%."""
    fy = _filing(2023, "11011", 매출액=("IS", {"thstrm_amount": 1200.0}))
    assert D.cumulative_amount(fy, "매출액") == 1200.0


def test_cash_flow_has_one_column_and_it_is_already_cumulative():
    """Measured over 84 companies: (Q1+H1+Q3)/FY = 1.31, which is double
    counting. Standalone quarters would have given 0.75."""
    q3 = _filing(2023, "11014",
                 영업활동현금흐름=("CF", {"thstrm_amount": 700.0}))
    assert D.cumulative_amount(q3, "영업활동현금흐름") == 700.0


def test_income_and_cash_flow_are_read_by_different_rules_in_one_filing():
    """The error this prevents: a Q3 operating cash flow read as three months
    and annualised is four times too large, and nothing raises."""
    q3 = _filing(2023, "11014",
                 매출액=("IS", {"thstrm_amount": 300.0, "thstrm_add_amount": 900.0}),
                 영업활동현금흐름=("CF", {"thstrm_amount": 700.0}))

    assert D.cumulative_amount(q3, "매출액") == 900.0        # 누계 컬럼
    assert D.cumulative_amount(q3, "영업활동현금흐름") == 700.0  # 단일 컬럼


def test_a_balance_is_taken_as_stated_and_never_accumulated():
    q3 = _filing(2023, "11014", 자본총계=("BS", {"thstrm_amount": 5000.0}))
    assert D.level_amount(q3, "자본총계") == 5000.0


# --------------------------------------------------------------------------- #
# TTM is a rollforward
# --------------------------------------------------------------------------- #
def _chain():
    """FY2022 = 1000, Q3 2022 cum = 700, Q3 2023 cum = 900."""
    return D.index_filings([
        _filing(2022, "11011", 당기순이익=("IS", {"thstrm_amount": 1000.0})),
        _filing(2022, "11014", 당기순이익=("IS", {"thstrm_amount": 250.0,
                                             "thstrm_add_amount": 700.0})),
        _filing(2023, "11014", 당기순이익=("IS", {"thstrm_amount": 320.0,
                                             "thstrm_add_amount": 900.0})),
    ])


def test_the_trailing_year_is_last_year_minus_its_stage_plus_this_one():
    value, basis = D.trailing_twelve_months(_chain(), 2023, "11014", "당기순이익")

    assert value == 1000.0 - 700.0 + 900.0 == 1200.0
    assert basis == D.BASIS_ROLLFORWARD


def test_the_annual_report_is_the_trailing_year_as_filed():
    value, basis = D.trailing_twelve_months(_chain(), 2022, "11011", "당기순이익")
    assert value == 1000.0 and basis == D.BASIS_ANNUAL


def test_a_broken_chain_yields_none_rather_than_an_annualisation():
    """9개월 x 4/3 은 아무도 보고하지 않은 분기를 지어내는 것입니다."""
    partial = D.index_filings([
        _filing(2023, "11014", 당기순이익=("IS", {"thstrm_amount": 320.0,
                                             "thstrm_add_amount": 900.0}))])
    value, basis = D.trailing_twelve_months(partial, 2023, "11014", "당기순이익")

    assert value is None and basis == D.BASIS_INCOMPLETE


def test_the_basis_is_published_so_the_two_kinds_are_not_confused():
    _, annual = D.trailing_twelve_months(_chain(), 2022, "11011", "당기순이익")
    _, rolled = D.trailing_twelve_months(_chain(), 2023, "11014", "당기순이익")
    assert annual != rolled


# --------------------------------------------------------------------------- #
# Ratios
# --------------------------------------------------------------------------- #
def _full(year, code, **kw):
    defaults = dict(ni=100.0, rev=1000.0, op=150.0, cf=200.0, capex=50.0,
                    equity=800.0, debt=400.0)
    defaults.update(kw)
    return _filing(
        year, code,
        당기순이익=("IS", {"thstrm_amount": defaults["ni"]}),
        매출액=("IS", {"thstrm_amount": defaults["rev"]}),
        영업이익=("IS", {"thstrm_amount": defaults["op"]}),
        영업활동현금흐름=("CF", {"thstrm_amount": defaults["cf"]}),
        유형자산의취득=("CF", {"thstrm_amount": defaults["capex"]}),
        자본총계=("BS", {"thstrm_amount": defaults["equity"]}),
        부채총계=("BS", {"thstrm_amount": defaults["debt"]}),
    )


def test_quality_comes_out_of_the_statements_alone():
    by_key = D.index_filings([_full(2023, "11011")])
    fields, basis = D.derive_fields(by_key, 2023, "11011")

    assert fields["roe"] == pytest.approx(100.0 / 800.0)
    assert fields["operatingMargin"] == pytest.approx(150.0 / 1000.0)
    assert fields["profitMargin"] == pytest.approx(100.0 / 1000.0)
    assert fields["debtToEquity"] == pytest.approx(400.0 / 800.0)
    assert basis["sharesAvailable"] is False


def test_negative_equity_yields_no_roe_rather_than_a_sign_flip():
    """A distressed company would otherwise rank as a quality name."""
    by_key = D.index_filings([_full(2023, "11011", equity=-500.0)])
    fields, _ = D.derive_fields(by_key, 2023, "11011")

    assert "roe" not in fields
    assert "debtToEquity" not in fields


def test_a_zero_denominator_is_refused():
    by_key = D.index_filings([_full(2023, "11011", rev=0.0)])
    fields, _ = D.derive_fields(by_key, 2023, "11011")
    assert "operatingMargin" not in fields and "profitMargin" not in fields


def test_value_needs_shares_and_says_so_when_it_has_none():
    by_key = D.index_filings([_full(2023, "11011")])

    without, basis_without = D.derive_fields(by_key, 2023, "11011")
    with_shares, basis_with = D.derive_fields(by_key, 2023, "11011", shares=10.0)

    assert "epsTtm" not in without and basis_without["sharesAvailable"] is False
    assert with_shares["epsTtm"] == pytest.approx(10.0)
    assert with_shares["bookValuePerShare"] == pytest.approx(80.0)
    assert basis_with["sharesAvailable"] is True


def test_free_cash_flow_subtracts_capex_however_its_sign_is_reported():
    """Filers state the outflow positive; a sign convention must not add it."""
    by_key = D.index_filings([_full(2023, "11011", cf=200.0, capex=50.0)])
    positive, _ = D.derive_fields(by_key, 2023, "11011", shares=10.0)

    by_key_neg = D.index_filings([_full(2023, "11011", cf=200.0, capex=-50.0)])
    negative, _ = D.derive_fields(by_key_neg, 2023, "11011", shares=10.0)

    assert positive["fcfPerShare"] == pytest.approx(15.0)
    assert negative["fcfPerShare"] == pytest.approx(15.0)


def test_free_cash_flow_is_allowed_to_be_negative():
    """Unlike earnings and book value, it carries no positivity guard —
    `pit_data.POSITIVE_ONLY_NUMERATORS` excludes it deliberately."""
    by_key = D.index_filings([_full(2023, "11011", cf=10.0, capex=500.0)])
    fields, _ = D.derive_fields(by_key, 2023, "11011", shares=10.0)
    assert fields["fcfPerShare"] < 0


def test_missing_capex_leaves_fcf_out_without_disturbing_the_rest():
    filing = _full(2023, "11011")
    del filing["accounts"]["유형자산의취득"]
    by_key = D.index_filings([filing])
    fields, basis = D.derive_fields(by_key, 2023, "11011", shares=10.0)

    assert "fcfPerShare" not in fields
    assert basis["freeCashFlowAvailable"] is False
    assert fields["epsTtm"] == pytest.approx(10.0)


def test_growth_compares_twelve_months_with_twelve_months():
    by_key = D.index_filings([_full(2022, "11011", ni=100.0),
                              _full(2023, "11011", ni=125.0)])
    fields, _ = D.derive_fields(by_key, 2023, "11011")
    assert fields["earningsGrowth"] == pytest.approx(0.25)


def test_growth_from_a_loss_uses_the_magnitude_so_the_sign_is_recovery():
    by_key = D.index_filings([_full(2022, "11011", ni=-100.0),
                              _full(2023, "11011", ni=50.0)])
    fields, _ = D.derive_fields(by_key, 2023, "11011")
    assert fields["earningsGrowth"] == pytest.approx(1.5)


# --------------------------------------------------------------------------- #
# The emitted record
# --------------------------------------------------------------------------- #
def test_the_visibility_date_is_carried_through_untouched():
    """Re-deriving it here would be a second definition of the one field the
    whole collection exists for."""
    by_key = D.index_filings([_full(2023, "11011")])
    fields, basis = D.derive_fields(by_key, 2023, "11011")
    row = D.pit_record(by_key[(2023, "11011")], fields, basis)

    assert row["availableFrom"] == "2024-03-15", "사업보고서는 이듬해 3월"
    assert row["ticker"] == "005930.KS"
    assert row["currency"] == "KRW"


def test_a_filing_yielding_nothing_is_dropped_not_emitted_empty():
    """`FundamentalStore` returns the NEWEST visible record; an empty one
    would mask the older filing that actually had numbers."""
    barren = _filing(2023, "11011", 자산총계=("BS", {"thstrm_amount": 1.0}))
    rows = D.build_for_ticker([barren, _full(2022, "11011")])

    assert [r["reportPeriod"] for r in rows] == ["2022-11011"]


def test_rows_come_out_ordered_by_when_they_became_visible():
    rows = D.build_for_ticker([_full(2023, "11011"), _full(2021, "11011"),
                               _full(2022, "11011")])
    assert [r["availableFrom"] for r in rows] == sorted(
        r["availableFrom"] for r in rows)


def test_coverage_separates_quality_from_value():
    """"재무를 모았다"가 "밸류 슬리브가 작동한다"로 읽히지 않도록."""
    rows = D.build_for_ticker([_full(2022, "11011"), _full(2023, "11011")])
    report = D.coverage(rows)

    assert report["qualityComplete"] is True
    assert report["valueComplete"] is False, "주식수 없이는 밸류가 서지 않는다"
    assert report["fieldCoveragePct"]["roe"] == 100.0
    assert report["fieldCoveragePct"]["epsTtm"] == 0.0


# --------------------------------------------------------------------------- #
# Share counts
# --------------------------------------------------------------------------- #
def test_treasury_stock_is_removed_from_the_share_count():
    """Per-share figures on the issued total understate every company with a
    buyback behind it, by exactly the amount that made it worth doing."""
    from pipeline import dart_fundamentals as DF

    assert DF.share_count({"istc_totqy": "1,000,000", "tesstk_co": "100,000"}) == 900000.0
    assert DF.share_count({"istc_totqy": "1,000,000"}) == 1000000.0


def test_an_unusable_share_count_is_none_rather_than_zero():
    from pipeline import dart_fundamentals as DF

    for row in ({}, {"istc_totqy": "0"}, {"istc_totqy": "-5"},
                {"istc_totqy": "1,000", "tesstk_co": "1,000"}):
        assert DF.share_count(row) is None


# --------------------------------------------------------------------------- #
# The contract round trip
#
# The emitted rows were rejected wholesale by `FundamentalStore.from_jsonl` for
# want of `reportDate` — 2,897 written, 0 loaded, and no error anywhere. In
# production that would have read as "PIT 재무 없음" and the value and quality
# sleeves would have stayed dark for a reason nobody could see.
# --------------------------------------------------------------------------- #
def test_an_emitted_row_is_accepted_by_the_store_that_reads_it(tmp_path):
    import json

    from pipeline import pit_data

    rows = D.build_for_ticker([_full(2022, "11011"), _full(2023, "11011")])
    path = tmp_path / "pit.jsonl"
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                    encoding="utf-8")

    store = pit_data.FundamentalStore.from_jsonl(path)

    assert store.diagnostics["rowsRead"] == len(rows)
    assert store.diagnostics["rowsRejected"] == 0, store.diagnostics["errors"][:3]
    assert store.available


def test_the_period_end_is_emitted_and_precedes_the_visibility_date():
    """The contract refuses a filing that claims to have been readable before
    the period it reports on had ended — which is the look-ahead itself."""
    rows = D.build_for_ticker([_full(2023, "11011")])
    row = rows[0]

    assert row["reportDate"] == "2023-12-31"
    assert row["reportDate"] <= row["publicationDate"] <= row["availableFrom"]


def test_every_report_code_has_a_period_end():
    from pipeline import dart_fundamentals as DF

    for code in DF.REPORT_CODES:
        assert DF.period_end(2023, code) is not None
    assert DF.period_end(2023, "11013") == "2023-03-31"
    assert DF.period_end(2023, "11014") == "2023-09-30"


def test_a_filing_is_invisible_before_it_was_filed(tmp_path):
    """The whole point, end to end: the 2023 annual report is not readable in
    January 2023, whatever period it describes."""
    import json

    from pipeline import pit_data

    rows = D.build_for_ticker([_full(2022, "11011"), _full(2023, "11011")])
    path = tmp_path / "pit.jsonl"
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                    encoding="utf-8")
    store = pit_data.FundamentalStore.from_jsonl(path)

    early, early_status = store.visible_as_of("005930.KS", "2021-01-01")
    later, later_status = store.visible_as_of("005930.KS", "2023-12-31")

    assert early == {} and early_status == pit_data.UNAVAILABLE
    assert later.get("roe") is not None and later_status == pit_data.PIT_EXACT
