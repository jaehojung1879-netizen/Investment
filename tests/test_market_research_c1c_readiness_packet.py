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


def _reseal(packet):
    packet["packetSha256"] = P.hashlib.sha256(P.canonical({k: v for k, v in packet.items() if k != "packetSha256"}).encode()).hexdigest()
    return packet


def test_a_forged_ready_packet_with_a_recomputed_digest_is_refused():
    """The packet must equal a fresh rebuild from code and disk: rewriting its own prerequisites cannot make it READY."""
    forged = copy.deepcopy(_committed())
    for item in forged["sourcePrerequisites"]:
        for dimension in ("rights", "pitVintage", "investability"):
            if item[dimension]["status"] != "NOT_APPLICABLE_SIGNAL_ONLY":
                item[dimension]["status"] = P.VERIFIED
                item[dimension]["evidence"] = [{"path": "docs/invented.json", "sha256": "a" * 64}]
    forged["accountingReadings"]["F_FUNDED_INVESTOR"]["status"] = "CONSTRUCTIBLE_AND_VERIFIED"
    forged["status"], forged["sourceBlockers"] = "READY_FOR_OWNER_SCOPE_REVIEW", []
    with pytest.raises(ValueError, match="FIELD_DIFFERS_FROM_REBUILD:sourcePrerequisites"):
        P.verify(_reseal(forged))


@pytest.mark.parametrize("edit", [
    lambda p: p.__setitem__("unapprovedThresholdsLeftNull", {}),
    lambda p: p["experiment"].__setitem__("buyCost", 0.0),
    lambda p: p["historicalDataReads"].__setitem__("strategyPathReturnsComputed", 7),
    lambda p: p.__setitem__("smallestNextStep", "approve"),
    lambda p: p.__setitem__("injected", True),
])
def test_other_resealed_edits_are_also_refused(edit):
    packet = copy.deepcopy(_committed())
    edit(packet)
    with pytest.raises(ValueError, match="FIELD_DIFFERS_FROM_REBUILD|UNKNOWN_FIELD"):
        P.verify(_reseal(packet))


def test_verified_without_retained_evidence_does_not_count():
    prereqs, readings = _all_verified()
    assert P.readiness_status(prereqs, readings)[0] == "READY_FOR_OWNER_SCOPE_REVIEW"
    prereqs[1]["rights"]["evidence"] = []
    status, blockers = P.readiness_status(prereqs, readings)
    assert status == "SOURCE_BLOCKED" and blockers == ["VIX:rights:VERIFIED_WITHOUT_RETAINED_EVIDENCE"]
    prereqs[1]["rights"]["evidence"] = [{"path": "x", "sha256": "short"}]
    assert P.readiness_status(prereqs, readings)[0] == "SOURCE_BLOCKED"


def test_the_superseded_versions_are_recorded_and_no_longer_present():
    packet = _committed()
    assert packet["supersedes"]["packet"].endswith("-v2") and len(packet["supersedes"]["packetSha256"]) == 64
    assert packet["supersedes"]["earlierVersions"][0]["packet"].endswith("-v1")
    assert "never consumed" in packet["supersedes"]["reason"] and "blocker count is unchanged" in packet["supersedes"]["reason"]
    for old in ("v1", "v2"):
        assert not (P.OUTPUT.parent / f"market-research-c1c-economic-readiness-packet-{old}.json").exists()
    assert packet["studyId"].endswith("-v3")


def test_the_blocker_comparison_is_computed_from_the_lists_and_shows_no_removed_blocker():
    cmp = _committed()["blockerComparison"]
    assert (cmp["before"], cmp["after"]) == (13, 13) and cmp["removed"] == [] and cmp["added"] == []
    assert len(P.PREVIOUS_BLOCKERS) == 13
    changed = {c["blocker"] for c in cmp["statusChanged"]}
    assert changed == {"069500.KS (KODEX 200):pitVintage", "069500.KS (KODEX 200):rights", "KS200 signal index:rights",
                       "Treasury 10y and 3m:rights", "VIX:rights"}
    assert cmp == P.blocker_comparison(_committed()["sourceBlockers"])
    # a removed blocker would have to show up as removed
    assert P.blocker_comparison([b for b in _committed()["sourceBlockers"] if not b.startswith("VIX:rights")])["removed"] == ["VIX:rights"]


def test_a_rights_entry_cannot_become_verified_without_a_recorded_owner_decision():
    prereqs, readings = _all_verified()
    assert P.readiness_status(prereqs, readings)[0] == "READY_FOR_OWNER_SCOPE_REVIEW"
    for index in range(5):
        trial = copy.deepcopy(prereqs)
        del trial[index]["rights"]["ownerDecision"]
        status, blockers = P.readiness_status(trial, readings)
        assert status == "SOURCE_BLOCKED" and blockers == [f"{trial[index]['input']}:rights:VERIFIED_WITHOUT_OWNER_DECISION_RECORD"]
    trial = copy.deepcopy(prereqs)
    trial[3]["rights"]["ownerDecision"] = {"path": "x", "sha256": "short"}
    assert P.readiness_status(trial, readings)[0] == "SOURCE_BLOCKED"


def test_the_restricted_and_third_party_rights_statuses_come_from_the_resolution_record_and_are_not_grants():
    by_input = {i["input"]: i["rights"] for i in _committed()["sourcePrerequisites"]}
    assert by_input["069500.KS (KODEX 200)"]["status"] == "EXPLICITLY_RESTRICTED_WITHOUT_PRIOR_PERMISSION"
    assert by_input["VIX"]["status"].startswith("THIRD_PARTY_OWNER_PERMISSION_REQUIRED")
    assert by_input["KS200 signal index"]["status"].startswith("UPSTREAM_UNRECORDED")
    assert by_input["Treasury 10y and 3m"]["status"].startswith("PARTIAL_PUBLISHER_PUBLIC_DOMAIN")
    assert all(v["status"] != P.VERIFIED for v in by_input.values())
    resolution = _committed()["identities"]["sourceResolutionJson"]
    assert by_input["069500.KS (KODEX 200)"]["evidence"] == [resolution]


def test_disclosure_names_every_file_family_read():
    reads = _committed()["historicalDataReads"]
    assert "bok-policy-rates" in reads["ratesAndCashAmountsRead"] and "issuer dividend" in reads["ratesAndCashAmountsRead"]
    assert "does not cover these modules" in reads["notCoveredByTheProtectedFileCounter"]


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
                item[dimension]["evidence"] = [{"path": "retained/evidence.json", "sha256": "b" * 64}]
                if dimension == "rights":
                    item[dimension]["ownerDecision"] = {"path": "owner/decision.json", "sha256": "d" * 64}
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
                item[dimension]["evidence"] = [{"path": "retained/evidence.json", "sha256": "b" * 64}]
                if dimension == "rights":
                    item[dimension]["ownerDecision"] = {"path": "owner/decision.json", "sha256": "d" * 64}
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
