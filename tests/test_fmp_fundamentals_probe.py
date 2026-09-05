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


# --------------------------------------------------------------------------- #
# The vendor's refusal is evidence, not noise
#
# The first run reported every statement call as "non-JSON response (HTTP 402)"
# — the body was read and then discarded — and that bare status became "FMP
# dropped statements from the free tier". FMP's 402 body names the plan an
# endpoint needs, so the sentence it sent IS the finding.
# --------------------------------------------------------------------------- #
def test_the_refusal_body_is_kept_and_trimmed():
    assert P.body_head(b'{"Error Message": "Exclusive Endpoint"}') \
        == '{"Error Message": "Exclusive Endpoint"}'
    assert P.body_head(b"a" * 500, limit=10) == "a" * 10
    assert P.body_head(None) == ""
    assert P.body_head(b"line one\nline two") == "line one line two"


# --------------------------------------------------------------------------- #
# A dead key and a limited plan are different problems with different fixes
# --------------------------------------------------------------------------- #
def _check(served, status=200, body=""):
    """One endpoint check's result. Named apart from this module's other
    `_row`, which builds a statement PERIOD — two different shapes."""
    return {"served": served, "httpStatus": status, "bodyHead": body}


def test_a_live_key_refused_only_on_statements_is_a_plan_limit():
    report = P.diagnose(
        {"profile": _check(True), "quote": _check(True)},
        {"stable": _check(False, 402, "Exclusive Endpoint: upgrade to Starter"),
         "v3": _check(False, 402, "Exclusive Endpoint: upgrade to Starter")})
    assert report["verdict"] == "KEY_LIVE_PLAN_EXCLUDES_STATEMENTS"
    assert "Starter" in report["refusalBodies"]["stable"]


def test_a_key_refused_everywhere_is_the_key_not_the_plan():
    report = P.diagnose(
        {"profile": _check(False, 401), "quote": _check(False, 401)},
        {"stable": _check(False, 401), "v3": _check(False, 401)})
    assert report["verdict"] == "KEY_NOT_LIVE"
    assert "no subscription changes that" in report["meaning"]


def test_statements_served_under_either_shape_opens_the_route():
    report = P.diagnose(
        {"profile": _check(True), "quote": _check(True)},
        {"stable": _check(False, 402), "v3": _check(True)})
    assert report["verdict"] == "STATEMENTS_AVAILABLE"
    assert report["servedBases"] == ["v3"]


def test_both_url_shapes_are_asked_rather_than_assumed():
    # /api/v3 was retired for statements, but a plan can expose them
    # differently, and "wrong path" and "excluded by plan" have different fixes.
    assert set(P.BASES) == {"stable", "v3"}
    assert P.BASES["v3"].endswith("/api/v3")


# --------------------------------------------------------------------------- #
# The filing date under both spellings FMP has shipped
#
# `/api/v3` carried a misspelt `fillingDate`; the `/stable` replacement spells
# it `filingDate`. The first response this repo was ever served came from
# `/stable`, so a probe that knew only the v3 spelling would have counted zero
# filing dates on rows that all carried one — and reported "no point-in-time"
# about the one source that has it.
# --------------------------------------------------------------------------- #
def test_the_stable_spelling_of_the_filing_date_is_counted():
    rows = [{"date": "2026-06-27", "filingDate": "2026-07-31"},
            {"date": "2026-03-28", "filingDate": "2026-05-01"}]
    entry = P.parse_statement_response("income", rows)
    assert entry["fillingDateCoverage"] == 2
    assert entry["fillingDateField"] == "filingDate"


def test_the_legacy_spelling_is_still_counted():
    rows = [{"date": "2023-12-31", "fillingDate": "2024-02-01"}]
    entry = P.parse_statement_response("income", rows)
    assert entry["fillingDateCoverage"] == 1
    assert entry["fillingDateField"] == "fillingDate"


def test_rows_with_no_filing_date_under_either_spelling_report_no_field():
    entry = P.parse_statement_response("income", [{"date": "2023-12-31"}])
    assert entry["fillingDateCoverage"] == 0
    assert entry["fillingDateField"] is None


def test_accepted_date_is_counted_separately_from_the_filing_date():
    rows = [{"date": "2026-06-27", "filingDate": "2026-07-31",
             "acceptedDate": "2026-07-31 18:04:19"},
            {"date": "2026-03-28", "filingDate": "2026-05-01"}]
    entry = P.parse_statement_response("income", rows)
    assert entry["acceptedDateCoverage"] == 1


# --------------------------------------------------------------------------- #
# The limit cap — the measurement that separates "the plan excludes
# statements" from "we asked for more history than the plan serves"
#
# The run that produced this test got HTTP 200 for limit=4 and HTTP 402 for
# limit=400, same endpoint, same key, same minute. Only `limit` varied, so
# only `limit` can be blamed — and the cap is a number to find.
# --------------------------------------------------------------------------- #
def _fake_requests(script):
    """Replaces P._request with a canned status/body per call, in order."""
    calls = []

    def fake(url, timeout=30):
        calls.append(url)
        status, body = script[min(len(calls) - 1, len(script) - 1)]
        return status, body, "" if status == 200 else f"HTTP {status}"

    return fake, calls


def test_the_ladder_stops_at_the_first_refusal_instead_of_spending_quota(monkeypatch):
    fake, calls = _fake_requests([
        (200, b'[{"date": "2026-06-27"}]'),
        (402, b'{"Error Message": "Special Endpoint : upgrade your plan"}'),
    ])
    monkeypatch.setattr(P, "_request", fake)
    monkeypatch.setattr(P.time, "sleep", lambda *_: None)
    cap = P.find_limit_cap("k", ladder=(4, 20, 50, 100))
    assert cap["largestServed"] == 4
    assert cap["refusedAt"] == 20
    assert len(calls) == 2          # 50 and 100 were never bought


def test_the_refusal_body_survives_into_the_cap_report(monkeypatch):
    fake, _ = _fake_requests([
        (200, b'[{"date": "2026-06-27"}]'),
        (402, b'{"Error Message": "Special Endpoint : upgrade your plan"}'),
    ])
    monkeypatch.setattr(P, "_request", fake)
    monkeypatch.setattr(P.time, "sleep", lambda *_: None)
    cap = P.find_limit_cap("k", ladder=(4, 20))
    assert "Special Endpoint" in cap["refusalBody"]


def test_a_two_hundred_carrying_an_error_body_is_a_refusal_not_a_served_rung(monkeypatch):
    # FMP answers some limits with 200 and an error object. Counting that as
    # served is exactly the mistake the whole probe exists to avoid.
    fake, _ = _fake_requests([(200, b'{"Error Message": "Limit Reach"}')])
    monkeypatch.setattr(P, "_request", fake)
    monkeypatch.setattr(P.time, "sleep", lambda *_: None)
    cap = P.find_limit_cap("k", ladder=(4, 20))
    assert cap["largestServed"] is None
    assert cap["refusedAt"] == 4


def test_a_ladder_served_all_the_way_up_reports_no_refusal(monkeypatch):
    fake, _ = _fake_requests([(200, b'[{"date": "2026-06-27"}]')])
    monkeypatch.setattr(P, "_request", fake)
    monkeypatch.setattr(P.time, "sleep", lambda *_: None)
    cap = P.find_limit_cap("k", ladder=(4, 20, 50))
    assert cap["largestServed"] == 50
    assert cap["refusedAt"] is None
    assert cap["refusalBody"] is None
