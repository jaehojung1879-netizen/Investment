"""What a stored DART filing has to mean.

The network half runs only in CI. What is pinned here is everything that
decides whether a stored row is usable: the receipt date that licenses its use,
the amounts that must not be invented, the account matching that must not be
loose, and the append-only identity that makes a restatement a new record
rather than an overwrite of what was actually visible at the time.
"""
from __future__ import annotations

import pytest

from pipeline import dart_fundamentals as DF


# --------------------------------------------------------------------------- #
# The receipt date — the field the whole collection exists for
# --------------------------------------------------------------------------- #
def test_the_receipt_date_is_the_head_of_the_receipt_number():
    assert DF.receipt_date("20230515000123") == "2023-05-15"


def test_a_missing_or_malformed_receipt_number_is_none_not_a_fallback():
    """There is no second source for it. Guessing would void the replay."""
    for value in (None, "", "2023", "notadate00000", "abcdefgh0001"):
        assert DF.receipt_date(value) is None


def test_an_impossible_calendar_date_is_refused():
    """A 13th month is a parse that happened to produce eight digits."""
    assert DF.receipt_date("20231315000001") is None
    assert DF.receipt_date("20230015000001") is None
    assert DF.receipt_date("20230500000001") is None


# --------------------------------------------------------------------------- #
# Amounts
# --------------------------------------------------------------------------- #
def test_thousands_separators_and_both_negative_conventions():
    assert DF.parse_amount("1,234,567") == 1234567.0
    assert DF.parse_amount("-1,234") == -1234.0
    assert DF.parse_amount("(1,234)") == -1234.0, "회계식 괄호 음수"


def test_an_unstated_line_is_none_and_never_zero():
    """0 is a number a filer stated. Blank is a line they did not.

    Returning 0.0 here would put a fabricated figure into every ratio built
    on it — a zero equity base, a zero margin — and none of it would error.
    """
    for blank in ("", "-", "—", "–", "N/A", None):
        assert DF.parse_amount(blank) is None
    assert DF.parse_amount("0") == 0.0


def test_text_that_is_not_a_number_is_refused():
    assert DF.parse_amount("해당사항없음") is None
    assert DF.parse_amount("1,2,3.4.5") is None


# --------------------------------------------------------------------------- #
# Account matching
# --------------------------------------------------------------------------- #
def test_matching_is_exact_so_a_ratio_is_never_read_as_an_amount():
    """'영업이익률' is a percentage; '영업이익' is a currency amount.

    A substring rule would fold them together and rank companies on two
    different units without erroring.
    """
    assert DF.match_account("영업이익") == "영업이익"
    assert DF.match_account("영업이익률") is None
    assert DF.match_account("영업이익증가율") is None


def test_filer_aliases_and_spacing_both_resolve():
    assert DF.match_account("수익(매출액)") == "매출액"
    assert DF.match_account("영업수익") == "매출액"
    assert DF.match_account(" 영업 이익 ") == "영업이익"
    assert DF.match_account("영업활동으로인한현금흐름") == "영업활동현금흐름"


def test_an_unrelated_account_is_not_forced_into_a_bucket():
    assert DF.match_account("이연법인세자산") is None


# --------------------------------------------------------------------------- #
# The record
# --------------------------------------------------------------------------- #
def _rows(**overrides):
    base = [
        {"account_nm": "매출액", "thstrm_amount": "1,000",
         "thstrm_add_amount": "3,000", "rcept_no": "20230515000123",
         "sj_div": "IS", "account_id": "ifrs-full_Revenue"},
        {"account_nm": "영업이익", "thstrm_amount": "100",
         "rcept_no": "20230515000123", "sj_div": "IS"},
        {"account_nm": "자본총계", "thstrm_amount": "5,000",
         "rcept_no": "20230515000123", "sj_div": "BS"},
    ]
    for row in base:
        row.update(overrides)
    return base


def test_a_record_carries_the_visibility_date_not_the_period():
    record, reason = DF.build_record(
        ticker="005930.KS", stock_code="005930", corp_code="00126380",
        fiscal_year=2023, report_code="11013", rows=_rows(),
        fs_div=DF.FS_CONSOLIDATED, collected_at="2026-08-30T00:00:00Z")

    assert reason == ""
    assert record["availableFrom"] == "2023-05-15"
    assert record["fiscalYear"] == 2023


def test_a_filing_without_a_receipt_date_is_refused_not_stored():
    """Storing it would leave a row that looks like coverage and cannot be used."""
    record, reason = DF.build_record(
        ticker="005930.KS", stock_code="005930", corp_code="00126380",
        fiscal_year=2023, report_code="11013",
        rows=_rows(rcept_no=None), fs_div=DF.FS_CONSOLIDATED,
        collected_at="2026-08-30T00:00:00Z")

    assert record is None and reason == "NO_RECEIPT_DATE"


