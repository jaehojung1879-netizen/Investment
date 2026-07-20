"""Provenance & run-state stamps attached to every artifact.

The single most important honesty fix: README, the build, the validator and
the screen must all express the *same* safe state. This module is the one
source of truth for:

  * schemaVersion   — bumped when the payload shape changes (consumers gate on it)
  * modelVersion    — the engine/algorithm version (bumped on scoring changes)
  * buildCommitSha  — the exact code that produced the artifact
  * generatedAt     — when the build ran (UTC)
  * marketAsOf      — the last *price* observation date
  * sourceAsOf      — the last *fundamental / macro* source date
  * runMode         — researchOnly | paperTrading | liveValidated (default paperTrading)
  * dataMode        — live | seed | stale | synthetic  (what the numbers ACTUALLY are)

runMode is a claim about how the output may be used; dataMode is a claim about
what the numbers are. They are independent: a seed build is always dataMode=seed
regardless of runMode, and can never be liveValidated.
"""
from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone

SCHEMA_VERSION = "2.1.0"
MODEL_VERSION = "longterm-v2.1+regime-v2.1+entry-v1"

RUN_MODES = ("researchOnly", "paperTrading", "liveValidated")
DEFAULT_RUN_MODE = "paperTrading"


def build_commit_sha() -> str | None:
    """Short SHA of the code that produced this artifact.

    CI exposes it as GITHUB_SHA; locally we ask git. Never fabricate — return
    None if it genuinely can't be determined so the UI shows 'unknown' rather
    than a misleading value.
    """
    for env in ("GITHUB_SHA", "GIT_COMMIT", "BUILD_COMMIT_SHA"):
        val = os.environ.get(env)
        if val:
            return val[:12]
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return None


def resolve_run_mode(configured: str | None) -> str:
    """Clamp the configured run mode to a known value; default paperTrading.

    liveValidated is NEVER honored from config alone — it must be earned by the
    ledger/validation layer, which upgrades it explicitly. Config asking for
    liveValidated is downgraded here to paperTrading.
    """
    mode = (configured or DEFAULT_RUN_MODE).strip()
    if mode not in RUN_MODES:
        return DEFAULT_RUN_MODE
    if mode == "liveValidated":
        return DEFAULT_RUN_MODE
    return mode


def data_mode(payload: dict) -> str:
    """Classify what the numbers in this payload actually are."""
    meta = payload.get("meta", {}) or {}
    if payload.get("seed") or meta.get("syntheticData"):
        return "synthetic" if meta.get("syntheticData") else "seed"
    if payload.get("stale"):
        return "stale"
    return "live"


def stamp(payload: dict, run_mode: str) -> dict:
    """Attach the provenance block in-place and return it."""
    meta = payload.setdefault("meta", {})
    prov = {
        "schemaVersion": SCHEMA_VERSION,
        "modelVersion": MODEL_VERSION,
        "buildCommitSha": build_commit_sha(),
        "generatedAt": payload.get("generatedAt") or datetime.now(timezone.utc).isoformat(),
        "marketAsOf": meta.get("latestDataDate"),
        "sourceAsOf": meta.get("sourceAsOf"),
        "runMode": run_mode,
        "dataMode": data_mode(payload),
    }
    payload["provenance"] = prov
    payload["schemaVersion"] = SCHEMA_VERSION
    payload["modelVersion"] = MODEL_VERSION
    payload["runMode"] = run_mode
    payload["dataMode"] = prov["dataMode"]
    payload["generatedAt"] = prov["generatedAt"]
    return prov
