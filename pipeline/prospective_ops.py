"""Common operations ledger for every registered PROSPECTIVE research recorder (prospective-ops-v1).

One registry (`research/prospective_ops/registry.json`), one status builder, one writer guard, one post-write verifier. A study is added by
registering it; nothing here schedules a writer for a study the registry does not mark approved AND automation-enabled.

Boundaries (all enforced below, none by convention):
* read-only over receipts: no function here opens a ledger for writing, edits a receipt, back-fills a session or reads a return, price, NAV or label;
* "the job succeeded" and "a valid receipt exists" are different facts. Status is derived from receipts only; an execution outcome is carried
  beside it and can add EXECUTION_FAILED, never HEALTHY;
* a missing closed window is `MISSED_NOT_OBSERVED`, never "no event happened" and never counted toward an independent sample;
* a measurement that cannot be made is `None`, not zero.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone

REGISTRY_SCHEMA = "PROSPECTIVE_OPS_REGISTRY_V1"
STATUS_SCHEMA = "PROSPECTIVE_OPS_STATUS_V1"
STATES = ("HEALTHY", "PENDING", "MISSED", "SOURCE_BLOCKED", "EXECUTION_FAILED", "DISABLED", "UNAUTHORIZED")
APPROVED = "APPROVED_PROSPECTIVE_RECORDING"
APPROVED_BY_MERGE = "APPROVED_BY_MERGE_OF_REGISTERED_SPEC"
APPROVED_STATUSES = (APPROVED, APPROVED_BY_MERGE)
KINDS = ("SESSION_DAILY_KR", "WEEKLY_LAST_KR_SESSION", "OBSERVED_ONLY")
FORBIDDEN_STUDY_FIELDS = ("alpha", "return", "nav", "weight", "position")  # a registry row describes operations, never results
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
# A session's receipt window: strictly after the 18:00 KST final close (09:00 UTC) and before the next session's open (00:00 UTC).
FINAL_CLOSE_UTC_HOUR = 9


# A ledger read has FOUR outcomes and they are never merged: rows present, a valid file with no rows, a file that is not there on a
# reachable ref, and a read that failed (bad ref, git error, corrupt JSON). Only the first two are observations; the last two are not.
LEDGER_ROWS, LEDGER_EMPTY_VALID, LEDGER_ABSENT, LEDGER_READ_FAILED = "ROWS", "EMPTY_VALID", "ABSENT", "READ_FAILED"
FRESHNESS_STATES = ("FRESH", "STALE", "UNKNOWN")
COMPLETENESS_STATES = ("VERIFIED_COMPLETE", "INCOMPLETE", "NOT_ASSESSABLE")
DEFAULT_DAILY_STALE_DAYS = 5
CUTOVER_SCHEMA = "PROSPECTIVE_WRITER_CUTOVER_V1"
CUTOVER_READBACK_MAX_AGE = timedelta(days=7)
CORPORATE_STUDY = "kr-corporate-information-events-v1"
CORPORATE_LEGACY_WRITERS = frozenset({
    "trig_01XwJ7yivCe5uokkmUTk8MWE", "trig_013qoRYz6H9UwUosNzCWv69B",
})
SUCCESSOR = {
    "repository": "jaehojung1879-netizen/Investment",
    "workflow": ".github/workflows/prospective-ops.yml",
    "ref": "refs/heads/main",
}


def coerce_read(read) -> dict:
    """Accept a ledger read dict, a bare row list (tests) or None (legacy: file absent)."""
    if isinstance(read, dict) and "state" in read:
        return {"state": read["state"], "rows": read.get("rows") or [], "detail": read.get("detail")}
    if read is None:
        return {"state": LEDGER_ABSENT, "rows": [], "detail": None}
    return {"state": LEDGER_ROWS if read else LEDGER_EMPTY_VALID, "rows": list(read), "detail": None}


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def receipt_digest(row: dict) -> str:
    return hashlib.sha256(canonical({k: v for k, v in row.items() if k != "receiptSha256"})).hexdigest()


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("offset-aware timestamp required")
    return parsed.astimezone(timezone.utc)


def _at(day: str, hour: int) -> datetime:
    return datetime(*date.fromisoformat(day).timetuple()[:3], hour, tzinfo=timezone.utc)


# --------------------------------------------------------------------------------------------------- registry
def validate_registry(registry: dict) -> list[str]:
    """Return every problem found; an empty list is valid. Never raises on content so a bad row cannot hide the others."""
    problems: list[str] = []
    if registry.get("schema") != REGISTRY_SCHEMA:
        problems.append("SCHEMA_MISMATCH")
    seen: set[str] = set()
    for study in registry.get("studies", []):
        sid = study.get("studyId", "<missing>")
        if sid in seen:
            problems.append(f"{sid}: DUPLICATE_STUDY_ID")
        seen.add(sid)
        if study.get("kind") not in KINDS:
            problems.append(f"{sid}: UNKNOWN_KIND")
        approval = study.get("approval", {})
        approved = approval.get("status") in APPROVED_STATUSES
        automation = study.get("automation", {})
        if automation.get("enabled") and not approved:
            problems.append(f"{sid}: AUTOMATION_ENABLED_WITHOUT_APPROVAL")
        if approval.get("status") == APPROVED:
            for key in ("authorizationSha256", "specSha256"):
                if not HEX64.fullmatch(str(approval.get(key, ""))):
                    problems.append(f"{sid}: APPROVED_WITHOUT_{key}")
        if automation.get("enabled"):
            if not HEX40.fullmatch(str(automation.get("pinnedTreeSha", ""))):
                problems.append(f"{sid}: AUTOMATION_WITHOUT_PINNED_TREE_HASH")
            if not HEX40.fullmatch(str(automation.get("pinnedCodeCommit", ""))):
                problems.append(f"{sid}: AUTOMATION_WITHOUT_PINNED_CODE")
            if not automation.get("singleWriterAttestation"):
                problems.append(f"{sid}: AUTOMATION_WITHOUT_SINGLE_WRITER_ATTESTATION")
        if any(any(token in key.lower() for token in FORBIDDEN_STUDY_FIELDS) for key in study):
            problems.append(f"{sid}: RESULT_FIELD_IN_OPERATIONS_REGISTRY")
    return problems


# ------------------------------------------------------------------------------------------ expected windows
def session_windows(sessions: Sequence[str], first: str) -> dict[str, datetime]:
    """Receipt window end for each session at or after `first`: the next session's open. `sessions` must include one future boundary."""
    if list(sessions) != sorted(set(sessions)) or first not in sessions:
        raise ValueError("ordered unique sessions containing the first authorized session required")
    return {day: _at(nxt, 0) for day, nxt in zip(sessions, sessions[1:]) if day >= first}


