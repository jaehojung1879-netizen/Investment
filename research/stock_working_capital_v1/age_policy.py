"""Explicit pending scientific policy; 550 remains a diagnostic reference only."""
import json
from pathlib import Path


def pending_policy():
    raw = json.loads((Path(__file__).parent / "fiscal-age-decision-v1.json").read_text())
    if raw["selectedPolicy"] is not None or raw["legacyReferenceIsPreregistered"]:
        raise ValueError("OWNER_POLICY_REGISTRATION_REQUIRES_SEPARATE_AUDIT")
    return {"status": raw["status"], "referenceDays": raw["legacyDiagnosticReferenceDays"], "admissionEnabled": False}


def synthetic_policy(days=550):
    if type(days) is not int or days < 1:
        raise ValueError("INVALID_SYNTHETIC_FISCAL_AGE")
    return {"status": "SYNTHETIC_TEST_POLICY_ONLY", "referenceDays": days, "admissionEnabled": True}
