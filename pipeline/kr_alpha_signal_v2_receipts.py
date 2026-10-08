"""kr-alpha-signal-v2 — the weekly PROSPECTIVE receipt (contract and synthetic tests only; nothing is written, scheduled or authorized here).

One immutable receipt per weekly KR decision session, written after that session's close and before the next session opens, appended to a JSON
Lines ledger and never rewritten. Storage, digest and evidence class are those of `prospective_receipt_core` (the format the three existing study
receipts use). A receipt carries what the signal knew and decided, never what happened next; outcomes are separate records built only after the
horizon matures (`prospective_receipt_core.build_outcome_record`).

States, in the order they are decided:
  BLOCKED                  PIT coverage below the floor: identities and counts only, no per-name signal, no forecast, no weights;
  NOT_READY                signal computed, no authorized calibrated forecast: research-only signal records, no weights;
  NO_ELIGIBLE_OPPORTUNITY  forecast present, nothing clears cost and uncertainty: zero names, the whole book in the declared fallback;
  CANDIDATE_PORTFOLIO      one to five names at one slot each, unused slots in the declared fallback.

No receipt is prospective evidence until the final design is merged AND an authorization is registered below. None is registered.
"""
from __future__ import annotations

import math

import pandas as pd

from . import kr_alpha_signal_v2 as S
from . import prospective_receipt_core as CORE

SCHEMA_VERSION = 1
EVIDENCE_CLASS = CORE.EVIDENCE_CLASS
KEY_FIELDS = ("studyId", "signalDate")
DECISION_STATES = ("BLOCKED", "NOT_READY", "NO_ELIGIBLE_OPPORTUNITY", "CANDIDATE_PORTFOLIO")
DATA_IDENTITY_KEYS = ("pitFeatureSnapshot", "universeSnapshot", "industryMembership")
REQUIRED = ("schemaVersion", "studyId", "designVersion", "designDigest", "specSha256", "codeIdentity", "authorization", "signalDate", "executionDate",
            "createdAtUtc", "dataSnapshotIdentity", "trainingCutoff", "benchmark", "evaluationHorizons", "coverage", "signal", "forecast", "decision",
            "costsAssumedBps", "researchOnly", "productionEffect", "evidenceClass")
TOLERANCE = 1e-9

# The authorization that makes receipts prospective evidence: {"specSha256", "mergeCommitSha", "mergedAtUtc"} of the merged, frozen design.
# None exists. A live writer must call `require_registered_authorization()`, which refuses until a later, reviewed change registers one.
REGISTERED_AUTHORIZATION = None


def require_registered_authorization():
    if REGISTERED_AUTHORIZATION is None:
        raise ValueError("KR_ALPHA_SIGNAL_V2_NOT_AUTHORIZED: no frozen design has been merged and authorized for prospective receipts")
    return dict(REGISTERED_AUTHORIZATION)


def _check_identities(spec_sha256, code_identity, data_identity, authorization):
    if not CORE.is_sha256(spec_sha256):
        raise ValueError("SPEC_IDENTITY_REQUIRED")
    if not CORE.is_git_sha(code_identity.get("commitSha")) or not code_identity.get("files") \
            or not all(CORE.is_sha256(v) for v in code_identity["files"].values()):
        raise ValueError("CODE_IDENTITY_REQUIRED")
    if sorted(data_identity) != sorted(DATA_IDENTITY_KEYS) or not all(CORE.is_sha256(v) for v in data_identity.values()):
        raise ValueError("DATA_SNAPSHOT_IDENTITY_REQUIRED")
    if not authorization or authorization.get("specSha256") != spec_sha256 or not CORE.is_git_sha(authorization.get("mergeCommitSha")) \
            or not authorization.get("mergedAtUtc"):
        raise ValueError("AUTHORIZATION_DOES_NOT_MATCH_THE_SPEC")


def build_receipt(*, rows, signal_date, created_at_utc, now_utc, spec_sha256, code_identity, data_identity, authorization, forecasts=None,
                  previous_holdings=(), fallback=S.PRIMARY_FALLBACK):
    """Build and seal one receipt from one signal date's PIT rows. Everything the decision depends on is recomputed here from `rows` and
    `forecasts`; no state, weight or score is accepted from the caller."""
    _check_identities(spec_sha256, code_identity, data_identity, authorization)
    if not CORE.is_weekly_decision_session(signal_date):
        raise ValueError("SIGNAL_DATE_IS_NOT_A_WEEKLY_DECISION_SESSION")
    execution = CORE.check_timing(signal_date=signal_date, created_at_utc=created_at_utc, now_utc=now_utc,
                                  merged_at_utc=authorization["mergedAtUtc"])
    records = S.cross_section(rows, signal_date)
    decision = S.decide(records, signal_date=signal_date, forecasts=forecasts, previous_holdings=previous_holdings, fallback=fallback)
    blocked = decision["status"] == "BLOCKED"
    forecast_block = None if (blocked or forecasts is None) else {
        k: forecasts[k] for k in ("modelId", "modelSha256", "trainingCutoff", "trainingTargetLastExitDate", "calibrationStatus", "names")}
    receipt = {"schemaVersion": SCHEMA_VERSION, "studyId": S.STUDY, "designVersion": S.DESIGN_VERSION, "designDigest": S.design_digest(),
               "specSha256": spec_sha256, "codeIdentity": {"commitSha": code_identity["commitSha"], "files": dict(sorted(code_identity["files"].items()))},
               "authorization": {"specSha256": authorization["specSha256"], "mergeCommitSha": authorization["mergeCommitSha"],
                                 "mergedAtUtc": authorization["mergedAtUtc"],
                                 "firstProspectiveSession": str(CORE.first_prospective_session(authorization["mergedAtUtc"]).date())},
               "signalDate": str(pd.Timestamp(signal_date).normalize().date()),
               "executionDate": str(execution.date()), "createdAtUtc": created_at_utc,
               "dataSnapshotIdentity": dict(sorted(data_identity.items())),
               "trainingCutoff": forecast_block["trainingCutoff"] if forecast_block else None,
               "benchmark": S.BENCHMARK, "evaluationHorizons": list(S.EVALUATION_HORIZONS), "coverage": S.coverage(records),
               "signal": None if blocked else records, "forecast": forecast_block,
               "decision": {"status": decision["status"], "reasons": decision["reasons"], "fallback": decision["fallback"],
                            "weights": decision["weights"], "fallbackWeight": decision["fallbackWeight"], "candidates": decision["candidates"],
                            "previousHoldings": sorted(previous_holdings), "maxHoldings": S.MAX_HOLDINGS, "slotWeight": S.SLOT_WEIGHT,
                            "maxNamesPerIndustry": S.MAX_NAMES_PER_INDUSTRY, "seMultiple": S.SE_MULTIPLE},
               "costsAssumedBps": {"stock": dict(S.STOCK_COSTS_BPS), "passiveLeg": dict(S.PASSIVE_LEG_COSTS_BPS),
                                   "roundTripUsedForEntry": S.round_trip_cost(fallback) * 10000.0},
               "researchOnly": True, "productionEffect": "NONE", "evidenceClass": EVIDENCE_CLASS}
    receipt["receiptSha256"] = CORE.receipt_digest(receipt)
    validate_receipt(receipt)
    return receipt