def weekly_last_sessions(sessions: Sequence[str], first: str) -> list[str]:
    """Last KR session of each ISO week from `first`; the final partial week is excluded (its last session is not yet known to be last)."""
    weeks: dict[tuple[int, int], str] = {}
    for day in sessions:
        if day >= first:
            iso = date.fromisoformat(day).isocalendar()
            weeks[(iso[0], iso[1])] = day
    ordered = sorted(weeks.values())
    return ordered[:-1]


def classify_windows(expected: dict[str, datetime], valid: set[str], as_of: datetime) -> tuple[list[str], list[str], list[str]]:
    """(closed, missed, pending): closed = window end <= as_of; pending = window open or not yet reached by the 18:00 KST close."""
    closed = sorted(day for day, end in expected.items() if end <= as_of)
    missed = [day for day in closed if day not in valid]
    pending = sorted(day for day, end in expected.items() if end > as_of and _at(day, 0) <= as_of and day not in valid)
    return closed, missed, pending


# ------------------------------------------------------------------------------------ receipt verification
def _corporate_receipt_errors(row, study, day, previous_session, next_open):
    """Check registered writer identity and actual source receipt structure."""
    problems = []
    if row.get("codeCommit") != study.get("automation", {}).get("pinnedCodeCommit") or not HEX40.fullmatch(str(row.get("codeCommit", ""))):
        problems.append("PINNED_RECEIPT_CODE_MISMATCH")
    sources, events = row.get("sources"), row.get("events")
    valid_days = set()
    queries = {(("pblntf_ty", "B"),), (("pblntf_detail_ty", "I001"),)}
    if not isinstance(sources, list) or not sources:
        problems.append("SOURCE_RECEIPTS_MISSING")
    else:
        seen = set()
        try:
            for source in sources:
                source_day = source["day"]
                if date.fromisoformat(source_day).isoformat() != source_day:
                    raise ValueError("source day")
                query = tuple(sorted(source["query"].items()))
                pages = source["pageSha256"]
                if (
                    query not in queries or not isinstance(pages, list) or not pages
                    or not all(isinstance(h, str) and HEX64.fullmatch(h) for h in pages)
                    or (source_day, query) in seen
                ):
                    raise ValueError("source evidence")
                seen.add((source_day, query))
                valid_days.add(source_day)
            end = date.fromisoformat(day)
            start = date.fromisoformat(previous_session or min(valid_days))
            n = (end - start).days
            if n <= 0 or n > 366:
                raise ValueError("source window")
            expected = {(start + timedelta(days=i)).isoformat() for i in range(n)}
            if seen != {(d, q) for d in expected for q in queries}:
                raise ValueError("source coverage")
        except (TypeError, ValueError, KeyError, AttributeError):
            problems.append("SOURCE_RECEIPT_SCHEMA_OR_COVERAGE_INVALID")
    if not isinstance(events, list) or type(row.get("eventCount")) is not int or row["eventCount"] != len(events):
        problems.append("EVENT_COUNT_MISMATCH")
    else:
        for event in events:
            if (
                not isinstance(event, dict)
                or not isinstance(event.get("corp_code"), str)
                or not re.fullmatch(r"\d{8}", event["corp_code"])
                or not isinstance(event.get("rcept_no"), str)
                or not re.fullmatch(r"\d{14}", event["rcept_no"])
                or event.get("hypothesis") not in ("A1", "B1")
                or not isinstance(event.get("receiptDay"), str) or event["receiptDay"] not in valid_days
                or next_open is None or event.get("entrySession") != next_open.date().isoformat()
                or not isinstance(event.get("sourceBodySha256"), str)
                or not HEX64.fullmatch(event["sourceBodySha256"])
                or type(event.get("sameSessionFollowOn")) is not bool
            ):
                problems.append("EVENT_RECEIPT_SCHEMA_INVALID")
                break
    return problems


