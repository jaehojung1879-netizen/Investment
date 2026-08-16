"""Write a compact, recurring audit of historical up/down probabilities.

Performance-gate failure is a valid model result and does not fail the workflow;
contract failures (no calibration despite matured current-generation outcomes,
look-ahead policy missing, malformed probabilities) do fail it.

Usage:
    python scripts/audit_probability.py <ledger-dir>
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import historical_store as HS  # noqa: E402
from pipeline import historical_calibration as HC  # noqa: E402
from pipeline import provenance as prov  # noqa: E402
from pipeline.config import load_config  # noqa: E402


def _compact(result: dict, *, outcome_count: int, matured_count: int) -> dict:
    regions = {}
    for region, blob in (result.get("regions") or {}).items():
        buckets = []
        for row in blob.get("buckets") or []:
            buckets.append({key: row.get(key) for key in (
                "bucket", "observations", "dates", "effectiveDates",
                "upProbabilityPct", "downProbabilityPct", "averageUpsidePct",
                "averageDownsidePct", "payoffRatio",
                "distributionExpectedExcessReturnPct", "binaryKellyFraction")})
        regions[region] = {
            "selectedVariant": blob.get("selectedVariant"),
            "selectionPeriod": blob.get("selectionPeriod"),
            "auditPeriod": blob.get("auditPeriod"),
            "audit": blob.get("audit"),
            "reliabilityGate": blob.get("reliabilityGate"),
            "labelAvailabilityPolicy": blob.get("labelAvailabilityPolicy"),
            "buckets": buckets,
        }
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "replayVersion": prov.REPLAY_VERSION,
        "modelVersion": prov.MODEL_VERSION,
        "evidenceClass": "HISTORICAL_OOS",
        "outcomesRead": int(outcome_count),
        "maturedTargetOutcomesRead": int(matured_count),
        "available": bool(result.get("available")),
        "method": result.get("method"),
        "target": result.get("target"),
        "reliabilityGate": result.get("reliabilityGate"),
        "integrityGate": result.get("integrityGate"),
        "regions": regions,
        "explainKo": result.get("explainKo"),
    }


def _contract_errors(audit: dict) -> list[str]:
    errors = []
    if audit.get("maturedTargetOutcomesRead", 0) > 0 and not audit.get("available"):
        errors.append("matured_current_generation_outcomes_not_calibrated")
    for region, blob in (audit.get("regions") or {}).items():
        if blob.get("labelAvailabilityPolicy") != "OUTCOME_END_DATE_LTE_PREDICTION_DATE":
            errors.append(f"label_availability_policy_missing:{region}")
        for row in blob.get("buckets") or []:
            up, down = row.get("upProbabilityPct"), row.get("downProbabilityPct")
            if up is None or down is None:
                errors.append(f"probability_missing:{region}:{row.get('bucket')}")
                continue
            if not all(math.isfinite(float(x)) and 0 <= float(x) <= 100 for x in (up, down)):
                errors.append(f"probability_invalid:{region}:{row.get('bucket')}")
            if abs(float(up) + float(down) - 100.0) > 0.05:
                errors.append(f"probability_sum_invalid:{region}:{row.get('bucket')}")
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger_dir")
    args = parser.parse_args(argv)
    cfg, _ = load_config()
    replay_cfg = cfg.historical_replay or {}
    horizon = int(replay_cfg.get("horizonDays", 126))
    probability_cfg = ((cfg.kelly_portfolio or {}).get("probabilityCalibration") or {})
    outcomes = HS.load(args.ledger_dir, HS.OUTCOMES, generation=prov.REPLAY_VERSION)
    diagnostics_path = HS.diagnostics_path(args.ledger_dir)
    try:
        diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        diagnostics = {}
    calibration = HC.calibrate(
        outcomes, horizon=horizon,
        buckets=replay_cfg.get("alphaPercentileBuckets", [0, 60, 80, 90, 95, 100]),
        cfg={"minEffectiveDates": int(replay_cfg.get("minEffectiveDates", 30)),
             "shrinkagePriorStrength": float(replay_cfg.get("shrinkagePriorStrength", 30)),
             "probabilityCalibration": probability_cfg},
        diagnostics=diagnostics,
        cost_adjusted=bool(replay_cfg.get("costAdjusted", True)),
        require_pit=bool(replay_cfg.get("requirePitQuality", True)))
    result = calibration.get("probabilityCalibration") or {
        "available": False, "reason": "expected_return_calibration_unavailable",
        "regions": {}, "reliabilityGate": {"eligible": False}}
    matured_count = sum(
        1 for outcome in outcomes
        if str(horizon) in (outcome.get("horizons") or {}))
    audit = _compact(result, outcome_count=len(outcomes), matured_count=matured_count)
    path = Path(args.ledger_dir) / "historical-probability-audit.json"
    path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    errors = _contract_errors(audit)
    print(f"probability audit: {len(outcomes)} outcomes, "
          f"Kelly eligible={bool((audit.get('reliabilityGate') or {}).get('eligible'))}")
    for region, blob in audit["regions"].items():
        print(f"  {region}: {blob.get('selectedVariant')} | {blob.get('audit')} | "
              f"gate={(blob.get('reliabilityGate') or {}).get('eligible')}")
    if errors:
        print("PROBABILITY AUDIT CONTRACT FAILED")
        for error in errors:
            print("-", error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
