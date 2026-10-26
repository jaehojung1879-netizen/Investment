"""Terminal-viewer plan, collector, verifier and extractor on a fake transport. No network, price or outcome."""
import hashlib
import json

import pytest

from scripts import collect_kr_industry_membership_sources as S

from . import kr22_terminal_viewer as TV

PLAN = TV.load_plan()


def test_plan_is_the_35_failed_receipts_with_their_prior_review_class():
    assert len(PLAN["targets"]) == 35 and PLAN["denominator"] == 22 and PLAN["keyRequired"] is False
    assert PLAN["counts"] == {"MATERIALLY_BLOCKING": 20, "POTENTIALLY_MATERIAL": 10, "REDUNDANT_SUPERSEDED_OR_UNNECESSARY": 5}
    recovery = json.loads((TV.HERE / "kr22-source-recovery.json").read_text())
    expected = {r for q in recovery["requests"] for r in (q.get("failedTerminalReceiptsToRetry") or [])}
    assert {t["receiptNo"] for t in PLAN["targets"]} == expected
    # Every one is an amendment except the regulator's correction order, which is filed by the FSS.
    assert [t["receiptNo"] for t in PLAN["targets"] if not t["amendmentMarker"]] == ["20260515100001"]
    assert TV.build_plan() == PLAN


def test_a_changed_plan_is_refused(tmp_path):
    bad = dict(PLAN, maxNodesPerReceipt=99)
    (tmp_path / "p.json").write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="PLAN_DIGEST_MISMATCH"):
        TV.load_plan(tmp_path / "p.json")


TARGET = {"receiptNo": "20181121000025", "corpCode": "00254045", "receiptDate": "2018-11-21", "amendmentMarker": "기재정정",
          "ticker": "000030.KS", "reportName": "[기재정정]주요사항보고서(주식교환ㆍ이전결정)", "priorReviewCategory": "MATERIALLY_BLOCKING"}


# Real viewer titles are `filer/form/date`, with no amendment marker (31 of 31 served terminal amendments).
def main_page(receipt="20181121000025", corp="00254045", title="우리은행/주요사항보고서/2018.11.21", n=2,
              first="정정신고(보고)"):
    nodes = "".join(
        "var node%d = {};node%d['text'] = \"%s\";node%d['rcpNo'] = \"%s\";node%d['dcmNo'] = \"%d\";node%d['eleId'] = \"%d\";"
        "node%d['offset'] = \"0\";node%d['length'] = \"10\";node%d['dtd'] = \"dart3.xsd\";"
        % (i, i, first if i == 1 else "주요사항보고서", i, receipt, i, 100 + i, i, i, i, i, i) for i in range(1, n + 1))
    return ("<html><title>%s</title><script>openCorpInfoNew('%s', 1);%s</script></html>" % (title, corp, nodes)).encode()


def notice(date="2018년 11월 21일", target="주요사항보고서(주식교환ㆍ이전결정)", first="2018년 06월 19일", table=True):
    """A 정정신고(보고) node in the layout real notices use (read from 27 served filings)."""
    rows = ("<TABLE><TR><TD>항 목</TD><TD>정 정 전</TD><TD>정 정 후</TD></TR>"
            "<TR><TD>주식교환일</TD><TD>2019년 01월 11일</TD><TD>2019년 02월 13일</TD></TR></TABLE>") if table else ""
    return ("<P>정 정 신 고 (보고)</P><P>%s</P><P>1. 정정대상 공시서류 : %s</P>"
            "<P>2. 정정대상 공시서류의 최초제출일 : %s</P><P>3. 정정사항</P>%s" % (date, target, first, rows)).encode()


CORRECTION = notice()
INDEX = [{"corpCode": "00254045", "receiptNo": "20180619000302", "receiptDate": "2018-06-19", "isAmendment": False,
          "reportName": "주요사항보고서(주식교환ㆍ이전결정)"},
         {"corpCode": "00254045", "receiptNo": "20181121000025", "receiptDate": "2018-11-21", "isAmendment": True,
          "reportName": "[기재정정]주요사항보고서(주식교환ㆍ이전결정)"}]
BODY = ("<TABLE><TR><TD>주식교환비율</TD><TD>1 : 1.0000000</TD></TR>"
        "<TR><TD>주식교환일</TD><TD>2019년 02월 13일</TD></TR><TR><TD>교환신주의 수</TD><TD>680,398,068</TD></TR></TABLE>").encode()


