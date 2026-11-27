"""Record one entry-state shadow observation and advance its paper books. PROSPECTIVE PAPER, no production effect.

    python scripts/record_entry_state_shadow.py run CHAMPION_LATEST WEEKLY_LATEST CONFIG LEDGER_STUDY_DIR [--offline]

Called from `scripts/update_ledger.py` (the paper-ledger step of the scheduled ledger workflow) through `run_isolated`, in a
child process with a timeout. It reads the last PUBLISHED weekly decision and champion artifact on signal-history, so a
new week is recorded on the run after it was published; receipts are write-once, so re-reading the same week appends
nothing. Any refusal is written to the study's own publication-status.json and never costs the paper ledger.
`pipeline/weekly_publish.py` is byte-pinned (docs/weekly-session-integrity-v1-pins.json) and is not touched.
`--offline` records decisions only and never fetches a price (used by tests and dry runs).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import entry_state_shadow_ledger as L      # noqa: E402

MJS = ROOT / "scripts" / "entry_state_shadow_observation.mjs"
CHILD_TIMEOUT_SECONDS = 600
CODE_FILES = ("scripts/entry_state_shadow_observation.mjs", "pipeline/entry_state_shadow_ledger.py",
              "scripts/record_entry_state_shadow.py")


def code_identity() -> dict:
    files = {rel: hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() for rel in CODE_FILES}
    commit = os.environ.get("GITHUB_SHA") or subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip() or None
    return {"commit": commit, "files": files}


def _status(directory: Path, **fields) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "publication-status.json").write_bytes(L.canonical(
        {"schema": "ENTRY_STATE_SHADOW_STATUS_V1", "studyId": L.STUDY, "productionEffect": "NONE",
         "atUtc": L.utc_now().strftime("%Y-%m-%dT%H:%M:%SZ"), **fields}) + b"\n")


def observe(champion: Path, weekly: Path, config: Path, *, source_commit: str, config_commit: str,
            pre_commit: bool) -> bytes:
    command = ["node", str(MJS), str(champion), str(weekly), str(config), source_commit, config_commit]
    if pre_commit:
        command.append("--pre-commit-bytes")
    done = subprocess.run(command, cwd=str(ROOT), capture_output=True, timeout=120, check=False)
    if done.returncode:
        lines = [x for x in done.stderr.decode(errors="replace").splitlines() if x.strip()]
        # Node prints the thrown message, then a stack, then its own version banner; the version is not the reason.
        reason = next((x.split(": ", 1)[1] for x in lines if re.match(r"\w*Error: ", x)), lines[-1] if lines else "NO_STDERR")
        raise RuntimeError("OBSERVATION_REFUSED: " + reason)
    return done.stdout


def live_closes(directory: Path):
    """Fixed-origin vendor index lookup; never carry units across raw adjusted vintages."""
    from pipeline.datafeed import fetch_prices
    decisions = [json.loads(s) for s in (directory / "decisions.jsonl").read_text().splitlines() if s.strip()]
    origins = {}
    for decision in decisions:
        tickers = set(decision.get("targetWeights") or {}) | {L.REGIONAL_ETF[decision["region"]]}
        for ticker in tickers:
            origins[ticker] = min(origins.get(ticker, decision["asOfDate"]), decision["asOfDate"])
    if not origins:
        raise ValueError("NO_DECISIONS_TO_VALUE")
    # The fixed signal-session denominator cancels later common rescalings.
    # Require the exact origin quote; never silently pick a new first row.
    frames = fetch_prices(sorted(origins), min(origins.values()), auto_adjust=True)
    nav_path = directory / "nav-daily.jsonl"
    prior_navs = [json.loads(s) for s in nav_path.read_text().splitlines() if s.strip()] if nav_path.exists() else []
    return L.anchored_closes(frames, origins, prior_navs)


def run(champion: Path, weekly: Path, config: Path, directory: Path, *, offline: bool = False,
        source_commit: str | None = None, config_commit: str | None = None) -> int:
    directory = Path(directory)
    code = code_identity()
    commit = source_commit or code["commit"] or "0" * 40
    try:
        raw, refusal = observe(champion, weekly, config, source_commit=commit, config_commit=config_commit or commit,
                               pre_commit=source_commit is None), None
    except RuntimeError as exc:
        # The weekly decision is rewritten daily but the champion artifact only when no session is mid-flight, so on most weekdays
        # the two published files are from different generations and cannot be paired. That concerns NEW decisions only. With a
        # stored ledger the stored book is still marked and the stored readout kept; with none, nothing exists to protect.
        if not (directory / "decisions.jsonl").exists():
            raise
        raw, refusal = None, str(exc)
    now = L.utc_now()                       # the writer's own clock, read AFTER the inputs were read: it decides the execution session
    if raw is None:
        report = {"decisions": {"appended": 0, "alreadyPresent": 0, "conflictsRefused": []},
                  "observation": {"status": "REFUSED", "reason": refusal}}
    else:
        receipts = L.decision_receipts(json.loads(raw), recorded_at=now, code=code, observation_sha256=L.sha256(raw))
        report = {"decisions": L.append_decisions(directory, receipts), "observation": {"status": "OK", "reason": None}}
    if not offline:
        report["accounting"] = L.advance(directory, now=now, close_of=live_closes(directory))
    report["maturity"] = L.maturity(directory, now=now)
    report["readout"] = L.status_report(directory, now=now)
    _status(directory, status="OK", report=report)
    print(json.dumps(report["decisions"], sort_keys=True))
    return 0


def run_isolated(champion: Path, weekly: Path, config: Path, directory: Path, *,
                 timeout: int = CHILD_TIMEOUT_SECONDS) -> int:
    command = [sys.executable, str(Path(__file__).resolve()), "run", str(champion), str(weekly), str(config),
               str(directory)]
    try:
        done = subprocess.run(command, cwd=str(ROOT), timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        _status(Path(directory), status="TIMEOUT", reason=f"CHILD_PROCESS_EXCEEDED_{timeout}_SECONDS")
        return 124
    if done.returncode:
        _status(Path(directory), status="EXCEPTION", reason=f"CHILD_PROCESS_EXITED_{done.returncode}")
    return int(done.returncode)


def hook_enabled() -> bool:
    """Only the scheduled paper-ledger workflow records; tests and local runs of weekly_publish never do."""
    return (os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("GITHUB_WORKFLOW") == "Append paper-signal ledger"
            and os.environ.get("GITHUB_REF") == "refs/heads/main")


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    offline = "--offline" in argv
    argv = [a for a in argv if a != "--offline"]
    if len(argv) == 5 and argv[0] == "envelope":
        # envelope LEDGER_STUDY_DIR STRATEGY_ID AS_OF OUT_JSON -> input for research.economic_path_readout_v1.cli --input
        _, directory, strategy_id, as_of, out = argv
        Path(out).write_text(json.dumps(L.readout_input(Path(directory), strategy_id, as_of,
                                                        source_commit=code_identity()["commit"] or "UNKNOWN"),
                                        indent=1, allow_nan=False) + "\n")
        return 0
    if len(argv) == 5 and argv[0] == "run":
        try:
            return run(*map(Path, argv[1:]), offline=offline)
        except Exception as exc:  # noqa: BLE001 - the refusal is this study's own published state
            _status(Path(argv[4]), status="REFUSED", error=f"{type(exc).__name__}: {exc}")
            print(f"entry-state shadow refused: {type(exc).__name__}: {exc}")
            return 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
