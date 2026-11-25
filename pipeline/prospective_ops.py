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
from datetime import date, datetime, timezone

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
def verify_rows(rows: list[dict], study: dict, windows: dict[str, datetime], as_of: datetime, date_field: str = "signalDate") -> tuple[set[str], list[dict]]:
    """Valid session set and structured errors. A row is valid only if registration, digest, mode and its own window all hold."""
    approval = study["approval"]
    errors: list[dict] = []
    valid: set[str] = set()
    seen: set[str] = set()
    for number, row in enumerate(rows, 1):
        day = row.get(date_field)
        problems: list[str] = []
        if day in seen:
            problems.append("DUPLICATE_SESSION")
            valid.discard(day)
        seen.add(day)
        if (row.get("studyId") != study["studyId"] or row.get("specSha256") != approval["specSha256"]
                or row.get("authorizationSha256") != approval["authorizationSha256"]
                or row.get("evidenceClass") != study.get("evidenceClass", "PROSPECTIVE_PAPER")
                or row.get("mode") != study.get("recordMode", "LIVE")):
            problems.append("REGISTRATION_OR_MODE_MISMATCH")
        if row.get("receiptSha256") != receipt_digest(row):
            problems.append("DIGEST_MISMATCH")
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
    return {"independentObservations": len(kept), "evaluable": len(mature), "nextMaturity": upcoming[0] if upcoming else None}


# ------------------------------------------------------------------------------------------------- status
def study_status(study: dict, rows: list[dict] | None, sessions: Sequence[str], as_of: datetime, *, last_commit_utc: str | None = None,
                 writer_outcome: str | None = None, source_blocked_reason: str | None = None) -> dict:
    """One row of the operations ledger. `rows is None` means the ledger is absent (never a zero-observation claim)."""
    approval = study["approval"]
    automation = study.get("automation", {})
    out: dict = {"studyId": study["studyId"], "approvalStatus": approval.get("status"), "automationEnabled": bool(automation.get("enabled")),
                 "kind": study["kind"], "writer": study.get("writer", {}).get("description"),
                 "lastSuccessfulExecution": writer_outcome, "dataFreshness": None, "scheduledRecords": None, "validRecords": None,
                 "missedRecords": None, "lastRecordSession": None, "nextRun": study.get("schedule", {}).get("description"),
                 "independentObservations": {}, "failureReason": None}
    if approval.get("status") not in APPROVED_STATUSES:
        out.update(operatingState="UNAUTHORIZED", failureReason="NO_OWNER_AUTHORIZATION_FOR_RECORDING")
        return out
    if rows is None:
        out.update(operatingState="SOURCE_BLOCKED", failureReason="LEDGER_FILE_ABSENT_ON_REF")
        return out
    date_field = study.get("dateField", "signalDate")
    all_days = [row.get(date_field) for row in rows if row.get(date_field)]
    out["lastRecordSession"] = max(all_days) if all_days else None
    out["dataFreshness"] = {"lastCommitUtc": last_commit_utc, "asOfUtc": as_of.isoformat()}
    kind = study["kind"]
    if kind == "OBSERVED_ONLY":
        stale_days = study["monitoring"]["maxStaleCalendarDays"]
        age = (as_of.date() - date.fromisoformat(out["lastRecordSession"])).days if out["lastRecordSession"] else None
        out.update(validRecords=len(set(all_days)), scheduledRecords=None, missedRecords=None,
                   completenessClaim="NONE_CADENCE_NOT_REGISTERED", ageCalendarDays=age)
        out["operatingState"] = "HEALTHY" if age is not None and age <= stale_days else "MISSED"
        if out["operatingState"] == "MISSED":
            out["failureReason"] = "LAST_RECORD_OLDER_THAN_MONITORING_THRESHOLD"
        return out
    first = study["firstEligibleSession"]
    if kind == "SESSION_DAILY_KR":
        windows = session_windows(sessions, first)
        expected = windows
    else:  # WEEKLY_LAST_KR_SESSION: window of a weekly signal is the same session window, expected set is the week-end sessions only
        windows = session_windows(sessions, first)
        weekly = set(weekly_last_sessions(sessions, first))
        expected = {day: end for day, end in windows.items() if day in weekly}
    valid, errors = verify_rows(rows, study, windows, as_of, date_field)
    closed, missed, pending = classify_windows(expected, valid, as_of)
    baseline = study.get("monitoring", {}).get("continuityBaselineSession")
    historic = [day for day in missed if baseline and day <= baseline]
    active_missed = [day for day in missed if not (baseline and day <= baseline)]
    out.update(scheduledRecords=len(closed), validRecords=len(closed) - len(missed), missedRecords=len(missed),
               missedSessions=missed, missedNotObservedBeforeBaseline=historic, pendingSessions=pending, receiptErrors=errors,
               continuityBaselineSession=baseline)
    # horizons / independence (only where the study registers an independence rule and receipts carry events)
    if study.get("horizons") and any("events" in r for r in rows):
        as_of_session = max((s for s in sessions if _at(s, 0) <= as_of), default=sessions[0])
        for horizon in study["horizons"]:
            out["independentObservations"][f"H{horizon}"] = maturity_summary(independent_observations(rows, valid, sessions, horizon), as_of_session)
    if errors:
        out.update(operatingState="EXECUTION_FAILED", failureReason="RECEIPT_INTEGRITY_ERRORS:" + ",".join(sorted({r for e in errors for r in e["reasons"]})))
    elif writer_outcome == "failure":
        out.update(operatingState="EXECUTION_FAILED", failureReason="LATEST_WRITER_RUN_FAILED")
    elif source_blocked_reason:
        out.update(operatingState="SOURCE_BLOCKED", failureReason=source_blocked_reason)
    elif active_missed:
        out.update(operatingState="MISSED", failureReason="CLOSED_WINDOW_WITHOUT_VALID_RECEIPT")
    elif not automation.get("enabled") and not (rows and valid):
        out.update(operatingState="DISABLED", failureReason="WRITER_NOT_ACTIVATED")
    elif pending and not valid:
        out["operatingState"] = "PENDING"
    elif not automation.get("enabled"):
        out.update(operatingState="DISABLED", failureReason="WRITER_NOT_ACTIVATED")
    else:
        out["operatingState"] = "HEALTHY"
    return out


