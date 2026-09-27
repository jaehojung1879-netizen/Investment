"""Sealed alpha-opportunity-model-v4 contract. Research only; no production
import. PREREGISTRATION ONLY -- this module never constructs a label,
fits a model, or reads a price.

v4 differs from v3 in exactly one structural way: it is KR-only (see the
spec's own `scope` block for why), and it separates SOURCE-FOUNDATION
completeness (`sourceFoundationCitation`, a snapshot of the already-sealed
`kr-terminal-action-reconstruction-v2` artifact AS OF THIS SEAL, which stays
`PARTIALLY_REPAIRED`) from STUDY-DESIGN readiness (`preregistrationStatus`).
The former is not, and cannot be, changed by this module. The latter can be
`READY_FOR_HISTORICAL_EXECUTION` even while the former is `PARTIALLY_
REPAIRED`, because the two v3 KR design blockers this spec inherited
(`KR_TERMINATED_NAME_DIVIDEND_LINEAGE_ABSENT`,
`KR_TERMINAL_CONSIDERATION_UNRESOLVED`) are resolved here by a predeclared,
machine-checked ELIGIBILITY POLICY (`pipeline/alpha_opportunity_v4_
eligibility.py`) that excludes affected observations, not by the underlying
data becoming complete.

CORRECTION (this revision): the first version of this module hash-pinned
`kr-terminal-action-reconstruction-v2.json` (and two sibling artifacts) into
`dependencyHashes`/`sealedDataInputs` and additionally re-verified the
artifact's own quoted `foundationStatus` against disk on every load. That
directly contradicted this same module's own documented claim (and
`docs/alpha-opportunity-model-v4-preregistration.md`'s own claim) that "a
future data-foundation PR that resolves a security's ex-date lineage would
let the SAME eligibility function admit it without a new preregistration" --
a future repair changes that artifact's bytes, which the OLD `load_sealed`
would refuse to load at all (`SEALED_DEPENDENCY_CHANGED`). Sealing a POLICY
and pinning its evidentiary INPUT's exact bytes are two different
promises, and this module now keeps only the first: `sourceFoundationCitation`
is a historical record of what the artifact looked like when this spec was
sealed (informational, never re-verified at load time), never an input this
loader's hash check depends on. The three KR terminal-action artifacts
(`kr-terminal-action-reconstruction-v2.json`, `kr-termination-inventory
.json`, `data/kr-terminal-corporate-actions.json`) are accordingly NOT in
`sealedDataInputs` -- they are expected to IMPROVE over time exactly as any
other growing ledger in this repository does (`Historical replay invariants`
(v2.6): "The invariant is PREFIX STABILITY, never immutability"), and a
future execution reads whatever current snapshot exists, calling
`alpha_opportunity_v4_eligibility.assert_foundation_not_regressed` first to
prove the new snapshot only ever adds evidence, never removes it, against
the cited snapshot recorded here (retrievable from this exact commit via
`git show`, named in `sourceFoundationCitation`).

v1, v2 AND v3 are verified byte-for-byte by their own spec digests and
sidecars -- v4 never re-derives their content, only pins and checks it,
following the discipline v3 already established for v1/v2 (v3's own
docstring: "v3 must not inherit v2's oversized [dependency list]"; the same
reasoning is why v4 does not re-import v3's own (empty, US-blocked)
dependency closure). This IS still the right discipline for v1/v2/v3, and
for the `alpha-opportunity-model-v3-survivorship-audit.json` this spec DOES
still hash-pin (unlike the KR terminal-action artifacts): both are
DECLARED-FROZEN, input-only snapshots that are never legitimately updated in
place, never a growing ledger.
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


def verify_source_foundation_citation(spec):
    """`sourceFoundationCitation` is a well-formed historical record -- this
    checks the SPEC's own internal shape only (every entry names a path and
    a sha256 it claims held AT SEAL TIME), never the artifact on disk today.
    Deliberately NOT called against the live filesystem: see module
    docstring for why re-verifying a growing ledger's current bytes against
    a sealed spec is exactly the contradiction this revision removes.
    """
    for name, entry in spec["sourceFoundationCitation"].items():
        if not entry.get("path") or not entry.get("shaAsOfThisSeal"):
            raise ValueError("MALFORMED_SOURCE_FOUNDATION_CITATION: " + name)
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
    verify_source_foundation_citation(spec)
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
        "sourceFoundationStatusAsOfThisSeal": {
            name: entry["foundationStatusAsOfThisSeal"]
            for name, entry in spec["sourceFoundationCitation"].items()
            if "foundationStatusAsOfThisSeal" in entry},
        "executionMustReverifyFoundationAgainstLiveData": True,
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
