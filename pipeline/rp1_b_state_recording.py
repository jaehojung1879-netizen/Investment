"""Inactive Track B recorder: synthetic end-to-end mechanics, no LIVE adapter.

Reuses #264's observer, sealed FAST and prospective timing. No download,
historical replay, outcome join, scheduler or activation flag. Synthetic writes
are permitted only outside the checkout. A separately reviewed registration,
source adapter and owner authorization are required before a LIVE writer exists.
"""
from __future__ import annotations

import ast
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat

import pandas as pd

from . import prospective_receipt_core as P
from . import replay_calendar as RC
from . import rp1_b_state_receipt as B

ROOT = Path(__file__).resolve().parents[1]
STUDY = "rp1-b-h1-state-recording-v1"
CONTRACT_PATH = "docs/research-program/specs/" + STUDY + ".json"
CONTRACT_SHA256 = "fe6b053e6ce23a411de49d633429e827c57d580f21c957b065ed2d0e0c9b23a1"
SYNTHETIC = "SYNTHETIC_FIXTURE"
REGISTERED_AUTHORIZATION = None
SOURCE_FIELDS = {"schemaVersion", "evidenceClass", "sourceId", "instrumentId", "priceBasis", "signalDate",
                 "availableAtUtc", "observedAtUtc", "observations", "sourceSha256"}
RECEIPT_FIELDS = {"schemaVersion", "studyId", "evidenceClass", "purpose", "signalDate", "nextSessionDate",
                  "createdAtUtc", "syntheticMergeAtUtc", "identity", "source", "availability", "preview", "receiptSha256"}


def digest(value):
    return hashlib.sha256(P.canonical(value)).hexdigest()


def load_contract():
    raw = (ROOT / CONTRACT_PATH).read_bytes()
    if hashlib.sha256(raw).hexdigest() != CONTRACT_SHA256:
        raise ValueError("CONTRACT_HASH_MISMATCH")
    contract = json.loads(raw)
    if (contract["studyId"] != STUDY or contract["definition"] != B.DEFINITION
            or contract["calendarVersion"] != RC.CALENDAR_VERSION
            or contract["status"] != "DISABLED_PENDING_REGISTRATION"
            or contract["registeredAuthorization"] is not None or contract["sourceAdmission"] is not None):
        raise ValueError("CONTRACT_IDENTITY_MISMATCH")
    return contract


def current_identity():
    """Hash disk bytes of the transitive repo import closure, CLI and runtime pins.

    This is identity, not owner approval. A LIVE registration must additionally
    bind a reviewed main commit and runtime/availability evidence.
    """
    load_contract()
    paths = _dependency_files()
    paths.update(("scripts/record_rp1_b_state.py", "requirements.txt", "requirements-dev.txt"))
    # Paths are values, not measurement keys (some dependency filenames contain
    # words such as "outcomes"). Keep the common outcome-key scanner intact.
    pins = [{"path": p, "sha256": hashlib.sha256((ROOT / p).read_bytes()).hexdigest()} for p in sorted(paths)]
    return {"contractSha256": CONTRACT_SHA256, "codeSha256": digest(pins), "codeFiles": pins,
            "calendarVersion": RC.CALENDAR_VERSION}


def _dependency_files():
    """Static local imports only; do not import an unrelated research harness.

    Includes imports in function bodies, so a lazy local dependency cannot evade
    the pin. Third-party runtime versions remain a separate LIVE admission gate.
    """
    seen, pending = {"pipeline/__init__.py"}, ["pipeline/rp1_b_state_recording.py"]
    while pending:
        rel = pending.pop()
        if rel in seen:
            continue
        seen.add(rel)
        names = set()
        for node in ast.walk(ast.parse((ROOT / rel).read_text())):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level == 1:
                    names.update([module.split(".")[0]] if module else [a.name for a in node.names])
                elif node.level == 0 and module == "pipeline":
                    names.update(a.name for a in node.names)
                elif node.level == 0 and module.startswith("pipeline."):
                    names.add(module.split(".")[1])
            elif isinstance(node, ast.Import):
                names.update(a.name.split(".")[1] for a in node.names if a.name.startswith("pipeline."))
        pending.extend("pipeline/" + name + ".py" for name in names if (ROOT / "pipeline" / (name + ".py")).is_file())
    return seen


def activation_status():
    c = load_contract()
    return {"studyId": STUDY, "status": c["status"], "blockers": c["blockers"],
            "liveEnabled": False, "registeredAuthorization": REGISTERED_AUTHORIZATION,
            "syntheticMechanicsAvailable": True}


def record_live():
    """Refuse before reading any source or opening any ledger; no flag activates it."""
    raise ValueError("LIVE_RECORDING_DISABLED_PENDING_REGISTRATION")


