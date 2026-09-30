"""verify / gates-only / separately authorized one-shot DEVELOPMENT execute."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import kr_model_portfolio_execution as X  # noqa: E402


def run(mode, *, input_root=None, output=None, root=ROOT):
    spec, sha = X.load_spec(root)
    counters = X.Counters()
    if mode == "verify":
        return {"studyId": X.STUDY, "mode": mode, "status": "VERIFIED", "specSha256": sha,
                "harnessHashes": spec["dependencyHashes"], "executeAuthorized": (Path(root) / X.AUTH_PATH).exists(),
                "counters": asdict(counters), "stoppedBeforeOutcomes": counters.zero()}
    if mode not in ("gates-only", "execute"):
        raise ValueError("UNREGISTERED_EXECUTION_MODE")
    if mode == "execute":
        # Refuse BEFORE any data is read if authorization is absent.
        if not (Path(root) / X.AUTH_PATH).is_file():
            raise ValueError("EXECUTE_UNAUTHORIZED")
        if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_REF") != "refs/heads/main":
            raise ValueError("FORMAL_EXECUTION_REQUIRES_ACTIONS_MAIN")
        committed = subprocess.check_output(["git", "show", "HEAD:" + X.AUTH_PATH], cwd=root)
        if committed != (Path(root) / X.AUTH_PATH).read_bytes():
            raise ValueError("AUTHORIZATION_NOT_COMMITTED_AT_HEAD")
        if (Path(root) / X.RESULT_PATH).exists():
            raise ValueError("SUBSTANTIVE_RESULT_ALREADY_CLOSED_V1")
    if input_root is None:
        return {"studyId": X.STUDY, "mode": mode, "status": "DATA_INSUFFICIENT", "specSha256": sha, "reason": "RAW_INPUT_SNAPSHOT_REQUIRED",
                "counters": asdict(counters), "stoppedBeforeOutcomes": counters.zero()}
    identity = X.input_identity(input_root)
    if mode == "execute":
        X.require_authorization(spec, sha, identity, root)
    try:
        bundle = X.prepare(input_root, spec)
        gates = X.pre_label_gates(bundle, spec, counters)
    except ValueError as exc:
        gates = {"status": "DATA_INSUFFICIENT", "reasons": [str(exc)], "counters": asdict(counters)}
    report = {"studyId": X.STUDY, "mode": mode, "specSha256": sha, "inputIdentity": identity,
              "status": gates["status"], "gates": gates, "counters": asdict(counters),
              "stoppedBeforeOutcomes": counters.zero()}
    if mode == "gates-only":
        return report
    if output is None:
        raise ValueError("DURABLE_OUTPUT_DIRECTORY_REQUIRED")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if (output / "primary.json").exists() or (output / "execution.started.json").exists():
        raise ValueError("ONE_SHOT_ALREADY_SPENT")
    if gates["status"] != "READY":
        return {**report, "executionAuthorizationConsumed": False, "substantive": False}
    # All identity and clean-gate checks precede the permanent repository claim.
    X.load_spec(root)
    if X.input_identity(input_root) != identity:
        raise ValueError("SAME_RUN_INPUT_SWAP")
    X.require_authorization(spec, sha, identity, root)
    if not counters.zero() or gates.get("counters") != asdict(X.Counters()):
        raise ValueError("OUTCOME_PERMIT_REQUIRES_CLEAN_PASSED_GATES")
    lock = X.claim_execution_lock(sha)
    # Nothing outcome-facing may intervene in this claim -> permit exchange.
    permit = X.issue_permit(gates, spec, sha, identity, root, lock=lock)
    X.atomic_write(output / "execution.started.json", {"specSha256": sha, "inputSha256": identity["sha256"]}, immutable=True)
    context = None
    try:
        primary, context = X.run_historical(permit, bundle, spec, counters)
        X.load_spec(root)
        if X.input_identity(input_root) != identity:
            raise ValueError("SAME_RUN_INPUT_SWAP")
    except Exception as exc:
        primary = {"studyId": X.STUDY, "state": "INFRASTRUCTURE_ERROR", "errorType": type(exc).__name__,
                   "executionAuthorizationConsumed": True, "prospectiveEvidence": False,
                   "counters": asdict(counters)}
        context = None
    primary.update(specSha256=sha, inputSnapshotSha256=identity["sha256"], substantive=True)
    # Primary is immutable and durable BEFORE importing/calling supplementary work.
    digest = X.atomic_write(output / "primary.json", primary, immutable=True)
    X.atomic_write(output / "primary.sha256.json", {"fileSha256": digest}, immutable=True)
    if context is None:
        return primary
    try:
        from pipeline.kr_portfolio_diagnostics import supplementary
        from pipeline.alpha_opportunity_v5_execution import jsonable
        diagnostics = supplementary(context, bundle, spec, permit, counters)
        X.atomic_write(output / "diagnostics" / "summary.json", jsonable(diagnostics), immutable=True)
    except BaseException as exc:
        # A diagnostic failure cannot make an already written primary retryable.
        X.atomic_write(output / "diagnostics" / "error.json", {"status": "DIAGNOSTIC_ERROR", "type": type(exc).__name__,
                                                              "affectsPrimary": False}, immutable=True)
    return primary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("verify", "gates-only", "execute"), default="verify")
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run(args.mode, input_root=args.inputs, output=args.output)
    if args.output and args.mode != "execute":
        X.atomic_write(args.output / (args.mode + ".json"), result)
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
