"""Table-form KSIC and affiliate self-row candidates. Synthetic HTML plus the committed report. No network or outcome."""
import hashlib
import json

from . import kr22_repository_originals as R
from . import kr22_table_ksic_candidates as T

REPORT = json.loads(T.REPORT.read_text())
CROSSWALK = json.loads((R.K.ROOT / R.CROSSWALK).read_text())

HEADER = "<THEAD><TR><TH>대분류</TH><TH>중분류</TH><TH>소분류</TH><TH>세분류</TH><TH>세세분류</TH></TR></THEAD>"


def statement(code="J58222", label="응용 소프트웨어 개발 및 공급업", cells=None):
    cells = cells or ["J<BR/>정보통신업", "58<BR/>출판업", "582<BR/>소프트웨어 개발 및 공급업",
                      "5822<BR/>시스템·응용 소프트웨어 개발 및 공급업", "58222<BR/>응용 소프트웨어개발 및 공급업"]
    body = "".join("<TD>%s</TD>" % c for c in cells)
    return ("<P>(나) 공시대상 사업부문의 구분</P><P>한국표준산업분류 : %s (%s)</P>"
            "<TABLE border='1'>%s<TBODY><TR>%s</TR></TBODY></TABLE>" % (label, code, HEADER, body))


def test_table_form_statement_is_parsed_and_its_hierarchy_checked_against_its_own_code():
    [s] = T.parse_statements(statement())
    assert (s["statedCode"], s["statedLabel"]) == ("J58222", "응용소프트웨어개발및공급업")
    assert [lv["code"] for lv in s["levels"]] == ["J", "58", "582", "5822", "58222"]
    assert s["checks"]["consistent"] is True
    three = next(lv for lv in s["levels"] if lv["level"] == "소분류")
    # Only the stated 3-digit row is looked up, and only exactly; the 5-digit label itself is not in the crosswalk.
    assert R.V4.research_group(three["label"], CROSSWALK) == "COMMUNICATION_MEDIA_SOFTWARE"
    assert R.V4.research_group(s["statedLabel"], CROSSWALK) is None


def test_a_row_whose_code_is_not_a_prefix_of_the_statement_is_inconsistent():
    bad = ["J<BR/>정보통신업", "58<BR/>출판업", "583<BR/>소프트웨어 개발 및 공급업",
           "5822<BR/>시스템", "58222<BR/>응용 소프트웨어개발 및 공급업"]
    [s] = T.parse_statements(statement(cells=bad))
    assert s["checks"]["levelCodesArePrefixesOfStatedCode"] is False and s["checks"]["consistent"] is False
    wrong_letter = ["C<BR/>제조업"] + bad[1:2] + ["582<BR/>소프트웨어 개발 및 공급업", "5822<BR/>x", "58222<BR/>응용 소프트웨어개발 및 공급업"]
    [s] = T.parse_statements(statement(cells=wrong_letter))
    assert s["checks"]["sectionLetterMatches"] is False and s["checks"]["consistent"] is False


def test_a_statement_without_its_hierarchy_table_has_no_three_digit_row():
    [s] = T.parse_statements("<P>사업분류를 내연기관제조업(표준산업분류 : 29111)으로 단일화</P>"
                             "<P>한국표준산업분류 : 응용 소프트웨어 개발 및 공급업 (J58222)</P><P>본문</P>")
    assert s["checks"] == {"hierarchyTableFollows": False} and s["levels"] == []


def row(kind="TABLE_FORM_KSIC", **kw):
    base = {"kind": kind, "statementsInReceipt": 1, "checks": {"consistent": True}, "admitMechanical": True,
            "crosswalkGroupOfThreeDigitRow": "X", "selfRowsInReceipt": 1, "crosswalkGroup": "X"}
    return {**base, **kw}


