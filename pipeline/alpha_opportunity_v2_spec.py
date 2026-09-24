"""Sealed alpha-opportunity-model-v2 contract. Research only; no production import.

v2 is a NEW immutable version. It never edits, reseals or falls back to v1:
loading v2 re-verifies that the v1 spec and its sidecar are byte-for-byte the
merged seal, and a v2 run refuses any spec whose studyId is not v2.
"""
from __future__ import annotations

from pathlib import Path

from .alpha_opportunity_spec import canonical, digest, file_hash, read_json

STUDY = "alpha-opportunity-model-v2"
V1_STUDY = "alpha-opportunity-model-v1"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = ROOT / "research_specs" / f"{STUDY}.json"
V1_SPEC = ROOT / "research_specs" / f"{V1_STUDY}.json"

READY = "READY_FOR_HISTORICAL_EXECUTION"
STATUSES = (READY, "BLOCKED_BY_DATA_INTEGRITY", "BLOCKED_BY_SAMPLE_DEPTH",
            "BLOCKED_BY_EXECUTION_DATA")
# Earlier categories win when blockers of several kinds remain.
BLOCKER_PRECEDENCE = STATUSES[1:]

# Quantities v1 required before execution and v2 deliberately does NOT: a
# spec that reintroduces any of them as a value is refused, not tolerated.
FORBIDDEN_DECISION_PARAMETERS = (
    "minimumEdge", "minimumAlphaHurdle", "concentrationRiskMultiple", "tradeNotional",
    "orderNotional", "portfolioValue", "maximumAdvFraction", "minimumAdv",
    "fixedTopN", "targetNames", "fixedHoldings", "regionQuota", "investedFraction",
)


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


def verify_v1_untouched(spec, root=ROOT):
    """v1 stays the merged, sealed provenance record; v2 never edits it."""
    record = spec["supersedes"]
    v1_path = Path(root) / "research_specs" / f"{V1_STUDY}.json"
    v1 = read_json(v1_path)
    sidecar = v1_path.with_suffix(".sha256").read_text().strip()
    if record["studyId"] != V1_STUDY or v1.get("studyId") != V1_STUDY:
        raise ValueError("V1_IDENTITY_CHANGED")
    if not digest(v1) == sidecar == record["specSha256"]:
        raise ValueError("V1_SEAL_CHANGED: v1 is immutable provenance")
    return True


def load_sealed(path=DEFAULT_SPEC, *, expected_hash, root=ROOT):
    """External reviewed digest AND sidecar must agree; no reseal switch."""
    path, root = Path(path), Path(root)
    spec = read_json(path)
    seal = path.with_suffix(".sha256")
    if not seal.is_file() or not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise ValueError("UNSEALED_SPEC")
    if not digest(spec) == seal.read_text().strip() == expected_hash:
        raise ValueError("SEALED_SPEC_CHANGED: create and review a NEW version")
    if spec.get("studyId") != STUDY or not spec.get("immutableVersion"):
        raise ValueError("INVALID_STUDY_IDENTITY: v2 runner never substitutes another study")
    if spec["horizons"] != [21, 126] or spec["regions"] != ["US", "KR"]:
        raise ValueError("UNSUPPORTED_CONTRACT")
    forbidden = _find_keys(spec, set(FORBIDDEN_DECISION_PARAMETERS))
    if forbidden:
        raise ValueError("FORBIDDEN_DECISION_PARAMETER: " + ", ".join(forbidden))
    for rel, sha in spec["dependencyHashes"].items():
        p = (root / rel).resolve()
        if not p.is_relative_to(root.resolve()) or not p.is_file() or file_hash(p) != sha:
            raise ValueError("SEALED_DEPENDENCY_CHANGED: " + rel)
    verify_v1_untouched(spec, root)
    registry = read_json(root / spec["featureRegistry"])
    keys = [(r["region"], r["name"]) for r in registry["features"]]
    if len(keys) != len(set(keys)):
        raise ValueError("DUPLICATE_FEATURE")
    for region in spec["regions"]:
        for horizon in spec["horizons"]:
            names = spec["allowedFeatures"][region][str(horizon)]
            allowed = [r["name"] for r in registry["features"] if r["region"] == region
                       and r["status"] == "PRIMARY" and horizon in r["horizons"]
                       and r["name"] not in spec["removedFeatures"].get(region, {})]
            if names != allowed:
                raise ValueError("REGISTRY_ALLOWLIST_MISMATCH")
    return spec, registry


def preregistration_status(spec):
    """One of the four statuses, derived from the remaining REAL blockers."""
    blockers = spec.get("designBlockers") or []
    categories = {b["category"] for b in blockers}
    if not categories <= set(BLOCKER_PRECEDENCE):
        raise ValueError("UNREGISTERED_BLOCKER_CATEGORY")
    computed = next((c for c in BLOCKER_PRECEDENCE if c in categories), READY)
    if spec.get("preregistrationStatus") != computed:
        raise ValueError("DECLARED_STATUS_DISAGREES_WITH_BLOCKERS")
    return computed


def readiness(spec, spec_hash):
    status = preregistration_status(spec)
    return {"studyId": STUDY, "immutableVersion": spec["immutableVersion"],
            "specSha256": spec_hash, "phase": "PREREGISTRATION_ONLY",
            "preregistrationStatus": status,
            "blockers": [b["id"] for b in spec.get("designBlockers") or []],
            "runtimePreLabelGates": [g["id"] for g in spec["runtimePreLabelGates"]],
            "supersedes": spec["supersedes"]["studyId"],
            "v1SpecSha256": spec["supersedes"]["specSha256"],
            "historicalOutcomesComputed": False, "historicalModelsTrained": False,
            "promotionEligible": False,
            "productionChanged": False}


def require_execution(spec, *, reviewed, branch, prerequisites):
    if not reviewed or branch != "refs/heads/main":
        raise ValueError("MERGE_AND_REVIEW_PREREGISTRATION_FIRST")
    status = preregistration_status(spec)
    if status != READY:
        raise ValueError(status)
    if not prerequisites or any(value is not True for value in prerequisites.values()):
        raise ValueError("PREREQUISITE_CONTRACT_FAILED")


def validate_result(report, predictions, spec):
    """Checked before any output directory is created."""
    schema = spec["expectedOutputSchema"]
    if not set(schema["resultRequired"]) <= report.keys():
        raise ValueError("INCOMPLETE_RESULT_SCHEMA")
    if report["studyId"] != STUDY or report["specSha256"] != digest(spec):
        raise ValueError("RESULT_IDENTITY_INVALID")
    if report["promotionEligible"] is not False:
        raise ValueError("PROMOTION_FORBIDDEN")
    if set(schema["noPortfolioFields"]) & report.keys():
        raise ValueError("PORTFOLIO_OUTPUT_FORBIDDEN")
    if predictions is not None and not predictions.empty:
        if not set(schema["predictionRequired"]) <= set(predictions.columns):
            raise ValueError("INCOMPLETE_PREDICTION_SCHEMA")
        if set(schema["noPortfolioFields"]) & set(predictions.columns):
            raise ValueError("PORTFOLIO_OUTPUT_FORBIDDEN")
        if not predictions.specSha256.eq(digest(spec)).all():
            raise ValueError("PREDICTION_IDENTITY_INVALID")
        if predictions.duplicated(["date", "ticker", "region", "horizon", "family"]).any():
            raise ValueError("DUPLICATE_PREDICTION")
    canonical(report)
