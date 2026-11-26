"""Market Risk Discovery v1 -- Stage 3 v2 one-shot harness for the P1 v2 protocol (independent audit B1/B2).

What changed from v1 (`stage3_execute.py`, now permanently refused):

* B1 exclusive one-shot. v1 checked "no marker" in verify() and later wrote the marker with os.replace, so two
  processes could both pass verify and both run. v2 claims the marker with os.open(O_CREAT | O_EXCL | O_WRONLY)
  AFTER verification and BEFORE any real credit value meets a label; exactly one process can create it, the loser
  raises before computing anything. The marker is fsynced (file and directory) and never removed, including on
  failure. The result is written to a unique temporary file, fsynced, and published with os.link, which refuses to
  overwrite an existing result.
* B2 structured scope. The authorization must carry exactly the expected keys, a scope object equal to
  EXPECTED_SCOPE, the protocol hash and pins of THIS protocol, an approval quote containing the required sentence
  with the protocol hash, a past ISO-8601 UTC timestamp, and an explicit acknowledgement that the file is an
  unauthenticated record. The file does not cryptographically prove who approved it; it proves only that the
  approved scope and the executed scope are the same.

    python -m research.market_risk_discovery_v1.stage3_execute_v2 --verify-only
    python -m research.market_risk_discovery_v1.stage3_execute_v2 --execute
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PROTOCOL = HERE / "protocol-stage2-v2.json"
PROTOCOL_SHA = HERE / "protocol-stage2-v2.sha256"
AUTHORIZATION = HERE / "authorization-stage3-v2.json"
RESULTS = HERE / "results"
MARKER = RESULTS / "STAGE3-V2-EXECUTION-STARTED.json"
FAILURE = RESULTS / "STAGE3-V2-EXECUTION-FAILED.json"
RESULT = RESULTS / "stage3-v2-p1-result.json"

EXPECTED_SCOPE = {
    "study": "market-risk-discovery-v1",
    "stage": "STAGE_3_P1",
    "hypothesis": "P1",
    "protocolFile": "research/market_risk_discovery_v1/protocol-stage2-v2.json",
    "action": "EXECUTE_ONCE_HISTORICAL_EXPLORATORY",
    "maxExecutions": 1,
    "excludes": ["MERGE", "OTHER_STUDIES", "PRODUCTION_CHANGE", "PROTOCOL_CHANGE", "RERUN", "STRATEGY_PROMOTION"],
}
REQUIRED_QUOTE = "P1 Stage 3 v2 1회 연구 실행을 승인한다. protocol-stage2-v2 sha256:{sha}"
AUTH_KEYS = {"protocolSha256", "pins", "scope", "approvedBy", "approvalQuote", "approvedAtUtc", "authenticity"}
AUTHENTICITY = "UNAUTHENTICATED_FILE_RECORD_OF_OWNER_APPROVAL"


class ExecutionRefused(RuntimeError):
    pass


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_constants() -> dict:
    from . import panels as P
    from . import stage2_design as D
    from . import stage2v2_crt as G
    return {"HORIZON": D.HORIZON, "RIDGE_LAMBDA": D.RIDGE_LAMBDA, "MIN_TRAIN_ROWS": D.MIN_TRAIN_ROWS,
            "MIN_TRAIN_EPISODES": D.MIN_TRAIN_EPISODES, "MIN_EVAL_EPISODES": D.MIN_EVAL_EPISODES,
            "MIN_EVAL_ROWS": D.MIN_EVAL_ROWS, "ALPHA": D.ALPHA, "P_CLIP": D.P_CLIP, "BLOCK_LENGTH": D.BLOCK_LENGTH,
            "BOOTSTRAP_DRAWS": D.BOOTSTRAP_DRAWS, "BOOTSTRAP_SEED": D.BOOTSTRAP_SEED,
            "CALIBRATION_EDGES": list(D.CALIBRATION_EDGES), "P80": P.P80, "MIN_HISTORY": P.MIN_HISTORY,
            "WIDEN_LAG": P.WIDEN_LAG, "FIRST_DECISION": P.FIRST_DECISION, "GEN_LAMBDA": G.GEN_LAMBDA,
            "CRT_DRAWS": G.CRT_DRAWS, "CRT_SEED": G.CRT_SEED, "ADEQUACY_DRAWS": G.ADEQUACY_DRAWS,
            "ADEQUACY_SEED": G.ADEQUACY_SEED}


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
    if auth["authenticity"] != AUTHENTICITY:
        raise ExecutionRefused("AUTHENTICITY_ACKNOWLEDGEMENT_MISSING")


def verify(require_authorization: bool = True) -> dict:
    """Every check that can be made without a label. Raises ExecutionRefused naming the first failure."""
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
        return {"protocolSha256": psha, "decision": spec.get("decision"), "authorization": None}
    if spec.get("decision") != "READY_FOR_STAGE_3":
        raise ExecutionRefused(f"PROTOCOL_NOT_READY:{spec.get('decision')}")
    if not label_free_adequacy()["adequate"]:
        raise ExecutionRefused("GENERATOR_INADEQUATE_BEFORE_ANY_LABEL")
    if not AUTHORIZATION.exists():
        raise ExecutionRefused("NO_AUTHORIZATION_FILE")
    auth = json.loads(AUTHORIZATION.read_text())
    check_authorization(auth, psha, spec["pins"])
    return {"protocolSha256": psha, "authorization": auth}


def signal_sequence() -> dict:
    """The defined credit-flag sequence and its X path. Reads credit and prices only; the risk-set mask uses the
    point-in-time 'inside an episode' state, never a forward label."""
    import numpy as np  # noqa: PLC0415

    from . import panels as P  # noqa: PLC0415
    price, events = P.price_side(), P.event_side()
    me = P.month_end_index(price["dates"])
    cs = P.credit_side()
    k = [me[m] for m, _ in cs]
    return {"months": [m for m, _ in cs], "flags": np.array([v for _, v in cs]),
            "gap": np.array([price["gap"][i] for i in k]), "vol": np.array([price["vol"][i] for i in k]),
            "common": np.array([price["fast"][i] == 0 and not events["active"][i] for i in k])}


def label_free_adequacy() -> dict:
    from . import stage2v2_crt as G  # noqa: PLC0415
    s = signal_sequence()
    return G.adequacy(s["gap"], s["vol"], s["flags"], s["months"], s["common"])


def _fsync_dir(path: Path) -> None:
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def claim_marker(content: dict) -> None:
    """Exclusive creation: exactly one process can succeed; the file is never removed."""
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
    _fsync_dir(RESULTS)


def publish(path: Path, text: str) -> None:
    """Write to a unique temporary file, fsync, then hard-link into place; refuses to overwrite."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        os.write(fd, text.encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.link(tmp, str(path))
    finally:
        os.unlink(tmp)
    _fsync_dir(path.parent)


