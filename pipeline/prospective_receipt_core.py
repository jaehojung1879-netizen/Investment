"""Study-agnostic core of a PROSPECTIVE prediction receipt: identity, timing, append-only storage and outcome separation.

Three studies already carry their own receipt module (`kr_alpha_tournament_receipts`, `kr_market_risk_model_receipts`,
`kr_integrated_alpha_portfolio_receipts`). Each is inside a sealed dependency closure and is never edited. This module keeps their storage format
exactly: the same canonical JSON (sorted keys, compact separators, UTF-8, no NaN), the same digest rule (SHA-256 of the canonical JSON of every
field except `receiptSha256`), the same JSON Lines append-only ledger and the same `PROSPECTIVE_PAPER` evidence class. A test proves the bytes
agree. What it adds is what each study re-implemented or left out:

* a no-backdating window: a receipt is created after its signal session closed and before the next session opens;
* a prospective-eligibility boundary: the first eligible signal session is strictly AFTER the KR date of the authorizing merge, so same-day
  observations are excluded even when the merge came before the close;
* outcomes live in a SEPARATE record that references a receipt by digest, can only be built once the maturity session itself has closed (by
  the writer's own clock on a live path), and never rewrites the receipt;
* a held name that stopped trading without a cited terminal consideration makes the portfolio outcome `None`, never a last-price mark.

Nothing here schedules, writes or evaluates a real receipt.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path

import pandas as pd

from . import replay_calendar as RC

EVIDENCE_CLASS = "PROSPECTIVE_PAPER"
OUTCOME_EVIDENCE_CLASS = "PROSPECTIVE_OUTCOME"
# A receipt key containing one of these (case-insensitive, underscores ignored) is an outcome and is refused anywhere in a receipt. Superset of
# `kr_integrated_alpha_portfolio_receipts.FORBIDDEN_RECEIPT_KEY_FRAGMENTS`.
FORBIDDEN_KEY_FRAGMENTS = ("forward", "realized", "realised", "outcome", "sharpe", "cagr", "label", "nextreturn", "pnl", "actualreturn",
                           "maturedreturn", "futurereturn")
# KRX regular session 09:00-15:30 KST (UTC+9, no daylight saving) = 00:00-06:30 UTC. Some sessions open late and close late (the first session of
# the year opens at 10:00; the college-entrance-exam day runs 10:00-16:30), and the after-hours closing-price window runs to 18:00 KST. A session is
# therefore treated as FINAL only from 18:00 KST = 09:00 UTC, the latest moment any variant of a KRX day can still change its close. Opening late
# never makes 09:00 KST unsafe as the earliest open, so the next session's 00:00 UTC stays the upper bound of the receipt window.
KR_OPEN_UTC = pd.Timedelta(hours=0)
KR_CLOSE_FINAL_UTC = pd.Timedelta(hours=9)
KST = pd.Timedelta(hours=9)
HEX64 = frozenset("0123456789abcdef")

# Per-name outcome states a later outcome join may carry. A terminated name without a cited consideration is never valued.
NAME_OUTCOME_STATES = ("PRICED", "TERMINAL_CONSIDERATION_CITED", "TERMINAL_ECONOMICS_UNRESOLVED")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def receipt_digest(receipt):
    body = {k: v for k, v in receipt.items() if k != "receiptSha256"}
    return hashlib.sha256(canonical(body)).hexdigest()


def is_sha256(value):
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX64


def is_git_sha(value):
    return isinstance(value, str) and len(value) == 40 and set(value) <= HEX64


def scan_for_outcome_keys(value, path=""):
    """Raise on any key, at any depth, that names an outcome. Values are not scanned: a ticker or a reason string is not a key."""
    if isinstance(value, dict):
        for key, inner in value.items():
            folded = str(key).lower().replace("_", "")
            if any(fragment in folded for fragment in FORBIDDEN_KEY_FRAGMENTS):
                raise ValueError("OUTCOME_FIELD_IN_RECEIPT: " + path + "/" + str(key))
            scan_for_outcome_keys(inner, path + "/" + str(key))
    elif isinstance(value, (list, tuple)):
        for inner in value:
            scan_for_outcome_keys(inner, path)


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


# --------------------------------------------------------------------------- #
# Calendar and timing
# --------------------------------------------------------------------------- #
def utc(value):
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        raise ValueError("TIMESTAMP_WITHOUT_TIMEZONE: " + str(value))
    return stamp.tz_convert("UTC")


def kr_sessions_from(day, days=20):
    day = pd.Timestamp(day).normalize()
    return RC.sessions(str(day.date()), str((day + pd.Timedelta(days=days)).date()), "KR")


def next_kr_session(day):
    """The first KR session strictly after `day`."""
    after = kr_sessions_from(pd.Timestamp(day) + pd.Timedelta(days=1))
    if len(after) == 0:
        raise ValueError("NO_KR_SESSION_WITHIN_20_DAYS")
    return after[0]


def is_kr_session(day):
    found = kr_sessions_from(day, 0)
    return len(found) == 1 and found[0] == pd.Timestamp(day).normalize()


def is_weekly_decision_session(day):
    """A KR session whose next KR session lies in a later ISO week. Decided from the exchange calendar, never from where data happen to stop."""
    if not is_kr_session(day):
        return False
    day, nxt = pd.Timestamp(day).normalize(), next_kr_session(day)
    return tuple(nxt.isocalendar())[:2] != tuple(day.isocalendar())[:2]


def first_prospective_session(merged_at_utc):
    """First KR session strictly after the KR (KST) calendar date of the authorizing merge. Same-day observations are excluded."""
    merge_kst_date = (utc(merged_at_utc) + KST).tz_localize(None).normalize()
    return next_kr_session(merge_kst_date)


def check_timing(*, signal_date, created_at_utc, now_utc, merged_at_utc):
    """Return the execution session for a receipt written at `created_at_utc` for `signal_date`, or raise.

    The receipt must be written after the signal session closed and before the execution session (the next KR session) opens, not in the future
    relative to the writer's clock, and only for a signal session on or after the first prospective session. `created_at_utc` is the writer's
    claim; the public proof is the commit or artifact time of the ledger row, which an outcome join checks again."""
    day = pd.Timestamp(signal_date).normalize()
    if not is_kr_session(day):
        raise ValueError("SIGNAL_DATE_IS_NOT_A_KR_SESSION")
    if day < first_prospective_session(merged_at_utc):
        raise ValueError("SIGNAL_BEFORE_PROSPECTIVE_ELIGIBILITY")
    created, now = utc(created_at_utc), utc(now_utc)
    if created > now:
        raise ValueError("RECEIPT_CREATED_IN_THE_FUTURE")
    execution = next_kr_session(day)
    if created < (day + KR_CLOSE_FINAL_UTC).tz_localize("UTC"):
        raise ValueError("RECEIPT_CREATED_BEFORE_SIGNAL_CLOSE")
    if created >= (execution + KR_OPEN_UTC).tz_localize("UTC"):
        raise ValueError("RECEIPT_CREATED_AFTER_EXECUTION_OPEN_BACKDATED")
    return execution


def system_utc_now():
    """The writer's own clock. A LIVE path reads time only from here and never accepts a caller-supplied timestamp as proof that a session closed."""
    return pd.Timestamp.now(tz="UTC")


