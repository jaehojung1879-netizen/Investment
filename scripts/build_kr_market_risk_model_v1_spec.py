#!/usr/bin/env python3
"""Write research_specs/kr-market-risk-model-v1.json — the frozen PREREGISTRATION — and its SHA-256 sidecar.

Every scientific section (model, portfolio, evaluation, decision) is computed from the module constants, so `load_spec` can compare the two on every
load. It pins the sealed kr-market-risk-anatomy-v2 artifacts, the exact retained source bytes, the receipt schema and the import closure. It reads no
source value and no outcome."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import kr_market_risk_model as K  # noqa: E402
from pipeline import kr_market_risk_model_execution as E  # noqa: E402

STUDY = E.STUDY
ENTRY_POINTS = ["pipeline/kr_market_risk_model_execution.py", "pipeline/kr_market_risk_model.py", "pipeline/kr_market_risk_model_receipts.py",
                "pipeline/kr_market_risk_model_seal.py"]


def build():
    inputs = {E.SNAPSHOT_DIR + "/" + sid + "/normalized.csv": E.file_hash(ROOT / E.SNAPSHOT_DIR / sid / "normalized.csv") for sid in E.SOURCES.values()}
    inputs[E.SNAPSHOT_DIR + "/audit.json"] = E.file_hash(ROOT / E.SNAPSHOT_DIR / "audit.json")
    sealed = sorted(set(list(E.PREDECESSOR_SEALED) + list(inputs) + [
        "docs/" + STUDY + "-design.md", ".github/workflows/" + STUDY + ".yml", "scripts/run_kr_market_risk_model_v1.py",
        "scripts/seal_kr_market_risk_model_v1.py", "scripts/build_kr_market_risk_model_v1_spec.py", E.RECEIPT_SCHEMA_PATH,
        "pipeline/kr_market_risk_overlay.py"]))
    spec = {
        "studyId": STUDY, "modelVersion": K.MODEL_VERSION, "scientificStatus": E.SCIENTIFIC_STATUS, "developmentStatement": K.DEVELOPMENT_STATEMENT,
        "phase": "PREREGISTRATION_AND_HARNESS_ONLY_NO_OUTCOME_COMPUTED",
        "question": "When KR market risk rises, how should KR equity exposure be reduced so that large losses fall meaningfully WITHOUT paying an excessive cost "
                    "through false alarms, missed rebounds, time de-risked, turnover or transaction costs?",
        "role": {"owns": "HOW MUCH KR equity risk: one equityRiskMultiplier per decision date",
                 "doesNotOwn": ["industry ranking", "stock ranking", "security selection", "valuation signals", "stock or industry excess-return signals",
                                "0-5 name portfolio selection", "Kelly sizing", "Market x Industry x Stock integration"]},
        "predecessor": {"studyId": E.PREDECESSOR, "status": "SEALED_EXPLORATORY_RESULT (PR #198)",
                        "rule": "the anatomy is closed: never rerun, altered, re-thresholded or read as prospective validation; it motivated this architecture and is "
                                "the reason every historical number here is development evidence",
                        "sealedArtifacts": {rel: E.file_hash(ROOT / rel) for rel in E.PREDECESSOR_SEALED}},
        "inherited": E.INHERITED,
        "inputs": {"sources": E.SOURCES, "files": inputs, "newExternalAcquisition": False,
                   "rule": "the exact immutable bytes kr-market-risk-anatomy-v1 retained (and v2 read); nothing is re-acquired; no vendor is contacted"},
        "model": E.model_definition(), "portfolio": E.portfolio_definition(), "evaluation": E.evaluation_definition(), "decision": E.decision_definition(),
        "prospective": {"receiptSchemaPath": E.RECEIPT_SCHEMA_PATH, "receiptSchemaSha256": E.file_hash(ROOT / E.RECEIPT_SCHEMA_PATH),
                        "module": "pipeline/kr_market_risk_model_receipts.py", "evidenceClass": "PROSPECTIVE_PAPER", "horizons": [21, 63, 126],
                        "rules": ["one immutable receipt per future decision date, appended before the execution-session close",
                                  "every candidate's multiplier is recorded, plus the final multiplier of the sealed nomination (C0 when none)",
                                  "append-only JSON Lines; a duplicate key, an out-of-order date, a changed spec or an altered earlier row refuses the append",
                                  "a receipt is evaluated only after its horizon has matured; no historical receipt is rewritten",
                                  "historical development results and prospective receipts are separate evidence classes and are never pooled"],
                        "status": "DESIGNED_NOT_RUNNING: no receipt is written and no schedule exists in this change"},
        "lifecycle": {
            "sequence": ["workflow_dispatch on merged main", "committed exact spec and sidecar", "every pin (predecessor, inputs, closure) verified",
                         "outcome-free readiness gates (dates only)", "no committed result, marker or manifest", "no execution lock under the study prefix",
                         "durable exclusive lock (atomic POST /git/refs)", "execution marker", "first source-value read", "outcomes", "immutable result artifact",
                         "automatic seal: verify run, artifact digest, file list, manifest, marker, spec and lock refs", "copy exact bytes plus provenance",
                         "ONE Draft pull request", "a human reviews and merges"],
            "executionLock": "refs/tags/" + STUDY + "-execution-lock plus -<specSha256>; any existing ref under the prefix refuses; never moved or deleted",
            "failureBeforeLock": "spends nothing", "failureAfterLock": "consumes the study permanently; never retried; the attempt artifact is preserved under -attempt-<runId>",
            "resultPath": E.RESULT_PATH, "markerPath": E.MARKER_PATH, "manifestPath": E.MANIFEST_PATH,
            "seal": {"module": "pipeline/kr_market_risk_model_seal.py", "script": "scripts/seal_kr_market_risk_model_v1.py",
                     "never": ["rerun outcomes", "change or reformat a result byte", "tune anything", "reinterpret the nomination", "merge", "mark ready for review",
                               "seal an attempt artifact"]}},
        "outcomeAccess": {"counters": list(E.COUNTER_NAMES), "inThisChange": "NONE", "verifyAndReadinessRequireAllZero": True},
        "boundary": {"isValidation": False, "isProspective": False, "isProductionModel": False, "isStockSelection": False, "isIndustrySelection": False,
                     "usesMachineLearning": False, "mayTuneAThresholdWindowOrMultiplier": False, "mayAddACandidateAfterOutcomes": False,
                     "mayChangeTheDecisionRuleAfterOutcomes": False, "mayRerunTheAnatomy": False, "outcomeExecutionInThisChange": False,
                     "changeAfterOutcomeAccessRequires": "a NEW study identity"},
        "entryPoints": ENTRY_POINTS, "sealedDataInputs": sealed,
    }
    closure = sorted(set(E.import_closure(ENTRY_POINTS, ROOT)) | set(sealed))
    spec["dependencyHashes"] = {rel: E.file_hash(ROOT / rel) for rel in closure}
    return spec


if __name__ == "__main__":
    spec = build()
    path = ROOT / E.SPEC_PATH
    path.write_text(json.dumps(spec, sort_keys=True, indent=2, ensure_ascii=False) + "\n")
    path.with_suffix(".sha256").write_text(E.digest(json.loads(path.read_text())) + "\n")
    print(E.digest(spec))
