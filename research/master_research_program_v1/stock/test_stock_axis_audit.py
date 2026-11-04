"""Schema and rule tests for the Lane C axis audit and register entries (no network, no outcome)."""
import copy

from research.master_research_program_v1.stock import stock_axis_audit as A

VOCAB = {
    "region": {"KR", "US", "COMMON"},
    "track": {"MARKET", "INDUSTRY", "STOCK", "PORTFOLIO", "DATA"},
    "evidenceClass": {"VERIFIED_EVIDENCE", "EXPLORATORY_EVIDENCE", "EMPIRICAL_FAIL", "SOURCE_BLOCKED",
                      "PREPARED_NOT_EXECUTED", "PROSPECTIVE_PENDING", "NOT_STARTED"},
    "progressStatus": {"ACTIVE", "SOURCE_BACKLOG", "CLOSED", "PARKED"},
    "highestGatePassed": {"NONE", "G0", "G1", "G2", "G3", "G4", "G5", "G6"},
}
FIELDS = ("researchId", "region", "track", "title", "economicMechanism", "overlapWithExisting", "pitSourceAndRights",
          "h126h252Feasibility", "effectiveSampleAndMde", "transactionCostMeasurable", "expectedEconomicImportance",
          "prerequisitesAndBlockers", "evidenceClass", "progressStatus", "highestGatePassed", "failedGate",
          "nextExecutionUnit", "ownerApprovalRequired", "priority", "evidenceRefs")

GATE = {"gate": {"verdict": "UNCERTAIN", "anchorsIntervalPass": 10, "anchorsIntervalUncertain": 100,
                 "anchorsIntervalFail": 45, "anchorsRequired": 93, "anchorsPointEstimatePass": 80},
        "source": {"parseRate": 0.99}, "quarantine": {"quarantined": 3}, "summary": {"pooledBuyerShare": 0.1},
        "quarantineRuleBound": {"gateRuleOff": {"verdict": "UNCERTAIN"}}}


def fresh():
    saved = copy.deepcopy(A.AXES)
    try:
        return A.build(GATE)
    finally:
        A.AXES[:] = saved


def test_at_least_twenty_axes_cover_every_family_in_both_regions():
    ranked, _ = fresh()
    assert len(ranked) >= 20 and len({a["axisId"] for a in ranked}) == len(ranked)
    for fam in ("S1", "S2", "S3", "S4", "S5"):
        regions = {a["region"] for a in ranked if a["family"] == fam}
        assert {"KR", "US"} <= regions, fam


def test_renames_and_recombinations_fail_g0():
    ranked, _ = fresh()
    by = {a["axisId"]: a for a in ranked}
    for axis in ("S3-KR-MOMENTUM-VARIANTS", "S3-KR-VOLUME-ATTENTION-VARIANTS", "S1-KR-VALUE-QUALITY-RECOMBINATION",
                 "S2-US-SUE-WITHOUT-CONSENSUS"):
        assert by[axis]["g0"]["verdict"] == "FAIL" and by[axis]["tier"] == "P3"


def test_at_most_two_non_insider_axes_selected_and_each_passed_g0_g1():
    ranked, selected = fresh()
    by = {a["axisId"]: a for a in ranked}
    assert len(selected) <= 2 and "S4-KR-INSIDER" not in selected
    for axis in selected:
        assert by[axis]["g0"]["verdict"] == "PASS" and by[axis]["g1"]["verdict"] == "PASS"


def test_register_entries_follow_the_schema():
    ranked, _ = fresh()
    for a in ranked:
        e = A.register_entry(a, GATE)
        assert tuple(e) == FIELDS
        assert e["researchId"].split("-")[0] in {"S1", "S2", "S3", "S4", "S5"}
        for key, allowed in VOCAB.items():
            assert e[key] in allowed, (e["researchId"], key, e[key])
        assert e["failedGate"] in (None, "G0", "G1", "G2", "G3", "G4", "G5", "G6")
        assert e["priority"]["tier"] in ("P1", "P2", "P3")
        assert all(0 <= e["priority"][c] <= 3 for c in A.CRITERIA)
        assert e["h126h252Feasibility"].split(":")[0] in ("FEASIBLE", "PROSPECTIVE_ONLY", "BLOCKED")
        assert e["transactionCostMeasurable"].split(":")[0] in ("YES", "PARTIAL", "NO")
        assert e["expectedEconomicImportance"].split(":")[0] in ("HIGH", "MEDIUM", "LOW")
        assert isinstance(e["evidenceRefs"], list) and all("@" in r for r in e["evidenceRefs"])


def test_insider_entry_tracks_the_gate_verdict():
    ranked, _ = fresh()
    ins = next(a for a in ranked if a["axisId"] == "S4-KR-INSIDER")
    for verdict, highest, failed in (("PROJECTED_PASS", "G2", None), ("PROJECTED_FAIL", "G1", "G2"),
                                     ("UNCERTAIN", "G1", None), ("SOURCE_BLOCKED", "G0", "G1")):
        g = copy.deepcopy(GATE)
        g["gate"]["verdict"] = verdict
        e = A.register_entry(ins, g)
        assert (e["highestGatePassed"], e["failedGate"]) == (highest, failed) and e["ownerApprovalRequired"]
    us = next(a for a in ranked if a["axisId"] == "S4-US-FORM4")
    e = A.register_entry(us, GATE)
    assert e["evidenceClass"] == "SOURCE_BLOCKED" and e["progressStatus"] == "SOURCE_BACKLOG"
