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


# --------------------------------------------------------------------------- #
# Body classification — a block page cannot forge a ZIP's magic bytes, so
# that is checked first and text markers are the fallback, not the rule
# --------------------------------------------------------------------------- #
def test_zip_magic_bytes_are_recognised_regardless_of_status():
    kind, marker = P.classify_body(200, b"PK\x03\x04rest of a real zip...")
    assert kind == "ZIP"
    assert marker is None


def test_sec_block_page_is_recognised_by_its_own_sentence():
    body = b"<html><title>SEC.gov | Request Rate Threshold Exceeded</title></html>"
    kind, marker = P.classify_body(403, body)
    assert kind == "BLOCK_PAGE"
    assert "Request Rate Threshold Exceeded" in marker


def test_undeclared_automated_tool_page_is_also_recognised():
    body = b"<html>Your Request Originates from an Undeclared Automated Tool</html>"
    kind, marker = P.classify_body(403, body)
    assert kind == "BLOCK_PAGE"


def test_json_body_is_told_apart_from_a_block_page():
    kind, marker = P.classify_body(200, b'{"cik": 320193, "name": "Apple Inc."}')
    assert kind == "JSON"
    assert marker is None


def test_html_that_is_not_a_known_block_marker_is_still_reported_as_html():
    # A refusal this probe has never seen must not be misread as data.
    kind, marker = P.classify_body(403, b"<html><body>Access Denied</body></html>")
    assert kind == "HTML"
    assert marker is None


def test_empty_body_is_unknown_not_crashed_on():
    kind, marker = P.classify_body(None, b"")
    assert kind == "UNKNOWN"


# --------------------------------------------------------------------------- #
# The judgement — A/B/C exactly as the task defines them
# --------------------------------------------------------------------------- #
def _bulk(no_ua_kind, fair_kind, fallback_kind=None):
    row = {"bodyKind": no_ua_kind}
    return {
        "requestNoUserAgent": {"bodyKind": no_ua_kind},
        "requestFairAccessUserAgent": {"bodyKind": fair_kind},
        "requestFallbackQuarter": {"bodyKind": fallback_kind} if fallback_kind else None,
    }


def test_a_served_zip_on_the_fair_access_ua_is_viable():
    bulk = _bulk("BLOCK_PAGE", "ZIP")
    verdict = P.judge(bulk, {"data.sec.gov": {"bodyKind": "BLOCK_PAGE"},
                             "www.sec.gov/Archives": {"bodyKind": "BLOCK_PAGE"}})
    assert verdict["verdict"] == "VIABLE"


def test_a_served_zip_on_the_bare_request_alone_is_also_viable():
    # The fair-access request can fail (rate-limited a beat later, say) while
    # the bare first request still answered with the ZIP — that must still
    # count, or the verdict silently depends on request order.
    bulk = _bulk("ZIP", "BLOCK_PAGE")
    verdict = P.judge(bulk, {"data.sec.gov": {"bodyKind": "BLOCK_PAGE"},
                             "www.sec.gov/Archives": {"bodyKind": "BLOCK_PAGE"}})
    assert verdict["verdict"] == "VIABLE"


def test_a_served_fallback_quarter_is_also_viable():
    bulk = _bulk("BLOCK_PAGE", "BLOCK_PAGE", fallback_kind="ZIP")
    verdict = P.judge(bulk, {})
    assert verdict["verdict"] == "VIABLE"


def test_zip_blocked_but_data_sec_or_archives_open_is_partially_viable():
    bulk = _bulk("BLOCK_PAGE", "BLOCK_PAGE")
    verdict = P.judge(bulk, {"data.sec.gov": {"bodyKind": "JSON"},
                             "www.sec.gov/Archives": {"bodyKind": "BLOCK_PAGE"}})
    assert verdict["verdict"] == "PARTIALLY_VIABLE"


def test_everything_refused_from_the_first_request_is_blocked():
    bulk = _bulk("BLOCK_PAGE", "BLOCK_PAGE")
    verdict = P.judge(bulk, {"data.sec.gov": {"bodyKind": "BLOCK_PAGE"},
                             "www.sec.gov/Archives": {"bodyKind": "BLOCK_PAGE"}})
    assert verdict["verdict"] == "BLOCKED"
    assert "self-hosted" in verdict["meaning"] or "local" in verdict["meaning"]


# --------------------------------------------------------------------------- #
# Redirect-chain capture — the caller must see every hop, not just the last
# --------------------------------------------------------------------------- #
def test_no_redirect_handler_stops_urllib_from_following_silently():
    # If this ever followed silently, the probe would report only the final
    # host and misattribute a redirect-time refusal to whichever host
    # happened to answer last. `req` is a non-None sentinel so a mutation
    # that returns it instead of None cannot pass by coincidence.
    handler = P._NoRedirect()
    sentinel_request = object()
    result = handler.redirect_request(sentinel_request, None, 302, "Found", {}, "https://x")
    assert result is None
    assert result is not sentinel_request


# --------------------------------------------------------------------------- #
# expectedFiles / fileSizes — additive to the existing sub.txt/num.txt gate
# --------------------------------------------------------------------------- #
def test_expected_files_reports_all_four_not_just_the_matching_pair():
    raw = _zip_bytes(sub_rows=[AAPL_SUB], num_rows=[],
                     extra_files={"tag.txt": "a\tb\n", "pre.txt": "c\td\n"})
    entry = P.parse_quarter_zip(raw, {"AAPL": 320193})
    assert entry["expectedFiles"] == {"sub.txt": True, "num.txt": True,
                                      "tag.txt": True, "pre.txt": True}
    assert entry["fileSizes"]["tag.txt"] > 0
    assert entry["zipIntegrityOk"] is True


def test_a_corrupted_zip_entry_is_reported_as_failing_integrity():
    raw = bytearray(_zip_bytes(sub_rows=[AAPL_SUB], num_rows=[],
                               extra_files={"tag.txt": "a\tb\n" * 50}))
    # Flip bytes in the middle of the archive, past the local file headers,
    # so the ZIP still opens (namelist works) but a member fails its CRC.
    mid = len(raw) // 2
    for i in range(mid, mid + 20):
        raw[i] ^= 0xFF
    entry = P.parse_quarter_zip(bytes(raw), {"AAPL": 320193})
    assert entry.get("zipIntegrityOk") is False or "error" in entry


def test_a_quarter_zip_missing_tag_and_pre_still_reports_which_ones():
    raw = _zip_bytes(sub_rows=[AAPL_SUB], num_rows=[])
    entry = P.parse_quarter_zip(raw, {"AAPL": 320193})
    assert entry["expectedFiles"]["tag.txt"] is False
    assert entry["expectedFiles"]["pre.txt"] is False
    assert "tag.txt" not in entry["fileSizes"]
