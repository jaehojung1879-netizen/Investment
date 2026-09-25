"""What `kr_corporate_action_events.py` may and may not claim.

Synthetic fixtures only. The network half runs solely in CI via
`scripts/probe_kr_corporate_actions.py`.
"""
from __future__ import annotations

import pytest

from pipeline import kr_corporate_action_events as KCA


def _list_row(**overrides):
    base = {"rcept_no": "20190201000123", "rcept_dt": "20190201",
            "corp_code": "00126380", "corp_name": "우리은행",
            "report_nm": "합병결정", "flr_nm": "우리은행"}
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# receipt_date is reused, not reimplemented
# --------------------------------------------------------------------------- #
def test_receipt_date_is_the_same_function_dart_fundamentals_exports():
    from pipeline import dart_fundamentals as DF
    assert KCA.receipt_date is DF.receipt_date


# --------------------------------------------------------------------------- #
# disclosure-family classification (report_nm text only)
# --------------------------------------------------------------------------- #
def test_merger_report_name_classifies_as_merger():
    assert KCA.classify_disclosure_family("합병결정") == (KCA.MERGER,)


def test_share_exchange_report_name_classifies():
    assert KCA.classify_disclosure_family("주식교환·이전결정") == \
        (KCA.SHARE_EXCHANGE_OR_TRANSFER,)


def test_tender_offer_report_name_classifies():
    assert KCA.classify_disclosure_family("공개매수신고서") == (KCA.TENDER_OFFER,)


def test_delisting_report_name_classifies():
    assert KCA.classify_disclosure_family("상장폐지 관련 안내") == (KCA.DELISTING,)


def test_dividend_decision_report_name_classifies():
    assert KCA.classify_disclosure_family("현금ㆍ현물배당결정") == (KCA.DIVIDEND_DECISION,)


def test_unrelated_report_name_classifies_as_nothing():
    assert KCA.classify_disclosure_family("사업보고서") == ()
    assert KCA.classify_disclosure_family(None) == ()


def test_a_report_name_may_match_more_than_one_family_and_both_are_kept():
    # Not a real DART name -- a constructed case to prove the classifier
    # never picks just one match and drops the rest.
    result = KCA.classify_disclosure_family("영업양수 및 상장폐지 관련 공시")
    assert set(result) == {KCA.BUSINESS_TRANSFER, KCA.DELISTING}


def test_amendment_marker_detected():
    assert KCA.is_amendment("[기재정정]합병결정")
    assert not KCA.is_amendment("합병결정")


# --------------------------------------------------------------------------- #
# filing_index_rows / candidate_disclosures -- the CONFIRMED list.json half
# --------------------------------------------------------------------------- #
def test_filing_index_rows_parses_the_confirmed_list_key():
    rows, error = KCA.filing_index_rows({"status": "000", "list": [_list_row()]})
    assert error == ""
    assert len(rows) == 1


def test_filing_index_rows_reports_a_missing_list_key_rather_than_returning_empty_silently():
    rows, error = KCA.filing_index_rows({"status": "000"})
    assert rows == []
    assert "no 'list' key" in error


def test_filing_index_rows_status_013_is_zero_rows_never_an_error():
    """DART's own 'no data found' answer -- a valid, common outcome for a
    ticker with no matching disclosures, not a schema failure."""
    rows, error = KCA.filing_index_rows({"status": "013", "message": "조회된 데이타가 없습니다."})
    assert rows == []
    assert error == ""


def test_filing_index_rows_reports_a_non_list_payload():
    rows, error = KCA.filing_index_rows("not a dict")
    assert rows == []
    assert "not an object" in error


def test_candidate_disclosures_keeps_only_family_matches():
    rows = [_list_row(report_nm="합병결정"), _list_row(rcept_no="20190301000456",
            report_nm="분기보고서")]
    candidates = KCA.candidate_disclosures(rows, ticker="000030.KS")
    assert len(candidates) == 1
    assert candidates[0]["disclosureFamilies"] == [KCA.MERGER]
    assert candidates[0]["receiptDate"] == "2019-02-01"
    assert candidates[0]["ticker"] == "000030.KS"


def test_candidate_disclosures_never_assigns_a_termination_type():
    candidates = KCA.candidate_disclosures([_list_row()], ticker="000030.KS")
    assert "terminationType" not in candidates[0]


