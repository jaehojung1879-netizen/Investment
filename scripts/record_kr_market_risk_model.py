"""kr-market-risk-model-v1 — LIVE recorder of the weekly PROSPECTIVE_PAPER receipts (state and multipliers only; no outcome, no order, no weight).

    python scripts/record_kr_market_risk_model.py run <study-dir>

It reuses, unchanged: ``kr_market_risk_model.layer_states`` (the sealed state machine), ``kr_market_risk_model_receipts.build_receipt`` /
``append_receipt`` (the sealed, append-only contract), ``rp1_b_h1_state.window_at`` (which weekly session a run may speak for, decided by the
writer's clock alone) and ``prospective_receipt_core.check_timing`` (receipt after the signal close, before the next open).

Authorization is ``research_specs/kr-market-risk-model-v1-prospective-registration.json``: its commit time on ``origin/main`` is the merge time
that decides the first prospective session, and it pins the sealed spec, the nomination result and every code file this recorder runs.
``scripts/update_ledger.py`` calls ``run_isolated`` (a child process with a timeout), so a hung vendor read or a crash can never hold up or fail the
paper ledger. Nothing here trades, sizes or promotes anything: ``productionEffect`` is NONE.

Files in ``<study-dir>`` (signal-history ``ledger/research-strategies/kr-market-risk-model-v1/``):
    receipts.jsonl            the evidence (append-only, one receipt per weekly decision session)
    attempts.jsonl            non-evidence log of every DEFERRED / REFUSED attempt in a window
    publication-status.json   what the last run did
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import kr_market_risk_anatomy as M  # noqa: E402
from pipeline import kr_market_risk_model as K  # noqa: E402
from pipeline import kr_market_risk_model_receipts as R  # noqa: E402
from pipeline import kr_selection_challenger as V1  # noqa: E402
from pipeline import prospective_receipt_core as CORE  # noqa: E402
from pipeline import rp1_b_h1_state as B  # noqa: E402

REGISTRATION_PATH = "research_specs/kr-market-risk-model-v1-prospective-registration.json"
RECEIPTS, ATTEMPTS, STATUS = "receipts.jsonl", "attempts.jsonl", "publication-status.json"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
FRED_SERIES = ("DGS10", "DGS3MO", "VIXCLS")
REFERENCE_START = "1990-01-01"      # the sealed execution's frozen expanding-history start
FETCH_TIMEOUT_SECONDS = 30
CHILD_TIMEOUT_SECONDS = 600
RECORDED, SKIPPED, DEFERRED, REFUSED = B.RECORDED, B.SKIPPED, B.DEFERRED, B.REFUSED


def file_sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_registration(root=ROOT) -> dict:
    """The registration, with every pin re-verified. A changed file is a new registration, never an edit."""
    root = Path(root)
    reg = json.loads((root / REGISTRATION_PATH).read_text(encoding="utf-8"))
    if reg.get("studyId") != K.STUDY or reg.get("status") != "REGISTERED_PROSPECTIVE_RECORDING" or reg.get("productionEffect") != "NONE":
        raise ValueError("REGISTRATION_IDENTITY_MISMATCH")
    if file_sha256(root / reg["sealedSpec"]["path"]) != reg["sealedSpec"]["sha256"]:
        raise ValueError("SEALED_SPEC_CHANGED")
    if file_sha256(root / reg["nominationResult"]["path"]) != reg["nominationResult"]["sha256"]:
        raise ValueError("NOMINATION_RESULT_CHANGED")
    for rel, pinned in sorted(reg["codeFileHashes"].items()):
        if file_sha256(root / rel) != pinned:
            raise ValueError("CODE_CHANGED_SINCE_REGISTRATION: " + rel)
    return reg


def registration_merged_at(root=ROOT) -> str:
    return V1.registration_from_git(root, REGISTRATION_PATH)["mergedAtUtc"]


def live_code_identity(reg: dict, root=ROOT) -> dict:
    head = V1._git("rev-parse", "HEAD", root=root).stdout.strip()
    if not CORE.is_git_sha(head):
        raise ValueError("CODE_COMMIT_UNKNOWN")
    files = {rel: file_sha256(Path(root) / rel) for rel in sorted(reg["codeFileHashes"])}
    files[REGISTRATION_PATH] = file_sha256(Path(root) / REGISTRATION_PATH)
    return {"commitSha": head, "files": files, "sealedSpecSha256": reg["sealedSpec"]["sha256"], "calendarVersion": B.RC.CALENDAR_VERSION}


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #
def fetch_fred(series_id: str) -> pd.Series:
    """Public FRED CSV, observation-dated; '.' is a missing observation. Any failure is the caller's DEFERRED."""
    request = urllib.request.Request(FRED_URL + series_id, headers={"User-Agent": "kr-market-risk-model-recorder"})
    previous = socket.getdefaulttimeout()
    socket.setdefaulttimeout(FETCH_TIMEOUT_SECONDS)
    try:
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:   # noqa: S310 - fixed https host
            text = response.read().decode("utf-8")
    finally:
        socket.setdefaulttimeout(previous)
    frame = pd.read_csv(io.StringIO(text), na_values=["."])
    values = pd.Series(pd.to_numeric(frame.iloc[:, 1], errors="coerce").to_numpy(), index=pd.to_datetime(frame.iloc[:, 0]), name=series_id)
    return values.dropna()