class Fake:
    def __init__(self, routes, budget=100):
        self.routes, self.calls, self.budget = routes, 0, budget

    def request(self, url):
        if self.calls >= self.budget:
            raise ValueError("CALL_BUDGET_EXCEEDED")
        self.calls += 1
        for key, value in self.routes.items():
            if key in url:
                status, raw = value
                return {"url": url, "status": status, "error": None,
                        "sha256": hashlib.sha256(raw).hexdigest() if raw is not None else None, "raw": raw}
        return {"url": url, "status": None, "error": "URLError", "raw": None}


def one_target_plan(target=TARGET):
    return dict(PLAN, targets=[target])


def test_served_receipt_is_verified_and_yields_candidates_never_adoptions(tmp_path):
    fake = Fake({"main.do": (200, main_page()), "dcmNo=101": (200, CORRECTION), "dcmNo=102": (200, BODY)})
    plan = one_target_plan()
    m = TV.collect(tmp_path / "c", plan, fake, S.nodes)
    assert m["records"][0]["status"] == "SERVED" and m["calls"] == 3 and m["stopped"] is None
    out = TV.verify_and_extract(tmp_path / "c", plan, INDEX)
    [r] = out["records"]
    assert r["verification"] == "VERIFIED" and r["adopted"] is False
    assert r["correctionRows"][-1]["cells"] == ["주식교환일", "2019년 01월 11일", "2019년 02월 13일"]
    assert r["fieldCandidates"]["exchangeDate"][0]["date"] == "2019-02-13"
    assert r["fieldCandidates"]["newSharesIssued"][0]["value"] == "680,398,068"
    # The correction table's own rows are never read as the decision's terms.
    assert all(c["node"] == "주요사항보고서" for c in r["fieldCandidates"]["exchangeDate"])


def _verify(tmp_path, name, page=None, correction=None, body=BODY, target=TARGET, index=INDEX):
    fake = Fake({"main.do": (200, page or main_page()), "dcmNo=101": (200, correction or CORRECTION), "dcmNo=102": (200, body)})
    TV.collect(tmp_path / name, one_target_plan(target), fake, S.nodes)
    [r] = TV.verify_and_extract(tmp_path / name, one_target_plan(target), index)["records"]
    return r


def test_a_title_without_an_amendment_marker_is_not_a_refusal(tmp_path):
    r = _verify(tmp_path, "c")
    assert r["verification"] == "VERIFIED", r["reasons"]
    assert r["amendmentLink"]["originalReceiptNo"] == "20180619000302"
    assert r["amendmentLink"]["noticeTargetKind"] == "THIS_REPORT"


@pytest.mark.parametrize("case,kw,reason", [
    ("issuer", {"page": main_page(corp="99999999")}, "ISSUER_IDENTITY_NOT_UNIQUE_IN_MAIN"),
    ("title-date", {"page": main_page(title="우리은행/주요사항보고서/2018.11.22")}, "TITLE_DATE_DIFFERS_FROM_RECEIPT_DATE"),
    ("title-form", {"page": main_page(title="우리은행/사업보고서/2018.11.21")}, "TITLE_REPORT_NAME_DIFFERS"),
    # A decision filing with no correction-notice node is not an amendment, whatever the plan says.
    ("no-notice-node", {"page": main_page(first="주식교환ㆍ이전 결정")}, "AMENDMENT_NOTICE_NODE_MISSING"),
    # A node merely named 정정신고 whose body is not a correction notice proves nothing.
    ("notice-without-table", {"correction": notice(table=False)}, "NOTICE_HAS_NO_CORRECTION_TABLE"),
    ("notice-other-date", {"correction": notice(date="2018년 11월 20일")}, "NOTICE_DATE_DIFFERS_FROM_RECEIPT_DATE"),
    ("notice-other-report", {"correction": notice(target="영업양도 결정")}, "NOTICE_TARGET_DIFFERS_FROM_REPORT"),
    ("no-original", {"correction": notice(first="2018년 06월 18일")}, "ORIGINAL_FILING_NOT_UNIQUELY_LINKED"),
    ("other-issuers-original", {"index": [dict(INDEX[0], corpCode="99999999")]}, "ORIGINAL_FILING_NOT_UNIQUELY_LINKED"),
    ("amended-original", {"index": [dict(INDEX[0], isAmendment=True)]}, "ORIGINAL_FILING_NOT_UNIQUELY_LINKED"),
    ("two-originals", {"index": [INDEX[0], dict(INDEX[0], receiptNo="20180619000999")]}, "ORIGINAL_FILING_NOT_UNIQUELY_LINKED"),
    ("other-subtype-original", {"index": [dict(INDEX[0], reportName="주요사항보고서(회사합병결정)")]},
     "ORIGINAL_FILING_NOT_UNIQUELY_LINKED"),
])
def test_a_document_that_does_not_prove_its_amendment_is_refused(tmp_path, case, kw, reason):
    r = _verify(tmp_path, case, **kw)
    assert r["verification"] == "REFUSED" and reason in r["reasons"] and "correctionRows" not in r


