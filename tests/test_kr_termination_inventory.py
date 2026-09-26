"""The per-security completeness matrix and foundation status, on synthetic
fixtures -- the real, sealed inventory is exercised in
`tests/test_build_kr_termination_inventory.py`.
"""
from __future__ import annotations

import pytest

from pipeline import kr_terminal_corporate_actions as TCA
from pipeline import kr_termination_inventory as INV


def _termination(code="004940.KS", krx_name="외환은행", last_session="2013-04-25",
                 dividend_events=0):
    return {"code": code, "krxName": krx_name, "lastSession": last_session,
           "dividendEvents": dividend_events,
           "terminationType": "TERMINATION_TYPE_UNRESOLVED",
           "resolveWith": "DART ..."}


# --------------------------------------------------------------------------- #
# completeness_row
# --------------------------------------------------------------------------- #
def test_fully_unresolved_security_is_blocked_on_every_applicable_field():
    row = INV.completeness_row(identity=None, action=None, dividends=None,
                               last_trading_date="2013-04-25")
    assert row["terminationTypeResolved"] == INV.BLOCKED
    assert row["dartIssuerResolved"] == INV.BLOCKED
    assert row["dividendLineageResolved"] == INV.BLOCKED
    assert row["exDateSemanticsResolved"] == INV.BLOCKED
    assert row["lastTradingDateResolved"] == INV.READY
    for field in ECONOMIC_FIELDS:
        assert row[field] == INV.BLOCKED


def test_ex_date_semantics_stays_blocked_without_a_directly_sourced_ex_date():
    action = TCA.build_record(old_security="004940.KS", action_type=TCA.MERGER_CASH,
                              cash_per_old_share=1000.0, effective_date="2013-04-25",
                              source_receipt_number="r1", source_receipt_date="2013-03-01")
    row = INV.completeness_row(identity={"corpCode": "00123"}, action=action,
                               dividends={"status": INV.DIVIDEND_RESOLVED},
                               last_trading_date="2013-04-25")
    assert row["exDateSemanticsResolved"] == INV.BLOCKED, \
        "no sealed dated KR settlement rule exists and no exDate was directly sourced"


def test_ex_date_semantics_ready_only_for_a_directly_sourced_ex_date():
    ready = INV.completeness_row(
        identity={"corpCode": "00123"}, action=None,
        dividends={"status": INV.DIVIDEND_RESOLVED, "exDateSource": "DIRECT"},
        last_trading_date="2013-04-25")
    derived = INV.completeness_row(
        identity={"corpCode": "00123"}, action=None,
        dividends={"status": INV.DIVIDEND_RESOLVED, "exDateSource": "DERIVED"},
        last_trading_date="2013-04-25")
    assert ready["exDateSemanticsResolved"] == INV.READY
    assert derived["exDateSemanticsResolved"] == INV.BLOCKED, \
        "a derived ex-date is never accepted without a sealed dated rule"


def test_a_cash_merger_with_full_evidence_is_ready_on_every_other_field():
    action = TCA.build_record(old_security="004940.KS", action_type=TCA.MERGER_CASH,
                              cash_per_old_share=1000.0, effective_date="2013-04-25",
                              source_receipt_number="r1", source_receipt_date="2013-03-01",
                              sources=("DART:r1",))
    row = INV.completeness_row(identity={"corpCode": "00123"}, action=action,
                               dividends={"status": INV.DIVIDEND_RESOLVED},
                               last_trading_date="2013-04-25")
    for field in INV.MATRIX_FIELDS:
        if field == "exDateSemanticsResolved":
            continue
        assert row[field] in (INV.READY, INV.NOT_APPLICABLE), field
    assert row["successorResolvedWhereRequired"] == INV.NOT_APPLICABLE, \
        "MERGER_CASH does not require a successor"


def test_a_stock_merger_without_a_successor_stays_blocked_on_that_field():
    action = TCA.build_record(old_security="000830.KS", action_type=TCA.MERGER_STOCK,
                              successor_security=None, effective_date="2015-09-01")
    row = INV.completeness_row(identity={"corpCode": "00123"}, action=action,
                               dividends=None, last_trading_date="2015-09-14")
    assert row["successorResolvedWhereRequired"] == INV.BLOCKED


# --------------------------------------------------------------------------- #
# build_inventory -- security list comes entirely from the caller
# --------------------------------------------------------------------------- #
def test_build_inventory_produces_one_row_per_termination_never_hardcoded():
    terminations = [_termination(code="A.KS"), _termination(code="B.KS")]
    rows = INV.build_inventory(kr_terminations=terminations)
    assert [row["code"] for row in rows] == ["A.KS", "B.KS"]


def test_build_inventory_is_sorted_by_code_deterministically():
    terminations = [_termination(code="Z.KS"), _termination(code="A.KS")]
    rows = INV.build_inventory(kr_terminations=terminations)
    assert [row["code"] for row in rows] == ["A.KS", "Z.KS"]


