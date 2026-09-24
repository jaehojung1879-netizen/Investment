"""Sealed, research-only contract. No production caller may import this module."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

STUDY = "alpha-opportunity-model-v1"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = ROOT / "research_specs" / f"{STUDY}.json"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _unique_object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key: " + key)
        out[key] = value
    return out


def read_json(path):
    def invalid(value):
        raise ValueError("non-finite JSON: " + value)
    return json.loads(Path(path).read_text(), object_pairs_hook=_unique_object,
                      parse_constant=invalid)


def load_sealed(path=DEFAULT_SPEC, *, expected_hash, root=ROOT):
    """An external reviewed digest AND sidecar are required; no reseal switch."""
    path, root = Path(path), Path(root)
    spec = read_json(path)
    seal = path.with_suffix(".sha256")
    if not seal.is_file() or len(expected_hash) != 64:
        raise ValueError("UNSEALED_SPEC")
    if not digest(spec) == seal.read_text().strip() == expected_hash:
        raise ValueError("SEALED_SPEC_CHANGED: create and review a NEW version")
    if spec.get("studyId") != STUDY or not spec.get("immutableVersion"):
        raise ValueError("INVALID_STUDY_IDENTITY")
    if spec["horizons"] != [21, 126] or spec["regions"] != ["US", "KR"]:
        raise ValueError("UNSUPPORTED_CONTRACT")
    for rel, sha in spec["dependencyHashes"].items():
        p = (root / rel).resolve()
        if not p.is_relative_to(root.resolve()) or file_hash(p) != sha:
            raise ValueError("SEALED_DEPENDENCY_CHANGED: " + rel)
    registry = read_json(root / spec["featureRegistry"])
    keys = [(r["region"], r["name"]) for r in registry["features"]]
    if len(keys) != len(set(keys)):
        raise ValueError("DUPLICATE_FEATURE")
    for region in spec["regions"]:
        for horizon in spec["horizons"]:
            names = spec["allowedFeatures"][region][str(horizon)]
            allowed = [r["name"] for r in registry["features"] if r["region"] == region
                       and r["status"] == "PRIMARY" and horizon in r["horizons"]]
            if names != allowed:
                raise ValueError("REGISTRY_ALLOWLIST_MISMATCH")
    return spec, registry


def design_blockers(spec):
    blockers = list(spec["designBlockers"])
    cfg = spec["investability"]
    checks = {
        "ECONOMIC_EDGE_AND_CONCENTRATION_BUDGET_UNSPECIFIED": any(cfg.get(k) is None for k in ("minimumEdge", "concentrationRiskMultiple")),
        "POSITION_NOTIONAL_LIQUIDITY_CAPACITY_AND_SLIPPAGE_UNSPECIFIED": any(cfg.get(k) is None for k in ("tradeNotional", "maximumAdvFraction", "minimumAdv", "slippageBps")),
        "AS_TRADED_ADV_SOURCE_CONTRACT_UNSEALED": not spec["snapshots"].get("advSnapshotSha256"),
        "FULL_PIT_UNIVERSE_FEATURE_COVERAGE_UNVERIFIED": not spec.get("validatedCoverageArtifact"),
    }
    for name, blocked in checks.items():
        if blocked and name not in blockers:
            blockers.append(name)
    return blockers


def readiness(spec, spec_hash):
    blockers = design_blockers(spec)
    return {"studyId": STUDY, "immutableVersion": spec["immutableVersion"],
            "specSha256": spec_hash, "phase": "PREREGISTRATION_ONLY",
            "verdict": "BLOCKED_PREREGISTRATION" if blockers else "READY_TO_EXECUTE_PREREGISTERED_STUDY",
            "blockers": blockers, "historicalOutcomesComputed": False,
            "historicalModelsTrained": False, "promotionEligible": False,
            "excludedNonblockingFamilies": spec["excludedFamilies"]}


def require_execution(spec, *, reviewed, branch, prerequisites):
    if not reviewed or branch != "refs/heads/main":
        raise ValueError("MERGE_AND_REVIEW_PREREGISTRATION_FIRST")
    blockers = design_blockers(spec)
    if blockers:
        raise ValueError("BLOCKED_PREREGISTRATION: " + ", ".join(blockers))
    if not prerequisites or any(value is not True for value in prerequisites.values()):
        raise ValueError("PREREQUISITE_CONTRACT_FAILED")


def validate_result(report, predictions, spec):
    """Validate the research output before creating any artifact directory."""
    schema = spec["expectedOutputSchema"]
    if not set(schema["resultRequired"]) <= report.keys():
        raise ValueError("INCOMPLETE_RESULT_SCHEMA")
    if report["specSha256"] != digest(spec) or report["promotionEligible"] is not False:
        raise ValueError("RESULT_IDENTITY_OR_PROMOTION_INVALID")
    if set(schema["noPortfolioFields"]) & report.keys():
        raise ValueError("PORTFOLIO_OUTPUT_FORBIDDEN")
    if predictions is not None and not predictions.empty:
        if not set(schema["predictionRequired"]) <= set(predictions.columns):
            raise ValueError("INCOMPLETE_PREDICTION_SCHEMA")
        if not predictions.specSha256.eq(digest(spec)).all():
            raise ValueError("PREDICTION_IDENTITY_INVALID")
        if predictions.duplicated(["date", "ticker", "region", "horizon", "family"]).any():
            raise ValueError("DUPLICATE_PREDICTION")
    canonical(report)  # No NaN/Infinity masquerading as a measured result.
