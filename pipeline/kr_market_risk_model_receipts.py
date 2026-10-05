"""KR market risk model v1 — the PROSPECTIVE receipt contract (designed and tested here; nothing is written or scheduled by this change).

Historical results of this model are development evidence on outcome-exposed history. The only route to real evidence is a prospective record made
BEFORE the outcome exists: on every future decision date one immutable receipt stores the exact inputs, the three layer states, every candidate's
multiplier and the final equity risk multiplier, under the model version, the frozen spec hash and the code identity. Receipts are appended to a JSON
Lines ledger and never rewritten; a key that already exists, an out-of-order date or an altered earlier row refuses the whole append. A receipt is
evaluated only after its horizon has matured on the KR calendar.

Recording ALL candidates' multipliers (not only the nominated one) keeps the prospective record independent of the development nomination.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pandas as pd

from . import kr_market_risk_anatomy as M
from . import kr_market_risk_model as K

SCHEMA_VERSION = 1
LAYER_FIELDS = ("slow", "transition", "fast")
REQUIRED = ("schemaVersion", "studyId", "modelVersion", "specSha256", "codeIdentity", "signalDate", "executionDate", "createdAtUtc", "inputIdentities",
            "layerInputs", "states", "candidateMultipliers", "heldForMissingState", "finalArchitecture", "finalEquityRiskMultiplier", "nominationSource", "evaluationHorizons",
            "evidenceClass")
EVIDENCE_CLASS = "PROSPECTIVE_PAPER"
EVALUATION_HORIZONS = (21, 63, 126)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def receipt_digest(receipt):
    body = {k: v for k, v in receipt.items() if k != "receiptSha256"}
    return hashlib.sha256(canonical(body)).hexdigest()


def _state(value, domain):
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return None
    if int(value) not in domain:
        raise ValueError("STATE_OUTSIDE_FROZEN_DOMAIN")
    return int(value)


def build_receipt(*, signal_date, input_identities, layer_inputs, states, spec_sha256, code_identity, created_at_utc, final_architecture,
                  nomination_source, previous_multipliers=None):
    """One receipt. `states` = {'slow','transition','fast'} (None when undefined). Every candidate's multiplier comes from the frozen rule; an
    undefined multiplier holds `previous_multipliers[candidate]` exactly as the historical replay does, and the hold is recorded."""
    if final_architecture not in K.CANDIDATE_ORDER:
        raise ValueError("UNKNOWN_ARCHITECTURE")
    if not input_identities or any(not isinstance(v, str) or len(v) != 64 for v in input_identities.values()):
        raise ValueError("INPUT_IDENTITY_REQUIRED")
    s = {"slow": _state(states.get("slow"), K.STATE_VALUES["SLOW"]), "transition": _state(states.get("transition"), K.STATE_VALUES["TRANSITION"]),
         "fast": _state(states.get("fast"), K.STATE_VALUES["FAST"])}
    multipliers, held = {}, {}
    for cid in K.CANDIDATE_ORDER:
        m = K.multiplier(cid, s["slow"], s["transition"], s["fast"])
        held[cid] = m is None
        if m is None:
            if not previous_multipliers or previous_multipliers.get(cid) is None:
                raise ValueError("STATE_UNAVAILABLE_WITHOUT_A_PREVIOUS_TARGET: " + cid)
            m = previous_multipliers[cid]
        multipliers[cid] = m
    day = pd.Timestamp(signal_date)
    calendar = M.kr_sessions(str(day.date()), str((day + pd.Timedelta(days=20)).date()))
    if len(calendar) < 2 or calendar[0] != day:
        raise ValueError("SIGNAL_DATE_IS_NOT_A_KR_SESSION")
    receipt = {"schemaVersion": SCHEMA_VERSION, "studyId": K.STUDY, "modelVersion": K.MODEL_VERSION, "specSha256": spec_sha256, "codeIdentity": dict(code_identity),
               "signalDate": str(day.date()), "executionDate": str(calendar[1].date()), "createdAtUtc": created_at_utc,
               "inputIdentities": dict(sorted(input_identities.items())), "layerInputs": dict(layer_inputs), "states": s,
               "candidateMultipliers": multipliers, "heldForMissingState": held, "finalArchitecture": final_architecture,
               "finalEquityRiskMultiplier": multipliers[final_architecture], "nominationSource": nomination_source,
               "evaluationHorizons": list(EVALUATION_HORIZONS), "evidenceClass": EVIDENCE_CLASS}
    receipt["receiptSha256"] = receipt_digest(receipt)
    validate_receipt(receipt)
    return receipt


def validate_receipt(receipt):
    missing = [k for k in REQUIRED + ("receiptSha256",) if k not in receipt]
    if missing:
        raise ValueError("RECEIPT_FIELD_MISSING: " + ",".join(missing))
    if receipt["receiptSha256"] != receipt_digest(receipt):
        raise ValueError("RECEIPT_DIGEST_MISMATCH")
    if receipt["studyId"] != K.STUDY or receipt["modelVersion"] != K.MODEL_VERSION or receipt["evidenceClass"] != EVIDENCE_CLASS:
        raise ValueError("RECEIPT_IDENTITY_MISMATCH")
    values = list(receipt["candidateMultipliers"].values()) + [receipt["finalEquityRiskMultiplier"]]
    if any(v not in K.LEVELS for v in values) or sorted(receipt["candidateMultipliers"]) != sorted(K.CANDIDATE_ORDER):
        raise ValueError("RECEIPT_MULTIPLIER_OUTSIDE_FROZEN_VOCABULARY")
    if receipt["finalEquityRiskMultiplier"] != receipt["candidateMultipliers"][receipt["finalArchitecture"]]:
        raise ValueError("FINAL_MULTIPLIER_DIFFERS_FROM_ITS_ARCHITECTURE")
    return True


def read_ledger(path):
    path = Path(path)
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    for row in rows:
        validate_receipt(row)
    return rows


def append_receipt(path, receipt):
    """Append-only. Refuses a duplicate (modelVersion, signalDate), a signal date not after the last one, a spec different from the ledger's, and any
    existing row whose digest no longer verifies. Existing bytes are never rewritten: the new row is appended to the end of the file."""
    validate_receipt(receipt)
    rows = read_ledger(path)
    keys = {(r["modelVersion"], r["signalDate"]) for r in rows}
    if (receipt["modelVersion"], receipt["signalDate"]) in keys:
        raise ValueError("RECEIPT_ALREADY_EXISTS")
    if rows and pd.Timestamp(receipt["signalDate"]) <= pd.Timestamp(rows[-1]["signalDate"]):
        raise ValueError("RECEIPT_OUT_OF_ORDER")
    if rows and receipt["specSha256"] != rows[0]["specSha256"]:
        raise ValueError("RECEIPT_SPEC_CHANGED_WITHIN_A_LEDGER")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as stream:
        stream.write(canonical(receipt) + b"\n")
    return receipt["receiptSha256"]


def matured(receipt, as_of, horizon):
    """True only once `horizon` KR sessions after the execution session have closed on or before `as_of`. Before that, no outcome may be computed."""
    if horizon not in EVALUATION_HORIZONS:
        raise ValueError("UNREGISTERED_HORIZON")
    start = pd.Timestamp(receipt["executionDate"])
    sessions = M.kr_sessions(str(start.date()), str(pd.Timestamp(as_of).date()))
    return len(sessions) - 1 >= horizon