def test_security_absent_from_an_evidence_map_stays_unresolved():
    rows = INV.build_inventory(kr_terminations=[_termination(code="A.KS")],
                               dart_identity={})  # empty, not missing the key entirely
    assert rows[0]["dartIdentityStatus"] == INV.DART_DIRECTORY_NOT_AVAILABLE
    assert rows[0]["terminationType"] == "TERMINATION_TYPE_UNRESOLVED"


def test_membership_window_is_carried_through_when_supplied():
    rows = INV.build_inventory(
        kr_terminations=[_termination(code="A.KS")],
        kr_membership_windows={"A.KS": {"first": "2013-01-02", "last": "2013-04-01"}})
    assert rows[0]["firstMembershipDate"] == "2013-01-02"
    assert rows[0]["lastMembershipDate"] == "2013-04-01"


# --------------------------------------------------------------------------- #
# foundation_status
# --------------------------------------------------------------------------- #
def test_no_identity_resolved_anywhere_is_blocked_by_source_access():
    rows = INV.build_inventory(kr_terminations=[_termination(code="A.KS")])
    assert INV.foundation_status(rows) == INV.BLOCKED_BY_SOURCE_ACCESS


def test_empty_inventory_is_blocked_by_source_access():
    assert INV.foundation_status([]) == INV.BLOCKED_BY_SOURCE_ACCESS


def test_never_forced_to_ready_and_all_fields_ready_reports_ready():
    action = TCA.build_record(old_security="A.KS", action_type=TCA.MERGER_CASH,
                              cash_per_old_share=1000.0, effective_date="2013-04-25",
                              source_receipt_number="r1", source_receipt_date="2013-03-01",
                              sources=("DART:r1",))
    rows = INV.build_inventory(
        kr_terminations=[_termination(code="A.KS")],
        dart_identity={"A.KS": {"corpCode": "00123", "status": "RESOLVED"}},
        terminal_actions={"A.KS": action},
        dividend_lineage={"A.KS": {"status": INV.DIVIDEND_RESOLVED, "exDateSource": "DIRECT"}})
    assert INV.foundation_status(rows) == INV.READY_FOR_V4_PREREGISTRATION


def test_partial_identity_resolution_with_no_field_ready_is_still_blocked_by_source_access():
    rows = INV.build_inventory(
        kr_terminations=[_termination(code="A.KS"), _termination(code="B.KS")],
        dart_identity={"A.KS": {"status": "NOT_FOUND"}})  # no corpCode -> no field turns READY
    assert INV.foundation_status(rows) == INV.BLOCKED_BY_SOURCE_ACCESS


# --------------------------------------------------------------------------- #
# v2 extension: TERMINAL_ACTION_CHAIN / EXCHANGE_RATIO (Section 19's 12th
# and 8th fields, additive to the v1 completeness matrix)
# --------------------------------------------------------------------------- #
def test_terminal_action_chain_needs_a_captured_amendment_history_and_evidence():
    unresolved = INV.completeness_row(identity=None, action=None, dividends=None,
                                      last_trading_date="2013-04-25")
    assert unresolved["terminalActionChainResolved"] == INV.BLOCKED

    action = TCA.build_record(old_security="004940.KS", action_type=TCA.MERGER_CASH,
                              cash_per_old_share=1000.0, effective_date="2013-04-25",
                              source_receipt_number="r1", source_receipt_date="2013-03-01",
                              sources=("DART:r1",))
    ready = INV.completeness_row(identity={"corpCode": "00123"}, action=action,
                                 dividends=None, last_trading_date="2013-04-25")
    assert ready["terminalActionChainResolved"] == INV.READY


def test_exchange_ratio_not_applicable_for_a_pure_cash_merger():
    action = TCA.build_record(old_security="004940.KS", action_type=TCA.MERGER_CASH,
                              cash_per_old_share=1000.0, effective_date="2013-04-25",
                              source_receipt_number="r1", source_receipt_date="2013-03-01")
    row = INV.completeness_row(identity=None, action=action, dividends=None,
                               last_trading_date="2013-04-25")
    assert row["exchangeRatioResolved"] == INV.NOT_APPLICABLE


def test_exchange_ratio_blocked_until_shares_per_old_share_is_known():
    action = TCA.build_record(old_security="000830.KS", action_type=TCA.MERGER_STOCK,
                              successor_security="028260.KS", successor_shares_per_old_share=None,
                              source_receipt_number="r1", source_receipt_date="2015-08-01")
    row = INV.completeness_row(identity=None, action=action, dividends=None,
                               last_trading_date="2015-09-14")
    assert row["exchangeRatioResolved"] == INV.BLOCKED
    ratio_known = TCA.build_record(
        old_security="000830.KS", action_type=TCA.MERGER_STOCK,
        successor_security="028260.KS", successor_shares_per_old_share=0.42,
        source_receipt_number="r1", source_receipt_date="2015-08-01")
    row2 = INV.completeness_row(identity=None, action=ratio_known, dividends=None,
                                last_trading_date="2015-09-14")
    assert row2["exchangeRatioResolved"] == INV.READY


