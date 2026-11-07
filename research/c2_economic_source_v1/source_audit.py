"""Qualify source observations without producing returns, NAV or attribution.

This complements the pinned #317 economic gate and #320 issuer parser. Their
declarations do not prove payload integrity, historical vintage or execution.
No source status produced here authorizes historical research or live trading.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import subprocess


class SourceError(ValueError):
    """A missing fact is a refusal, never a substituted cash flow or price."""


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_digest(value) -> str:
    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode())


def verified_payload(path: Path, expected_sha256: str) -> bytes:
    raw = path.read_bytes()
    if digest(raw) != expected_sha256:
        raise SourceError("SOURCE_PAYLOAD_HASH_MISMATCH")
    return raw


def pinned_bytes(repo: Path, pin: dict) -> bytes:
    """Read an already available Git object, with no lazy fetch or branch write."""
    commit, path = pin["commit"], pin["path"]
    if (len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit)
            or not path.startswith("research/") or ".." in Path(path).parts):
        raise SourceError("INVALID_REFERENCE_PIN")
    try:
        raw = subprocess.run(
            ["git", "--no-replace-objects", "-c", "remote.origin.promisor=false",
             "show", f"{commit}:{path}"], cwd=repo, check=True,
            capture_output=True, timeout=30).stdout
    except (subprocess.SubprocessError, OSError) as exc:
        raise SourceError("PINNED_REFERENCE_OBJECT_UNAVAILABLE") from exc
    if digest(raw) != pin["sha256"]:
        raise SourceError("PINNED_REFERENCE_HASH_MISMATCH")
    return raw


def _day(value) -> str:
    text = str(value)
    if len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise SourceError("INVALID_SOURCE_DATE") from exc


def _number(value) -> Decimal | None:
    if isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).replace(",", ""))
        return number if number.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def audit_market_rows(dates, read_value, *, expected_sessions, through: str) -> dict:
    """Inspect actual close/volume, filtering dates BEFORE accessing values.

    ``read_value(index, column)`` exposes only columns 1 (market close) and 4
    (reported volume) of the verified issuer XLS. The provider's NAV, price
    changes and published performance are never selected. Future rows remain
    quarantined even when the requested cutoff is printed in the XLS header.
    Positive volume is necessary evidence; it does not establish a fill/spread.
    """
    cutoff = _day(through)
    expected = [_day(d) for d in expected_sessions]
    if not expected or expected != sorted(set(expected)) or expected[-1] > cutoff:
        raise SourceError("ORDERED_INDEPENDENT_SESSION_GRID_REQUIRED")
    actual = [_day(d) for d in dates]
    if len(set(actual)) != len(actual):
        raise SourceError("DUPLICATE_PRICE_DATE")
    eligible = set()
    future = []
    bad_price, bad_volume, zero = [], [], []
    for index, day in enumerate(actual):
        if day > cutoff:
            future.append(day)
            continue
        if day < expected[0]:
            continue
        eligible.add(day)
        close, volume = (_number(read_value(index, column)) for column in (1, 4))
        if close is None or close <= 0:
            bad_price.append(day)
        if volume is None or volume < 0 or volume != volume.to_integral_value():
            bad_volume.append(day)
        elif volume == 0:
            zero.append(day)
    missing = sorted(set(expected) - eligible)
    unexpected = sorted(eligible - set(expected))
    blockers = [code for code, failed in (
        ("MISSING_EXPECTED_SESSIONS", missing), ("OFF_CALENDAR_OBSERVATIONS", unexpected),
        ("INVALID_MARKET_CLOSE", bad_price), ("INVALID_REPORTED_VOLUME", bad_volume),
        ("ZERO_REPORTED_VOLUME", zero)) if failed]
    return {
        "status": "BLOCKED" if blockers else "OBSERVED_MARKET_INPUTS_COVER_GRID",
        "from": expected[0], "through": cutoff,
        "expectedSessions": len(expected), "observedSessions": len(eligible),
        "calendarSha256": canonical_digest(expected), "missingSessions": missing,
        "offCalendarDates": unexpected, "invalidCloseDates": sorted(bad_price),
        "invalidVolumeDates": sorted(bad_volume), "zeroVolumeDates": sorted(zero),
        "quarantinedAfterCutoff": sorted(future), "blockers": blockers,
        "valuesRetained": False, "returnsComputed": 0,
        "historicalVintageVerified": False, "actualFillVerified": False,
        "outcomeExecutionAuthorized": False,
    }


def audit_issuer_xls(raw: bytes, *, issuer_parser, expected_sessions, through: str) -> dict:
    """Reuse #320's exact schema/date parser; xlrd is an optional offline tool."""
    import xlrd

    projection = issuer_parser.project_price_dates(raw)
    dates = json.loads(projection)["dates"]
    sheet = xlrd.open_workbook(file_contents=raw).sheet_by_index(0)
    result = audit_market_rows(
        dates, lambda index, column: sheet.cell_value(index + 4, column),
        expected_sessions=expected_sessions, through=through)
    result.update(sourceSha256=digest(raw), dateProjectionSha256=digest(projection),
                  requestedHeader=str(sheet.cell_value(1, 0)),
                  xlsParserVersion=xlrd.__version__,
                  headerIsPublicationVintage=False)
    return result


