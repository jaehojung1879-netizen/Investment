"""Synthetic source contracts only; no C2 outcomes or network are accessed."""
import gzip
import json

import pytest

from research.c2_economic_source_v1 import source_audit as S
from research.c2_economic_source_v1.frozen_payload_audit import verify_input_object


def audit(dates, values=None, expected=None):
    return S.audit_market_rows(dates, lambda i, c: (values or [(100, 10)] * len(dates))[i][c == 4],
                               expected_sessions=expected or ["2026-09-14"], through="2026-09-14")


def test_future_cutoff_is_applied_before_any_numeric_read():
    def read(i, column):
        assert i == 1, "future observations must not be accessed"
        assert column in (1, 4), "NAV and provider returns must not be accessed"
        return 100 if column == 1 else 10
    result = S.audit_market_rows(["20261106", "20260914"], read,
                                 expected_sessions=["2026-09-14"], through="2026-09-14")
    assert result["status"] == "OBSERVED_MARKET_INPUTS_COVER_GRID"
    assert result["quarantinedAfterCutoff"] == ["2026-11-06"]
    assert result["returnsComputed"] == 0
    assert result["actualFillVerified"] is False


@pytest.mark.parametrize("close", [None, True, 0, -1, "NaN", "Infinity", "unknown"])
def test_invalid_close_is_never_a_fill(close):
    result = audit(["2026-09-14"], [(close, 10)])
    assert result["blockers"] == ["INVALID_MARKET_CLOSE"]


@pytest.mark.parametrize("volume", [None, True, -1, 0.5, "NaN", "missing"])
def test_invalid_volume_is_refused(volume):
    assert "INVALID_REPORTED_VOLUME" in audit(["2026-09-14"], [(100, volume)])["blockers"]


def test_zero_volume_stays_a_separate_execution_blocker():
    assert audit(["2026-09-14"], [(100, 0)])["blockers"] == ["ZERO_REPORTED_VOLUME"]


def test_missing_session_is_not_forward_filled():
    result = audit([], expected=["2026-09-14"])
    assert result["missingSessions"] == ["2026-09-14"]


def test_duplicate_and_off_calendar_dates_are_refused():
    with pytest.raises(S.SourceError, match="DUPLICATE"):
        audit(["2026-09-14", "2026-09-14"])
    assert "OFF_CALENDAR_OBSERVATIONS" in audit(
        ["2026-09-11", "2026-09-13", "2026-09-14"],
        expected=["2026-09-11", "2026-09-14"])["blockers"]


@pytest.mark.parametrize("grid", [[], ["2026-09-15"], ["2026-09-14", "2026-09-14"],
                                  ["2026-09-14", "2026-09-11"]])
def test_independent_grid_must_be_ordered_and_within_cutoff(grid):
    with pytest.raises(S.SourceError, match="ORDERED"):
        S.audit_market_rows([], None, expected_sessions=grid, through="2026-09-14")


def event():
    return {"ticker": "153130", "recordDate": "2026-09-15", "payDate": "2026-09-17", "grossCash": "255"}


def notice():
    return {**event(), "exDate": "2026-09-14", "publishedDate": "2026-09-11",
            "bodySha256": "a" * 64, "scheduleSha256": "b" * 64}


def test_record_date_after_cutoff_cannot_discard_boundary_ex_date():
    result = S.qualify_distributions([event()], [notice()], through="2026-09-14")
    assert result["explicitExDateEvents"][0]["withinCutoff"] is True
    assert result["totalReturnReady"] is False


def test_notice_date_formats_are_canonical_before_cutoff_comparison():
    compact = {**notice(), "exDate": "20260914", "publishedDate": "20260911"}
    result = S.qualify_distributions([event()], [compact], through="2026-09-14")
    assert result["explicitExDateEvents"][0]["exDate"] == "2026-09-14"
    assert result["explicitExDateEvents"][0]["withinCutoff"] is True


def test_no_exdate_inference_and_no_completeness_claim():
    result = S.qualify_distributions([event()], [], through="2026-09-14")
    assert result["unresolvedExDateRecordDates"] == ["2026-09-15"]
    assert result["payloadIntegrityVerifiedByThisFunction"] is False


@pytest.mark.parametrize("field,value,error", [
    ("ticker", "069500", "SECURITY"), ("grossCash", "254", "MISMATCH"),
    ("payDate", "2026-09-18", "MISMATCH"), ("exDate", "2026-09-16", "SEQUENCE"),
    ("publishedDate", "2026-09-15", "SEQUENCE"), ("scheduleSha256", "", "DIGEST")])
def test_notice_identity_amount_schedule_and_original_are_required(field, value, error):
    changed = {**notice(), field: value}
    with pytest.raises(S.SourceError, match=error):
        S.qualify_distributions([event()], [changed], through="2026-09-14")


def test_duplicate_sources_are_refused():
    with pytest.raises(S.SourceError, match="DUPLICATE_NOTICE"):
        S.qualify_distributions([event()], [notice(), notice()], through="2026-09-14")
    with pytest.raises(S.SourceError, match="DUPLICATE_DISTRIBUTION"):
        S.qualify_distributions([event(), event()], [], through="2026-09-14")


def test_raw_hash_is_checked_before_parse(tmp_path):
    path = tmp_path / "source"
    path.write_bytes(b"original")
    assert S.verified_payload(path, S.digest(b"original")) == b"original"
    path.write_bytes(b"amended")
    with pytest.raises(S.SourceError, match="HASH_MISMATCH"):
        S.verified_payload(path, S.digest(b"original"))


def test_target_projection_never_reads_outcome_values():
    class Targets(dict):
        def __getitem__(self, key):
            assert key not in {"grossReturn", "terminalWeights", "dailyGrossNav"}
            return super().__getitem__(key)
    row = Targets(date="2020-01-02", endDate="2020-02-03", signalDate="2020-01-01",
                  weights={"A": 0.2, "B": 0.2, "C": 0.2}, selectedTickers=["A", "B", "C"],
                  grossReturn=object(), terminalWeights=object())
    result = S.fixed_input_projection([row])
    assert result["outcomeFieldsRead"] == [] and result["blocks"] == 1
    assert "weights" not in json.dumps(result)


def test_pinned_reference_refuses_unknown_or_changed_objects(tmp_path):
    with pytest.raises(S.SourceError, match="INVALID_REFERENCE"):
        S.pinned_bytes(tmp_path, {"commit": "main", "path": "research/a.py", "sha256": "0" * 64})
    with pytest.raises(S.SourceError, match="UNAVAILABLE"):
        S.pinned_bytes(tmp_path, {"commit": "0" * 40, "path": "research/a.py", "sha256": "0" * 64})


def test_frozen_input_integrity_is_checked_without_parsing_economic_rows():
    raw = b"SYNTHETIC_NON_JSON_BYTES"
    verify_input_object(gzip.compress(raw), S.digest(raw))
    with pytest.raises(S.SourceError, match="DIGEST_MISMATCH"):
        verify_input_object(gzip.compress(raw), S.digest(b"altered"))
    with pytest.raises(S.SourceError, match="INVALID_GZIP"):
        verify_input_object(b"not gzip", S.digest(raw))