def test_raw_evidence_retained_counts_disclosure_sources_even_without_a_resolved_term():
    # A security with retained disclosure receipts but no resolved
    # termination type -- exactly this repository's real state for all 22
    # -- still has RAW_EVIDENCE, distinct from having resolved anything.
    action = TCA.build_record(old_security="004940.KS",
                              action_type=TCA.TERMINATION_TYPE_UNRESOLVED,
                              sources=("DART:20130301000111", "DART:20130814001621"))
    row = INV.completeness_row(identity=None, action=action, dividends=None,
                               last_trading_date="2013-04-25")
    assert row["rawEvidenceRetained"] == INV.READY
    assert row["terminationTypeResolved"] == INV.BLOCKED


ECONOMIC_FIELDS = (
    "terminalConsiderationResolved", "successorResolvedWhereRequired",
    "exchangeRatioResolved", "terminalActionChainResolved",
)


@pytest.mark.parametrize("action_type", [TCA.TERMINATION_TYPE_UNRESOLVED, TCA.MERGER_STOCK])
@pytest.mark.parametrize("receipt", [None, "r1"])
def test_raw_receipt_or_sealed_status_without_terms_never_resolves_economics(action_type, receipt):
    action = TCA.build_record(
        old_security="A.KS", action_type=action_type,
        source_receipt_number=receipt, source_receipt_date="2020-01-01",
        sources=("DART:r1",), effective_date="2020-02-01",
        amendment_history=(TCA.build_amendment_entry(
            receipt_number="r1", receipt_date="2020-01-01"),))
    row = INV.completeness_row(identity=None, action=action, dividends=None,
                               last_trading_date=None)
    assert row["rawEvidenceRetained"] == INV.READY
    for field in ECONOMIC_FIELDS:
        assert row[field] == INV.BLOCKED


@pytest.mark.parametrize("action_type", [TCA.INSOLVENCY_DELISTING,
                                         TCA.VOLUNTARY_DELISTING, TCA.OTHER_TERMINATION])
def test_generic_resolved_type_does_not_prove_share_terms_irrelevant(action_type):
    action = TCA.build_record(old_security="A.KS", action_type=action_type)
    row = INV.completeness_row(identity=None, action=action, dividends=None,
                               last_trading_date=None)
    for field in ECONOMIC_FIELDS:
        assert row[field] == INV.BLOCKED


def test_unknown_type_can_have_independently_cited_successor_and_ratio():
    action = TCA.build_record(
        old_security="A.KS", action_type=TCA.TERMINATION_TYPE_UNRESOLVED,
        successor_security="B.KS", successor_shares_per_old_share=0.42,
        source_receipt_number="r1", source_receipt_date="2020-01-01")
    row = INV.completeness_row(identity=None, action=action, dividends=None,
                               last_trading_date=None)
    assert row["successorResolvedWhereRequired"] == INV.READY
    assert row["exchangeRatioResolved"] == INV.READY
    assert row["terminalConsiderationResolved"] == INV.BLOCKED
    assert row["terminalActionChainResolved"] == INV.BLOCKED


@pytest.mark.parametrize("missing", ["successorSecurity", "successorSharesPerOldShare"])
def test_partial_stock_economics_cannot_resolve_consideration_or_chain(missing):
    action = TCA.build_record(
        old_security="A.KS", action_type=TCA.MERGER_STOCK,
        successor_security="B.KS", successor_shares_per_old_share=0.42,
        effective_date="2020-02-01", source_receipt_number="r1",
        source_receipt_date="2020-01-01")
    action[missing] = None
    row = INV.completeness_row(identity=None, action=action, dividends=None,
                               last_trading_date=None)
    assert row["terminalConsiderationResolved"] == INV.BLOCKED
    assert row["terminalActionChainResolved"] == INV.BLOCKED


def test_explicitly_unresolved_chain_cannot_be_ready_from_cited_terms():
    action = TCA.build_record(
        old_security="A.KS", action_type=TCA.MERGER_CASH, cash_per_old_share=0,
        effective_date="2020-02-01", source_receipt_number="r1",
        source_receipt_date="2020-01-01", unresolved_fields=("terminalActionChain",))
    row = INV.completeness_row(identity=None, action=action, dividends=None,
                               last_trading_date=None)
    assert row["terminalConsiderationResolved"] == INV.READY
    assert row["terminalActionChainResolved"] == INV.BLOCKED