def test_candidate_disclosures_refuses_a_row_with_no_receipt_date():
    row = _list_row(rcept_no="")
    assert KCA.candidate_disclosures([row]) == []


def test_candidate_disclosures_sorted_deterministically():
    rows = [_list_row(rcept_no="20200101000002", report_nm="합병결정"),
            _list_row(rcept_no="20190101000001", report_nm="합병결정")]
    candidates = KCA.candidate_disclosures(rows)
    assert [c["receiptNo"] for c in candidates] == ["20190101000001", "20200101000002"]


# --------------------------------------------------------------------------- #
# amendment_chain -- amendments are preserved, never collapsed
# --------------------------------------------------------------------------- #
def test_amendment_chain_preserves_every_filing_and_marks_priors():
    rows = [_list_row(rcept_no="20190101000001", report_nm="합병결정"),
            _list_row(rcept_no="20190201000002", report_nm="[기재정정]합병결정")]
    candidates = KCA.candidate_disclosures(rows, ticker="000030.KS")
    chained = KCA.amendment_chain(candidates)
    assert len(chained) == 2, "no filing is dropped, original or amendment"
    assert chained[0]["priorFilingsInChain"] == []
    assert chained[1]["priorFilingsInChain"] == ["20190101000001"]
    assert chained[1]["isAmendment"] is True


def test_amendment_chain_keys_by_corp_and_family_not_just_corp():
    rows = [_list_row(rcept_no="20190101000001", report_nm="합병결정"),
            _list_row(rcept_no="20190102000002", report_nm="공개매수신고서")]
    candidates = KCA.candidate_disclosures(rows, ticker="000030.KS")
    chained = KCA.amendment_chain(candidates)
    assert all(row["priorFilingsInChain"] == [] for row in chained), \
        "different families never chain into each other"


# --------------------------------------------------------------------------- #
# alotMatter -- CANDIDATE, unconfirmed, raw-preserving
# --------------------------------------------------------------------------- #
def test_dividend_section_row_is_marked_unconfirmed():
    row = {"rcept_no": "20230312000789", "corp_code": "00126380",
          "corp_name": "삼성전자", "se": "주당 현금배당금(원)",
          "thstrm": "361", "frmtrm": "361", "lwfr": "354", "stock_knd": "보통주"}
    record, reason = KCA.build_dividend_section_row(
        row, ticker="005930.KS", collected_at="2026-09-25T00:00:00Z")
    assert reason == ""
    assert record["endpointConfidence"] == KCA.CANDIDATE_UNCONFIRMED
    assert record["categoryRaw"] == "주당 현금배당금(원)", "se kept raw, never interpreted"
    assert record["receiptDate"] == "2023-03-12"


def test_dividend_section_row_never_invents_a_record_or_ex_date():
    row = {"rcept_no": "20230312000789", "se": "주당 현금배당금(원)"}
    record, _ = KCA.build_dividend_section_row(row, ticker=None, collected_at="")
    assert record["recordDate"] is None
    assert record["exDate"] is None
    assert record["effectiveDate"] is None


def test_dividend_section_row_refuses_without_a_receipt():
    record, reason = KCA.build_dividend_section_row({"se": "x"}, ticker=None, collected_at="")
    assert record is None
    assert reason == "NO_RECEIPT_NO"


def test_dividend_section_row_refuses_an_unparseable_receipt():
    record, reason = KCA.build_dividend_section_row(
        {"rcept_no": "not-a-date"}, ticker=None, collected_at="")
    assert record is None
    assert reason == "NO_RECEIPT_DATE"


# --------------------------------------------------------------------------- #
# date roles -- every role stays a distinct, never-collapsed field
# --------------------------------------------------------------------------- #
def test_date_roles_are_seven_distinct_named_fields():
    assert KCA.DATE_ROLES == (
        "receiptDate", "decisionDate", "recordDate", "exDate",
        "effectiveDate", "lastTradingDate", "paymentDate")


def test_ex_date_stays_blocked_with_no_sealed_dated_rule():
    assert KCA.EX_DATE_STATUS_BLOCKED == "DIVIDEND_EX_DATE_LINEAGE_BLOCKED"


# --------------------------------------------------------------------------- #
# pagination -- every page walked, deduplicated, fails closed
# --------------------------------------------------------------------------- #
def _paged(rows, *, page_no, total_count, total_page, page_count=100, status="000"):
    return {"status": status, "list": rows, "page_no": page_no, "page_count": page_count,
           "total_count": total_count, "total_page": total_page}


