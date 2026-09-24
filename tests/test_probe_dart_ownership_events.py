"""The DART ownership probe's SERVED/blocked judging logic, pinned without a
network call — this is what the simplified `dart-ownership-events.yml`
workflow's `auto` mode gates collection on, so a wrong verdict here would
either skip a good collection run or let a bad one through silently.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "probe_dart_ownership_events", ROOT / "scripts" / "probe_dart_ownership_events.py")
P = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = P
_spec.loader.exec_module(P)


def _served_entry(fields_ok=True):
    fields = dict.fromkeys(P.EXPECTED_FIELDS, 100.0 if fields_ok else 0.0)
    return {"status": "000 (정상)", "rows": 10, "fieldsPresentPct": fields}


def test_all_fields_present_is_served():
    report = {"samples": {"005930": _served_entry(fields_ok=True)}}
    assert P.classify_verdict(report) == "SERVED"


def test_a_missing_expected_field_is_schema_changed_even_with_rows():
    report = {"samples": {"005930": _served_entry(fields_ok=False)}}
    assert P.classify_verdict(report) == "SCHEMA_CHANGED"


def test_a_fatal_dart_status_with_no_rows_is_auth_required():
    report = {"samples": {"005930": {"status": "010 (등록되지 않은 키)", "rows": 0}}}
    assert P.classify_verdict(report) == "AUTH_REQUIRED"


def test_a_connection_level_error_is_network_error():
    report = {"samples": {"005930": {"error": "TimeoutError: timed out"}}}
    assert P.classify_verdict(report) == "NETWORK_ERROR"


def test_an_http_level_error_with_no_rows_is_blocked_source():
    report = {"samples": {"005930": {"error": "HTTP 403"}}}
    assert P.classify_verdict(report) == "BLOCKED_SOURCE"


def test_no_data_no_error_is_inconclusive_not_served():
    """status 013 (no disclosures for this sample) must never read as SERVED
    — a probe that saw zero rows never confirmed the field set."""
    report = {"samples": {"005930": {"status": "013 (조회된 데이터 없음)", "rows": 0}}}
    assert P.classify_verdict(report) == "INCONCLUSIVE_NO_ROWS"


def test_a_never_seen_report_tp_does_not_downgrade_an_otherwise_served_verdict():
    """A new categorical value is noted separately, never a block — raw
    passthrough handles any string, known or not."""
    entry = _served_entry(fields_ok=True)
    entry["reportTypesSeen"] = {"공시정정": 1}
    report = {"samples": {"005930": entry}}
    assert P.classify_verdict(report) == "SERVED"
