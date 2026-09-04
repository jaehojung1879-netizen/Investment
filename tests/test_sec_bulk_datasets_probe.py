"""The bulk-dataset probe's parsing, which must hold without a vendor.

The network half can only run in CI. What is pinned here is the part that
decides what the probe's answer MEANS: that submissions are matched by CIK
(a plain integer here, not the zero-padded form the XBRL API's URL path
uses), that numeric facts are filtered to both the matched filing AND a
wanted tag, and that `qtrs` — which states a fact's period length directly,
unlike DART's amount columns that had to be inferred by measurement — is
read as given rather than assumed.
"""
from __future__ import annotations

import importlib.util
import io
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "probe_sec_bulk_datasets", ROOT / "scripts" / "probe_sec_bulk_datasets.py")
P = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = P
_spec.loader.exec_module(P)


def _tsv(rows: list[dict], columns: list[str]) -> str:
    lines = ["\t".join(columns)]
    for row in rows:
        lines.append("\t".join(str(row.get(c, "")) for c in columns))
    return "\n".join(lines) + "\n"


def _zip_bytes(sub_rows=None, num_rows=None, extra_files: dict[str, str] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        if sub_rows is not None:
            archive.writestr("sub.txt", _tsv(
                sub_rows, ["adsh", "cik", "name", "form", "fy", "fp", "period", "filed"]))
        if num_rows is not None:
            archive.writestr("num.txt", _tsv(
                num_rows, ["adsh", "tag", "version", "ddate", "qtrs", "uom", "value"]))
        for name, content in (extra_files or {}).items():
            archive.writestr(name, content)
    return buf.getvalue()


AAPL_SUB = {"adsh": "0000320193-24-000001", "cik": "320193", "name": "APPLE INC",
           "form": "10-Q", "fy": "2024", "fp": "Q1", "period": "20231230",
           "filed": "20240201"}


# --------------------------------------------------------------------------- #
# Reachability shape — a non-ZIP or a ZIP missing the expected files is
# reported, not crashed on
# --------------------------------------------------------------------------- #
def test_a_non_zip_response_is_reported_not_crashed_on():
    entry = P.parse_quarter_zip(b"<html>not a zip</html>", {"AAPL": 320193})
    assert "error" in entry and "zip" in entry["error"].lower()


def test_a_zip_missing_the_expected_files_is_reported():
    raw = _zip_bytes(extra_files={"readme.htm": "hello"})
    entry = P.parse_quarter_zip(raw, {"AAPL": 320193})
    assert "error" in entry
    assert "sub.txt" in entry["error"] or "num.txt" in entry["error"]


# --------------------------------------------------------------------------- #
# CIK matching — plain integers here, not the zero-padded companyfacts form
# --------------------------------------------------------------------------- #
def test_a_known_cik_is_matched_to_its_ticker():
    raw = _zip_bytes(sub_rows=[AAPL_SUB], num_rows=[])
    entry = P.parse_quarter_zip(raw, {"AAPL": 320193})
    assert entry["samplesFound"]["AAPL"]["form"] == "10-Q"
    assert entry["samplesFound"]["AAPL"]["filed"] == "20240201"


def test_an_unmatched_cik_is_absent_not_fabricated():
    raw = _zip_bytes(sub_rows=[AAPL_SUB], num_rows=[])
    entry = P.parse_quarter_zip(raw, {"AAPL": 320193, "JPM": 19617})
    assert "JPM" not in entry["samplesFound"]


# --------------------------------------------------------------------------- #
# Numeric facts — filtered to a matched filing AND a wanted tag
# --------------------------------------------------------------------------- #
def test_a_fact_is_relevant_only_if_both_its_filing_and_tag_are_wanted():
    matched_fact = {"adsh": AAPL_SUB["adsh"], "tag": "NetIncomeLoss",
                    "ddate": "20231230", "qtrs": "1", "uom": "USD", "value": "1000"}
    wrong_tag = {"adsh": AAPL_SUB["adsh"], "tag": "SomeIrrelevantTag",
                "ddate": "20231230", "qtrs": "1", "uom": "USD", "value": "5"}
    wrong_filing = {"adsh": "0000999999-24-000001", "tag": "NetIncomeLoss",
                    "ddate": "20231230", "qtrs": "1", "uom": "USD", "value": "5"}
    raw = _zip_bytes(sub_rows=[AAPL_SUB], num_rows=[matched_fact, wrong_tag, wrong_filing])
    entry = P.parse_quarter_zip(raw, {"AAPL": 320193})

    assert entry["relevantFacts"] == 1
    assert entry["sampleFact"]["value"] == "1000"


def test_qtrs_is_read_directly_not_inferred():
    """Unlike DART's amount columns, `qtrs` states the period length as a
    field — a quarterly fact and a cumulative one are told apart by this
    value, not by measuring ratios over many filings."""
    quarterly = {"adsh": AAPL_SUB["adsh"], "tag": "NetIncomeLoss",
                "ddate": "20231230", "qtrs": "1", "uom": "USD", "value": "300"}
    annual = {"adsh": AAPL_SUB["adsh"], "tag": "Revenues",
             "ddate": "20231230", "qtrs": "4", "uom": "USD", "value": "1200"}
    raw = _zip_bytes(sub_rows=[AAPL_SUB], num_rows=[quarterly, annual])
    entry = P.parse_quarter_zip(raw, {"AAPL": 320193})

    assert entry["qtrsDistribution"] == {"1": 1, "4": 1}


def test_no_relevant_facts_reports_an_empty_distribution_not_a_guess():
    raw = _zip_bytes(sub_rows=[AAPL_SUB], num_rows=[])
    entry = P.parse_quarter_zip(raw, {"AAPL": 320193})
    assert entry["relevantFacts"] == 0
    assert entry["qtrsDistribution"] == {}
    assert "sampleFact" not in entry
