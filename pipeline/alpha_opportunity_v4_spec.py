"""Sealed alpha-opportunity-model-v4 contract. Research only; no production
import. PREREGISTRATION ONLY -- this module never constructs a label,
fits a model, or reads a price.

v4 differs from v3 in exactly one structural way: it is KR-only (see the
spec's own `scope` block for why), and it separates SOURCE-FOUNDATION
completeness (`sourceFoundation`, read from the already-sealed
`kr-terminal-action-reconstruction-v2` artifact, which stays
`PARTIALLY_REPAIRED`) from STUDY-DESIGN readiness (`preregistrationStatus`).
The former is not, and cannot be, changed by this module. The latter can be
`READY_FOR_HISTORICAL_EXECUTION` even while the former is `PARTIALLY_
REPAIRED`, because the two v3 KR design blockers this spec inherited
(`KR_TERMINATED_NAME_DIVIDEND_LINEAGE_ABSENT`,
`KR_TERMINAL_CONSIDERATION_UNRESOLVED`) are resolved here by a predeclared,
machine-checked ELIGIBILITY POLICY (`pipeline/alpha_opportunity_v4_
eligibility.py`) that excludes affected observations, not by the underlying
data becoming complete. `docs/alpha-opportunity-model-v4-preregistration.md`
states this distinction in full; this module enforces it by never reading
or writing `sourceFoundation.krTerminalActionReconstructionV2.
foundationStatus` as anything other than a cited, hash-pinned fact.

v1, v2 AND v3 are verified byte-for-byte by their own spec digests and
sidecars -- v4 never re-derives their content, only pins and checks it,
following the discipline v3 already established for v1/v2 (v3's own
docstring: "v3 must not inherit v2's oversized [dependency list]"; the same
reasoning is why v4 does not re-import v3's own (empty, US-blocked)
dependency closure).
"""
from __future__ import annotations

from pathlib import Path

from .alpha_opportunity_spec import digest, file_hash, read_json
from .alpha_opportunity_v3_spec import FORBIDDEN_DECISION_PARAMETERS, _find_keys, import_closure

STUDY = "alpha-opportunity-model-v4"
PRIOR = ("alpha-opportunity-model-v1", "alpha-opportunity-model-v2", "alpha-opportunity-model-v3")
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = ROOT / "research_specs" / f"{STUDY}.json"

READY = "READY_FOR_HISTORICAL_EXECUTION"
STATUSES = (READY, "BLOCKED_BY_DATA_INTEGRITY", "BLOCKED_BY_SAMPLE_DEPTH", "BLOCKED_BY_EXECUTION_DATA")
BLOCKER_PRECEDENCE = STATUSES[1:]

# A spec that gives any of these a value is refused -- exactly v3's list,
# reused rather than re-declared so the two studies cannot silently diverge
# on what counts as a forbidden hidden hurdle or portfolio-layer parameter.
__all__ = ["STUDY", "PRIOR", "DEFAULT_SPEC", "READY", "load_sealed", "verify_prior_versions",
          "preregistration_status", "readiness", "require_execution", "digest", "read_json"]


def sealed_file_set(spec, root=ROOT):
    return sorted(set(import_closure(spec["dependencyClosure"]["entryPoints"], root))
                  | set(spec["sealedDataInputs"]))


def verify_prior_versions(spec, root=ROOT):
    """v1, v2 AND v3 remain the merged seals, checked by their own digests."""
    for record in spec["priorVersions"]:
        path = Path(root) / "research_specs" / f"{record['studyId']}.json"
        prior = read_json(path)
        sidecar = path.with_suffix(".sha256").read_text().strip()
        if prior.get("studyId") != record["studyId"] or record["studyId"] not in PRIOR:
            raise ValueError("PRIOR_IDENTITY_CHANGED: " + record["studyId"])
        if not digest(prior) == sidecar == record["specSha256"]:
            raise ValueError("PRIOR_SEAL_CHANGED: " + record["studyId"])
    return True