def maturity_session(execution_date, horizon):
    """The KR session `horizon` sessions after the execution session (the execution session is session 0). Holidays and weekends are skipped by the
    pinned exchange calendar, never by where price data happen to stop."""
    if not isinstance(horizon, int) or horizon <= 0:
        raise ValueError("HORIZON_MUST_BE_A_POSITIVE_SESSION_COUNT")
    start = pd.Timestamp(execution_date).normalize()
    sessions = RC.sessions(str(start.date()), str((start + pd.Timedelta(days=2 * horizon + 30)).date()), "KR")
    if len(sessions) <= horizon or sessions[0] != start:
        raise ValueError("EXECUTION_DATE_IS_NOT_A_KR_SESSION_OR_CALENDAR_TOO_SHORT")
    return sessions[horizon]


def maturity_close_utc(execution_date, horizon):
    return (maturity_session(execution_date, horizon) + KR_CLOSE_FINAL_UTC).tz_localize("UTC")


def has_matured(execution_date, horizon, now_utc):
    """True only once the maturity session itself has closed (final at 09:00 UTC on that date), judged by a timezone-aware clock."""
    return utc(now_utc) >= maturity_close_utc(execution_date, horizon)


# --------------------------------------------------------------------------- #
# Append-only ledger
# --------------------------------------------------------------------------- #
def read_ledger(path, validate):
    path = Path(path)
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in rows:
        validate(row)
    return rows