def qualify_distributions(events: list[dict], notices: list[dict], *, through: str) -> dict:
    """Match independently transcribed issuer notices to exact cash events.

    A notice needs an identity, amount, record date, explicit ex-date and the
    original body/image digests. It is not inferred from a settlement calendar.
    Payment date and record date never decide whether an event belongs before
    the cutoff. Unmatched events remain unresolved, including boundary events.
    Actual raw bytes must separately pass ``verified_payload`` before callers
    describe the evidence as verified. This is a field-consistency check only.
    """
    cutoff = _day(through)
    indexed = {}
    for notice in notices:
        if notice.get("ticker") != "153130":
            raise SourceError("NOTICE_SECURITY_MISMATCH")
        key = _day(notice["recordDate"])
        if key in indexed:
            raise SourceError("DUPLICATE_NOTICE_RECORD_DATE")
        ex_date = _day(notice["exDate"])
        published = _day(notice["publishedDate"])
        if not published <= ex_date <= key <= _day(notice["payDate"]):
            raise SourceError("NOTICE_DATE_SEQUENCE_INVALID")
        for field in ("bodySha256", "scheduleSha256"):
            sha = notice.get(field, "")
            if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
                raise SourceError("EX_DATE_ORIGINAL_DIGEST_REQUIRED")
        indexed[key] = {**notice, "exDate": ex_date, "publishedDate": published}
    seen, resolved, unresolved = set(), [], []
    for event in events:
        if event.get("ticker") != "153130":
            raise SourceError("DISTRIBUTION_SECURITY_MISMATCH")
        record = _day(event["recordDate"])
        if _day(event["payDate"]) < record:
            raise SourceError("DISTRIBUTION_DATE_SEQUENCE_INVALID")
        if record in seen:
            raise SourceError("DUPLICATE_DISTRIBUTION_EVENT")
        seen.add(record)
        amount = _number(event["grossCash"])
        if amount is None or amount < 0:
            raise SourceError("INVALID_GROSS_DISTRIBUTION")
        notice = indexed.get(record)
        if notice is None:
            unresolved.append(record)
            continue
        if (_number(notice["grossCash"]) != amount
                or _day(notice["payDate"]) != _day(event["payDate"])):
            raise SourceError("ISSUER_NOTICE_EVENT_MISMATCH")
        resolved.append({"recordDate": record, "exDate": notice["exDate"],
                         "withinCutoff": notice["exDate"] <= cutoff,
                         "publishedBeforeExDate": notice["publishedDate"] <= notice["exDate"]})
    if set(indexed) - seen:
        raise SourceError("NOTICE_WITHOUT_MATCHING_EVENT")
    return {"observedEvents": len(events), "explicitExDateEvents": resolved,
            "unresolvedExDateRecordDates": sorted(unresolved),
            "historicalCompletenessCertified": False,
            "payloadIntegrityVerifiedByThisFunction": False,
            "totalReturnReady": False, "outcomeExecutionAuthorized": False}


def fixed_input_projection(rows: list[dict]) -> dict:
    """Project only pre-existing targets/dates; no return/NAV/terminal fields."""
    selected = []
    for row in rows:
        item = {key: row[key] for key in (
            "date", "endDate", "signalDate", "weights", "selectedTickers")}
        start, end, signal = (_day(item[k]) for k in ("date", "endDate", "signalDate"))
        weights = item["weights"]
        values = [_number(v) for v in weights.values()]
        if (not signal < start < end or len(weights) != 3 or len(item["selectedTickers"]) != 3
                or set(weights) != set(item["selectedTickers"])
                or any(v is None or v <= 0 for v in values)
                or sum(values) > 1):
            raise SourceError("FIXED_INPUT_CONTRACT_MISMATCH")
        if selected and selected[-1]["endDate"] != start:
            raise SourceError("NON_CONTIGUOUS_FIXED_BLOCKS")
        selected.append(item)
    if not selected:
        raise SourceError("FIXED_BLOCKS_REQUIRED")
    return {"blocks": len(selected),
            "distinctNames": len({t for row in selected for t in row["weights"]}),
            "from": selected[0]["date"], "through": selected[-1]["endDate"],
            "projectionSha256": canonical_digest(selected),
            "outcomeFieldsRead": [], "actionableTargetsExported": False,
            "outcomeExecutionAuthorized": False}
