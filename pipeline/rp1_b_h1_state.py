"""RP1 Track B — B-H1 PROSPECTIVE market-state receipts (KR, MARKET_OBSERVED). State only: no outcome, no weight, no order.

Every KR weekly decision session gets one receipt that fixes, before the next session opens, what B-H1 needs to know about the market on that
session and nothing else: the sealed FAST count on the KOSPI 200 price index and the sign of its trailing 24-calendar-month return, combined as
`docs/research-program/03-studies-abc-ko.md` B-H1 defines it (FAST == 2 OR trailing 24m return < 0). The legs are computed by the #264 preview
(`rp1_b_state_receipt.observe`, which calls the sealed `kr_market_risk_model.fast_states`) on a series that this module first aligns to the pinned
KRX calendar with `kr_bar_integrity`, so a session the vendor did not serve, or served without a valid close or volume, is a hole in the window and
never a shorter window. Nothing here adds a window, threshold, lag or horizon. The frozen design is ``docs/research-program/specs/rp1-b-h1-state-v1.json``.

What is reused, not re-implemented: `prospective_receipt_core` (canonical JSON, digest, timing window, append-only JSON Lines, maturity), the
KR selection challenger's main-only registration, code identity and write-time clock gate (`kr_selection_challenger`), and the read-side bar
integrity of `kr_bar_integrity`. Each is pinned by bytes in the spec.

An attempt ends in exactly one of: RECORDED (one receipt appended), SKIPPED (not this run's turn), DEFERRED (the provider has not served what the
receipt needs; nothing written, a later run in the window retries) or REFUSED (an integrity failure; nothing written). A missing leg is never
benign: before the last 24 hours of the receipt window a provider gap is DEFERRED, inside them it is recorded as an undetermined leg with its
reason, and `adverse` is None unless the determined leg alone is adverse. Receipts are hash-chained (`previousReceiptSha256`), so a deleted,
reordered or inserted row breaks every later row.

Outcome evaluation (the H63 momentum spread by state) is a SEPARATE contract that is not registered: `outcome_gate` refuses, and nothing in this
module reads a forward price, a stock cross-section or a return after the signal session.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from . import kr_bar_integrity as BI
from . import kr_market_risk_model as K
from . import kr_selection_challenger as V1
from . import prospective_receipt_core as CORE
from . import replay_calendar as RC
from . import rp1_b_state_receipt as PREVIEW

ROOT = Path(__file__).resolve().parents[1]
STUDY = "rp1-b-h1-state-v1"
SPEC_PATH = "docs/research-program/specs/rp1-b-h1-state-v1.json"
SCHEMA_VERSION = 1
LIVE, SYNTHETIC = "LIVE", "SYNTHETIC_FIXTURE"
EVIDENCE_CLASS_BY_PATHWAY = {LIVE: CORE.EVIDENCE_CLASS, SYNTHETIC: "SYNTHETIC_FIXTURE"}
HYPOTHESIS = "B-H1"
STATE_CLASS = "MARKET_OBSERVED"
DEFINITION = PREVIEW.DEFINITION
LOOKBACK_MONTHS = PREVIEW.LOOKBACK_MONTHS
FAST_WINDOW_SESSIONS = K.FAST_TREND_WINDOW + 1          # the sealed rule reads the 201 sessions ending at the signal session
KEY_FIELDS = ("studyId", "signalDate")
SOURCE = {"sourceId": "FDR_KS200", "instrument": "KOSPI 200 price index", "symbol": "KS200",
          "route": "FinanceDataReader.DataReader('KS200') -> KrxIndexReaderCache (yearly CSV files of FinanceData/fdr_krx_data_cache)",
          "vendorPackage": "finance-datareader==0.9.110"}
FETCH_MARGIN_DAYS = 40              # rows before the 24-month base, so a vendor row on a closed day near it is visible
FETCH_TIMEOUT_SECONDS = 30          # per vendor socket read; a hung read is a provider failure, never a hung paper ledger
FINAL_ATTEMPT_HOURS = 24            # a provider gap inside a window is recorded as undetermined only this close to the next open
TRADED = ("VALID", "RANGE_UNRESOLVED")

RECORDED, SKIPPED, DEFERRED, REFUSED = "RECORDED", "SKIPPED", "DEFERRED", "REFUSED"
LEG_REASONS = ("FAST_DATA_INSUFFICIENT", "FAST_WINDOW_OFF_CALENDAR_ROW", "TRAILING_24M_BASE_UNAVAILABLE",
               "TRAILING_24M_BASE_OFF_CALENDAR_ROW")
FAST_REASONS, BASE_REASONS = LEG_REASONS[:2], LEG_REASONS[2:]


class AttemptStop(ValueError):
    """An attempt that writes no receipt. ``kind`` is SKIPPED, DEFERRED or REFUSED; the message starts with the reason code."""

    def __init__(self, kind: str, reason: str, detail: dict | None = None):
        super().__init__(reason)
        self.kind, self.reason, self.detail = kind, reason, dict(detail or {})


# --------------------------------------------------------------------------- #
# Frozen design and its dependencies
# --------------------------------------------------------------------------- #
# Research-owned modules this study calls are pinned by BYTES; the sealed market-risk model's FAST function and the pinned KRX calendar are
# pinned by BEHAVIOUR (their outputs on fixed synthetic probes). A changed rule is a new study version, never a re-pin of this one.
SCIENTIFIC_FILES = ("pipeline/prospective_receipt_core.py", "pipeline/rp1_b_state_receipt.py", "pipeline/kr_bar_integrity.py",
                    "pipeline/kr_selection_challenger.py")
CONFORMANCE_CALENDAR_SPAN = ("2026-10-01", "2031-12-31")


def _probe_close(n=320, drift=0.0004, amplitude=0.012, start="2024-01-02"):
    days = pd.DatetimeIndex(RC.sessions(start, "2026-12-31", "KR"))[:n]
    steps = np.full(n, drift) + amplitude * np.sin(np.arange(n) / 4.0)
    return pd.Series(100.0 * np.exp(np.cumsum(steps)), index=days)


def conformance_values() -> dict:
    """Outputs of the sealed FAST function, the preview's leg arithmetic and the KRX calendar on fixed inputs. No market data is read."""
    fast = {}
    for name, (drift, amplitude) in {"calm": (0.0006, 0.004), "trend": (-0.0015, 0.004), "storm": (-0.0010, 0.03)}.items():
        frame = K.fast_states(_probe_close(drift=drift, amplitude=amplitude)).iloc[-3:]
        fast[name] = {k: [None if not math.isfinite(v) else float(f"{v:.10g}") for v in frame[k].tolist()] for k in frame.columns}
    series = _probe_close(n=560, drift=-0.0003, amplitude=0.01, start="2024-06-03")
    signal = next(d for d in reversed(series.index) if CORE.is_weekly_decision_session(d))
    legs = PREVIEW.observe(series.loc[:signal], signal)
    preview = {"fast": legs["fast"], "ret": None if legs["ret"] is None else float(f"{legs['ret']:.10g}"),
               "base": None if legs["base"] is None else str(legs["base"].date()), "adverse": legs["adverse"], "reasons": legs["reasons"]}
    days = RC.sessions(*CONFORMANCE_CALENDAR_SPAN, "KR")
    calendar = {"sessions": len(days), "sha256": hashlib.sha256(",".join(str(d.date()) for d in days).encode()).hexdigest()}
    return {"fastStates": fast, "previewLegs": preview, "krCalendar": calendar, "fastVolThreshold": float(K.FAST_VOL_THRESHOLD),
            "fastTrendWindow": int(K.FAST_TREND_WINDOW), "fastVolWindow": int(K.FAST_VOL_WINDOW), "lookbackMonths": int(LOOKBACK_MONTHS)}


