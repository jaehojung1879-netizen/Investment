"""Record one entry-state shadow observation and advance its paper books. PROSPECTIVE PAPER, no production effect.

    python scripts/record_entry_state_shadow.py run CHAMPION_LATEST WEEKLY_LATEST CONFIG LEDGER_STUDY_DIR [--offline]

Called from `pipeline.weekly_publish` (the paper-ledger workflow's weekly step) through `run_isolated`, in a child process
with a timeout; any refusal is written to the study's own publication-status.json and never costs the weekly decision.
`--offline` records decisions only and never fetches a price (used by tests and dry runs).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
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
        raise RuntimeError("OBSERVATION_REFUSED: " + done.stderr.decode(errors="replace").strip().splitlines()[-1])
    return done.stdout


def live_closes(directory: Path):
    """Close lookup backed by one vendor fetch for every ticker any decision can hold."""
    from pipeline.datafeed import fetch_prices
    decisions = [json.loads(s) for s in (directory / "decisions.jsonl").read_text().splitlines() if s.strip()]
    tickers = sorted({t for d in decisions for t in (d.get("targetWeights") or {})}
                     | set(L.REGIONAL_ETF.values()) | set(L.SEPARATE_COMPARISON.values()))
    start = min(d["asOfDate"] for d in decisions)
    frames = fetch_prices(tickers, start)
    series = {t: f["Close"] for t, f in frames.items() if f is not None and "Close" in f}

    def close_of(ticker, session):
        s = series.get(ticker)
        if s is None:
            return None
        index = s.index.tz_localize(None) if getattr(s.index, "tz", None) else s.index
        hit = s[index.strftime("%Y-%m-%d") == session]
        return float(hit.iloc[-1]) if len(hit) and hit.iloc[-1] == hit.iloc[-1] else None
    return close_of


def run(champion: Path, weekly: Path, config: Path, directory: Path, *, offline: bool = False,
        source_commit: str | None = None, config_commit: str | None = None) -> int:
    directory = Path(directory)
    code = code_identity()
    commit = source_commit or code["commit"] or "0" * 40
    raw = observe(champion, weekly, config, source_commit=commit, config_commit=config_commit or commit,
                  pre_commit=source_commit is None)
    observation = json.loads(raw)
    now = L.utc_now()
    receipts = L.decision_receipts(observation, recorded_at=now, code=code, observation_sha256=L.sha256(raw))
    report = {"decisions": L.append_decisions(directory, receipts)}
    if not offline:
        report["accounting"] = L.advance(directory, now=now, close_of=live_closes(directory))
    report["maturity"] = L.maturity(directory, now=now)
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
