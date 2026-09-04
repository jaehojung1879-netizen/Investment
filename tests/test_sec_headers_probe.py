"""The header-isolation probe's judgement, pinned without SEC.

The earlier SEC conclusion — "the Actions IP pool is blocked site-wide" — was
reached without sending `Accept-Encoding: gzip, deflate`, which SEC's access
policy asks for alongside the declaring User-Agent. "Undeclared Automated
Tool" is what SEC serves for a non-compliant header set AND what an
IP-reputation refusal looks like from outside, and the two were never
separated. What is pinned here is that the probe can only claim the headers
were the cause when a variant is SERVED while the shipped baseline is REFUSED
in the same run — anything weaker leaves the earlier conclusion standing.
"""
from __future__ import annotations

import gzip
import importlib.util
import io
import json
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location(
    "probe_sec_headers", ROOT / "scripts" / "probe_sec_headers.py")
P = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = P
_spec.loader.exec_module(P)

JSON_BODY = b'{"cik": 320193, "facts": {}}'
BLOCK_PAGE = (b"<html><body>Your Request Originates from an Undeclared "
              b"Automated Tool</body></html>")


def _row(outcome, status=200):
    return {"outcome": outcome, "status": status}


# --------------------------------------------------------------------------- #
# The baseline has to be in the run, or nothing is attributable
# --------------------------------------------------------------------------- #
def test_the_first_variant_is_exactly_what_the_refused_probes_sent():
    variants = P.header_variants("me@example.com")
    name, headers, _ = variants[0]
    assert name == "baseline_as_shipped"
    assert "Accept-Encoding" not in headers
    assert headers["User-Agent"].startswith("InvestmentResearchDashboard/1.1")


def test_every_later_variant_carries_the_header_the_policy_asks_for():
    for name, headers, _ in P.header_variants("me@example.com")[1:]:
        assert headers.get("Accept-Encoding") == "gzip, deflate", name


def test_the_documented_shape_drops_the_slash_version_token():
    variants = dict((n, h) for n, h, _ in P.header_variants("me@example.com"))
    assert "/1.1" not in variants["documented_ua_shape"]["User-Agent"]
    assert variants["documented_ua_shape"]["User-Agent"].endswith("me@example.com")


# --------------------------------------------------------------------------- #
# Classification: a block page is not data, whatever status it wears
# --------------------------------------------------------------------------- #
def test_a_block_page_served_with_200_is_still_blocked():
    outcome, marker = P.classify(200, BLOCK_PAGE)
    assert outcome == "BLOCKED"
    assert "Undeclared" in marker


def test_a_block_page_served_with_403_is_blocked():
    assert P.classify(403, BLOCK_PAGE)[0] == "BLOCKED"


def test_json_with_200_is_served():
    assert P.classify(200, JSON_BODY) == ("SERVED", None)


def test_a_200_that_is_neither_json_nor_a_known_marker_is_not_counted_as_data():
    outcome, marker = P.classify(200, b"<html>something else entirely</html>")
    assert outcome == "BLOCKED"
    assert marker == "200 with a non-JSON body"


# --------------------------------------------------------------------------- #
# Asking for gzip and then not decoding it is its own silent failure
# --------------------------------------------------------------------------- #
def test_a_gzip_body_is_decompressed_before_it_is_judged():
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as fh:
        fh.write(JSON_BODY)
    decoded = P.decode_body(buf.getvalue(), "gzip")
    assert decoded == JSON_BODY
    assert P.classify(200, decoded)[0] == "SERVED"


def test_a_deflate_body_is_decompressed_too():
    compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    raw = compressor.compress(JSON_BODY) + compressor.flush()
    assert P.decode_body(raw, "deflate") == JSON_BODY


def test_an_undecodable_body_is_returned_rather_than_raising():
    assert P.decode_body(b"not actually gzip", "gzip") == b"not actually gzip"


# --------------------------------------------------------------------------- #
# The verdict — the only claim that matters
# --------------------------------------------------------------------------- #
def test_a_variant_served_while_the_baseline_is_refused_blames_the_headers():
    report = P.verdict({"data.sec.gov": {
        "baseline_as_shipped": _row("BLOCKED", 403),
        "plus_accept_encoding": _row("SERVED"),
    }})
    assert report["verdict"] == "HEADERS_WERE_THE_BLOCKER"
    assert "data.sec.gov/plus_accept_encoding" in report["served"]


def test_everything_refused_leaves_the_ip_conclusion_standing():
    report = P.verdict({"data.sec.gov": {
        "baseline_as_shipped": _row("BLOCKED", 403),
        "plus_accept_encoding": _row("BLOCKED", 403),
    }})
    assert report["verdict"] == "REFUSED_ON_EVERY_HEADER_SET"
    assert report["served"] == []


def test_a_baseline_that_also_succeeds_isolates_nothing_and_says_so():
    # If the shipped headers work today, the earlier refusal was not permanent
    # and no variant can be credited with fixing it.
    report = P.verdict({"data.sec.gov": {
        "baseline_as_shipped": _row("SERVED"),
        "plus_accept_encoding": _row("SERVED"),
    }})
    assert report["verdict"] == "BASELINE_SERVED_TOO"
    assert "re-run before concluding" in report["meaning"]