def _day(value):
    if not isinstance(value, str):
        raise ValueError("SESSION_DATE_MALFORMED")
    day = pd.Timestamp(value)
    if pd.isna(day) or day.tzinfo is not None or day.isoformat()[:10] != value or len(value) != 10:
        raise ValueError("SESSION_DATE_MALFORMED")
    return day


def source_digest(source):
    return digest({k: v for k, v in source.items() if k != "sourceSha256"})


def _read_source(source, now):
    if not isinstance(source, dict) or set(source) != SOURCE_FIELDS:
        raise ValueError("SOURCE_FIELDS_MISMATCH")
    P.scan_for_outcome_keys(source)
    if (source["schemaVersion"] != 1 or source["evidenceClass"] != SYNTHETIC
            or source["sourceId"] != "SYNTHETIC_KR_INDEX" or source["instrumentId"] != "SYNTHETIC_KR_INDEX"
            or source["priceBasis"] != "SYNTHETIC_INDEX_CLOSE"):
        raise ValueError("SOURCE_NOT_AN_ADMITTED_SYNTHETIC_FIXTURE")
    if not P.is_sha256(source["sourceSha256"]) or source["sourceSha256"] != source_digest(source):
        raise ValueError("SOURCE_HASH_MISMATCH")
    day = _day(source["signalDate"])
    if not P.is_weekly_decision_session(day):
        raise ValueError("SIGNAL_DATE_IS_NOT_A_WEEKLY_DECISION_SESSION")
    available, observed = P.utc(source["availableAtUtc"]), P.utc(source["observedAtUtc"])
    if (pd.isna(available) or pd.isna(observed) or available > observed or observed > now
            or observed < (day + P.KR_CLOSE_FINAL_UTC).tz_localize("UTC")):
        raise ValueError("SOURCE_AVAILABILITY_OR_OBSERVATION_TIME_INVALID")
    rows = source["observations"]
    if not isinstance(rows, list) or not rows:
        raise ValueError("SOURCE_INPUT_EMPTY")
    days, values = [], []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"sessionDate", "close"}:
            raise ValueError("SOURCE_OBSERVATION_FIELDS_MISMATCH")
        d = _day(row["sessionDate"])
        if d > day:
            raise ValueError("DATA_AFTER_SIGNAL_DATE")
        if row["close"] is not None and not P.finite(row["close"]):
            raise ValueError("SOURCE_CLOSE_MALFORMED")
        days.append(d); values.append(row["close"])
    idx = pd.DatetimeIndex(days)
    if idx.has_duplicates or not idx.is_monotonic_increasing:
        raise ValueError("SOURCE_DUPLICATE_OR_UNORDERED_SESSIONS")
    expected = RC.sessions(str(idx[0].date()), str(day.date()), "KR")
    if len(idx.difference(expected)):
        raise ValueError("SOURCE_OFF_CALENDAR_SESSION")
    supplied = pd.Series(values, index=idx, dtype=float)
    # Calendar positions are preserved, including absent bars. No forward fill,
    # stale-base substitution or row-count approximation of exchange sessions.
    aligned = supplied.reindex(expected)
    invalid = supplied.index[supplied.isna() | (supplied <= 0)]
    availability = {"missingSessions": [str(d.date()) for d in expected.difference(idx)],
                    "invalidCloseSessions": [str(d.date()) for d in invalid],
                    "firstSessionDate": str(expected[0].date()),
                    "suppliedSessions": len(idx), "expectedSessions": len(expected)}
    return aligned, availability


def _build(source, merged_at, now, identity):
    if not isinstance(source, dict) or set(source) != SOURCE_FIELDS:
        raise ValueError("SOURCE_FIELDS_MISMATCH")
    if pd.isna(now) or pd.isna(P.utc(merged_at)):
        raise ValueError("TIMESTAMP_MISSING")
    next_session = P.check_timing(signal_date=source["signalDate"], created_at_utc=now,
                                 now_utc=now, merged_at_utc=merged_at)
    series, availability = _read_source(source, now)
    preview = B.build_preview(series, source["signalDate"])
    availability["fast"] = "AVAILABLE" if preview["fast"] is not None else "UNAVAILABLE"
    availability["base24m"] = "AVAILABLE" if preview["baseSessionDate"] is not None else "UNAVAILABLE"
    r = {"schemaVersion": 1, "studyId": STUDY, "evidenceClass": SYNTHETIC,
         "purpose": "MARKET_OBSERVED_STATE_ONLY", "signalDate": source["signalDate"],
         "nextSessionDate": str(next_session.date()), "createdAtUtc": now.isoformat(),
         "syntheticMergeAtUtc": P.utc(merged_at).isoformat(), "identity": identity,
         "source": {k: source[k] for k in SOURCE_FIELDS - {"observations", "schemaVersion", "evidenceClass", "signalDate"}},
         "availability": availability, "preview": preview}
    P.scan_for_outcome_keys(r)
    r["receiptSha256"] = P.receipt_digest(r)
    return r


