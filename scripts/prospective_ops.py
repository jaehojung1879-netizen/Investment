"""Operations CLI for the prospective-research ledger (status / guard / verify-receipt). Read-only over every receipt file.

    python scripts/prospective_ops.py status --ledger-ref origin/signal-history --as-of 2026-11-25T12:00:00Z --out status.json
    python scripts/prospective_ops.py guard --study kr-corporate-information-events-v1 --ledger-ref origin/signal-history
    python scripts/prospective_ops.py verify-receipt --study kr-corporate-information-events-v1 --session 2026-11-26 --ledger-ref origin/signal-history

Exit codes: status 1 when an alert is owed; guard 2 on REFUSE; verify-receipt 3 when the session is not verifiably recorded; verify-immutability 4 when it is not verified.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

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
        if not all(isinstance(row, dict) for row in rows):
            raise ValueError("ledger records must be objects")
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


def prefix_matches(ref, study):
    baseline = study.get("baselineLedger")
    if not baseline:
        return None
    size = baseline["bytes"]
    code, raw = git_bytes("show", f"{ref}:{study['ledgerPath']}")
    return code == 0 and len(raw) >= size and hashlib.sha256(raw[:size]).hexdigest() == baseline["sha256"]


def owner_approval_time(comment, attestation_bytes):
    """Match current owner endorsement to the exact committed cutover bytes."""
    owner_id = 238918679
    issue = "https://api.github.com/repos/jaehojung1879-netizen/Investment/issues/292"
    expected_line = f"{ops.CUTOVER_SCHEMA} sha256={hashlib.sha256(attestation_bytes).hexdigest()}"
    if (comment.get("issue_url") != issue or comment.get("user", {}).get("id") != owner_id
            or comment.get("author_association") != "OWNER"
            or expected_line not in comment.get("body", "").splitlines()):
        return None
    try:
        return ops.parse_utc(comment["updated_at"])
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def read_owner_approval(study, raw):
    automation = study["automation"]
    comment_id = automation.get("cutoverApprovalCommentId")
    token = os.environ.get("GITHUB_TOKEN")
    if not raw or type(comment_id) is not int or comment_id <= 0 or not token:
        return None
    request = Request(
        f"https://api.github.com/repos/{ops.SUCCESSOR['repository']}/issues/comments/{comment_id}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
    )
    try:
        with urlopen(request, timeout=15) as response:
            comment = json.load(response)
        if not isinstance(comment, dict) or comment.get("id") != comment_id:
            return None
        return owner_approval_time(comment, raw)
    except (URLError, TimeoutError, OSError, ValueError):
        return None



def outcome_publication(ref, study):
    """Summarize the existing evaluator's counters without reading outcome rows."""
    path = study.get("outcomeStatusPath")
    if not path:
        state = "MATURITY_CALENDAR_ONLY" if study.get("horizons") else "NO_EVALUATOR_REGISTERED_HERE"
        return {"state": state}
    code, raw = git_bytes("show", f"{ref}:{path}")
    if code:
        return {"state": "EVALUATOR_STATUS_UNAVAILABLE"}
    try:
        status = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return {"state": "EVALUATOR_STATUS_INVALID"}
    if (not isinstance(status, dict) or status.get("studyId") != study["studyId"]
            or status.get("action") != "outcomes" or not isinstance(status.get("status"), str)):
        return {"state": "EVALUATOR_STATUS_INVALID"}
    counts = {key: status[key] for key in ("receipts", "graded", "computed", "openDecisions")
              if type(status.get(key)) is int and status[key] >= 0}
    return {"state": status["status"], "source": path, "attemptedAt": status.get("attemptedAt"), **counts}



def cmd_status(args):
    registry = load_registry(args.registry)
    as_of = ops.parse_utc(args.as_of)
    rows, commits = {}, {}
    for study in registry["studies"]:
        path = study.get("ledgerPath")
        rows[study["studyId"]] = read_ledger(args.ledger_ref, path)
        if prefix_matches(args.ledger_ref, study) is False:
            rows[study["studyId"]] = {"state": ops.LEDGER_READ_FAILED, "rows": [], "detail": "BASELINE_LEDGER_BYTES_CHANGED"}
        commits[study["studyId"]] = last_commit(args.ledger_ref, path) if path else None
    outcomes = json.loads(args.writer_outcomes) if args.writer_outcomes else {}
    status = ops.build_status(registry, rows, sessions_through(as_of), as_of, commits=commits, writer_outcomes=outcomes)
    for item, study in zip(status["studies"], registry["studies"], strict=True):
        item["outcomePublication"] = outcome_publication(args.ledger_ref, study)
    listing = git("ls-tree", "-r", "--name-only", args.ledger_ref, "ledger/research-strategies", "ledger/weekly-decisions", check=False)
    registered = {study["ledgerPath"] for study in registry["studies"] if study.get("ledgerPath")}
    status["unregisteredReceiptPaths"] = sorted(
        path for path in listing.stdout.splitlines() if path.endswith("/receipts.jsonl") and path not in registered
    ) if listing.returncode == 0 else None
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
    facts["durablyReferenced"] = durably_referenced(pinned, automation.get("preservationTag"))
    return facts