def fetch_ks200(start: str) -> pd.Series:
    import FinanceDataReader as fdr

    previous = socket.getdefaulttimeout()
    socket.setdefaulttimeout(FETCH_TIMEOUT_SECONDS)
    try:
        frame = fdr.DataReader(B.SOURCE["symbol"], start)
    finally:
        socket.setdefaulttimeout(previous)
    return pd.Series(frame["Close"].astype(float).to_numpy(), index=pd.DatetimeIndex(frame.index).normalize(), name="KS200").dropna()


def fetch_inputs(signal_date: str) -> dict:
    out = {"KS200": fetch_ks200(REFERENCE_START)}
    for sid in FRED_SERIES:
        out[sid] = fetch_fred(sid)
    return out


def input_identity(series: pd.Series, signal_date: str) -> str:
    """SHA-256 of the canonical (date, value) rows observed on or before the signal date: later rows of a refreshed vendor file cannot move it."""
    rows = [[str(d.date()), float(v)] for d, v in series.loc[:pd.Timestamp(signal_date)].items()]
    return hashlib.sha256(CORE.canonical(rows)).hexdigest()


def compute_states(inputs: dict, signal_date: str) -> tuple[dict, dict, dict]:
    """(states, layerInputs, inputIdentities) at the signal session from signal-time observations only."""
    day = pd.Timestamp(signal_date)
    close = inputs["KS200"].loc[:day]
    if close.empty or close.index[-1] != day:
        raise B.AttemptStop(DEFERRED, "KS200_CLOSE_FOR_SIGNAL_SESSION_NOT_YET_SERVED")
    sessions = M.kr_sessions(str(close.index[0].date()), signal_date)
    both = pd.concat([inputs["DGS10"], inputs["DGS3MO"]], axis=1).dropna()
    spread = (both.iloc[:, 0] - both.iloc[:, 1]).loc[:day]
    vix = inputs["VIXCLS"].loc[:day]
    frame = K.layer_states(close.reindex(sessions), spread, vix, sessions)
    row = frame.loc[day]

    def cell(name):
        value = row[name]
        return None if value is None or (isinstance(value, float) and not math.isfinite(value)) else value

    states = {"slow": cell("slow"), "transition": cell("transition"), "fast": cell("fast")}
    layer_inputs = {"spreadAtSample": cell("spreadAtSample"), "vixPercentile": cell("vixPercentile"), "vol63": cell("vol63")}
    layer_inputs = {k: (None if v is None else float(v)) for k, v in layer_inputs.items()}
    identities = {"KS200": input_identity(inputs["KS200"], signal_date)}
    identities.update({sid: input_identity(inputs[sid], signal_date) for sid in FRED_SERIES})
    return states, layer_inputs, identities


# --------------------------------------------------------------------------- #
# Record
# --------------------------------------------------------------------------- #
def _write_status(directory: Path, **fields) -> None:
    payload = {"schema": "KR_MARKET_RISK_MODEL_V1_STATUS", "studyId": K.STUDY, "productionEffect": "NONE", "runId": os.environ.get("GITHUB_RUN_ID"),
               "attemptedAt": str(CORE.system_utc_now().isoformat()), **fields}
    directory.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str) + "\n"
    (directory / STATUS).write_text(text, encoding="utf-8")
    print(text, end="")


def _log_attempt(directory: Path, *, signal_date, kind, reason, now) -> None:
    row = {"studyId": K.STUDY, "evidence": False, "signalDate": signal_date, "status": kind, "reason": reason,
           "attemptedAtUtc": str(CORE.utc(now).isoformat()), "runId": os.environ.get("GITHUB_RUN_ID")}
    row["rowSha256"] = hashlib.sha256(CORE.canonical(row)).hexdigest()
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ATTEMPTS).open("ab") as stream:
        stream.write(CORE.canonical(row) + b"\n")