def conformance_digest(values: dict | None = None) -> str:
    return hashlib.sha256(CORE.canonical(values if values is not None else conformance_values())).hexdigest()


def load_spec(root=ROOT, *, verify_code=True) -> dict:
    spec = json.loads((Path(root) / SPEC_PATH).read_text(encoding="utf-8"))
    if spec.get("studyId") != STUDY or spec.get("stateDefinition", {}).get("definition") != DEFINITION \
            or spec.get("reference", {}).get("sourceId") != SOURCE["sourceId"]:
        raise ValueError("SPEC_STUDY_MISMATCH")
    if verify_code:
        for rel, pinned in sorted(spec["codeFileHashes"].items()):
            if V1.file_sha256(Path(root) / rel) != pinned:
                raise ValueError("CODE_CHANGED_SINCE_REGISTRATION: " + rel)
        V1.verify_scientific_dependencies(spec, root, files=SCIENTIFIC_FILES, values=conformance_values())
    return spec


def spec_sha256(root=ROOT) -> str:
    return V1.file_sha256(Path(root) / SPEC_PATH)


def registration_merged_at(root=ROOT) -> str:
    """Commit time of the first-parent commit on origin/main that added this study's spec; refuses an unmerged branch."""
    return V1.registration_from_git(root, SPEC_PATH)["mergedAtUtc"]


def live_code_identity(spec: dict, root=ROOT) -> dict:
    return V1.live_code_identity(spec, root)


# --------------------------------------------------------------------------- #
# Which session a run speaks for, decided by the writer's clock alone
# --------------------------------------------------------------------------- #
def _final_at(session) -> pd.Timestamp:
    return (pd.Timestamp(session).normalize() + CORE.KR_CLOSE_FINAL_UTC).tz_localize("UTC")


