#!/usr/bin/env python3
"""Write research_specs/kr-integrated-alpha-portfolio-v1.json — the frozen PREREGISTRATION — and its SHA-256 sidecar.

Every scientific section is computed from the module constants, so `load_spec` can compare the two on every load. It pins every sealed prior study
byte-for-byte, the market source bytes, the cash-yield file, the receipt schema and the import closure. It reads no source value and no outcome."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import kr_integrated_alpha_portfolio as M  # noqa: E402
from pipeline import kr_integrated_alpha_portfolio_execution as E  # noqa: E402

STUDY = E.STUDY
ENTRY_POINTS = ["pipeline/kr_integrated_alpha_portfolio_execution.py", "pipeline/kr_integrated_alpha_portfolio.py", "pipeline/kr_integrated_alpha_portfolio_replay.py",
                "pipeline/kr_integrated_alpha_portfolio_receipts.py", "pipeline/kr_integrated_alpha_portfolio_seal.py"]
TESTS = ["test_kr_integrated_alpha_portfolio_v1.py", "test_kr_integrated_alpha_portfolio_v1_replay.py", "test_kr_integrated_alpha_portfolio_v1_lifecycle.py",
         "test_kr_integrated_alpha_portfolio_v1_result_seal.py"]


def prior_files():
    """Exact files of every sealed prior study: its specs, schemas and sidecars, its committed results and its design documents."""
    found = set()
    for study in E.PRIOR_STUDIES:
        found.update(str(p.relative_to(ROOT)) for p in (ROOT / "research_specs").glob(study + "*") if p.is_file())
        found.update(str(p.relative_to(ROOT)) for p in (ROOT / "docs/results").glob(study + "-*") if p.is_file())
        found.update(str(p.relative_to(ROOT)) for p in (ROOT / "docs").glob(study + "-*.md") if p.is_file())
        found.update(str(p.relative_to(ROOT)) for p in (ROOT / "research_specs" / study).rglob("*") if p.is_file()) if (ROOT / "research_specs" / study).is_dir() else None
    return sorted(found)


def build():
    stock = json.loads((ROOT / E.STOCK_SPEC).read_text())
    market_spec = json.loads((ROOT / E.MARKET_SPEC).read_text())
    priors = {rel: E.file_hash(ROOT / rel) for rel in prior_files()}
    sources = {rel: E.file_hash(ROOT / rel) for rel in market_spec["inputs"]["files"]}
    sealed = sorted(set(list(priors) + list(sources) + list(stock["membership"]["files"]) + [
        M.CASH_YIELD["path"], "docs/" + STUDY + "-design.md", ".github/workflows/" + STUDY + ".yml", "scripts/run_kr_integrated_alpha_portfolio_v1.py",
        "scripts/seal_kr_integrated_alpha_portfolio_v1.py", "scripts/build_kr_integrated_alpha_portfolio_v1_spec.py", E.RECEIPT_SCHEMA_PATH,
        "data/kr-industry-membership-foundation-v1/identity-inventory.json", "data/kr-industry-membership-foundation-v1/identity-provenance.json",
        "data/kr-industry-membership-foundation-v1/top120-inputs.json"]))
    spec = {
        "studyId": STUDY, "scientificStatus": E.SCIENTIFIC_STATUS, "developmentStatement": M.DEVELOPMENT_STATEMENT,
        "phase": "PREREGISTRATION_AND_HARNESS_ONLY_NO_OUTCOME_COMPUTED",
        "question": "Which fixed combination of the sealed Market, Industry and Stock components is worth recording prospectively: S, S+M0, S+M1, I+S, I+S+M0 or I+S+M1?",
        "benchmark": M.BENCHMARK, "returnBasis": M.RETURN_BASIS, "developmentCutoff": M.DEVELOPMENT_CUTOFF, "featureStart": M.FEATURE_START,
        "evaluationStart": M.EVALUATION_START, "strideKrSessions": M.STRIDE_KR_SESSIONS,
        "priors": {"studies": list(E.PRIOR_STUDIES), "neverRerun": list(E.PRIOR_NEVER_RERUN), "sealedArtifacts": priors,
                   "rule": "every prior sealed study is pinned byte-for-byte; none is rerun, re-thresholded, reinterpreted or altered; the component studies motivated this "
                           "architecture and are the reason every historical number here is development evidence"},
        "inputs": {"marketSourceFiles": sources, "cashYieldFileSha256": E.file_hash(ROOT / M.CASH_YIELD["path"]), "newExternalAcquisition": False,
                   "rule": "the exact immutable bytes the sealed studies read; the preserved raw-input artifact is pinned by name, run, id, archive digest and identity"},
        "input": stock["input"], "membership": stock["membership"], "readiness": {"minimumNamesWithMarketCapPerDate": 3},
        "stockLayer": E.stock_layer_definition(), "industryLayer": E.industry_layer_definition(), "marketLayer": E.market_layer_definition(),
        "portfolio": E.portfolio_definition(), "architectures": E.architecture_definition(), "metrics": E.metrics_definition(), "decision": E.decision_definition(),
        "cashYield": M.CASH_YIELD, "governance": E.governance_definition(), "preOutcomeRevisions": E.pre_outcome_revisions(),
        "prospective": {"receiptSchemaPath": E.RECEIPT_SCHEMA_PATH, "receiptSchemaSha256": E.file_hash(ROOT / E.RECEIPT_SCHEMA_PATH),
                        "module": "pipeline/kr_integrated_alpha_portfolio_receipts.py", "evidenceClass": "PROSPECTIVE_PAPER", "horizons": [21, 63, 126],
                        "rules": ["one immutable receipt per future decision date, appended before the execution-session close",
                                  "every input identity, the industry membership used, the registered feature values, the three scores, the eligible names, both underlying books, "
                                  "the C0 and C1 states and multipliers and all six target portfolios are recorded; no future outcome exists at creation",
                                  "the six targets are derived as underlying x multiplier, never accepted from the caller",
                                  "append-only JSON Lines; a duplicate key, an out-of-order date, a changed spec or an altered earlier row refuses the append",
                                  "a receipt is evaluated only after its horizon has matured; no historical receipt is rewritten",
                                  "historical development results and prospective receipts are separate evidence classes and are never pooled"],
                        "status": "DESIGNED_NOT_RUNNING: no receipt is written and no schedule exists in this change"},
        "lifecycle": {
            "sequence": ["workflow_dispatch on merged main", "committed exact spec and sidecar", "every pin verified", "signal-time feature assembly and the registered "
                         "depth / ranking gates (can stop before anything is spent)", "no committed result, marker or manifest", "no execution lock under the study prefix",
                         "durable exclusive lock (atomic POST /git/refs)", "execution marker", "first market-value read", "six paths x three cost stresses", "immutable result artifact",
                         "automatic seal: verify run, artifact digest, file list, manifest, marker, spec and lock refs", "copy exact bytes plus provenance", "ONE Draft pull request",
                         "a human reviews and merges"],
            "executionLock": "refs/tags/" + STUDY + "-execution-lock plus -<specSha256>; any existing ref under the prefix refuses; never moved or deleted",
            "failureBeforeLock": "spends nothing", "failureAfterLock": "consumes the study permanently; never retried; the attempt artifact is preserved under -attempt-<runId>",
            "resultPath": E.RESULT_PATH, "markerPath": E.MARKER_PATH, "manifestPath": E.MANIFEST_PATH,
            "seal": {"module": "pipeline/kr_integrated_alpha_portfolio_seal.py", "script": "scripts/seal_kr_integrated_alpha_portfolio_v1.py",
                     "never": ["rerun outcomes", "change or reformat a result byte", "tune anything", "reinterpret a layer decision", "merge", "mark ready for review",
                               "seal an attempt artifact"]}},
        "outcomeAccess": {"counters": list(E.COUNTER_NAMES), "outcomeCounters": list(E.OUTCOME_COUNTER_NAMES), "inThisChange": "NONE",
                          "verifyAndReadinessRequireAllZero": True},
        "boundary": {"isValidation": False, "isProspective": False, "isProductionModel": False, "usesMachineLearning": False, "mayDiscoverNewFactors": False,
                     "mayTuneAThresholdOrWeightFromOutcomes": False, "mayAddMacroPredictors": False, "mayChangeC0OrC1": False, "mayRedesignIndustryMembership": False,
                     "mayChangeBenchmarkOrHorizons": False, "mayAddAnArchitectureAfterOutcomes": False, "mayRerunAnyPriorStudy": False,
                     "outcomeExecutionInThisChange": False, "changeAfterOutcomeAccessRequires": "a NEW study identity"},
        "tests": TESTS, "entryPoints": ENTRY_POINTS, "sealedDataInputs": sealed,
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
