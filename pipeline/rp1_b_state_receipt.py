"""RP1 Track B — B-H1 prospective MARKET_OBSERVED state receipt PREVIEW.

Builds, from a past-only KR index close series, the one thing B-H1 needs on a decision date: whether the market state is 'adverse'
(FAST == 2 OR trailing 24-month market return < 0), exactly as `docs/research-program/03-studies-abc-ko.md` B-H1 defines it. FAST is the sealed
`kr_market_risk_model.fast_states`; nothing here adds a window, threshold or lag, collects data, or reads a macro vintage.

A PREVIEW is not a receipt. It carries `evidenceClass = PROSPECTIVE_PAPER_PREVIEW`, is never appended to a ledger by this module, runs no
authorization or timing check, and cannot be mistaken for `PROSPECTIVE_PAPER` evidence. It records state, inputs and availability only; the
outcome-key scanner of `prospective_receipt_core` is applied to every receipt. B receipts stay independent of A and C.

Missing is neither adverse nor benign: if one leg is adverse the state is adverse whatever the other leg; if neither is adverse and a leg is
missing the state is None, never False.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

from . import kr_market_risk_model as K
from . import prospective_receipt_core as P
from . import replay_calendar as RC

STUDY = "rp1-b-h1-state-receipt-preview-v1"
SCHEMA_VERSION = 1
EVIDENCE_CLASS = "PROSPECTIVE_PAPER_PREVIEW"
DEFINITION = "B-H1: FAST == 2 OR trailing 24-calendar-month index return < 0"
LOOKBACK_MONTHS = 24
REQUIRED = ("schemaVersion", "studyId", "evidenceClass", "definition", "signalDate", "inputIdentity", "fast", "trailing24mReturn",
            "baseSessionDate", "adverse", "unavailableReasons", "ledgerWritten")


def series_identity(close):
    s = pd.Series(close, dtype=float)
    rows = [[str(pd.Timestamp(d).date()), float(v) if np.isfinite(v) else None] for d, v in s.items()]
    return hashlib.sha256(P.canonical(rows)).hexdigest()


def observe(close, signal_date):
    """State at `signal_date` from closes dated on or before it. Data after the signal date is a refusal, never silently dropped."""
    s = pd.Series(close, dtype=float)
    s.index = pd.DatetimeIndex(s.index)
    if not s.index.is_monotonic_increasing:
        raise ValueError("TIMESTAMPS_NOT_MONOTONIC")
    if s.index.has_duplicates:
        raise ValueError("DUPLICATE_TIMESTAMPS")
    day = pd.Timestamp(signal_date).normalize()
    if len(s) and s.index[-1] > day:
        raise ValueError("DATA_AFTER_SIGNAL_DATE")
    if not P.is_weekly_decision_session(day):
        raise ValueError("SIGNAL_DATE_IS_NOT_A_WEEKLY_DECISION_SESSION")
    reasons = []
    if len(s) == 0 or s.index[-1] != day or not np.isfinite(s.iloc[-1]) or s.iloc[-1] <= 0:
        return {"fast": None, "ret": None, "base": None, "adverse": None, "reasons": ["SIGNAL_DATE_CLOSE_UNAVAILABLE"], "series": s}
    fast = K.fast_states(s)["fast"].iloc[-1]
    fast = None if not np.isfinite(fast) else int(fast)
    if fast is None:
        reasons.append("FAST_DATA_INSUFFICIENT")
    target = day - pd.DateOffset(months=LOOKBACK_MONTHS)
    # The sealed definition names no staleness tolerance. The base is the last KR exchange session on or before the target date
    # (holidays resolve through the calendar); the series must carry that exact session with a valid close, otherwise the leg is unavailable.
    cal = pd.DatetimeIndex(RC.sessions(str((target - pd.Timedelta(days=15)).date()), str(target.date()), "KR"))
    expected = cal[-1] if len(cal) else None
    valid = s[np.isfinite(s) & (s > 0)]
    eligible = valid.loc[expected:expected] if expected is not None else valid.iloc[:0]
    ret, base = None, None
    if len(eligible) == 0:
        reasons.append("TRAILING_24M_BASE_UNAVAILABLE")
    else:
        base, ret = eligible.index[-1], float(s.iloc[-1] / eligible.iloc[-1] - 1.0)
    legs = [fast == 2 if fast is not None else None, ret < 0 if ret is not None else None]
    adverse = True if any(v is True for v in legs) else (None if any(v is None for v in legs) else False)
    return {"fast": fast, "ret": ret, "base": base, "adverse": adverse, "reasons": reasons, "series": s}


def build_preview(close, signal_date):
    o = observe(close, signal_date)
    receipt = {"schemaVersion": SCHEMA_VERSION, "studyId": STUDY, "evidenceClass": EVIDENCE_CLASS, "definition": DEFINITION,
               "signalDate": str(pd.Timestamp(signal_date).date()), "inputIdentity": series_identity(o["series"]), "fast": o["fast"],
               "trailing24mReturn": o["ret"], "baseSessionDate": None if o["base"] is None else str(o["base"].date()), "adverse": o["adverse"],
               "unavailableReasons": o["reasons"], "ledgerWritten": False}
    P.scan_for_outcome_keys(receipt)
    receipt["receiptSha256"] = P.receipt_digest(receipt)
    validate_preview(receipt)
    return receipt


def validate_preview(receipt):
    missing = [k for k in REQUIRED + ("receiptSha256",) if k not in receipt]
    if missing:
        raise ValueError("PREVIEW_FIELD_MISSING: " + ",".join(missing))
    if receipt["evidenceClass"] != EVIDENCE_CLASS or receipt["ledgerWritten"] is not False:
        raise ValueError("PREVIEW_MUST_NOT_CLAIM_LEDGER_EVIDENCE")
    if receipt["receiptSha256"] != P.receipt_digest(receipt):
        raise ValueError("PREVIEW_DIGEST_MISMATCH")
    P.scan_for_outcome_keys(receipt)
    if receipt["adverse"] is False and receipt["unavailableReasons"]:
        raise ValueError("NOT_ADVERSE_CLAIMED_WITH_A_MISSING_LEG")
    json.dumps(receipt, allow_nan=False)
    return True
