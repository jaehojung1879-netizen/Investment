"""`scripts/build_kr_terminal_action_reconstruction_v2.py`'s pure logic on
synthetic fixtures, plus a determinism/honesty check against the real
committed artifact this PR ships (built from a real `signal-history`
checkout, verified in `docs/kr-terminal-action-reconstruction-v2.md`).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location(
    "build_kr_terminal_action_reconstruction_v2",
    ROOT / "scripts/build_kr_terminal_action_reconstruction_v2.py")
BUILD = importlib.util.module_from_spec(spec)
spec.loader.exec_module(BUILD)

from pipeline import kr_terminal_corporate_actions as TCA  # noqa: E402


# --------------------------------------------------------------------------- #
# build_dart_identity -- read straight from the real fetch-state, never
# re-resolved
# --------------------------------------------------------------------------- #
def test_build_dart_identity_reads_success_and_no_identity_states():
    fetch_state = {
        "000030.KS": {"status": "SUCCESS", "corpCode": "00123", "identityBasis": "EXACT_STOCK_CODE"},
        "999999.KS": {"status": "NO_DART_IDENTITY", "basis": "UNRESOLVED"},
        "111111.KS": {"status": "PAGINATION_FAILED"},
    }
    identity = BUILD.build_dart_identity(fetch_state)
    assert identity["000030.KS"] == {"corpCode": "00123", "status": "RESOLVED",
                                     "basis": "EXACT_STOCK_CODE"}
    assert identity["999999.KS"]["status"] == "UNRESOLVED"
    assert "111111.KS" not in identity, \
        "a pagination failure is neither resolved nor unresolved -- it is retried, not reported"


# --------------------------------------------------------------------------- #
# build_terminal_actions -- disclosure metadata never becomes a termination
# type; raw evidence and amendment history ARE captured
# --------------------------------------------------------------------------- #
def _disclosure(ticker, receipt_no, receipt_date, report_name="합병결정"):
    return {"ticker": ticker, "corpCode": "00123", "corpName": "x",
           "reportName": report_name, "disclosureFamilies": ["MERGER"],
           "receiptNo": receipt_no, "receiptDate": receipt_date,
           "filerName": "x", "isAmendment": "정정" in report_name}


def test_a_ticker_with_disclosures_but_no_review_stays_unresolved_with_evidence():
    disclosures = [_disclosure("000030.KS", "20140728000271", "2014-07-28"),
                   _disclosure("000030.KS", "20140814001621", "2014-08-14",
                              report_name="[기재정정]합병결정")]
    identity = {"000030.KS": {"corpCode": "00123", "status": "RESOLVED"}}
    actions = BUILD.build_terminal_actions(disclosures, identity, {"actions": []})
    row = actions["000030.KS"]
    assert row["actionType"] == TCA.TERMINATION_TYPE_UNRESOLVED
    assert row["oldIssuerCorpCode"] == "00123"
    assert set(row["sources"]) == {"DART:20140728000271", "DART:20140814001621"}
    assert len(row["amendmentHistory"]) == 2
    assert row["amendmentHistory"][1]["receiptNumber"] == "20140814001621"
    assert "terminationType" in row["unresolvedFields"]


def test_a_reviewed_book_entry_overrides_the_report_name_only_reading():
    disclosures = [_disclosure("004940.KS", "20130301000111", "2013-03-01")]
    reviewed = TCA.build_record(
        old_security="004940.KS", action_type=TCA.MERGER_CASH, cash_per_old_share=1000.0,
        effective_date="2013-04-25", source_receipt_number="20130301000111",
        source_receipt_date="2013-03-01")
    actions = BUILD.build_terminal_actions(
        disclosures, {}, {"actions": [reviewed]})
    assert actions["004940.KS"]["actionType"] == TCA.MERGER_CASH
    assert actions["004940.KS"]["cashPerOldShare"] == 1000.0


def test_no_termination_type_is_ever_guessed_from_a_report_name():
    # Even an unambiguous single-family match ("합병결정" only) never becomes
    # MERGER_CASH/MERGER_STOCK/etc without a human-reviewed book entry --
    # report names carry no consideration terms (Section 3's own rule).
    disclosures = [_disclosure("000060.KS", "20200101000001", "2020-01-01",
                               report_name="합병결정")]
    actions = BUILD.build_terminal_actions(disclosures, {}, {"actions": []})
    assert actions["000060.KS"]["actionType"] == TCA.TERMINATION_TYPE_UNRESOLVED


# --------------------------------------------------------------------------- #
# Against the real committed artifact this PR ships
# --------------------------------------------------------------------------- #
V2_INVENTORY_PATH = ROOT / "docs/results/kr-terminal-action-reconstruction-v2.json"


@pytest.mark.skipif(not V2_INVENTORY_PATH.exists(), reason="v2 artifact not built")
def test_committed_v2_inventory_matches_the_sealed_audits_22_names():
    inventory = json.loads(V2_INVENTORY_PATH.read_text(encoding="utf-8"))
    audit = json.loads((ROOT / "docs/results/"
                        "alpha-opportunity-model-v3-survivorship-audit.json")
                       .read_text(encoding="utf-8"))
    audit_codes = sorted(row["code"] for row in audit["krTerminations"])
    inventory_codes = sorted(row["code"] for row in inventory["securities"])
    assert inventory_codes == audit_codes
    assert len(inventory_codes) == 22


@pytest.mark.skipif(not V2_INVENTORY_PATH.exists(), reason="v2 artifact not built")
def test_committed_v2_inventory_reflects_the_real_collection_not_a_guess():
    inventory = json.loads(V2_INVENTORY_PATH.read_text(encoding="utf-8"))
    # Verified 2026-09-25 against real GitHub Actions runs 36091590740 /
    # 36094672107 -- see docs/kr-terminal-action-reconstruction-v2.md.
    assert inventory["inputs"]["totalDisclosureRowsOnShard"] == 451
    assert all(row["dartIdentityStatus"] == "RESOLVED" for row in inventory["securities"])
    assert all(row["dartCorpCode"] for row in inventory["securities"])
    # No content-level extraction pipeline exists yet, so termination type
    # stays unresolved for every security -- never guessed from a report
    # name (Section 3's rule).
    assert all(row["terminationType"] == "TERMINATION_TYPE_UNRESOLVED"
              for row in inventory["securities"])
    assert inventory["foundationStatus"] != "READY_FOR_V4_PREREGISTRATION"


@pytest.mark.skipif(not V2_INVENTORY_PATH.exists(), reason="v2 artifact not built")
def test_committed_v2_inventory_sha256_sidecar_matches():
    import hashlib
    sidecar = V2_INVENTORY_PATH.with_suffix(V2_INVENTORY_PATH.suffix + ".sha256")
    assert sidecar.exists()
    assert hashlib.sha256(V2_INVENTORY_PATH.read_bytes()).hexdigest() == \
        sidecar.read_text().strip()


@pytest.mark.skipif(not V2_INVENTORY_PATH.exists(), reason="v2 artifact not built")
def test_no_dividend_section_rows_are_claimed_before_the_operator_has_collected_them():
    inventory = json.loads(V2_INVENTORY_PATH.read_text(encoding="utf-8"))
    if inventory["inputs"]["totalDividendSectionRowsOnShard"] == 0:
        assert all(row["dividendLineageStatus"] == "NOT_COLLECTED"
                  for row in inventory["securities"])


def test_disclosure_list_and_amendments_do_not_resolve_terminal_economics():
    disclosures = [_disclosure("A.KS", "20200101000001", "2020-01-01"),
                   _disclosure("A.KS", "20200201000001", "2020-02-01", "[정정]합병결정")]
    action = BUILD.build_terminal_actions(disclosures, {}, {"actions": []})["A.KS"]
    row = BUILD.INV.completeness_row(identity=None, action=action, dividends=None,
                                     last_trading_date=None)
    assert row["rawEvidenceRetained"] == BUILD.INV.READY
    for field in ("terminalConsiderationResolved", "successorResolvedWhereRequired",
                  "exchangeRatioResolved", "terminalActionChainResolved"):
        assert row[field] == BUILD.INV.BLOCKED