def _open_at(session) -> pd.Timestamp:
    return (pd.Timestamp(session).normalize() + CORE.KR_OPEN_UTC).tz_localize("UTC")


def last_final_session(now_utc) -> pd.Timestamp:
    """The latest KR session whose close was final (18:00 KST) at ``now_utc``."""
    now = CORE.utc(now_utc)
    today = (now + CORE.KST).tz_localize(None).normalize()
    days = [d for d in RC.sessions(str((today - pd.Timedelta(days=20)).date()), str(today.date()), "KR") if _final_at(d) <= now]
    if not days:
        raise AttemptStop(REFUSED, "NO_FINAL_KR_SESSION_WITHIN_20_DAYS")
    return pd.Timestamp(days[-1])


def window_at(now_utc) -> dict:
    """``{signalDate, executionDate, closesAtUtc}`` of the receipt window ``now_utc`` lies in, or SKIPPED."""
    now = CORE.utc(now_utc)
    session = last_final_session(now)
    if not CORE.is_weekly_decision_session(session):
        raise AttemptStop(SKIPPED, "NOT_A_WEEKLY_DECISION_SESSION: " + str(session.date()))
    execution = CORE.next_kr_session(session)
    if now >= _open_at(execution):
        raise AttemptStop(SKIPPED, "RECEIPT_CREATED_AFTER_EXECUTION_OPEN_BACKDATED: window of " + str(session.date()) + " closed")
    return {"signalDate": str(session.date()), "executionDate": str(execution.date()), "closesAtUtc": _open_at(execution)}


def is_final_attempt(signal_date, now_utc) -> bool:
    """True inside the last FINAL_ATTEMPT_HOURS before the execution session opens: the last scheduled run of a window."""
    closes = _open_at(CORE.next_kr_session(signal_date))
    return closes - CORE.utc(now_utc) <= pd.Timedelta(hours=FINAL_ATTEMPT_HOURS)


def fetch_start(signal_date) -> str:
    target = pd.Timestamp(signal_date) - pd.DateOffset(months=LOOKBACK_MONTHS)
    return str((target - pd.Timedelta(days=FETCH_MARGIN_DAYS)).date())


def base_target(signal_date) -> pd.Timestamp:
    return pd.Timestamp(signal_date).normalize() - pd.DateOffset(months=LOOKBACK_MONTHS)


def expected_base_session(signal_date):
    """The last KR session on or before the 24-month target date, from the calendar (the preview's rule)."""
    target = base_target(signal_date)
    days = RC.sessions(str((target - pd.Timedelta(days=15)).date()), str(target.date()), "KR")
    return pd.Timestamp(days[-1]) if len(days) else None


# --------------------------------------------------------------------------- #
# Observation: calendar-aligned legs, signal-time facts only
# --------------------------------------------------------------------------- #
def _number(value):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _served_rows(raw: pd.DataFrame) -> list:
    return [[str(d.date()), _number(r.get("Close")), _number(r.get("Volume"))] for d, r in raw.iterrows()]


def combine(fast, ret):
    """B-H1's OR with missingness: an adverse determined leg decides; otherwise any undetermined leg makes the state None."""
    legs = [None if fast is None else fast == 2, None if ret is None else ret < 0]
    return True if any(v is True for v in legs) else (None if any(v is None for v in legs) else False)


def normalize_frame(frame) -> pd.DataFrame:
    if frame is None or not len(frame) or "Close" not in frame:
        raise AttemptStop(DEFERRED, "PROVIDER_EMPTY_RESPONSE")
    raw = frame.copy()
    index = pd.DatetimeIndex(pd.to_datetime(raw.index))
    raw.index = (index.tz_localize(None) if index.tz is not None else index).normalize()
    if raw.index.has_duplicates:
        raise AttemptStop(REFUSED, "VENDOR_DUPLICATE_DATES", {"dates": sorted({str(d.date()) for d in raw.index[raw.index.duplicated()]})[:10]})
    return raw.sort_index()


