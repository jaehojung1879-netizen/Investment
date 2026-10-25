"""No external traffic, Git dependency or hidden admission in portable recovery."""
from copy import deepcopy
import json
import subprocess

import pytest

from . import portable_collection as P
from . import source_inventory as I
from . import xbrl_recovery as R
from .test_xbrl_recovery import public_target, download_page
from .test_pit_admission import filing, package


@pytest.fixture
def invented_plan(monkeypatch):
    t = public_target()
    monkeypatch.setattr(P, "reference_targets", lambda: [{k: v for k, v in t.items() if k != "mainRaw"}])
    return P.build_plan([t])


def test_no_git_or_original_history_needed_on_receiving_machine(invented_plan, monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError("must not read Git or call a new source")
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(R, "registry", forbidden)
    monkeypatch.setattr(R, "environment_access", lambda: {"status": "ENVIRONMENT_NETWORK_HOST_NOT_ALLOWED"})
    file = tmp_path / "plan.json"
    file.write_text(json.dumps(invented_plan))
    r = P.collect_plan(file, tmp_path / "new")
    assert r["publicRequestsAttempted"] == 0
    assert r["statusCounts"] == {"NOT_ATTEMPTED_ENVIRONMENT_NETWORK_BLOCKED": 1}


@pytest.mark.parametrize("kind", ["code", "receipt", "issuer", "fiscal", "vintage", "main", "authority", "duplicate"])
def test_portable_plan_tampering_refused_before_any_network(invented_plan, kind):
    p = deepcopy(invented_plan)
    if kind == "code":
        p["codeSha256"]["xbrl_recovery.py"] = "0" * 64
    elif kind == "authority":
        p["sourceAdmissionAuthorized"] = True
    elif kind == "duplicate":
        p["targets"] *= 2
    else:
        key = {"receipt": "receipt", "issuer": "corpCode", "fiscal": "fiscalYear",
               "vintage": "availableFrom", "main": "mainBase64"}[kind]
        p["targets"][0][key] = "YmFk" if kind == "main" else "WRONG"
    with pytest.raises(ValueError):
        P.validate_plan(p)


def test_permitted_collection_uses_existing_provenance_reader_not_a_new_shortcut(invented_plan, monkeypatch, tmp_path):
    t = public_target()
    zip_bytes = package(filing(2024))["raw"]
    seen = []
    def transport(url):
        seen.append(url)
        return download_page(t) if "/main.do" in url else zip_bytes
    original_collect = R.collect
    monkeypatch.setattr(R, "collect", lambda targets, output, **kwargs: original_collect(
        targets, output, **kwargs, transport=transport, throttle_seconds=0))
    monkeypatch.setattr(R, "environment_access", lambda: {"status": "UNOBSERVED_ATTEMPT_REQUIRED"})
    file = tmp_path / "plan.json"
    file.write_text(json.dumps(invented_plan))
    r = P.collect_plan(file, tmp_path / "new")
    assert len(seen) == 2
    assert r["newHistoricalLabelsRead"] == 0
    assert r["statusCounts"] == {"ACQUIRED_UNVERIFIED_ORIGINAL_XBRL_ZIP": 1}
    assert len(R.load_packages(tmp_path / "new")) == 1
    assert invented_plan["sourceAdmissionAuthorized"] is False


def test_export_refuses_overwrite_and_preserves_exact_main(monkeypatch, tmp_path, invented_plan):
    targets = P.validate_plan(invented_plan)
    monkeypatch.setattr(R, "registry", lambda _: targets)
    path = tmp_path / "plan.json.gz"
    r = P.export_plan(path)
    assert r["publicRequestsAttempted"] == 0
    assert P.validate_plan(P.read_plan(path)) == targets
    with pytest.raises(FileExistsError):
        P.export_plan(path)


def test_committed_plan_has_exact_68_original_metadata_and_current_transport_hashes():
    path = P.HERE / "xbrl_recovery_v2/portable-plan.json.gz"
    targets = P.validate_plan(P.read_plan(path))
    assert len(targets) == len({t["receipt"] for t in targets}) == 68
    assert len({t["corpCode"] for t in targets}) == 14
    assert all(t["originalFinancialValuesVerified"] is False for t in targets)


def test_older_fiscal_report_and_same_ticker_are_not_original_receipt_substitutes():
    rows = [{"ticker": "SYN", "fiscalYear": 2015, "reportCode": "11014", "receiptNos": ["20151114000001"]}]
    report = I.compare(rows, [{"ticker": "SYN", "receipt": "20170331000001"}])
    assert report["sameReceiptMetadataCount"] == 0
    assert report["originalZipBytesRecovered"] == report["originalFinancialFactsVerified"] == 0


def test_even_same_receipt_metadata_does_not_prove_original_bytes_or_amounts():
    rows = [{"fiscalYear": 2020, "reportCode": "11011", "receiptNos": ["20210331000001"]}]
    report = I.compare(rows, [{"receipt": "20210331000001"}])
    assert report["sameReceiptMetadataCount"] == 1
    assert report["originalZipBytesRecovered"] == report["originalFinancialFactsVerified"] == 0


def test_weekend_calendar_example_does_not_silently_become_a_legal_deadline():
    report = I.filing_lags([{"receipt": "20180402000001", "fiscalYear": 2017,
                            "periodEndMonth": "2017-12", "availableFrom": "2018-04-02"}])
    row = report["rows"][0]
    assert row["monthEndToReceiptCalendarDaysDiagnostic"] == 92
    assert row["naive90DayDateDiagnostic"] == "2018-03-31"
    assert row["naive90DayDateWeekday"] == "Saturday"
    assert row["fiscalWindowCertified"] is row["legalDeadlineCertified"] is False
    assert report["selectedPolicy"] is None
    assert report["legalReviewStatus"] == "INCOMPLETE_NOT_READY_TO_PREREGISTER"


def test_new_source_receipts_preserve_denominator_hashes_and_do_not_claim_an_increase():
    directory = P.HERE / "xbrl_recovery_v2"
    receipt = json.loads((directory / "validation-v2.json").read_text())
    for name, expected in receipt["sha256"].items():
        assert P.E.sha((P.HERE / name).read_bytes()) == expected
    inventory = json.loads((directory / "existing-ledger-inventory.json").read_text())
    assert inventory["source"]["codeSha256"] == P.E.sha((P.HERE / "source_inventory.py").read_bytes())
    quality = json.loads((directory / "source-quality-v2.json").read_text())
    assert quality["verifiedOriginalFactsImprovement"] == {"inventory_discipline": 0, "collection_discipline": 0}
    for signal in quality["signals"].values():
        assert signal["denominator"] == sum(signal["exclusiveFirstUnresolvedStage"].values()) == 51360
        assert signal["originalFinancialFactsVerifiedPairs"] == signal["researchEligibleObservations"] == 0
