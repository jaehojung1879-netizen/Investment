"""Early descriptive monitoring and the evidence schedule for us-capital-allocation-alpha-v1. Research only; NEVER a verdict.

The registered H126 claim has a single look at its maturity gate (`us_capital_allocation_evaluation.evaluate_program`). Waiting for
that gate does not mean learning nothing in the meantime, and the answer is NOT to peek at the primary statistic early. This module
defines what may be watched while evidence accumulates, and refuses to compute the one thing that must not be watched:

* signal coverage, blocked share, candidate persistence, turnover, sector and name concentration (from receipts alone, no price);
* H21 DESCRIPTIVE returns after each receipt's 21-session horizon has matured (means and counts, no interval, no test, no verdict);
* H126 PROGRESS toward the gate (counts of matured weeks and independent windows), never the H126 excess return itself.

Short-horizon observations do not establish the primary H126 claim and are not substituted for it. The registered statistical success
criteria are not touched.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from pipeline import prospective_receipt_core as CORE
from pipeline import us_capital_allocation_diagnostics as DG
from pipeline import us_capital_allocation_evaluation as E
from pipeline import us_capital_allocation_policy as P
from pipeline import us_capital_allocation_receipts as R

DESCRIPTIVE_HORIZON = 21
DESCRIPTIVE_LABEL = "DESCRIPTIVE_H21_NOT_A_VERDICT"
GATE = P.registration()["maturityGate"]
BLOCK_WEEKS = P.registration()["inference"]["blockWeeks"]


# --------------------------------------------------------------------------- #
# From receipts alone (no price, no outcome)
# --------------------------------------------------------------------------- #
def signal_monitor(receipts) -> dict:
    """Coverage, persistence, turnover and exposure of the prospective signals. `receipts` are validated receipt dicts."""
    rows = sorted(receipts, key=lambda r: r["signalDate"])
    if not rows:
        return {"receipts": 0, "label": "NO_RECEIPTS_YET"}
    measured = [r["coverage"]["funnel"]["measured"] for r in rows]
    passers = [len(r["decision"]["passers"]) for r in rows]
    decisions = [(r["signalDate"], r["decision"]) for r in rows]
    pathways = sorted({r["pathway"] for r in rows})
    return {"label": "DESCRIPTIVE_SIGNAL_MONITOR", "receipts": len(rows), "pathways": pathways,
            "evidenceClass": "PROSPECTIVE_PAPER_RESEARCH_CANDIDATE" if pathways == [R.LIVE] else "MIXED_OR_SYNTHETIC_NOT_EVIDENCE",
            "measuredNames": {"min": min(measured), "median": float(np.median(measured)), "max": max(measured)},
            "passersPerWeek": {"min": min(passers), "median": float(np.median(passers)), "max": max(passers)},
            **DG.decision_diagnostics(decisions, include_names=True), "margins": DG.margins(decisions),
            "reading": "descriptive only: how often the rule participates, how stable its names are, where it concentrates"}


# --------------------------------------------------------------------------- #
# H21 descriptive (after each receipt's own 21-session maturity; never before)
# --------------------------------------------------------------------------- #
def descriptive_h21_record(receipt, *, price_frames, now_utc, terminal=None) -> dict:
    """Net portfolio return over 21 sessions and the excess over SPY and QQQ. Refused until the 21st session after execution is final."""
    if receipt["decision"]["status"] == "BLOCKED":
        return {"label": DESCRIPTIVE_LABEL, "receiptSha256": receipt["receiptSha256"], "status": "BLOCKED_RECEIPT"}
    now = CORE.utc(now_utc)
    exit_session = R.maturity_session(receipt["executionDate"], DESCRIPTIVE_HORIZON)
    if not R.has_matured(receipt["executionDate"], DESCRIPTIVE_HORIZON, now):
        raise ValueError("H21_NOT_MATURED: maturity session %s is final %s" % (
            exit_session.date(), (exit_session + R.US_CLOSE_FINAL_UTC).tz_localize("UTC")))
    entry = receipt["executionDate"]
    bench = {}
    for ticker in (P.OFFICIAL_BENCHMARK, P.ALTERNATIVE_BENCHMARK):
        value, reason = E.total_return_between(price_frames.get(ticker), entry, exit_session)
        if value is None:
            raise ValueError("BENCHMARK_OUTCOME_UNAVAILABLE: %s %s" % (ticker, reason))
        bench[ticker] = value
    weights = dict(receipt["decision"]["weights"] or {})
    names = {t: E.name_outcome(price_frames.get(t), entry, exit_session, (terminal or {}).get(t)) for t in sorted(weights)}
    portfolio = E.portfolio_outcome(weights, receipt["decision"]["fallbackWeight"], names, bench["SPY"], bench["QQQ"])
    return {"label": DESCRIPTIVE_LABEL, "receiptSha256": receipt["receiptSha256"], "signalDate": receipt["signalDate"],
            "horizonSessions": DESCRIPTIVE_HORIZON, "maturitySession": str(exit_session.date()), "benchmarkReturns": bench,
            "portfolio": portfolio, "pathway": receipt["pathway"]}


def summarize_h21(records) -> dict:
    """Counts and plain means. No standard error, no interval, no p-value, no verdict: that would be a repeated look at a short horizon."""
    complete = [r for r in records if r.get("portfolio", {}).get("status") == "COMPLETE"]
    unresolved = [r for r in records if r.get("portfolio", {}).get("status") not in (None, "COMPLETE")]
    out = {"label": DESCRIPTIVE_LABEL, "horizonSessions": DESCRIPTIVE_HORIZON, "matured": len(records), "complete": len(complete),
           "unresolvedOrBlocked": len(unresolved) + sum(1 for r in records if r.get("status") == "BLOCKED_RECEIPT"),
           "inference": "NONE: no interval, test or verdict is computed at H21; short-horizon results do not establish the H126 claim"}
    if complete:
        for key, field in (("meanExcessVsSPY", "excessVsSPY"), ("meanExcessVsQQQ", "excessVsQQQ"), ("meanNetReturn", "netReturn")):
            out[key] = round(float(np.mean([r["portfolio"][field] for r in complete])), 6)
        out["passiveSpreadQQQMinusSPY"] = round(float(np.mean([r["benchmarkReturns"]["QQQ"] - r["benchmarkReturns"]["SPY"] for r in complete])), 6)
    return out


# --------------------------------------------------------------------------- #
# H126 progress: counts toward the gate, never the primary statistic
# --------------------------------------------------------------------------- #
def h126_progress(outcomes) -> dict:
    """How far the primary evaluation is from its maturity gate. Reads no return field."""
    matured = len(outcomes)
    unresolved = sum(1 for o in outcomes if o.get("portfolio", {}).get("status") not in ("COMPLETE", "BLOCKED_RECEIPT"))
    independent = matured // BLOCK_WEEKS
    return {"label": "H126_PROGRESS_COUNTS_ONLY", "maturedSignalWeeks": matured, "independentWindows": independent,
            "gate": {"minMaturedSignals": GATE["minMaturedSignals"], "minIndependentWindows": GATE["minIndependentWindows"]},
            "weeksRemainingToGate": max(GATE["minIndependentWindows"] * BLOCK_WEEKS - matured, GATE["minMaturedSignals"] - matured, 0),
            "unresolvedTerminalOutcomes": unresolved,
            "primaryStatisticComputed": False,
            "rule": "the H126 excess return and its interval are computed once, by evaluate_program, at the gate; this function never reads them"}


# --------------------------------------------------------------------------- #
# Schedule
# --------------------------------------------------------------------------- #
def _weekly_sessions(first, count):
    """The next `count` weekly decision sessions (last US session of each ISO week) on or after `first`."""
    out, cursor = [], pd.Timestamp(first).normalize()
    while len(out) < count:
        window = R._sessions(cursor - pd.Timedelta(days=cursor.weekday()), 6)
        if len(window) and window[-1] >= cursor and (not out or window[-1] > out[-1]):
            out.append(window[-1])
        cursor = cursor - pd.Timedelta(days=cursor.weekday()) + pd.Timedelta(days=7)
    return out


def evidence_schedule(merged_at_utc) -> dict:
    """Dates for a hypothetical owner approval (merge of the authorizing commit) at `merged_at_utc`. Calendar facts only."""
    first_session = R.first_prospective_session(merged_at_utc)
    needed = max(GATE["minIndependentWindows"] * BLOCK_WEEKS, GATE["minMaturedSignals"])
    signals = _weekly_sessions(first_session, needed + 1)
    first_signal, gate_signal = signals[0], signals[needed - 1]
    execution = lambda s: R.next_us_session(s)      # noqa: E731
    first_h21 = R.maturity_session(execution(first_signal), DESCRIPTIVE_HORIZON)
    first_h126 = R.maturity_session(execution(first_signal), P.HORIZON_SESSIONS)
    gate_maturity = R.maturity_session(execution(gate_signal), P.HORIZON_SESSIONS)
    paper_days = math.ceil((gate_maturity - first_signal).days)
    return {
        "assumedApproval": str(CORE.utc(merged_at_utc)), "firstProspectiveSession": str(first_session.date()), "firstSignalSession": str(first_signal.date()),
        "firstH21Maturity": str(first_h21.date()), "firstH126Maturity": str(first_h126.date()),
        "gate": {"maturedSignalWeeksRequired": needed, "independentWindowsRequired": GATE["minIndependentWindows"], "blockWeeks": BLOCK_WEEKS,
                 "signalWeekThatMakesTheGateReachable": str(gate_signal.date()), "earliestSingleLookVerdictSession": str(gate_maturity.date()),
                 "calendarDaysFromFirstSignal": paper_days, "minPaperDays": GATE["minPaperDays"],
                 "calendarBound": "replay_calendar pinned to 2035-12-31"},
        "monitoring": {"signalMonitor": "from the first receipt, weekly, descriptive", "h21Descriptive": "per receipt, after its own 21st session; counts and means only",
                       "h126Progress": "counts only until the gate", "primaryVerdict": "once, at the gate; later updates are continuation reports"},
        "notAccelerated": "observed returns can neither bring the gate forward nor redefine it",
    }