def observe(frame, signal_date, *, start=None) -> dict:
    """The B-H1 legs at ``signal_date`` from one vendor frame, or AttemptStop.

    A vendor row dated after the signal session is REFUSED, never dropped: nothing can legitimately trade between the signal close and the next
    open, so such a row means the clock or the source is wrong. The signal session itself must carry a traded close (DEFERRED otherwise: the
    provider has not served it yet). Every other hole only removes the leg that needs it."""
    day = pd.Timestamp(signal_date).normalize()
    if not CORE.is_weekly_decision_session(day):
        raise AttemptStop(REFUSED, "SIGNAL_DATE_IS_NOT_A_WEEKLY_DECISION_SESSION")
    raw = normalize_frame(frame)
    after = raw.index[raw.index > day]
    if len(after):
        raise AttemptStop(REFUSED, "VENDOR_ROW_AFTER_SIGNAL_SESSION", {"dates": [str(d.date()) for d in after[:10]]})
    first = pd.Timestamp(start or fetch_start(day))
    aligned = BI.calendar_frame(raw, start=first, end=day)
    span = raw[(raw.index >= first) & (raw.index <= day)]
    off = sorted(d for d in span.index if d not in aligned.index)
    if BI.traded_close(aligned, day) is None:
        state = str(aligned.loc[day, "state"]) if day in aligned.index else "SESSION_MISSING"
        raise AttemptStop(DEFERRED, "SIGNAL_SESSION_CLOSE_UNAVAILABLE", {"state": state})
    close = aligned["Close"].where(aligned["state"].isin(TRADED))
    legs = PREVIEW.observe(close, day)              # the #264 preview's arithmetic on the calendar-aligned series
    components = K.fast_states(close).iloc[-1]
    window = aligned.index[-FAST_WINDOW_SESSIONS:]
    gaps = [str(d.date()) for d in window if aligned.loc[d, "state"] not in TRADED] if len(window) == FAST_WINDOW_SESSIONS else ["SHORT_HISTORY"]
    fast_off = [str(d.date()) for d in off if len(window) and d >= window[0]]
    target, expected = base_target(day), expected_base_session(day)
    base_off = [str(d.date()) for d in off if expected is not None and expected < d <= target]
    fast, ret, base = legs["fast"], legs["ret"], legs["base"]
    reasons = [r for r in legs["reasons"] if r in LEG_REASONS]
    if fast is not None and fast_off:
        fast = None
        reasons.append("FAST_WINDOW_OFF_CALENDAR_ROW")
    if ret is not None and base_off:
        ret, base = None, None
        reasons.append("TRAILING_24M_BASE_OFF_CALENDAR_ROW")
    if fast is None and not any(r in reasons for r in FAST_REASONS):
        reasons.append("FAST_DATA_INSUFFICIENT")
    fast_ok = fast is not None
    state = {"fast": fast,
             "fastTrendAdverse": bool(components["trendAdverse"]) if fast_ok else None,
             "fastVolAdverse": bool(components["volAdverse"]) if fast_ok else None,
             "vol63": float(components["vol63"]) if fast_ok else None,
             "fastLegAdverse": None if fast is None else fast == 2,
             "trailing24mReturn": ret, "baseSessionDate": None if base is None else str(base.date()),
             "target24mDate": str(target.date()), "returnLegAdverse": None if ret is None else ret < 0,
             "adverse": combine(fast, ret)}
    identity_rows = [[str(d.date()), str(aligned.loc[d, "state"]), _number(close.loc[d])] for d in aligned.index]
    return {"state": state, "undeterminedReasons": sorted(set(reasons), key=LEG_REASONS.index),
            "detail": {"fastWindowGapSessions": gaps[:20], "fastWindowOffCalendarRows": fast_off[:20], "baseOffCalendarRows": base_off[:20],
                       "expectedBaseSession": None if expected is None else str(expected.date())},
            "inputIdentity": hashlib.sha256(CORE.canonical(identity_rows)).hexdigest(),
            "served": {"requestedStart": str(first.date()), "servedFirstDate": str(raw.index[0].date()), "servedLastDate": str(raw.index[-1].date()),
                       "servedRows": int(len(raw)), "servedSha256": hashlib.sha256(CORE.canonical(_served_rows(raw))).hexdigest(),
                       "offCalendarRowsInSpan": len(off), "sessionStates": BI.summary(aligned)["states"]}}


# --------------------------------------------------------------------------- #
# Receipts
# --------------------------------------------------------------------------- #
REQUIRED = ("schemaVersion", "studyId", "hypothesisId", "stateClass", "definition", "pathway", "evidenceClass", "researchOnly",
            "productionEffect", "specSha256", "codeIdentity", "authorization", "signalDate", "executionDate", "signalSessionFinalAtUtc",
            "createdAtUtc", "source", "inputIdentity", "state", "undeterminedReasons", "undeterminedDetail", "previousReceiptSha256",
            "receiptSha256")
STATE_KEYS = ("fast", "fastTrendAdverse", "fastVolAdverse", "vol63", "fastLegAdverse", "trailing24mReturn", "baseSessionDate",
              "target24mDate", "returnLegAdverse", "adverse")


