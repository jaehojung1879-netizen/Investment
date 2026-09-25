"""Sealed alpha-opportunity-model-v3 contract. Research only; no production import.

The seal pins the TRUE execution closure, computed, never hand-listed: every
repository module reachable from the declared entry points through a pipeline
import (top-level OR inside a function, because a lazy import runs when its
function is called), plus explicitly declared data inputs. Loading refuses a
spec whose sealed file set differs from the recomputed one, so a new import
cannot slip in unsealed, and a module outside the closure (portfolio code, the
production scorer) cannot strand the seal by changing.

v1 and v2 are verified byte-for-byte by their own spec digests and sidecars,
NOT through their dependency lists: v3 must not inherit v2's oversized one.
"""
from __future__ import annotations

import ast
from pathlib import Path

from .alpha_opportunity_spec import digest, file_hash, read_json

STUDY = "alpha-opportunity-model-v3"
PRIOR = ("alpha-opportunity-model-v1", "alpha-opportunity-model-v2")
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = ROOT / "research_specs" / f"{STUDY}.json"

READY = "READY_FOR_HISTORICAL_EXECUTION"
STATUSES = (READY, "BLOCKED_BY_DATA_INTEGRITY", "BLOCKED_BY_SAMPLE_DEPTH", "BLOCKED_BY_EXECUTION_DATA")
BLOCKER_PRECEDENCE = STATUSES[1:]

# A spec that gives any of these a value is refused: each would be a hidden
# hurdle on the EXISTENCE of expected alpha, or a portfolio-layer decision.
FORBIDDEN_DECISION_PARAMETERS = (
    "minimumEdge", "minimumAlphaHurdle", "concentrationRiskMultiple", "tradeNotional",
    "orderNotional", "portfolioValue", "maximumAdvFraction", "minimumAdv", "fixedTopN",
    "targetNames", "fixedHoldings", "regionQuota", "investedFraction",
    "probabilityHurdle", "minimumProbability", "lowerBoundHurdle", "minimumLowerBound",
    "riskAversion", "confidenceWeight", "kellyFraction",
)


def _pipeline_imports(path):
    """Pipeline module names imported anywhere in one file (top-level or lazy)."""
    names = set()
    for node in ast.walk(ast.parse(Path(path).read_text())):
        if isinstance(node, ast.ImportFrom):
            if node.level == 1:
                names.update([node.module.split(".")[0]] if node.module else [a.name for a in node.names])
            elif node.level == 0 and (node.module or "").split(".")[0] == "pipeline":
                parts = node.module.split(".")
                names.update([parts[1]] if len(parts) > 1 else [a.name for a in node.names])
        elif isinstance(node, ast.Import):
            names.update(a.name.split(".")[1] for a in node.names if a.name.startswith("pipeline."))
    return names


def import_closure(entry_points, root=ROOT):
    """Deterministic repo-relative closure of the entry points (sorted)."""
    root = Path(root)
    seen, stack = set(), [root / e for e in entry_points]
    while stack:
        path = stack.pop()
        rel = str(path.relative_to(root))
        if rel in seen or not path.is_file():
            continue
        seen.add(rel)
        for name in _pipeline_imports(path):
            module = root / "pipeline" / f"{name}.py"
            if module.is_file():
                stack.append(module)
    if any(p.startswith("pipeline/") for p in seen):
        seen.add("pipeline/__init__.py")
    return sorted(seen)


def sealed_file_set(spec, root=ROOT):
    return sorted(set(import_closure(spec["dependencyClosure"]["entryPoints"], root))
                  | set(spec["sealedDataInputs"]))


def _find_keys(value, names, path=""):
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            here = f"{path}.{key}" if path else key
            if key in names and item is not None:
                found.append(here)
            found.extend(_find_keys(item, names, here))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            found.extend(_find_keys(item, names, f"{path}[{i}]"))
    return found


def verify_prior_versions(spec, root=ROOT):
    """v1 and v2 remain the merged seals, checked by their own digests."""
    for record in spec["priorVersions"]:
        path = Path(root) / "research_specs" / f"{record['studyId']}.json"
        prior = read_json(path)
        sidecar = path.with_suffix(".sha256").read_text().strip()
        if prior.get("studyId") != record["studyId"] or record["studyId"] not in PRIOR:
            raise ValueError("PRIOR_IDENTITY_CHANGED: " + record["studyId"])
        if not digest(prior) == sidecar == record["specSha256"]:
            raise ValueError("PRIOR_SEAL_CHANGED: " + record["studyId"])
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
        raise ValueError("INVALID_STUDY_IDENTITY: the v3 runner never substitutes another study")
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
    return {"studyId": STUDY, "immutableVersion": spec["immutableVersion"], "specSha256": spec_hash,
            "phase": "PREREGISTRATION_ONLY", "preregistrationStatus": preregistration_status(spec),
            "blockers": [b["id"] for b in spec.get("designBlockers") or []],
            "regionVerdicts": {r: v["verdict"] for r, v in spec["survivorship"]["regions"].items()},
            "priorVersions": {p["studyId"]: p["specSha256"] for p in spec["priorVersions"]},
            "executionWorkflow": spec["executionWorkflow"],
            "historicalOutcomesComputed": False, "historicalModelsTrained": False,
            "promotionEligible": False, "productionChanged": False}


def require_execution(spec, *, reviewed, branch):
    """Fails closed BEFORE any input is opened. A blocked spec never executes."""
    status = preregistration_status(spec)
    if status != READY:
        raise ValueError(status)
    if not reviewed or branch != "refs/heads/main":
        raise ValueError("MERGE_AND_REVIEW_PREREGISTRATION_FIRST")