def validate_receipt(receipt):
    """Structural and semantic checks a reader re-runs on every row. A blocked or not-ready receipt can carry no weight; weights must equal the
    registered slot rule; nothing in the receipt may name an outcome."""
    missing = [k for k in REQUIRED + ("receiptSha256",) if k not in receipt]
    if missing:
        raise ValueError("RECEIPT_FIELD_MISSING: " + ",".join(missing))
    extra = sorted(set(receipt) - set(REQUIRED) - {"receiptSha256"})
    if extra:
        raise ValueError("RECEIPT_FIELD_NOT_IN_CONTRACT: " + ",".join(extra))
    if receipt["receiptSha256"] != CORE.receipt_digest(receipt):
        raise ValueError("RECEIPT_DIGEST_MISMATCH")
    if receipt["studyId"] != S.STUDY or receipt["evidenceClass"] != EVIDENCE_CLASS or receipt["schemaVersion"] != SCHEMA_VERSION:
        raise ValueError("RECEIPT_IDENTITY_MISMATCH")
    if receipt["researchOnly"] is not True or receipt["productionEffect"] != "NONE":
        raise ValueError("RECEIPT_MUST_BE_RESEARCH_ONLY")
    if receipt["authorization"]["specSha256"] != receipt["specSha256"]:
        raise ValueError("AUTHORIZATION_DOES_NOT_MATCH_THE_SPEC")
    if receipt["signalDate"] < receipt["authorization"]["firstProspectiveSession"]:
        raise ValueError("SIGNAL_BEFORE_PROSPECTIVE_ELIGIBILITY")
    CORE.scan_for_outcome_keys({k: v for k, v in receipt.items() if k != "receiptSha256"})
    decision = receipt["decision"]
    status = decision["status"]
    if status not in DECISION_STATES:
        raise ValueError("UNKNOWN_DECISION_STATE")
    if status in ("BLOCKED", "NOT_READY"):
        if decision["weights"] is not None or decision["fallbackWeight"] is not None or decision["candidates"] or receipt["forecast"] is not None:
            raise ValueError("NON_ACTIONABLE_RECEIPT_CARRIES_A_DECISION")
        if status == "BLOCKED" and receipt["signal"] is not None:
            raise ValueError("BLOCKED_RECEIPT_CARRIES_A_SIGNAL")
        return True
    weights = decision["weights"]
    if receipt["forecast"] is None or weights is None:
        raise ValueError("ACTIONABLE_STATE_WITHOUT_A_FORECAST")
    if len(weights) > S.MAX_HOLDINGS or any(abs(w - S.SLOT_WEIGHT) > TOLERANCE for w in weights.values()):
        raise ValueError("WEIGHTS_VIOLATE_THE_SLOT_RULE")
    if abs(decision["fallbackWeight"] - (1.0 - math.fsum(weights.values()))) > TOLERANCE:
        raise ValueError("FALLBACK_WEIGHT_INCONSISTENT")
    if (status == "NO_ELIGIBLE_OPPORTUNITY") != (not weights):
        raise ValueError("STATE_DISAGREES_WITH_WEIGHTS")
    states = {r["ticker"]: r["state"] for r in receipt["signal"]}
    if any(states.get(t) != "CHEAP_CONFIRMED" for t in weights):
        raise ValueError("HELD_NAME_IS_NOT_CHEAP_CONFIRMED")
    return True


def read_ledger(path):
    return CORE.read_ledger(path, validate_receipt)


def append_receipt(path, receipt):
    return CORE.append(path, receipt, validate=validate_receipt, key_fields=KEY_FIELDS)


def build_outcome_record(receipt, *, horizon, as_of, name_outcomes, created_at_utc):
    """The only route from a receipt to an outcome: a separate record, after maturity, keyed by the receipt digest."""
    if horizon not in S.EVALUATION_HORIZONS:
        raise ValueError("UNREGISTERED_HORIZON")
    return CORE.build_outcome_record(receipt, validate=validate_receipt, horizon=horizon, as_of=as_of, name_outcomes=name_outcomes,
                                     created_at_utc=created_at_utc, weights_field=("decision", "weights"))