def real_compute() -> dict:
    import numpy as np  # noqa: PLC0415

    from . import panels as P  # noqa: PLC0415
    from . import stage2_design as D  # noqa: PLC0415
    from . import stage2v2_crt as G  # noqa: PLC0415
    c = P.common_rows("real")
    price, events = P.price_side(), P.event_side()
    seq = c["flagSequence"]
    gap = np.array([price["gap"][i] for i, _ in seq])
    vol = np.array([price["vol"][i] for i, _ in seq])
    months = [price["dates"][i][:7] for i, _ in seq]
    common = np.array([price["fast"][i] == 0 and not events["active"][i] for i, _ in seq])
    return G.evaluate_v2(D.Panel(c["rows"]), D.refit_points(c["monthEnds"]), seq, gap, vol, months, common, c["starts"])


def execute(compute=real_compute, verify_fn=verify) -> dict:
    checked = verify_fn()
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    marker = {"study": "market-risk-discovery-v1", "stage": "STAGE_3_P1_V2", "protocolSha256": checked["protocolSha256"],
              "gitHead": head, "pid": os.getpid(), "startedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "creditLabelJoinsBeforeThisMarker": 0}
    claim_marker(marker)
    try:
        res = compute()
    except BaseException as exc:
        try:
            publish(FAILURE, json.dumps({"marker": marker, "error": repr(exc),
                                         "atUtc": dt.datetime.now(dt.timezone.utc).isoformat()}, indent=1) + "\n")
        finally:
            raise
    result = {"study": "market-risk-discovery-v1", "stage": "STAGE_3_P1_V2",
              "evidenceClass": "EXPLORATORY_ON_OUTCOME_EXPOSED_HISTORY", "promotionEligible": False, "marker": marker,
              "finishedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat(), **res}
    publish(RESULT, json.dumps(result, indent=1, sort_keys=True, default=float) + "\n")
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
