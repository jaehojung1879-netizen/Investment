"""Outcome-free universe evidence checks. No default liquidity rule or price reader."""
from __future__ import annotations

from datetime import date, datetime
from math import isfinite
import re
from zoneinfo import ZoneInfo


def _instant(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("TIMEZONE_REQUIRED")
    return result


def security_at(rows: list[dict], issuer_id: str, cutoff: str) -> dict:
    """Resolve dated security identity without assuming today's ticker existed earlier.

    Identity intervals and listing/delisting facts must each have evidence visible
    by cutoff. One issuer can have several securities; ambiguity stays blocked.
    ``valid_to`` is exclusive and only applied when ``end_known_at`` is visible.
    """
    instant = _instant(cutoff)
    candidates = []
    for row in rows:
        if row.get("issuer_id") != issuer_id:
            continue
        required = ("security_id", "ticker", "valid_from", "known_at", "source_sha256")
        if any(not row.get(key) for key in required):
            continue
        if not re.fullmatch(r"[0-9a-f]{64}", row["source_sha256"]) or _instant(row["known_at"]) > instant:
            continue
        if date.fromisoformat(row["valid_from"]) > instant.astimezone(ZoneInfo("Asia/Seoul")).date():
            continue
        end = row.get("valid_to")
        if end and row.get("end_known_at") and _instant(row["end_known_at"]) <= instant:
            if date.fromisoformat(end) <= instant.astimezone(ZoneInfo("Asia/Seoul")).date():
                continue
        candidates.append(row)
    if len(candidates) != 1:
        return {"status": "BLOCKED", "reason": "IDENTITY_ABSENT_OR_AMBIGUOUS",
                "security_id": None, "ticker": None}
    row = candidates[0]
    return {"status": "IDENTITY_RESOLVED_ONLY", "reason": None,
            "security_id": row["security_id"], "ticker": row["ticker"],
            "return_eligible": False}


def liquidity_candidate(evidence: dict, cutoff: str, rule: dict | None = None) -> dict:
    """Inspect one explicitly supplied proposal; never select a cutoff from outcomes.

    Official trailing traded-value evidence, full-window coverage and a cutoff
    precede evaluation. A proposal cannot grant research or return eligibility.
    """
    base = {"research_admitted": False, "return_eligible": False}
    if rule is None:
        return {**base, "candidate": None, "reason": "LIQUIDITY_CONTRACT_NOT_APPROVED"}
    needed = ("median_traded_value_krw", "window_start", "window_end", "known_at",
              "expected_sessions", "observed_sessions", "source_sha256", "basis")
    if any(evidence.get(k) is None for k in needed):
        return {**base, "candidate": None, "reason": "MISSING_TRAILING_WINDOW_EVIDENCE"}
    if _instant(evidence["known_at"]) > _instant(cutoff):
        return {**base, "candidate": None, "reason": "FUTURE_INFORMATION"}
    if date.fromisoformat(evidence["window_end"]) > _instant(cutoff).astimezone(ZoneInfo("Asia/Seoul")).date():
        return {**base, "candidate": None, "reason": "FUTURE_WINDOW"}
    for key in ("expected_sessions", "observed_sessions"):
        if type(evidence[key]) is not int or evidence[key] < 0:
            return {**base, "candidate": None, "reason": "INVALID_SESSION_COUNT"}
    if (evidence["expected_sessions"] <= 0
            or evidence["observed_sessions"] != evidence["expected_sessions"]):
        return {**base, "candidate": None, "reason": "INCOMPLETE_TRAILING_WINDOW"}
    if evidence["basis"] != "KRX_ACC_TRDVAL":
        return {**base, "candidate": None, "reason": "UNVERIFIED_TRADED_VALUE_BASIS"}
    if date.fromisoformat(evidence["window_start"]) > date.fromisoformat(evidence["window_end"]):
        raise ValueError("INVALID_WINDOW")
    if not re.fullmatch(r"[0-9a-f]{64}", evidence["source_sha256"]):
        raise ValueError("INVALID_SOURCE_HASH")
    floor = rule.get("minimum_median_traded_value_krw")
    if (not isinstance(floor, (int, float)) or isinstance(floor, bool)
            or not isfinite(floor) or floor < 0):
        raise ValueError("EXPLICIT_NONNEGATIVE_FLOOR_REQUIRED")
    median = evidence["median_traded_value_krw"]
    if (not isinstance(median, (int, float)) or isinstance(median, bool)
            or not isfinite(median) or median < 0):
        return {**base, "candidate": None, "reason": "INVALID_TRADED_VALUE"}
    return {**base, "candidate": median >= floor,
            "reason": "PROPOSAL_ONLY", "rule": dict(rule)}


def membership_inventory(snapshots: dict[str, list[str]]) -> dict:
    """Count observed dated membership; disappearance is never a delisting claim."""
    by_month = {day: len(set(names)) for day, names in sorted(snapshots.items())}
    sets = [set(snapshots[day]) for day in sorted(snapshots)]
    union = set().union(*sets) if sets else set()
    return {"snapshot_counts": by_month, "distinct_observed_securities": len(union),
            "observed_absent_from_last_snapshot": len(union - sets[-1]) if sets else None,
            "confirmed_delisted_count": None,
            "limitation": "MONTHLY_OBSERVATIONS_ARE_NOT_EXACT_LISTING_OR_TERMINATION_DATES",
            "return_eligible": False}
