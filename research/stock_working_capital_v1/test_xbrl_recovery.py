"""Offline public-attachment, temporal-cache and pending-policy counterexamples."""
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path

import pytest
import requests

from . import age_policy as AP
from . import features as F
from . import pit_filing_evidence as E
from . import xbrl_recovery as R
from . import source_quality as Q
from .test_pit_admission import filing, meta, package, worker


def public_target():
    m = meta(2024)
    body = (f'<title>테스트기업/사업보고서/2025.03.20</title><script>node1["rcpNo"]="{m["receipt"]}";'
            f"openPdfDownload('{m['receipt']}','12345');</script>").encode()
    m["mainSha256"] = E.sha(body)
    return {**m, "mainRaw": body, "downloadPageUrl": R.popup_url(body, m["receipt"])}


def download_page(target, *, href=None, extra=""):
    receipt = target["receipt"]
    href = href or f"/pdf/download/ifrs.do?rcp_no={receipt}&dcm_no=12345"
    return (f'<table><tr><td>IFRS_XBRL_2024.zip</td><td><a href="{href}">다운로드</a></td></tr>{extra}</table>').encode()


def test_public_original_document_and_attachment_are_bound_to_same_receipt():
    t = public_target()
    result = R.select_attachment(download_page(t), t["downloadPageUrl"], t["receipt"])
    assert result["url"].startswith("https://dart.fss.or.kr/pdf/download/ifrs.do?")
    assert result["filename"].endswith(".zip")


@pytest.mark.parametrize("kind", ["other_receipt", "other_document", "offsite", "javascript", "http", "non_xbrl"])
def test_no_unlawful_or_wrong_original_attachment_fallback(kind):
    t = public_target()
    url = f"/pdf/download/ifrs.do?rcp_no={t['receipt']}&dcm_no=12345"
    if kind == "other_receipt":
        url = url.replace(t["receipt"], "20250321000001")
    elif kind == "other_document":
        url = url.replace("12345", "99999")
    elif kind == "offsite":
        url = "https://evil.invalid" + url
    elif kind == "javascript":
        url = "javascript:download()"
    elif kind == "http":
        url = "http://dart.fss.or.kr" + url
    else:
        url = url.replace("ifrs.do", "excel.do")
    with pytest.raises(ValueError):
        R.select_attachment(download_page(t, href=url), t["downloadPageUrl"], t["receipt"])


def test_ambiguous_original_document_is_not_chosen_by_numeric_values():
    t = public_target()
    more = f"<script>openPdfDownload('{t['receipt']}','99999')</script>".encode()
    with pytest.raises(ValueError, match="AMBIGUOUS"):
        R.popup_url(t["mainRaw"] + more, t["receipt"])


def test_successful_public_recovery_is_still_subject_to_original_fact_validation(tmp_path):
    t = public_target()
    p = package(filing(2024))
    def transport(url):
        return download_page(t) if "/main.do" in url else p["raw"]
    report = R.collect([t], tmp_path / "new", access={"status": "HOST_LISTED_ACTUAL_REQUEST_STILL_REQUIRED"},
                       transport=transport, throttle_seconds=0)
    assert report["publicRequestsAttempted"] == 2
    packages = R.load_packages(tmp_path / "new")
    assert E.original_financial_facts(filing(2024), t, packages[t["receipt"]], "inventory")["ready"]
    assert report["rows"][0]["status"] == "ACQUIRED_UNVERIFIED_ORIGINAL_XBRL_ZIP"


def test_blocked_host_never_becomes_68_absent_sources_or_68_retry_requests(tmp_path):
    calls = []
    def transport(url):
        calls.append(url)
        raise AssertionError("must not request")
    report = R.collect([public_target()] * 68, tmp_path / "new", access={"status": "ENVIRONMENT_NETWORK_HOST_NOT_ALLOWED"},
                       transport=transport, throttle_seconds=0)
    assert report["publicRequestsAttempted"] == 0 and not calls
    assert report["statusCounts"] == {"NOT_ATTEMPTED_ENVIRONMENT_NETWORK_BLOCKED": 68}
    assert R.load_packages(tmp_path / "new") == {}


def test_transport_failure_opens_circuit_not_permanent_source_absence(tmp_path):
    def failure(url):
        raise requests.exceptions.ProxyError("CONNECT tunnel failed:403")
    report = R.collect([public_target()] * 68, tmp_path / "new", access={"status": "UNOBSERVED_ATTEMPT_REQUIRED"},
                       transport=failure, throttle_seconds=0)
    assert report["publicRequestsAttempted"] == 1
    assert report["statusCounts"]["NOT_ATTEMPTED_AFTER_TRANSPORT_FAILURE"] == 67
    assert report["statusCounts"]["TRANSPORT_ACCESS_FAILURE_NOT_SOURCE_ABSENCE"] == 1


def test_public_wrong_original_provenance_and_object_tamper_are_rejected(tmp_path):
    t = public_target()
    p = package(filing(2024))
    R.collect([t], tmp_path / "new", access={"status": "UNOBSERVED_ATTEMPT_REQUIRED"},
              transport=lambda u: download_page(t) if "/main.do" in u else p["raw"], throttle_seconds=0)
    packages = R.load_packages(tmp_path / "new")
    item = packages[t["receipt"]]
    bad = deepcopy(item)
    bad["mainRaw"] += b"wrong-vintage"
    with pytest.raises(ValueError, match="MAIN_SOURCE_DIGEST"):
        E.original_financial_facts(filing(2024), t, bad, "inventory")
    manifest = json.loads((tmp_path / "new/manifest.json").read_text())
    object_path = tmp_path / "new" / manifest["rows"][0]["packageObject"]
    object_path.write_bytes(b"tamper")
    with pytest.raises(ValueError, match="OBJECT_DIGEST"):
        R.load_packages(tmp_path / "new")