def verify_rows(rows: list[dict], study: dict, windows: dict[str, datetime], as_of: datetime, date_field: str = "signalDate") -> tuple[set[str], list[dict]]:
    """Valid session set and structured errors. A row is valid only if registration, digest, mode and its own window all hold."""
    approval = study["approval"]
    errors: list[dict] = []
    valid: set[str] = set()
    seen: set[str] = set()
    ordered = sorted(windows)
    prior = dict(zip(ordered[1:], ordered))
    for number, row in enumerate(rows, 1):
        day = row.get(date_field)
        problems: list[str] = []
        if not isinstance(day, str):
            errors.append({"line": number, "session": None, "reasons": ["INVALID_SESSION"]})
            continue
        if day in seen:
            problems.append("DUPLICATE_SESSION")
            valid.discard(day)
        seen.add(day)
        if (row.get("studyId") != study["studyId"] or row.get("specSha256") != approval["specSha256"]
                or row.get("authorizationSha256") != approval["authorizationSha256"]
                or row.get("evidenceClass") != study.get("evidenceClass", "PROSPECTIVE_PAPER")
                or row.get("mode") != study.get("recordMode", "LIVE")):
            problems.append("REGISTRATION_OR_MODE_MISMATCH")
        try:
            if row.get("receiptSha256") != receipt_digest(row):
                problems.append("DIGEST_MISMATCH")
        except (ValueError, TypeError):
            problems.append("DIGEST_MISMATCH")
        if study["studyId"] == CORPORATE_STUDY:
            problems.extend(_corporate_receipt_errors(row, study, day, prior.get(day), windows.get(day)))
        events = row.get("events")
        if "events" in row and (not isinstance(events, list) or type(row.get("eventCount")) is not int or row["eventCount"] != len(events)):
            problems.append("EVENT_COUNT_MISMATCH")
        try:
            stamp = parse_utc(row["createdAtUtc"])
            if day not in windows or not _at(day, FINAL_CLOSE_UTC_HOUR) <= stamp < windows[day] or stamp > as_of:
                problems.append("OUTSIDE_AUTHORIZED_WINDOW")
        except (KeyError, TypeError, ValueError, AttributeError):
            problems.append("INVALID_TIMESTAMP")
        if problems:
            errors.append({"line": number, "session": day, "reasons": problems})
        else:
            valid.add(day)
    return valid, errors


