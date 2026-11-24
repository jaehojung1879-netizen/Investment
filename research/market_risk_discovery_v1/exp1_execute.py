"""Experiment 1 one-shot harness: verify pins and the owner's structured authorization, claim the run exclusively,
compute the frozen historical forecast comparison ONCE, publish the result without overwrite.

Reuses the audited primitives of stage3_execute_v2 (`publish`, `_fsync_dir`) and its exclusive-claim pattern.

    python -m research.market_risk_discovery_v1.exp1_execute --verify-only
    python -m research.market_risk_discovery_v1.exp1_execute --execute
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from . import stage3_execute_v2 as V2

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PROTOCOL = HERE / "exp1-protocol.json"
PROTOCOL_SHA = HERE / "exp1-protocol.sha256"
AUTHORIZATION = HERE / "authorization-exp1.json"
RESULTS = HERE / "results"
MARKER = RESULTS / "EXP1-EXECUTION-STARTED.json"
FAILURE = RESULTS / "EXP1-EXECUTION-FAILED.json"
RESULT = RESULTS / "exp1-historical-forecast-comparison.json"

EXPECTED_SCOPE = {
    "study": "market-risk-discovery-v1",
    "experiment": "EXP1_HISTORICAL_FORECAST_COMPARISON",
    "protocolFile": "research/market_risk_discovery_v1/exp1-protocol.json",
    "action": "EXECUTE_ONCE_HISTORICAL_EXPLORATORY_NO_INFERENCE",
    "maxExecutions": 1,
    "models": ["M0", "M1", "M2", "M3", "M4", "M5"],
    "excludes": ["INVESTMENT_SIMULATION", "MERGE", "OTHER_STUDIES", "P1_STAGE3_INFERENCE", "PRODUCTION_CHANGE",
                 "PROTOCOL_CHANGE", "RERUN", "STRATEGY_PROMOTION"],
}
REQUIRED_QUOTE = "실험 1 역사 예측 비교를 1회 실행하는 것을 승인한다. exp1-protocol sha256:{sha}"
AUTH_KEYS = {"protocolSha256", "pins", "scope", "approvedBy", "approvalQuote", "approvedAtUtc", "authenticity"}


class ExecutionRefused(RuntimeError):
    pass


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_constants() -> dict:
    from . import exp1_design as E
    from . import exp1_panels as EP
    from . import panels as P
    from . import stage2_design as D
    return {"HORIZON": D.HORIZON, "RIDGE_LAMBDA": D.RIDGE_LAMBDA, "MIN_TRAIN_ROWS": D.MIN_TRAIN_ROWS,
            "MIN_TRAIN_EPISODES": D.MIN_TRAIN_EPISODES, "MIN_EVAL_EPISODES": D.MIN_EVAL_EPISODES,
            "MIN_EVAL_ROWS": D.MIN_EVAL_ROWS, "P_CLIP": D.P_CLIP, "CALIBRATION_EDGES": list(D.CALIBRATION_EDGES),
            "P80": P.P80, "MIN_HISTORY": P.MIN_HISTORY, "WIDEN_LAG": P.WIDEN_LAG, "FIRST_DECISION": P.FIRST_DECISION,
            "MODELS": {k: list(v) for k, v in E.MODELS.items()},
            "SAMPLES": {k: {"requires": list(v["requires"]), "models": list(v["models"])} for k, v in E.SAMPLES.items()},
            "WARNING_MULTIPLE": E.WARNING_MULTIPLE, "PERIOD_SPLIT_YEAR": E.PERIOD_SPLIT_YEAR,
            "MAX_STALE_DAYS": EP.MAX_STALE_DAYS}


def check_authorization(auth: dict, psha: str, pins: dict, now: dt.datetime | None = None) -> None:
    if not isinstance(auth, dict) or set(auth) != AUTH_KEYS:
        raise ExecutionRefused("AUTHORIZATION_KEYS_DIFFER")
    if auth["protocolSha256"] != psha:
        raise ExecutionRefused("AUTHORIZATION_PINS_ANOTHER_PROTOCOL")
    if auth["pins"] != pins:
        raise ExecutionRefused("AUTHORIZATION_PINS_DIFFER")
    if auth["scope"] != {**EXPECTED_SCOPE, "protocolSha256": psha}:
        raise ExecutionRefused("AUTHORIZATION_SCOPE_DIFFERS")
    if REQUIRED_QUOTE.format(sha=psha) not in str(auth["approvalQuote"]):
        raise ExecutionRefused("APPROVAL_QUOTE_LACKS_REQUIRED_SENTENCE")
    if not isinstance(auth["approvedBy"], str) or not auth["approvedBy"].strip():
        raise ExecutionRefused("APPROVED_BY_MISSING")
    try:
        when = dt.datetime.fromisoformat(str(auth["approvedAtUtc"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExecutionRefused("APPROVED_AT_NOT_ISO8601") from exc
    if when.tzinfo is None or when > (now or dt.datetime.now(dt.timezone.utc)):
        raise ExecutionRefused("APPROVED_AT_INVALID")
    if auth["authenticity"] != V2.AUTHENTICITY:
        raise ExecutionRefused("AUTHENTICITY_ACKNOWLEDGEMENT_MISSING")


def verify(require_authorization: bool = True) -> dict:
    if MARKER.exists() or RESULT.exists() or FAILURE.exists():
        raise ExecutionRefused("ONE_SHOT_ALREADY_SPENT")
    if not PROTOCOL.exists() or not PROTOCOL_SHA.exists():
        raise ExecutionRefused("PROTOCOL_MISSING")
    psha = sha(PROTOCOL)
    if PROTOCOL_SHA.read_text().split()[0] != psha:
        raise ExecutionRefused("PROTOCOL_HASH_MISMATCH")
    spec = json.loads(PROTOCOL.read_text())
    if spec["frozenConstants"] != frozen_constants():
        raise ExecutionRefused("FROZEN_CONSTANTS_DIFFER_FROM_CODE")
    for group in ("code", "inputs", "evidence"):
        for rel, want in spec["pins"][group].items():
            if sha(REPO / rel) != want:
                raise ExecutionRefused(f"PIN_MISMATCH:{rel}")
    if not require_authorization:
        return {"protocolSha256": psha, "authorization": None}
    if not AUTHORIZATION.exists():
        raise ExecutionRefused("NO_AUTHORIZATION_FILE")
    check_authorization(json.loads(AUTHORIZATION.read_text()), psha, spec["pins"])
    return {"protocolSha256": psha}


def claim_marker(content: dict) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(MARKER), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o444)
    except FileExistsError as exc:
        raise ExecutionRefused("ONE_SHOT_ALREADY_SPENT") from exc
    try:
        os.write(fd, (json.dumps(content, indent=1, sort_keys=True) + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    V2._fsync_dir(RESULTS)


def real_compute() -> dict:
    from . import exp1_design as E  # noqa: PLC0415
    from . import exp1_panels as EP  # noqa: PLC0415
    c = EP.rows("real")
    return E.evaluate(c["rows"], c["refits"], c["starts"])


def execute(compute=real_compute, verify_fn=verify) -> dict:
    checked = verify_fn()
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    marker = {"study": "market-risk-discovery-v1", "experiment": "EXP1", "protocolSha256": checked["protocolSha256"],
              "gitHead": head, "pid": os.getpid(), "startedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "signalLabelJoinsBeforeThisMarker": 0}
    claim_marker(marker)
    try:
        res = compute()
    except BaseException as exc:
        try:
            V2.publish(FAILURE, json.dumps({"marker": marker, "error": repr(exc)}, indent=1) + "\n")
        finally:
            raise
    result = {"study": "market-risk-discovery-v1", "experiment": "EXP1_HISTORICAL_FORECAST_COMPARISON",
              "evidenceClass": "EXPLORATORY_ON_OUTCOME_EXPOSED_HISTORY", "inferentialClaim": None,
              "promotionEligible": False, "marker": marker,
              "finishedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(), "samples": res}
    V2.publish(RESULT, json.dumps(result, indent=1, sort_keys=True, default=float) + "\n")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--verify-only", action="store_true")
    g.add_argument("--execute", action="store_true")
    a = ap.parse_args()
    try:
        if a.verify_only:
            print(json.dumps({"verify": "OK", **verify(require_authorization=False)}, indent=1))
            return 0
        out = execute()
        print(json.dumps({s: {m: {k: v[k] for k in ("brier", "brierSkillVsM0") if k in v}
                              for m, v in r.get("models", {}).items()} for s, r in out["samples"].items()}, indent=1))
        return 0
    except ExecutionRefused as exc:
        print(f"REFUSED: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