def test_date_specific_pair_and_metadata_cache_keys_do_not_reuse_first_asof(monkeypatch):
    w = worker(real_packages=False)
    calls = []
    original = F.annual_pair
    def dated(current, prior, signal):
        calls.append(signal)
        result = original(current, prior, signal)
        if signal >= "2025-04-01":
            result["signals"]["inventory_discipline"]["reasons"].append("SYNTHETIC_DATE_DEPENDENT_GATE")
            result["signals"]["inventory_discipline"]["value"] = None
        return result
    monkeypatch.setattr(F, "annual_pair", dated)
    _, first = w.on("2025-03-21")
    _, later = w.on("2025-04-04")
    assert first[0]["pairAsOf"] == "2025-03-21" and later[0]["pairAsOf"] == "2025-04-04"
    assert calls == ["2025-03-21", "2025-04-04"]
    assert "SYNTHETIC_DATE_DEPENDENT_GATE" in later[0]["signals"]["inventory_discipline"]["reasons"]
    assert {k[-1] for k in w.metadata_cache} == {"2025-03-21", "2025-04-04"}


def test_550_is_not_silently_registered_and_cannot_admit_real_input():
    w = worker()
    w.fiscal_age_policy = AP.pending_policy()
    _, rows = w.on("2025-03-21")
    r = rows[0]["signals"]["inventory_discipline"]
    assert r["originalFinancialFactsMatched"] and r["fiscalWindowsComparable"]
    assert r["legacyFreshnessReferencePassed"] and not r["inputAdmitted"]
    assert "FISCAL_AGE_POLICY_NOT_PREREGISTERED" in r["reasons"]
    policy = json.loads((Path(AP.__file__).parent / "fiscal-age-decision-v1.json").read_text())
    assert policy["selectedPolicy"] is None and not policy["legacyReferenceIsPreregistered"]
    assert {x["id"] for x in policy["options"]} == {"NEXT_ANNUAL_DEADLINE", "FIXED_550_DAYS", "FIXED_365_DAYS"}


def test_legacy_550_boundary_is_explicit_inclusive_not_an_outcome_choice():
    end = F.day("2024-12-31")
    for age in (550, 551):
        w = worker()
        signal = (end + timedelta(days=age)).isoformat()
        # Invented exchange sessions isolate the age boundary from real holidays.
        w.sessions = sorted(set(w.sessions + [signal]))
        w.snapshots.sessions.add(signal)
        _, rows = w.on(signal)
        value = rows[0]["signals"]["inventory_discipline"]
        assert value["fiscalAgeDays"] == age
        assert value["legacyFreshnessReferencePassed"] is (age == 550)
        assert ("STALE_VERIFIED_FISCAL_WINDOW" in value["reasons"]) is (age == 551)


def test_source_reason_partition_preserves_denominator_and_never_reads_returns():
    w = worker(real_packages=False)
    c, rows = w.on("2025-03-21")
    t = public_target()
    manifest = {"rows": [{**t, "status": "NOT_ATTEMPTED_ENVIRONMENT_NETWORK_BLOCKED"}],
                "statusCounts": {"NOT_ATTEMPTED_ENVIRONMENT_NETWORK_BLOCKED": 1}, "publicRequestsAttempted": 0}
    report = Q.decompose([c], rows, manifest)
    for s in F.SIGNALS:
        assert sum(report["signals"][s]["exclusiveFirstUnresolvedStage"].values()) == 3
        assert report["signals"][s]["originalFinancialFactsCoverage"] == 0
    assert report["historicalReturnLabelsRead"] == 0


def test_regenerated_v2_receipts_and_measured_source_counts_are_consistent():
    from . import pit_join as J
    root = Path(__file__).parent
    report = json.loads((root / "pit_measurement_v2/coverage.json").read_text())
    manifest = json.loads((root / "xbrl_recovery_v1/manifest.json").read_text())
    quality = json.loads((root / "xbrl_recovery_v1/source-quality-v1.json").read_text())
    assert J.verify_measurement(root / "pit_measurement_v2")["memberDates"] == 51360
    assert manifest["fixedReceipts"] == 68 and len({r["receipt"] for r in manifest["rows"]}) == 68
    assert quality["originalPackagesAcquiredUnverified"] == sum(r["status"] == "ACQUIRED_UNVERIFIED_ORIGINAL_XBRL_ZIP" for r in manifest["rows"])
    for s in F.SIGNALS:
        assert quality["signals"][s]["originalFinancialFactsVerifiedPairs"] == report["coverage"]["signals"][s]["originalFinancialFactsMatched"]
        assert sum(quality["signals"][s]["exclusiveFirstUnresolvedStage"].values()) == 51360
        assert quality["signals"][s]["researchEligibleObservations"] == 0  # pending F2, not silent550 approval
    for name, expected in report["codeSha256"].items():
        assert E.sha((root / name).read_bytes()) == expected
    assert quality["sourceReceipts"]["codeSha256"] == E.sha(Path(Q.__file__).read_bytes())
