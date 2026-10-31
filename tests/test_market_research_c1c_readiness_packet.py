import ast
import copy
import json
from pathlib import Path

import pytest

from pipeline import market_research_c1c_contract as CONTRACT
from pipeline import market_research_c1c_readiness_packet as P


def _committed():
    return json.loads(P.OUTPUT.read_text())


def test_committed_packet_verifies_against_every_identity_on_disk():
    """If this fails, a listed file changed: cut a NEW packet version, never edit this one."""
    packet = _committed()
    assert P.verify(packet) == "SOURCE_BLOCKED"
    assert packet["historicalExecutionAuthorized"] is False and packet["status"] == "SOURCE_BLOCKED"


def test_packet_reads_the_registered_contract_and_leaves_exactly_its_null_fields_null():
    packet = _committed()
    proposal = CONTRACT.contract()["economicExperimentProposal"]
    nulls = sorted(k for k, v in proposal.items() if v is None)
    assert sorted(packet["unapprovedThresholdsLeftNull"]) == nulls and len(nulls) == 8
    assert all(v is None for v in packet["unapprovedThresholdsLeftNull"].values())
    assert packet["experiment"]["primaryContrast"] == proposal["primaryContrast"]
    assert packet["identities"]["registeredContractSha256"] == CONTRACT.contract_digest()
    assert packet["identities"]["checkMarketResearchProtectedFiles"] == 94


def test_status_is_derived_so_it_cannot_be_forged_to_ready():
    packet = _committed()
    forged = copy.deepcopy(packet)
    forged["status"], forged["sourceBlockers"] = "READY_FOR_OWNER_SCOPE_REVIEW", []
    with pytest.raises(ValueError, match="STATUS_NOT_DERIVED_FROM_PREREQUISITES"):
        P.verify(forged)
    repackaged = copy.deepcopy(forged)
    repackaged["packetSha256"] = P.hashlib.sha256(P.canonical({k: v for k, v in repackaged.items() if k != "packetSha256"}).encode()).hexdigest()
    with pytest.raises(ValueError, match="STATUS_NOT_DERIVED_FROM_PREREQUISITES"):
        P.verify(repackaged)       # even with a recomputed digest the derived status disagrees


@pytest.mark.parametrize("mutate,expected", [
    (lambda p: p["unapprovedThresholdsLeftNull"].__setitem__("economicTolerances", 0.005), "THRESHOLD_NOT_NULL"),
    (lambda p: p.__setitem__("historicalExecutionAuthorized", True), "EXECUTION_FLAG_NOT_FALSE"),
    (lambda p: p["identities"]["codeAndProposalFiles"][0].__setitem__("sha256", "0" * 64), "FILE_CHANGED"),
    (lambda p: p["identities"].__setitem__("registeredContractSha256", "0" * 64), "REGISTERED_CONTRACT_CHANGED"),
    (lambda p: p["identities"]["sourceEvidenceInputs"][0].__setitem__("sha256", "0" * 64), "INPUT_CHANGED"),
])
def test_any_tampered_identity_threshold_or_flag_is_refused(mutate, expected):
    packet = copy.deepcopy(_committed())
    mutate(packet)
    packet["packetSha256"] = P.hashlib.sha256(P.canonical({k: v for k, v in packet.items() if k != "packetSha256"}).encode()).hexdigest()
    with pytest.raises(ValueError, match=expected):
        P.verify(packet)


def test_ready_is_reachable_only_when_every_source_prerequisite_is_verified():
    prereqs = copy.deepcopy(P.prerequisites())
    readings = copy.deepcopy(_committed()["accountingReadings"])
    assert P.readiness_status(prereqs, readings)[0] == "SOURCE_BLOCKED"
    for item in prereqs:
        for dimension in ("rights", "pitVintage", "investability"):
            if item[dimension]["status"] != "NOT_APPLICABLE_SIGNAL_ONLY":
                item[dimension]["status"] = P.VERIFIED
    assert P.readiness_status(prereqs, readings)[0] == "SOURCE_BLOCKED"       # the funded-investor reading is still blocked
    readings["F_FUNDED_INVESTOR"]["status"] = "CONSTRUCTIBLE_AND_VERIFIED"
    assert P.readiness_status(prereqs, readings) == ("READY_FOR_OWNER_SCOPE_REVIEW", [])
    prereqs[3]["rights"]["status"] = "CHECKSUM_MATCH"                           # a checksum is never a licence grant
    status, blockers = P.readiness_status(prereqs, readings)
    assert status == "SOURCE_BLOCKED" and any("rights:CHECKSUM_MATCH" in b for b in blockers)


