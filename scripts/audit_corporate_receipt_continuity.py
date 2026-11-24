"""Read-only continuity check for the already registered corporate event writer."""
import argparse
import hashlib
import json
import re
import subprocess
from datetime import date, datetime, time, timezone
from pathlib import Path

STUDY = "kr-corporate-information-events-v1"
CODE = "8aee189ff453d9bd624a67df5e1e5975bd7d211c"
AUTH_PATH = "research/corporate_event_readiness_v1/cohort/AUTHORIZATION-prospective-recording.json"
LEDGER_PATH = f"ledger/research-strategies/{STUDY}/receipts.jsonl"
ROOT = Path(__file__).resolve().parents[1]


def utc(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timezone required")
    return result.astimezone(timezone.utc)


def at(day, hour):
    return datetime.combine(date.fromisoformat(day), time(hour), timezone.utc)


def digest(row):
    body = {key: value for key, value in row.items() if key != "receiptSha256"}
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def inspect(rows, sessions, first, as_of, spec_sha, auth_sha):
    """Sessions must include the next trading session beyond as_of; no inference from rows."""
    if sessions != sorted(set(sessions)) or not sessions or sessions[-1] <= as_of.date().isoformat():
        raise ValueError("ordered unique sessions with a future boundary required")
    if first not in sessions:
        raise ValueError("first authorized session missing from calendar")
    windows = {day: at(nxt, 0) for day, nxt in zip(sessions, sessions[1:]) if day >= first}
    closed = {day for day, end in windows.items() if end <= as_of}
    open_windows = {day for day, end in windows.items() if at(day, 9) <= as_of < end}
    errors, seen, valid = [], set(), set()
    for number, row in enumerate(rows, 1):
        day = row.get("signalDate")
        problems = []
        if day in seen:
            problems.append("DUPLICATE_SESSION")
            valid.discard(day)
        seen.add(day)
        if (row.get("studyId") != STUDY or row.get("mode") != "LIVE"
                or row.get("evidenceClass") != "PROSPECTIVE_PAPER"
                or row.get("specSha256") != spec_sha
                or row.get("authorizationSha256") != auth_sha
                or row.get("codeCommit") != CODE):
            problems.append("REGISTRATION_OR_MODE_MISMATCH")
        if row.get("receiptSha256") != digest(row):
            problems.append("DIGEST_MISMATCH")
        events = row.get("events")
        if not isinstance(events, list) or type(row.get("eventCount")) is not int or row["eventCount"] != len(events):
            problems.append("EVENT_COUNT_MISMATCH")
        try:
            stamp = utc(row["createdAtUtc"])
            if day not in windows or not at(day, 9) <= stamp < windows[day] or stamp > as_of:
                problems.append("OUTSIDE_AUTHORIZED_WINDOW")
        except (KeyError, TypeError, ValueError, AttributeError):
            problems.append("INVALID_TIMESTAMP")
        if problems:
            errors.append({"line": number, "session": day, "reasons": problems})
        elif day not in valid:
            valid.add(day)
    missing = sorted(closed - valid)
    return {"study": STUDY, "asOfUtc": as_of.isoformat(), "storedRows": len(rows),
            "closedWindows": len(closed), "validClosedWindows": len(closed & valid),
            "missingClosedSessions": missing, "pendingOpenSessions": sorted(open_windows - valid),
            "errors": errors, "status": "ATTENTION" if errors or missing else "OK",
            "limitations": "Checks claimed timestamps and row digests, not first public commit/push time or source completeness."}


def git_bytes(ref, path):
    return subprocess.check_output(["git", "show", f"{ref}:{path}"], cwd=ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger-sha", required=True, help="Exact, locally available signal-history commit")
    parser.add_argument("--as-of", required=True, help="Explicit offset-aware audit cutoff, not a writer clock")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.ledger_sha):
        parser.error("--ledger-sha must be a full commit SHA")
    as_of = utc(args.as_of)
    auth_raw = git_bytes(CODE, AUTH_PATH)
    auth = json.loads(auth_raw)
    raw = git_bytes(args.ledger_sha, LEDGER_PATH)
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    # Use the repository's versioned exchange calendar, never weekdays or price presence.
    import sys
    sys.path.insert(0, str(ROOT))
    from pipeline import replay_calendar as calendar
    from datetime import timedelta
    days = calendar.sessions(auth["firstEligibleSignalSession"],
                             (as_of.date() + timedelta(days=20)).isoformat(), "KR")
    report = inspect(rows, [d.strftime("%Y-%m-%d") for d in days],
                     auth["firstEligibleSignalSession"], as_of, auth["specSha256"],
                     hashlib.sha256(auth_raw).hexdigest())
    report.update(ledgerSha=args.ledger_sha, ledgerFileSha256=hashlib.sha256(raw).hexdigest(),
                  calendarVersion=calendar.CALENDAR_VERSION)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return int(report["status"] != "OK")


if __name__ == "__main__":
    raise SystemExit(main())