def build_receipt(frame, *, pathway: str, signal_date: str, created_at_utc, now_utc, fetched_at_utc, merged_at_utc, spec: dict,
                  spec_digest: str, code_identity: dict, vendor_package: str, previous_receipt_sha256) -> dict:
    """One receipt for ``signal_date`` from the frame the vendor served at ``fetched_at_utc``, or AttemptStop."""
    if pathway not in EVIDENCE_CLASS_BY_PATHWAY:
        raise ValueError("UNKNOWN_PATHWAY")
    if not CORE.is_sha256(spec_digest) or not CORE.is_git_sha(code_identity.get("commitSha")) or not code_identity.get("files"):
        raise AttemptStop(REFUSED, "IDENTITY_REQUIRED")
    if vendor_package != SOURCE["vendorPackage"]:
        raise AttemptStop(REFUSED, "SOURCE_ROUTE_CHANGED: " + str(vendor_package))
    floor = spec["schedule"]["firstEligibleSignalSessionFloor"]
    if signal_date < floor:
        raise AttemptStop(SKIPPED, "SIGNAL_BEFORE_REGISTERED_FLOOR: " + floor)
    try:
        execution = CORE.check_timing(signal_date=signal_date, created_at_utc=created_at_utc, now_utc=now_utc, merged_at_utc=merged_at_utc)
    except ValueError as exc:
        quiet = str(exc).startswith(("SIGNAL_BEFORE_PROSPECTIVE_ELIGIBILITY", "RECEIPT_CREATED_AFTER_EXECUTION_OPEN_BACKDATED",
                                     "RECEIPT_CREATED_BEFORE_SIGNAL_CLOSE"))
        raise AttemptStop(SKIPPED if quiet else REFUSED, str(exc)) from exc
    fetched = CORE.utc(fetched_at_utc)
    if fetched < _final_at(signal_date) or fetched > CORE.utc(created_at_utc):
        raise AttemptStop(REFUSED, "FETCH_TIME_OUTSIDE_SIGNAL_CLOSE_AND_RECEIPT")
    seen = observe(frame, signal_date)
    if seen["undeterminedReasons"] and not is_final_attempt(signal_date, created_at_utc):
        raise AttemptStop(DEFERRED, "PROVIDER_WINDOW_GAP: " + ",".join(seen["undeterminedReasons"]), seen["detail"])
    receipt = {
        "schemaVersion": SCHEMA_VERSION, "studyId": STUDY, "hypothesisId": HYPOTHESIS, "stateClass": STATE_CLASS, "definition": DEFINITION,
        "pathway": pathway, "evidenceClass": EVIDENCE_CLASS_BY_PATHWAY[pathway], "researchOnly": True, "productionEffect": "NONE",
        "specSha256": spec_digest,
        "codeIdentity": {"commitSha": code_identity["commitSha"], "files": dict(sorted(code_identity["files"].items())),
                         **{k: code_identity[k] for k in ("conformanceDigest", "calendarVersion") if k in code_identity}},
        "authorization": {"basis": "MERGE_OF_THE_REGISTERED_SPEC", "mergedAtUtc": str(CORE.utc(merged_at_utc).isoformat()),
                          "firstProspectiveSession": str(CORE.first_prospective_session(merged_at_utc).date()), "registeredFloor": floor},
        "signalDate": signal_date, "executionDate": str(execution.date()),
        "signalSessionFinalAtUtc": str(_final_at(signal_date).isoformat()), "createdAtUtc": str(CORE.utc(created_at_utc).isoformat()),
        "source": {**{k: SOURCE[k] for k in ("sourceId", "instrument", "route")}, "vendorPackage": vendor_package,
                   "fetchedAtUtc": str(fetched.isoformat()), **seen["served"]},
        "inputIdentity": seen["inputIdentity"], "state": seen["state"],
        "undeterminedReasons": seen["undeterminedReasons"], "undeterminedDetail": seen["detail"],
        "previousReceiptSha256": previous_receipt_sha256,
    }
    receipt["receiptSha256"] = CORE.receipt_digest(receipt)
    validate_receipt(receipt, pathway=pathway)
    return receipt


def _is_num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_receipt(receipt: dict, *, pathway: str) -> None:
    """Bytes AND logic. A recomputed digest proves only the bytes; every dependent field is re-derived from the receipt's own legs and the
    calendar, so a tampered value with a recomputed digest is still refused."""
    missing = [k for k in REQUIRED if k not in receipt]
    if missing:
        raise ValueError("RECEIPT_FIELDS_MISSING: " + ",".join(missing))
    if receipt["studyId"] != STUDY or receipt["pathway"] != pathway or receipt["evidenceClass"] != EVIDENCE_CLASS_BY_PATHWAY[pathway]:
        raise ValueError("RECEIPT_PATHWAY_MISMATCH")
    if receipt["productionEffect"] != "NONE" or receipt["researchOnly"] is not True:
        raise ValueError("RECEIPT_CLAIMS_PRODUCTION_EFFECT")
    if receipt["schemaVersion"] != SCHEMA_VERSION or receipt["definition"] != DEFINITION or receipt["hypothesisId"] != HYPOTHESIS \
            or receipt["stateClass"] != STATE_CLASS:
        raise ValueError("RECEIPT_IDENTITY_OR_DEFINITION_MISMATCH")
    if CORE.receipt_digest(receipt) != receipt["receiptSha256"]:
        raise ValueError("RECEIPT_DIGEST_MISMATCH")
    CORE.scan_for_outcome_keys(receipt)
    json.dumps(receipt, allow_nan=False)
    previous = receipt["previousReceiptSha256"]
    if previous is not None and not CORE.is_sha256(previous):
        raise ValueError("RECEIPT_CHAIN_FIELD_MALFORMED")
    if not CORE.is_sha256(receipt["inputIdentity"]) or not CORE.is_sha256(receipt["specSha256"]):
        raise ValueError("RECEIPT_IDENTITY_MALFORMED")
    _check_timing(receipt)
    _check_state(receipt)