# ----------------------------------------------------------------------------------- horizons / independence
def independent_observations(rows: list[dict], valid: set[str], sessions: Sequence[str], horizon: int) -> list[dict]:
    """One event per (issuer, hypothesis) per horizon window from entry, greedy in entry order (the study's registered independence rule).

    Only events from VALID receipts count. Returns the retained events with their maturity session (entry + `horizon` sessions) or None when
    the calendar does not reach it.
    """
    index = {day: i for i, day in enumerate(sessions)}
    kept: list[dict] = []
    last_entry: dict[tuple, int] = {}
    events = [(event, row["signalDate"]) for row in rows if row.get("signalDate") in valid for event in row.get("events", [])]
    for event, _ in sorted(events, key=lambda pair: (pair[0].get("entrySession", ""), pair[0].get("rcept_no", ""))):
        entry = event.get("entrySession")
        if entry not in index:
            continue  # entry session not in the calendar horizon: unmeasurable, not independent
        key = (event.get("corp_code"), event.get("hypothesis"))
        position = index[entry]
        if key in last_entry and position - last_entry[key] < horizon:
            continue
        last_entry[key] = position
        maturity = index[entry] + horizon
        kept.append({"key": key, "entrySession": entry, "maturitySession": sessions[maturity] if maturity < len(sessions) else None})
    return kept


def maturity_summary(kept: list[dict], as_of_session: str) -> dict:
    mature = [item for item in kept if item["maturitySession"] is not None and item["maturitySession"] <= as_of_session]
    upcoming = sorted(item["maturitySession"] for item in kept if item["maturitySession"] and item["maturitySession"] > as_of_session)
    return {"independentObservations": len(kept), "maturedSessions": len(mature), "evaluable": len(mature),
            "nextMaturity": upcoming[0] if upcoming else None, "outcomesComputed": False}


# ------------------------------------------------------------------------------- baseline immutability
def verify_baseline(rows: list[dict], study: dict) -> dict:
    """The receipts the owner saw on the day this system was built must still be there, byte-for-byte (by digest), in order, at the head."""
    baseline = study.get("baselineReceipts")
    if not baseline:
        return {"state": "NOT_REGISTERED", "checked": 0, "problems": []}
    date_field = study.get("dateField", "signalDate")
    problems = []
    for index, expected in enumerate(baseline):
        if index >= len(rows):
            problems.append({"index": index, "session": expected["session"], "reason": "RECEIPT_MISSING"})
        elif rows[index].get(date_field) != expected["session"] or rows[index].get("receiptSha256") != expected["receiptSha256"]:
            problems.append({"index": index, "session": expected["session"], "reason": "RECEIPT_ALTERED_OR_REORDERED"})
        elif receipt_digest(rows[index]) != expected["receiptSha256"]:
            problems.append({"index": index, "session": expected["session"], "reason": "STORED_DIGEST_DOES_NOT_MATCH_CONTENT"})
    return {"state": "VIOLATED" if problems else "INTACT", "checked": len(baseline), "problems": problems}


def window_session(now: datetime, sessions: Sequence[str]) -> str | None:
    """The session whose RECEIPT WINDOW contains `now`: after its 18:00 KST final close and before the next session's open.

    A weekend or holiday keeps the previous session's window open until the next open, so a receipt created then is still VALID. Whether the
    registered writer would actually write then is a different rule: see `writer_session`.
    """
    for day, nxt in zip(sessions, sessions[1:]):
        if _at(day, FINAL_CLOSE_UTC_HOUR) <= now < _at(nxt, 0):
            return day
    return None


def writer_session(now: datetime, sessions: Sequence[str]) -> str | None:
    """The session the registered writer (`live_run.todays_signal_session`) speaks for at `now`, or None (NO_RECEIPT_DUE).

    It reads the KST DATE of now, requires that date to be a session and requires the 18:00 KST close (09:00 UTC) to have passed. So it can
    only write between 09:00 UTC and 15:00 UTC (KST midnight) on a session day; a run delayed past 15:00 UTC, or on a weekend or holiday,
    writes nothing and the session stays missed.
    """
    kst_day = (now + timedelta(hours=9)).date().isoformat()
    if kst_day in set(sessions) and now >= _at(kst_day, FINAL_CLOSE_UTC_HOUR):
        return kst_day
    return None


# ------------------------------------------------------------------------------------------------- status
def _freshness(last_session: str | None, as_of: datetime, threshold_days: int, basis: str, last_commit_utc: str | None) -> dict:
    age = (as_of.date() - date.fromisoformat(last_session)).days if last_session else None
    state = "UNKNOWN" if age is None else ("FRESH" if age <= threshold_days else "STALE")
    return {"state": state, "lastRecordSession": last_session, "ageCalendarDays": age, "thresholdCalendarDays": threshold_days,
            "thresholdBasis": basis, "lastCommitUtc": last_commit_utc, "asOfUtc": as_of.isoformat(),
            "meaning": "How recent the newest record is. Says nothing about whether earlier windows are all present."}


