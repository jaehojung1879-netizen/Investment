"""Collection plan, collector and offline verifier. Synthetic DART responses only; no network, no price, no outcome."""
import copy
import io
import json
import zipfile

import pytest

from . import kr22_collection_plan as C

PLAN = C.load_plan()
REPORT = json.loads((C.HERE / "kr22-source-recovery.json").read_text())


def doc_zip(corp, name, body="", member="d.xml"):
    xml = (f'<?xml version="1.0" encoding="utf-8"?><DOCUMENT><DOCUMENT-HEADER><DOCUMENT-NAME ACODE="1">{name}</DOCUMENT-NAME>'
           f'<COMPANY-NAME AREGCIK="{corp}">X</COMPANY-NAME></DOCUMENT-HEADER><BODY>{body}</BODY></DOCUMENT>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(member, xml.encode())
    return buf.getvalue()


DIVIDEND_BODY = ("<TABLE><TR><TD>1. 배당구분</TD><TD>결산배당</TD></TR><TR><TD>3. 1주당 배당금(원)</TD><TD>보통주식</TD>"
                 "<TD>1,250</TD></TR><TR><TD>6. 배당기준일</TD><TD>2015-12-31</TD></TR></TABLE>")
ANNUAL_BODY = "<P>당사는 한국표준산업분류상 (241) 제1차철강제조업 을 영위하고 있습니다.</P>"
MINI = {"contract": C.CONTRACT, "requests": [
    {"kind": "LIST_A001", "code": "A.KS", "corpCode": "00000001", "params": {"bgn_de": "20130101", "end_de": "20171231",
     "corp_code": "00000001", "pblntf_detail_ty": "A001"}, "fiscalYears": [2015]},
    {"kind": "DOCUMENT_ANNUAL", "code": "A.KS", "corpCode": "00000001", "receiptNo": "20170331000001", "fiscalYear": 2016,
     "origin": "KR_RAW_HELD"},
    {"kind": "DOCUMENT_DIVIDEND_DECISION", "code": "A.KS", "corpCode": "00000001", "receiptNo": "20160215000002",
     "receiptDate": "2016-02-15", "isAmendment": False},
    {"kind": "VIEWER_ROUTE_REQUIRED", "code": "A.KS", "corpCode": "00000001", "receiptNo": "20170901000003"}]}
MINI["planSha256"] = C.digest(MINI)
LIST_ROWS = [{"corp_code": "00000001", "rcept_no": "20160330000009", "rcept_dt": "20160330", "report_nm": "사업보고서 (2015.12)"},
             {"corp_code": "00000001", "rcept_no": "20160415000010", "rcept_dt": "20160415", "report_nm": "[기재정정]사업보고서 (2015.12)"},
             {"corp_code": "00000001", "rcept_no": "20150331000011", "rcept_dt": "20150331", "report_nm": "사업보고서 (2014.12)"}]


def fake(documents=None, list_status="000", rows=LIST_ROWS):
    documents = documents or {"20170331000001": doc_zip("00000001", "사업보고서", ANNUAL_BODY),
                              "20160330000009": doc_zip("00000001", "사업보고서", ANNUAL_BODY),
                              "20160215000002": doc_zip("00000001", "현금ㆍ현물배당결정", DIVIDEND_BODY)}
    called = []

    def list_page(params, page):
        called.append(("list", page))
        return {"status": list_status, "page_no": page, "page_count": 100, "total_count": len(rows), "total_page": 1, "list": rows}

    def document(receipt):
        called.append(("doc", receipt))
        return documents[receipt]
    return list_page, document, called


def run(tmp_path, **kw):
    out = tmp_path / "acq"
    lp, doc, called = fake(**kw)
    manifest = C.collect(MINI, out, list_page=lp, document=doc, max_calls=50, now=lambda: "2026-10-26T00:00:00+00:00")
    return out, manifest, called


def test_committed_plan_is_digest_pinned_and_keeps_the_22_denominator():
    assert PLAN["denominator"] == 22 and len(PLAN["inWindowSecurities"]) == 16
    assert len(PLAN["outOfWindowSecuritiesNotRequested"]) == 6
    assert PLAN["counts"]["DOCUMENT_ANNUAL"] == REPORT["summary"]["annualReceiptsHeld"] == 32
    assert PLAN["fiscalYearSlots"] == REPORT["summary"]["fiscalYearsNeedingListJsonQuery"] == 56
    assert PLAN["counts"]["VIEWER_ROUTE_REQUIRED"] == REPORT["summary"]["failedTerminalReceiptsToRetryInWindow"] == 35
    assert PLAN["historicalOutcomesRead"] == 0 and PLAN["pricesRead"] == 0 and PLAN["networkUsed"] is False
    tampered = copy.deepcopy(PLAN)
    tampered["requests"][0]["params"]["end_de"] = "20991231"
    with pytest.raises(ValueError, match="PLAN_DIGEST_MISMATCH"):
        path = __import__("tempfile").mkdtemp() + "/p.json"
        open(path, "w").write(json.dumps(tampered))
        C.load_plan(path)


def test_plan_requests_is_pure_and_refuses_a_corp_code_mismatch_or_unknown_failed_receipt():
    report = {"requests": [{"code": "A.KS", "dartCorpCode": "00000001", "listJsonQuery": None, "fiscalYearsNeedingListJsonQuery": [],
                            "annualReportReceiptsHeldInRepository": {"2016": "20170331000001"}, "failedTerminalReceiptsToRetry": ["R1"]}]}
    disclosures = [{"ticker": "A", "corpCode": "00000001", "receiptNo": "20160215000002", "receiptDate": "2016-02-15",
                    "disclosureFamilies": ["DIVIDEND_DECISION"]}]
    state = {"receipts": {"R1": {"status": "FETCH_FAILED"}}}
    kinds = [r["kind"] for r in C.plan_requests(report, disclosures, state)]
    assert kinds == ["DOCUMENT_ANNUAL", "DOCUMENT_DIVIDEND_DECISION", "VIEWER_ROUTE_REQUIRED"]
    with pytest.raises(ValueError, match="DISCLOSURE_CORP_CODE_DIFFERS"):
        C.plan_requests(report, [dict(disclosures[0], corpCode="00000009")], state)
    with pytest.raises(ValueError, match="FAILED_RECEIPT_NOT_IN_FETCH_STATE"):
        C.plan_requests(report, disclosures, {"receipts": {"R1": {"status": "SUCCESS"}}})


def test_collect_verify_extract_round_trip_and_viewer_route_is_never_called(tmp_path):
    out, manifest, called = run(tmp_path)
    assert manifest["stop"] == "COMPLETE"
    assert ("doc", "20170901000003") not in called                      # VIEWER_ROUTE_REQUIRED is not document.xml
    assert ("doc", "20160415000010") not in called                      # amendment not fetched as the original
    assert ("doc", "20150331000011") not in called                      # fiscal year not needed
    assert C.verify(MINI, out) == []
    rows = {r["receiptNo"]: r for r in C.extract(MINI, out)}
    assert rows["20160215000002"]["recordDate"] == "2015-12-31" and rows["20160215000002"]["commonDividendPerShareKrw"] == 1250
    assert rows["20160215000002"]["exDate"] is None and rows["20160215000002"]["exDateSource"] is None
    assert rows["20160330000009"]["industryCandidates"][0]["reportedLabel"] == "제1차철강제조업"


@pytest.mark.parametrize("mutate,problem", [
    (lambda out, m: (out / m["entries"][-1]["file"]).write_bytes(b"PKtampered"), "SHA256_MISMATCH"),
    (lambda out, m: m["entries"].append(dict(m["entries"][-1])), "DUPLICATE_FILE"),
    (lambda out, m: m["entries"][-1].update(receiptNo="20160215099999"), "RECEIPT_NOT_IN_PLAN"),
    (lambda out, m: m.update(planSha256="0" * 64), "PLAN_DIGEST_MISMATCH"),
    (lambda out, m: m["entries"][-1].update(retrievedAt="2016-01-01T00:00:00+00:00"), "RECEIPT_DATED_AFTER_RETRIEVAL"),
])
def test_verifier_refuses_tampering(tmp_path, mutate, problem):
    out, manifest, _ = run(tmp_path)
    m = json.loads((out / "manifest.json").read_text())
    mutate(out, m)
    (out / "manifest.json").write_text(json.dumps(m))
    assert any(p.startswith(problem) for p in C.verify(MINI, out))
    with pytest.raises(ValueError, match="ACQUISITION_NOT_VERIFIED"):
        C.extract(MINI, out)


def test_issuer_mismatch_and_wrong_document_kind_are_refused(tmp_path):
    docs = {"20170331000001": doc_zip("00000002", "사업보고서", ANNUAL_BODY),
            "20160330000009": doc_zip("00000001", "사업보고서", ANNUAL_BODY),
            "20160215000002": doc_zip("00000001", "주요사항보고서(합병결정)")}
    out, _, _ = run(tmp_path, documents=docs)
    problems = C.verify(MINI, out)
    assert "DOCUMENT_ISSUER_DIFFERS_FROM_PLAN: 20170331000001" in problems
    assert "DOCUMENT_NAME_DIFFERS_FROM_KIND: 20160215000002" in problems


def test_a_discovered_receipt_must_come_from_a_verified_list_response(tmp_path):
    out, _, _ = run(tmp_path)
    m = json.loads((out / "manifest.json").read_text())
    for e in m["entries"]:
        if e["kind"] == "LIST_A001":
            payload = json.loads((out / e["file"]).read_text())
            payload["list"] = payload["list"][1:]
            raw = C.canonical(payload)
            (out / e["file"]).write_bytes(raw)
            e["sha256"] = __import__("hashlib").sha256(raw).hexdigest()
    (out / "manifest.json").write_text(json.dumps(m))
    assert "DISCOVERED_RECEIPT_NOT_IN_VERIFIED_LIST: 20160330000009" in C.verify(MINI, out)


def test_list_rows_from_another_issuer_or_outside_the_window_are_refused(tmp_path):
    rows = LIST_ROWS + [{"corp_code": "00000001", "rcept_no": "20190101000012", "rcept_dt": "20190101", "report_nm": "기타"}]
    out, _, _ = run(tmp_path, rows=rows)
    assert "LIST_ROW_OUTSIDE_QUERY_WINDOW: 20190101000012" in C.verify(MINI, out)
    with pytest.raises(ValueError, match="LIST_ROW_CORP_CODE_DIFFERS"):
        C.annual_receipts_from_list([dict(LIST_ROWS[0], corp_code="00000002")], "00000001", {2015})


def test_a_refusal_stops_the_run_and_014_is_recorded_as_what_dart_said(tmp_path):
    out, manifest, called = run(tmp_path, list_status="020")
    assert manifest["stop"].startswith("Refused") and called == [("list", 1)]
    docs = {"20170331000001": b"<result><status>014</status><message>x</message></result>",
            "20160330000009": doc_zip("00000001", "사업보고서"),
            "20160215000002": doc_zip("00000001", "현금ㆍ현물배당결정", DIVIDEND_BODY)}
    C.collect(MINI, tmp_path / "b", list_page=fake()[0], document=docs.__getitem__, max_calls=50,
              now=lambda: "2026-10-26T00:00:00+00:00")
    assert any(e["status"] == "DART_014" for e in json.loads((tmp_path / "b" / "manifest.json").read_text())["entries"])
    assert C.verify(MINI, tmp_path / "b") == []


def test_budget_is_checked_before_each_call_and_output_must_be_empty(tmp_path):
    lp, doc, called = fake()
    m = C.collect(MINI, tmp_path / "x", list_page=lp, document=doc, max_calls=2, now=lambda: "2026-10-26T00:00:00+00:00")
    assert m["calls"] == 2 and m["stop"].startswith("BudgetExhausted") and len(called) == 2
    with pytest.raises(ValueError, match="OUTPUT_DIRECTORY_NOT_EMPTY"):
        C.collect(MINI, tmp_path / "x", list_page=lp, document=doc, max_calls=2)


def test_zip_traversal_and_member_bombs_are_refused():
    with pytest.raises(ValueError, match="UNSAFE_ZIP_MEMBER"):
        C.zip_members(doc_zip("00000001", "사업보고서", member="../evil.xml"))
    with pytest.raises(ValueError, match="NOT_A_ZIP"):
        C.zip_members(b"<html>")


def test_extractors_state_only_what_the_filing_states():
    assert C.dividend_terms("<P>배당기준일 2016.12.31</P>")["recordDate"] == "2016-12-31"
    stated = C.dividend_terms("<P>배당기준일: 2016-12-31 배당락일: 2016-12-28</P>")
    assert stated["exDate"] == "2016-12-28" and stated["exDateSource"] == "DIRECT"
    assert C.dividend_terms("<P>지급예정일 2017-04-20</P>") == {"recordDate": None, "exDate": None, "exDateSource": None,
                                                              "commonDividendPerShareKrw": None}
    assert C.industry_candidates("<P>당사는 한국표준산업분류에 의거하여 은행업으로 분류되고</P>")[0]["reportedLabel"] == "은행업"
    before = C.industry_candidates("<P>사업분류를 내연기관제조업(표준산업분류 : 29111)으로</P>")[0]
    assert (before["reportedCode"], before["reportedLabel"]) == ("29111", "내연기관제조업")
    assert C.industry_candidates("<P>주요 제품은 반도체입니다.</P>") == []


def test_industry_extractor_recovers_every_fact_in_the_foundations_reviewed_annual_filings():
    """Development recall on the set the patterns were written from (the foundation's 12 recorded explicit facts)."""
    import base64
    import glob
    import gzip
    base = C.HERE.parents[1] / "data/kr-industry-membership-foundation-v1"
    src = {}
    for f in sorted(glob.glob(str(base / "acquired-dart/*.gz"))):
        src.update(json.load(gzip.open(f)))
    obs = json.loads((base / "classification-observations.json").read_text())
    facts = {}
    for x in obs["reportedClassificationFacts"]:
        facts.setdefault(x["source_sha256"], set()).add("".join(x["reportedIndustryLabel"].split()))
    hits, extra = 0, 0
    for sha in {o["source_sha256"] for o in obs["annualFilingObservations"]} | set(facts):
        raw = base64.b64decode(src[sha])
        text = next(raw.decode(e) for e in ("utf-8", "cp949") if _decodes(raw, e))
        labels = {c["reportedLabel"] for c in C.industry_candidates(text)}
        if sha in facts:
            hits += bool(facts[sha] & labels)
        else:
            extra += bool(labels)
    assert (hits, len(facts)) == (12, 12) and extra <= 1


def _decodes(raw, enc):
    try:
        raw.decode(enc)
        return True
    except UnicodeDecodeError:
        return False


def test_acquisition_effect_never_admits_from_a_candidate_and_needs_direct_ex_dates_for_every_event():
    code = REPORT["securities"][0]["code"]
    rows = [{"code": code, "kind": "DOCUMENT_ANNUAL", "industryCandidates": [{"reportedLabel": "은행업"}]},
            {"code": code, "kind": "DOCUMENT_DIVIDEND_DECISION", "recordDate": "2016-12-31", "exDateSource": None}]
    e = C.acquisition_effect(REPORT, rows)
    assert e["gatesAfter"]["industryAdmitted"] == e["gatesBefore"]["industryAdmitted"] == 0
    assert e["gatesAfter"]["exDateSemanticsResolved"] == 0
    assert e["totalReturnLabelEligible"] == {"before": 0, "after": 0} and e["recordDatesStated"] == 1
    rows[1]["exDateSource"] = "DIRECT"
    assert C.acquisition_effect(REPORT, rows)["gatesAfter"]["exDateSemanticsResolved"] == 1
    assert C.acquisition_effect(REPORT)["gatesAfter"] == C.acquisition_effect(REPORT)["gatesBefore"]
