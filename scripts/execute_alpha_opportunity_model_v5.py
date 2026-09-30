"""Execution CLI for the SEALED `alpha-opportunity-model-v5` KR preregistration.

THIS IS NOT THE PREREGISTRATION'S SEALED ENTRY POINT. `scripts/run_alpha_opportunity_model_v5.py`
stays byte-identical to what PR #174 merged and its `--execute` still refuses. This script calls
`pipeline.alpha_opportunity_v5_spec.load_sealed` first, as a read-only proof that the protocol it
executes is exactly the one that was reviewed, then hands control to the reviewed harness in
`pipeline/alpha_opportunity_v5_execution.py`.

MODES
  --print-code-identity   the harness file hashes and the diagnostic-spec digest an operator authorization pins.
                          Reads nothing else.
  --freeze-only           every identity check; reads no price, label or outcome; prints the frozen identity.
  --stop-before-labels    the PRE-LABEL GATES on the real inputs, then stops. Builds no label, fits nothing.
                          Its artifact is never a substantive result and closes nothing. It exists so that
                          the one authorized run is not spent discovering an input fact (a coverage or
                          depth gate) that no outcome could have changed.
  --execute               the one formal historical execution. Refused unless ALL hold: it runs inside
                          GitHub Actions on refs/heads/main; the operator authorization file exists, names
                          this spec digest, authorizes exactly one execution and pins these harness file
                          hashes; and no committed result exists. The authorization file is NOT part of the
                          change that introduced this script.

The formal run is PRIMARY FIRST: the complete registered result is built, canonicalised and hashed before the
supplemental descriptive diagnostics (`research_specs/alpha-opportunity-model-v5-diagnostics-v1.json`) run on copies.
A diagnostic failure is reported as DIAGNOSTIC_ERROR beside the unchanged primary result and authorises no retry.
Diagnostics cannot be skipped in a formal run and the authorization pins their spec digest.

A scientific verdict (PASS / FAIL / INCONCLUSIVE / DATA_INSUFFICIENT) is a successful process (exit 0);
only INFRASTRUCTURE_ERROR exits non-zero, and the artifact is written either way. A refusal before the
identities are frozen (a moved seal, a missing authorization) raises and writes no artifact: it is not an
attempt.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import alpha_opportunity_v5_diagnostics as DIAG  # noqa: E402
from pipeline import alpha_opportunity_v5_evidence as EV  # noqa: E402
from pipeline import alpha_opportunity_v5_execution as X  # noqa: E402
from pipeline import alpha_opportunity_v5_spec as S5  # noqa: E402
from pipeline import kr_repaired_accounting_snapshot as K  # noqa: E402
from pipeline.alpha_opportunity_spec import digest, read_json  # noqa: E402

AUTHORIZATION = ROOT / "research_specs/alpha-opportunity-model-v5-execution-authorization.json"
COMMITTED_RESULT = ROOT / "docs/results/alpha-opportunity-model-v5-result.json"
GATES_ONLY_NAME = "alpha-opportunity-model-v5-gates-only.json"
SURVIVORSHIP_AUDIT = ROOT / "docs/results/alpha-opportunity-model-v3-survivorship-audit.json"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


class Refusal(RuntimeError):
    """The run may not start. Nothing has been read; nothing is written."""


def verify_authorization(path, *, spec_sha256, harness_files, diagnostic_spec_sha256,
                         committed_result=COMMITTED_RESULT):
    """The operator's explicit, single-use authorization, tied to the reviewed harness bytes and to the frozen
    supplemental diagnostic spec."""
    path = Path(path)
    if Path(committed_result).exists():
        raise Refusal("A_COMMITTED_V5_RESULT_ALREADY_EXISTS: the run is one-shot")
    if not path.is_file():
        raise Refusal("AUTHORIZATION_MISSING: " + path.name)
    record = json.loads(path.read_text())
    checks = (record.get("studyId") == S5.STUDY, record.get("specSha256") == spec_sha256,
              record.get("authorizedExecutions") == 1, bool(str(record.get("authorizedBy", "")).strip()),
              record.get("harnessFiles") == harness_files,
              record.get("diagnosticSpecSha256") == diagnostic_spec_sha256)
    if not all(checks):
        raise Refusal("AUTHORIZATION_DOES_NOT_MATCH_SPEC_OR_HARNESS")
    return record


def require_actions_main(env=os.environ):
    if env.get("GITHUB_ACTIONS") != "true":
        raise Refusal("FORMAL_EXECUTION_ONLY_FROM_THE_ACTIONS_WORKFLOW")
    if env.get("GITHUB_REF") != "refs/heads/main":
        raise Refusal("FORMAL_EXECUTION_ONLY_FROM_MAIN: " + str(env.get("GITHUB_REF")))


def library_versions():
    import numpy
    import pandas
    import scipy
    import sklearn
    return {"python": sys.version.split()[0], "numpy": numpy.__version__, "pandas": pandas.__version__,
            "scipy": scipy.__version__, "scikit-learn": sklearn.__version__}


def make_guard(*, spec, spec_path, sealed, input_root, merged_dir, v4_spec, frozen_hash, expected_signal_history_sha,
               diagnostic_sha):
    pin = spec["inputs"]["krAccounting"]
    return X.IdentityGuard({
        "spec": lambda: X.spec_identity(spec_path, sealed),
        "sealedClosureAndPriors": lambda: digest(S5.load_sealed(spec_path, expected_hash=sealed, root=ROOT)),
        "krAccountingSnapshot": lambda: X.verify_snapshot_dir(pin, merged_dir),
        "sealedRawInputs": lambda: X.verify_raw_inputs(spec, input_root,
                                                       expected_signal_history_sha=expected_signal_history_sha),
        "calibratedInference": lambda: X.calibration_identity(spec, ROOT),
        "terminalActionExecutionSnapshot": X.foundation_identity_fn(v4_spec, ROOT, frozen_hash),
        "harnessCode": lambda: X.harness_file_hashes(ROOT),
        "diagnosticSpec": lambda: digest(DIAG.load_diagnostic_spec(expected_hash=diagnostic_sha)),
    })


def make_prepare(*, spec, runtime_spec, input_root, merged_dir, foundation_snapshot):
    """PIT features and prices, read once, before the gates. No forward label is built here."""
    def prepare():
        from pipeline import alpha_opportunity_v4_execution as X4
        from pipeline import regional_alpha_features as SOURCES
        ledger = Path(input_root) / "ledger"
        manifest, prices, _, _ = SOURCES.load_inputs(ledger)
        if manifest["sha256"] != spec["inputs"]["sealedRaw"]["replayManifestSha256"]:
            raise ValueError("INPUT_MANIFEST_CHANGED_MID_RUN")
        raw = X.load_snapshot_raw(merged_dir)
        shares = X.load_kr_shares(ledger)
        frame = X4.build_kr_matrix(prices, X4.load_kr_memberships(ledger), raw, shares,
                                   start=runtime_spec["walkForward"]["featureStart"],
                                   through=runtime_spec["dataCutoff"])
        frame = X.attach_tradability(frame, prices, runtime_spec)
        terminated = [r["code"] for r in read_json(SURVIVORSHIP_AUDIT)["krTerminations"]]
        return frame, prices, X.completeness_map_from(foundation_snapshot), terminated
    return prepare


def execute(args) -> dict:
    formal = args.execute
    spec = S5.load_sealed(args.spec, expected_hash=args.sealed_sha256)
    diag = DIAG.load_diagnostic_spec(expected_hash=args.diagnostic_sha256)
    v4_spec = read_json(ROOT / S5.V4_SPEC)
    code = X.code_identity(ROOT)
    if formal:
        require_actions_main()
        verify_authorization(args.authorization, spec_sha256=args.sealed_sha256, harness_files=code["harnessFiles"],
                             diagnostic_spec_sha256=args.diagnostic_sha256)
    output = Path(args.output).resolve() if args.output else None
    if output is not None and (output.exists() or output.is_relative_to(ROOT)):
        raise Refusal("OUTPUT_MUST_BE_NEW_AND_OUTSIDE_THE_REPOSITORY")
    runtime_spec = X.build_runtime_spec(spec)
    foundation, foundation_snapshot = X.freeze_foundation(v4_spec, ROOT)
    with tempfile.TemporaryDirectory() as tmp:
        dirs = K.materialize_from_git(ROOT, Path(tmp), spec["inputs"]["krAccounting"]["sourceCommit"])
        guard = make_guard(spec=spec, spec_path=args.spec, sealed=args.sealed_sha256, input_root=args.input_root,
                           merged_dir=dirs["merged"], v4_spec=v4_spec,
                           frozen_hash=foundation["frozenExecutionSnapshotHash"],
                           expected_signal_history_sha=args.expected_signal_history_sha,
                           diagnostic_sha=args.diagnostic_sha256)
        frozen = guard.freeze()
        if args.freeze_only:
            return {"frozenIdentity": frozen, "frozenSha256": guard.frozen_digest, "foundation": foundation,
                    "outcomeAccess": "NONE"}
        # The attempt block is provenance of THIS attempt and is the only part of `provenance` outside the
        # substantive digest: the same frozen code hashes and inputs must reproduce the same result digest
        # whichever commit or run happened to carry them.
        provenance = {"codeIdentity": code, "libraries": library_versions(),
                      "attempt": {"attemptId": args.attempt_id, "executionCodeCommitSha": git("rev-parse", "HEAD"),
                                  "executionCodeDirty": bool(git("status", "--porcelain", "--untracked-files=no"))},
                      "sealedSignalHistoryCommit": spec["inputs"]["sealedRaw"]["signalHistoryCommit"],
                      "krAccountingSourceCommit": spec["inputs"]["krAccounting"]["sourceCommit"],
                      "diagnosticSpecSha256": args.diagnostic_sha256}
        run_kwargs = dict(
            spec=spec, spec_sha=args.sealed_sha256, runtime_spec=runtime_spec,
            prepare=make_prepare(spec=spec, runtime_spec=runtime_spec, input_root=args.input_root,
                                 merged_dir=dirs["merged"], foundation_snapshot=foundation_snapshot),
            guard=guard, calibration=X.calibration_params(ROOT), mode=X.FORMAL if formal else X.GATES_ONLY,
            provenance=provenance, foundation=foundation)
        primary_name = X.RESULT_NAME if formal else GATES_ONLY_NAME

        def persist_primary(data: bytes):
            write_primary(Path(args.output).resolve(), primary_name, data)

        return DIAG.execute_with_diagnostics(run_kwargs=run_kwargs, diag=diag if formal else None,
                                             diag_sha=args.diagnostic_sha256, harness_hashes=code["harnessFiles"],
                                             persist_primary=persist_primary)


def _atomic_write(path: Path, data: bytes):
    """Write-then-rename in the same directory with fsync, so a reader (or a crash) sees either no file or the whole one."""
    tmp = path.with_name(path.name + ".partial")
    with open(tmp, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_primary(output: Path, name: str, data: bytes):
    """Make the PRIMARY result durable. Called BEFORE any supplemental diagnostic runs; the file is never rewritten."""
    output.mkdir(parents=True, exist_ok=True)
    target = output / name
    if target.exists():
        raise Refusal("PRIMARY_RESULT_ALREADY_EXISTS: it is written once and never overwritten")
    _atomic_write(target, data)


def write_diagnostics(outcome: dict, output: Path):
    """Diagnostic artifacts and their references, in a subdirectory, never at (or over) a primary path."""
    artifacts = dict(outcome["diagnosticArtifacts"])
    if outcome.get("referencesBytes") is not None:
        artifacts[DIAG.REFERENCES_NAME] = outcome["referencesBytes"]
    if not artifacts:
        return
    folder = (output / "diagnostics").resolve()
    folder.mkdir(exist_ok=True)
    for name, data in artifacts.items():
        target = (folder / name).resolve()
        if target.parent != folder or name in (X.RESULT_NAME, GATES_ONLY_NAME):
            raise Refusal("DIAGNOSTIC_ARTIFACT_MAY_NOT_TOUCH_A_PRIMARY_PATH: " + name)
        _atomic_write(target, data)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--spec", type=Path, default=S5.DEFAULT_SPEC)
    p.add_argument("--sealed-sha256")
    p.add_argument("--diagnostic-sha256", help="digest of research_specs/alpha-opportunity-model-v5-diagnostics-v1.json")
    p.add_argument("--input-root", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--authorization", type=Path, default=AUTHORIZATION)
    p.add_argument("--expected-signal-history-sha")
    p.add_argument("--attempt-id", default="local")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--print-code-identity", action="store_true")
    mode.add_argument("--freeze-only", action="store_true")
    mode.add_argument("--stop-before-labels", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = p.parse_args(argv)
    if args.print_code_identity:
        diag_sidecar = DIAG.DEFAULT_SPEC.with_suffix(".sha256").read_text().strip()
        print(json.dumps({"harnessFiles": X.code_identity(ROOT)["harnessFiles"], "diagnosticSpecSha256": diag_sidecar},
                         sort_keys=True, indent=2))
        return 0
    if not args.sealed_sha256 or not args.diagnostic_sha256 or args.input_root is None:
        p.error("--sealed-sha256, --diagnostic-sha256 and --input-root are required")
    if not args.freeze_only and args.output is None:
        p.error("--output is required")
    result = execute(args)
    if args.freeze_only:
        print(json.dumps(result, sort_keys=True))
        return 0
    outcome = result
    output = Path(args.output).resolve()
    written = json.loads(outcome["primaryBytes"])          # already durable on disk (written before diagnostics ran)
    write_diagnostics(outcome, output)
    print(json.dumps({"overallStatus": written["overallStatus"], "claims": written["claims"],
                      "diagnosticStatus": outcome["diagnosticStatus"],
                      "counters": written["ordering"]["counters"], "executionMode": written["executionMode"],
                      "substantiveResult": written["substantiveResult"],
                      "substantiveResultSha256": written["resultDigests"]["substantiveResultSha256"]},
                     sort_keys=True))
    return 1 if written["overallStatus"] == EV.INFRASTRUCTURE_ERROR else 0


if __name__ == "__main__":
    raise SystemExit(main())
