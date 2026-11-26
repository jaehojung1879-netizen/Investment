"""Operations CLI for the prospective-research ledger (status / guard / verify-receipt). Read-only over every receipt file.

    python scripts/prospective_ops.py status --ledger-ref origin/signal-history --as-of 2026-11-25T12:00:00Z --out status.json
    python scripts/prospective_ops.py guard --study kr-corporate-information-events-v1 --ledger-ref origin/signal-history
    python scripts/prospective_ops.py verify-receipt --study kr-corporate-information-events-v1 --session 2026-11-26 --ledger-ref origin/signal-history

Exit codes: status 1 when an alert is owed; guard 2 on REFUSE; verify-receipt 3 when the session is not verifiably recorded; verify-immutability 4 when it is not verified.
"""
import argparse
import hashlib
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


def git_bytes(*args, cwd=ROOT):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    return result.returncode, result.stdout


def read_ledger(ref, path):
    """Four-way ledger read: ROWS, EMPTY_VALID, ABSENT (ref reachable, file not there), READ_FAILED (anything else, incl. corrupt JSON)."""
    if not path:
        return {"state": ops.LEDGER_ABSENT, "rows": [], "detail": "NO_PATH_REGISTERED"}
    if git("rev-parse", "--verify", "-q", f"{ref}^{{commit}}", check=False).returncode != 0:
        return {"state": ops.LEDGER_READ_FAILED, "rows": [], "detail": f"REF_UNREACHABLE:{ref}"}
    if git("cat-file", "-e", f"{ref}:{path}", check=False).returncode != 0:
        return {"state": ops.LEDGER_ABSENT, "rows": [], "detail": None}
    code, raw = git_bytes("show", f"{ref}:{path}")
    if code != 0:
        return {"state": ops.LEDGER_READ_FAILED, "rows": [], "detail": "GIT_SHOW_FAILED"}
    try:
        rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    except (UnicodeDecodeError, ValueError) as exc:
        return {"state": ops.LEDGER_READ_FAILED, "rows": [], "detail": "CORRUPT_LEDGER:" + type(exc).__name__}
    return {"state": ops.LEDGER_ROWS if rows else ops.LEDGER_EMPTY_VALID, "rows": rows, "detail": None}


def read_rows(ref, path):
    """Rows or None; kept for callers that only need observations. A failed read raises instead of reading as 'no rows'."""
    read = read_ledger(ref, path)
    if read["state"] == ops.LEDGER_READ_FAILED:
        raise RuntimeError("LEDGER_READ_FAILED: " + str(read["detail"]))
    return None if read["state"] == ops.LEDGER_ABSENT else read["rows"]


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
        rows[study["studyId"]] = read_ledger(args.ledger_ref, path)
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


def pinned_facts(study):
    """Evidence about the pinned code, read from git objects: bytes hashes, tree hash, durable reference."""
    automation = study.get("automation", {})
    pinned = automation.get("pinnedCodeCommit")
    present = bool(pinned) and git("cat-file", "-e", f"{pinned}^{{commit}}", check=False).returncode == 0
    facts = {"pinnedCommitPresent": present, "pinnedTreeSha": None, "durablyReferenced": False, "authorization": None,
             "authorizationBytesSha256": None, "specBytesSha256": None}
    if not present:
        return facts
    facts["pinnedTreeSha"] = git("rev-parse", f"{pinned}^{{tree}}", check=False).stdout.strip() or None
    code, raw = git_bytes("show", f"{pinned}:{study['authorizationPath']}") if study.get("authorizationPath") else (1, b"")
    if code == 0:
        facts["authorizationBytesSha256"] = hashlib.sha256(raw).hexdigest()
        try:
            facts["authorization"] = json.loads(raw)
        except ValueError:
            facts["authorization"] = None
    code, raw = git_bytes("show", f"{pinned}:{study['specPath']}") if study.get("specPath") else (1, b"")
    if code == 0:
        facts["specBytesSha256"] = hashlib.sha256(raw).hexdigest()
    facts["durablyReferenced"] = durably_referenced(pinned)
    return facts


