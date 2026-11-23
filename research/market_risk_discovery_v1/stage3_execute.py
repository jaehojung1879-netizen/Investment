"""Market Risk Discovery v1 -- Stage 3 one-shot harness for the frozen P1 design.

Nothing here runs without the owner's explicit approval. `--verify-only` checks every pin and touches no outcome;
`--execute` additionally requires `authorization-stage3.json` (written only after the owner approves), writes the
execution marker BEFORE the first real credit value meets a label, computes the frozen evaluation once, and writes the
result atomically. A second execution is refused whatever happened to the first.

    python -m research.market_risk_discovery_v1.stage3_execute --verify-only
    python -m research.market_risk_discovery_v1.stage3_execute --execute
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

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PROTOCOL = HERE / "protocol-stage2.json"
PROTOCOL_SHA = HERE / "protocol-stage2.sha256"
AUTHORIZATION = HERE / "authorization-stage3.json"
MARKER = HERE / "results" / "STAGE3-EXECUTION-STARTED.json"
RESULT = HERE / "results" / "stage3-p1-result.json"


class ExecutionRefused(RuntimeError):
    pass


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_constants() -> dict:
    from . import panels as P
    from . import stage2_design as D
    return {"HORIZON": D.HORIZON, "RIDGE_LAMBDA": D.RIDGE_LAMBDA, "ROTATION_GUARD": D.ROTATION_GUARD,
            "BLOCK_LENGTH": D.BLOCK_LENGTH, "BOOTSTRAP_DRAWS": D.BOOTSTRAP_DRAWS, "BOOTSTRAP_SEED": D.BOOTSTRAP_SEED,
            "MIN_TRAIN_ROWS": D.MIN_TRAIN_ROWS, "MIN_TRAIN_EPISODES": D.MIN_TRAIN_EPISODES,
            "MIN_EVAL_EPISODES": D.MIN_EVAL_EPISODES, "MIN_EVAL_ROWS": D.MIN_EVAL_ROWS,
            "MIN_ROTATIONS": D.MIN_ROTATIONS, "ALPHA": D.ALPHA, "P_CLIP": D.P_CLIP,
            "CALIBRATION_EDGES": list(D.CALIBRATION_EDGES), "P80": P.P80, "MIN_HISTORY": P.MIN_HISTORY,
            "WIDEN_LAG": P.WIDEN_LAG, "FIRST_DECISION": P.FIRST_DECISION}


def verify(require_authorization: bool = True) -> dict:
    """Every pin, in order. Raises ExecutionRefused naming the first failure."""
    if MARKER.exists() or RESULT.exists():
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
    auth = json.loads(AUTHORIZATION.read_text())
    if auth.get("protocolSha256") != psha:
        raise ExecutionRefused("AUTHORIZATION_PINS_ANOTHER_PROTOCOL")
    if auth.get("pins") != spec["pins"]:
        raise ExecutionRefused("AUTHORIZATION_PINS_DIFFER")
    for field in ("approvedBy", "approvalQuote", "approvedAtUtc", "scope"):
        if not auth.get(field):
            raise ExecutionRefused(f"AUTHORIZATION_FIELD_MISSING:{field}")
    return {"protocolSha256": psha, "authorization": auth}


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as h:
        h.write(text)
        h.flush()
        os.fsync(h.fileno())
    os.replace(tmp, path)


def execute() -> dict:
    checked = verify(require_authorization=True)
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    marker = {"study": "market-risk-discovery-v1", "stage": "STAGE_3_P1", "protocolSha256": checked["protocolSha256"],
              "gitHead": head, "startedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "creditLabelJoinsBeforeThisMarker": 0}
    _atomic_write(MARKER, json.dumps(marker, indent=1, sort_keys=True) + "\n")

    from . import panels as P
    from . import stage2_design as D
    c = P.common_rows("real")
    p = D.Panel(c["rows"])
    res = D.evaluate(p, D.refit_points(c["monthEnds"]), c["flagSequence"], c["starts"])
    result = {"study": "market-risk-discovery-v1", "stage": "STAGE_3_P1", "evidenceClass":
              "EXPLORATORY_ON_OUTCOME_EXPOSED_HISTORY", "promotionEligible": False, "marker": marker,
              "finishedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(), **res}
    _atomic_write(RESULT, json.dumps(result, indent=1, sort_keys=True, default=float) + "\n")
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
        print(json.dumps({"verdict": out["verdict"], "primary": out.get("primary")}, indent=1, default=float))
        return 0
    except ExecutionRefused as exc:
        print(f"REFUSED: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