def durably_referenced(commit, tag):
    """Require a live remote annotated tag targeting the exact commit or reachability from remote main."""
    if tag:
        ref = f"refs/tags/{tag}"
        rows = git("ls-remote", "origin", ref, ref + "^{}", check=False).stdout.splitlines()
        refs = dict(line.split()[::-1] for line in rows)
        local_tag = git("rev-parse", "--verify", ref, check=False).stdout.strip()
        if (refs.get(ref + "^{}") == commit and refs.get(ref) == local_tag
                and git("cat-file", "-t", local_tag, check=False).stdout.strip() == "tag"):
            return True
    return git("merge-base", "--is-ancestor", commit, "origin/main", check=False).returncode == 0


def cmd_guard(args):
    registry = load_registry(args.registry)
    study = find(registry, args.study)
    as_of = ops.parse_utc(args.as_of) if args.as_of else datetime.now(timezone.utc)
    automation = study.get("automation", {})
    attestation_path = automation.get("singleWriterAttestation")
    raw, attestation = None, None
    if attestation_path and (ROOT / attestation_path).is_file():
        try:
            raw = (ROOT / attestation_path).read_bytes()
            attestation = json.loads(raw)
        except (OSError, ValueError):
            pass
    ledger = read_ledger(args.ledger_ref, study.get("ledgerPath"))
    sessions = sessions_through(as_of)
    windows = ops.session_windows(sessions, study["firstEligibleSession"])
    valid, errors = ops.verify_rows(ledger["rows"], study, windows, as_of)
    enabled = automation.get("enabled") is True
    on_current_main = (os.environ.get("GITHUB_REF") == ops.SUCCESSOR["ref"]
                       and os.environ.get("GITHUB_REPOSITORY") == ops.SUCCESSOR["repository"]
                       and os.environ.get("GITHUB_WORKFLOW_REF") == (
                           f"{ops.SUCCESSOR['repository']}/{ops.SUCCESSOR['workflow']}@{ops.SUCCESSOR['ref']}"))
    if enabled:
        remote = git("ls-remote", "origin", ops.SUCCESSOR["ref"], check=False)
        on_current_main = on_current_main and remote.returncode == 0 and remote.stdout.split()[:1] == git("rev-parse", "HEAD").stdout.split()
    facts = {
        **pinned_facts(study), "attestation": attestation,
        "ownerApprovalAt": read_owner_approval(study, raw) if enabled and on_current_main else None,
        "baselineBytesMatch": prefix_matches(args.ledger_ref, study), "ledger": ledger,
        "integrityErrors": errors, "asOf": as_of,
    }
    decision = ops.guard_decision(study, facts)
    session = ops.writer_session(as_of, sessions)
    decision.update(automationEnabled=enabled, session=session)
    if enabled and not on_current_main:
        decision["reasons"].append("WRITER_NOT_ON_CURRENT_MAIN_ACTION")
        decision["decision"] = "REFUSE"
    if decision["decision"] == "ALLOW_WRITE":
        baseline = study.get("monitoring", {}).get("continuityBaselineSession")
        if session is None or (baseline and session <= baseline):
            decision["decision"] = "NO_RECEIPT_DUE"
        elif session in valid:
            decision["decision"] = "ALREADY_RECORDED"
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
        "baselineLedgerBytesIntact": prefix_matches(args.ledger_ref, study),
    }
    changed = git("diff", "--name-only", f"{args.base}...HEAD", check=False)
    prefixes = tuple(registry.get("protectedPathPrefixes", []))
    touched = [p for p in changed.stdout.split() if p.startswith(prefixes)] if changed.returncode == 0 else None
    from pipeline.prospective_workflow_maintenance import WORKFLOW, verify_install
    if touched and WORKFLOW in touched:
        verify_install(ROOT)
        touched.remove(WORKFLOW)
    checks["protectedPathsTouchedSinceBase"] = touched if touched is None else sorted(touched)
    ok = (checks["baselineReceipts"].get("state") == "INTACT" and checks["authorizationBytesMatchRegistry"] and checks["specBytesMatchRegistry"]
          and checks["pinnedTreeMatchesRegistry"] and checks["baselineLedgerBytesIntact"] is not False and touched == [])
    checks["result"] = "IMMUTABILITY_VERIFIED" if ok else "IMMUTABILITY_NOT_VERIFIED"
    print(json.dumps(checks, indent=2, ensure_ascii=False))
    return 0 if ok else 4


def cmd_verify(args):
    registry = load_registry(args.registry)
    study = find(registry, args.study)
    as_of = ops.parse_utc(args.as_of) if args.as_of else datetime.now(timezone.utc)
    read = read_ledger(args.ledger_ref, study["ledgerPath"])
    if prefix_matches(args.ledger_ref, study) is False:
        print(json.dumps({"session": args.session, "valid": False, "result": "BASELINE_LEDGER_BYTES_CHANGED"}))
        return 3
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
