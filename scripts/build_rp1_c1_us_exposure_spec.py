#!/usr/bin/env python3
"""Write the frozen rp1-c1 preregistration, its SHA-256 sidecar and the scientific-content sidecar.

Every scientific section is computed from module constants (and, where inherited, from the sealed KR modules), so `load_spec` can compare them on
every load. The scientific sidecar pins those sections alone: freezing the US sources later re-pins the inputs (the committed source-freeze manifest) and the
dependency map, and the builder refuses to write if that would change one scientific byte. `--check` rebuilds in memory and fails on any difference.
No value is read."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import rp1_c1_us_exposure as U  # noqa: E402
from pipeline import rp1_c1_us_exposure_spec as SP  # noqa: E402
from pipeline import rp1_c1_us_execution as X  # noqa: E402
from pipeline import rp1_c1_us_sources as SRC
from pipeline import rp1_c1_us_refetch as R  # noqa: E402

DOC = "docs/research-program/rp1-c1-us-exposure-ladder-replication.md"
SCRIPTS = ["scripts/build_rp1_c1_us_exposure_spec.py", "scripts/run_rp1_c1_us_exposure.py", "scripts/acquire_rp1_c1_us_sources.py",
           "scripts/acquire_kr_market_risk_sources.py"]


def build(root=ROOT):
    root = Path(root)
    reused = SP.kr_reused_files(root)
    us_pin = SP.us_snapshot_pin(root)
    manifest = {us_pin["manifestPath"]} if us_pin["manifestPath"] else set()
    sealed = sorted(set(SP.KR_SEALED) | set(reused) | manifest | set(SCRIPTS) | set(R.CODE_FILES) | {DOC, "pipeline/kr_market_risk_overlay.py"})
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
            "usRegistry": SRC.SOURCES, "usRights": SRC.SOURCE_RIGHTS, "reusedRights": SRC.REUSED_RIGHTS, "usExpectedIdentity": SRC.EXPECTED_IDENTITY,
            "usSnapshot": {**us_pin, "acquisition": "scripts/acquire_rp1_c1_us_sources.py inside the freeze job (see lifecycle.route); raw bytes never "
                                                    "enter git, a log or any source artifact; re-fetch must match exact bounded inputs"}},
        "model": SP.model_definition(), "portfolio": SP.portfolio_definition(), "evaluation": SP.evaluation_definition(),
        "decision": SP.decision_definition(), "interpretation": SP.interpretation_definition(), "stopRules": SP.stop_rules(),
        "newHypotheses": SP.new_hypotheses(), "preOutcomeRevisions": [],
        "lifecycle": {
            "thisChange": "WP4a-WP4d machinery: data foundation, calendar wrapper, KR equivalence, readiness, frozen spec, source freeze, owner "
                          "authorization, one-shot execution, independent validator and comparison report. Nothing here reads a US value outside the "
                          "registered post-lock path.",
            "route": {"workflow": X.HOST_WORKFLOW, "input": "rp1_c1_action",
                      "actions": {"none": "the host's original job only; every rp1-c1 job is skipped",
                                  "freeze-sources": "manual, main only: acquire, bounded exact input hashes, dates-only readiness, open one Draft PR with "
                                                    "the manifest and the re-pinned spec",
                                  "dry-run": "manual: re-fetch and verify exact bounded input hashes, run every pre-lock check, then the whole evaluation, validator "
                                             "and report on INVENTED values over the real calendar; no lock, no US value",
                                  "execute": "manual, main only, the owner's dispatch: authorization, pins, readiness, equivalence, then the lock, the marker "
                                             "and only then the first US value"},
                      "whyAHostWorkflow": "every workflow inventory layer and both census tests are byte-pinned by sealed Phase C specs, so a new "
                                          "workflow file cannot be added without breaking a seal; the jobs live in an existing, unpinned, spent workflow "
                                          "behind an explicit input whose default runs only that workflow's original job"},
            "storage": {"rule": SRC.STORAGE, "version": R.VERSION, "normalization": R.contract(), "requiredNewSecrets": [],
                        "rawHashes": "audit-only full-response hashes; timestamps and after-end rows may differ",
                        "analysisHashes": "exact byte equality over bounded observations and action/identity context; no tolerance",
                        "limitation": "re-fetch does not preserve bytes or guarantee availability. Revision or access denial stops before the lock; no automatic re-pin"},
            "formalExecution": "workflow_dispatch of rp1_c1_action=execute on merged main by the owner, first attempt, with the exact committed "
                               "authorization (" + X.AUTHORIZATION_PATH + ") whose SHA-256 is typed into the dispatch; the authorization pins this spec, "
                               "its scientific digest, the source freeze and every harness file. Readiness READY and equivalence EXACT, no result, marker "
                               "or lock, then an atomic lock ref, a marker, and only then the first US value read",
            "executionLock": "refs/tags/" + SP.STUDY + "-execution-lock plus -<specSha256>; any ref under the prefix refuses",
            "resultPath": SP.RESULT_PATH, "markerPath": SP.MARKER_PATH,
            "infrastructureRevisions": [
                {"id": "STORAGE_AND_ROUTE_REVISION_1", "madeBeforeAnyUsOutcome": True, "scientificDigestUnchanged": True,
                 "replaced": "US raw bytes committed under data/rp1-c1-us-exposure/sources and no execution route (blocked by the frozen census)",
                 "reason": "three of the four sources are licensed data whose terms do not permit redistribution from a public repository; a new "
                           "workflow file would break the Phase C-pinned census",
                 "now": "encrypted Actions artifact plus a committed dates-and-hashes manifest; jobs in an existing unpinned workflow behind an input"},
                {"id": R.VERSION, "madeBeforeAnyUsOutcome": True, "scientificDigestUnchanged": True,
                 "replaced": "encrypted artifact storage and key setup",
                 "reason": "no Settings, extra credential or external storage dependency; reject re-fetch drift instead of claiming retained-byte reproducibility",
                 "now": "runner-temporary raw data; pinned bounded canonical inputs and code hashes; original response hashes audit-only"}]},
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