def record(directory: Path, *, clock=None, fetch=None, merged_at=None, code_identity=None, root=ROOT) -> int:
    """LIVE. The clock is the writer's own; the merge time and code identity come from git; synthetic tests replace the injectable parts."""
    clock, fetch = clock or CORE.system_utc_now, fetch or fetch_inputs
    signal = None
    try:
        reg = load_registration(root)
        now = clock()
        window = B.window_at(now)                                   # SKIPPED outside a weekly decision session's window
        signal = window["signalDate"]
        try:
            rows = R.read_ledger(directory / RECEIPTS)              # every existing receipt still verifies its own digest
        except ValueError as exc:
            raise B.AttemptStop(REFUSED, "LEDGER_INTEGRITY_FAILED: " + str(exc)) from exc
        if signal in {r["signalDate"] for r in rows}:
            raise B.AttemptStop(SKIPPED, "RECEIPT_ALREADY_EXISTS: " + signal)
        if signal < reg["firstEligibleSignalSessionFloor"]:
            raise B.AttemptStop(SKIPPED, "SIGNAL_BEFORE_REGISTERED_FLOOR: " + reg["firstEligibleSignalSessionFloor"])
        try:
            merged = merged_at if merged_at is not None else registration_merged_at(root)
            identity = code_identity if code_identity is not None else live_code_identity(reg, root)
        except ValueError as exc:
            raise B.AttemptStop(REFUSED, str(exc)) from exc
        if signal < str(CORE.first_prospective_session(merged).date()):
            raise B.AttemptStop(SKIPPED, "SIGNAL_BEFORE_PROSPECTIVE_ELIGIBILITY: " + signal)
        try:
            inputs = fetch(signal)
        except Exception as exc:  # noqa: BLE001 - any vendor failure is a provider gap, retried by a later run in the window
            raise B.AttemptStop(DEFERRED, f"PROVIDER_FETCH_FAILED: {type(exc).__name__}: {exc}") from exc
        states, layer_inputs, identities = compute_states(inputs, signal)
        fetched = clock()
        if CORE.utc(fetched) >= window["closesAtUtc"]:
            raise B.AttemptStop(REFUSED, "RECEIPT_WINDOW_CLOSED_DURING_RECORDING")
        previous = rows[-1]["candidateMultipliers"] if rows else None
        try:
            receipt = R.build_receipt(signal_date=signal, input_identities=identities, layer_inputs=layer_inputs, states=states,
                                      spec_sha256=reg["sealedSpec"]["sha256"], code_identity=identity, created_at_utc=str(CORE.utc(fetched).isoformat()),
                                      final_architecture=reg["finalArchitecture"], nomination_source=reg["nominationSource"], previous_multipliers=previous)
            CORE.check_timing(signal_date=signal, created_at_utc=receipt["createdAtUtc"], now_utc=clock(), merged_at_utc=merged)
            R.append_receipt(directory / RECEIPTS, receipt)
        except ValueError as exc:
            reason = str(exc)
            raise B.AttemptStop(SKIPPED if reason.startswith("RECEIPT_ALREADY_EXISTS") else REFUSED, reason) from exc
    except B.AttemptStop as stop:
        if signal is not None and stop.kind in (DEFERRED, REFUSED):
            _log_attempt(directory, signal_date=signal, kind=stop.kind, reason=stop.reason, now=clock())
        _write_status(directory, status=stop.kind, reason=stop.reason, signalDate=signal)
        return 1 if stop.kind == REFUSED else 0
    except ValueError as exc:       # registration pins, calendar
        _write_status(directory, status=REFUSED, reason=str(exc), signalDate=signal)
        return 1
    _write_status(directory, status=RECORDED, signalDate=receipt["signalDate"], executionDate=receipt["executionDate"], receiptSha256=receipt["receiptSha256"],
                  states=receipt["states"], candidateMultipliers=receipt["candidateMultipliers"])
    return 0


def run_all(directory: Path) -> int:
    try:
        return record(directory)
    except Exception as exc:  # noqa: BLE001 - reported, never fatal to the caller
        _write_status(Path(directory), status="EXCEPTION", reason=f"{type(exc).__name__}: {exc}")
        return 1


def run_isolated(directory: Path, *, timeout=CHILD_TIMEOUT_SECONDS, command=None) -> int:
    """Run ``run_all`` in a child process. A timeout or a crash is written as this study's own status and returned as a non-zero code; it never
    raises into the caller and never touches anything outside ``directory``."""
    directory = Path(directory)
    command = command or [sys.executable, str(Path(__file__).resolve()), "run", str(directory)]
    try:
        done = subprocess.run(command, cwd=str(ROOT), timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        _write_status(directory, status="TIMEOUT", reason=f"CHILD_PROCESS_EXCEEDED_{timeout}_SECONDS")
        return 124
    if done.returncode not in (0, 1):
        _write_status(directory, status="EXCEPTION", reason=f"CHILD_PROCESS_EXITED_{done.returncode}")
    return int(done.returncode)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) == 2 and argv[0] == "run":
        return run_all(Path(argv[1]))
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