def study_status(study: dict, read, sessions: Sequence[str], as_of: datetime, *, last_commit_utc: str | None = None,
                 writer_outcome: str | None = None, source_blocked_reason: str | None = None) -> dict:
    """One row of the operations ledger. `read` is a ledger read (see `coerce_read`); freshness and completeness are separate fields."""
    approval = study["approval"]
    automation = study.get("automation", {})
    ledger = coerce_read(read)
    rows = ledger["rows"]
    out: dict = {"studyId": study["studyId"], "approvalStatus": approval.get("status"), "automationEnabled": bool(automation.get("enabled")),
                 "kind": study["kind"], "writer": study.get("writer", {}).get("description"),
                 "lastSuccessfulExecution": writer_outcome, "ledgerRead": ledger["state"], "freshness": None,
                 "completeness": {"state": "NOT_ASSESSABLE", "basis": "NOT_EVALUATED"}, "scheduledRecords": None, "validRecords": None,
                 "missedRecords": None, "lastRecordSession": None, "nextRun": study.get("schedule", {}).get("description"),
                 "independentObservations": {}, "failureReason": None, "baselineImmutability": None}
    if approval.get("status") not in APPROVED_STATUSES:
        out.update(operatingState="UNAUTHORIZED", failureReason="NO_OWNER_AUTHORIZATION_FOR_RECORDING")
        return out
    if not study.get("ledgerPath"):
        out.update(operatingState="SOURCE_BLOCKED", failureReason="NO_LEDGER_PATH_REGISTERED")
        return out
    if ledger["state"] == LEDGER_READ_FAILED:
        out.update(operatingState="SOURCE_BLOCKED", failureReason="LEDGER_READ_FAILED", ledgerReadDetail=ledger["detail"])
        return out
    if ledger["state"] == LEDGER_ABSENT:
        # A study that already has receipts must keep its file; its absence is a source problem, never "zero observations".
        out.update(operatingState="SOURCE_BLOCKED",
                   failureReason="LEDGER_FILE_ABSENT_ON_REACHABLE_REF" if study.get("ledgerMustExist") else "LEDGER_NOT_YET_CREATED")
        return out
    date_field = study.get("dateField", "signalDate")
    all_days = [row.get(date_field) for row in rows if row.get(date_field)]
    out["lastRecordSession"] = max(all_days) if all_days else None
    baseline = verify_baseline(rows, study)
    out["baselineImmutability"] = baseline
    kind = study["kind"]
    if kind == "OBSERVED_ONLY":
        stale_days = study["monitoring"]["maxStaleCalendarDays"]
        out["freshness"] = _freshness(out["lastRecordSession"], as_of, stale_days, study["monitoring"].get("thresholdBasis", "UNREGISTERED"), last_commit_utc)
        keys = study.get("observationKey", [date_field])
        observed = {tuple(row[key] for key in keys) for row in rows if all(isinstance(row.get(key), str) and row[key] for key in keys)}
        out.update(observedRecords=len(observed), validRecords=None, scheduledRecords=None, missedRecords=None,
                   completeness={"state": "NOT_ASSESSABLE", "basis": "NO_REGISTERED_CADENCE"})
        if baseline["state"] == "VIOLATED":
            out.update(operatingState="EXECUTION_FAILED", failureReason="BASELINE_RECEIPTS_ALTERED_OR_MISSING")
        elif out["freshness"]["state"] != "FRESH":
            out.update(operatingState="MISSED", failureReason="LAST_RECORD_OLDER_THAN_MONITORING_THRESHOLD")
        else:  # recent is not complete: this state is never HEALTHY
            out.update(operatingState="PENDING", failureReason="COMPLETENESS_NOT_ASSESSABLE_NO_REGISTERED_CADENCE")
        return out
    first = study["firstEligibleSession"]
    windows = session_windows(sessions, first)
    if kind == "SESSION_DAILY_KR":
        expected = windows
    else:  # WEEKLY_LAST_KR_SESSION: window of a weekly signal is the same session window, expected set is the week-end sessions only
        weekly = set(weekly_last_sessions(sessions, first))
        expected = {day: end for day, end in windows.items() if day in weekly}
    valid, errors = verify_rows(rows, study, windows, as_of, date_field)
    closed, missed, pending = classify_windows(expected, valid, as_of)
    cadence_days = study.get("monitoring", {}).get("maxStaleCalendarDays", DEFAULT_DAILY_STALE_DAYS if kind == "SESSION_DAILY_KR" else 9)
    out["freshness"] = _freshness(out["lastRecordSession"], as_of, cadence_days, "REGISTERED_CADENCE:" + kind, last_commit_utc)
    mon = study.get("monitoring", {})
    ledger_baseline = mon.get("continuityBaselineSession")
    historic = [day for day in missed if ledger_baseline and day <= ledger_baseline]
    active_missed = [day for day in missed if not (ledger_baseline and day <= ledger_baseline)]
    if errors or baseline["state"] == "VIOLATED":
        completeness = {"state": "NOT_ASSESSABLE", "basis": "RECEIPT_INTEGRITY_ERRORS"}
    elif missed:
        completeness = {"state": "INCOMPLETE", "basis": "CLOSED_WINDOWS_WITHOUT_VALID_RECEIPT"}
    elif closed:
        completeness = {"state": "VERIFIED_COMPLETE", "basis": "EVERY_CLOSED_WINDOW_HAS_ONE_VALID_RECEIPT"}
    else:
        completeness = {"state": "NOT_ASSESSABLE", "basis": "NO_CLOSED_WINDOW_YET"}
    out.update(scheduledRecords=len(closed), validRecords=len(closed) - len(missed), missedRecords=len(missed), completeness=completeness,
               missedSessions=missed, missedNotObservedBeforeBaseline=historic, pendingSessions=pending, receiptErrors=errors,
               continuityBaselineSession=ledger_baseline)
    if study.get("horizons") and any("events" in r for r in rows):
        as_of_session = max((s for s in sessions if _at(s, 0) <= as_of), default=sessions[0])
        for horizon in study["horizons"]:
            out["independentObservations"][f"H{horizon}"] = maturity_summary(independent_observations(rows, valid, sessions, horizon), as_of_session)
    active_closed = [day for day in closed if not ledger_baseline or day > ledger_baseline]
    out["operationalContinuity"] = {
        "closedWindows": len(active_closed), "missedWindows": len(active_missed),
    }
    if baseline["state"] == "VIOLATED":
        out.update(operatingState="EXECUTION_FAILED", failureReason="BASELINE_RECEIPTS_ALTERED_OR_MISSING")
    elif errors:
        out.update(operatingState="EXECUTION_FAILED", failureReason="RECEIPT_INTEGRITY_ERRORS:" + ",".join(sorted({r for e in errors for r in e["reasons"]})))
    elif writer_outcome == "failure":
        out.update(operatingState="EXECUTION_FAILED", failureReason="LATEST_WRITER_RUN_FAILED")
    elif source_blocked_reason:
        out.update(operatingState="SOURCE_BLOCKED", failureReason=source_blocked_reason)
    elif active_missed:
        out.update(operatingState="MISSED", failureReason="CLOSED_WINDOW_WITHOUT_VALID_RECEIPT")
    elif automation.get("enabled") is not True:
        out.update(operatingState="DISABLED", failureReason="WRITER_NOT_ACTIVATED")
    elif active_closed and out["freshness"]["state"] == "FRESH":
        out["operatingState"] = "HEALTHY"
    else:
        out.update(operatingState="PENDING", failureReason="NOT_YET_VERIFIED_COMPLETE_OR_FRESH")
    return out


