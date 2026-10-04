#!/usr/bin/env python3
"""Write research_specs/kr-market-risk-anatomy-v1.json — the EXECUTION spec — and its SHA-256 sidecar.

It references (never contains) the frozen scientific design by digest, pins the committed source snapshot file by file, copies the preserved raw-input pin
for the extended tier from the sealed industry spec, and computes every dependency hash from the import closure plus the sealed data inputs. It reads no
source value, price or outcome."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import kr_market_risk_anatomy as M  # noqa: E402
from pipeline.alpha_opportunity_v3_spec import import_closure  # noqa: E402
from pipeline.kr_model_portfolio_execution import digest, file_hash  # noqa: E402

STUDY = M.STUDY
PRE_SOURCE_FREEZE_COMMIT = "8091944a2dea3a7fc91c6135b364222bdc997fd0"
ENTRY_POINTS = ["pipeline/kr_market_risk_anatomy_execution.py", "pipeline/kr_market_risk_anatomy_analysis.py", "pipeline/kr_market_risk_anatomy.py",
                "pipeline/kr_market_risk_sources.py", "pipeline/kr_market_risk_source_parse.py"]
SNAPSHOT = "data/kr-market-risk-anatomy-v1/sources"


def snapshot_files():
    base = ROOT / SNAPSHOT
    return sorted(str(p.relative_to(base)) for p in base.rglob("*") if p.is_file() and p.name != "audit.json")


def build():
    design_path = ROOT / "research_specs" / (STUDY + "-design.json")
    design = json.loads(design_path.read_text())
    industry = json.loads((ROOT / "research_specs/kr-industry-opportunity-anatomy-v1.json").read_text())
    files = snapshot_files()
    sealed = sorted(set([
        "research_specs/" + STUDY + "-design.json", "research_specs/" + STUDY + "-design.sha256", "docs/" + STUDY + "-design.md",
        ".github/workflows/" + STUDY + ".yml", "scripts/run_kr_market_risk_anatomy_v1.py", "scripts/build_kr_market_risk_anatomy_design.py",
        "scripts/build_kr_market_risk_anatomy_spec.py", SNAPSHOT + "/audit.json", "data/kr-industry-membership-foundation-v1/top120-inputs.json",
        "research_specs/kr-model-overlay-portfolio-v1.json", "research_specs/kr-model-overlay-portfolio-v1.sha256"] + [SNAPSHOT + "/" + f for f in files]))
    spec = {
        "studyId": STUDY, "scientificStatus": M.SCIENTIFIC_STATUS, "phase": "ANATOMY_SOURCE_FOUNDATION_AND_HARNESS_ONLY_NO_OUTCOME_COMPUTED",
        "designSha256": digest(design), "designPath": "research_specs/" + STUDY + "-design.json", "preSourceFreezeCommit": PRE_SOURCE_FREEZE_COMMIT,
        "boundary": design["boundary"],
        "sourcePins": {"snapshotDir": SNAPSHOT, "auditSha256": file_hash(ROOT / SNAPSHOT / "audit.json"),
                       "files": {f: file_hash(ROOT / SNAPSHOT / f) for f in files},
                       "rule": "the committed snapshot is the only source input; an ACQUIRED source is immutable and any change to a pinned byte fails verification"},
        "input": industry["input"],
        "inputRole": "EXTENDED_KR_INTERNALS only: the preserved raw-input artifact (prices, market caps, PIT Top120 membership); never recollected, never part of the CORE decision",
        "lifecycle": design["lifecycle"],
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
