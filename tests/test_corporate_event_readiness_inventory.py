from copy import deepcopy

import pytest

from research.corporate_event_readiness_v1.inventory import sample_inventory
from research.corporate_event_readiness_v1.universe import (
    liquidity_candidate,
    membership_inventory,
    security_at,
)


def test_inventory_preserves_unknowns_and_conflicting_versions():
    assert sample_inventory([])["repeat_issuer_filing_share"] is None
    row = {"issuer_id": "A", "receipt_id": "R", "received_date": "2024-01-01"}
    result = sample_inventory([row, row])
    assert result["filing_versions"] == 1
    assert result["duplicate_rows_removed"] == 1
    assert result["unique_events"] is None
    assert result["quarantine_share"] is None
    assert result["error_share"] is None
    assert result["mde"] is None
    assert result["overlap"]["H126"] is None
    with pytest.raises(ValueError, match="CONFLICTING_RECEIPT"):
        sample_inventory([row, {**row, "family": "changed"}])


def test_followup_is_a_version_not_an_independent_event():
    rows = [{"issuer_id": "A", "receipt_id": "R", "received_date": "2024-01-01",
             "relation_type": "ORIGINAL", "chain_id": "C"},
            {"issuer_id": "A", "receipt_id": "S", "received_date": "2024-01-02",
             "relation_type": "CORRECTION", "chain_id": "C"}]
    result = sample_inventory(rows, ["2024-01-01", "2024-01-02", "2024-01-03"])
    assert result["filing_versions"] == 2
    assert result["unique_events"] == 1
    assert result["independent_observations"] is None
    assert result["overlap"]["H126"]["originals_with_signal_session"] == 1
    assert result["overlap"]["H126"]["right_censored_windows"] == 1


def test_disappearance_is_not_a_confirmed_delisting():
    result = membership_inventory({"2020-01-02": ["OLD", "A"], "2021-01-04": ["A"]})
    assert result["observed_absent_from_last_snapshot"] == 1
    assert result["confirmed_delisted_count"] is None
    assert result["return_eligible"] is False


def test_identity_uses_local_kr_date_and_never_todays_name_or_future_end():
    row = {"issuer_id": "A", "security_id": "S", "ticker": "OLD", "valid_from": "2020-01-02",
           "known_at": "2020-01-01T15:00:00Z", "source_sha256": "a" * 64,
           "valid_to": "2020-01-03", "end_known_at": "2020-01-04T00:00:00Z"}
    assert security_at([row], "A", "2020-01-01T16:00:00Z")["ticker"] == "OLD"
    assert security_at([row], "A", "2020-01-03T00:00:00Z")["ticker"] == "OLD"
    assert security_at([row], "A", "2020-01-04T00:00:00Z")["status"] == "BLOCKED"
    assert security_at([{**row, "source_sha256": "z" * 64}], "A", "2020-01-02T00:00:00Z")["status"] == "BLOCKED"
    assert security_at([row, row], "A", "2020-01-02T00:00:00Z")["status"] == "BLOCKED"


@pytest.fixture
def liquidity():
    return {"median_traded_value_krw": 1e9, "window_start": "2023-01-01",
            "window_end": "2023-12-31", "known_at": "2024-01-01T00:00:00Z",
            "expected_sessions": 250, "observed_sessions": 250,
            "source_sha256": "a" * 64, "basis": "KRX_ACC_TRDVAL"}


def test_liquidity_is_unapproved_and_future_or_partial_data_cannot_promote(liquidity):
    cutoff = "2024-01-01T00:00:00Z"
    rule = {"minimum_median_traded_value_krw": 1e9}
    assert liquidity_candidate(liquidity, cutoff)["candidate"] is None
    result = liquidity_candidate(liquidity, cutoff, rule)
    assert result["candidate"] is True
    assert result["research_admitted"] is False
    bad = deepcopy(liquidity)
    bad["observed_sessions"] = 249
    assert liquidity_candidate(bad, cutoff, rule)["candidate"] is None
    bad = {**liquidity, "known_at": "2024-01-02T00:00:00Z"}
    assert liquidity_candidate(bad, cutoff, rule)["reason"] == "FUTURE_INFORMATION"
    bad = {**liquidity, "basis": "CLOSE_X_VOLUME"}
    assert liquidity_candidate(bad, cutoff, rule)["candidate"] is None


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, True])
def test_invalid_liquidity_is_not_a_failed_filter(liquidity, value):
    rule = {"minimum_median_traded_value_krw": 1e9}
    result = liquidity_candidate({**liquidity, "median_traded_value_krw": value},
                                 "2024-01-01T00:00:00Z", rule)
    assert result["candidate"] is None
    with pytest.raises(ValueError, match="EXPLICIT_NONNEGATIVE"):
        liquidity_candidate(liquidity, "2024-01-01T00:00:00Z",
                            {"minimum_median_traded_value_krw": value})


def test_no_calendar_or_originals_is_not_zero_overlap():
    row = {"issuer_id": "A", "receipt_id": "R", "received_date": "2024-01-01",
           "relation_type": "CORRECTION", "chain_id": "C"}
    assert sample_inventory([row], [])["overlap"]["H126"] is None
    assert sample_inventory([row], ["2024-01-02"])["overlap"]["H126"] is None


def test_chain_ids_are_issuer_scoped_and_duplicate_originals_block_overlap():
    row = {"issuer_id": "A", "receipt_id": "R", "received_date": "2024-01-01",
           "relation_type": "ORIGINAL", "chain_id": "C"}
    result = sample_inventory([row, {**row, "issuer_id": "B"}], ["2024-01-01", "2024-01-02"])
    assert result["unique_events"] == 2
    result = sample_inventory([row, {**row, "receipt_id": "S"}], ["2024-01-01", "2024-01-02"])
    assert result["overlap"]["H126"] is None
    assert result["overlap_reason"] == "MULTIPLE_ORIGINALS_IN_SAME_CHAIN"


def test_calendar_left_truncation_cannot_move_an_old_event_to_first_session():
    row = {"issuer_id": "A", "receipt_id": "R", "received_date": "2020-01-01",
           "relation_type": "ORIGINAL", "chain_id": "C"}
    result = sample_inventory([row], ["2024-01-01", "2024-01-02"])
    assert result["overlap"]["H126"] is None
    assert result["overlap_reason"] == "LEFT_CENSORED_CALENDAR_RANGE"
    with pytest.raises(ValueError):
        sample_inventory([row], ["not-a-date"])
