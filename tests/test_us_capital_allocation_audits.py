"""The committed outcome-blind audits: internal consistency, agreement with the code, and the absence of any return access."""
from __future__ import annotations

import ast
import gzip
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import us_capital_allocation_policy as P      # noqa: E402
from pipeline import us_capital_allocation_receipts as R    # noqa: E402

READINESS = ROOT / "docs/us-readiness"
COVERAGE = json.loads((READINESS / "us-capital-allocation-weekly-coverage-v1.json").read_text())
DEFINITIONS = json.loads((READINESS / "us-capital-allocation-definition-audit-v1.json").read_text())
OVERLAP = json.loads((READINESS / "us-capital-allocation-feature-overlap-v1.json").read_text())
AUDIT_220 = json.loads((READINESS / "us-shareholder-distribution-feature-audit.json").read_text())
REGISTRATION = ROOT / "docs/us-capital-allocation/us-capital-allocation-alpha-v1-registration.json"
PROTECTED = ROOT / "docs/us-capital-allocation/protected-official-files.json"
NEW_CODE = ("pipeline/us_capital_allocation_policy.py", "pipeline/us_capital_allocation_receipts.py", "pipeline/us_capital_allocation_evaluation.py",
            "pipeline/us_capital_allocation_coverage.py", "pipeline/us_capital_allocation_weekly.py",
            "scripts/audit_us_capital_allocation_coverage.py", "scripts/audit_us_capital_allocation_definitions.py",
            "scripts/audit_us_capital_allocation_overlap.py", "scripts/build_us_capital_allocation_registration.py")
SUMMARY = COVERAGE["summary"]


def test_weekly_coverage_is_per_weekly_date_and_not_per_filing_event():
    assert SUMMARY["weeklyDates"] == 715 and SUMMARY["memberDates"] == 359526
    assert SUMMARY["firstDate"] == "2013-01-04" and SUMMARY["lastDate"] == "2026-09-11"
    assert sum(SUMMARY["funnelCounts"].values()) == SUMMARY["memberDates"]
    assert sum(v["memberDates"] for v in SUMMARY["byYear"].values()) == SUMMARY["memberDates"]
    assert sum(v["memberDates"] for v in SUMMARY["bySector"].values()) == SUMMARY["memberDates"]
    assert SUMMARY["filingEligibleMemberDates"] < SUMMARY["priceEligibleMemberDates"] < SUMMARY["memberDates"]


def test_every_member_date_is_classified_into_exactly_one_named_stage():
    assert set(SUMMARY["funnelCounts"]) == {"IDENTITY_AMBIGUOUS", "NO_PRICE_PANEL", "PRICE_HISTORY_INSUFFICIENT", "PRICE_STALE", "NO_FUNDAMENTAL_RECORD",
                                            "NO_VISIBLE_FILING", "REPORT_STALE_OVER_180_DAYS", "FEATURES_NOT_MEASURED", "JOINT_MEASURED"}
    assert SUMMARY["funnelCounts"]["JOINT_MEASURED"] == pytest.approx(SUMMARY["jointMeasuredOfAllMemberDatesPct"] * SUMMARY["memberDates"] / 100, abs=1)


def test_missing_zero_ambiguous_and_insufficient_history_are_kept_apart():
    states = {s for family in SUMMARY["featureStatesByFamily"].values() for feature in family.values() for s in feature}
    assert {"VALID", "REPORTED_ZERO", "NOT_REPORTED", "AMBIGUOUS_ACCOUNTING", "INSUFFICIENT_HISTORY", "BLOCKED"} <= states
    assert SUMMARY["featureStatesByFamily"]["dilution"]["sharesOutstandingChangeYoY"] == {"BLOCKED": sum(
        SUMMARY["featureStatesByFamily"]["dilution"]["sharesOutstandingChangeYoY"].values())}


def test_coverage_uses_the_same_source_evidence_as_the_committed_220_audit():
    assert COVERAGE["inputs"]["matchesCommitted220Evidence"] is True
    assert COVERAGE["inputs"]["cumulativeEvidence"] == AUDIT_220["sourceMetadata"]["cumulativeEvidence"]
    assert COVERAGE["featureVersion"] == P.U.FEATURE_VERSION