def build_synthetic_receipt(source, *, merged_at_utc, now_utc):
    """Explicit fixture clocks; cannot produce PROSPECTIVE_PAPER evidence."""
    r = _build(source, merged_at_utc, P.utc(now_utc), current_identity())
    validate_synthetic_receipt(r, source=source)
    return r


def validate_synthetic_receipt(r, *, source=None):
    if not isinstance(r, dict) or set(r) != RECEIPT_FIELDS:
        raise ValueError("RECEIPT_FIELDS_MISMATCH")
    P.scan_for_outcome_keys(r)
    if (r["schemaVersion"] != 1 or r["studyId"] != STUDY or r["evidenceClass"] != SYNTHETIC
            or r["purpose"] != "MARKET_OBSERVED_STATE_ONLY"):
        raise ValueError("RECEIPT_IDENTITY_MISMATCH")
    if r["receiptSha256"] != P.receipt_digest(r):
        raise ValueError("RECEIPT_DIGEST_MISMATCH")
    if r["identity"] != current_identity():
        raise ValueError("CONTRACT_OR_CODE_IDENTITY_MISMATCH")
    if not isinstance(r["preview"], dict) or set(r["preview"]) != set(B.REQUIRED) | {"receiptSha256"}:
        raise ValueError("RECEIPT_PREVIEW_FIELDS_MISMATCH")
    B.validate_preview(r["preview"])
    if r["preview"]["signalDate"] != r["signalDate"]:
        raise ValueError("RECEIPT_SIGNAL_DATE_MISMATCH")
    _validate_metadata(r)
    nxt = P.check_timing(signal_date=r["signalDate"], created_at_utc=r["createdAtUtc"],
                         now_utc=r["createdAtUtc"], merged_at_utc=r["syntheticMergeAtUtc"])
    if r["nextSessionDate"] != str(nxt.date()):
        raise ValueError("RECEIPT_NEXT_SESSION_MISMATCH")
    if source is not None:
        expected = _build(source, r["syntheticMergeAtUtc"], P.utc(r["createdAtUtc"]), r["identity"])
        if r != expected:
            raise ValueError("RECEIPT_DISAGREES_WITH_SOURCE")
    P.canonical(r)
    return True


def _validate_metadata(r):
    """Validate stored facts even when the original input is not supplied.

    Source re-computation is mandatory before append; old rows additionally need
    the independent checkpoint. A self-consistent hash is not source provenance.
    """
    s, a, p = r["source"], r["availability"], r["preview"]
    source_keys = SOURCE_FIELDS - {"observations", "schemaVersion", "evidenceClass", "signalDate"}
    if (not isinstance(s, dict) or set(s) != source_keys or not P.is_sha256(s["sourceSha256"])
            or s["sourceId"] != "SYNTHETIC_KR_INDEX" or s["instrumentId"] != "SYNTHETIC_KR_INDEX"
            or s["priceBasis"] != "SYNTHETIC_INDEX_CLOSE"):
        raise ValueError("RECEIPT_SOURCE_METADATA_INVALID")
    available, observed, created = P.utc(s["availableAtUtc"]), P.utc(s["observedAtUtc"]), P.utc(r["createdAtUtc"])
    if not available <= observed <= created or observed < (_day(r["signalDate"]) + P.KR_CLOSE_FINAL_UTC).tz_localize("UTC"):
        raise ValueError("RECEIPT_SOURCE_TIME_INVALID")
    if not isinstance(a, dict) or set(a) != {"missingSessions", "invalidCloseSessions", "firstSessionDate",
                                            "suppliedSessions", "expectedSessions", "fast", "base24m"}:
        raise ValueError("RECEIPT_AVAILABILITY_INVALID")
    days = RC.sessions(str(_day(a["firstSessionDate"]).date()), r["signalDate"], "KR")
    dates = {str(d.date()) for d in days}
    for key in ("missingSessions", "invalidCloseSessions"):
        values = a[key]
        if (not isinstance(values, list) or any(not isinstance(v, str) for v in values)
                or values != sorted(set(values)) or not set(values) <= dates):
            raise ValueError("RECEIPT_SESSION_DIAGNOSTICS_INVALID")
    if (set(a["missingSessions"]) & set(a["invalidCloseSessions"])
            or not all(isinstance(a[k], int) and not isinstance(a[k], bool) for k in ("suppliedSessions", "expectedSessions"))
            or a["expectedSessions"] != len(days) or a["suppliedSessions"] != len(days) - len(a["missingSessions"])
            or a["suppliedSessions"] <= 0):
        raise ValueError("RECEIPT_SESSION_COUNTS_INVALID")
    if (a["fast"] != ("AVAILABLE" if p["fast"] is not None else "UNAVAILABLE")
            or a["base24m"] != ("AVAILABLE" if p["baseSessionDate"] is not None else "UNAVAILABLE")):
        raise ValueError("RECEIPT_AVAILABILITY_DISAGREES_WITH_STATE")