def test_a_node_of_another_receipt_is_never_fetched_nor_accepted(tmp_path):
    r = _verify(tmp_path, "f", page=main_page(receipt="20181121000099"))
    assert r["verification"] == "NOT_SERVED" and r["collectionStatus"] == "LISTED_BUT_VIEWER_EMPTY"
    fake = Fake({"main.do": (200, main_page()), "dcmNo=101": (200, CORRECTION), "dcmNo=102": (200, BODY)})
    m = TV.collect(tmp_path / "g", one_target_plan(), fake, S.nodes)
    record, objects = m["records"][0], TV.load_collection(tmp_path / "g", one_target_plan())[1]
    record["nodes"][1]["node"]["rcpNo"] = "20181121000099"
    verdict, reasons, _ = TV.verify_record(TARGET, record, objects, INDEX)
    assert verdict == "REFUSED" and "FOREIGN_RECEIPT_NODE" in reasons


def test_an_attachment_name_is_a_target_only_for_an_attachment_correction(tmp_path):
    att = notice(target="외부평가기관의평가의견서")
    r = _verify(tmp_path, "a", correction=att, target=dict(TARGET, amendmentMarker="첨부정정",
                                                            reportName="[첨부정정]주요사항보고서(주식교환ㆍ이전결정)"))
    assert r["verification"] == "VERIFIED" and r["amendmentLink"]["noticeTargetKind"] == "ATTACHMENT_OF_THIS_REPORT"
    r = _verify(tmp_path, "b", correction=att)
    assert r["verification"] == "REFUSED" and "NOTICE_TARGET_DIFFERS_FROM_REPORT" in r["reasons"]


def test_the_bare_form_name_in_a_notice_still_links_only_to_the_exact_subtype(tmp_path):
    r = _verify(tmp_path, "c", correction=notice(target="주요사항보고서"))
    assert r["verification"] == "VERIFIED" and r["amendmentLink"]["originalReceiptNo"] == "20180619000302"


def test_notice_date_after_a_dash_is_read():
    assert TV.correction_notice(notice(date="- 2017년 01월 02일").decode())["noticeDate"] == "2017-01-02"


def test_the_index_is_refused_unless_its_blob_matches_the_plan(monkeypatch):
    monkeypatch.setattr(TV.IN, "git_blobs", lambda commit, paths, root=None: {paths[0]: b"not the pinned index"})
    with pytest.raises(ValueError, match="DISCLOSURE_INDEX_CHANGED"):
        TV.load_index(PLAN)


def test_transport_failure_is_not_absence_and_stops_after_three(tmp_path):
    targets = [dict(TARGET, receiptNo="2018112100002%d" % i) for i in range(5)]
    m = TV.collect(tmp_path / "c", dict(PLAN, targets=targets), Fake({}), S.nodes)
    assert [r["status"] for r in m["records"]] == ["TRANSPORT_FAILURE"] * 3
    assert m["stopped"] == "REPEATED_TRANSPORT_FAILURE" and m["calls"] == 3
    out = TV.verify_and_extract(tmp_path / "c", dict(PLAN, targets=targets), INDEX)
    assert out["counts"]["NOT_SERVED"] == 3 and len(out["notAttempted"]) == 2


def test_listed_receipt_with_an_empty_viewer_is_flagged_not_called_absent(tmp_path):
    m = TV.collect(tmp_path / "c", one_target_plan(), Fake({"main.do": (200, main_page(n=0))}), S.nodes)
    assert m["records"][0]["status"] == "LISTED_BUT_VIEWER_EMPTY"


def test_a_tampered_archive_is_refused(tmp_path):
    fake = Fake({"main.do": (200, main_page()), "dcmNo=101": (200, CORRECTION), "dcmNo=102": (200, BODY)})
    TV.collect(tmp_path / "c", one_target_plan(), fake, S.nodes)
    (tmp_path / "c" / "objects.json.gz").write_bytes(b"x")
    with pytest.raises(ValueError, match="ARCHIVE_CHANGED"):
        TV.verify_and_extract(tmp_path / "c", one_target_plan(), INDEX)