def test_parse_pagination_metadata_reads_all_four_fields():
    meta, error = KCA.parse_pagination_metadata(
        _paged([], page_no=1, total_count=250, total_page=3))
    assert error == ""
    assert meta == {"pageNo": 1, "pageCount": 100, "totalCount": 250, "totalPage": 3}


def test_parse_pagination_metadata_refuses_a_missing_field():
    meta, error = KCA.parse_pagination_metadata({"status": "000", "list": []})
    assert meta is None
    assert "missing pagination field" in error


def test_parse_pagination_metadata_refuses_a_non_integer_field():
    payload = _paged([], page_no=1, total_count="not-a-number", total_page=1)
    meta, error = KCA.parse_pagination_metadata(payload)
    assert meta is None
    assert "not an integer" in error


def test_parse_pagination_metadata_refuses_inconsistent_zero_count():
    payload = _paged([], page_no=1, total_count=0, total_page=5)
    meta, error = KCA.parse_pagination_metadata(payload)
    assert meta is None
    assert "totalCount is 0" in error


def test_pagination_consistent_true_when_totals_match():
    first = {"totalCount": 250, "totalPage": 3}
    later = {"totalCount": 250, "totalPage": 3}
    assert KCA.pagination_consistent(first, later)


def test_pagination_consistent_false_when_a_new_filing_landed_mid_walk():
    first = {"totalCount": 250, "totalPage": 3}
    later = {"totalCount": 251, "totalPage": 3}
    assert not KCA.pagination_consistent(first, later)


def test_merge_paginated_rows_dedupes_by_receipt_number():
    page1 = [{"rcept_no": "1"}, {"rcept_no": "2"}]
    page2 = [{"rcept_no": "2"}, {"rcept_no": "3"}]  # "2" repeated across pages
    merged = KCA.merge_paginated_rows([page1, page2])
    assert [row["rcept_no"] for row in merged] == ["1", "2", "3"]


def test_fetch_all_pages_walks_a_single_page():
    row = _list_row(rcept_no="20190201000123")

    def fetch_page(page_no):
        assert page_no == 1
        return _paged([row], page_no=1, total_count=1, total_page=1)

    rows, meta = KCA.fetch_all_pages(fetch_page)
    assert rows == [row]
    assert meta["pagesFetched"] == 1
    assert meta["rowsFetched"] == 1


def _daily_receipt_nos(start, count):
    """`count` sequential valid YYYYMMDD receipt numbers, one per day."""
    import datetime as _dt
    day = _dt.date.fromisoformat(start)
    out = []
    for _ in range(count):
        out.append(day.strftime("%Y%m%d") + "0001")
        day += _dt.timedelta(days=1)
    return out


def test_fetch_all_pages_walks_every_page_of_a_gt_100_row_issuer():
    """A >100-row issuer: two full pages, with a relevant filing appearing
    only on page 2 -- both pages must be reached and merged."""
    day1 = _daily_receipt_nos("2013-01-01", 100)
    day2 = _daily_receipt_nos("2013-04-11", 45)
    page1 = [{"rcept_no": no, "report_nm": "사업보고서"} for no in day1]
    page2_relevant = {"rcept_no": day2[0], "report_nm": "공개매수신고서"}
    page2 = [{"rcept_no": no, "report_nm": "사업보고서"} for no in day2[1:]] + [page2_relevant]

    def fetch_page(page_no):
        if page_no == 1:
            return _paged(page1, page_no=1, total_count=145, total_page=2)
        if page_no == 2:
            return _paged(page2, page_no=2, total_count=145, total_page=2)
        raise AssertionError(f"unexpected page {page_no}")

    rows, meta = KCA.fetch_all_pages(fetch_page)
    assert meta["pagesFetched"] == 2
    assert len(rows) == 145
    assert page2_relevant in rows
    candidates = KCA.candidate_disclosures(rows)
    assert len(candidates) == 1
    assert candidates[0]["receiptNo"] == page2_relevant["rcept_no"], \
        "the page-2-only corporate-action filing must survive the merge"


def test_fetch_all_pages_zero_results_status_013_short_circuits():
    def fetch_page(page_no):
        assert page_no == 1
        return {"status": "013", "message": "no data"}

    rows, meta = KCA.fetch_all_pages(fetch_page)
    assert rows == []
    assert meta["pagesFetched"] == 0


