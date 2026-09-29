"""Sealed alpha-opportunity-model-v5 contract. Research only; no production import.

PREREGISTRATION ONLY. This module verifies identities and refuses to execute; it
never builds a label, fits a model or reads a price or outcome.

v5 is the first version whose confirmatory ordering statistic is
`rankWeightedSpread` (explicitly a pre-outcome revision of the earlier rank-IC
expectation) and whose inference is the calendar-time self-normalised interval
that `ALPHA_INFERENCE_CALIBRATION_V5` calibrated on synthetic data. It is KR-only
for this single execution because the US survivorship defect has no repaired,
sealed input; the two regions remain separate models and are never pooled.

Execution code is deliberately OUTSIDE the sealed dependency closure (as v4's
was): adding a reviewed execution harness later must not rewrite what this
preregistration froze, and `require_execution` refuses until that harness exists.
"""
from __future__ import annotations

import json
from pathlib import Path

from .alpha_opportunity_spec import digest, file_hash, read_json
from .alpha_opportunity_v3_spec import FORBIDDEN_DECISION_PARAMETERS, _find_keys, import_closure

STUDY = "alpha-opportunity-model-v5"
PRIOR = ("alpha-opportunity-model-v1", "alpha-opportunity-model-v2",
         "alpha-opportunity-model-v3", "alpha-opportunity-model-v4")
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = ROOT / "research_specs" / f"{STUDY}.json"
READY = "READY_FOR_HISTORICAL_EXECUTION"
NO_HARNESS = "NO_V5_EXECUTION_HARNESS_IN_THIS_PR"
SNAPSHOT_MANIFEST = "research_specs/kr-repaired-accounting-snapshot-v1.json"
CALIBRATION_V5 = "research_specs/alpha-inference-calibration-v5.json"
V4_SPEC = "research_specs/alpha-opportunity-model-v4.json"

__all__ = ["STUDY", "PRIOR", "DEFAULT_SPEC", "READY", "load_sealed", "verify_prior_versions",
           "verify_inherited", "verify_snapshot_pin", "verify_calibration_pin", "require_execution",
           "digest", "read_json"]


def sealed_file_set(spec, root=ROOT):
    return sorted(set(import_closure(spec["dependencyClosure"]["entryPoints"], root))
                  | set(spec["sealedDataInputs"]))


def verify_prior_versions(spec, root=ROOT):
    """v1-v4 remain the merged seals, checked by their own digests and sidecars."""
    for record in spec["priorVersions"]:
        path = Path(root) / "research_specs" / f"{record['studyId']}.json"
        prior = read_json(path)
        sidecar = path.with_suffix(".sha256").read_text().strip()
        if prior.get("studyId") != record["studyId"] or record["studyId"] not in PRIOR:
            raise ValueError("PRIOR_IDENTITY_CHANGED: " + record["studyId"])
        if not digest(prior) == sidecar == record["specSha256"]:
            raise ValueError("PRIOR_SEAL_CHANGED: " + record["studyId"])
    return True


def _pointer(document, dotted):
    node = document
    for part in dotted.split("."):
        node = node[part]
    return node


def verify_inherited(spec, root=ROOT):
    """Every value marked inherited must still equal its sealed source, byte for byte."""
    v4 = read_json(Path(root) / V4_SPEC)
    for name, entry in spec["inherited"].items():
        source = _pointer(v4, entry["sourcePointer"])
        if digest(source) != entry["valueSha256"] or source != entry["value"]:
            raise ValueError("INHERITED_VALUE_CHANGED: " + name)
    return True


