"""rp1-b-h1-state-v1 — LIVE recorder of Track B's weekly MARKET_OBSERVED state receipts (state only; no outcome, no order, no weight).

    python scripts/record_rp1_b_h1_state.py run      <study-dir>     record, then coverage, then the outcome gate
    python scripts/record_rp1_b_h1_state.py record   <study-dir>
    python scripts/record_rp1_b_h1_state.py coverage <study-dir>
    python scripts/record_rp1_b_h1_state.py outcomes <study-dir>

``scripts/update_ledger.py`` (the paper-ledger step of ledger.yml) calls ``run_isolated`` after its own work and after Track A's recorders:
this script runs in a CHILD process with a timeout, so a hung vendor read, a crash or an exception here can never hold up or fail the paper
ledger, Track A or the commit step. It needs no site artifact: the session it speaks for is decided by the writer's clock alone.

Files in ``<study-dir>`` (signal-history ``ledger/research-strategies/rp1-b-h1-state-v1/``):
    receipts.jsonl                 the evidence: append-only, hash-chained receipts (PROSPECTIVE_PAPER)
    attempts.jsonl                 non-evidence log of every in-window DEFERRED / REFUSED attempt, so a missed week says why
    coverage.json                  recorded / missed weekly sessions, state counts, H63 block geometry (signal-time facts only)
    publication-status.<step>.json one file per step; publication-status.json aggregates them (failedSteps, signalRecordState)
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import prospective_receipt_core as CORE  # noqa: E402
from pipeline import rp1_b_h1_state as B  # noqa: E402

RECEIPTS, ATTEMPTS, COVERAGE, STATUS = "receipts.jsonl", "attempts.jsonl", "coverage.json", "publication-status.json"
SCHEMA = "RP1_B_H1_STATE_STATUS_V1"
STEPS = ("record", "coverage", "outcomes")
FAILED = ("REFUSED", "EXCEPTION", "TIMEOUT")
CHILD_TIMEOUT_SECONDS = 600


def _status(directory: Path, **fields) -> None:
    """One file per step plus an aggregate; a later step never overwrites an earlier step's refusal."""
    action = fields["action"]
    payload = {"schema": SCHEMA, "studyId": B.STUDY, "runId": os.environ.get("GITHUB_RUN_ID"),
               "attemptedAt": str(CORE.system_utc_now().isoformat()), "productionEffect": "NONE", **fields}
    directory.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str) + "\n"
    (directory / f"publication-status.{action}.json").write_text(text, encoding="utf-8")
    steps = {}
    for name in (*STEPS, "hook"):
        path = directory / f"publication-status.{name}.json"
        if path.exists():
            steps[name] = json.loads(path.read_text(encoding="utf-8"))
    failed = sorted(n for n, v in steps.items() if v.get("status") in FAILED)
    record_step = steps.get("record", {})
    aggregate = {"schema": SCHEMA, "studyId": B.STUDY, "productionEffect": "NONE", "runId": os.environ.get("GITHUB_RUN_ID"),
                 "attemptedAt": payload["attemptedAt"], "status": "STEP_FAILED" if failed else "OK", "failedSteps": failed,
                 "signalRecordState": record_step.get("status", "NOT_ATTEMPTED"), "signalRecordReason": record_step.get("reason"),
                 "steps": steps}
    (directory / STATUS).write_text(json.dumps(aggregate, ensure_ascii=False, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(text, end="")


def fetch_reference(start: str):
    """The registered route (FDR_KS200) with a socket timeout, and the installed vendor package identity. Any failure is the caller's DEFERRED."""
    import FinanceDataReader as fdr

    previous = socket.getdefaulttimeout()
    socket.setdefaulttimeout(B.FETCH_TIMEOUT_SECONDS)
    try:
        frame = fdr.DataReader(B.SOURCE["symbol"], start)
    finally:
        socket.setdefaulttimeout(previous)
    return frame, "finance-datareader==" + str(getattr(fdr, "__version__", "unknown"))


def _log_attempt(directory: Path, row: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ATTEMPTS).open("ab") as stream:
        stream.write(CORE.canonical(row) + b"\n")


def read_attempts(directory: Path) -> list[dict]:
    path = directory / ATTEMPTS
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def record(directory: Path, *, clock=None, fetch=None, merged_at=None, code_identity=None) -> int:
    """LIVE. The clock is the writer's own (``prospective_receipt_core.system_utc_now``), the merge time and code identity come from git and
    the frame from the registered route; synthetic tests replace them, and nothing else."""
    clock, fetch = clock or CORE.system_utc_now, fetch or fetch_reference
    signal = None
    try:
        spec = B.load_spec()                                    # the study's own files and its scientific dependencies, or nothing
        now = clock()
        window = B.window_at(now)                               # SKIPPED outside a weekly decision session's window
        signal = window["signalDate"]
        try:
            receipts = B.read_receipts(directory / RECEIPTS, pathway=B.LIVE)
            B.verify_row_anchors(receipts, directory / RECEIPTS)    # every receipt still sits in committed history as it claims
            anchor = B.ledger_anchor(directory / RECEIPTS)          # and the working ledger extends every committed version
        except ValueError as exc:
            raise B.AttemptStop(B.REFUSED, "LEDGER_INTEGRITY_FAILED: " + str(exc)) from exc
        if signal in {r["signalDate"] for r in receipts}:      # before any download: a later run in the same window has nothing to do
            raise B.AttemptStop(B.SKIPPED, "RECEIPT_ALREADY_EXISTS: " + signal)
        floor = spec["schedule"]["firstEligibleSignalSessionFloor"]
        if signal < floor:
            raise B.AttemptStop(B.SKIPPED, "SIGNAL_BEFORE_REGISTERED_FLOOR: " + floor)
        try:
            merged = merged_at if merged_at is not None else B.registration_merged_at()
            identity = code_identity if code_identity is not None else B.live_code_identity(spec)
        except ValueError as exc:
            raise B.AttemptStop(B.REFUSED, str(exc)) from exc
        if signal < str(CORE.first_prospective_session(merged).date()):
            raise B.AttemptStop(B.SKIPPED, "SIGNAL_BEFORE_PROSPECTIVE_ELIGIBILITY: " + signal)
        try:
            frame, package = fetch(B.fetch_start(signal))
        except Exception as exc:  # noqa: BLE001 - any vendor failure is a provider gap, retried by a later run in the window
            raise B.AttemptStop(B.DEFERRED, f"PROVIDER_FETCH_FAILED: {type(exc).__name__}: {exc}") from exc
        fetched = clock()
        if CORE.utc(fetched) >= window["closesAtUtc"]:            # the download outlived the window: never a backdated receipt
            raise B.AttemptStop(B.REFUSED, "RECEIPT_WINDOW_CLOSED_DURING_RECORDING: download ended " + str(CORE.utc(fetched).isoformat()))
        receipt = B.build_receipt(frame, pathway=B.LIVE, signal_date=signal, created_at_utc=fetched, now_utc=fetched, fetched_at_utc=fetched,
                                  merged_at_utc=merged, spec=spec, spec_digest=B.spec_sha256(), code_identity=identity,
                                  vendor_package=package, previous_receipt_sha256=B.last_digest(receipts),
                                  ledger_anchor=anchor)
        try:
            receipt = B.append_live_receipt(directory / RECEIPTS, receipt, merged_at_utc=merged, clock=clock)
        except ValueError as exc:
            reason = str(exc)
            raise B.AttemptStop(B.SKIPPED if reason.startswith("RECEIPT_ALREADY_EXISTS") else B.REFUSED, reason) from exc
    except B.AttemptStop as stop:
        if signal is not None and stop.kind in (B.DEFERRED, B.REFUSED):
            _log_attempt(directory, B.attempt_row(signal_date=signal, kind=stop.kind, reason=stop.reason, detail=stop.detail,
                                                  attempted_at_utc=clock(), run_id=os.environ.get("GITHUB_RUN_ID")))
        _status(directory, action="record", status=stop.kind, reason=stop.reason, detail=stop.detail, signalDate=signal)
        return 1 if stop.kind == B.REFUSED else 0
    except ValueError as exc:      # load_spec and the window check raise plain ValueError on a moved dependency or calendar
        _status(directory, action="record", status=B.REFUSED, reason=str(exc), signalDate=signal)
        return 1
    _status(directory, action="record", status=B.RECORDED, signalDate=receipt["signalDate"], executionDate=receipt["executionDate"],
            receiptSha256=receipt["receiptSha256"], adverse=receipt["state"]["adverse"], undeterminedReasons=receipt["undeterminedReasons"])
    return 0


def coverage(directory: Path, *, clock=None, merged_at=None) -> int:
    """Written on every run, receipts or not: a first eligible week that closed with only DEFERRED attempts (or none) is MISSED from the
    moment its window closes, not from whenever a later week first records. The registration comes from the first receipt when one exists,
    otherwise from git (main-only, fail closed); an unregistered spec has nothing due.

    Every REGISTERED report is preceded by the same history verification the record step runs, zero rows included: a working ledger that
    was emptied or deleted after a receipt was committed must not read as weeks that were merely missed. A failure publishes
    LEDGER_INTEGRITY_FAILED, never a normal report."""
    clock = clock or CORE.system_utc_now
    spec = B.load_spec()
    path = directory / RECEIPTS
    try:
        receipts = B.read_receipts(path, pathway=B.LIVE)
    except ValueError as exc:
        return _integrity_failed(directory, exc)
    if receipts:
        merged, floor = receipts[0]["authorization"]["mergedAtUtc"], receipts[0]["authorization"]["registeredFloor"]
    else:
        floor = spec["schedule"]["firstEligibleSignalSessionFloor"]
        try:
            merged = merged_at if merged_at is not None else B.registration_merged_at()
        except ValueError as exc:
            _write_coverage(directory, {"registration": "NOT_REGISTERED", "reason": str(exc), "dueSessions": 0, "recordedSessions": 0,
                                        "missedSessions": []})
            _status(directory, action="coverage", status="NOT_REGISTERED", reason=str(exc))
            return 0
    try:
        B.verify_row_anchors(receipts, path)
        anchor = B.ledger_anchor(path)
    except ValueError as exc:
        return _integrity_failed(directory, exc)
    report = B.coverage(receipts, read_attempts(directory), merged_at_utc=merged, floor=floor, now_utc=clock(),
                        horizon=spec["outcomeEvaluation"]["horizonSessions"],
                        min_blocks=spec["outcomeEvaluation"]["inheritedFixed"]["minNonOverlappingBlocksPerState"])
    report.update({"registration": "REGISTERED", "integrity": "VERIFIED", "ledgerAnchor": anchor})
    _write_coverage(directory, report)
    _status(directory, action="coverage", status="REPORTED", recorded=report["recordedSessions"], due=report["dueSessions"],
            missed=len(report["missedSessions"]), inferenceStatus=report["blockGeometry"]["inferenceStatus"])
    return 0


def _integrity_failed(directory: Path, exc: Exception) -> int:
    """No session counts are published from a ledger whose history does not verify; the previous coverage.json is replaced, not kept."""
    reason = "LEDGER_INTEGRITY_FAILED: " + str(exc)
    _write_coverage(directory, {"registration": None, "integrity": "FAILED", "reason": reason})
    _status(directory, action="coverage", status=B.REFUSED, reason=reason)
    return 1


def _write_coverage(directory: Path, report: dict) -> None:
    report = {**report, "schema": "RP1_B_H1_STATE_COVERAGE_V1", "studyId": B.STUDY, "evidence": False, "productionEffect": "NONE"}
    directory.mkdir(parents=True, exist_ok=True)
    (directory / COVERAGE).write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def outcomes(directory: Path) -> int:
    gate = B.outcome_gate(B.load_spec())
    _status(directory, action="outcomes", status=gate["status"], openDecisions=gate["openDecisions"], computed=False)
    return 0


def run_all(directory: Path) -> int:
    """record, then coverage, then the outcome gate; each runs even if an earlier one failed."""
    codes = []
    for name, step in zip(STEPS, (lambda: record(directory), lambda: coverage(directory), lambda: outcomes(directory))):
        try:
            codes.append(step())
        except Exception as exc:  # noqa: BLE001 - one step's failure is reported, not fatal to the next
            print(f"rp1-b-h1-state step failed: {type(exc).__name__}: {exc}")
            _status(directory, action=name, status="EXCEPTION", error=f"{type(exc).__name__}: {exc}")
            codes.append(1)
    return max(codes)


def run_isolated(directory: Path, *, timeout=CHILD_TIMEOUT_SECONDS, command=None) -> int:
    """Run ``run_all`` in a child process. A timeout or a crash is written as this study's own hook failure and returned as a non-zero code;
    it never raises into the caller and never touches anything outside ``directory``."""
    directory = Path(directory)
    command = command or [sys.executable, str(Path(__file__).resolve()), "run", str(directory)]
    try:
        done = subprocess.run(command, cwd=str(ROOT), timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        _status(directory, action="hook", status="TIMEOUT", reason=f"CHILD_PROCESS_EXCEEDED_{timeout}_SECONDS")
        return 124
    if done.returncode not in (0, 1):
        _status(directory, action="hook", status="EXCEPTION", reason=f"CHILD_PROCESS_EXITED_{done.returncode}")
    elif (directory / "publication-status.hook.json").exists():
        _status(directory, action="hook", status="OK", reason=None)
    return int(done.returncode)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    actions = {"run": run_all, "record": record, "coverage": coverage, "outcomes": outcomes}
    if len(argv) == 2 and argv[0] in actions:
        return actions[argv[0]](Path(argv[1]))
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
