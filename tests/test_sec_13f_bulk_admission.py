"""Synthetic ZIP fixtures only; no actual SEC bytes or cache changes."""
import csv
import io
from zipfile import ZipFile

import pytest

from operations.sec_13f_bulk_v1 import admission as a

M = {"id": "test", "cik": "0000000001", "name": "Synthetic"}
URL = "https://www.sec.gov/files/datastandardsinnovation/data/form-13f-data-sets/"


def archive(tmp_path, first, last, number, report, filed, *, total="200"):
    p = tmp_path / (first + ".zip")
    acc = "0000000001-26-" + str(number).zfill(6)
    records = {
        "SUBMISSION": {"ACCESSION_NUMBER": acc, "CIK": "1", "FILING_DATE": filed,
                       "SUBMISSIONTYPE": "13F-HR", "PERIODOFREPORT": report},
        "COVERPAGE": {"ACCESSION_NUMBER": acc, "REPORTCALENDARORQUARTER": report,
                      "AMENDMENTNO": "", "AMENDMENTTYPE": ""},
        "SUMMARYPAGE": {"ACCESSION_NUMBER": acc, "TABLEENTRYTOTAL": "1", "TABLEVALUETOTAL": total},
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
    return {"path": str(p), "url": URL + first + "-" + last + "_form13f.zip", "sha256": a.digest(p)}


def fixtures(tmp_path):
    return [
        archive(tmp_path, "01jun2026", "31aug2026", 1, "30-JUN-2026", "14-AUG-2026"),
        archive(tmp_path, "01sep2026", "30nov2026", 2, "30-SEP-2026", "16-NOV-2026"),
    ]


def test_candidate_preserves_units_and_compares_consecutive_reports(tmp_path):
    result = a.candidate(fixtures(tmp_path), [M], "2026-09-30")
    manager = result["candidateManagers"]["test"]
    assert manager["totalValueUsd"] == 200
    assert manager["changes"]["increased"][0]["currentShares"] == 20
    assert manager["status"] == "CANDIDATE_ONLY"
    assert result["publicationAuthorized"] is False
    assert result["productionEffect"] == "NONE"


def test_bad_hash_and_incomplete_coverage_rejected(tmp_path):
    manifest = fixtures(tmp_path)
    with pytest.raises(ValueError, match="INSUFFICIENT_ARCHIVE_COVERAGE"):
        a.candidate(manifest[1:], [M], "2026-09-30")
    manifest[0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="ARCHIVE_PROVENANCE_MISMATCH"):
        a.candidate(manifest, [M], "2026-09-30")


def test_summary_mismatch_is_not_a_partial_valid_archive(tmp_path):
    item = archive(tmp_path, "01sep2026", "30nov2026", 2, "30-SEP-2026", "16-NOV-2026", total="201")
    with pytest.raises(ValueError, match="VALUE_TOTAL_MISMATCH"):
        a.load_archive(item["path"], item["url"], item["sha256"], {1})


def test_missing_amendment_number_is_rejected():
    from datetime import date

    row = {"number": 2, "filed": date(2026, 11, 16), "SUBMISSIONTYPE": "13F-HR/A",
           "amendment": "NEW HOLDINGS", "rows": [], "ACCESSION_NUMBER": "synthetic"}
    with pytest.raises(ValueError, match="INCOMPLETE_OR_UNORDERED_AMENDMENTS"):
        a.resolve_chain([row])
