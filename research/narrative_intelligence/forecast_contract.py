"""Inactive forecast receipt/scoring primitives. No live registration or writer.

Forecasts are distinct from other people's statements. A hash establishes
payload identity, not when it was observed; trusted publication/commit evidence
and separate authorization are necessary before using real records.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone

from .ledger import number

REQUIRED = {
    "id", "model", "as_of", "target_end", "target", "unit", "kind",
    "prediction", "baseline", "baseline_source", "evidence", "resolution",
    "mechanism", "alternative", "missing_policy",
}


def utc(value):
    if not isinstance(value, str):
        raise ValueError("CLOCK_REQUIRED")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("OFFSET_REQUIRED")
    return dt.astimezone(timezone.utc)


def digest(payload):
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                         allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate(payload):
    if set(payload) != REQUIRED:
        raise ValueError("FORECAST_SCHEMA")
    start, end = utc(payload["as_of"]), utc(payload["target_end"])
    if start >= end:
        raise ValueError("TARGET_NOT_FUTURE")
    for key in ("id", "model", "target", "unit", "baseline_source", "mechanism", "alternative"):
        if not isinstance(payload[key], str) or not payload[key].strip():
            raise ValueError("MISSING_FORECAST_FIELD")
    if payload["missing_policy"] != "UNRESOLVED_NO_IMPUTATION":
        raise ValueError("MISSING_POLICY")
    if payload["kind"] not in ("POINT", "BINARY_PROBABILITY"):
        raise ValueError("UNKNOWN_FORECAST_KIND")
    for key in ("prediction", "baseline"):
        val = number(payload[key])
        if payload["kind"] == "BINARY_PROBABILITY" and not 0 <= val <= 1:
            raise ValueError("PROBABILITY_RANGE")
    seen = set()
    if not isinstance(payload["evidence"], list) or not payload["evidence"]:
        raise ValueError("EVIDENCE_REQUIRED")
    for item in payload["evidence"]:
        if set(item) != {"id", "available_at"} or not isinstance(item["id"], str) or not item["id"].strip():
            raise ValueError("EVIDENCE_SCHEMA")
        if item["id"] in seen:
            raise ValueError("DUPLICATE_EVIDENCE")
        seen.add(item["id"])
        if utc(item["available_at"]) > start:
            raise ValueError("FUTURE_EVIDENCE")
    if payload["baseline_source"] not in seen:
        raise ValueError("BASELINE_EVIDENCE_REQUIRED")
    resolution = payload["resolution"]
    if set(resolution) != {"source", "vintage", "definition"} or not all(
        isinstance(v, str) and v.strip() for v in resolution.values()
    ):
        raise ValueError("RESOLUTION_RULE_REQUIRED")
    return payload


def candidate_receipt(payload):
    """Candidate only; no claim of real timestamp, registration or authorization."""
    validate(payload)
    return {
        "schema": "NARRATIVE_CANDIDATE_FORECAST_V1", "status": "DESIGN_ONLY",
        "payload": payload, "sha256": digest(payload),
        "registration_authorized": False, "investment_evaluation_authorized": False,
    }


def score_synthetic(receipt, actual):
    """Test scoring arithmetic only. Production/real forecast resolution is not implemented."""
    if receipt["status"] != "DESIGN_ONLY" or receipt["registration_authorized"] is not False:
        raise ValueError("UNAUTHORIZED_RECEIPT")
    payload = validate(receipt["payload"])
    if receipt["sha256"] != digest(payload):
        raise ValueError("FORECAST_HASH")
    if actual.get("synthetic") is not True:
        raise ValueError("SYNTHETIC_ONLY")
    if actual["forecast_id"] != payload["id"]:
        raise ValueError("UNMATCHED_FORECAST")
    for key in ("target", "unit"):
        if actual[key] != payload[key]:
            raise ValueError("UNMATCHED_TARGET")
    for key in ("source", "vintage"):
        if actual[key] != payload["resolution"][key]:
            raise ValueError("UNMATCHED_RESOLUTION")
    if utc(actual["available_at"]) < utc(payload["target_end"]):
        raise ValueError("PREMATURE_RESOLUTION")
    value = actual["value"]
    if value is None:
        return {"status": "UNRESOLVED", "model_loss": None, "baseline_loss": None}
    value = number(value)
    if payload["kind"] == "BINARY_PROBABILITY":
        if value not in (0, 1):
            raise ValueError("BINARY_OUTCOME_REQUIRED")
        model_loss = (payload["prediction"] - value) ** 2
        baseline_loss = (payload["baseline"] - value) ** 2
        metric = "BRIER"
    else:
        model_loss = abs(payload["prediction"] - value)
        baseline_loss = abs(payload["baseline"] - value)
        metric = "ABSOLUTE_ERROR"
    if not math.isfinite(model_loss) or not math.isfinite(baseline_loss):
        raise ValueError("LOSS_NOT_FINITE")
    return {"status": "SYNTHETIC_SCORED", "metric": metric,
            "model_loss": model_loss, "baseline_loss": baseline_loss,
            "improvement": baseline_loss - model_loss}
