"""RP1 Track C — KR C0-C3 risk-state receipt PREVIEW (no ledger, no collection, no US).

Maps already-observed layer states (SLOW, TRANSITION, FAST) at a weekly decision date to the frozen `kr_market_risk_model` multiplier of each
candidate C0-C3, by calling `kr_market_risk_model.multiplier` itself. Nothing here adds a rule, window, threshold or multiplier, and it does not
authorize, dispatch or read anything of the US C1 execution (owner-only). Layer states are INPUTS; this module fetches nothing.

A PREVIEW is not a receipt: `evidenceClass = PROSPECTIVE_PAPER_PREVIEW`, never appended to a ledger here, no timing or authorization check.
A multiplier is None when the missing layers could change the answer; the sealed model's "hold the previous target" needs a path, so the preview
reports the undetermined cell instead of inventing a held value. Multipliers describe a risk state only; no weight, order or portfolio.
"""
from __future__ import annotations

import json

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


def _state(value, layer):
    if value is None or (isinstance(value, float) and value != value):
        return None
    if int(value) != value or int(value) not in K.STATE_VALUES[layer.upper()]:
        raise ValueError("STATE_OUTSIDE_FROZEN_DOMAIN: " + layer)
    return int(value)


def build_preview(signal_date, slow, transition, fast):
    day = pd.Timestamp(signal_date).normalize()
    if not P.is_weekly_decision_session(day):
        raise ValueError("SIGNAL_DATE_IS_NOT_A_WEEKLY_DECISION_SESSION")
    layers = {k: _state(v, k) for k, v in zip(LAYER_KEYS, (slow, transition, fast))}
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
    missing = [k for k in REQUIRED + ("receiptSha256",) if k not in receipt]
    if missing:
        raise ValueError("PREVIEW_FIELD_MISSING: " + ",".join(missing))
    if receipt["evidenceClass"] != EVIDENCE_CLASS or receipt["ledgerWritten"] is not False or receipt["region"] != REGION:
        raise ValueError("PREVIEW_MUST_NOT_CLAIM_LEDGER_EVIDENCE")
    if receipt["receiptSha256"] != P.receipt_digest(receipt):
        raise ValueError("PREVIEW_DIGEST_MISMATCH")
    if set(receipt["multipliers"]) != set(K.CANDIDATE_ORDER):
        raise ValueError("CANDIDATE_SET_CHANGED")
    for c, m in receipt["multipliers"].items():
        if m is not None and m not in K.LEVELS:
            raise ValueError("MULTIPLIER_OUTSIDE_FROZEN_LEVELS: " + c)
    P.scan_for_outcome_keys(receipt)
    json.dumps(receipt, allow_nan=False)
    return True
