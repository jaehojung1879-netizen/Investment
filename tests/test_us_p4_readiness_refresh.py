"""P4 readiness v2 refresh: outcome-blind, derives CALIBRATED_GEOMETRY from the supplement verdict and nothing else."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import us_p4_readiness_refresh as R     # noqa: E402

READINESS = ROOT / "docs/us-readiness"
V1 = json.loads((READINESS / "us-cash-profitability-exploratory-readiness-v1.json").read_bytes())
PRE = json.loads((READINESS / "us-cash-profitability-exploratory-preflight-v1.json").read_bytes())
IDENT = dict(PRE["identities"])


def supp(status="SUPPLEMENT_PASS", present=30, dev=False, bad=()):
    return {"developmentOnly": dev, "replicates": 2000, "protocolSha256": "p",
            "verdict": {"supplementStatus": status, "cellsPresent": present, "cellsExpected": 30,
                        "primaryStateCounts": {"PASS": present - len(bad)}, "nonPassingCells": list(bad)}}


def make(s):
    return R.refresh(V1, PRE, s, IDENT, "a", "b", "c")


def test_pass_makes_geometry_pass_but_keeps_everything_else_blocked_or_conditional():
    r = make(supp())
    assert r["groups"]["calibrationReadiness"]["state"] == "PASS"
    assert r["scientificReadiness"] == "CONDITIONAL" and r["executionReadiness"] == "BLOCKED"
    assert r["groups"]["survivorshipLimitation"]["state"] == "CONDITIONAL"
    assert r["groups"]["ownerAuthorization"]["state"] == "BLOCKED" and r["groups"]["durableOneShotLock"]["state"] == "BLOCKED"
    assert r["authorizes"] == "NOTHING" and r["executed"] is False
    assert r["interpretation"]["independentConfirmation"] is False and r["interpretation"]["survivorshipUnbiased"] is False
    assert r["counters"]["outcomeReads"] == 0


@pytest.mark.parametrize("s", [supp("SUPPLEMENT_BLOCKED", bad=[{"dgp": "X", "weeks": 260, "state": "INCONCLUSIVE"}]),
                               supp(dev=True), supp(present=29)])
def test_anything_but_a_complete_formal_pass_leaves_geometry_blocked(s):
    r = make(s)
    assert r["groups"]["calibrationReadiness"]["state"] == "BLOCKED" and r["scientificReadiness"] == "BLOCKED"
    assert "NOT dropped" in r["groups"]["calibrationReadiness"]["items"][0]["condition"]


def test_other_items_are_carried_verbatim_from_v1():
    r = make(supp())
    v1 = {i["id"]: i for i in V1["items"]}
    assert r["groups"]["survivorshipLimitation"]["items"][0] == v1["DEPARTED_SECURITIES_AND_TERMINAL_CONSIDERATION"]
    assert r["groups"]["membershipAndIdentityLimitation"]["items"][0] == v1["UNIVERSE_MEMBERSHIP_AND_IDENTITY"]
    assert {i["id"]: i for i in r["carriedUnchangedFromV1"]}["COMPLETE_CASE_SAMPLE"] == v1["COMPLETE_CASE_SAMPLE"]


def test_a_moved_identity_or_nonzero_counter_is_refused():
    moved = {**IDENT, "membershipSha256": "0" * 64}
    with pytest.raises(ValueError, match="PINNED_IDENTITY_CHANGED"):
        R.refresh(V1, PRE, supp(), moved, "a", "b", "c")
    dirty = copy.deepcopy(PRE)
    dirty["counters"]["outcomeReads"] = 1
    with pytest.raises(ValueError, match="COUNTERS_NOT_ZERO"):
        R.refresh(V1, dirty, supp(), IDENT, "a", "b", "c")


def test_committed_v2_if_present_matches_its_inputs():
    path = READINESS / "us-cash-profitability-exploratory-readiness-v2.json"
    if not path.exists():
        pytest.skip("v2 not yet written")
    v2 = json.loads(path.read_bytes())
    s = json.loads((READINESS / "us-h63-inference-calibration-v1-supplement-result.json").read_bytes())
    assert v2 == json.loads(R.canonical(R.refresh(V1, PRE, s, IDENT, R.sha256_file(READINESS / "us-cash-profitability-exploratory-readiness-v1.json"),
                                                  R.sha256_file(READINESS / "us-cash-profitability-exploratory-preflight-v1.json"),
                                                  R.sha256_file(READINESS / "us-h63-inference-calibration-v1-supplement-result.json"))))