def test_an_empty_or_irrelevant_response_is_refused_with_its_reason():
    for rows, expected in (([], "EMPTY_RESPONSE"),
                           ([{"account_nm": "이연법인세자산", "thstrm_amount": "1",
                              "rcept_no": "20230515000123"}], "NO_WANTED_ACCOUNTS")):
        record, reason = DF.build_record(
            ticker="005930.KS", stock_code="005930", corp_code="00126380",
            fiscal_year=2023, report_code="11013", rows=rows,
            fs_div=DF.FS_CONSOLIDATED, collected_at="2026-08-30T00:00:00Z")
        assert record is None and reason == expected


def test_both_amount_columns_are_kept_because_they_mean_different_things():
    """A Q3 income figure is nine months cumulative, not three.

    Picking one column here would decide the TTM question silently and wrongly.
    """
    record, _ = DF.build_record(
        ticker="005930.KS", stock_code="005930", corp_code="00126380",
        fiscal_year=2023, report_code="11014", rows=_rows(),
        fs_div=DF.FS_CONSOLIDATED, collected_at="2026-08-30T00:00:00Z")
    amounts = record["accounts"]["매출액"]["amounts"]

    assert amounts["thstrm_amount"] == 1000.0
    assert amounts["thstrm_add_amount"] == 3000.0


def test_the_statement_basis_is_recorded_rather_than_left_implicit():
    """CFS and OFS are different definitions; a book mixing them must say so."""
    record, _ = DF.build_record(
        ticker="005930.KS", stock_code="005930", corp_code="00126380",
        fiscal_year=2023, report_code="11011", rows=_rows(),
        fs_div=DF.FS_SEPARATE, collected_at="2026-08-30T00:00:00Z")

    assert record["fsDiv"] == DF.FS_SEPARATE
    assert record["source"].endswith(DF.FS_SEPARATE)


def test_the_earliest_receipt_date_wins_when_a_response_mixes_filings():
    rows = _rows()
    rows[1]["rcept_no"] = "20230814000999"
    record, _ = DF.build_record(
        ticker="005930.KS", stock_code="005930", corp_code="00126380",
        fiscal_year=2023, report_code="11013", rows=rows,
        fs_div=DF.FS_CONSOLIDATED, collected_at="2026-08-30T00:00:00Z")

    assert record["availableFrom"] == "2023-05-15"
    assert len(record["receiptNos"]) == 2


# --------------------------------------------------------------------------- #
# Identity and resumption
# --------------------------------------------------------------------------- #
def test_the_id_is_the_filing_so_a_rerun_skips_what_it_holds():
    assert DF.record_id("005930.KS", 2023, "11013") == "005930.KS:2023:11013"


def test_the_work_list_skips_what_is_already_on_disk():
    held = {DF.record_id("A.KS", 2015, "11011")}
    pending = DF.work_list(["A.KS"], [2015], held, report_codes=["11011", "11012"])

    assert pending == [("A.KS", 2015, "11012")]


def test_years_before_dart_serves_them_are_not_queued():
    """DART starts at 2015; the replay starts 2013. Queuing 2013 spends the
    budget on responses that cannot exist."""
    pending = DF.work_list(["A.KS"], [2013, 2014, 2015], set(), report_codes=["11011"])

    assert [year for _, year, _ in pending] == [2015]


def test_the_work_list_is_oldest_first_and_stable():
    """A resumed backfill that reshuffles re-fetches what it already bought,
    and a run that dies halfway should have bought the scarcer early end."""
    first = DF.work_list(["B.KS", "A.KS"], [2016, 2015], set(), report_codes=["11011"])

    assert [year for _, year, _ in first] == [2015, 2015, 2016, 2016]
    assert first == DF.work_list(["A.KS", "B.KS"], [2015, 2016], set(),
                                 report_codes=["11011"])


def test_progress_is_reported_against_the_whole_job_not_the_slice():
    assert DF.progress(300, 100) == {
        "collected": 300, "absent": 0, "pending": 100,
        "total": 400, "completePct": 75.0}
    assert DF.progress(0, 0)["completePct"] is None


# --------------------------------------------------------------------------- #
# Statuses
# --------------------------------------------------------------------------- #
def test_a_key_problem_and_a_spent_quota_are_told_apart():
    """One means stop forever, the other means come back tomorrow."""
    assert "010" in DF.FATAL_STATUSES and "011" in DF.FATAL_STATUSES
    assert DF.QUOTA_STATUS not in DF.FATAL_STATUSES
    assert "등록되지 않은" in DF.describe_status("010")
    assert "요청 제한" in DF.describe_status(DF.QUOTA_STATUS)


def test_an_unknown_status_is_named_as_unknown():
    assert "알 수 없는" in DF.describe_status("777")


