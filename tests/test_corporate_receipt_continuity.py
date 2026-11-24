from scripts.audit_corporate_receipt_continuity import CODE, STUDY, digest, inspect, utc

DAYS = ["2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13"]
SPEC = "a" * 64
AUTH = "b" * 64


def row(day, stamp=None, events=None):
    events = [] if events is None else events
    value = {"studyId": STUDY, "signalDate": day, "createdAtUtc": stamp or day + "T10:40:00Z",
             "mode": "LIVE", "evidenceClass": "PROSPECTIVE_PAPER", "specSha256": SPEC,
             "authorizationSha256": AUTH, "codeCommit": CODE, "events": events, "eventCount": len(events)}
    value["receiptSha256"] = digest(value)
    return value


def check(rows, cutoff="2026-11-11T10:45:00Z", days=DAYS):
    return inspect(rows, days, DAYS[0], utc(cutoff), SPEC, AUTH)


def test_zero_events_is_valid_but_missing_is_not():
    result = check([row(DAYS[0])])
    assert result["validClosedWindows"] == 1
    assert result["missingClosedSessions"] == [DAYS[1]]
    assert result["pendingOpenSessions"] == [DAYS[2]]


def test_pending_does_not_fail():
    result = check([row(DAYS[0]), row(DAYS[1])])
    assert result["status"] == "OK"


def test_next_open_is_exclusive():
    result = check([row(DAYS[0], "2026-11-10T00:00:00Z")])
    assert "OUTSIDE_AUTHORIZED_WINDOW" in result["errors"][0]["reasons"]
    assert DAYS[0] in result["missingClosedSessions"]


def test_digest_and_registration():
    value = row(DAYS[0])
    value["mode"] = "DRY_RUN"
    reasons = check([value])["errors"][0]["reasons"]
    assert reasons == ["REGISTRATION_OR_MODE_MISMATCH", "DIGEST_MISMATCH"]


def test_duplicate_invalidates_session():
    value = row(DAYS[0])
    result = check([value, value])
    assert DAYS[0] in result["missingClosedSessions"]
    assert "DUPLICATE_SESSION" in result["errors"][0]["reasons"]


def test_nontrading_days_not_required():
    days = [DAYS[0], DAYS[2], DAYS[4]]
    result = check([row(DAYS[0])], days=days)
    assert result["status"] == "OK"
    assert result["pendingOpenSessions"] == [DAYS[2]]