def _check_timing(r: dict) -> None:
    day = r["signalDate"]
    try:
        stamp = pd.Timestamp(day)
    except (ValueError, TypeError) as exc:
        raise ValueError("RECEIPT_SIGNAL_DATE_MALFORMED") from exc
    if str(stamp.date()) != day or not CORE.is_weekly_decision_session(stamp):
        raise ValueError("RECEIPT_SIGNAL_DATE_NOT_A_WEEKLY_DECISION_SESSION")
    if day < r["authorization"]["registeredFloor"] or day < r["authorization"]["firstProspectiveSession"]:
        raise ValueError("RECEIPT_SIGNAL_BEFORE_ELIGIBILITY")
    if r["authorization"]["firstProspectiveSession"] != str(CORE.first_prospective_session(r["authorization"]["mergedAtUtc"]).date()):
        raise ValueError("RECEIPT_AUTHORIZATION_INCONSISTENT")
    if r["executionDate"] != str(CORE.next_kr_session(stamp).date()) or r["signalSessionFinalAtUtc"] != str(_final_at(stamp).isoformat()):
        raise ValueError("RECEIPT_SESSION_FIELDS_INCONSISTENT")
    created, fetched = CORE.utc(r["createdAtUtc"]), CORE.utc(r["source"]["fetchedAtUtc"])
    if not _final_at(stamp) <= fetched <= created < _open_at(r["executionDate"]):
        raise ValueError("RECEIPT_OUTSIDE_ITS_WINDOW")
    if r["source"]["servedLastDate"] != day:
        raise ValueError("RECEIPT_SOURCE_DOES_NOT_END_AT_THE_SIGNAL_SESSION")
    if r["source"]["sourceId"] != SOURCE["sourceId"] or r["source"]["vendorPackage"] != SOURCE["vendorPackage"]:
        raise ValueError("RECEIPT_SOURCE_MISMATCH")
    if r["undeterminedReasons"] and not is_final_attempt(day, created):
        raise ValueError("RECEIPT_UNDETERMINED_LEG_RECORDED_BEFORE_THE_FINAL_ATTEMPT_WINDOW")


def _check_state(r: dict) -> None:
    s, reasons = r["state"], r["undeterminedReasons"]
    if set(s) != set(STATE_KEYS):
        raise ValueError("RECEIPT_STATE_KEYS_MISMATCH")
    if not isinstance(reasons, list) or any(x not in LEG_REASONS for x in reasons) or len(set(reasons)) != len(reasons):
        raise ValueError("RECEIPT_REASONS_MALFORMED")
    fast, ret, base = s["fast"], s["trailing24mReturn"], s["baseSessionDate"]
    target = base_target(r["signalDate"])
    if s["target24mDate"] != str(target.date()):
        raise ValueError("RECEIPT_TARGET_DATE_INCONSISTENT")
    if fast is None:
        if any(s[k] is not None for k in ("fastTrendAdverse", "fastVolAdverse", "vol63", "fastLegAdverse")) or \
                not any(x in reasons for x in FAST_REASONS):
            raise ValueError("RECEIPT_FAST_LEG_INCONSISTENT")
    else:
        if isinstance(fast, bool) or fast not in (0, 1, 2) or any(x in reasons for x in FAST_REASONS):
            raise ValueError("RECEIPT_FAST_LEG_INCONSISTENT")
        if not _is_num(s["vol63"]) or s["vol63"] < 0 or s["fastVolAdverse"] is not (s["vol63"] > K.FAST_VOL_THRESHOLD) \
                or not isinstance(s["fastTrendAdverse"], bool) or fast != int(s["fastTrendAdverse"]) + int(s["fastVolAdverse"]) \
                or s["fastLegAdverse"] is not (fast == 2):
            raise ValueError("RECEIPT_FAST_COMPONENTS_INCONSISTENT")
    if ret is None:
        if base is not None or s["returnLegAdverse"] is not None or not any(x in reasons for x in BASE_REASONS):
            raise ValueError("RECEIPT_RETURN_LEG_INCONSISTENT")
    else:
        expected = expected_base_session(r["signalDate"])
        if not _is_num(ret) or ret <= -1.0 or any(x in reasons for x in BASE_REASONS) or expected is None \
                or base != str(expected.date()) or s["returnLegAdverse"] is not (ret < 0):
            raise ValueError("RECEIPT_RETURN_LEG_INCONSISTENT")
    if s["adverse"] is not combine(fast, ret):
        raise ValueError("RECEIPT_ADVERSE_DISAGREES_WITH_LEGS")