def verify_snapshot_pin(spec, root=ROOT):
    """The KR accounting snapshot pin must agree with the frozen manifest and its module constants."""
    from . import kr_repaired_accounting_snapshot as K
    pin = spec["inputs"]["krAccounting"]
    manifest_path = Path(root) / SNAPSHOT_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if pin["snapshotContentSha256"] != K.FROZEN_CONTENT_SHA256 or \
            manifest["snapshotContentSha256"] != K.FROZEN_CONTENT_SHA256:
        raise ValueError("SNAPSHOT_CONTENT_HASH_CHANGED")
    if (pin["candidateIdentitySha256"] != K.CANDIDATE_SHA256 or pin["sourceCommit"] != K.SOURCE_COMMIT
            or manifest["candidateIdentitySha256"] != K.CANDIDATE_SHA256
            or pin["manifestFileSha256"] != file_hash(manifest_path)
            or pin["recordCount"] != manifest["recordCount"]):
        raise ValueError("SNAPSHOT_PIN_DISAGREES_WITH_MANIFEST")
    if {n: s["gitBlobSha1"] for n, s in manifest["shards"].items()} != pin["gitBlobSha1"]:
        raise ValueError("SNAPSHOT_SHARD_IDENTITY_CHANGED")
    return True


def verify_calibration_pin(spec, root=ROOT):
    """The calibrated inference contract this study inherits is the frozen one."""
    calib_path = Path(root) / CALIBRATION_V5
    calibration = read_json(calib_path)
    pin = spec["inference"]["calibration"]
    if file_hash(calib_path) != pin["specFileSha256"]:
        raise ValueError("CALIBRATION_SPEC_CHANGED")
    for rel, sha in calibration["engineIdentity"]["files"].items():
        if file_hash(Path(root) / rel) != sha or pin["engineFiles"].get(rel) != sha:
            raise ValueError("CALIBRATION_ENGINE_CHANGED: " + rel)
    statistics = calibration["statistics"]
    if (statistics["confirmatory"] != pin["confirmatoryStatistics"]
            or statistics["descriptive"] != pin["descriptiveStatistics"]
            or calibration["intervalConstruction"]["U1CriticalValue"] != pin["U1CriticalValue"]
            or calibration["confidence"]["nominalCoverage"] != pin["nominalCoverage"]):
        raise ValueError("CALIBRATED_CONTRACT_DISAGREES_WITH_V5_PIN")
    return True


def load_sealed(path=DEFAULT_SPEC, *, expected_hash, root=ROOT):
    path, root = Path(path), Path(root)
    spec = read_json(path)
    seal = path.with_suffix(".sha256")
    if not seal.is_file() or not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise ValueError("UNSEALED_SPEC")
    if not digest(spec) == seal.read_text().strip() == expected_hash:
        raise ValueError("SEALED_SPEC_CHANGED: create and review a NEW version")
    if spec.get("studyId") != STUDY or not spec.get("immutableVersion"):
        raise ValueError("INVALID_STUDY_IDENTITY: the v5 runner never substitutes another study")
    if spec.get("regions") != ["KR"]:
        raise ValueError("UNSUPPORTED_CONTRACT: this single execution is KR-only; US is blocked")
    forbidden = _find_keys(spec, set(FORBIDDEN_DECISION_PARAMETERS))
    if forbidden:
        raise ValueError("FORBIDDEN_DECISION_PARAMETER: " + ", ".join(forbidden))
    if sorted(spec["dependencyHashes"]) != sealed_file_set(spec, root):
        raise ValueError("DEPENDENCY_CLOSURE_CHANGED: sealed files differ from the recomputed closure")
    for rel, sha in spec["dependencyHashes"].items():
        p = (root / rel).resolve()
        if not p.is_relative_to(root.resolve()) or not p.is_file() or file_hash(p) != sha:
            raise ValueError("SEALED_DEPENDENCY_CHANGED: " + rel)
    verify_prior_versions(spec, root)
    verify_inherited(spec, root)
    verify_snapshot_pin(spec, root)
    verify_calibration_pin(spec, root)
    return spec


def require_execution(spec):
    """Refuse execution until a separately reviewed harness exists."""
    raise RuntimeError(NO_HARNESS)
