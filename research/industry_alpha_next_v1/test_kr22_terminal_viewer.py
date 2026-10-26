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


def main_page(receipt="20181121000025", corp="00254045", title="우리은행/[기재정정]주요사항보고서/2018.11.21", n=2):
    nodes = "".join(
        "var node%d = {};node%d['text'] = \"%s\";node%d['rcpNo'] = \"%s\";node%d['dcmNo'] = \"%d\";node%d['eleId'] = \"%d\";"
        "node%d['offset'] = \"0\";node%d['length'] = \"10\";node%d['dtd'] = \"dart3.xsd\";"
        % (i, i, "정정신고(보고)" if i == 1 else "주요사항보고서", i, receipt, i, 100 + i, i, i, i, i, i) for i in range(1, n + 1))
    return ("<html><title>%s</title><script>openCorpInfoNew('%s', 1);%s</script></html>" % (title, corp, nodes)).encode()


CORRECTION = ("<TABLE><TR><TD>정정사항</TD><TD>정정전</TD><TD>정정후</TD></TR>"
              "<TR><TD>주식교환일</TD><TD>2019년 01월 11일</TD><TD>2019년 02월 13일</TD></TR></TABLE>").encode()
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
    out = TV.verify_and_extract(tmp_path / "c", plan)
    [r] = out["records"]
    assert r["verification"] == "VERIFIED" and r["adopted"] is False
    assert r["correctionRows"][-1]["cells"] == ["주식교환일", "2019년 01월 11일", "2019년 02월 13일"]
    assert r["fieldCandidates"]["exchangeDate"][0]["date"] == "2019-02-13"
    assert r["fieldCandidates"]["newSharesIssued"][0]["value"] == "680,398,068"
    # The correction table's own rows are never read as the decision's terms.
    assert all(c["node"] == "주요사항보고서" for c in r["fieldCandidates"]["exchangeDate"])


def test_wrong_issuer_date_or_marker_is_refused(tmp_path):
    for i, page in enumerate([main_page(corp="99999999"), main_page(title="우리은행/[기재정정]주요사항보고서/2018.11.22"),
                              main_page(title="우리은행/주요사항보고서/2018.11.21")]):
        fake = Fake({"main.do": (200, page), "dcmNo=101": (200, CORRECTION), "dcmNo=102": (200, BODY)})
        TV.collect(tmp_path / str(i), one_target_plan(), fake, S.nodes)
        [r] = TV.verify_and_extract(tmp_path / str(i), one_target_plan())["records"]
        assert r["verification"] == "REFUSED" and "correctionRows" not in r


def test_transport_failure_is_not_absence_and_stops_after_three(tmp_path):
    targets = [dict(TARGET, receiptNo="2018112100002%d" % i) for i in range(5)]
    m = TV.collect(tmp_path / "c", dict(PLAN, targets=targets), Fake({}), S.nodes)
    assert [r["status"] for r in m["records"]] == ["TRANSPORT_FAILURE"] * 3
    assert m["stopped"] == "REPEATED_TRANSPORT_FAILURE" and m["calls"] == 3
    out = TV.verify_and_extract(tmp_path / "c", dict(PLAN, targets=targets))
    assert out["counts"]["NOT_SERVED"] == 3 and len(out["notAttempted"]) == 2


def test_listed_receipt_with_an_empty_viewer_is_flagged_not_called_absent(tmp_path):
    m = TV.collect(tmp_path / "c", one_target_plan(), Fake({"main.do": (200, main_page(n=0))}), S.nodes)
    assert m["records"][0]["status"] == "LISTED_BUT_VIEWER_EMPTY"


def test_a_tampered_archive_is_refused(tmp_path):
    fake = Fake({"main.do": (200, main_page()), "dcmNo=101": (200, CORRECTION), "dcmNo=102": (200, BODY)})
    TV.collect(tmp_path / "c", one_target_plan(), fake, S.nodes)
    (tmp_path / "c" / "objects.json.gz").write_bytes(b"x")
    with pytest.raises(ValueError, match="ARCHIVE_CHANGED"):
        TV.verify_and_extract(tmp_path / "c", one_target_plan())