def checkpoint(raw=b"", rows=0):
    """Caller must preserve this outside the mutable ledger (LIVE policy pending).

    Hash chains alone cannot detect a rewritten whole history. The independently
    retained byte hash/size/count is mandatory for validation and append.
    """
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "rows": rows}


def _verify(raw, expected_checkpoint):
    rows = []
    if raw and not raw.endswith(b"\n"):
        raise ValueError("LEDGER_TRUNCATED")
    for line in raw.splitlines():
        row = json.loads(line)
        if not isinstance(row, dict) or set(row) != {"receipt", "previousSha256", "recordSha256"}:
            raise ValueError("LEDGER_RECORD_FIELDS_MISMATCH")
        validate_synthetic_receipt(row["receipt"])
        if line != P.canonical(row) or row["recordSha256"] != digest({k:v for k,v in row.items() if k != "recordSha256"}):
            raise ValueError("LEDGER_RECORD_DIGEST_MISMATCH")
        if row["previousSha256"] != (rows[-1]["recordSha256"] if rows else None):
            raise ValueError("LEDGER_CHAIN_MISMATCH")
        if rows:
            prior, r = rows[-1]["receipt"], row["receipt"]
            if r["signalDate"] <= prior["signalDate"]:
                raise ValueError("LEDGER_DUPLICATE_OR_OUT_OF_ORDER")
            for key in ("identity", "syntheticMergeAtUtc"):
                if r[key] != prior[key]:
                    raise ValueError("LEDGER_REGISTRATION_CHANGED")
            for key in ("sourceId", "instrumentId", "priceBasis"):
                if r["source"][key] != prior["source"][key]:
                    raise ValueError("LEDGER_SOURCE_CHANGED")
        rows.append(row)
    if expected_checkpoint != checkpoint(raw, len(rows)):
        raise ValueError("LEDGER_CHECKPOINT_MISMATCH")
    return rows


def verify_synthetic_ledger(path, *, expected_checkpoint):
    path = Path(path)
    rows = _verify(path.read_bytes() if path.exists() else b"", expected_checkpoint)
    return {"status": "SYNTHETIC_LEDGER_VALID", "rows": len(rows)}


def append_synthetic(path, receipt, *, source, expected_checkpoint):
    """One lock covers validation+append; stale/concurrent checkpoint loses safely.

    This is a synthetic-only writer. It never opens a checkout ledger and returns
    a new checkpoint only after a complete fsynced write. It is not a remote
    immutable store or protection against an actor rewriting both ledger and pin.
    """
    validate_synthetic_receipt(receipt, source=source)
    path = Path(path)
    if path.is_symlink() or path.resolve().is_relative_to(ROOT):
        raise ValueError("SYNTHETIC_LEDGER_MUST_BE_OUTSIDE_CHECKOUT")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "r+b") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("LEDGER_MUST_BE_A_REGULAR_SINGLE_LINK_FILE")
        raw = stream.read()
        rows = _verify(raw, expected_checkpoint)
        if rows and receipt["signalDate"] <= rows[-1]["receipt"]["signalDate"]:
            raise ValueError("RECEIPT_ALREADY_EXISTS_OR_OUT_OF_ORDER")
        if rows:
            old = rows[-1]["receipt"]
            if receipt["identity"] != old["identity"] or receipt["syntheticMergeAtUtc"] != old["syntheticMergeAtUtc"]:
                raise ValueError("LEDGER_REGISTRATION_CHANGED")
        row = {"receipt": receipt, "previousSha256": rows[-1]["recordSha256"] if rows else None}
        row["recordSha256"] = digest(row)
        data = P.canonical(row) + b"\n"
        # Validate the prospective full ledger before touching existing bytes.
        new_pin = checkpoint(raw + data, len(rows) + 1)
        _verify(raw + data, new_pin)
        if stream.write(data) != len(data):
            raise OSError("LEDGER_SHORT_WRITE")
        stream.flush()
        os.fsync(stream.fileno())
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    return new_pin
