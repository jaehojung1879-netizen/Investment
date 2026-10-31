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


LISTING_ROWS = [{"corp_code": "00000001", "rcept_no": "20160215000002", "rcept_dt": "20160215", "report_nm": "현금ㆍ현물배당결정"}]


def fake(documents=None, list_status="000", rows=LIST_ROWS, listing=LISTING_ROWS):
    documents = documents or {"20170331000001": doc_zip("00000001", "사업보고서", ANNUAL_BODY),
                              "20160330000009": doc_zip("00000001", "사업보고서", ANNUAL_BODY),
                              "20160215000002": doc_zip("00000001", "현금ㆍ현물배당결정", DIVIDEND_BODY)}
    called = []

    def list_page(params, page):
        called.append(("list", page))
        # The annual query names a report type; the dividend listing confirmation asks one issuer on one day.
        got = rows if "pblntf_detail_ty" in params else listing
        return {"status": list_status, "page_no": page, "page_count": 100, "total_count": len(got), "total_page": 1, "list": got}

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


def _doc(m):
    return [e for e in m["entries"] if e["kind"].startswith("DOCUMENT_")][-1]


@pytest.mark.parametrize("mutate,problem", [
    (lambda out, m: (out / _doc(m)["file"]).write_bytes(b"PKtampered"), "SHA256_MISMATCH"),
    (lambda out, m: m["entries"].append(dict(_doc(m))), "DUPLICATE_FILE"),
    (lambda out, m: _doc(m).update(receiptNo="20160215099999"), "RECEIPT_NOT_IN_PLAN"),
    (lambda out, m: m.update(planSha256="0" * 64), "PLAN_DIGEST_MISMATCH"),
    (lambda out, m: _doc(m).update(retrievedAt="2016-01-01T00:00:00+00:00"), "RECEIPT_DATED_AFTER_RETRIEVAL"),
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


# --------------------------------------------------------------------------- #
# KRX exchange-filing forms, the layout 119 of 141 real dividend decisions use
# --------------------------------------------------------------------------- #
def xforms_zip(name="LIG손해보험", date="2016.02.15", title="현금ㆍ현물 배당 결정", member="/20160215000002.xml",
               enc="cp949", members=None):
    html = ('<html><head><meta content="text/html; charset=euc-kr" http-equiv="Content-Type"/><STYLE> .xforms * '
            '{ font-family: 돋움체;} </STYLE></head><body><div class="xforms"><div class="xforms_title">'
            f'{name}/{title}/({date})</div>{title}{DIVIDEND_BODY}</div></body></html>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for m in members or [member]:
            z.writestr(m, html.encode(enc))
    return buf.getvalue()


def xforms_run(tmp_path, listing=LISTING_ROWS, **kw):
    docs = {"20170331000001": doc_zip("00000001", "사업보고서", ANNUAL_BODY),
            "20160330000009": doc_zip("00000001", "사업보고서", ANNUAL_BODY),
            "20160215000002": xforms_zip(**kw)}
    out = tmp_path / "x"
    lp, doc, _ = fake(documents=docs, listing=listing)
    C.collect(MINI, out, list_page=lp, document=doc, max_calls=50, now=lambda: "2026-10-26T00:00:00+00:00")
    return out


def test_a_headerless_exchange_form_is_proven_by_the_listing_not_by_the_filer_name(tmp_path):
    # cp949 bytes, a `/<receipt>.xml` member and a filer name that is not today's name: all as served by DART.
    out = xforms_run(tmp_path)
    assert C.verify(MINI, out) == []
    [row] = [r for r in C.extract(MINI, out) if r["receiptNo"] == "20160215000002"]
    assert row["recordDate"] == "2015-12-31" and row["exDate"] is None and row["exDateSource"] is None


@pytest.mark.parametrize("kw,problem", [
    ({"listing": []}, "LISTING_DOES_NOT_CONFIRM_RECEIPT"),
    ({"listing": [dict(LISTING_ROWS[0], rcept_no="20160215000099")]}, "LISTING_DOES_NOT_CONFIRM_RECEIPT"),
    ({"listing": [dict(LISTING_ROWS[0], report_nm="주주총회소집결의")]}, "LISTING_DOES_NOT_CONFIRM_RECEIPT"),
    ({"listing": [dict(LISTING_ROWS[0], corp_code="00000009")]}, "LISTING_ROW_OUTSIDE_QUERY"),
    ({"listing": [dict(LISTING_ROWS[0], rcept_dt="20160216")]}, "LISTING_ROW_OUTSIDE_QUERY"),
    ({"member": "/20160215000099.xml"}, "DOCUMENT_MEMBER_NOT_THIS_RECEIPT"),
    ({"date": "2016.02.16"}, "DOCUMENT_HEADING_DATE_DIFFERS_FROM_RECEIPT"),
    ({"title": "주주총회소집결의"}, "DOCUMENT_NAME_DIFFERS_FROM_KIND"),
    ({"members": ["20160215000002.xml", "extra.xml"]}, "DOCUMENT_ISSUER_DIFFERS_FROM_PLAN"),
])
def test_a_headerless_form_without_complete_evidence_is_refused(tmp_path, kw, problem):
    out = xforms_run(tmp_path, **kw)
    assert any(p.startswith(problem) for p in C.verify(MINI, out)), C.verify(MINI, out)
    with pytest.raises(ValueError, match="ACQUISITION_NOT_VERIFIED"):
        C.extract(MINI, out)


def test_a_headerless_form_with_no_listing_at_all_is_not_proven(tmp_path):
    out = xforms_run(tmp_path)
    m = json.loads((out / "manifest.json").read_text())
    m["entries"] = [e for e in m["entries"] if e["kind"] != "LISTING_CONFIRMATION"]
    (out / "manifest.json").write_text(json.dumps(m))
    assert "ISSUER_NOT_PROVEN_NO_HEADER_NO_LISTING: 20160215000002" in C.verify(MINI, out)


def test_confirm_listings_completes_an_existing_acquisition_without_refetching_documents(tmp_path):
    out = xforms_run(tmp_path)
    m = json.loads((out / "manifest.json").read_text())
    m["entries"] = [e for e in m["entries"] if e["kind"] != "LISTING_CONFIRMATION"]
    (out / "manifest.json").write_text(json.dumps(m))
    for f in (out / "raw").glob("listing-*"):
        f.unlink()
    lp, _, called = fake()
    m = C.confirm_listings(MINI, out, list_page=lp, max_calls=5, now=lambda: "2026-10-26T00:00:00+00:00")
    assert m["listingStop"] == "COMPLETE" and called == [("list", 1)] and C.verify(MINI, out) == []
    C.confirm_listings(MINI, out, list_page=lp, max_calls=5)        # already confirmed: nothing is asked again
    assert called == [("list", 1)]
    with pytest.raises(ValueError, match="MANIFEST_NOT_FOR_THIS_PLAN"):
        C.confirm_listings(dict(MINI, planSha256="0" * 64), out, list_page=lp, max_calls=5)


def _zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for info, data in entries:
            z.writestr(info, data)
    return buf.getvalue()


def test_only_a_single_leading_slash_before_one_component_is_read_as_relative():
    assert C.safe_member_name("/20160215000002.xml") == "20160215000002.xml"
    assert C.safe_member_name("dir/a.xml") == "dir/a.xml"
    for name in ["/a/b.xml", "//a.xml", "/", "", "../a.xml", "a/../../b.xml", "./a.xml", "a//b.xml", "\\a.xml",
                 "a\\..\\b.xml", "C:a.xml", "a.xml:stream", "a\x00.xml", "/..", "/."]:
        with pytest.raises(ValueError, match="UNSAFE_ZIP_MEMBER"):
            C.safe_member_name(name)


def test_malicious_archives_are_refused_and_never_extracted(tmp_path, monkeypatch):
    link = zipfile.ZipInfo("a.xml")
    link.external_attr = (0o120777 << 16)
    cases = {
        "SYMLINK_ZIP_MEMBER": _zip([(link, b"/etc/passwd")]),
        "DUPLICATE_ZIP_MEMBER": _zip([("/a.xml", b"x"), ("a.xml", b"y")]),
        "ZIP_COMPRESSION_RATIO_EXCEEDED": _zip([("a.xml", b"\0" * (4 << 20))]),
        "UNSAFE_ZIP_MEMBER": _zip([("/a/../../etc/passwd", b"x")]),
        "TOO_MANY_ZIP_MEMBERS": _zip([(f"m{i}.xml", b"x") for i in range(C.MAX_ZIP_MEMBERS + 1)]),
        "UNDECODABLE_ZIP_MEMBER": _zip([("a.xml", b"\xff\xfe\xfa\xfb" * 10)]),
    }
    for problem, raw in cases.items():
        with pytest.raises(ValueError, match=problem):
            C.zip_members(raw)
    # zipfile clears the encryption bit on write, so it is set in both headers directly.
    raw = bytearray(_zip([("b.xml", b"x")]))
    for sig, at in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        i = raw.index(sig) + at
        raw[i] |= 0x1
    with pytest.raises(ValueError, match="ENCRYPTED_ZIP_MEMBER"):
        C.zip_members(bytes(raw))
    monkeypatch.setattr(C, "MAX_TOTAL_BYTES", 10)
    with pytest.raises(ValueError, match="UNSAFE_ZIP_MEMBER"):
        C.zip_members(_zip([("a.xml", b"123456"), ("b.xml", b"123456")]))
    # Nothing was written anywhere by reading any of them.
    assert list(tmp_path.iterdir()) == []


def test_cp949_and_utf8_members_decode_to_the_same_text():
    for enc in ("cp949", "utf-8"):
        [m] = C.zip_members(xforms_zip(enc=enc))
        assert m["encoding"] == enc and m["filename"] == "20160215000002.xml" and m["storedName"] == "/20160215000002.xml"
        assert C.xforms_heading(m["text"]) == ("LIG손해보험", "현금ㆍ현물 배당 결정", "2016-02-15")