def test_fetch_all_pages_raises_on_missing_pagination_metadata():
    def fetch_page(page_no):
        return {"status": "000", "list": [_list_row(rcept_no="1")]}  # no pagination fields

    with pytest.raises(KCA.PaginationError):
        KCA.fetch_all_pages(fetch_page)


def test_fetch_all_pages_raises_when_a_later_page_disagrees_with_the_first():
    def fetch_page(page_no):
        if page_no == 1:
            return _paged([_list_row(rcept_no="1")], page_no=1, total_count=150, total_page=2)
        return _paged([_list_row(rcept_no="2")], page_no=2, total_count=151, total_page=2)

    with pytest.raises(KCA.PaginationError, match="changed mid-walk"):
        KCA.fetch_all_pages(fetch_page)


def test_fetch_all_pages_raises_on_a_row_parse_failure_on_a_later_page():
    def fetch_page(page_no):
        if page_no == 1:
            return _paged([_list_row(rcept_no="1")], page_no=1, total_count=150, total_page=2)
        return {"status": "000", "page_no": 2, "page_count": 100,
               "total_count": 150, "total_page": 2}  # no 'list' key

    with pytest.raises(KCA.PaginationError):
        KCA.fetch_all_pages(fetch_page)


# --------------------------------------------------------------------------- #
# historical DART issuer identity -- reused from dart_ownership_universe
# --------------------------------------------------------------------------- #
def test_resolve_historical_dart_identity_uses_dart_ownership_universes_own_function():
    import inspect
    source = inspect.getsource(KCA.resolve_historical_dart_identity)
    assert "DOU._resolve_security" in source, \
        "must call the repository's existing resolver, never reimplement it"


def test_exact_stock_code_resolves_first():
    directory = [{"corpCode": "00123", "corpName": "우리은행", "stockCode": "000030",
                 "modifyDate": None}]
    identity = KCA.resolve_historical_dart_identity("000030", "우리은행", directory)
    assert identity["status"] == KCA.RESOLVED
    assert identity["basis"] == KCA.EXACT_STOCK_CODE
    assert identity["corpCode"] == "00123"


def test_delisted_issuer_with_blank_stock_code_resolves_by_unique_name():
    """DART blanks a corp's stock_code once it delists -- a real terminated
    issuer's current corpCode.xml row looks like this."""
    directory = [{"corpCode": "00999", "corpName": "외환은행", "stockCode": "",
                 "modifyDate": None}]
    identity = KCA.resolve_historical_dart_identity("004940", "외환은행", directory)
    assert identity["status"] == KCA.RESOLVED
    assert identity["basis"] == KCA.UNIQUE_NORMALIZED_NAME
    assert identity["corpCode"] == "00999"


def test_an_ambiguous_name_match_stays_unresolved():
    directory = [
        {"corpCode": "00801", "corpName": "동명주식회사", "stockCode": "", "modifyDate": None},
        {"corpCode": "00802", "corpName": "동명주식회사", "stockCode": "", "modifyDate": None},
    ]
    identity = KCA.resolve_historical_dart_identity("999999", "동명주식회사", directory)
    assert identity["status"] == KCA.UNRESOLVED
    assert identity["corpCode"] is None


def test_no_stock_code_and_no_name_match_stays_unresolved():
    directory = [{"corpCode": "00123", "corpName": "우리은행", "stockCode": "000030",
                 "modifyDate": None}]
    identity = KCA.resolve_historical_dart_identity("999999", "존재하지않는이름", directory)
    assert identity["status"] == KCA.UNRESOLVED


def test_identity_resolution_never_uses_fuzzy_or_ticker_similarity():
    import inspect
    source = inspect.getsource(KCA)
    for forbidden in ("fuzzywuzzy", "rapidfuzz", "levenshtein", "difflib",
                      "sequencematcher", "jaro", "ratio("):
        assert forbidden not in source.lower(), forbidden


def test_a_near_miss_name_is_not_treated_as_a_match():
    """A name differing by even one character must never resolve -- proves
    the match is exact, not fuzzy, behaviourally rather than by keyword."""
    directory = [{"corpCode": "00123", "corpName": "우리은행", "stockCode": "",
                 "modifyDate": None}]
    identity = KCA.resolve_historical_dart_identity("999999", "우리은행A", directory)
    assert identity["status"] == KCA.UNRESOLVED
