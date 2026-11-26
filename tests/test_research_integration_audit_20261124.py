"""research-integration-audit-20261124: the pin audit and the evidence it rests on, from committed bytes only."""
from __future__ import annotations

import json
from pathlib import Path

from research.research_integration_audit_20261124 import check_pins as C

EVIDENCE = Path(C.HERE) / "evidence"


def _load(name: str) -> dict:
    return json.loads((EVIDENCE / name).read_text())


def test_every_pin_mismatch_is_classified_and_none_is_stale():
    result = C.check()
    assert result["unclassified"] == [], result["unclassified"]
    assert result["stale"] == [], result["stale"]
    assert result["verified"] >= 400


def test_repaired_pin_now_verifies():
    audit = _load("pin-audit.json")
    for repair in audit["repairedInThisBranch"]:
        assert C._sha(C.ROOT / repair["path"]) == repair["pinned"]
        assert repair["pinned"] != repair["atPrHead"]


def test_classified_mismatches_name_a_reason():
    allowed = {"SNAPSHOT_IDENTITY_BY_DESIGN", "SAME_COMMIT_CODE_IDENTITY_DRIFT",
               "SUPERSEDED_PROTOCOL_INTENTIONALLY_DISABLED", "RESOLVER_FALSE_POSITIVE"}
    for m in _load("pin-audit.json")["classifiedMismatches"]:
        assert m["classification"] in allowed and m["explanation"]


def test_snapshot_records_hands_off_prs_and_no_closed_pr_lost():
    snap = _load("github-snapshot.json")
    by_number = {p["number"]: p for p in snap["pullRequests"]}
    assert {n for n, p in by_number.items() if p["handsOff"]} == {370, 372, 373}
    assert 371 not in by_number
    assert snap["ladderBranch"]["pullRequest"] is None
    assert _load("closed-pr-preservation.json")["lost"] == []


def test_correction_files_match_the_lineage_record():
    lineage = _load("us-input-lineage.json")["corrections"]
    assert C._sha(C.ROOT / lineage["353"]["file"]) == lineage["353"]["sha256"]
    assert C._sha(C.ROOT / lineage["CTVA"]["receipt"]) == lineage["CTVA"]["receiptSha256"]
