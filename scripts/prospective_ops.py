"""Operations CLI for the prospective-research ledger (status / guard / verify-receipt). Read-only over every receipt file.

    python scripts/prospective_ops.py status --ledger-ref origin/signal-history --as-of 2026-11-25T12:00:00Z --out status.json
    python scripts/prospective_ops.py guard --study kr-corporate-information-events-v1 --ledger-ref origin/signal-history
    python scripts/prospective_ops.py verify-receipt --study kr-corporate-information-events-v1 --session 2026-11-26 --ledger-ref origin/signal-history

Exit codes: status 1 only when an ENABLED study owes an alert; guard 2 on REFUSE; verify-receipt 3 when the session is not verifiably recorded.
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import prospective_ops as ops  # noqa: E402
from pipeline import replay_calendar as calendar  # noqa: E402

REGISTRY = ROOT / "research" / "prospective_ops" / "registry.json"


def git(*args, cwd=ROOT, check=True):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check)


def read_rows(ref, path):
    """Rows of a JSON Lines ledger at an exact ref, or None when the file is absent (absence is never zero rows)."""
    result = git("show", f"{ref}:{path}", check=False)
    if result.returncode != 0:
        return None
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def last_commit(ref, path):
    out = git("log", "-1", "--format=%cI", ref, "--", path, check=False).stdout.strip()
    return out or None


def sessions_through(as_of):
    # H252 maturities lie about one year out, so the calendar must reach past them.
    days = calendar.sessions("2026-01-01", (as_of.date() + timedelta(days=420)).isoformat(), "KR")
    return [d.strftime("%Y-%m-%d") for d in days]


def load_registry(path=REGISTRY):
    registry = json.loads(Path(path).read_text(encoding="utf-8"))
    problems = ops.validate_registry(registry)
    if problems:
        raise SystemExit("REGISTRY_INVALID: " + "; ".join(problems))
    return registry


def find(registry, study_id):
    return next(s for s in registry["studies"] if s["studyId"] == study_id)


def cmd_status(args):
    registry = load_registry(args.registry)
    as_of = ops.parse_utc(args.as_of)
    rows, commits = {}, {}
    for study in registry["studies"]:
        path = study.get("ledgerPath")
        rows[study["studyId"]] = read_rows(args.ledger_ref, path) if path else None
        commits[study["studyId"]] = last_commit(args.ledger_ref, path) if path else None
    outcomes = json.loads(args.writer_outcomes) if args.writer_outcomes else {}
    status = ops.build_status(registry, rows, sessions_through(as_of), as_of, commits=commits, writer_outcomes=outcomes)
    status["ledgerRef"] = args.ledger_ref
    status["ledgerHead"] = git("rev-parse", args.ledger_ref, check=False).stdout.strip() or None
    text = json.dumps(status, indent=2, ensure_ascii=False, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 1 if status["alerts"] else 0


def cmd_guard(args):
    registry = load_registry(args.registry)
    study = find(registry, args.study)
    as_of = ops.parse_utc(args.as_of) if args.as_of else datetime.now(timezone.utc)
    attestation_path = study.get("automation", {}).get("singleWriterAttestation")
    attestation = None
    if attestation_path and (ROOT / attestation_path).is_file():
        attestation = json.loads((ROOT / attestation_path).read_text(encoding="utf-8"))
    authorization = None
    pinned = study.get("automation", {}).get("pinnedCodeCommit")
    present = bool(pinned) and git("cat-file", "-e", f"{pinned}^{{commit}}", check=False).returncode == 0
    if present and study.get("authorizationPath"):
        shown = git("show", f"{pinned}:{study['authorizationPath']}", check=False)
        if shown.returncode == 0:
            authorization = json.loads(shown.stdout)
    rows = read_rows(args.ledger_ref, study["ledgerPath"]) or []
    errors = []
    if rows:
        sessions = sessions_through(as_of)
        _, errors = ops.verify_rows(rows, study, ops.session_windows(sessions, study["firstEligibleSession"]), as_of)
    decision = ops.guard_decision(study, attestation, authorization, present, errors)
    print(json.dumps(decision, ensure_ascii=False))
    return 2 if decision["decision"] == "REFUSE" else 0


def cmd_verify(args):
    registry = load_registry(args.registry)
    study = find(registry, args.study)
    as_of = ops.parse_utc(args.as_of) if args.as_of else datetime.now(timezone.utc)
    rows = read_rows(args.ledger_ref, study["ledgerPath"]) or []
    windows = ops.session_windows(sessions_through(as_of), study["firstEligibleSession"])
    result = ops.verify_new_receipt(rows, study, args.session, windows, as_of)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 3


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--registry", default=str(REGISTRY))
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status")
    status.add_argument("--ledger-ref", required=True)
    status.add_argument("--as-of", required=True)
    status.add_argument("--out")
    status.add_argument("--writer-outcomes", help='JSON {"studyId": "success|failure|skipped"} from the workflow')
    status.set_defaults(func=cmd_status)
    guard = sub.add_parser("guard")
    guard.add_argument("--study", required=True)
    guard.add_argument("--ledger-ref", required=True)
    guard.add_argument("--as-of")
    guard.set_defaults(func=cmd_guard)
    verify = sub.add_parser("verify-receipt")
    verify.add_argument("--study", required=True)
    verify.add_argument("--session", required=True)
    verify.add_argument("--ledger-ref", required=True)
    verify.add_argument("--as-of")
    verify.set_defaults(func=cmd_verify)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
