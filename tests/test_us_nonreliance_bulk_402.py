import io
import json
from zipfile import ZipFile

import pytest

from research.us_nonreliance_source_pilot_v1.bulk_402 import FIELDS, extract

CIK = "0000000001"
ROOT = f"CIK{CIK}.json"
OLD = f"CIK{CIK}-submissions-001.json"


def block(items, accession="a", form="8-K", day="2022-01-01"):
    return dict(zip(FIELDS, [[form], [items], [day], [day + "T16:00:00Z"], [accession], [day], ["filing.htm"]]))


def run(recent, old=None, declared=True, include_root=True):
    buf = io.BytesIO()
    with ZipFile(buf, "w") as z:
        if include_root:
            files = [{"name": OLD, "filingFrom": "2020-01-01", "filingTo": "2023-01-01"}] if declared else []
            z.writestr(ROOT, json.dumps({"cik": "1", "filings": {"recent": recent, "files": files}}))
        if old is not None:
            z.writestr(OLD, json.dumps(old))
    with ZipFile(buf) as z:
        return extract(z, [CIK], "2014-01-01", "2026-11-21")


def test_full_intersection_and_standalone():
    r = run(block("2.02,4.02"), block("4.02", "b", "8-K/A"))
    assert r["unique402"] == 2 and r["unique402Without202"] == 1
    assert r["coverageCounts"] == {"DECLARED_PAGES_SCANNED": 1}
    assert all(x["timestampStatus"] == "RAW_UNVERIFIED" for x in r["records"])


def test_missing_page_or_root_not_zero():
    assert run(block("2.02"))["coverageCounts"] == {"INCOMPLETE_PAGES": 1}
    assert run(block("2.02"), include_root=False)["issuers"][0]["missingPages"] == [ROOT]


def test_unknown_items():
    assert run(block(""), declared=False)["coverageCounts"] == {"UNKNOWN_ITEM_CODES": 1}


def test_duplicate_and_conflict():
    assert run(block("4.02"), block("4.02"))["unique402"] == 1
    with pytest.raises(ValueError, match="conflicting"):
        run(block("4.02"), block("2.02"))


def test_exact_item_and_window():
    assert run(block("4.021"), block("4.02", "b", day="2013-12-31"))["unique402"] == 0


def test_misaligned_columns():
    row = block("4.02")
    row["items"] = []
    with pytest.raises(ValueError, match="misaligned"):
        run(row, declared=False)
