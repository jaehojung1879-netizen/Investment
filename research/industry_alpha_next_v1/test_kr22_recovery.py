"""The 22-security recovery inventory reads committed source files only, and never admits a candidate."""
import json

import pytest

from . import kr22_recovery as K


@pytest.fixture(scope="module")
def report():
    return K.build()


def test_inventory_covers_exactly_the_22_and_reads_no_outcome(report):
    assert len(report["securities"]) == 22 and report["summary"]["securities"] == 22
    assert report["historicalOutcomesRead"] == 0 and report["pricesRead"] == 0 and report["networkUsed"] is False
    for key, meta in report["inputs"].items():
        assert meta["path"] == K.INPUTS[key] and len(meta["sha256"]) == 64


def test_no_industry_candidate_is_ever_admitted(report):
    assert all(row["industry"]["admitted"] is False for row in report["securities"])
    assert report["summary"]["industry"]["admitted"] == 0
    assert report["summary"]["eligibleForIndustryTotalReturnLabelToday"] == 0


def test_study_window_member_months_reconcile_with_the_label_free_input_check(report):
    s = report["summary"]
    assert abs(s["studyWindowMemberMonths"] - s["studyWindowMemberMonthsCrossCheck"]) <= 10


def test_counts_agree_with_the_sealed_reconstruction_summary(report):
    sealed = json.loads((K.ROOT / K.INPUTS["reconstruction"]).read_text())["summary"]["byField"]
    t = report["summary"]["terminal"]
    assert t["typeResolved"] == sealed["terminationTypeResolved"]
    assert t["considerationResolvedReady"] == sealed["terminalConsiderationResolved"]
    assert t["terminalActionChainReady"] == sealed["terminalActionChainResolved"]
    assert report["summary"]["distributions"]["exDateSemanticsReady"] == sealed["exDateSemanticsResolved"]


def test_a_counterparty_name_never_becomes_a_self_statement():
    names = {"우리은행"}
    assert K.normalise_name("㈜우리은행(Woori Bank)") in names
    assert K.normalise_name("주식회사 메리츠금융지주(MERITZ FINANCIAL GROUP INC.)") not in {K.normalise_name("메리츠화재")}


def test_affiliate_row_and_main_business_patterns():
    row = "| 두산건설(주) | 종합 건설업 | 110111-0194277 |"
    assert K._AFFILIATE.findall(row) == [("두산건설(주)", "종합 건설업")]
    table = "가. 회사명 | ㈜우리은행(Woori Bank) | 나. 대표자 | 손태승 | 다. 주요사업 | 은행업 | 라. 회사와의 관계 |"
    assert K._ROW.findall(table) == [("㈜우리은행(Woori Bank)", "은행업")]


def test_every_candidate_carries_its_receipt_and_quote(report):
    for row in report["securities"]:
        for c in row["industry"]["candidates"]:
            assert c["receiptNo"] and c["quote"] and c["rule"]