def test_a_shard_is_one_fiscal_year():
    assert DF.shard_path("/tmp/store", 2019).name == "dart-2019.jsonl.gz"


# --------------------------------------------------------------------------- #
# Absences
#
# The first two real runs spent 950 of every 1,500 calls on filings that do not
# exist, and the work list did not shrink by a single one of them: an absence
# leaves no record, so its id stays missing and the next run asks again. Left
# alone the pending list converges to nothing but known absences and the
# backfill never finishes.
# --------------------------------------------------------------------------- #
def test_a_recorded_absence_leaves_the_work_list():
    absent = {DF.record_id("A.KS", 2016, "11013")}
    pending = DF.work_list(["A.KS"], [2016], set(), report_codes=["11013", "11012"],
                           absent_ids=absent)

    assert [code for _, _, code in pending] == ["11012"]


def test_the_deadline_separates_never_filed_from_not_filed_yet():
    """DART answers 013 for both, and they need opposite handling."""
    # 2016 Q1 was due 2016-05-15; long settled by 2026.
    assert DF.absence_is_settled(2016, "11013", "2026-08-31") is True
    # 2026 Q3 is due 2026-11-14 — it has not been filed because it cannot be.
    assert DF.absence_is_settled(2026, "11014", "2026-08-31") is False
    # The annual report falls in the following year.
    assert DF.absence_is_settled(2025, "11011", "2026-08-31") is True
    assert DF.absence_is_settled(2026, "11011", "2026-08-31") is False


def test_a_late_filer_is_given_grace_before_the_absence_is_permanent():
    """Recording it permanently the day after the deadline skips a late
    submission for good."""
    assert DF.absence_is_settled(2026, "11013", "2026-05-16") is False
    assert DF.absence_is_settled(2026, "11013", "2026-07-20") is True


def test_the_deadlines_match_the_filings_the_probe_actually_saw():
    """2023 samples landed 05-15, 08-14, 11-14 and 03-12 of the next year."""
    assert DF.filing_deadline(2023, "11013") == "2023-05-15"
    assert DF.filing_deadline(2023, "11012") == "2023-08-14"
    assert DF.filing_deadline(2023, "11014") == "2023-11-14"
    assert DF.filing_deadline(2023, "11011") == "2024-03-31"


def test_only_settled_absences_are_skipped():
    absent = {
        DF.record_id("A.KS", 2016, "11013"): {"fiscalYear": 2016, "reportCode": "11013"},
        DF.record_id("A.KS", 2026, "11014"): {"fiscalYear": 2026, "reportCode": "11014"},
    }
    settled = DF.settled_absences(absent, "2026-08-31")

    assert settled == {DF.record_id("A.KS", 2016, "11013")}


def test_a_malformed_absence_entry_is_not_skipped():
    """A row that cannot say which filing it is must not silence a fetch."""
    assert DF.settled_absences({"junk": {}}, "2026-08-31") == set()
    assert DF.settled_absences({"junk": {"fiscalYear": None,
                                         "reportCode": "11013"}}, "2026-08-31") == set()


def test_progress_counts_a_settled_absence_as_done_not_as_pending():
    """DART has answered. Leaving it pending reports a backfill that can
    never reach 100%."""
    assert DF.progress(1316, 3446, absent=950) == {
        "collected": 1316, "absent": 950, "pending": 3446,
        "total": 5712, "completePct": 39.67}


# --------------------------------------------------------------------------- #
# The share pass must not be a thing to remember
#
# `target` was a manual choice, and the GitHub mobile app cannot pass workflow
# inputs at all — so the pass the entire value sleeve depends on was reachable
# only from a desktop. Once the statements are in hand a scheduled run would
# also spend its whole budget discovering there is nothing left to fetch.
# --------------------------------------------------------------------------- #
def test_the_collector_defaults_to_finishing_both_passes():
    """No mode has to be chosen for the value sleeve to get its share counts."""
    from pathlib import Path as _Path

    source = (_Path(__file__).resolve().parent.parent / "scripts" /
              "collect_dart_fundamentals.py").read_text(encoding="utf-8")

    assert '"auto", "statements", "shares"' in source
    assert 'default="auto"' in source
    # And the fall-through actually exists rather than the flag merely naming it.
    assert 'if args.target == "auto":' in source
    assert "return collect_shares(key, codes, store, left, run_deadline)" in source


def test_the_scheduled_workflow_passes_no_mode_of_its_own():
    """A schedule supplies no inputs, so the default has to be the useful one."""
    from pathlib import Path as _Path

    root = _Path(__file__).resolve().parent.parent
    workflow = (root / ".github" / "workflows" / "dart-fundamentals.yml").read_text(
        encoding="utf-8")

    assert "inputs.target || 'auto'" in workflow
    assert 'default: "auto"' in workflow