def test_eligibility_needs_one_statement_consistency_admit_and_an_exact_crosswalk_hit():
    assert T.eligible_candidate(row())
    assert not T.eligible_candidate(row(statementsInReceipt=2))
    assert not T.eligible_candidate(row(checks={"consistent": False}))
    assert not T.eligible_candidate(row(admitMechanical=False))
    assert not T.eligible_candidate(row(crosswalkGroupOfThreeDigitRow=None))
    assert T.eligible_candidate(row("AFFILIATE_SELF_ROW")) and not T.eligible_candidate(row("AFFILIATE_SELF_ROW", crosswalkGroup=None))


OVERVIEW = ("<P>가. 당사의 명칭은 주식회사 현대홈쇼핑이라고 표기합니다.</P><TABLE><THEAD><TR><TH>상장여부</TH><TH>회사명</TH>"
            "<TH>업종</TH></TR></THEAD><TBODY><TR><TD rowspan='2'>상장</TD><TD>(주)현대백화점</TD><TD>도소매업</TD></TR>"
            "<TR><TD>(주)현대홈쇼핑</TD><TD>TV 홈쇼핑, 방송프로그램 제작업</TD></TR></TBODY></TABLE>")


def test_affiliate_self_row_is_the_filings_own_stated_name_aligned_from_the_right():
    out = T.affiliate_self_rows(OVERVIEW)
    assert out["legalName"] == "주식회사 현대홈쇼핑" and out["tables"] == 1
    [r] = out["rows"]
    assert (r["nameCell"], r["label"]) == ("(주)현대홈쇼핑", "TV 홈쇼핑, 방송프로그램 제작업")
    assert R.V4.research_group(r["label"], CROSSWALK) is None   # free text, never mapped to a nearest group
    quoted = OVERVIEW.replace("주식회사 현대홈쇼핑이라고 표기합니다", "'현대홈쇼핑 주식회사' 이고")
    assert [x["label"] for x in T.affiliate_self_rows(quoted)["rows"]] == ["TV 홈쇼핑, 방송프로그램 제작업"]
    other = OVERVIEW.replace("주식회사 현대홈쇼핑이라고", "주식회사 현대그린푸드라고")
    assert T.affiliate_self_rows(other)["rows"] == []


def test_kind_interval_lookup_is_half_open_and_skips_unknown():
    iv = {"A.KS": [{"start": None, "end": "2016-01-01", "status": "S", "raw_industry_name": "전기 업", "research_industry_id": "E"},
                   {"start": "2016-01-01", "end": None, "status": "UNKNOWN", "raw_industry_name": "x", "research_industry_id": None}]}
    assert T.kind_label_on(iv, "A.KS", "2015-12-31")["label"] == "전기업"
    assert T.kind_label_on(iv, "A.KS", "2016-01-01") is None


def test_committed_report_admits_nothing_changes_no_frozen_input_and_defers_the_verdict():
    s = REPORT["summary"]
    assert REPORT["historicalOutcomesRead"] == 0 and REPORT["pricesRead"] == 0 and REPORT["networkUsed"] is False
    assert REPORT["finalEligibilityVerdict"] == "DEFERRED_TO_INDEPENDENT_AUDIT"
    assert s["kr22"]["industryAdmitted"] == {"before": 0, "after": 0}
    assert s["frozenTemplateChanged"] is False and s["frozenCrosswalkChanged"] is False
    assert REPORT["inputs"]["crosswalkSha256"] == hashlib.sha256((R.K.ROOT / R.CROSSWALK).read_bytes()).hexdigest()
    assert s["denominator"] == 22 and s["kr22"]["windowMemberMonthsAll16"] == 535
    # Measured scope: the table form exists in one issuer of the whole retained corpus, and no KIND interval checks it.
    tf = s["allIssuers"]["TABLE_FORM_KSIC"]
    assert (tf["allRows"], tf["allRowsIssuers"], tf["allRowsComparedWithV4KindInterval"]) == (8, 1, 0)
    assert s["kr22"]["securitiesWithEligibleCandidate"] == ["012510.KS"]


def test_rebuild_reproduces_the_committed_summary():
    assert T.build()["summary"] == REPORT["summary"]
