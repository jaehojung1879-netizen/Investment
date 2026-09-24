"""The backfill script's pure logic — pagination, bulk-ZIP parsing, and the
resumable reconstruct-instead-of-redownload path — pinned without a network.
"""
from __future__ import annotations

import importlib.util
import io
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "backfill_guru_13f", ROOT / "scripts" / "backfill_guru_13f.py")
B = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = B
_spec.loader.exec_module(B)


# --------------------------------------------------------------------------- #
# list_13f_filings — every filing, paginated, never truncated
# --------------------------------------------------------------------------- #
def _recent_block(rows):
    keys = ("form", "accessionNumber", "filingDate", "reportDate", "primaryDocument")
    return {k: [row[k] for row in rows] for k in keys}


def test_recent_and_older_filings_are_merged_and_forms_are_filtered():
    recent_rows = [
        {"form": "13F-HR", "accessionNumber": "0001-24-000002", "filingDate": "2024-05-15",
         "reportDate": "2024-03-31", "primaryDocument": "x.xml"},
        {"form": "10-K", "accessionNumber": "0001-24-000003", "filingDate": "2024-06-01",
         "reportDate": "2024-03-31", "primaryDocument": "x.xml"},
    ]
    older_rows = [
        {"form": "13F-HR", "accessionNumber": "0001-23-000001", "filingDate": "2023-02-14",
         "reportDate": "2022-12-31", "primaryDocument": "x.xml"},
    ]
    submissions = {
        "filings": {"recent": _recent_block(recent_rows), "files": [{"name": "CIK0000001111-submissions-001.json"}]},
    }

    def fetch_json(url):
        if url.endswith("CIK0000001111-submissions-001.json"):
            # SEC's own paginated shard files are the flat block itself, not
            # wrapped in another {"filings": {"recent": ...}} layer.
            return _recent_block(older_rows)
        return submissions

    filings = B.list_13f_filings("0000001111", fetch_json)
    accessions = {f["accessionNumber"] for f in filings}
    assert accessions == {"0001-24-000002", "0001-23-000001"}, "10-K is filtered out"
    assert filings[0]["reportDate"] == "2022-12-31", "sorted ascending by report date"


def test_duplicate_accessions_across_pages_are_not_double_counted():
    row = {"form": "13F-HR", "accessionNumber": "0001-24-000001", "filingDate": "2024-02-14",
          "reportDate": "2023-12-31", "primaryDocument": "x.xml"}
    submissions = {"filings": {"recent": _recent_block([row]), "files": [{"name": "extra.json"}]}}

    def fetch_json(url):
        if url.endswith("extra.json"):
            return _recent_block([row])
        return submissions

    filings = B.list_13f_filings("0000001111", fetch_json)
    assert len(filings) == 1


# --------------------------------------------------------------------------- #
# parse_bulk_zip — the built-but-unverified bulk dataset route
# --------------------------------------------------------------------------- #
def _tsv(rows, columns):
    lines = ["\t".join(columns)]
    for row in rows:
        lines.append("\t".join(str(row.get(c, "")) for c in columns))
    return "\n".join(lines) + "\n"


def _bulk_zip_bytes(sub_rows, info_rows):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("SUBMISSION.tsv", _tsv(
            sub_rows, ["ACCESSION_NUMBER", "CIK", "SUBMISSIONTYPE", "FILING_DATE", "PERIODOFREPORT"]))
        archive.writestr("INFOTABLE.tsv", _tsv(
            info_rows, ["ACCESSION_NUMBER", "NAMEOFISSUER", "TITLEOFCLASS", "CUSIP", "VALUE",
                       "SSHPRNAMT", "SSHPRNAMTTYPE", "PUTCALL"]))
    return buf.getvalue()


