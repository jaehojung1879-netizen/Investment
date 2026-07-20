"""Validated production-state snapshots used by rank buffers and prior regime.

The repository artifact is deliberately not a state source: it may be a seed or
synthetic preview.  Only ``state/latest.json`` written after production
validation and a successful Pages deployment is accepted.
"""
from __future__ import annotations

import json
from pathlib import Path


def _status(reason: str) -> dict:
    return {"available": False, "reason": reason}


def load_prior_state(path: str | Path | None, *, expected_schema_version: str,
                     expected_model_version: str) -> tuple[dict, dict]:
    """Load a compatible, validated live snapshot or return an explicit reason."""
    if not path:
        return {}, _status("state_path_not_configured")
    state_path = Path(path)
    if not state_path.exists():
        return {}, _status("state_file_missing")
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}, _status("state_file_invalid")
    if state.get("schemaVersion") != expected_schema_version:
        return {}, _status("schema_version_mismatch")
    if state.get("modelVersion") != expected_model_version:
        return {}, _status("model_version_mismatch")
    if state.get("dataMode") != "live" or state.get("seed") or state.get("stale"):
        return {}, _status("non_live_state")
    if not (state.get("productionValidation") or {}).get("passed"):
        return {}, _status("production_validation_missing")
    holdings = state.get("holdingsByRegion")
    if not isinstance(holdings, dict):
        return {}, _status("holdings_missing")
    return state, {"available": True, "reason": None}


def snapshot_from_payload(payload: dict, *, validation_passed: bool) -> dict:
    """Create the minimal non-recursive state written after a good deployment."""
    provenance = payload.get("provenance") or {}
    data_mode = payload.get("dataMode") or provenance.get("dataMode")
    if data_mode != "live" or payload.get("seed") or payload.get("stale"):
        raise ValueError("only live artifacts may become production state")
    if not validation_passed:
        raise ValueError("production validation must pass before state publication")
    regions = ((payload.get("longTerm") or {}).get("regions") or {})
    holdings = {
        region: list((blob or {}).get("holdings") or [])
        for region, blob in regions.items()
    }
    macro = ((payload.get("macroRegime") or {}).get("regime"))
    return {
        "schemaVersion": payload.get("schemaVersion") or provenance.get("schemaVersion"),
        "modelVersion": payload.get("modelVersion") or provenance.get("modelVersion"),
        "buildCommitSha": provenance.get("buildCommitSha"),
        "generatedAt": payload.get("generatedAt") or provenance.get("generatedAt"),
        "marketAsOf": provenance.get("marketAsOf") or (payload.get("meta") or {}).get("latestDataDate"),
        "macroRegime": macro,
        "holdingsByRegion": holdings,
        "dataMode": "live",
        "seed": False,
        "stale": False,
        "productionValidation": {
            "passed": True,
            "validatedAt": payload.get("generatedAt") or provenance.get("generatedAt"),
            "errors": [],
        },
    }
