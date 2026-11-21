"""Outcome-free adapters to one PREPARED prospective contract, never an engine.

The named reference is #316's prospective proposal. Its scientific admission,
registration and execution status are not changed here. #317 plans describe a
different estimand and are inspected for identity only, never silently converted.
No source module is imported/executed and no price, return or score is computed.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

from pipeline import prospective_receipt_core as core
from pipeline import replay_calendar
from pipeline import weekly_decision as weekly

CANONICAL_COMMIT = "75aab7bc7096b551543bc1582c1e7fd288e94e59"
CANONICAL_PATH = "research/master_research_program_v1/portfolio/portfolio-d-p0-p5-comparison-v1.json"
CANONICAL_SHA256 = "eecdb60753efa8e9600a3d0595109914a56851be236ebfb037d6ca102db3021c"
FOUNDATION_COMMIT = "a3ee7a716e56c97c99b02537ac060aca01bdb038"
FOUNDATION_PATH = "research/cross_market_foundation_v1/comparison.py"
FOUNDATION_SHA256 = "a4a27e8511d2a3bd23d390652b2318bb11ea616161d4088389246e5a668c97fa"
ARMS = tuple(f"P{i}" for i in range(6))
HASH_IDENTITIES = ("commonUniverseSha256", "costPolicySha256", "executionPolicySha256", "returnBasisSha256")
IDENTITIES = (*HASH_IDENTITIES, "calendarVersion", "informationCutoffUtc")
QUALIFICATION_STATES = {"UNOBSERVED", "UNVALIDATED", "SOURCE_BLOCKED"}


def _require(condition, code):
    if not condition:
        raise ValueError(code)


def digest(value):
    return hashlib.sha256(core.canonical(value)).hexdigest()


def contract_reference():
    """Immutable proposal identity; PREPARED does not assert registration."""
    return {"studyId": "portfolio-d-p0-p5-comparison-v1", "status": "PREPARED",
            "sourceCommit": CANONICAL_COMMIT, "path": CANONICAL_PATH,
            "sha256": CANONICAL_SHA256, "scientificAdmission": False,
            "productionActivation": False}


def verify_contract_bytes(raw: bytes):
    """Verify a small already-acquired original contract, not its use rights.

    The complete byte pin prevents an adapter from changing an inconvenient
    source rule while retaining the original source name. No Git/network access.
    """
    _require(isinstance(raw, bytes) and hashlib.sha256(raw).hexdigest() == CANONICAL_SHA256,
             "CANONICAL_CONTRACT_BYTES_UNAVAILABLE_OR_CHANGED")
    contract = json.loads(raw)
    _require(contract.get("studyId") == contract_reference()["studyId"], "CANONICAL_STUDY_ID_MISMATCH")
    return {**contract_reference(), "byteIdentityVerified": True,
            "sourceRights": "NOT_INFERRED_FROM_BYTE_IDENTITY"}


def _refuse_actions(value):
    """Metadata adapters do not accept picks, weights, scores or result payloads."""
    if isinstance(value, dict):
        for key, inner in value.items():
            folded = str(key).lower().replace("_", "")
            _require(folded not in {"weights", "targetweights", "holdings", "positions", "picks", "scores",
                                    "factorvalues", "nav", "totalreturn", "excessreturn", "performance"},
                     "ACTION_OR_PERFORMANCE_PAYLOAD_NOT_METADATA")
            _refuse_actions(inner)
    elif isinstance(value, (list, tuple)):
        for inner in value:
            _refuse_actions(inner)


def adapt_synthetic_inputs(observation, arm_inputs):
    """Check cross-arm common identities before the existing receipt codec.

    Only synthetic metadata may enter this prototype. The receipt module owns
    weekly/calendar/timing/source-byte verification and append-only mechanics;
    this adapter adds the *joint* six-arm identity condition, not another writer.
    This returns the original observation shape and never grants ADMITTED.
    """
    core.scan_for_outcome_keys(observation)
    core.scan_for_outcome_keys(arm_inputs)
    _refuse_actions(observation)
    _refuse_actions(arm_inputs)
    _require(observation.get("dataKind") == "SYNTHETIC"
             and isinstance(observation.get("fixtureId"), str)
             and observation["fixtureId"].startswith("synthetic:"), "ACTUAL_RECEIPT_ADAPTATION_NOT_AUTHORIZED")
    _require(observation.get("region") in ("KR", "US"), "REGION_REQUIRED")
    universe = observation.get("commonUniverse")
    _require(isinstance(universe, list) and universe and universe == sorted(set(universe))
             and all(isinstance(name, str) and name for name in universe), "COMMON_UNIVERSE_REQUIRED")
    _require(observation.get("commonUniverseSha256") == digest(universe), "COMMON_UNIVERSE_IDENTITY_MISMATCH")
    _require(all(core.is_sha256(observation.get(key)) for key in HASH_IDENTITIES), "COMMON_POLICY_IDENTITIES_REQUIRED")
    _require(observation.get("calendarVersion") == replay_calendar.CALENDAR_VERSION, "COMMON_CALENDAR_VERSION_REQUIRED")
    cutoff = core.utc(observation["informationCutoffUtc"])
    qualification = observation.get("stockQualification", {})
    _require(set(qualification) == {f"S{i}" for i in range(1, 6)}
             and all(value in QUALIFICATION_STATES for value in qualification.values()),
             "UNREGISTERED_SCORE_ADMISSION_REFUSED")
    _require(isinstance(arm_inputs, list) and len(arm_inputs) == len(ARMS)
             and all(isinstance(row, dict) for row in arm_inputs)
             and {row.get("arm") for row in arm_inputs} == set(ARMS), "SIX_UNIQUE_ARM_IDENTITIES_REQUIRED")
    for row in arm_inputs:
        _require(set(row) == {"arm", *IDENTITIES}, "ARM_METADATA_SHAPE_INVALID")
        _require(all(row.get(key) == observation[key] for key in IDENTITIES), "CROSS_ARM_COMMON_IDENTITY_MISMATCH")
    sources = observation.get("sourceEvidence", [])
    _require(isinstance(sources, list) and sources, "SOURCE_EVIDENCE_REQUIRED")
    roles = [row.get("role") for row in sources]
    _require(all(isinstance(role, str) and role for role in roles) and len(set(roles)) == len(roles), "UNIQUE_SOURCE_ROLES_REQUIRED")
    for source in sources:
        raw = source.get("raw")
        _require(isinstance(raw, bytes) and core.is_sha256(source.get("sha256"))
                 and hashlib.sha256(raw).hexdigest() == source["sha256"], "SOURCE_BYTES_MISSING_OR_CHANGED")
        _require(core.is_git_sha(source.get("sourceCommit")), "SOURCE_COMMIT_REQUIRED")
        _require(source.get("dataKind") == "SYNTHETIC" and source.get("rightsStatus") == "SYNTHETIC_ONLY",
                 "SOURCE_RIGHTS_NOT_SYNTHETIC")
        _require(source.get("pitStatus") == "VERIFIED", "SOURCE_PIT_INCOMPLETE")
        _require(core.utc(source["availableAtUtc"]) <= cutoff and core.utc(source["vintageAtUtc"]) <= cutoff,
                 "SOURCE_NOT_AVAILABLE_AT_CUTOFF")
    return deepcopy(observation)


def adapt_foundation_plan(plan):
    """Project #317 plan identities and explicitly refuse estimand conversion.

    A valid plan digest is a local integrity check, not authentication that #317
    produced the plan, rights admission, or approval of any score. The incoming
    targets are never emitted. Even a valid #317 plan cannot become a canonical
    prospective receipt because funding/rebalance/missingness semantics differ.
    """
    _require(isinstance(plan, dict), "FOUNDATION_PLAN_REQUIRED")
    core.scan_for_outcome_keys(plan)
    _require(plan.get("contract") == "hierarchical-vs-direct-selection-comparison-v1"
             and plan.get("schemaVersion") == 1, "FOUNDATION_CONTRACT_MISMATCH")
    _require(plan.get("executionEnabled") is False and plan.get("deployable") is False,
             "EXECUTABLE_PLAN_REFUSED")
    body = {key: value for key, value in plan.items() if key != "planSha256"}
    _require(core.is_sha256(plan.get("planSha256")) and digest(body) == plan["planSha256"], "FOUNDATION_PLAN_DIGEST_MISMATCH")
    common = plan.get("common", {})
    _require(plan.get("commonSha256") == digest(common), "FOUNDATION_COMMON_DIGEST_MISMATCH")
    _require(all(core.is_sha256(common.get(key)) for key in ("costPolicySha256", "executionPolicySha256")),
             "FOUNDATION_POLICY_IDENTITIES_REQUIRED")
    model = common.get("costModel", {})
    _require(common["costPolicySha256"] == digest(model), "FOUNDATION_COST_POLICY_DIGEST_MISMATCH")
    universe = common.get("universe", [])
    _require(isinstance(universe, list) and universe and universe == sorted(set(universe)), "FOUNDATION_UNIVERSE_REQUIRED")
    paths = plan.get("paths", [])
    _require(isinstance(paths, list) and len(paths) == 6 and {row.get("path") for row in paths} == set(ARMS),
             "SIX_UNIQUE_ARM_IDENTITIES_REQUIRED")
    for row in paths:
        _require(row.get("universe") == universe and row.get("commonSha256") == plan["commonSha256"],
                 "CROSS_ARM_COMMON_IDENTITY_MISMATCH")
    return {"status": "INCOMPATIBLE", "canonicalRef": contract_reference(),
            "helperRef": {"sourceCommit": FOUNDATION_COMMIT, "path": FOUNDATION_PATH, "sha256": FOUNDATION_SHA256},
            "planSha256": plan["planSha256"], "commonUniverseSha256": digest(universe),
            "costPolicySha256": common["costPolicySha256"],
            "executionPolicySha256": common["executionPolicySha256"],
            "blockers": ["REBAlANCE_21_SESSIONS_VS_FIXED_ENTRY_TERMINAL_EXIT".upper(),
                         "FUNDING_AND_COST_ESTIMANDS_DIFFER", "ARM_BLOCK_VS_PAIRED_BLOCK_MISSINGNESS_DIFFER"],
            "receiptPreparationAllowed": False, "sourceAdmission": "NOT_INFERRED_FROM_DECLARATIONS"}


def inspect_operational_receipt(raw, *, expected_sha256):
    """Delegate the existing weekly codec; return identities, never allocation.

    The external byte identity covers metadata excluded from its business digest.
    A valid stored FINAL does not authorize a new receipt, score or investment.
    """
    _require(isinstance(raw, bytes) and core.is_sha256(expected_sha256)
             and hashlib.sha256(raw).hexdigest() == expected_sha256, "OPERATIONAL_BYTES_CHANGED")
    row = json.loads(raw)
    core.canonical(row)
    _require(isinstance(row, dict), "OPERATIONAL_OBJECT_REQUIRED")
    _require(row.get("schema") == "WEEKLY_DECISION_RECEIPT_V1"
             and row.get("policyVersion") == weekly.POLICY_VERSION
             and row.get("region") in ("KR", "US"), "OPERATIONAL_SCHEMA_INVALID")
    _require(row.get("receiptId") == weekly.receipt_id(row["region"], row["asOfDate"])
             and row.get("digest") == weekly.receipt_digest(row), "OPERATIONAL_CODEC_DIGEST_INVALID")
    _require(weekly.receipt_session_error(row) is None and row.get("weekStatus") == "FINAL_WEEKLY",
             "OPERATIONAL_FINAL_SESSION_UNVERIFIED")
    return {"region": row["region"], "signalDate": row["asOfDate"], "receiptId": row["receiptId"],
            "digest": row["digest"], "byteSha256": expected_sha256, "readOnly": True,
            "sourceAdmission": "NOT_INFERRED_FROM_RECEIPT", "activationEnabled": False}