def build_status(registry: dict, ledger_rows: dict, sessions: Sequence[str], as_of: datetime, *,
                 commits: dict[str, str | None] | None = None, writer_outcomes: dict[str, str] | None = None) -> dict:
    problems = validate_registry(registry)
    if problems:
        raise ValueError("REGISTRY_INVALID: " + "; ".join(problems))
    commits = commits or {}
    writer_outcomes = writer_outcomes or {}
    studies = [study_status(s, ledger_rows.get(s["studyId"]), sessions, as_of, last_commit_utc=commits.get(s["studyId"]),
                            writer_outcome=writer_outcomes.get(s["studyId"])) for s in registry["studies"]]
    # An alert is only owed by a study the owner has enabled for automation: a disabled writer is a known state, not an incident.
    # Exceptions that are incidents whether or not a writer is enabled: altered baseline receipts, and an approved study's ledger that cannot be read.
    alerts = [s["studyId"] for s, entry in zip(studies, registry["studies"])
              if (entry.get("automation", {}).get("enabled") and s["operatingState"] in ("MISSED", "EXECUTION_FAILED", "SOURCE_BLOCKED"))
              or (s.get("baselineImmutability") or {}).get("state") == "VIOLATED"
              or (entry.get("ledgerMustExist") and (
                  s["ledgerRead"] in (LEDGER_READ_FAILED, LEDGER_ABSENT) or bool(s.get("receiptErrors"))
              ))]
    return {"schema": STATUS_SCHEMA, "asOfUtc": as_of.isoformat(), "studies": studies, "alerts": alerts,
            "notes": ["Status is derived from receipts only; a successful workflow run is not a receipt.",
                      "Missed windows are MISSED_NOT_OBSERVED and are never back-filled, re-dated or read as zero events.",
                      "Independent observations come from valid receipts under each study's registered independence rule; raw event counts are not sample size."]}