def test_bulk_zip_is_filtered_to_wanted_ciks_and_forms():
    sub_rows = [
        {"ACCESSION_NUMBER": "0001-24-000001", "CIK": "1111111", "SUBMISSIONTYPE": "13F-HR",
         "FILING_DATE": "14-FEB-2024", "PERIODOFREPORT": "31-DEC-2023"},
        {"ACCESSION_NUMBER": "0002-24-000001", "CIK": "9999999", "SUBMISSIONTYPE": "13F-HR",
         "FILING_DATE": "14-FEB-2024", "PERIODOFREPORT": "31-DEC-2023"},
        {"ACCESSION_NUMBER": "0003-24-000001", "CIK": "1111111", "SUBMISSIONTYPE": "13F-NT",
         "FILING_DATE": "14-FEB-2024", "PERIODOFREPORT": "31-DEC-2023"},
    ]
    info_rows = [
        {"ACCESSION_NUMBER": "0001-24-000001", "NAMEOFISSUER": "ALPHA INC", "TITLEOFCLASS": "COM",
         "CUSIP": "111111111", "VALUE": "1000000", "SSHPRNAMT": "10000", "SSHPRNAMTTYPE": "SH",
         "PUTCALL": ""},
        {"ACCESSION_NUMBER": "0002-24-000001", "NAMEOFISSUER": "BETA INC", "TITLEOFCLASS": "COM",
         "CUSIP": "222222222", "VALUE": "500000", "SSHPRNAMT": "5000", "SSHPRNAMTTYPE": "SH",
         "PUTCALL": ""},
    ]
    raw = _bulk_zip_bytes(sub_rows, info_rows)
    out = B.parse_bulk_zip(raw, {"0001111111"})
    assert set(out) == {"0001111111"}, "the unwanted CIK and the 13F-NT are both excluded"
    filings = out["0001111111"]
    assert len(filings) == 1
    assert filings[0]["reportDate"] == "2023-12-31", "DD-MON-YYYY is normalized to ISO"
    assert filings[0]["infoTableRows"][0]["cusip"] == "111111111"


def test_a_non_zip_response_raises_a_readable_error():
    import pytest
    with pytest.raises(zipfile.BadZipFile):
        B.parse_bulk_zip(b"not a zip", {"0001111111"})


def test_a_zip_missing_expected_tables_is_reported_not_crashed_on():
    import pytest
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("README.txt", "nothing useful")
    with pytest.raises(ValueError, match="SUBMISSION"):
        B.parse_bulk_zip(buf.getvalue(), {"0001111111"})


# --------------------------------------------------------------------------- #
# run_backfill — resumable: an already-stored filing is reconstructed, not
# re-downloaded
# --------------------------------------------------------------------------- #
def test_run_backfill_reconstructs_already_stored_filings_instead_of_refetching(tmp_path):
    manager = {"id": "acme", "name": "Acme Capital", "cik": "0001111111"}
    submissions = {"filings": {"recent": _recent_block([
        {"form": "13F-HR", "accessionNumber": "0001-24-000001", "filingDate": "2024-02-14",
         "reportDate": "2023-12-31", "primaryDocument": "x.xml"},
    ])}}

    calls = {"bytes": 0}

    def fetch_json(url):
        return submissions

    def fetch_bytes(url):
        calls["bytes"] += 1
        return (b'<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">'
                b'<infoTable><nameOfIssuer>ALPHA INC</nameOfIssuer><titleOfClass>COM</titleOfClass>'
                b'<cusip>111111111</cusip><value>1000000</value>'
                b'<shrsOrPrnAmt><sshPrnamt>10000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>'
                b'</infoTable></informationTable>')

    # information-table URL resolution needs an index.json fetch too
    def fetch_json_with_index(url):
        if "index.json" in url:
            return {"directory": {"item": [{"name": "infotable.xml", "type": "INFORMATION TABLE"}]}}
        return submissions

    report1 = B.run_backfill(managers=[manager], store_root=tmp_path, start_date="2013-01-01",
                             end_date="2025-01-01", fetch_json=fetch_json_with_index,
                             fetch_bytes=fetch_bytes, bulk_url=None, sleep=lambda s: None)
    assert report1["managers"]["acme"]["filingsDownloaded"] == 1
    assert calls["bytes"] == 1

    report2 = B.run_backfill(managers=[manager], store_root=tmp_path, start_date="2013-01-01",
                             end_date="2025-01-01", fetch_json=fetch_json_with_index,
                             fetch_bytes=fetch_bytes, bulk_url=None, sleep=lambda s: None)
    assert report2["managers"]["acme"]["filingsDownloaded"] == 0
    assert report2["managers"]["acme"]["filingsReconstructedFromStore"] == 1
    assert calls["bytes"] == 1, "the second run must not touch the network for the same filing"
    assert report2["managers"]["acme"]["rowsAppended"] == 0