def verify_chain(rows: list[dict]) -> None:
    """Each row names its predecessor's digest and the first names none, so a deleted, reordered or inserted row is refused."""
    previous = None
    for row in rows:
        if row["previousReceiptSha256"] != previous:
            raise ValueError("LEDGER_CHAIN_BROKEN at " + str(row.get("signalDate")))
        previous = row["receiptSha256"]
    dates = [row["signalDate"] for row in rows]
    if dates != sorted(set(dates)):
        raise ValueError("LEDGER_ORDER_BROKEN")
    if len({row["specSha256"] for row in rows}) > 1:
        raise ValueError("RECEIPT_SPEC_CHANGED_WITHIN_A_LEDGER")


def read_receipts(path, *, pathway: str) -> list[dict]:
    """Every row validated (bytes and logic) and the chain verified; any failure refuses the whole ledger."""
    try:
        rows = CORE.read_ledger(path, lambda r: validate_receipt(r, pathway=pathway))
    except json.JSONDecodeError as exc:
        raise ValueError("LEDGER_ROW_NOT_JSON: " + str(exc)) from exc
    verify_chain(rows)
    return rows


def last_digest(rows: list[dict]):
    return rows[-1]["receiptSha256"] if rows else None


def append_receipt(path, receipt: dict, *, pathway: str) -> str:
    """SYNTHETIC (and test) append: the chain is re-verified with the new row before the core's append-only write."""
    verify_chain([*read_receipts(path, pathway=pathway), receipt])
    return CORE.append(path, receipt, validate=lambda r: validate_receipt(r, pathway=pathway), key_fields=KEY_FIELDS)


def append_live_receipt(path, receipt: dict, *, merged_at_utc, clock) -> dict:
    """LIVE append: the chain is re-verified, then the selection challenger's write-time gate restamps ``createdAtUtc`` with a fresh clock,
    re-checks the window and reads the clock once more immediately before the bytes are written (09:00 KST exactly is outside)."""
    verify_chain([*read_receipts(path, pathway=LIVE), receipt])
    return V1.append_live_receipt(path, receipt, merged_at_utc=merged_at_utc, clock=clock,
                                  validate=lambda r: validate_receipt(r, pathway=LIVE), key_fields=KEY_FIELDS)


# --------------------------------------------------------------------------- #
# Attempt log (non-evidence) and coverage
# --------------------------------------------------------------------------- #
def attempt_row(*, signal_date, kind, reason, detail, attempted_at_utc, run_id=None) -> dict:
    row = {"studyId": STUDY, "evidence": False, "signalDate": signal_date, "status": kind, "reason": reason, "detail": detail,
           "attemptedAtUtc": str(CORE.utc(attempted_at_utc).isoformat()), "runId": run_id}
    row["rowSha256"] = hashlib.sha256(CORE.canonical(row)).hexdigest()
    return row


def weekly_sessions(start, end) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """``(weekly decision session, its next KR session)`` for every weekly decision session in [start, end], from ONE calendar read. Equal to
    ``prospective_receipt_core.is_weekly_decision_session`` session by session (tested), which re-reads the calendar per day."""
    days = RC.sessions(str(pd.Timestamp(start).date()), str((pd.Timestamp(end) + pd.Timedelta(days=20)).date()), "KR")
    return [(d, n) for d, n in zip(days[:-1], days[1:])
            if d <= pd.Timestamp(end) and tuple(n.isocalendar())[:2] != tuple(d.isocalendar())[:2]]


def expected_sessions(first_eligible, now_utc) -> list[str]:
    """Weekly decision sessions from ``first_eligible`` whose receipt window has CLOSED by ``now_utc`` (a window still open is not missed)."""
    now = CORE.utc(now_utc)
    end = (now + CORE.KST).tz_localize(None).normalize()
    if pd.Timestamp(first_eligible) > end:
        return []
    return [str(d.date()) for d, nxt in weekly_sessions(first_eligible, end) if _open_at(nxt) <= now]