def durably_referenced(commit):
    """True only if a tag contains the commit or main's history does. A feature branch alone is deletable and does not count."""
    if git("tag", "--contains", commit, check=False).stdout.strip():
        return True
    for main in ("origin/main", "main"):
        if git("merge-base", "--is-ancestor", commit, main, check=False).returncode == 0:
            return True
    return False


def cmd_guard(args):
    registry = load_registry(args.registry)
    study = find(registry, args.study)
    as_of = ops.parse_utc(args.as_of) if args.as_of else datetime.now(timezone.utc)
    attestation_path = study.get("automation", {}).get("singleWriterAttestation")
    attestation = None
    if attestation_path and (ROOT / attestation_path).is_file():
        try:
            attestation = json.loads((ROOT / attestation_path).read_text(encoding="utf-8"))
        except ValueError:
            attestation = None
    ledger = read_ledger(args.ledger_ref, study.get("ledgerPath"))
    errors = []
    if ledger["rows"]:
        _, errors = ops.verify_rows(ledger["rows"], study, ops.session_windows(sessions_through(as_of), study["firstEligibleSession"]), as_of)
    facts = {**pinned_facts(study), "attestation": attestation, "ledger": ledger, "integrityErrors": errors, "asOf": as_of}
    decision = ops.guard_decision(study, facts)
    print(json.dumps(decision, ensure_ascii=False))
    return 2 if decision["decision"] == "REFUSE" else 0


def cmd_immutability(args):
    """Read-only proof that what must not change has not: baseline receipts, registered hashes, pinned tree, protected paths."""
    registry = load_registry(args.registry)
    study = find(registry, args.study)
    ledger = read_ledger(args.ledger_ref, study["ledgerPath"])
    facts = pinned_facts(study)
    approval, automation = study["approval"], study["automation"]
    checks = {
        "ledgerRead": ledger["state"],
        "baselineReceipts": ops.verify_baseline(ledger["rows"], study) if ledger["state"] in (ops.LEDGER_ROWS, ops.LEDGER_EMPTY_VALID) else {"state": "UNREADABLE"},
        "authorizationBytesMatchRegistry": facts["authorizationBytesSha256"] == approval["authorizationSha256"],
        "specBytesMatchRegistry": facts["specBytesSha256"] == approval["specSha256"],
        "pinnedTreeMatchesRegistry": facts["pinnedTreeSha"] == automation.get("pinnedTreeSha"),
        "pinnedCodeDurablyReferenced": facts["durablyReferenced"],
    }
    changed = git("diff", "--name-only", f"{args.base}...HEAD", check=False)
    prefixes = tuple(registry.get("protectedPathPrefixes", []))
    touched = [p for p in changed.stdout.split() if p.startswith(prefixes)] if changed.returncode == 0 else None
    checks["protectedPathsTouchedSinceBase"] = touched if touched is None else sorted(touched)
    ok = (checks["baselineReceipts"].get("state") == "INTACT" and checks["authorizationBytesMatchRegistry"] and checks["specBytesMatchRegistry"]
          and checks["pinnedTreeMatchesRegistry"] and touched == [])
    checks["result"] = "IMMUTABILITY_VERIFIED" if ok else "IMMUTABILITY_NOT_VERIFIED"
    print(json.dumps(checks, indent=2, ensure_ascii=False))
    return 0 if ok else 4


def cmd_verify(args):
    registry = load_registry(args.registry)
    study = find(registry, args.study)
    as_of = ops.parse_utc(args.as_of) if args.as_of else datetime.now(timezone.utc)
    read = read_ledger(args.ledger_ref, study["ledgerPath"])
    if read["state"] == ops.LEDGER_READ_FAILED:
        print(json.dumps({"session": args.session, "valid": False, "result": "LEDGER_READ_FAILED", "detail": read["detail"]}))
        return 3
    rows = read["rows"]
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
    imm = sub.add_parser("verify-immutability")
    imm.add_argument("--study", required=True)
    imm.add_argument("--ledger-ref", required=True)
    imm.add_argument("--base", default="origin/main")
    imm.set_defaults(func=cmd_immutability)
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
