#!/usr/bin/env python3
"""Write research_specs/kr-market-risk-anatomy-v2.json — the v2 EXECUTION spec — and its SHA-256 sidecar.

It inherits (never copies) v1's frozen design by digest, pins v1's sealed artifacts and v1's retained source bytes unchanged (v2 acquires nothing), carries the
frozen v2 source-admissibility rules, and computes every dependency hash from the import closure plus the sealed data inputs. It reads no source value or outcome."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import kr_market_risk_anatomy_v2_execution as E  # noqa: E402
from pipeline.alpha_opportunity_v3_spec import import_closure  # noqa: E402
from pipeline.kr_model_portfolio_execution import digest, file_hash  # noqa: E402

STUDY = E.STUDY
ENTRY_POINTS = ["pipeline/kr_market_risk_anatomy_v2_execution.py", "pipeline/kr_market_risk_sources_v2.py", "pipeline/kr_market_risk_anatomy_execution.py",
                "pipeline/kr_market_risk_anatomy_analysis.py", "pipeline/kr_market_risk_anatomy.py", "pipeline/kr_market_risk_sources.py",
                "pipeline/kr_market_risk_source_parse.py"]


def build():
    v1 = json.loads((ROOT / E.V1_SPEC_PATH).read_text())
    snapshot = v1["sourcePins"]["snapshotDir"]
    sealed = sorted(set(list(E.V1_SEALED_ARTIFACTS) + [
        "docs/" + STUDY + "-design.md", ".github/workflows/" + STUDY + ".yml", "scripts/run_kr_market_risk_anatomy_v2.py", "scripts/build_kr_market_risk_anatomy_v2_spec.py",
        "data/kr-industry-membership-foundation-v1/top120-inputs.json", snapshot + "/audit.json"] + [snapshot + "/" + f for f in v1["sourcePins"]["files"]]
        + [rel for rel in v1["sealedDataInputs"] if rel.startswith("research_specs/kr-model-overlay-portfolio-v1")]))
    spec = {
        "studyId": STUDY, "scientificStatus": E.SCIENTIFIC_STATUS, "phase": "SOURCE_ADMISSIBILITY_CORRECTION_AND_READINESS_HARNESS_ONLY_NO_OUTCOME_COMPUTED",
        "predecessor": {"studyId": E.V1_STUDY, "status": "DATA_BLOCKED_BEFORE_MARKET_RISK_ANATOMY", "blocker": "PRIMARY_REFERENCE_NOT_SELECTED",
                        "rule": "v1 is a permanently valid blocked study; v2 never unblocks, edits, reinterprets or reruns it",
                        "sealedArtifacts": {rel: file_hash(ROOT / rel) for rel in E.V1_SEALED_ARTIFACTS}},
        "inheritedDesign": {"path": E.V1_DESIGN_PATH, "sha256": v1["designSha256"],
                            "unchanged": ["features and orientations", "slow / transition / fast / internals structure", "past-only expanding percentiles", "exact future-path targets",
                                          "underwater-episode algorithm", "SMA200 / Vol63 overlay comparison", "time-series statistics", "revised-history exclusions",
                                          "every v1 coverage, continuity and identity threshold"]},
        "designSha256": v1["designSha256"], "boundary": v1["boundary"], "sourceRules": E.source_rules(),
        "newExternalAcquisition": False, "sourcePins": v1["sourcePins"], "input": v1["input"],
        "inputRole": v1["inputRole"],
        "lifecycle": {"executionLock": "refs/tags/" + STUDY + "-execution-lock plus -<specSha256>, atomic POST /git/refs; any existing ref refuses; failure before the lock spends nothing, after it consumes v2",
                      "markerPath": E.MARKER_PATH, "resultPath": E.RESULT_PATH,
                      "sequence": ["committed authorization (workflow_dispatch on merged main)", "committed exact spec", "frozen immutable source identities", "label-free data-quality gates",
                                   "no prior result", "no prior marker", "no prior study lock", "durable exclusive lock", "first source-value read and outcome computation", "result artifact"]},
        "outcomeAccess": {"counters": ["valueReads", "forwardTargetCalls", "episodeCalls", "analysisCalls", "markerWrites"], "inThisChange": "NONE", "verifyAndReadinessRequireAllZero": True},
        "entryPoints": ENTRY_POINTS, "sealedDataInputs": sealed,
    }
    closure = sorted(set(import_closure(ENTRY_POINTS, ROOT)) | set(sealed))
    spec["dependencyHashes"] = {rel: file_hash(ROOT / rel) for rel in closure}
    return spec


if __name__ == "__main__":
    spec = build()
    path = ROOT / "research_specs" / (STUDY + ".json")
    path.write_text(json.dumps(spec, sort_keys=True, indent=2, ensure_ascii=False) + "\n")
    path.with_suffix(".sha256").write_text(digest(json.loads(path.read_text())) + "\n")
    print(digest(spec))
