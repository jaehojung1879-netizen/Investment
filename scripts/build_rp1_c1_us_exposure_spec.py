#!/usr/bin/env python3
"""Write the frozen rp1-c1 preregistration, its SHA-256 sidecar and the scientific-content sidecar.

Every scientific section is computed from module constants (and, where inherited, from the sealed KR modules), so `load_spec` can compare them on
every load. The scientific sidecar pins those sections alone: acquiring the US snapshot later re-pins the inputs and the dependency map, and the
builder refuses to write if that would change one scientific byte. `--check` rebuilds in memory and fails on any difference. No value is read."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import rp1_c1_us_exposure as U  # noqa: E402
from pipeline import rp1_c1_us_exposure_spec as SP  # noqa: E402
from pipeline import rp1_c1_us_sources as SRC  # noqa: E402

DOC = "docs/research-program/rp1-c1-us-exposure-ladder-replication.md"
SCRIPTS = ["scripts/build_rp1_c1_us_exposure_spec.py", "scripts/run_rp1_c1_us_exposure.py", "scripts/acquire_rp1_c1_us_sources.py",
           "scripts/acquire_kr_market_risk_sources.py"]


def build(root=ROOT):
    root = Path(root)
    reused = SP.kr_reused_files(root)
    us_files = SP.us_snapshot_files(root)
    sealed = sorted(set(SP.KR_SEALED) | set(reused) | set(us_files) | set(SCRIPTS) | {DOC, "pipeline/kr_market_risk_overlay.py"})
    spec = {
        "studyId": SP.STUDY, "scientificStatus": U.SCIENTIFIC_STATUS, "evidenceStatement": U.EVIDENCE_STATEMENT,
        "phase": "PREREGISTRATION_AND_DATA_FOUNDATION_NO_OUTCOME_COMPUTED",
        "question": "When US market risk rises, does cutting S&P 500 exposure by the sealed KR rules reduce large losses by more than it costs in "
                    "up-market return, re-entry delay, false alarms and trading? Does it raise long-run return, or only cut volatility and drawdown?",
        "role": {"owns": "HOW MUCH US equity index exposure: one equityRiskMultiplier per weekly decision", "independentOf": ["Study A", "Study B"],
                 "doesNotOwn": ["stock or industry selection", "expected-return signals", "Kelly sizing", "any production weight"]},
        "krSealed": {"studyId": "kr-market-risk-model-v1", "decision": "NO_CANDIDATE_NOMINATED_CONTROL_RETAINED",
                     "files": {rel: SP.file_hash(root / rel) for rel in SP.KR_SEALED},
                     "rule": "never rerun, re-thresholded or reinterpreted; C1 imports its rules and reproduces its decision exactly (equivalence audit)"},
        "inputs": {
            "reusedKrFiles": reused, "reusedRule": "the exact bytes the sealed KR spec pins; never re-acquired",
            "usRegistry": SRC.SOURCES,
            "usSnapshot": {"directory": SRC.SNAPSHOT_DIR, "files": us_files, "status": "PINNED" if us_files else "NOT_ACQUIRED",
                           "acquisition": "scripts/acquire_rp1_c1_us_sources.py (network + FRED_API_KEY); see lifecycle.blockers for why no workflow ships"}},
        "model": SP.model_definition(), "portfolio": SP.portfolio_definition(), "evaluation": SP.evaluation_definition(),
        "decision": SP.decision_definition(), "interpretation": SP.interpretation_definition(), "stopRules": SP.stop_rules(),
        "newHypotheses": SP.new_hypotheses(), "preOutcomeRevisions": [],
        "lifecycle": {
            "thisChange": "WP4a-WP4c: data foundation, calendar wrapper, KR equivalence, readiness, frozen spec. No US value read, no lock, no execution.",
            "formalExecution": "WP4d, a separate change: workflow_dispatch on merged main, exact committed spec, owner authorization pinning spec and code "
                               "hashes, readiness READY, equivalence EXACT, no result/marker/lock under the prefix, then an atomic lock ref, a marker, and only "
                               "then the first US value read; one immutable result artifact and an exact-byte Draft seal PR (the kr-market-risk-model-v1 pattern)",
            "executionLock": "refs/tags/" + SP.STUDY + "-execution-lock plus -<specSha256>; any ref under the prefix refuses",
            "resultPath": SP.RESULT_PATH, "markerPath": SP.MARKER_PATH,
            "blockers": [
                {"id": "WORKFLOW_CENSUS_FROZEN", "status": "OWNER_DECISION_REQUIRED",
                 "fact": "every workflow inventory layer (docs/workflow-inventory*.md) and both census tests (tests/test_workflow_inventory.py, "
                         "tests/test_kr_alpha_atlas_price_repair_workflow_inventory.py) are hash-pinned by sealed Phase C specs. Any new .yml or .yaml file "
                         "fails a pinned census test, and editing a pinned test fails the sealed Phase C amendment check. Neither the source workflow nor the "
                         "WP4d execution workflow can be added without a versioned decision on that census.",
                 "options": ["owner runs the acquisition script outside Actions and commits the bytes (provenance: operator machine, recorded in audit.json)",
                             "a versioned census layer for post-Phase-C workflows, decided and recorded by the owner, before WP4d"]},
                {"id": "US_SOURCES_UNREACHABLE_FROM_AUTHORING_SANDBOX", "status": "ENVIRONMENT",
                 "fact": "query1.finance.yahoo.com and api.stlouisfed.org answer CONNECT 403 here and no FRED_API_KEY is set; nothing was acquired"}]},
        "outcomeAccess": {"inThisChange": "NONE_FOR_US", "krSealedReproduction": "the equivalence audit reads the sealed KR study's retained bytes and "
                                                                                 "compares with its sealed result; it opens no new outcome",
                          "verifyAndReadinessRequire": "usValueReads == stateComputationsOnValues == replayCallsOnValues == 0"},
        "boundary": {"isValidation": False, "isProspective": False, "isProductionModel": False, "blocksStudyA": False, "blocksStudyB": False,
                     "mayTuneAThresholdWindowOrMultiplier": False, "mayAddACandidateAfterOutcomes": False, "mayChangeTheDecisionRuleAfterOutcomes": False,
                     "mayRerunTheKrStudy": False, "changeAfterOutcomeAccessRequires": "a NEW study identity"},
        "entryPoints": SP.ENTRY_POINTS, "sealedDataInputs": sealed,
    }
    closure = sorted(set(SP.import_closure(SP.ENTRY_POINTS, root)) | set(sealed))
    spec["dependencyHashes"] = {rel: SP.file_hash(root / rel) for rel in closure}
    return spec


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    spec = build()
    path = ROOT / SP.SPEC_PATH
    scientific = ROOT / SP.SCIENTIFIC_SIDECAR
    if args.check:
        same = path.exists() and json.loads(path.read_text()) == spec and scientific.read_text().strip() == SP.scientific_digest(spec)
        print("SPEC_REPRODUCED" if same else "SPEC_DIFFERS")
        return 0 if same else 1
    if scientific.exists() and scientific.read_text().strip() != SP.scientific_digest(spec):
        raise SystemExit("REFUSED: the scientific content would change; that needs a new study identity or a recorded pre-outcome revision")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec, sort_keys=True, indent=2, ensure_ascii=False) + "\n")
    path.with_suffix(".sha256").write_text(SP.digest(json.loads(path.read_text())) + "\n")
    scientific.write_text(SP.scientific_digest(spec) + "\n")
    print(SP.digest(spec), SP.scientific_digest(spec))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
