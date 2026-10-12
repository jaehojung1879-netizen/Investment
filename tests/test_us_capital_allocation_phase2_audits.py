"""The committed Phase 2 audits: internal consistency, agreement with the frozen v1 rule, and the absence of any return access."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import us_capital_allocation_policy as P      # noqa: E402
from pipeline import us_capital_allocation_receipts as R    # noqa: E402

READINESS = ROOT / "docs/us-readiness"
CAP = ROOT / "docs/us-capital-allocation"


def load(path):
    return json.loads(Path(path).read_text())


COVERAGE = load(READINESS / "us-capital-allocation-weekly-coverage-v1.json")["summary"]
DIAG = load(READINESS / "us-capital-allocation-v1-selection-diagnostics-v1.json")
GAPS = load(READINESS / "us-capital-allocation-source-gap-diagnosis-v1.json")
MF = load(READINESS / "us-multifactor-pit-readiness-v1.json")
DIL = load(READINESS / "us-capital-allocation-dilution-evidence-v1.json")
REPORT = load(CAP / "phase2-readiness-v1.json")
PROPOSAL = load(CAP / "us-multifactor-study-proposal-v1.json")

# SHA-256 of the two files as merged by PR #224 (main 82b1aac). An edit to either is a NEW study, not a v1 change.
FROZEN_V1 = {"pipeline/us_capital_allocation_policy.py": "65a5dbe33f0f09bd618ac988e0c690f6c75afb44bf29101efe0579697dc75046",
             "docs/us-capital-allocation/us-capital-allocation-alpha-v1-registration.json":
                 "b82a9b16712605d9d7df643229b998e719f1665f1c0dfdaaa3151750b5ba2d9e"}


def sha(relative):
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


# --------------------------------------------------------------------------- #
# The frozen v1 is untouched
# --------------------------------------------------------------------------- #
def test_the_registered_v1_rule_and_registration_are_byte_frozen():
    assert sha("pipeline/us_capital_allocation_policy.py") == FROZEN_V1["pipeline/us_capital_allocation_policy.py"]
    assert sha("docs/us-capital-allocation/us-capital-allocation-alpha-v1-registration.json") == FROZEN_V1[
        "docs/us-capital-allocation/us-capital-allocation-alpha-v1-registration.json"]
    assert P.design_digest() == "73c347a34bc53f038c9e33ebbc2cb322960f33fc4170919b85d2561a4f073342"
    assert R.REGISTERED_AUTHORIZATION is None


def test_every_diagnostic_describes_the_current_registered_rule():
    assert DIAG["registeredRule"] == {"designDigest": P.design_digest(), "policyVersion": P.POLICY_VERSION}
    assert REPORT["frozenV1"]["designDigest"] == P.design_digest() and REPORT["frozenV1"]["registeredAuthorization"] is None
    assert REPORT["frozenV1"]["scheduledPublication"] == "NOT_STARTED" and REPORT["frozenV1"]["officialWeeklyFilesUnchanged"] is True


# --------------------------------------------------------------------------- #
# Outcome blindness
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("audit", [DIAG, GAPS, MF, DIL])
def test_each_audit_declares_and_shows_no_return_access(audit):
    assert audit["readsReturns"] is False and audit["readsLabels"] is False and audit["fitsModels"] is False


def test_diagnostics_vary_no_threshold_and_publish_no_historical_picks():
    assert DIAG["variesThresholds"] is False and "no alternative threshold" in DIAG["noThresholdSweep"]
    assert "mostFrequent" not in DIAG["decisions"]["distinctNames"]
    text = json.dumps(DIAG)
    assert "wouldHold" not in text and "DRY_RUN_NOT_A_SIGNAL" not in text


# --------------------------------------------------------------------------- #
# Selection diagnostics reproduce the known observations
# --------------------------------------------------------------------------- #
def test_diagnostics_reproduce_the_coverage_audit_and_the_605_five_name_weeks():
    assert DIAG["funnelReproducesCommittedCoverageAudit"] is True and DIAG["weeks"] == COVERAGE["weeklyDates"] == 715
    live = DIAG["decisions"]
    assert live["status"] == {"BLOCKED": 110, "CANDIDATE_PORTFOLIO": 605}
    assert live["participation"]["namesPerWeek"] == {"5": 605} and live["participation"]["weeksWithFullFiveNames"] == 605
    assert DIAG["margins"]["weeksWithFiveSelected"] == 605 and DIAG["margins"]["weeksWithFewerThanFive"] == 0


def test_the_gate_table_is_internally_consistent():
    gates = DIAG["gates"]
    eliminated = sum(v["eliminated"] for k, v in gates.items() if k != "PASSED_EVERY_GATE")
    first = gates[P.GATES[0]]["reached"]
    assert first == eliminated + gates["PASSED_EVERY_GATE"]["reached"]
    for earlier, later in zip(P.GATES, P.GATES[1:]):
        assert gates[later]["reached"] == gates[earlier]["reached"] - gates[earlier]["eliminated"]


def test_the_findings_that_answer_why_five_names_every_week():
    sc, sel = DIAG["scoreConstruction"], DIAG["selectedComposition"]
    assert 0.3 < sc["hurdleVersusMedianGrowth"]["shareOfMeasuredAtOrAboveHurdle"] < 0.6     # a large minority of measured names clear the growth hurdle
    assert sc["passers"]["spearmanScoreVsGrowth"] > 0.7                                      # the score is mostly the growth rate
    assert sel["repurchaseLed"] > 0.9 and sel["dividendLed"] < 0.05                         # the selected increases are buyback-led
    assert DIAG["decisions"]["sectorCap"]["share"] > 0.25                                    # the sector cap binds in a large share of weeks
    assert DIAG["decisions"]["distinctNames"]["everSelected"] < 160                          # a small recurring pool, not a broad one
    assert DIAG["accountingVsExpectedReturn"]["verdict"].startswith("The v1 rule selects on A")


def test_the_current_input_attempt_is_a_blocker_not_a_signal():
    attempt = DIAG["currentInputAttempt"]
    assert attempt["label"] == "CURRENT_INPUT_ATTEMPT_BLOCKED_NOT_A_SIGNAL" and attempt["notAReceipt"] is True
    prices = attempt["inputs"]["prices"]
    assert prices["status"] == "STALE" and prices["ageDays"] > prices["registeredMaxAgeDays"]
    assert attempt["result"]["status"] == "BLOCKED" and attempt["result"]["weights"] is None and attempt["result"]["residualSPYWeight"] == 1.0
    assert attempt["blocker"].startswith("NO_FRESH_US_PRICES")
    assert attempt["inputs"]["fundamentals"]["status"] == "FRESH" and attempt["inputs"]["membership"]["status"] == "AGED_NO_REGISTERED_LIMIT"
    assert "ticker" not in json.dumps(attempt["fundamentalsSideIfPricesWereFresh"])


# --------------------------------------------------------------------------- #
# Source gaps
# --------------------------------------------------------------------------- #
def test_the_source_gap_baseline_is_the_committed_coverage_audit():
    assert GAPS["inputs"]["memberDates"] == COVERAGE["memberDates"]
    assert GAPS["baselineFunnel"] == {k: v for k, v in COVERAGE["funnelCounts"].items() if v}
    assert GAPS["baselineJointMeasuredPct"] == COVERAGE["jointMeasuredOfAllMemberDatesPct"]


def test_the_candidate_view_is_an_upper_bound_that_loses_nothing_and_leaves_v1_alone():
    view = GAPS["candidateView"]
    assert view["frozenV1Untouched"] is True and view["evidence"] == "STORE_EVIDENCE_NOT_CONTEXT_VERIFIED" and view["version"] != "US_SHAREHOLDER_DISTRIBUTION_V1"
    cov = view["coverageUnderView"]
    assert cov["lostMemberDates"] == 0 and cov["jointMeasuredPct"] > GAPS["baselineJointMeasuredPct"]
    assert cov["gainedMemberDates"] == cov["funnel"]["JOINT_MEASURED"] - GAPS["baselineFunnel"]["JOINT_MEASURED"]
    assert "UPPER BOUND" in view["reading"].upper()
    assert all(c in ("CUMULATIVE_CORROBORATED",) for c in [s["verdict"] for s in view["aliasCumulativeSemantics"].values()])


def test_unverifiable_evidence_is_labelled_blocked_rather_than_assumed():
    assert GAPS["blocked"]["secXbrlContext"].startswith("BLOCKED_NETWORK_POLICY")
    assert GAPS["blocked"]["dilutionFeature"].startswith("BLOCKED")
    assert DIL["producesADilutionFeature"] is False and DIL["status"]["periodEndVerifiedDilution"] == "BLOCKED"
    assert DIL["overall"]["periodEndSameBasisNoSplitPairsPct"] < 1.0
    assert GAPS["priceAndIdentity"]["noPricePanelMemberDates"]["currentMembers"] == 0           # every missing panel is a departed member


def test_filing_timestamps_follow_the_strict_visibility_rule():
    stamps = GAPS["timestamps"]
    assert stamps["acceptedDatePct"] > 99 and "strictly before the signal date" in stamps["visibilityRule"]


# --------------------------------------------------------------------------- #
# Multifactor readiness
# --------------------------------------------------------------------------- #
def test_the_multifactor_combinations_only_shrink_as_families_are_added():
    c = MF["combinations"]
    order = ["existingModelInputs", "plusCashFlow", "plusValue", "plusDistribution"]
    assert [c[k]["memberDates"] for k in order] == sorted([c[k]["memberDates"] for k in order], reverse=True)
    assert MF["sampling"]["dates"] == 55 and MF["forwardPricesRead"] is False


def test_the_multifactor_report_does_not_claim_a_fully_pit_matrix():
    assert "NOT a fully point-in-time research matrix" in MF["verdict"]
    snapshot_only = MF["pitClassification"]["SNAPSHOT_ONLY_OR_ABSENT"]
    assert {"marketCap", "forwardPE_consensus", "periodEndSharesAndDilution", "catalysts"} <= set(snapshot_only)
    assert set(MF["pitClassification"]["RECONSTRUCTED"]) == {"asTradedPrice", "value"}


def test_the_distribution_score_is_redundant_only_with_its_own_ingredient():
    flagged = set(MF["featureRedundancy"]["flaggedAtAbsRho70"])
    assert "incrementalDistributionOverOCF~totalCashDistributionChangeYoY" in flagged            # score vs its growth input
    cross = {p for p in flagged if "istribution" in p and not all("istribution" in x for x in p.split("~"))}
    assert cross == set()                                                                       # not redundant with value, quality, momentum or risk


# --------------------------------------------------------------------------- #
# Readiness report and proposal
# --------------------------------------------------------------------------- #
def test_the_readiness_files_are_regenerable_from_the_committed_audits():
    spec = importlib.util.spec_from_file_location("builder", ROOT / "scripts/build_us_capital_allocation_phase2_readiness.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["builder"] = module
    spec.loader.exec_module(module)
    assert module.main(["--check"]) == 0


def test_the_verdict_is_one_of_the_registered_labels_and_nothing_is_authorized():
    assert REPORT["verdict"]["overall"] in REPORT["verdict"]["ordering"]
    assert REPORT["verdict"]["v1UnchangedPilot"].startswith("NOT_STARTABLE")
    assert REPORT["pilotPreflight"]["passed"] == REPORT["pilotPreflight"]["total"] == 12 and REPORT["pilotPreflight"]["writesToProductionHistory"] is False
    assert REPORT["currentInputAttempt"]["result"]["status"] == "BLOCKED"
    assert REPORT["earlyMonitoring"]["statisticalCriteriaChanged"] is False


def test_the_proposal_registers_nothing_and_classifies_past_data_as_exposed():
    assert PROPOSAL["status"] == "PROPOSED_NOT_REGISTERED" and PROPOSAL["registered"] is False and PROPOSAL["authorizes"] == "NOTHING"
    classes = {c["id"]: c["class"] for c in PROPOSAL["pastDataClassification"]}
    assert classes["US_LABELED_2013_2026H1"] == "OUTCOME_EXPOSED" and classes["PROSPECTIVE_AFTER_AUTHORIZATION"] == "UNTOUCHED_BY_CONSTRUCTION"
    assert PROPOSAL["validation"]["confirmatoryEvidence"].startswith("prospective only")
    assert PROPOSAL["zeroToFiveNamePolicy"]["hurdle"].startswith("UNCALIBRATED_HURDLE") and "forbidden" in PROPOSAL["zeroToFiveNamePolicy"]["mechanicalTopFive"]
    assert PROPOSAL["primaryHypothesis"]["horizonSessions"] == 126 and PROPOSAL["primaryHypothesis"]["primaryBenchmark"] == "SPY"
    assert PROPOSAL["productionEffect"] == "NONE" and PROPOSAL["scheduledPublication"] == "NOT_STARTED"


def test_the_power_tables_show_that_breadth_beats_a_five_name_book():
    power = PROPOSAL["validation"]["power"]
    ic = power["minimumDetectableMeanRankIC"]
    assert ic["330 names"]["12 windows"] < ic["50 names"]["12 windows"] and ic["330 names"]["12 windows"] < ic["330 names"]["4 windows"]
    book = power["minimumDetectableAnnualExcessOfAFiveNameBook"]["tracking error 8%"]["6.5 years"]
    assert book > 0.05                                                                           # several percent a year even after 6.5 years


# --------------------------------------------------------------------------- #
# Static guards
# --------------------------------------------------------------------------- #
FORBIDDEN_IMPORT_PARTS = ("outcome", "label", "alpha_opportunity_model", "regional_alpha_model", "replay_v", "historical_replay")
READ_ONLY_CODE = ("pipeline/us_capital_allocation_diagnostics.py", "pipeline/us_capital_allocation_source_views.py", "pipeline/us_multifactor_inputs.py",
                  "scripts/audit_us_capital_allocation_selection_diagnostics.py", "scripts/audit_us_capital_allocation_source_gaps.py",
                  "scripts/audit_us_capital_allocation_dilution_evidence.py", "scripts/audit_us_multifactor_pit_readiness.py")


@pytest.mark.parametrize("relative", READ_ONLY_CODE)
def test_new_audit_code_imports_no_outcome_label_or_model_code(relative):
    tree = ast.parse((ROOT / relative).read_text())
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names += [node.module or ""] + [a.name for a in node.names]
    assert [n for n in names if any(part in n.lower() for part in FORBIDDEN_IMPORT_PARTS)] == []


def test_monitoring_never_runs_the_primary_evaluation():
    source = (ROOT / "pipeline/us_capital_allocation_monitoring.py").read_text()
    assert "evaluate_program(" not in source and "one_sided_bounds(" not in source and "block_indices(" not in source


def test_no_workflow_site_or_sealed_file_is_a_target_of_the_new_code():
    for relative in READ_ONLY_CODE + ("pipeline/us_capital_allocation_monitoring.py", "pipeline/us_capital_allocation_pilot.py",
                                      "scripts/build_us_capital_allocation_phase2_readiness.py"):
        text = (ROOT / relative).read_text()
        assert ".github/workflows" not in text and "index.html" not in text and "app.js" not in text and "styles.css" not in text
