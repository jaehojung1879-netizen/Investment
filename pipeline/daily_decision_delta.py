"""Read-only two-snapshot comparison for Portfolio D's existing daily brief.

This operates on *already-rendered* report.json files. It does not authenticate
GitHub source bytes, construct signals, evaluate outcomes or make allocations.
UNKNOWN is None and must never be interpreted as numeric zero.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re

SCHEMA = "READ_ONLY_DAILY_DECISION_REPORT_V1"
_SHA = re.compile(r"[a-f0-9]{40}\Z")
REGION_FIELDS = (
    ("observedSession", "REGION_OBSERVED_SESSION"),
    ("lastValidFinalSession", "REGION_FINAL_SESSION"),
    ("persistedWeekStatus", "REGION_WEEK_STATUS"),
    ("persistedPolicyStatus", "REGION_POLICY_STATUS"),
)
STUDY_FIELDS = (
    ("recordedReceipts", "PAPER_RECEIPT_COUNT"),
    ("maturedRecordedOutcomes", "PAPER_MATURED_OUTCOME_COUNT"),
    ("eligibleCounts", "PAPER_ELIGIBILITY_COUNT"),
    ("aggregateStatus", "PAPER_AGGREGATE_STATUS"),
    ("errors", "PAPER_SOURCE_ERRORS"),
)


def _when(value):
    if not isinstance(value, str):
        raise ValueError("AWARE_ISO_REPORT_TIMESTAMP_REQUIRED")
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("AWARE_ISO_REPORT_TIMESTAMP_REQUIRED") from exc
    if t.tzinfo is None:
        raise ValueError("AWARE_ISO_REPORT_TIMESTAMP_REQUIRED")
    return t.astimezone(timezone.utc)


def _validate(report):
    if not isinstance(report, dict) or report.get("schema") != SCHEMA:
        raise ValueError("VALID_DAILY_REPORT_SCHEMA_REQUIRED")
    commit = report.get("sourceCommitSha")
    if not isinstance(commit, str) or _SHA.fullmatch(commit) is None:
        raise ValueError("FULL_SOURCE_COMMIT_REQUIRED")
    report_time = _when(report.get("reportAsOfUtc"))
    if _when(report.get("sourceCommitTimestamp")) > report_time:
        raise ValueError("SOURCE_FUTURE_OF_REPORT")
    safety = report.get("safety")
    if (not isinstance(safety, dict) or safety.get("readOnly") is not True
            or safety.get("historicalOutcomesExecuted") is not False
            or safety.get("productionEffect") != "NONE"):
        raise ValueError("READ_ONLY_NO_OUTCOME_REPORT_REQUIRED")
    if (not isinstance(report.get("regions"), dict)
            or set(report["regions"]) != {"KR", "US"}
            or not isinstance(report.get("paperStudies"), dict)
            or not isinstance(report.get("sources"), dict)):
        raise ValueError("COMPLETE_REPORT_SHAPE_REQUIRED")
    for region in ("KR", "US"):
        value = report["regions"][region]
        if not isinstance(value, dict) or not isinstance(value.get("freshnessAtReport"), dict):
            raise ValueError("REGION_FRESHNESS_SHAPE_REQUIRED")
        if value.get("newNominationsInThisReport") != 0 or value.get("evidenceCertifiedCandidateCount") is not None:
            raise ValueError("NO_NEW_APPROVED_NOMINATIONS_IN_REPORT")
    for study in report["paperStudies"].values():
        if not isinstance(study, dict):
            raise ValueError("PAPER_STUDY_SHAPE_REQUIRED")
        for key in ("recordedReceipts", "maturedRecordedOutcomes"):
            v = study.get(key)
            if v is not None and (type(v) is not int or v < 0):
                raise ValueError("PAPER_COUNTS_NONNEGATIVE_OR_UNKNOWN")
    return report_time


def compare(before, after):
    """Compare two explicit immutable-source report snapshots; no computation of returns."""
    previous, current = _validate(before), _validate(after)
    if current <= previous:
        raise ValueError("CURRENT_REPORT_MUST_HAVE_LATER_AS_OF")
    events = []

    def record(scope, key, kind, old, new):
        if old != new:
            events.append({"scope": scope, "key": key, "kind": kind, "before": old, "after": new})

    for region in ("KR", "US"):
        earlier, latest = before["regions"][region], after["regions"][region]
        for key, kind in REGION_FIELDS:
            record(region, key, kind, earlier.get(key), latest.get(key))
        for key in ("status", "expectedSession", "sourceDate"):
            record(region, "freshnessAtReport." + key, "REGION_FRESHNESS",
                   earlier["freshnessAtReport"].get(key), latest["freshnessAtReport"].get(key))
        record(region, "certificationReason", "CERTIFICATION_GATE",
               earlier.get("certificationReason"), latest.get("certificationReason"))

    for study in sorted(set(before["paperStudies"]) | set(after["paperStudies"])):
        earlier = before["paperStudies"].get(study)
        latest = after["paperStudies"].get(study)
        if earlier is None or latest is None:
            record(study, "studyAvailable", "PAPER_STUDY_SCOPE", earlier is not None, latest is not None)
            continue
        for key, kind in STUDY_FIELDS:
            record(study, key, kind, earlier.get(key), latest.get(key))
        for key in ("status", "reason", "runId", "attemptedAt"):
            record(study, "latestRecordAttempt." + key, "PAPER_ATTEMPT",
                   (earlier.get("latestRecordAttempt") or {}).get(key),
                   (latest.get("latestRecordAttempt") or {}).get(key))
        record(study, "latestReceipt.receiptSha256", "PAPER_RECEIPT_ID",
               (earlier.get("latestReceipt") or {}).get("receiptSha256"),
               (latest.get("latestReceipt") or {}).get("receiptSha256"))

    def source_counts(snapshot):
        statuses = [s.get("status") for s in snapshot["sources"].values() if isinstance(s, dict)]
        return {"READ": statuses.count("READ"), "MISSING": statuses.count("MISSING"),
                "OTHER": len(statuses) - statuses.count("READ") - statuses.count("MISSING")}
    record("source", "pathStatusCounts", "SOURCE_READ_STATUS",
           source_counts(before), source_counts(after))
    record("source", "commitSha", "SOURCE_COMMIT_ID",
           before["sourceCommitSha"], after["sourceCommitSha"])
    return {
        "schema": "READ_ONLY_DAILY_DECISION_DELTA_V1",
        "status": "REPORTED_FIELDS_CHANGED" if events else "NO_TRACKED_FIELD_CHANGE",
        "earlierReportAsOfUtc": previous.isoformat(),
        "laterReportAsOfUtc": current.isoformat(),
        "earlierSourceCommitSha": before["sourceCommitSha"],
        "laterSourceCommitSha": after["sourceCommitSha"],
        "comparisonAuthority": "UNVERIFIED_INPUT_REPORTS_NOT_SOURCE_REATTESTATION",
        "changes": events,
        "safety": {
            "readOnly": True, "productionEffect": "NONE",
            "signalsGenerated": False, "historicalOutcomesRecomputed": False,
            "researchEvidenceAdmitted": False, "investmentRecommendation": False,
            "unknownIsNotZero": True,
        },
    }
