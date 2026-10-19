"""RP1 Track C — KR C0-C3 risk-state receipt PREVIEW (no ledger, no collection, no US).

Maps already-observed layer states (SLOW, TRANSITION, FAST) at a weekly decision date to the frozen `kr_market_risk_model` multiplier of each
candidate C0-C3, by calling `kr_market_risk_model.multiplier` itself. Nothing here adds a rule, window, threshold or multiplier, and it does not
authorize, dispatch or read anything of the US C1 execution (owner-only). Layer states are INPUTS; this module fetches nothing.

A PREVIEW is not a receipt: `evidenceClass = PROSPECTIVE_PAPER_PREVIEW`, never appended to a ledger here, no timing or authorization check.
A multiplier is None when the missing layers could change the answer; the sealed model's "hold the previous target" needs a path, so the preview
reports the undetermined cell instead of inventing a held value. Multipliers describe a risk state only; no weight, order or portfolio.
"""
from __future__ import annotations

import datetime as dt
import json
from numbers import Real

import pandas as pd

from . import kr_market_risk_model as K
from . import prospective_receipt_core as P

STUDY = "rp1-c-kr-risk-state-receipt-preview-v1"
SCHEMA_VERSION = 1
EVIDENCE_CLASS = "PROSPECTIVE_PAPER_PREVIEW"
REGION = "KR"
LAYER_KEYS = ("slow", "transition", "fast")
REQUIRED = ("schemaVersion", "studyId", "evidenceClass", "region", "signalDate", "layers", "multipliers", "undeterminedCandidates",
            "ledgerWritten", "modelVersion")


def _state(value, layer, *, allow_nan=False):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("STATE_OUTSIDE_FROZEN_DOMAIN: " + layer)
    # The builder retains its existing NaN -> JSON null normalization. Received
    # receipts must already be finite JSON states or explicit null.
    if allow_nan and value != value:
        return None
    if value not in K.STATE_VALUES[layer.upper()]:
        raise ValueError("STATE_OUTSIDE_FROZEN_DOMAIN: " + layer)
    return int(value)


def build_preview(signal_date, slow, transition, fast):
    day = pd.Timestamp(signal_date).normalize()
    if not P.is_weekly_decision_session(day):
        raise ValueError("SIGNAL_DATE_IS_NOT_A_WEEKLY_DECISION_SESSION")
    layers = {k: _state(v, k, allow_nan=True) for k, v in zip(LAYER_KEYS, (slow, transition, fast))}
    mult = {c: K.multiplier(c, layers["slow"], layers["transition"], layers["fast"]) for c in K.CANDIDATE_ORDER}
    receipt = {"schemaVersion": SCHEMA_VERSION, "studyId": STUDY, "evidenceClass": EVIDENCE_CLASS, "region": REGION,
               "signalDate": str(day.date()), "layers": layers, "multipliers": mult,
               "undeterminedCandidates": [c for c, m in mult.items() if m is None], "ledgerWritten": False,
               "modelVersion": K.MODEL_VERSION}
    P.scan_for_outcome_keys(receipt)
    receipt["receiptSha256"] = P.receipt_digest(receipt)
    validate_preview(receipt)
    return receipt


def validate_preview(receipt):
    """Validate an external preview independently of its producer/digest.

    A digest detects accidental alteration; it is not authentication and cannot
    establish agreement with the frozen model or the original observations.
    """
    if not isinstance(receipt, dict):
        raise ValueError("PREVIEW_MUST_BE_AN_OBJECT")
    fields = REQUIRED + ("receiptSha256",)
    missing = [k for k in fields if k not in receipt]
    if missing:
        raise ValueError("PREVIEW_FIELD_MISSING: " + ",".join(missing))
    if set(receipt) != set(fields):
        raise ValueError("PREVIEW_FIELD_SET_CHANGED")
    if (not isinstance(receipt["schemaVersion"], int) or isinstance(receipt["schemaVersion"], bool)
            or receipt["schemaVersion"] != SCHEMA_VERSION):
        raise ValueError("PREVIEW_SCHEMA_VERSION_CHANGED")
    if not isinstance(receipt["studyId"], str) or receipt["studyId"] != STUDY:
        raise ValueError("PREVIEW_STUDY_ID_CHANGED")
    if not isinstance(receipt["modelVersion"], str) or receipt["modelVersion"] != K.MODEL_VERSION:
        raise ValueError("PREVIEW_MODEL_VERSION_CHANGED")
    if (not isinstance(receipt["evidenceClass"], str) or receipt["evidenceClass"] != EVIDENCE_CLASS
            or receipt["ledgerWritten"] is not False
            or not isinstance(receipt["region"], str) or receipt["region"] != REGION):
        raise ValueError("PREVIEW_MUST_NOT_CLAIM_LEDGER_EVIDENCE")

    signal = receipt["signalDate"]
    if not isinstance(signal, str):
        raise ValueError("SIGNAL_DATE_MUST_BE_AN_ISO_DATE")
    try:
        day = dt.date.fromisoformat(signal)
    except ValueError as exc:
        raise ValueError("SIGNAL_DATE_MUST_BE_AN_ISO_DATE") from exc
    if day.isoformat() != signal:
        raise ValueError("SIGNAL_DATE_MUST_BE_AN_ISO_DATE")
    if not P.is_weekly_decision_session(pd.Timestamp(day)):
        raise ValueError("SIGNAL_DATE_IS_NOT_A_WEEKLY_DECISION_SESSION")

    layers = receipt["layers"]
    if not isinstance(layers, dict) or set(layers) != set(LAYER_KEYS):
        raise ValueError("LAYER_SET_CHANGED")
    states = {layer: _state(layers[layer], layer) for layer in LAYER_KEYS}
    actual = receipt["multipliers"]
    if not isinstance(actual, dict) or set(actual) != set(K.CANDIDATE_ORDER):
        raise ValueError("CANDIDATE_SET_CHANGED")
    for c, m in actual.items():
        if m is not None and (isinstance(m, bool) or not isinstance(m, (int, float)) or m not in K.LEVELS):
            raise ValueError("MULTIPLIER_OUTSIDE_FROZEN_LEVELS: " + c)
    undetermined = receipt["undeterminedCandidates"]
    if not isinstance(undetermined, list) or any(not isinstance(c, str) for c in undetermined):
        raise ValueError("UNDETERMINED_CANDIDATES_INVALID")
    # Strict schema/type checks precede canonicalization: malformed containers,
    # non-finite numbers and non-JSON scalars must produce a validation error.
    try:
        json.dumps(receipt, allow_nan=False)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("PREVIEW_MUST_BE_FINITE_JSON") from exc
    if not P.is_sha256(receipt["receiptSha256"]) or receipt["receiptSha256"] != P.receipt_digest(receipt):
        raise ValueError("PREVIEW_DIGEST_MISMATCH")

    expected = {c: K.multiplier(c, states["slow"], states["transition"], states["fast"])
                for c in K.CANDIDATE_ORDER}
    if actual != expected:
        raise ValueError("MULTIPLIERS_DISAGREE_WITH_FROZEN_MODEL")
    if undetermined != [c for c in K.CANDIDATE_ORDER if expected[c] is None]:
        raise ValueError("UNDETERMINED_CANDIDATES_DISAGREE_WITH_FROZEN_MODEL")
    P.scan_for_outcome_keys(receipt)
    return True