# ------------------------------------------------------------------------------------------------- guard
def cutover_refusals(study: dict, facts: dict) -> list[str]:
    attestation = facts.get("attestation")
    if not isinstance(attestation, dict) or attestation.get("studyId") != study["studyId"]:
        return ["SINGLE_WRITER_ATTESTATION_MISSING"]
    reasons = []
    if (attestation.get("schema") != CUTOVER_SCHEMA or attestation.get("successor") != SUCCESSOR
            or attestation.get("legacyRunsDrained") is not True or attestation.get("retiredPermanently") is not True
            or attestation.get("pinnedCodeCommit") != study["automation"].get("pinnedCodeCommit")
            or attestation.get("authorizationSha256") != study["approval"].get("authorizationSha256")):
        reasons.append("SINGLE_WRITER_CUTOVER_SCOPE_MISMATCH")
    try:
        approved_at = facts["ownerApprovalAt"]
        attested_at = parse_utc(attestation["attestedAtUtc"])
        if not attested_at <= approved_at <= min(facts["asOf"], attested_at + CUTOVER_READBACK_MAX_AGE):
            reasons.append("SINGLE_WRITER_APPROVAL_TIME_INVALID")
    except (KeyError, TypeError, ValueError, AttributeError):
        attested_at = None
        reasons.append("SINGLE_WRITER_APPROVAL_TIME_INVALID")
    legacy = {item["id"] for item in study.get("writer", {}).get("legacyWriters", [])}
    if study["studyId"] == CORPORATE_STUDY and legacy != CORPORATE_LEGACY_WRITERS:
        reasons.append("REGISTERED_LEGACY_WRITERS_CHANGED")
        legacy = CORPORATE_LEGACY_WRITERS
    readbacks = attestation.get("readbacks")
    if not isinstance(readbacks, list) or not all(isinstance(item, dict) and isinstance(item.get("id"), str) for item in readbacks):
        return reasons + ["LEGACY_WRITER_STATE_EVIDENCE_INVALID"]
    by_id = {item["id"]: item for item in readbacks}
    if len(by_id) != len(readbacks) or set(by_id) != legacy:
        reasons.append("LEGACY_WRITER_READBACK_IDS_MISMATCH")
    for trigger in sorted(legacy & set(by_id)):
        item = by_id[trigger]
        if item.get("enabled") is not False or item.get("source") != "CLAUDE_GET_TRIGGER_READBACK":
            reasons.append(f"LEGACY_WRITER_NOT_VERIFIED_DISABLED:{trigger}")
        try:
            observed_at = parse_utc(item["readbackUtc"])
            if attested_at is None or not attested_at - CUTOVER_READBACK_MAX_AGE <= observed_at <= attested_at:
                reasons.append(f"LEGACY_WRITER_READBACK_OUTSIDE_CUTOVER_WINDOW:{trigger}")
        except (KeyError, TypeError, ValueError, AttributeError):
            reasons.append(f"LEGACY_WRITER_READBACK_TIMESTAMP_INVALID:{trigger}")
    return reasons


