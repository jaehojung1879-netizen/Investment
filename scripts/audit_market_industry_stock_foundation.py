"""Metadata/identity audit only: no return runner, price inputs, model, or execution mode."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.industry_foundation import VERSION  # noqa: E402

SPEC = "research_specs/market-industry-stock-data-foundation-v1.json"
ALLOWED_PREFIXES = ("pipeline/", "scripts/", "research_specs/", "docs/", "tests/", ".github/workflows/")
FORBIDDEN_OUTPUT_KEYS = {"return", "returns", "outcomes", "prediction", "weights", "positions", "alpha", "cagr", "sharpe"}


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(root=ROOT):
    """Hash ONLY the explicitly enumerated source/code contracts. Never open results."""
    root = Path(root)
    path = root / SPEC
    expected = path.with_suffix(".sha256").read_text().strip()
    if _hash(path) != expected:
        raise ValueError("FOUNDATION_SPEC_IDENTITY_CHANGED")
    spec = json.loads(path.read_text())
    if spec["studyId"] != VERSION or spec["execution"] != {
        "historicalReturnsAllowed": False, "modelsAllowed": False,
        "portfolioAllowed": False, "taxonomyOutcomeSelectionAllowed": False,
        "returnPrimitiveScope": "SYNTHETIC_ONLY", "workflowMode": "METADATA_AUDIT_AND_MANUAL_SOURCE_SMOKE_ONLY"
    }:
        raise ValueError("FOUNDATION_EXECUTION_BOUNDARY_CHANGED")
    for rel, wanted in spec["dependencyHashes"].items():
        if ((rel != "config.json" and not rel.startswith(ALLOWED_PREFIXES)) or ".." in Path(rel).parts
                or rel.startswith("docs/results/") or "result" in Path(rel).name):
            raise ValueError("OUTCOME_PATH_NOT_ALLOWED_IN_AUDIT")
        if _hash(root / rel) != wanted:
            raise ValueError("FOUNDATION_DEPENDENCY_CHANGED: " + rel)
    return {"studyId": VERSION, "mainShaUsed": spec["mainShaUsed"], "specSha256": expected,
            "auditType": "REPOSITORY_CONTRACT_AND_SOURCE_READINESS; not a historical row audit",
            "status": "DATA_FOUNDATION_REQUIRED", "primitiveStatus": "READY_SYNTHETIC_ONLY",
            "historicalMembershipRowsVerified": 0, "historicalClassificationCoverageFraction": None,
            "historicalIndustryObservationCount": None,
            "sourceMatrix": spec["sourceMatrix"], "featureMatrix": spec["featureMatrix"],
            "marketContextFoundation": spec["marketContextFoundation"],
            "verifiedDependencies": sorted(spec["dependencyHashes"]),
            "historicalOutcomeComputed": False, "modelFitPerformed": False,
            "taxonomyChosenUsingOutcomes": False, "priorStudyRerun": False}


def assert_audit_only(value):
    if isinstance(value, dict):
        if FORBIDDEN_OUTPUT_KEYS & {str(k).lower() for k in value}:
            raise ValueError("FORBIDDEN_FOUNDATION_AUDIT_OUTPUT")
        for child in value.values():
            assert_audit_only(child)
    elif isinstance(value, list):
        for child in value:
            assert_audit_only(child)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # Refuse overwriting ANY existing file; the workflow writes a fresh temp path.
    # In particular this audit can never overwrite a sealed historical result.
    result = audit()
    assert_audit_only(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    print("DATA_FOUNDATION_REQUIRED; metadata audit only; zero outcome/fit calls")


if __name__ == "__main__":
    main()