def first_eligible_session(merged_at_utc, floor) -> str:
    first = max(CORE.first_prospective_session(merged_at_utc), pd.Timestamp(floor))
    return str(weekly_sessions(first, first + pd.Timedelta(days=20))[0][0].date())


def coverage(receipts: list[dict], attempts: list[dict], *, merged_at_utc, floor, now_utc, horizon=None, min_blocks=None) -> dict:
    """Signal-time facts only: which weekly sessions were recorded, which were missed and why, how often a leg was undetermined, and the
    state geometry of H63 blocks. Reads no price after a signal session and no outcome."""
    first = first_eligible_session(merged_at_utc, floor)
    due = expected_sessions(first, now_utc)
    recorded = {r["signalDate"]: r for r in receipts}
    last_reason = {}
    for row in attempts:
        last_reason[row["signalDate"]] = [row["status"], row["reason"]]
    missed = [{"signalDate": d, "lastAttempt": last_reason.get(d, ["NO_ATTEMPT_RECORDED", None])} for d in due if d not in recorded]
    states = {"adverse": 0, "notAdverse": 0, "undetermined": 0}
    for r in receipts:
        states["adverse" if r["state"]["adverse"] is True else "notAdverse" if r["state"]["adverse"] is False else "undetermined"] += 1
    out = {"firstEligibleSignalSession": first, "dueSessions": len(due), "recordedSessions": len(receipts), "missedSessions": missed,
           "states": states, "receiptsWithUndeterminedLeg": sum(bool(r["undeterminedReasons"]) for r in receipts)}
    if horizon:
        out["blockGeometry"] = state_blocks(receipts, now_utc=now_utc, horizon=horizon, min_blocks=min_blocks, first_eligible=first)
    return out


def state_blocks(receipts: list[dict], *, now_utc, horizon: int, min_blocks: int, first_eligible: str) -> dict:
    """Non-overlapping H-session blocks from the first eligible execution session, each carrying the state of the weekly decision session
    that last preceded its entry (UNOBSERVED when that session has no receipt, never benign). Only blocks whose maturity session is final by
    ``now_utc`` count. The convention is the README B diagnostic's, carried forward for the outcome registration to confirm; no return is read."""
    origin = CORE.next_kr_session(first_eligible)
    span = RC.sessions(str(origin.date()), str((CORE.utc(now_utc) + CORE.KST).tz_localize(None).normalize().date()), "KR")
    by_date = {r["signalDate"]: r for r in receipts}
    weekly = [d for d, _ in weekly_sessions(pd.Timestamp(first_eligible) - pd.Timedelta(days=7), span[-1] if len(span) else origin)]
    counts = {"adverse": 0, "notAdverse": 0, "undetermined": 0, "unobserved": 0}
    blocks = []
    for position in range(0, len(span), horizon):
        entry = span[position]
        if not CORE.has_matured(entry, horizon, now_utc):
            break
        before = [d for d in weekly if d < entry]
        signal = str(before[-1].date()) if before else None
        receipt = by_date.get(signal)
        label = "unobserved" if receipt is None else {True: "adverse", False: "notAdverse"}.get(receipt["state"]["adverse"], "undetermined")
        counts[label] += 1
        blocks.append({"entrySession": str(entry.date()), "stateSignalDate": signal, "state": label})
    sufficient = counts["adverse"] >= min_blocks and counts["notAdverse"] >= min_blocks
    return {"convention": "INHERITED_README_B_DIAGNOSTIC_PENDING_OUTCOME_REGISTRATION", "horizonSessions": horizon, "originSession":
            str(origin.date()), "maturedBlocks": len(blocks), "counts": counts, "minBlocksPerState": min_blocks,
            "inferenceStatus": "STATE_BLOCKS_SUFFICIENT_OUTCOME_CONTRACT_NOT_REGISTERED" if sufficient
            else "DESCRIPTIVE_ONLY_INSUFFICIENT_STATE_BLOCKS", "blocks": blocks}


# --------------------------------------------------------------------------- #
# Outcome evaluation: a separate, unregistered contract
# --------------------------------------------------------------------------- #
OUTCOME_BLOCKED = "BLOCKED_OUTCOME_CONTRACT_NOT_REGISTERED"


def outcome_gate(spec: dict) -> dict:
    """The H63 evaluation of B-H1 stays blocked until a separately registered outcome contract exists. Nothing is fetched or computed."""
    contract = spec["outcomeEvaluation"]
    if contract.get("status") != OUTCOME_BLOCKED or contract.get("registeredContract") is not None:
        raise ValueError("OUTCOME_CONTRACT_STATE_UNEXPECTED: a registered outcome contract is a new study version, not an edit of this spec")
    return {"status": OUTCOME_BLOCKED, "horizonSessions": contract["horizonSessions"],
            "openDecisions": [d["id"] for d in contract["openDecisions"]], "computed": False}