def _all_verified():
    prereqs = copy.deepcopy(P.prerequisites())
    for item in prereqs:
        for dimension in ("rights", "pitVintage", "investability"):
            if item[dimension]["status"] != "NOT_APPLICABLE_SIGNAL_ONLY":
                item[dimension]["status"] = P.VERIFIED
    readings = copy.deepcopy(_committed()["accountingReadings"])
    readings["F_FUNDED_INVESTOR"]["status"] = "CONSTRUCTIBLE_AND_VERIFIED"
    return prereqs, readings


@pytest.mark.parametrize("index", range(5))
@pytest.mark.parametrize("dimension", ["rights", "pitVintage", "investability"])
def test_one_unverified_dimension_of_one_input_is_enough_to_block(index, dimension):
    prereqs, readings = _all_verified()
    assert P.readiness_status(prereqs, readings)[0] == "READY_FOR_OWNER_SCOPE_REVIEW"
    if prereqs[index][dimension]["status"] == "NOT_APPLICABLE_SIGNAL_ONLY":
        pytest.skip("signal-only input has no investability requirement")
    prereqs[index][dimension]["status"] = "UNKNOWN"
    status, blockers = P.readiness_status(prereqs, readings)
    assert status == "SOURCE_BLOCKED" and blockers == [f"{prereqs[index]['input']}:{dimension}:UNKNOWN"]


def test_no_prerequisite_reads_verified_today_and_each_names_its_smallest_missing_evidence():
    for item in P.prerequisites():
        for dimension in ("rights", "pitVintage", "investability"):
            entry = item[dimension]
            assert entry["status"] != P.VERIFIED and entry["smallestMissingEvidence"]
    assert {i["input"] for i in P.prerequisites()} == {"KS200 signal index", "VIX", "Treasury 10y and 3m", "069500.KS (KODEX 200)", "KRW cash"}


def test_the_scenario_reading_and_the_funded_investor_reading_are_kept_apart():
    readings = _committed()["accountingReadings"]
    scenario, funded = readings["R_REGISTERED_SCENARIO"], readings["F_FUNDED_INVESTOR"]
    assert scenario["status"].startswith("DESCRIPTIVE_SCENARIO") and "ZERO cash" in scenario["basis"] and scenario["admitted"] is False
    assert funded["status"] == "BLOCKED" and any("26 of 46" in r for r in funded["requires"])
    assert any("15.4%" in r and "assumption" in r for r in funded["requires"])
    assert "never substituted" in readings["separation"]


def test_data_read_disclosure_is_explicit_and_the_packet_is_immutable(tmp_path, monkeypatch):
    reads = _committed()["historicalDataReads"]
    assert (reads["strategyPathReturnsComputed"], reads["stateOrSignalValuesComputed"], reads["armReturnsComputed"],
            reads["labelsOrOutcomesRead"]) == (0, 0, 0, 0)
    assert "benchmark" in reads["benchmarkSeriesRead"] and "outcome-exposed" in reads["benchmarkSeriesRead"]
    with pytest.raises(SystemExit, match="PACKET_IS_IMMUTABLE"):
        P.main()


def test_packet_module_runs_no_strategy_replay_and_imports_only_the_registered_contract_and_evidence():
    tree = ast.parse(Path(P.__file__).read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.update(("." * node.level) + (node.module or a.name) for a in node.names)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert imported <= {"__future__", "hashlib", "json", "pathlib", ".market_research_c1c_contract", ".market_research_c1c_source_evidence"}
    source = Path(P.__file__).read_text()
    assert "replay(" not in source and "market_research_c1c import" not in source
