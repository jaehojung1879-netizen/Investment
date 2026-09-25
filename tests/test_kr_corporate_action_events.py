"""What `kr_corporate_action_events.py` may and may not claim.

Synthetic fixtures only. The network half runs solely in CI via
`scripts/probe_kr_corporate_actions.py`.
"""
from __future__ import annotations

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
    rows, error = KCA.filing_index_rows({"status": "013"})
    assert rows == []
    assert "no 'list' key" in error


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
