"""Official KRX raw collection -> immutable inputs -> frozen gates-only. NO execute mode."""
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

from pipeline import kr_model_raw_snapshot as S  # noqa: E402
from pipeline import kr_model_portfolio_execution as X  # noqa: E402
from scripts.run_kr_model_overlay_portfolio_v1 import run as formal  # noqa: E402


def boundary(root):
    if (Path(root) / X.AUTH_PATH).exists() or (Path(root) / X.RESULT_PATH).exists():
        raise ValueError("DATA_READINESS_REQUIRES_NO_AUTHORIZATION_OR_RESULT")
    refs = subprocess.check_output(["git", "ls-remote", "--tags", "origin",
                                   "refs/tags/kr-model-overlay-portfolio-v1-execution-lock-*"], cwd=root)
    if refs.strip():
        raise ValueError("PERMANENT_EXECUTION_LOCK_ALREADY_EXISTS_STOP")
    return {"executionAuthorizationCreated": False, "permanentLockExists": False,
            "executionPermitIssued": False, "historicalExecutionPerformed": False}


def replay_acquisition(directory, spec, expected_cache_sha256=None):
    """The ALREADY COMPLETED official acquisition, read from a preserved artifact. Never contacts the source."""
    acquisition = json.loads((Path(directory) / "acquisition.json").read_text())
    required = S.required_dates(spec)
    if (acquisition.get("status") != "SERVED" or not acquisition.get("complete") or acquisition.get("missingDates")
            or acquisition.get("requiredDates") != len(required)
            or (expected_cache_sha256 and acquisition["cache"]["sha256"] != expected_cache_sha256)):
        raise ValueError("REPLAY_ARTIFACT_IS_NOT_THE_COMPLETED_ACQUISITION")
    return acquisition


def no_network(*args, **kwargs):
    raise RuntimeError("NETWORK_ACQUISITION_FORBIDDEN_IN_REPLAY")


def collect_and_gate(directory, *, root=ROOT, key=None, fetch=S.call, pace=.4, replay=False, expected_cache_sha256=None,
                     expected_input_identity=None):
    spec = S.frozen_spec(root)
    states = boundary(root)
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    output = {"studyId": X.STUDY, "collectionCodeHead": base, "specSha256": S.SPEC_SHA,
              "diagnosticSpecSha256": S.DIAGNOSTIC_SHA, "rawSnapshotSha256": None,
              "inputIdentitySha256": None, "componentHashes": {}, "counters": asdict(X.Counters()),
              "annualCoreFamilyCoverage": "NOT_MEASURED", **states}
    try:
        members = S.materialize_universe(directory, spec, root)
        if replay:
            acquisition = replay_acquisition(directory, spec, expected_cache_sha256)
            output["acquisitionSource"] = "REPLAY_OF_PRESERVED_ARTIFACT_NO_NETWORK"
        else:
            acquisition = S.collect_official(directory, S.required_dates(spec), members, key=key, fetch=fetch, pace=pace)
        output["acquisition"] = acquisition
        output["componentHashes"] = {str(p.relative_to(Path(directory))): S.file_hash(p) for p in S._raw_files(directory)}
        output["componentHashStatus"] = "PARTIAL_ACQUISITION_NOT_EXECUTION_SNAPSHOT"
        if acquisition["complete"]:
            S.materialize_inherited(directory, spec, root)
            snapshot = S.freeze_snapshot(directory, spec)
            if expected_input_identity and snapshot["inputIdentity"]["sha256"] != expected_input_identity:
                raise ValueError("INPUT_IDENTITY_CHANGED_BY_CORRECTION")
            if replay:
                output["loaderEquivalence"] = S.loader_equivalence(directory, spec)
            output.update(componentHashStatus="IMMUTABLE_COMPLETE_RAW_SNAPSHOT", rawSnapshotSha256=snapshot["sha256"], inputIdentitySha256=snapshot["inputIdentity"]["sha256"],
                          componentHashes={p:m["sha256"] for p,m in snapshot["components"].items()})
            report = S.gates_only(directory, root=root)
        else:
            # A partial cache is retained as acquisition evidence, never sealed
            # or offered as the authorized execution snapshot.
            with S.outcome_firewall():
                report = formal("gates-only", root=root)
            report["acquisitionFailure"] = acquisition["failure"]
        output.update(status=report["status"], readiness=report.get("readiness", report["status"]),
                      formalGatesOnly=report, counters=report["counters"],
                      annualCoreFamilyCoverage=report.get("annualCoreFamilyCoverage", "NOT_MEASURED"))
        output["failedGates"] = report.get("gates", {}).get("reasons", [report["reason"]] if "reason" in report else [])
    except Exception as exc:  # machinery faults are INFRASTRUCTURE_ERROR, never an uncaught crash with no report
        output.update(status="INFRASTRUCTURE_ERROR", readiness="INFRASTRUCTURE_ERROR", errorType=type(exc).__name__, error=str(exc))
    output.update(boundary(root))
    S.frozen_spec(root)
    output["statements"] = ["NO HISTORICAL LABELS ACCESSED", "NO MODEL FITTING PERFORMED",
                            "NO HISTORICAL PREDICTIONS CALCULATED", "NO PORTFOLIO PERFORMANCE CALCULATED",
                            "NO EXECUTION AUTHORIZATION CREATED", "NO PERMANENT ONE-SHOT LOCK CREATED",
                            "NO HISTORICAL EXECUTION PERFORMED"]
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("raw-inputs"))
    parser.add_argument("--output", type=Path, default=Path("readiness.json"))
    parser.add_argument("--mode", choices=("collect", "replay", "verify", "gates-only"), default="collect")
    parser.add_argument("--expected-cache-sha256", default=None)
    parser.add_argument("--expected-input-identity", default=None)
    args = parser.parse_args()
    if args.mode == "replay":
        result = collect_and_gate(args.directory, key=None, fetch=no_network, replay=True,
                                  expected_cache_sha256=args.expected_cache_sha256,
                                  expected_input_identity=args.expected_input_identity)
    elif args.mode == "collect":
        result = collect_and_gate(args.directory, key=os.environ.get("KRX_API_KEY"))
    else:
        boundary(ROOT)
        S.frozen_spec(ROOT)
        if args.mode == "verify":
            result = {"status": "VERIFIED", "snapshot": S.verify_snapshot(args.directory)}
        else:
            result = S.gates_only(args.directory)
        boundary(ROOT)
    X.atomic_write(args.output, result)
    args.output.with_name(args.output.name + ".sha256").write_text(S.file_hash(args.output) + "\n")
    print(json.dumps({k:v for k,v in result.items() if k not in ("componentHashes", "formalGatesOnly", "acquisition")}, sort_keys=True))
    if isinstance(result.get("annualCoreFamilyCoverage"), dict):
        for year, row in sorted(result["annualCoreFamilyCoverage"].items()):
            print("coverage", year, row["pitUniverseDenominator"], {n: round(v["share"], 4) for n, v in row["families"].items()})
    print("loaderEquivalence", json.dumps(result.get("loaderEquivalence"), sort_keys=True))
    print("snapshot", result.get("rawSnapshotSha256"), "identity", result.get("inputIdentitySha256"),
          "components", len(result.get("componentHashes", {})))
    return 0 if result["status"] in ("READY", "VERIFIED") else 2


if __name__ == "__main__":
    raise SystemExit(main())
