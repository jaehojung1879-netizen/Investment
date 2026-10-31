"""Reconciliation of the KR22 plan with originals the repository already holds. No network, price or outcome."""
import base64
import gzip
import hashlib
import json

import pytest

from . import kr22_collection_plan as P
from . import kr22_repository_originals as R

REPORT = json.loads(R.REPORT.read_text())
CROSSWALK = json.loads((R.K.ROOT / R.CROSSWALK).read_text())


def test_committed_reconciliation_reads_no_outcome_and_admits_nothing():
    s = REPORT["summary"]
    assert REPORT["historicalOutcomesRead"] == 0 and REPORT["pricesRead"] == 0 and REPORT["networkUsed"] is False
    assert s["denominator"] == 22 and s["inWindowSecurities"] == 16 == s["v2IssuersFound"]
    assert s["industryAdmitted"] == {"before": 0, "after": 0}
    assert s["planFiscalYearSlotsAnsweredByRepository"] == s["planFiscalYearSlots"] == 56
    assert s["selectedAnnualReceiptsRetained"] == s["selectedAnnualReceipts"]
    assert s["remainingRequests"] == {"ANNUAL_ORIGINAL_NOT_RETAINED": 0, "DOCUMENT_DIVIDEND_DECISION": 141,
                                      "VIEWER_ROUTE_REQUIRED": 35}
    assert s["securitiesWithExplicitKsicStatement"] == ["012510.KS"]
    for sec in REPORT["securities"]:
        for c in sec["industryCandidates"]:
            assert c["frozenV2TemplateProducedIt"] is False


def test_rebuild_reproduces_the_committed_report():
    assert R.build()["summary"] == REPORT["summary"]


def test_remaining_plan_is_a_digest_pinned_subset_of_the_original_plan():
    plan = P.load_plan(R.REMAINING_PLAN)
    original = {r["receiptNo"]: r for r in P.load_plan()["requests"] if "receiptNo" in r}
    assert plan["counts"]["DOCUMENT_DIVIDEND_DECISION"] == len(plan["requests"]) == 141
    assert all(r["kind"] == "DOCUMENT_DIVIDEND_DECISION" and original[r["receiptNo"]] == r for r in plan["requests"])
    assert plan["reducedFrom"]["planSha256"] == P.load_plan()["planSha256"] and plan["denominator"] == 22


SECTION = ("<HTML><BODY><P>(나) 공시대상 사업부문의 구분 한국표준산업분류 : 응용 소프트웨어 개발 및 공급업 (J58222) "
           "대분류 중분류 소분류 J 출판업 582 소프트웨어 개발및 공급업 5822 시스템</P></BODY></HTML>").encode()


def _world(retained=True, main_title="더존/사업보고서/2016.03.30"):
    main = f"<html><title>{main_title}</title><script>openCorpInfoNew('00000001', 1)</script></html>".encode()
    sources = {hashlib.sha256(b).hexdigest(): b for b in (main, SECTION)}
    shas = list(sources)
    target = {"receiptNos": ["20160330000001"], "corpCode": "00000001", "ticker": "A.KS", "fiscalYear": 2015,
              "identityBasis": "EXACT_STOCK_CODE", "availableFrom": "2016-03-30"}
    record = {"target": target, "responses": [{"sha256": shas[0], "status": 200, "url": "u?rcpNo=20160330000001"},
                                              {"sha256": shas[1], "section": "business_overview", "status": 200}],
              "sections": [{"section": "business_overview", "sha256": shas[1], "node": {"rcpNo": "20160330000001"}}]}
    inventory = [{"issuer": {"corpCode": "00000001"}, "paginationComplete": True, "missingYears": [2016],
                  "selected": [target, dict(target, fiscalYear=2014, receiptNos=["20150331000002"])]}]
    report = {"summary": {"denominator": 22}, "requests": [{
        "code": "A.KS", "dartCorpCode": "00000001", "fiscalYearsNeedingListJsonQuery": [2014, 2016, 2017],
        "annualReportReceiptsHeldInRepository": {}}]}
    plan = {"planSha256": "x", "requests": [{"kind": "DOCUMENT_DIVIDEND_DECISION", "code": "A.KS", "corpCode": "00000001",
                                             "receiptNo": "20160215000009"}]}
    return plan, report, inventory, ({"20160330000001": record} if retained else {}), sources


def test_a_candidate_passes_the_unchanged_admit_but_is_never_counted_as_admitted():
    out = R.reconcile(*_world(), CROSSWALK, [])
    sec = out["securities"][0]
    c = sec["industryCandidates"][0]
    assert (c["reportedCode"], c["reportedLabel"]) == ("J58222", "응용소프트웨어개발및공급업")
    assert c["admitMechanical"] and c["datedIssuerReleaseProven"] and c["crosswalkGroupOfReportedLabel"] is None
    assert [h["crosswalkGroup"] for h in c["statedHierarchy"] if h["level"] == 3] == ["COMMUNICATION_MEDIA_SOFTWARE"]
    assert out["summary"]["industryAdmitted"] == {"before": 0, "after": 0}
    # 2014 is selected, 2016 is listed with no original, 2017 was never answered by the listing.
    assert sec["planFiscalYearSlotsAnsweredByRepository"] == 2
    kinds = sorted(r["kind"] for r in out["remainingRequests"])
    assert kinds == ["ANNUAL_ORIGINAL_NOT_RETAINED", "DOCUMENT_DIVIDEND_DECISION"]