def append(path, receipt, *, validate, key_fields, date_field="signalDate", spec_field="specSha256"):
    """Append one sealed row. Refuses a duplicate key, a date not strictly after the last row's, a spec different from the ledger's and any existing
    row whose digest no longer verifies. Existing bytes are never rewritten; the new row is written to the end of the file and fsynced."""
    validate(receipt)
    rows = read_ledger(path, validate)
    key = tuple(receipt[k] for k in key_fields)
    if any(tuple(r[k] for k in key_fields) == key for r in rows):
        raise ValueError("RECEIPT_ALREADY_EXISTS")
    if rows and pd.Timestamp(receipt[date_field]) <= pd.Timestamp(rows[-1][date_field]):
        raise ValueError("RECEIPT_OUT_OF_ORDER")
    if rows and spec_field and receipt[spec_field] != rows[0][spec_field]:
        raise ValueError("RECEIPT_SPEC_CHANGED_WITHIN_A_LEDGER")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as stream:
        stream.write(canonical(receipt) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    return receipt["receiptSha256"]


# --------------------------------------------------------------------------- #
# Outcomes: a separate record, never a field of the receipt
# --------------------------------------------------------------------------- #
def portfolio_outcome(weights, name_outcomes):
    """Weighted benchmark-relative outcome of the names a receipt held, or None with a status.

    `name_outcomes[ticker] = {"state": one of NAME_OUTCOME_STATES, "excessReturn": float | None}`. A held name that is missing, unresolved or
    carries no finite value makes the whole outcome None: it is never marked at a last price, dropped, renormalised away or assumed to receive
    anything. Unheld weight is the receipt's declared fallback and is reported separately by the caller."""
    unresolved = sorted(t for t, w in weights.items() if w > 0 and (
        t not in name_outcomes or name_outcomes[t].get("state") == "TERMINAL_ECONOMICS_UNRESOLVED"
        or name_outcomes[t].get("state") not in NAME_OUTCOME_STATES or not finite(name_outcomes[t].get("excessReturn"))))
    if unresolved:
        return {"status": "TERMINAL_ECONOMICS_UNRESOLVED" if any(name_outcomes.get(t, {}).get("state") == "TERMINAL_ECONOMICS_UNRESOLVED"
                                                                  for t in unresolved) else "NAME_OUTCOME_MISSING",
                "unresolvedTickers": unresolved, "heldExcessReturn": None}
    value = math.fsum(w * name_outcomes[t]["excessReturn"] for t, w in sorted(weights.items()) if w > 0)
    return {"status": "COMPLETE", "unresolvedTickers": [], "heldExcessReturn": value}


def build_outcome_record(receipt, *, validate, horizon, name_outcomes, now_utc, weights_field=("portfolio", "weights")):
    """A separate outcome record keyed by the receipt's digest. Refuses a receipt whose digest no longer verifies, refuses before the maturity
    session has closed by `now_utc`, and refuses a PRICED name whose exit price is not from the maturity session itself.

    The receipt object is not modified: the caller stores this record in a different ledger. `now_utc` must come from the writer's own clock on a
    live path (`system_utc_now`); only synthetic fixtures may pass a test clock."""
    validate(receipt)
    now = utc(now_utc)
    exit_session = maturity_session(receipt["executionDate"], horizon)
    if not has_matured(receipt["executionDate"], horizon, now):
        raise ValueError("HORIZON_NOT_MATURED: maturity session %s closes %s" % (exit_session.date(), maturity_close_utc(receipt["executionDate"], horizon)))
    for ticker, outcome in name_outcomes.items():
        if outcome.get("state") == "PRICED" and outcome.get("exitSession") != str(exit_session.date()):
            raise ValueError("NAME_OUTCOME_NOT_PRICED_AT_THE_MATURITY_SESSION: " + ticker)
    block = receipt
    for part in weights_field:
        block = (block or {}).get(part)
    weights = dict(block or {})
    record = {"evidenceClass": OUTCOME_EVIDENCE_CLASS, "receiptSha256": receipt["receiptSha256"], "studyId": receipt["studyId"],
              "signalDate": receipt["signalDate"], "executionDate": receipt["executionDate"], "horizonSessions": int(horizon),
              "maturitySession": str(exit_session.date()), "createdAtUtc": now.isoformat(),
              "nameOutcomes": {t: dict(v) for t, v in sorted(name_outcomes.items())},
              "portfolio": portfolio_outcome(weights, name_outcomes)}
    record["recordSha256"] = hashlib.sha256(canonical(record)).hexdigest()
    return record