def build_status(registry: dict, ledger_rows: dict[str, list[dict] | None], sessions: Sequence[str], as_of: datetime, *,
                 commits: dict[str, str | None] | None = None, writer_outcomes: dict[str, str] | None = None) -> dict:
    problems = validate_registry(registry)
    if problems:
        raise ValueError("REGISTRY_INVALID: " + "; ".join(problems))
    commits = commits or {}
    writer_outcomes = writer_outcomes or {}
    studies = [study_status(s, ledger_rows.get(s["studyId"]), sessions, as_of, last_commit_utc=commits.get(s["studyId"]),
                            writer_outcome=writer_outcomes.get(s["studyId"])) for s in registry["studies"]]
    # An alert is only owed by a study the owner has enabled for automation: a disabled writer is a known state, not an incident.
    alerts = [s["studyId"] for s, entry in zip(studies, registry["studies"])
              if entry.get("automation", {}).get("enabled") and s["operatingState"] in ("MISSED", "EXECUTION_FAILED", "SOURCE_BLOCKED")]
    return {"schema": STATUS_SCHEMA, "asOfUtc": as_of.isoformat(), "studies": studies, "alerts": alerts,
            "notes": ["Status is derived from receipts only; a successful workflow run is not a receipt.",
                      "Missed windows are MISSED_NOT_OBSERVED and are never back-filled, re-dated or read as zero events.",
                      "Independent observations come from valid receipts under each study's registered independence rule; raw event counts are not sample size."]}


# ------------------------------------------------------------------------------------------------- guard
def guard_decision(study: dict, attestation: dict | None, authorization: dict | None, pinned_commit_present: bool,
                   remote_errors: list[dict]) -> dict:
    """Pre-write decision. Every refusal is a reason code; absence of evidence refuses (fail closed). Never writes."""
    reasons: list[str] = []
    automation = study.get("automation", {})
    if study["approval"].get("status") != APPROVED:  # only an owner-hashed authorization may drive an Actions writer
        reasons.append("STUDY_NOT_APPROVED")
    if not automation.get("enabled"):
        reasons.append("AUTOMATION_NOT_ENABLED_BY_OWNER")
    if not pinned_commit_present:
        reasons.append("PINNED_CODE_COMMIT_UNAVAILABLE")
    if authorization is None or authorization.get("specSha256") != study["approval"]["specSha256"] or authorization.get("studyId") != study["studyId"]:
        reasons.append("AUTHORIZATION_OR_SPEC_MISMATCH")
    legacy = study.get("writer", {}).get("legacyWriters", [])
    if legacy:
        states = (attestation or {}).get("legacyWriterStates", {})
        if attestation is None or attestation.get("studyId") != study["studyId"]:
            reasons.append("SINGLE_WRITER_ATTESTATION_MISSING")
        for item in legacy:
            if states.get(item["id"]) != "DISABLED":
                reasons.append(f"LEGACY_WRITER_NOT_ATTESTED_DISABLED:{item['id']}")
    if remote_errors:
        reasons.append("REMOTE_LEDGER_INTEGRITY_ERRORS")
    return {"studyId": study["studyId"], "decision": "REFUSE" if reasons else "ALLOW_WRITE", "reasons": sorted(set(reasons))}


def verify_new_receipt(rows: list[dict], study: dict, session: str, windows: dict[str, datetime], as_of: datetime) -> dict:
    """After a writer run: exactly one valid receipt for `session` must be on the remote ledger. A green job is not this."""
    matching = [r for r in rows if r.get(study.get("dateField", "signalDate")) == session]
    valid, errors = verify_rows(rows, study, windows, as_of, study.get("dateField", "signalDate"))
    ok = len(matching) == 1 and session in valid
    return {"session": session, "rowsForSession": len(matching), "valid": ok, "errors": [e for e in errors if e["session"] == session],
            "result": "RECORDED_AND_VERIFIED" if ok else "NOT_RECORDED"}


__all__ = ["APPROVED", "APPROVED_BY_MERGE", "STATES", "build_status", "guard_decision", "study_status", "validate_registry", "verify_new_receipt"]
