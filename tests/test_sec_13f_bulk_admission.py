"""Synthetic ZIP fixtures only; no actual SEC bytes or cache changes."""
import csv
import io
from datetime import datetime, timezone
from zipfile import ZipFile

import pytest

from operations.sec_13f_bulk_v1 import admission as a

M = {"id": "test", "cik": "0000000001", "name": "Synthetic"}
URL = "https://www.sec.gov/files/datastandardsinnovation/data/form-13f-data-sets/"
AS_OF = datetime(2026, 12, 2, tzinfo=timezone.utc)


def archive(tmp_path, first, last, number, report, filed, *, total="200",
            report_type="13F HOLDINGS REPORT", omitted="N"):
    p = tmp_path / (first + ".zip")
    acc = "0000000001-26-" + str(number).zfill(6)
    records = {
        "SUBMISSION": {"ACCESSION_NUMBER": acc, "CIK": "1", "FILING_DATE": filed,
                       "SUBMISSIONTYPE": "13F-HR", "PERIODOFREPORT": report},
        "COVERPAGE": {"ACCESSION_NUMBER": acc, "REPORTCALENDARORQUARTER": report,
                      "AMENDMENTNO": "", "AMENDMENTTYPE": "", "REPORTTYPE": report_type},
        "SUMMARYPAGE": {"ACCESSION_NUMBER": acc, "TABLEENTRYTOTAL": "1", "TABLEVALUETOTAL": total,
                        "ISCONFIDENTIALOMITTED": omitted},
        "INFOTABLE": {"ACCESSION_NUMBER": acc, "INFOTABLE_SK": "1", "NAMEOFISSUER": "Synthetic",
                      "TITLEOFCLASS": "COM", "CUSIP": "000000001", "VALUE": "200",
                      "SSHPRNAMT": str(number * 10), "SSHPRNAMTTYPE": "SH", "PUTCALL": ""},
    }
    with ZipFile(p, "w") as z:
        for name, row in records.items():
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=list(row), delimiter="\t")
            w.writeheader()
            w.writerow(row)
            z.writestr(name + ".tsv", buf.getvalue())
    return {"path": str(p), "url": URL + first + "-" + last + "_form13f.zip",
            "sha256": a.digest(p), "retrievedAtUtc": "2026-12-01T12:00:00Z"}


def fixtures(tmp_path):
    return [
        archive(tmp_path, "01jun2026", "31aug2026", 1, "30-JUN-2026", "14-AUG-2026"),
        archive(tmp_path, "01sep2026", "30nov2026", 2, "30-SEP-2026", "16-NOV-2026"),
    ]


def test_candidate_preserves_units_and_compares_consecutive_reports(tmp_path):
    result = a.candidate(fixtures(tmp_path), [M], "2026-09-30", as_of=AS_OF)
    manager = result["candidateManagers"]["test"]
    assert manager["totalValueUsd"] == 200
    assert manager["changes"]["increased"][0]["currentShares"] == 20
    assert manager["status"] == "CANDIDATE_ONLY"
    assert result["publicationAuthorized"] is False
    assert result["productionEffect"] == "NONE"


def test_bad_hash_and_incomplete_coverage_rejected(tmp_path):
    manifest = fixtures(tmp_path)
    with pytest.raises(ValueError, match="INSUFFICIENT_ARCHIVE_COVERAGE"):
        a.candidate(manifest[1:], [M], "2026-09-30", as_of=AS_OF)
    manifest[0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="ARCHIVE_PROVENANCE_MISMATCH"):
        a.candidate(manifest, [M], "2026-09-30", as_of=AS_OF)


def test_summary_mismatch_is_not_a_partial_valid_archive(tmp_path):
    item = archive(tmp_path, "01sep2026", "30nov2026", 2, "30-SEP-2026", "16-NOV-2026", total="201")
    with pytest.raises(ValueError, match="VALUE_TOTAL_MISMATCH"):
        a.load_archive(item["path"], item["url"], item["sha256"], {1},
                       retrieved_at=item["retrievedAtUtc"], as_of=AS_OF)


def test_missing_amendment_number_is_rejected():
    from datetime import date

    row = {"number": 2, "filed": date(2026, 11, 16), "SUBMISSIONTYPE": "13F-HR/A",
           "amendment": "NEW HOLDINGS", "rows": [], "ACCESSION_NUMBER": "synthetic"}
    with pytest.raises(ValueError, match="INCOMPLETE_OR_UNORDERED_AMENDMENTS"):
        a.resolve_chain([row])


@pytest.mark.parametrize("report_type,omitted,warning", [
    ("13F COMBINATION REPORT", "N", "COMBINATION_REPORT"),
    ("13F HOLDINGS REPORT", "Y", "CONFIDENTIAL_SCOPE_NOT_CONFIRMED"),
    ("13F HOLDINGS REPORT", "", "CONFIDENTIAL_SCOPE_NOT_CONFIRMED"),
])
def test_incomplete_disclosure_scope_never_compares_quantities(tmp_path, report_type, omitted, warning):
    manifest = fixtures(tmp_path)
    manifest[1] = archive(tmp_path, "01sep2026", "30nov2026", 2, "30-SEP-2026",
                          "16-NOV-2026", report_type=report_type, omitted=omitted)
    row = a.candidate(manifest, [M], "2026-09-30", as_of=AS_OF)["candidateManagers"]["test"]
    assert row["totalValueUsd"] == 200
    assert row["changes"] is None
    assert warning in row["scopeWarnings"]
    assert row["comparisonStatus"] == "WITHHELD_SCOPE_UNCERTAIN"


@pytest.mark.parametrize("receipt", ["2026-11-27T12:00:00Z", "2026-12-03T12:00:00Z",
                                      "2026-12-01T12:00:00", None])
def test_future_unfinished_or_unzoned_archive_receipt_refused(tmp_path, receipt):
    manifest = fixtures(tmp_path)
    manifest[1]["retrievedAtUtc"] = receipt
    with pytest.raises(ValueError, match="ARCHIVE_CLOCK_INVALID|OFFSET_AWARE_RECEIPT_TIME_REQUIRED"):
        a.candidate(manifest, [M], "2026-09-30", as_of=AS_OF)


def test_actual_2026_q3_deadline_includes_weekend():
    from datetime import date

    assert a._deadline(date(2026, 9, 30)) == date(2026, 11, 16)
    assert a._deadline(date(2026, 12, 31)) == date(2027, 2, 16)
