"""Read sealed summaries only; no prices, state reconstruction, fitting or Oracle solver."""
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path

STUDY = "EXP-C-RECOVERY-01"
KR = "docs/results/kr-market-risk-model-v1-result.json"
ANATOMY = "docs/results/kr-market-risk-anatomy-v2-result.json"
US = "docs/research-program/results/rp1-c1-us-exposure-formal-20261024/payload/result.json.gz.b64"
PINS = {
    KR: "2578bbfa245a6540235cc05e231441b4ebb4da165240a84e715756477a897c4b",
    ANATOMY: "7be4f68f30cf57b01cde88f106b3c0c2ed88fc9942ca2a14007664ffbe4ca769",
    US: "910215317eedcaf45f293dc056749688f9400cd00f95102b565d265f552e3938",
}
FEATURES = (
    "fast_trend_distance_sma200", "fast_sma200_slope_21",
    "fast_realized_vol_21", "fast_realized_vol_63", "fast_downside_vol_63",
    "fast_vol_acceleration", "trans_vix_level", "slow_resteepening_flag_10y3m",
    "fast_drawdown_252", "fast_ret_63", "fast_ret_126",
)


def sealed(root: Path, path: str):
    raw = (root / path).read_bytes()
    if path.endswith(".gz.b64"):
        raw = gzip.decompress(base64.b64decode(raw.strip(), validate=True))
    if hashlib.sha256(raw).hexdigest() != PINS[path]:
        raise ValueError("SEALED_SOURCE_HASH_MISMATCH: " + path)
    return json.loads(raw)


def accounting(passive: float, gross: float, net: float):
    """CAGR differences, in percentage points/year. Not additive causal attribution."""
    return {
        "passiveMinusNetCagrPp": 100 * (passive - net),
        "grossMinusNetCostCagrPp": 100 * (gross - net),
        "unattributedNonCostCagrPp": 100 * (passive - gross),
        "delayedExitCagrPp": None,
        "falseAlarmCagrPp": None,
        "delayedReentryCagrPp": None,
    }


def extract(root: Path):
    out = {"studyId": STUDY, "status": "SEALED_EVIDENCE_REVIEW_ONLY",
           "newHistoricalEvaluations": 0, "sourceSha256": PINS, "regions": {}}
    for region, path in (("KR", KR), ("US", US)):
        result = sealed(root, path)
        passive = result["passive"]["summary"]
        candidates = {}
        for name in ("C0", "C1"):
            c = result["candidates"][name]
            candidates[name] = {
                "accounting": accounting(passive["annualizedReturn"],
                                         c["gross"]["annualizedReturn"],
                                         c["net"]["annualizedReturn"]),
                "net": c["net"], "implementation": c["implementation"],
                "falseAlarm": c["falseAlarm"], "heldForMissingState": c["heldForMissingState"],
                "episodesDepthGe15pct": c["episodes"]["depth_ge_15pct"],
            }
        out["regions"][region] = {"window": result["window"], "passive": passive,
                                   "decision": result["decision"]["developmentNomination"],
                                   "candidates": candidates}
    anatomy = sealed(root, ANATOMY)
    out["featureEvidence"] = {}
    for name in FEATURES:
        horizons = {}
        for h, row in anatomy["features"][name].items():
            horizons[h] = {"validDates": row["validDates"], "start": row["start"],
                           "end": row["end"], "lossLe15Auroc": row["events"]["loss_le_15"]["auroc"]}
        out["featureEvidence"][name] = {"sample": anatomy["sample"]["features"][name],
                                        "horizons": horizons}
    out["breadthCoverage"] = anatomy["extendedInternals"]["sample"]
    return out


def require_ex_ante(observations, decision_at):
    """Audit a proposed feature boundary, not a forecast/data-admission engine.

    All instants must be timezone-aware. 'availableAt' must have independent
    source evidence; passing this check cannot authenticate a caller's timestamp.
    """
    decision = datetime.fromisoformat(decision_at)
    if decision.tzinfo is None:
        raise ValueError("TIMEZONE_REQUIRED")
    required = {"feature", "observedAt", "availableAt", "value"}
    for row in observations:
        if set(row) != required or row["feature"] not in FEATURES + ("fast", "slow", "transition", "vixPercentile"):
            raise ValueError("NON_FEATURE_OR_ORACLE_FIELD")
        value = row["value"]
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
            raise ValueError("NON_NUMERIC_FEATURE_VALUE")
        observed = datetime.fromisoformat(row["observedAt"])
        available = datetime.fromisoformat(row["availableAt"])
        if observed.tzinfo is None or available.tzinfo is None:
            raise ValueError("TIMEZONE_REQUIRED")
        if not observed <= available <= decision:
            raise ValueError("NOT_KNOWN_AT_DECISION")


def require_mature_training_label(execution_at, outcome_end_at, final_at, cutoff_at):
    instants = [datetime.fromisoformat(x) for x in
                (execution_at, outcome_end_at, final_at, cutoff_at)]
    if any(x.tzinfo is None for x in instants):
        raise ValueError("TIMEZONE_REQUIRED")
    execution, end, final, cutoff = instants
    if not execution < end <= final < cutoff:
        raise ValueError("UNMATURED_OR_NONFINAL_TRAINING_LABEL")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    print(json.dumps(extract(args.repo_root), indent=2, sort_keys=True, allow_nan=False))
