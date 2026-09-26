"""Conservative text extraction and observed real DART table patterns."""
from __future__ import annotations

from pipeline import kr_terminal_action_document_parser as PARSER


# --------------------------------------------------------------------------- #
# extract_labeled_value -- conservative: exactly one candidate or None
# --------------------------------------------------------------------------- #
def test_a_single_unambiguous_label_extracts_its_value():
    text = "합병비율: 1 : 0.523"
    value, reason = PARSER.extract_labeled_value(text, ("합병비율",))
    assert value == "1 : 0.523"
    assert reason is None


def test_zero_matches_is_its_own_reason():
    text = "이 문서에는 관련 내용이 없습니다"
    value, reason = PARSER.extract_labeled_value(text, ("합병비율",))
    assert value is None
    assert reason == PARSER.AMBIGUOUS_ZERO_MATCHES


def test_two_different_values_for_the_same_label_is_ambiguous():
    text = "합병비율: 1 : 0.5\n...\n합병비율: 1 : 0.6"
    value, reason = PARSER.extract_labeled_value(text, ("합병비율",))
    assert value is None
    assert reason == PARSER.AMBIGUOUS_MULTIPLE_MATCHES


def test_the_same_label_repeated_with_the_same_value_is_not_ambiguous():
    # A summary table restating a detail table's own figure -- one true
    # value, not a disagreement.
    text = "합병비율: 1 : 0.523\n(요약) 합병비율: 1 : 0.523"
    value, reason = PARSER.extract_labeled_value(text, ("합병비율",))
    assert value == "1 : 0.523"
    assert reason is None


def test_a_value_never_crosses_a_line_break():
    text = "합병비율:\n다른 내용입니다"
    value, reason = PARSER.extract_labeled_value(text, ("합병비율",))
    # No value on the SAME line as the label -- zero matches, not a guess
    # at the next line's unrelated content.
    assert value is None
    assert reason == PARSER.AMBIGUOUS_ZERO_MATCHES


def test_label_synonyms_are_tried_but_never_merged_if_they_disagree():
    text = "1주당 신주배정주식수: 0.5\n1주당 배정주식수: 0.6"
    value, reason = PARSER.extract_labeled_value(
        text, ("1주당 신주배정주식수", "1주당 배정주식수"))
    assert value is None
    assert reason == PARSER.AMBIGUOUS_MULTIPLE_MATCHES


# --------------------------------------------------------------------------- #
# parse_filing_document -- every field, never a partial claim of confidence
# --------------------------------------------------------------------------- #
def test_every_field_in_field_labels_gets_a_result_entry():
    result = PARSER.parse_filing_document("(빈 문서)", receipt_no="20200101000001")
    assert set(result["fields"]) == set(PARSER.FIELD_LABELS)
    assert all(f["value"] is None for f in result["fields"].values())


def test_validation_status_describes_observed_patterns_not_economic_readiness():
    result = PARSER.parse_filing_document("(빈 문서)", receipt_no="20200101000001")
    assert result["parserValidationStatus"] == "REAL_DART_TABLE_PATTERNS_VALIDATED"


def test_a_synthetic_standard_form_document_extracts_its_unambiguous_fields():
    # Modeled on the PUBLIC description of a 주요사항보고서(합병결정)
    # template's field layout -- constructed by this repository, not a real
    # filing. See module docstring: this only proves the extraction LOGIC
    # behaves as designed on a document shaped like the public template,
    # never that it will work on a real filing's actual formatting.
    text = (
        "존속회사: (주)가나다홀딩스\n"
        "소멸회사: (주)라마바\n"
        "합병비율: 1 : 0.523\n"
        "합병기일: 2020-06-01\n"
        "합병등기일: 2020-06-15\n"
    )
    result = PARSER.parse_filing_document(text, receipt_no="20200101000001")
    assert result["fields"]["survivingCompany"]["value"] == "(주)가나다홀딩스"
    assert result["fields"]["dissolvingCompany"]["value"] == "(주)라마바"
    assert result["fields"]["mergerRatio"]["value"] == "1 : 0.523"
    assert result["fields"]["mergerEffectiveDate"]["value"] == "2020-06-01"
    # A field this synthetic document never mentions stays None, not
    # guessed from context.
    assert result["fields"]["tenderOfferPrice"]["value"] is None


def test_no_field_is_ever_read_from_a_report_name():
    import inspect
    signature = inspect.signature(PARSER.parse_filing_document)
    assert set(signature.parameters) == {"text", "receipt_no"}
    signature = inspect.signature(PARSER.extract_labeled_value)
    assert set(signature.parameters) == {"text", "labels"}



def test_real_dart_table_patterns_and_cash_valuation_ratio_separation():
    import json
    from pathlib import Path
    fixtures = json.loads((Path(__file__).parent / "fixtures" /
                           "kr-terminal-real-table-patterns.json").read_text())
    for fixture in fixtures:
        structure = PARSER.document_structure(fixture["xml"])
        rows = PARSER.labeled_rows(structure, fixture["label"])
        assert rows, fixture["receiptNo"]
        value = rows[-1]["cells"][-1]
        if isinstance(fixture["expected"], int):
            assert PARSER.cash_instead_of_stock(value) == fixture["expected"]
        elif fixture["expected"]:
            assert PARSER.korean_date(value) == fixture["expected"]
        else:
            assert "0.7367839" in value and "1.1102438" in value
            assert PARSER.cash_instead_of_stock(value) is None


def test_before_after_table_is_not_a_current_terms_table():
    text = ("<TABLE><TR><TH>정정항목</TH><TH>정정전</TH><TH>정정후</TH></TR>"
            "<TR><TD>합병기일</TD><TD>2016년 11월 01일</TD><TD>2016년 12월 29일</TD></TR>"
            "</TABLE><TABLE><TR><TD>합병기일</TD><TE>2016년 12월 29일</TE></TR></TABLE>")
    rows = PARSER.labeled_rows(PARSER.document_structure(text), "합병기일")
    assert len(rows) == 1
    assert PARSER.korean_date(rows[0]["cells"][-1]) == "2016-12-29"


def test_tender_price_or_appraisal_value_is_not_cash_exchange_consideration():
    assert PARSER.cash_instead_of_stock("공개매수가격 주당 현금 8,750원") is None
    assert PARSER.cash_instead_of_stock("매수예정가격 7,383원") is None
