"""`scripts/build_kr_termination_inventory.py`'s pure logic, plus a
determinism/foundation-status check against the real sealed artifact this
repository already committed.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location(
    "build_kr_termination_inventory", ROOT / "scripts/build_kr_termination_inventory.py")
BUILD = importlib.util.module_from_spec(spec)
spec.loader.exec_module(BUILD)


def _row(date, code, rank):
    return {"date": date, "ticker": f"{code}.KS", "rank": rank}


# --------------------------------------------------------------------------- #
# membership_windows
# --------------------------------------------------------------------------- #
def test_first_and_last_membership_dates_from_ranked_rows():
    rows = [_row("2013-01-02", "000030", 40), _row("2013-02-01", "000030", 45),
           _row("2019-02-01", "000030", 118)]
    windows = BUILD.membership_windows(rows, {"000030"})
    assert windows["000030"] == {"first": "2013-01-02", "last": "2019-02-01"}


def test_a_code_never_ranked_gets_no_window_rather_than_a_guessed_one():
    rows = [_row("2013-01-02", "000030", 200)]  # outside KR_TOP=120
    windows = BUILD.membership_windows(rows, {"000030"})
    assert windows["000030"] == {"first": None, "last": None}


def test_a_code_absent_from_rows_entirely_gets_no_window():
    windows = BUILD.membership_windows([], {"999999"})
    assert windows["999999"] == {"first": None, "last": None}


def test_only_top_kr_top_ranked_names_count():
    rows = [_row("2013-01-02", "A", 1), _row("2013-01-02", "B", 121)]
    windows = BUILD.membership_windows(rows, {"A", "B"})
    assert windows["A"]["first"] == "2013-01-02"
    assert windows["B"]["first"] is None


# --------------------------------------------------------------------------- #
# run() -- reads the 22-security list from the sealed audit, never hardcoded
# --------------------------------------------------------------------------- #
def test_run_refuses_an_audit_with_no_kr_terminations(tmp_path):
    audit = {"krTerminations": [], "inputs": {"signalHistoryCommit": "x"}}
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(json.dumps(audit))
    ledger = tmp_path / "input-root" / "ledger" / "universe" / "kr"
    ledger.mkdir(parents=True)
    with pytest.raises(ValueError, match="nothing to build"):
        BUILD.run(tmp_path / "input-root", audit_path)


# --------------------------------------------------------------------------- #
# Against the real committed artifact this PR ships.
# --------------------------------------------------------------------------- #
INVENTORY_PATH = ROOT / "docs/results/kr-termination-inventory.json"


@pytest.mark.skipif(not INVENTORY_PATH.exists(), reason="inventory artifact not built")
def test_committed_inventory_matches_the_sealed_survivorship_audits_22_names():
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    audit = json.loads((ROOT / "docs/results/"
                        "alpha-opportunity-model-v3-survivorship-audit.json")
                       .read_text(encoding="utf-8"))
    audit_codes = sorted(row["code"] for row in audit["krTerminations"])
    inventory_codes = sorted(row["code"] for row in inventory["securities"])
    assert inventory_codes == audit_codes, \
        "the inventory's security list must come from the sealed audit, not be hardcoded"
    assert len(inventory_codes) == 22


@pytest.mark.skipif(not INVENTORY_PATH.exists(), reason="inventory artifact not built")
def test_committed_inventory_is_honest_about_zero_live_dart_collection():
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    assert inventory["foundationStatus"] == "BLOCKED_BY_SOURCE_ACCESS"
    assert all(row["dartCorpCode"] is None for row in inventory["securities"])
    assert all(row["terminationType"] == "TERMINATION_TYPE_UNRESOLVED"
              for row in inventory["securities"])


@pytest.mark.skipif(not INVENTORY_PATH.exists(), reason="inventory artifact not built")
def test_committed_inventory_sha256_sidecar_matches():
    import hashlib
    sidecar = INVENTORY_PATH.with_suffix(INVENTORY_PATH.suffix + ".sha256")
    assert sidecar.exists()
    assert hashlib.sha256(INVENTORY_PATH.read_bytes()).hexdigest() == \
        sidecar.read_text().strip()
