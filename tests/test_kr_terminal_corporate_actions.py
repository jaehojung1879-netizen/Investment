"""What a normalized KR terminal corporate-action record may claim."""
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline import kr_terminal_corporate_actions as TCA

ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# build_record -- no term without a citing receipt
# --------------------------------------------------------------------------- #
def test_unresolved_record_needs_no_evidence():
    row = TCA.build_record(old_security="000030.KS", action_type=TCA.TERMINATION_TYPE_UNRESOLVED)
    assert row["evidenceStatus"] == TCA.EVIDENCE_UNRESOLVED
    assert row["cashPerOldShare"] is None


def test_cash_merger_with_a_receipt_is_sealed():
    row = TCA.build_record(
        old_security="004940.KS", action_type=TCA.MERGER_CASH,
        cash_per_old_share=1000.0, effective_date="2013-04-25",
        source_receipt_number="20130301000111", source_receipt_date="2013-03-01",
        sources=("DART:20130301000111",))
    assert row["evidenceStatus"] == TCA.EVIDENCE_SEALED
    assert row["cashPerOldShare"] == 1000.0


def test_a_cash_term_with_no_receipt_is_refused_at_construction():
    with pytest.raises(ValueError, match="requires its DART receipt"):
        TCA.build_record(old_security="004940.KS", action_type=TCA.MERGER_CASH,
                         cash_per_old_share=1000.0)


def test_a_successor_with_no_receipt_is_refused_at_construction():
    with pytest.raises(ValueError, match="requires its DART receipt"):
        TCA.build_record(old_security="000830.KS", action_type=TCA.MERGER_STOCK,
                         successor_security="028260.KS")


def test_an_unknown_action_type_is_refused():
    with pytest.raises(ValueError, match="unknown actionType"):
        TCA.build_record(old_security="000030.KS", action_type="NOT_A_REAL_TYPE")


def test_acquirer_is_never_substituted_as_the_terminated_security_itself():
    # An "acquired without evidence" record cannot even be built: no term may
    # exist without a receipt, which is the structural guard against ever
    # substituting an acquirer's identity for an unresolved exit.
    row = TCA.build_record(old_security="003600.KS", action_type=TCA.TERMINATION_TYPE_UNRESOLVED)
    assert row["successorSecurity"] is None


# --------------------------------------------------------------------------- #
# validate_book -- the same checks, reapplied at load time
# --------------------------------------------------------------------------- #
def test_validate_book_accepts_a_clean_book():
    TCA.validate_book([TCA.build_record(
        old_security="004940.KS", action_type=TCA.MERGER_CASH, cash_per_old_share=1000.0,
        source_receipt_number="r1", source_receipt_date="2013-03-01")])


def test_validate_book_rejects_a_duplicate_identity():
    row = TCA.build_record(old_security="004940.KS", action_type=TCA.TERMINATION_TYPE_UNRESOLVED,
                           effective_date="2013-04-25")
    with pytest.raises(ValueError, match="duplicate terminal action"):
        TCA.validate_book([row, dict(row)])


def test_validate_book_rejects_a_hand_edited_unvouched_term():
    # Simulates a JSON file hand-edited to carry a term without its receipt --
    # `build_record` cannot produce this, but `validate_book` must still catch
    # it on load, the same defence `replay_recovery` applies to the US book.
    row = TCA.build_record(old_security="004940.KS", action_type=TCA.TERMINATION_TYPE_UNRESOLVED)
    row["cashPerOldShare"] = 1000.0
    with pytest.raises(ValueError, match="unvouched consideration term"):
        TCA.validate_book([row])


def test_validate_book_rejects_an_unknown_action_type():
    with pytest.raises(ValueError, match="unknown actionType"):
        TCA.validate_book([{"oldSecurity": "x", "actionType": "MADE_UP"}])


def test_load_book_reads_the_reviewed_empty_book():
    book = TCA.load_book(ROOT / "data/kr-terminal-corporate-actions.json")
    assert book["schema"] == TCA.CONTRACT
    assert book["actions"] == [], "no security has actually been resolved in this PR"


# --------------------------------------------------------------------------- #
# chain_successors / successor_has_panel -- lineage only, never a return
# --------------------------------------------------------------------------- #
def test_chain_of_one_link():
    actions = [TCA.build_record(old_security="A", action_type=TCA.MERGER_STOCK,
                                successor_security="B", successor_shares_per_old_share=0.5,
                                source_receipt_number="r1", source_receipt_date="2020-01-01")]
    assert TCA.chain_successors(actions) == {"A": ["A", "B"]}


def test_chain_follows_multiple_links():
    actions = [
        TCA.build_record(old_security="A", action_type=TCA.MERGER_STOCK, successor_security="B",
                         successor_shares_per_old_share=1.0,
                         source_receipt_number="r1", source_receipt_date="2020-01-01"),
        TCA.build_record(old_security="B", action_type=TCA.SHARE_EXCHANGE, successor_security="C",
                         successor_shares_per_old_share=1.0,
                         source_receipt_number="r2", source_receipt_date="2021-01-01"),
    ]
    chains = TCA.chain_successors(actions)
    assert chains["A"] == ["A", "B", "C"]
    assert chains["B"] == ["B", "C"]


def test_chain_stops_rather_than_looping_on_a_cycle():
    actions = [
        TCA.build_record(old_security="A", action_type=TCA.MERGER_STOCK, successor_security="B",
                         successor_shares_per_old_share=1.0,
                         source_receipt_number="r1", source_receipt_date="2020-01-01"),
        TCA.build_record(old_security="B", action_type=TCA.MERGER_STOCK, successor_security="A",
                         successor_shares_per_old_share=1.0,
                         source_receipt_number="r2", source_receipt_date="2020-06-01"),
    ]
    chains = TCA.chain_successors(actions)
    assert chains["A"] == ["A", "B"], "the repeat is never re-appended"


def test_successor_has_panel_reports_terminus_pricing_and_further_action():
    actions = [
        TCA.build_record(old_security="A", action_type=TCA.MERGER_STOCK, successor_security="B",
                         successor_shares_per_old_share=1.0,
                         source_receipt_number="r1", source_receipt_date="2020-01-01"),
        TCA.build_record(old_security="B", action_type=TCA.SHARE_EXCHANGE, successor_security="C",
                         successor_shares_per_old_share=1.0,
                         source_receipt_number="r2", source_receipt_date="2021-01-01"),
    ]
    chains = TCA.chain_successors(actions)
    report = TCA.successor_has_panel(chains, priced={"C"})
    assert report["A"]["terminusHasPricePanel"] is True
    assert report["A"]["terminusHasItsOwnFurtherAction"] is False
    assert report["B"]["terminusHasPricePanel"] is True


def test_no_return_is_ever_computed_by_this_module():
    import inspect
    source = inspect.getsource(TCA)
    for forbidden in ("fwdReturn", "excessReturn", "cagr", "sharpe", "sortino"):
        assert forbidden.lower() not in source.lower()