def test_a_release_date_absent_from_the_main_page_title_is_not_proven():
    out = R.reconcile(*_world(main_title="더존/사업보고서/2017.03.30"), CROSSWALK, [])
    assert out["securities"][0]["industryCandidates"][0]["datedIssuerReleaseProven"] is False
    assert out["summary"]["mechanicallyAdmissibleRows"] == 0


def test_load_refuses_a_changed_archive_or_blob(tmp_path):
    batch = tmp_path / R.V2 / "acquired-dart/annual/batch-00"
    batch.mkdir(parents=True)
    (tmp_path / R.V2 / "inventory").mkdir(parents=True)
    (tmp_path / R.V1 / "acquired-dart").mkdir(parents=True)
    body = b"<html>x</html>"
    archive = gzip.compress(json.dumps({"0" * 64: base64.b64encode(body).decode()}).encode())
    (batch / "originals.json.gz").write_bytes(archive)
    manifest = {"archive": "originals.json.gz", "archiveSha256": hashlib.sha256(archive).hexdigest(), "records": []}
    (batch / "manifest-originals.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="V2_SOURCE_SHA_CHANGED"):
        R.load_v2(tmp_path)
    manifest["archiveSha256"] = "f" * 64
    (batch / "manifest-originals.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="V2_ARCHIVE_CHANGED"):
        R.load_v2(tmp_path)


def _transport(plan):
    """A fake OpenDART that serves each planned dividend decision as the header-less KRX form DART really serves."""
    import io
    import zipfile
    by_receipt = {r["receiptNo"]: r for r in plan["requests"]}
    calls = []

    def document(receipt):
        calls.append(("doc", receipt))
        d = by_receipt[receipt]["receiptDate"].replace("-", ".")
        html = ('<html><div class="xforms"><div class="xforms_title">옛이름/현금ㆍ현물 배당 결정/(%s)</div>'
                "<TABLE><TR><TD>6. 배당기준일</TD><TD>2015-12-31</TD></TR></TABLE></div></html>" % d)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("/" + receipt + ".xml", html.encode("cp949"))
        return buf.getvalue()

    def list_page(params, page):
        calls.append(("list", params["corp_code"], params["bgn_de"]))
        rows = [{"corp_code": r["corpCode"], "rcept_no": r["receiptNo"], "rcept_dt": params["bgn_de"],
                 "report_nm": "현금ㆍ현물배당결정"} for r in plan["requests"]
                if r["corpCode"] == params["corp_code"] and r["receiptDate"].replace("-", "") == params["bgn_de"]]
        return {"status": "000", "page_no": 1, "page_count": 100, "total_count": len(rows), "total_page": 1, "list": rows}
    return list_page, document, calls


def test_collect_remaining_runs_end_to_end_through_the_cli(tmp_path, monkeypatch, capsys):
    """Regression: the CLI passed the two DART callers positionally to a keyword-only `collect` and raised TypeError
    before any request; it must now collect, confirm every listing and verify clean."""
    plan = P.load_plan(R.REMAINING_PLAN)
    list_page, document, calls = _transport(plan)
    monkeypatch.setenv("DART_API_KEY", "x" * 40)
    monkeypatch.setattr(P, "_dart_callers", lambda key: (list_page, document))
    monkeypatch.setattr(P.time, "sleep", lambda s: None)
    rc = R.main(["collect-remaining", "--output", str(tmp_path / "acq")])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["stop"] == "COMPLETE" and out["verifyProblems"] == [], out
    assert out["calls"] == 141 and out["listingCalls"] == 141
    assert sum(c[0] == "doc" for c in calls) == 141


def test_confirm_remaining_adds_listings_to_an_existing_acquisition_without_refetching(tmp_path, monkeypatch, capsys):
    plan = P.load_plan(R.REMAINING_PLAN)
    list_page, document, calls = _transport(plan)
    P.collect(plan, tmp_path / "acq", list_page=list_page, document=document, max_calls=141)  # documents only
    assert P.verify(plan, tmp_path / "acq")[0].startswith("ISSUER_NOT_PROVEN_NO_HEADER_NO_LISTING")
    calls.clear()
    monkeypatch.setenv("DART_API_KEY", "x" * 40)
    monkeypatch.setattr(P, "_dart_callers", lambda key: (list_page, document))
    monkeypatch.setattr(P.time, "sleep", lambda s: None)
    rc = R.main(["confirm-remaining", "--input", str(tmp_path / "acq")])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["verifyProblems"] == [] and all(c[0] == "list" for c in calls) and len(calls) == 141


def test_collect_remaining_refuses_to_start_without_a_key(monkeypatch, tmp_path):
    monkeypatch.delenv("DART_API_KEY", raising=False)
    assert R.main(["collect-remaining", "--output", str(tmp_path / "acq")]) == 2
