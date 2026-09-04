"""The FMP probe's parsing, which must hold without a vendor.

The network half can only run in CI. What is pinned here is the part that
decides what the probe's answer MEANS: that a 200-status response can still
be a free-tier refusal (FMP is known to answer that way) and must be told
apart from real data, that `fillingDate` coverage is counted against every
period returned and not just some, and that a field is reported present only
when at least one row actually carries a non-null value for it.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "probe_fmp_fundamentals", ROOT / "scripts" / "probe_fmp_fundamentals.py")
P = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = P
_spec.loader.exec_module(P)


def _row(**kw):
    base = {"date": "2023-12-31", "period": "Q4", "fillingDate": "2024-02-01"}
    base.update(kw)
    return base


# --------------------------------------------------------------------------- #
# A 200 status is not the same claim as real data — FMP answers some
# free-tier refusals with an error message in the body
# --------------------------------------------------------------------------- #
def test_a_dict_payload_is_an_error_body_not_a_zero_period_result():
    entry = P.parse_statement_response("income", {"Error Message": "Limit Reach"})
    assert entry["errorBody"] == "Limit Reach"
    assert "periodCount" not in entry


def test_an_unrecognised_error_shape_is_still_reported_not_silently_empty():
    entry = P.parse_statement_response("income", {"unexpected": "shape"})
    assert "errorBody" in entry


def test_a_non_list_non_dict_payload_is_reported_not_crashed_on():
    entry = P.parse_statement_response("income", "not json we expected")
    assert "errorBody" in entry


def test_an_empty_list_is_zero_periods_not_an_error():
    entry = P.parse_statement_response("income", [])
    assert entry == {"periodCount": 0}


# --------------------------------------------------------------------------- #
# Filing date coverage — the field the whole plan hangs on, same standard as
# DART's receipt date and SEC's `filed`
# --------------------------------------------------------------------------- #
def test_filing_date_coverage_is_counted_against_every_period_not_just_some():
    rows = [_row(fillingDate="2024-02-01"), _row(fillingDate=None)]
    entry = P.parse_statement_response("income", rows)
    assert entry["periodCount"] == 2
    assert entry["fillingDateCoverage"] == 1, "누락된 filed는 있는 것으로 세면 안 된다"


def test_the_date_range_spans_the_earliest_to_latest_period():
    rows = [_row(date="2023-12-31"), _row(date="2015-03-31"), _row(date="2020-06-30")]
    entry = P.parse_statement_response("income", rows)
    assert entry["dateRange"] == ["2015-03-31", "2023-12-31"]


# --------------------------------------------------------------------------- #
# Field presence — a candidate counts only if some row actually carries a
# non-null value for it, not merely because the key exists
# --------------------------------------------------------------------------- #
def test_a_field_present_but_always_null_is_reported_missing():
    rows = [_row(revenue=None), _row(revenue=None)]
    entry = P.parse_statement_response("income", rows)
    assert entry["fieldsFound"]["revenue"]["field"] is None


def test_a_field_with_at_least_one_real_value_is_found():
    rows = [_row(revenue=None), _row(revenue=1000)]
    entry = P.parse_statement_response("income", rows)
    assert entry["fieldsFound"]["revenue"]["field"] == "revenue"


def test_the_second_candidate_is_used_when_the_first_is_never_populated():
    """`weightedAverageShsOut` is the first candidate for shares; if a filer's
    rows only ever carry the diluted figure, that must still resolve."""
    rows = [_row(weightedAverageShsOut=None, weightedAverageShsOutDil=5000)]
    entry = P.parse_statement_response("income", rows)
    assert entry["fieldsFound"]["sharesOutstanding"]["field"] == "weightedAverageShsOutDil"


def test_balance_sheet_equity_falls_back_to_the_second_candidate():
    rows = [{"date": "2023-12-31", "totalStockholdersEquity": None, "totalEquity": 8000}]
    entry = P.parse_statement_response("balance", rows)
    assert entry["fieldsFound"]["equity"]["field"] == "totalEquity"


# --------------------------------------------------------------------------- #
# What the model actually reads
# --------------------------------------------------------------------------- #
def test_every_factor_input_the_production_model_needs_is_probed():
    covered = {item for inputs in P.FACTOR_INPUTS.values() for item in inputs}
    for needed in ("income.netIncome", "balance.equity", "income.revenue",
                  "income.operatingIncome", "balance.liabilities",
                  "cashflow.operatingCashFlow", "cashflow.capex",
                  "income.sharesOutstanding"):
        assert needed in covered, f"{needed} 없이는 만들 수 없는 팩터가 있다"
