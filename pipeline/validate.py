"""Validate site-data artifacts before Pages deployment.

Enforces the invariants that keep README / build / screen / validator telling
the SAME safe story:
  * provenance is present (schemaVersion, modelVersion, runMode, buildCommitSha,
    marketAsOf) so a consumer can always tell what produced the numbers;
  * runMode is a known value and is NEVER liveValidated straight from a build
    (that must be earned by the ledger);
  * a blocked artifact carries NO actionable output — no short-term ideas,
    long-term positions/weights, entry states, or actionable reasons;
  * seed / synthetic / stale artifacts are rejected for production.
"""
from __future__ import annotations
import json, math, sys
from pathlib import Path

VALID_RUN_MODES = {"researchOnly", "paperTrading", "liveValidated"}
ACTIONABLE_REASON_TERMS = (
    "buy", "sell", "avoid", "wait", "accumulate", "entry", "매수", "매도",
    "진입", "대기", "회피", "되돌림", "편입", "비중",
)


def _walk(o, path="$"):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _walk(v, f"{path}[{i}]")
    elif isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        yield path


def _longterm_has_weights(data: dict) -> bool:
    lt = data.get("longTerm") or {}
    for blob in (lt.get("regions") or {}).values():
        for p in (blob or {}).get("picks", []):
            if p.get("modelSleeveWeightPct") is not None:
                return True
    return False


def _longterm_has_positions(data: dict) -> bool:
    lt = data.get("longTerm") or {}
    for blob in (lt.get("regions") or {}).values():
        if (blob or {}).get("picks") or (blob or {}).get("holdings"):
            return True
    return False


def _has_blocked_entry_actions(obj) -> bool:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "entryState" and value is not None:
                return True
            if key in {"reasons", "reason"}:
                values = value if isinstance(value, list) else [value]
                for item in values:
                    text = str(item or "").lower()
                    if any(term in text for term in ACTIONABLE_REASON_TERMS):
                        return True
            if _has_blocked_entry_actions(value):
                return True
    elif isinstance(obj, list):
        return any(_has_blocked_entry_actions(item) for item in obj)
    return False


def validate(path: str | Path, production: bool = True) -> list[str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    errors = []
    m = data.get("meta", {})
    for k in ["portfolioName", "meta", "generatedAt", "core", "screened", "tradeIdeas"]:
        if k not in data:
            errors.append(f"missing_{k}")

    # Provenance: the single source of truth must be attached and coherent.
    prov = data.get("provenance") or {}
    for k in ["schemaVersion", "modelVersion", "runMode", "marketAsOf"]:
        if not prov.get(k) and not data.get(k):
            errors.append(f"missing_provenance_{k}")
    run_mode = data.get("runMode") or prov.get("runMode")
    if run_mode not in VALID_RUN_MODES:
        errors.append("invalid_run_mode")
    if run_mode == "liveValidated" and not (data.get("validation") or {}).get("liveValidatedEarned"):
        errors.append("liveValidated_not_earned")

    bad = list(_walk(data))
    if bad:
        errors.append("nan_or_infinity:" + ",".join(bad[:5]))

    if production:
        if data.get("seed"):
            errors.append("seed_artifact_not_allowed_for_production")
        artifact_modes = {data.get("dataMode"), prov.get("dataMode")}
        if m.get("syntheticData") or artifact_modes & {"synthetic", "seed"}:
            errors.append("synthetic_artifact_not_allowed_for_production")
        if data.get("stale") or "stale" in artifact_modes:
            errors.append("stale_artifact_not_allowed_for_production")
        if m.get("modelsTrained", 0) <= 0:
            errors.append("modelsTrained_zero")
        if (m.get("coveragePct") or 0) < (m.get("coverageFloor") or 95):
            errors.append("coverage_below_floor")

    # A blocked artifact must not carry actionable output of ANY kind.
    if data.get("recommendationsBlocked"):
        if any((data.get("tradeIdeas") or {}).get(r) for r in ("KR", "US")):
            errors.append("blocked_artifact_contains_trade_ideas")
        if _longterm_has_weights(data):
            errors.append("blocked_artifact_contains_longterm_weights")
        if _longterm_has_positions(data):
            errors.append("blocked_artifact_contains_longterm_positions")
        if _has_blocked_entry_actions(data.get("longTerm") or {}):
            errors.append("blocked_artifact_contains_entry_actions")
    return errors


def main(argv=None):
    argv = argv or sys.argv[1:]
    if not argv:
        print("usage: python -m pipeline.validate data/site-data.json [--allow-seed]")
        return 2
    production = "--allow-seed" not in argv
    errs = validate(argv[0], production=production)
    if errs:
        print("VALIDATION FAILED")
        for e in errs:
            print("-", e)
        return 1
    print("validation ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
