"""Synthetic tests for the register and the evidence map generator."""
import copy
import json

import pytest

from research.master_research_program_v1.evidence_map import build_evidence_map as M
from research.master_research_program_v1.evidence_map import register as R

GOOD = {"researchId": "S4-KR-TEST", "region": "KR", "track": "STOCK", "title": "t", "economicMechanism": "m",
        "overlapWithExisting": "none", "pitSourceAndRights": "DART", "h126h252Feasibility": "PROSPECTIVE_ONLY",
        "effectiveSampleAndMde": "UNKNOWN", "transactionCostMeasurable": "YES", "expectedEconomicImportance": "LOW",
        "prerequisitesAndBlockers": [], "evidenceClass": "NOT_STARTED", "progressStatus": "ACTIVE",
        "highestGatePassed": "G0", "failedGate": None, "nextExecutionUnit": "x", "ownerApprovalRequired": False,
        "priority": {"tier": "P2", "netReturnRelevance": 1, "mechanism": 1, "independence": 1,
                     "sourceObtainable": 1, "timeToDecision": 1, "krUsExtensible": 1},
        "evidenceRefs": []}


def write(tmp_path, name, entries):
    d = tmp_path / name
    d.mkdir()
    (d / "register-entries.json").write_text(json.dumps({"entries": entries}))


def test_valid_entry_passes_and_unknown_mde_is_allowed():
    R.validate(GOOD)


@pytest.mark.parametrize("field", R.REQUIRED)
def test_every_missing_field_is_named(field):
    bad = copy.deepcopy(GOOD)
    bad.pop(field)
    with pytest.raises(ValueError, match=f"MISSING_FIELD:{field}"):
        R.validate(bad)


def test_bad_vocabulary_scores_and_verified_without_g5_fail():
    for patch, msg in (({"region": "JP"}, "BAD_VOCAB:region"), ({"evidenceClass": "PASS"}, "BAD_VOCAB:evidenceClass"),
                       ({"failedGate": "G9"}, "failedGate"), ({"researchId": "Z-1"}, "BAD_ID_PREFIX"),
                       ({"evidenceClass": "VERIFIED_EVIDENCE", "highestGatePassed": "G4"}, "VERIFIED_WITHOUT_G5")):
        with pytest.raises(ValueError, match=msg):
            R.validate({**GOOD, **patch})
    with pytest.raises(ValueError, match="BAD_PRIORITY_SCORE"):
        R.validate({**GOOD, "priority": {**GOOD["priority"], "mechanism": 4}})


def test_duplicate_id_across_lane_files_is_refused(tmp_path):
    write(tmp_path, "a", [GOOD])
    write(tmp_path, "b", [GOOD])
    with pytest.raises(ValueError, match="DUPLICATE_RESEARCH_ID"):
        R.load_all(tmp_path)


def test_prioritize_is_deterministic():
    hi = {**GOOD, "researchId": "S4-B", "priority": {**GOOD["priority"], "tier": "P1"}}
    tie1 = {**GOOD, "researchId": "S4-C"}
    tie2 = {**GOOD, "researchId": "S4-A"}
    order = [e["researchId"] for e in R.prioritize([tie1, hi, tie2])]
    assert order == ["S4-B", "S4-A", "S4-C"]
    assert "S4-B" in R.render_markdown([tie1, hi, tie2]).splitlines()[4]


def test_committed_lane_registers_validate():
    entries = R.load_all()
    assert len(entries) >= 3 and all(e["evidenceClass"] != "VERIFIED_EVIDENCE" for e in entries)


def test_evidence_map_is_regenerated_exactly_and_has_no_verified_cell():
    m = M.build(json.loads(M.CATALOGUE.read_text()))
    assert m["rowCounts"]["VERIFIED_EVIDENCE"] == 0
    assert (M.HERE / "evidence_map.json").read_text() == json.dumps(m, ensure_ascii=False, indent=1,
                                                                     sort_keys=True) + "\n"
    with pytest.raises(ValueError, match="UNMAPPED"):
        M.build({"mainCommit": "x", "lanes": [{"items": [{"id": "unknown-study", "class": "PARTIAL",
                                                          "evidence": "e"}]}]})
