"""H2 paired return contrast: preliminary-entry vs formal-entry, the same signal and names.

NOT EXECUTED in this change. ``execute`` refuses unless an owner authorization file
pins this contract's exact SHA-256 (Phase D exception, see h2_return_contract.json).
The arithmetic is implemented and tested on invented prices only; it has never been
run on real Korean prices.

Input panel format (only after authorization): a JSON file
``{"sessions": [...ISO dates...], "closes": {"<ticker>": {"<date>": tr_close}}, "benchmark": {"<date>": tr_close}}``
of total-return closes from a pinned snapshot, plus a units file
``[{"ticker", "quarter", "y", "prelimDate", "formalDate"}]``.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTRACT = HERE / "h2_return_contract.json"
AUTHORIZATION = HERE / "AUTHORIZATION.json"
OWNER = "jaehojung1879-netizen"
sys.path.insert(0, str(HERE))
import transfer as T  # noqa: E402


class NotAuthorized(RuntimeError):
    pass


def contract_sha256(path: Path = CONTRACT) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_authorization(auth_path: Path = AUTHORIZATION, contract_path: Path = CONTRACT, *, require_git: bool = True) -> str:
    """Return the contract hash if, and only if, the owner approved exactly this contract."""
    digest = contract_sha256(contract_path)
    if not auth_path.exists():
        raise NotAuthorized("AUTHORIZATION_ABSENT: KR historical return evaluation is closed by Phase D; "
                            "an owner-committed AUTHORIZATION.json pinning " + digest + " is required")
    auth = json.loads(auth_path.read_text(encoding="utf-8"))
    expected = {"studyId": "industry-information-transfer-v1", "contractSha256": digest,
                "approval": f"APPROVE KR_PHASE_D_EXCEPTION industry-information-transfer-v1-h2 {digest}",
                "approvedBy": OWNER}
    for key, value in expected.items():
        if auth.get(key) != value:
            raise NotAuthorized(f"AUTHORIZATION_MISMATCH: field {key}")
    if require_git:
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", str(auth_path)], cwd=HERE,
                                 capture_output=True, text=True)
        if tracked.returncode != 0:
            raise NotAuthorized("AUTHORIZATION_NOT_COMMITTED")
    return digest


def centred_rank_weights(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: (values[i], i))
    ranks = [0.0] * len(values)
    for r, i in enumerate(order, start=1):
        ranks[i] = float(r)
    centre = (len(values) + 1) / 2
    dev = [r - centre for r in ranks]
    scale = sum(abs(d) for d in dev)
    return [d / scale for d in dev] if scale else [0.0] * len(values)


def _excess(closes: dict, bench: dict, sessions: list[str], entry: str, horizon: int) -> float | None:
    i = bisect.bisect_left(sessions, entry)
    if i >= len(sessions) or sessions[i] != entry or i + horizon >= len(sessions):
        return None
    exit_ = sessions[i + horizon]
    a, b, ba, bb = closes.get(entry), closes.get(exit_), bench.get(entry), bench.get(exit_)
    if None in (a, b, ba, bb) or a <= 0 or ba <= 0:
        return None
    return (b / a - 1) - (bb / ba - 1)


def paired_contrast(units: list[dict], panel: dict, horizon: int, *, authorized_digest: str) -> dict:
    """Per quarter D_q = sum_i w_i (excessA_i - excessB_i) on the identical, fully priced name set."""
    if not authorized_digest:
        raise NotAuthorized("paired_contrast needs the digest returned by check_authorization")
    sessions = panel["sessions"]
    by_q = defaultdict(list)
    dropped = 0
    for u in units:
        closes = panel["closes"].get(u["ticker"], {})
        a = _excess(closes, panel["benchmark"], sessions, _next_session(sessions, u["prelimDate"]), horizon)
        b = _excess(closes, panel["benchmark"], sessions, _next_session(sessions, u["formalDate"]), horizon)
        if a is None or b is None:
            dropped += 1  # removed from BOTH legs
            continue
        by_q[u["quarter"]].append((u["y"], a, b))
    per_q = {}
    for q, items in sorted(by_q.items()):
        if len(items) < 3:
            continue
        w = centred_rank_weights([y for y, _, _ in items])
        per_q[q] = {"n": len(items), "D": sum(wi * (a - b) for wi, (_, a, b) in zip(w, items)),
                    "legA": sum(wi * a for wi, (_, a, _) in zip(w, items)),
                    "legB": sum(wi * b for wi, (_, _, b) in zip(w, items))}
    return {"horizon": horizon, "quarters": len(per_q), "unitsDroppedFromBothLegs": dropped,
            "D": T.nw_summary([v["D"] for v in per_q.values()]), "perQuarter": per_q,
            "evidenceClass": "OUTCOME_EXPOSED_EXPLORATORY", "authorizedContractSha256": authorized_digest}


def _next_session(sessions: list[str], day: str) -> str:
    i = bisect.bisect_right(sessions, day)
    return sessions[i] if i < len(sessions) else ""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--units")
    parser.add_argument("--panel")
    parser.add_argument("--out")
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"contractSha256": contract_sha256(), "authorizationPresent": AUTHORIZATION.exists()}))
        return 0
    digest = check_authorization()  # raises before any price is opened
    units = json.loads(Path(args.units).read_text())
    panel = json.loads(Path(args.panel).read_text())
    result = {h: paired_contrast(units, panel, h, authorized_digest=digest) for h in (126, 252)}
    Path(args.out).write_text(json.dumps(result, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
