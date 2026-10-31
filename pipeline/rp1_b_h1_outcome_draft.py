"""Unregistered B-H1 contract probes. No LIVE evaluator, fetcher, writer or authorization.

Selection and outcome arithmetic accept invented SYN tickers only. Registration
cannot be obtained by editing a status string in a caller-supplied dictionary.
"""
from __future__ import annotations

import copy
import math

import numpy as np
import pandas as pd

from . import kr_bar_integrity as BI
from . import longterm as LT
from . import prospective_receipt_core as CORE
from . import replay_calendar as RC
from . import rp1_b_h1_state as STATE
from .rp1_kr_a0 import eligibility

STUDY = "rp1-b-h1-outcome-v1"
STATUS = "OWNER_REVIEW_DRAFT_NOT_REGISTERED"
MIN_BLOCKS = 6
ORIGIN = "2026-11-02"
MAX_BLOCKS = 20


def live_gate(_document=None):
    """Unconditionally closed, including a forged REGISTERED status/approval."""
    return {"status": STATE.OUTCOME_BLOCKED, "computed": False, "productionEffect": "NONE"}


def schedule():
    days = RC.sessions(ORIGIN, "2031-12-31", "KR")
    weekly = [d for d, _ in STATE.weekly_sessions("2026-10-30", "2031-12-31")]
    return [{"block": k + 1, "entrySession": str(days[k * 63].date()),
             "maturitySession": str(days[(k + 1) * 63].date()),
             "stateSignalDate": str(max(d for d in weekly if d < days[k * 63]).date())}
            for k in range(MAX_BLOCKS)]


def support(states):
    """States must already be authenticated; this is geometry, never registration."""
    counts = {key: states.count(key) for key in ("adverse", "notAdverse", "undetermined", "unobserved")}
    if sum(counts.values()) != len(states):
        raise ValueError("UNKNOWN_STATE")
    enough = min(counts["adverse"], counts["notAdverse"]) >= MIN_BLOCKS
    return {"counts": counts, "enough": enough, "p": 1,
            "status": "DESCRIPTIVE_ONLY_UNCALIBRATED_KR_H63" if enough
            else "DESCRIPTIVE_ONLY_INSUFFICIENT_STATE_BLOCKS"}


def _synthetic(tickers):
    if not tickers or any(not isinstance(t, str) or not t.startswith("SYN") for t in tickers):
        raise ValueError("SYNTHETIC_ONLY")


def synthetic_selection(rows, frames, *, signal, snapshot_date, available_at):
    """Exercise the proposed D1-D3 contract using invented inputs only.

    Evidence availability is independently checked; a future row is refused, not
    silently truncated. Rows/frames are never modified. No outcome is an argument.
    """
    _synthetic([r["ticker"] for r in rows])
    day = pd.Timestamp(signal)
    if pd.Timestamp(snapshot_date) >= day or CORE.utc(available_at) >= day.tz_localize("Asia/Seoul").tz_convert("UTC"):
        raise ValueError("POPULATION_NOT_STRICTLY_PRIOR")
    if len({r["ticker"] for r in rows}) != len(rows) or len(rows) > 120:
        raise ValueError("POPULATION_IDENTITY_INVALID")
    reasons = eligibility(rows, signal)
    ranked = []
    for row in rows:
        t = row["ticker"]
        CORE.scan_for_outcome_keys(row)
        f = frames[t]
        if f.index.has_duplicates or (f.index > day).any():
            raise ValueError("DUPLICATE_OR_POST_SIGNAL_BAR")
        if reasons[t]:
            continue
        sessions = RC.sessions(str((day - pd.Timedelta(days=600)).date()), signal, "KR")[-LT.MIN_HISTORY:]
        aligned = BI.calendar_frame(f, start=sessions[0], end=day)
        close = aligned["Close"].reindex(sessions)
        if len(close) != LT.MIN_HISTORY or close.isna().any():
            reasons[t].append("MOMENTUM_WINDOW_INCOMPLETE")
            continue
        ranked.append((LT.momentum_12_1(close), t))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]))
    k = len(ranked) // 3
    if not k:
        return {"status": "CROSS_SECTION_UNAVAILABLE", "excluded": reasons}
    # Equal-score endpoints use the same descending-score/ascending-ticker order.
    return {"status": "SYNTHETIC_FIXTURE", "n": len(ranked), "k": k,
            "long": [t for _, t in ranked[:k]], "short": [t for _, t in ranked[-k:]], "excluded": reasons}


def synthetic_spread(selection, outcomes, *, execution, now):
    """No missing selected name can disappear or change the fixed denominators."""
    if selection.get("status") != "SYNTHETIC_FIXTURE":
        raise ValueError("SYNTHETIC_ONLY")
    names = selection["long"] + selection["short"]
    _synthetic(names)
    if len(names) != len(set(names)) or len(selection["long"]) != len(selection["short"]):
        raise ValueError("INVALID_SELECTION")
    if not CORE.has_matured(execution, 63, now):
        raise ValueError("NOT_MATURED")
    maturity = str(CORE.maturity_session(execution, 63).date())
    before = copy.deepcopy(selection)
    values = {}
    for t in names:
        o = outcomes.get(t, {})
        if o.get("state") != "PRICED_TOTAL_RETURN" or o.get("exitSession") != maturity \
                or o.get("basisVerified") is not True or not CORE.finite(o.get("return")):
            return {"status": "DESCRIPTIVE_ONLY_SELECTED_SECURITY_UNPRICED", "spread": None, "p": 1}
        values[t] = o["return"]
    result = math.fsum(values[t] for t in selection["long"]) / len(selection["long"]) \
        - math.fsum(values[t] for t in selection["short"]) / len(selection["short"])
    assert selection == before
    return {"status": "SYNTHETIC_FIXTURE", "spread": result, "p": 1}


def state_contrast_attribution(daily, weights, states, *, horizon=63, calendar_step=5):
    """Synthetic additive-return feasibility probe, NOT a certified B-H1 estimator.

    Reuse the v4 SN interval on an exact calendar attribution of the difference
    between state means. Sparse signed state weights are not v4's approved statistic.
    A full design still needs compounded total-return, endogenous-state and missingness calibration.
    """
    from . import alpha_inference_calibration_v4 as v4

    if not support(list(states))["enough"]:
        raise ValueError("INSUFFICIENT_STATE_BLOCKS")
    n, names = weights.shape
    if daily.shape != (n * horizon, names) or len(states) != n:
        raise ValueError("GEOMETRY_MISMATCH")
    counts = {s: list(states).count(s) for s in ("adverse", "notAdverse")}
    daily_d = np.zeros(n * horizon)
    for k, s in enumerate(states):
        if s in counts:
            sign = 1 if s == "notAdverse" else -1
            daily_d[k * horizon:(k + 1) * horizon] = daily[k * horizon:(k + 1) * horizon] @ weights[k] * sign / counts[s]
    weeks = np.arange(n * horizon) // calendar_step
    d = np.bincount(weeks, weights=daily_d)
    x = np.bincount(weeks, weights=np.ones(n * horizon) / (n * horizon))
    interval = v4.calendar_time_sn_interval(d, x, 66.57, 1e-12)
    return d, x, interval