def guard_decision(study: dict, facts: dict) -> dict:
    """Pre-write decision from evidence the CLI gathered. Every refusal is a reason code; missing evidence refuses (fail closed). Never writes.

    `facts` keys: attestation (parsed or None), authorization (parsed or None), authorizationBytesSha256, specBytesSha256, pinnedCommitPresent,
    pinnedTreeSha, durablyReferenced, ledger (a ledger read), integrityErrors, asOf (datetime).
    Hashes are of the BYTES at the pinned commit and are compared with the registry; a parsed field alone is never accepted.
    """
    reasons: list[str] = []
    automation = study.get("automation", {})
    approval = study["approval"]
    if approval.get("status") != APPROVED:  # only an owner-hashed authorization may drive an Actions writer
        reasons.append("STUDY_NOT_APPROVED")
    if automation.get("enabled") is not True:
        reasons.append("AUTOMATION_NOT_ENABLED_BY_OWNER")
    if not facts.get("pinnedCommitPresent"):
        reasons.append("PINNED_CODE_COMMIT_UNAVAILABLE")
    else:
        if automation.get("pinnedTreeSha") and facts.get("pinnedTreeSha") != automation["pinnedTreeSha"]:
            reasons.append("PINNED_TREE_HASH_MISMATCH")
        if not facts.get("durablyReferenced"):
            reasons.append("PINNED_CODE_NOT_DURABLY_REFERENCED")
    # The authorization and the spec are checked by the sha256 of their bytes at the pinned commit against the registered hashes; the
    # parsed studyId/specSha256 fields only have to agree on top of that, they can never substitute for it.
    authorization = facts.get("authorization")
    if facts.get("authorizationBytesSha256") != approval.get("authorizationSha256"):
        reasons.append("AUTHORIZATION_BYTES_HASH_MISMATCH")
    if facts.get("specBytesSha256") != approval.get("specSha256"):
        reasons.append("SPEC_BYTES_HASH_MISMATCH")
    if (authorization is None or authorization.get("specSha256") != approval.get("specSha256")
            or authorization.get("studyId") != study["studyId"]):
        reasons.append("AUTHORIZATION_FIELDS_MISMATCH")
    cutover_state = "NOT_REQUIRED"
    if study.get("writer", {}).get("legacyWriters") or study["studyId"] == CORPORATE_STUDY:
        cutover_errors = cutover_refusals(study, facts)
        reasons.extend(cutover_errors)
        cutover_state = "UNVERIFIED" if cutover_errors else "OWNER_APPROVED_READBACK"
    if facts.get("baselineBytesMatch") is False or (study.get("baselineLedger") and facts.get("baselineBytesMatch") is not True):
        reasons.append("BASELINE_LEDGER_BYTES_CHANGED")
    ledger = coerce_read(facts.get("ledger"))
    if ledger["state"] == LEDGER_READ_FAILED:
        reasons.append("LEDGER_READ_FAILED")
    elif ledger["state"] == LEDGER_ABSENT and study.get("ledgerMustExist"):
        reasons.append("LEDGER_FILE_ABSENT_FOR_STUDY_WITH_EXISTING_RECEIPTS")
    elif ledger["state"] in (LEDGER_ROWS, LEDGER_EMPTY_VALID):
        if verify_baseline(ledger["rows"], study)["state"] == "VIOLATED":
            reasons.append("BASELINE_RECEIPTS_ALTERED_OR_MISSING")
        if ledger["state"] == LEDGER_EMPTY_VALID and study.get("ledgerMustExist"):
            reasons.append("LEDGER_EMPTY_FOR_STUDY_WITH_EXISTING_RECEIPTS")
    if facts.get("integrityErrors"):
        reasons.append("REMOTE_LEDGER_INTEGRITY_ERRORS")
    return {"studyId": study["studyId"], "decision": "REFUSE" if reasons else "ALLOW_WRITE", "reasons": sorted(set(reasons)),
            "ledgerRead": ledger["state"],
            "cutoverEvidence": cutover_state}


def verify_new_receipt(rows: list[dict], study: dict, session: str, windows: dict[str, datetime], as_of: datetime) -> dict:
    """After a writer run: exactly one valid receipt for `session` must be on the remote ledger. A green job is not this."""
    matching = [r for r in rows if r.get(study.get("dateField", "signalDate")) == session]
    valid, errors = verify_rows(rows, study, windows, as_of, study.get("dateField", "signalDate"))
    ok = len(matching) == 1 and session in valid and not errors
    return {"session": session, "rowsForSession": len(matching), "valid": ok, "errors": errors,
            "result": "RECORDED_AND_VERIFIED" if ok else "NOT_RECORDED"}


__all__ = ["APPROVED", "APPROVED_BY_MERGE", "window_session", "writer_session", "verify_baseline", "coerce_read", "STATES", "build_status", "guard_decision", "study_status", "validate_registry", "verify_new_receipt"]