def test_selection_feasibility_describes_the_current_registered_rule():
    feasibility = SUMMARY["selectionFeasibility"]
    assert feasibility["designDigest"] == P.design_digest() and feasibility["rule"] == P.POLICY_VERSION
    assert sum(feasibility["weeklyDecisions"].values()) == SUMMARY["weeklyDates"]
    assert sum(feasibility["namesSelectedPerWeek"].values()) == SUMMARY["weeklyDates"]
    assert feasibility["weeklyDecisions"]["BLOCKED"] == feasibility["namesSelectedPerWeek"]["0"]
    assert set(feasibility["namesSelectedPerWeek"]) <= {str(n) for n in range(P.MAX_NAMES + 1)}


def test_blocked_weeks_are_exactly_the_weeks_below_the_measured_name_floor():
    blocked = SUMMARY["selectionFeasibility"]["weeklyDecisions"]["BLOCKED"]
    assert blocked == sum(v["weeksBelowFloor"] for v in SUMMARY["weeklyMeasuredNamesByYear"].values())


def test_audits_declare_that_they_read_no_return_or_label():
    for audit in (COVERAGE, DEFINITIONS, OVERLAP):
        assert audit["readsReturns"] is False and audit["readsLabels"] is False and audit["fitsModels"] is False
    assert COVERAGE["historicalResearchExecuted"] is False and COVERAGE["writesSignalHistory"] is False
    assert OVERLAP["forwardPricesRead"] is False and DEFINITIONS["readsPrices"] is False


def test_definition_audit_documents_the_blocked_dilution_source_and_the_amendment_chronology():
    assert DEFINITIONS["dilution"]["status"] == "BLOCKED" and DEFINITIONS["dilution"]["periodEndShareCountFilings"]["pct"] < 5
    assert P.DILUTION_STATUS == "UNVERIFIED_SOURCE_BLOCKED"
    chronology = DEFINITIONS["amendmentChronology"]
    assert chronology["failures"] == [] and chronology["slotsChecked"] == chronology["slotsWithMoreThanOneFiling"] > 0
    assert DEFINITIONS["proposesNoDefinitionChange"] is True


def test_no_existing_feature_is_redundant_with_the_candidate_features():
    assert OVERLAP["flaggedPairs"] == [] and OVERLAP["redundancyThreshold"] == 0.70
    assert OVERLAP["sampling"]["datesSampled"] >= 30


def test_registration_file_equals_the_code():
    stored = json.loads(REGISTRATION.read_text())
    assert stored == json.loads(json.dumps(P.registration(), sort_keys=True, allow_nan=False))
    assert stored["authorization"] is None and stored["status"] == "REGISTERED_PENDING_OWNER_APPROVAL"
    assert R.REGISTERED_AUTHORIZATION is None
    assert stored["scheduledPublication"] == "NOT_STARTED" and stored["promotionEligible"] is False and stored["productionEffect"] == "NONE"


def test_official_weekly_decision_files_are_unchanged():
    record = json.loads(PROTECTED.read_text())
    assert record["docs/weekly-decision"], "no protected files recorded"
    for name, digest in record["docs/weekly-decision"].items():
        assert hashlib.sha256((ROOT / "docs/weekly-decision" / name).read_bytes()).hexdigest() == digest, name


def test_the_funnel_by_date_artifact_matches_the_summary():
    with gzip.open(ROOT / "data/research/us-capital-allocation-alpha-v1/weekly-funnel-by-date.csv.gz", "rt") as stream:
        lines = stream.read().strip().splitlines()
    assert len(lines) - 1 == SUMMARY["weeklyDates"]
    header = lines[0].split(",")
    members = sum(int(line.split(",")[header.index("members")]) for line in lines[1:])
    assert members == SUMMARY["memberDates"]


FORBIDDEN_IMPORT_PARTS = ("outcome", "label", "alpha_opportunity_model", "regional_alpha_model", "replay_v", "historical_replay")


@pytest.mark.parametrize("relative", NEW_CODE)
def test_new_code_imports_no_historical_outcome_or_model_code(relative):
    tree = ast.parse((ROOT / relative).read_text())
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names += [(node.module or "")] + [a.name for a in node.names]
    offending = [n for n in names if any(part in n.lower() for part in FORBIDDEN_IMPORT_PARTS)]
    allowed_overlap = relative.endswith("audit_us_capital_allocation_overlap.py")      # reads price FEATURES, refuses forward prices
    assert not offending or allowed_overlap, offending


def test_no_workflow_file_or_pinned_surface_was_added_by_this_program():
    for relative in NEW_CODE:
        assert not relative.startswith(".github/")
    assert not list((ROOT / ".github/workflows").glob("*capital*"))
