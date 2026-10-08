"""kr-alpha-discovery-tournament-v1 forensic closure: the committed audit bytes, what they say, and that nothing sealed moved."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "docs/results/kr-alpha-discovery-tournament-v1-postoutcome-integrity-audit-run37757869994"
SEALED_RESULT_SHA = "4a117ed23d30f9d716c87dbd987e1b80798484b0ab3558638379bf65cf9ccc5d"
INCOMPLETE = {"DECISION_FOCUSED_CHALLENGER:BASE": ("000030.KS", "2019-02-13"), "PRIMARY_ROBUST_KELLY:BASE": ("079440.KS", "2020-02-14"),
              "PRIMARY_ROBUST_KELLY:EXECUTION_DELAY_ONE_SESSION": ("079440.KS", "2020-02-14"),
              "PRIMARY_ROBUST_KELLY:LIQUIDITY_HAIRCUT_HALF_ADV": ("079440.KS", "2020-02-14")}


def _json(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def test_committed_files_are_the_exact_bytes_the_run_printed():
    record = _json(PREFIX + "-provenance.json")
    assert record["sourceAuditRun"]["runId"] == 37757869994 and record["sourceAuditRun"]["conclusion"] == "success"
    assert record["sourceAuditRun"]["headSha"] == record["sourceAuditRun"]["auditRef"] == "685b33dea77a032a56f6780d6213c396802da367"
    assert record["sourceArtifact"]["zipSha256"] == "1fed282b676509c84a34bc3caaf65e350567a5bc70f4ab0725336901da3bceac"
    assert record["formalTournamentRerun"] is False and record["lockTouched"] is False and record["sealedResultTouched"] is False
    for entry in record["files"].values():
        data = (ROOT / entry["committedAs"]).read_bytes()
        assert len(data) == entry["bytes"] and hashlib.sha256(data).hexdigest() == entry["sha256"], entry["committedAs"]


def test_the_audit_reproduced_the_sealed_result_in_the_formal_python_environment():
    full = _json(PREFIX + "-full.json")
    parity = _json(PREFIX + "-environment-parity.json")
    assert full["reproduction"]["status"] == "RECONSTRUCTION_REPRODUCES_THE_SEALED_RESULT" and full["reproduction"]["firstDivergence"] is None
    assert full["status"] == "POST_OUTCOME_FORENSIC_DIAGNOSTIC_NOT_CONFIRMATORY"
    assert parity["pythonEnvironment"]["classification"] == "PYTHON_ENVIRONMENT_EXACT_MATCH" and parity["ok"] is True
    assert parity["host"]["classification"] == "HOST_HARDWARE_IMAGE_DIFFERS" and parity["host"]["blocksTheAudit"] is False
    assert full["formal"]["resultSha256"] == SEALED_RESULT_SHA == hashlib.sha256(
        (ROOT / "docs/results/kr-alpha-discovery-tournament-v1-result.json").read_bytes()).hexdigest()
    assert full["inputIdentityAfterSha256"] == full["formal"]["inputIdentitySha256"]


def test_every_incomplete_path_fails_on_unresolved_terminal_economics_of_a_held_name():
    full = _json(PREFIX + "-full.json")
    sealed = _json("docs/results/kr-alpha-discovery-tournament-v1-result.json")
    assert sorted(full["formal"]["incompletePaths"]) == sorted(p for p, ok in sealed["complete"].items() if not ok) == sorted(INCOMPLETE)
    for failure in full["firstFailures"]:
        ticker, session = INCOMPLETE[failure["path"]]
        assert (failure["ticker"], failure["firstFailingSession"]) == (ticker, session)
        assert failure["mechanism"] == "RAW_PRICE_ABSENT_AFTER_LAST_TRADING_DATE_HELD_THROUGH_PRE_TERMINAL_TRADING_SUSPENSION"
        assert failure["heldWeightImmediatelyBeforeFailure"] > 0 and failure["terminationInformationAvailableToTheFrozenProcess"] is False
        completeness = failure["terminalFoundation"]["reconstructionCompleteness"]
        assert completeness["terminalConsiderationResolved"] == completeness["terminalActionChainResolved"] == "BLOCKED"
    assert all(entry["costX2EverEntered"] is False for entry in full["costX2"])


def test_the_scan_replicated_byte_for_byte_and_the_formal_decision_is_unchanged():
    record = _json(PREFIX + "-provenance.json")
    assert record["files"]["audit/model-free-scan.json"]["sha256"] == hashlib.sha256(
        (ROOT / "docs/results/kr-alpha-discovery-tournament-v1-postoutcome-integrity-audit-run37688582489-model-free-scan.json").read_bytes()).hexdigest()
    sealed = _json("docs/results/kr-alpha-discovery-tournament-v1-result.json")
    assert sealed["verdict"]["verdict"] == "BLOCKED_BY_DATA_INTEGRITY" and sealed["verdict"]["code"] == "E" and sealed["promotionEligible"] is False
    provenance = _json("docs/results/kr-alpha-discovery-tournament-v1-seal-provenance.json")
    for rel, meta in provenance["committedFiles"].items():
        assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == meta["sha256"], rel