def verify_source_foundation(spec, root=ROOT):
    """The cited source-foundation artifacts are unchanged AND their status
    is quoted verbatim -- this function never computes or infers a status,
    only checks that the one the spec quotes still matches the artifact on
    disk. A foundation improving OR regressing after this seal both raise
    here, because either would mean the spec's own quoted fact is stale.
    """
    for entry in spec["sourceFoundation"].values():
        path = Path(root) / entry["path"]
        if file_hash(path) != entry["sha256"]:
            raise ValueError("SOURCE_FOUNDATION_ARTIFACT_CHANGED: " + entry["path"])
        if "foundationStatus" in entry:
            actual = read_json(path).get("foundationStatus")
            if actual != entry["foundationStatus"]:
                raise ValueError("SOURCE_FOUNDATION_STATUS_STALE: " + entry["path"])
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
        raise ValueError("INVALID_STUDY_IDENTITY: the v4 runner never substitutes another study")
    if spec.get("regions") != ["KR"]:
        raise ValueError("UNSUPPORTED_CONTRACT: v4 is KR-only")
    forbidden = _find_keys(spec, set(FORBIDDEN_DECISION_PARAMETERS))
    if forbidden:
        raise ValueError("FORBIDDEN_DECISION_PARAMETER: " + ", ".join(forbidden))
    expected = sealed_file_set(spec, root)
    if sorted(spec["dependencyHashes"]) != expected:
        raise ValueError("DEPENDENCY_CLOSURE_CHANGED: sealed files differ from the recomputed closure")
    for rel, sha in spec["dependencyHashes"].items():
        p = (root / rel).resolve()
        if not p.is_relative_to(root.resolve()) or not p.is_file() or file_hash(p) != sha:
            raise ValueError("SEALED_DEPENDENCY_CHANGED: " + rel)
    verify_prior_versions(spec, root)
    verify_source_foundation(spec, root)
    return spec


def preregistration_status(spec):
    blockers = spec.get("designBlockers") or []
    categories = {b["category"] for b in blockers}
    if not categories <= set(BLOCKER_PRECEDENCE):
        raise ValueError("UNREGISTERED_BLOCKER_CATEGORY")
    computed = next((c for c in BLOCKER_PRECEDENCE if c in categories), READY)
    if spec.get("preregistrationStatus") != computed:
        raise ValueError("DECLARED_STATUS_DISAGREES_WITH_BLOCKERS")
    return computed


def readiness(spec, spec_hash):
    return {
        "studyId": STUDY, "immutableVersion": spec["immutableVersion"], "specSha256": spec_hash,
        "phase": "PREREGISTRATION_ONLY", "preregistrationStatus": preregistration_status(spec),
        "sourceFoundationStatus": {
            name: entry["foundationStatus"] for name, entry in spec["sourceFoundation"].items()
            if "foundationStatus" in entry},
        "blockers": [b["id"] for b in spec.get("designBlockers") or []],
        "formerBlockersResolvedByPolicyNotByData": [
            b["id"] for b in spec.get("formerV3BlockersResolvedByPolicy") or []],
        "priorVersions": {p["studyId"]: p["specSha256"] for p in spec["priorVersions"]},
        "executionWorkflow": spec["executionWorkflow"],
        "historicalOutcomesComputed": False, "historicalModelsTrained": False,
        "labelsConstructed": False, "promotionEligible": False, "productionChanged": False,
    }


def require_execution(spec, *, reviewed, branch):
    """Fails closed BEFORE any input is opened. Even a READY design has no
    execution harness in this PR -- see module docstring and
    `scripts/run_alpha_opportunity_model_v4.py`."""
    status = preregistration_status(spec)
    if status != READY:
        raise ValueError(status)
    if not reviewed or branch != "refs/heads/main":
        raise ValueError("MERGE_AND_REVIEW_PREREGISTRATION_FIRST")
