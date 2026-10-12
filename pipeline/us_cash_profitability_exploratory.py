"""One-shot exploratory harness for `us-cash-profitability-signal-v1` on replay-v16 (prerequisite P4). NOT EXECUTED HERE.

The study this harness would run is `EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_US_HISTORY`: a futility screen on history that
earlier studies have already exposed. It can abandon the hypothesis (the calibrated one-sided 95% upper bound of the controlled H63
factor spread is <= 0); it can never confirm it. Nothing in this module changes the frozen hypothesis, feature, controls, horizon,
weights, statistic or interval:

* weights:  `us_h63_inference_calibration.centred_ranks` / `residual_weights` (the calibrated construction, called not copied);
* interval: `alpha_inference_calibration_v4.calendar_time_sn_interval` with the calibrated U1 90% critical value 28.31;
* minimums: 150 complete-case names per signal date (protocol) and 260 defined weekly cohorts (calibration licence).

What is new, and only mechanical:
1. COMPOUNDED calendar-time attribution on REAL sessions. The calibration simulated additive returns on uniform 5-session weeks;
   real cohorts earn C[exit]/C[entry] - 1 and real weeks have 3-5 sessions. A cohort's return telescopes exactly into
   sum_s (C[s] - C[s-1]) / C[entry], so each session's contribution is attributed to the calendar week containing it with weights
   a = w / C[entry]; `attribute_compounded` equals v4's `calendar_time_series` on uniform additive data (tested) and the sum of the
   weekly series equals the sum of the signal-date statistic on every input (asserted, raises otherwise).
2. An outcome firewall. Feature construction never touches a close after the signal date. Every outcome read goes through
   `read_outcomes`, which refuses without an `OutcomePermit`; a permit is issued only by `authorize`, which requires an owner
   authorization record pinning this harness's file hashes and every input identity. No such record exists in the repository.
   `Counters.outcomeReads` is incremented at the call site, so "no outcome was read" is a measured fact, not a flag.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from pipeline import us_h63_inference_calibration as CAL
from pipeline.alpha_inference_calibration_v4 import calendar_time_sn_interval

CONTRACT = "US_CASH_PROFITABILITY_EXPLORATORY_V1"
STUDY_ID = "us-cash-profitability-signal-v1"
EVIDENCE_CLASS = "EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_US_HISTORY"
HORIZON = 63
SN_CRITICAL_VALUE = 28.31
NEAR_ZERO_TOLERANCE = 1e-12
MIN_NAMES_PER_DATE = 150
MIN_DEFINED_WEEKS = 260
MAX_UNRESOLVED_SHARE = 0.10        # protocol decisionRules.inconclusive: "too many UNRESOLVED dates (> 10%)"
EXCLUDED_SECTORS = ("Financials", "Real Estate")
FEATURE = "cashOperatingProfitability"
CONTROLS = ("logTradedValue63", "mom121", "vol252", "operatingProfitabilityToAssets")

ABANDON = "ABANDON_BEFORE_PROSPECTIVE_COLLECTION"
CONTINUE = "CONTINUE_TO_PROSPECTIVE_REGISTRATION_REVIEW"
NOT_EVALUABLE = "NOT_EVALUABLE"


@dataclass
class Counters:
    featureBuilds: int = 0
    outcomeReads: int = 0
    intervalComputations: int = 0

    def as_dict(self) -> dict[str, int]:
        return {"featureBuilds": self.featureBuilds, "outcomeReads": self.outcomeReads,
                "intervalComputations": self.intervalComputations}


@dataclass(frozen=True)
class OutcomePermit:
    authorizationSha256: str
    _token: object = field(repr=False, compare=False, default=None)


_PERMIT_TOKEN = object()


class OutcomeAccessRefused(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def authorize(authorization_path: Path, expected: dict[str, str]) -> OutcomePermit:
    """An outcome permit, only for an owner authorization that pins exactly the expected identities."""
    path = Path(authorization_path)
    if not path.exists():
        raise OutcomeAccessRefused("NO_OWNER_AUTHORIZATION: " + str(path))
    record = json.loads(path.read_text())
    if record.get("contract") != CONTRACT or record.get("authorizes") != "ONE_EXPLORATORY_EXECUTION":
        raise OutcomeAccessRefused("AUTHORIZATION_WRONG_CONTRACT_OR_SCOPE")
    pinned = record.get("pinnedIdentities") or {}
    mismatched = sorted(k for k, v in expected.items() if pinned.get(k) != v)
    if mismatched or set(pinned) != set(expected):
        raise OutcomeAccessRefused("AUTHORIZATION_IDENTITY_MISMATCH: " + ",".join(mismatched or sorted(set(pinned) ^ set(expected))))
    return OutcomePermit(sha256_file(path), _PERMIT_TOKEN)


# --------------------------------------------------------------------------
# cohorts (signal-date information only)
# --------------------------------------------------------------------------
def finite(x) -> bool:
    return x is not None and isinstance(x, (int, float)) and bool(np.isfinite(x))


def complete_case(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows outside Financials/Real Estate with a sector label, the feature and every control."""
    return [r for r in rows if r.get("sector") not in EXCLUDED_SECTORS and r.get("sector") not in (None, "UNCLASSIFIED")
            and finite(r.get(FEATURE)) and all(finite(r.get(c)) for c in CONTROLS)]


def cohort_weights(rows: list[dict[str, Any]], counters: Counters | None = None) -> dict[str, Any]:
    """Gross-2 residualised weights for one signal date, or an undefined cohort below the name floor."""
    if counters is not None:
        counters.featureBuilds += 1
    cc = sorted(complete_case(rows), key=lambda r: r["ticker"])
    if len(cc) < MIN_NAMES_PER_DATE:
        return {"defined": False, "reason": "BELOW_MIN_NAMES_PER_DATE", "names": len(cc), "tickers": [], "weights": np.zeros(0)}
    n = len(cc)
    available = np.ones(n, dtype=bool)
    sectors_raw = [r["sector"] for r in cc]
    codes = {s: k for k, s in enumerate(sorted(set(sectors_raw)))}
    sectors = np.array([codes[s] for s in sectors_raw])
    feature_rank = CAL.centred_ranks(np.array([r[FEATURE] for r in cc], dtype=float), available)
    control_ranks = np.column_stack([CAL.centred_ranks(np.array([r[c] for r in cc], dtype=float), available) for c in CONTROLS])
    weights = CAL.residual_weights(feature_rank, control_ranks, sectors, available)
    return {"defined": True, "reason": None, "names": n, "tickers": [r["ticker"] for r in cc], "weights": weights}


def entry_exit(sessions: list[str], signal_date: str) -> tuple[int, int]:
    """Entry = close of the first session AFTER the signal date (no same-close execution); exit = entry + 63 sessions."""
    idx = int(np.searchsorted(np.array(sessions), signal_date, side="right"))
    return idx, idx + HORIZON


def iso_week_ordinals(sessions: list[str]) -> np.ndarray:
    """Calendar week of each session (Monday-based ISO week), as consecutive ordinals from 0."""
    keys = [dt.date.fromisoformat(s).isocalendar()[:2] for s in sessions]
    order = {k: i for i, k in enumerate(sorted(set(keys)))}
    return np.array([order[k] for k in keys])


# --------------------------------------------------------------------------
# outcomes (permit only)
# --------------------------------------------------------------------------
def read_outcomes(permit: OutcomePermit, reader, counters: Counters):
    """The ONLY way to obtain post-signal closes. `reader` is called once and returns the close matrix."""
    if not isinstance(permit, OutcomePermit) or permit._token is not _PERMIT_TOKEN:
        raise OutcomeAccessRefused("NO_OUTCOME_PERMIT")
    counters.outcomeReads += 1
    return reader()


def attribute_compounded(close: np.ndarray, weights: np.ndarray, entry: np.ndarray, defined: np.ndarray,
                         week_of: np.ndarray, horizon: int = HORIZON, *, compounded: bool = True
                         ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(D, x, S): calendar-week series, exposure profile, and signal-date statistic of defined cohorts.

    close[s, i] is the (total-return) close of name i at global session s; weights[t, i] the gross-2 weights of cohort t (zero for
    names not held); entry[t] its entry session; a cohort is held over sessions entry+1 .. entry+horizon. Cohorts must be defined
    only where every held name has a finite positive close at entry and exit (`execute_study` decides; interior gaps carried forward).
    `compounded=False` is the additive special case (a = w, S = w . (C[exit] - C[entry])), used only to prove equality with v4.
    """
    cohorts, names = weights.shape
    sessions = close.shape[0]
    a = np.zeros_like(weights)
    contrib = np.zeros(sessions)
    active = np.zeros(sessions)
    s_values = np.full(cohorts, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        delta = np.vstack([np.zeros((1, names)), np.diff(close, axis=0)])
    for t in range(cohorts):
        if not defined[t]:
            continue
        e = int(entry[t])
        held = weights[t] != 0
        if e + horizon >= sessions or not np.all(np.isfinite(close[e:e + horizon + 1][:, held])):
            raise ValueError("UNRESOLVED_COHORT_MARKED_DEFINED")
        a[t, held] = weights[t, held] / close[e, held] if compounded else weights[t, held]
        window = slice(e + 1, e + horizon + 1)
        contrib[window] += delta[window][:, held] @ a[t, held]
        active[window] += 1.0
        s_values[t] = float(weights[t, held] @ (close[e + horizon, held] / close[e, held] - 1.0 if compounded
                                                else close[e + horizon, held] - close[e, held]))
    weeks = int(week_of.max()) + 1
    d = np.bincount(week_of, weights=contrib, minlength=weeks)
    x = np.bincount(week_of, weights=active, minlength=weeks) / horizon
    first, last = int(week_of[np.flatnonzero(active)[0]]) if active.any() else 0, int(week_of[np.flatnonzero(active)[-1]]) if active.any() else -1
    d, x = d[first:last + 1], x[first:last + 1]
    total = float(np.nansum(s_values))
    if abs(float(d.sum()) - total) > 1e-9 * max(1.0, float(np.nansum(np.abs(s_values)))):
        raise RuntimeError("ATTRIBUTION_IDENTITY_BROKEN")
    return d, x, s_values


def evaluate(d: np.ndarray, x: np.ndarray, defined_weeks: int, counters: Counters) -> dict[str, Any]:
    """The frozen decision: CT_SN one-sided 95% bounds; futility screen reading only."""
    if defined_weeks < MIN_DEFINED_WEEKS:
        return {"status": NOT_EVALUABLE, "reason": "FEWER_THAN_260_DEFINED_WEEKLY_COHORTS", "definedWeeks": defined_weeks}
    counters.intervalComputations += 1
    interval = calendar_time_sn_interval(d, x, SN_CRITICAL_VALUE, NEAR_ZERO_TOLERANCE)
    if interval is None:
        return {"status": NOT_EVALUABLE, "reason": "INTERVAL_UNDEFINED", "definedWeeks": defined_weeks}
    screen = ABANDON if interval["upper"] <= 0 else CONTINUE
    statistical = "SUPPORTED_IN_DEVELOPMENT" if interval["lower"] > 0 else ("REFUTED_IN_DEVELOPMENT" if interval["upper"] <= 0 else "INCONCLUSIVE")
    return {"status": screen, "developmentReading": statistical, "definedWeeks": defined_weeks,
            "estimatePerH63": interval["estimate"], "lowerOneSided95": interval["lower"], "upperOneSided95": interval["upper"],
            "interpretation": "exploratory futility screen on outcome-exposed, survivor-conditioned history; never confirmation"}


def forward_fill(close: np.ndarray) -> np.ndarray:
    """Carry the last close forward over interior gaps (a gap cannot change a telescoped cohort return)."""
    out = close.copy()
    for s in range(1, out.shape[0]):
        gap = ~np.isfinite(out[s])
        out[s, gap] = out[s - 1, gap]
    return out


def execute_study(cohorts: list[dict[str, Any]], sessions: list[str], last_session: str, close_reader,
                  permit: OutcomePermit, counters: Counters) -> dict[str, Any]:
    """The one-shot exploratory computation. `cohorts` hold signal-date facts only (date, defined, heldTickers, heldWeights).

    `close_reader(tickers, session_dates)` returns a float matrix (sessions x tickers; NaN where no close) and is called exactly
    once, through `read_outcomes`. A matured cohort is UNRESOLVED (undefined, counted) when a held name has no close on its entry
    or exit session; interior gaps are carried forward.
    """
    last_idx = sessions.index(last_session)
    rows = []
    for c in cohorts:
        entry, exit_ = entry_exit(sessions, c["date"])
        if c["defined"] and exit_ <= last_idx:
            rows.append((c, entry))
    if not rows:
        return {"status": NOT_EVALUABLE, "reason": "NO_MATURED_DEFINED_COHORT"}
    tickers = sorted({t for c, _ in rows for t in c["heldTickers"]})
    col = {t: k for k, t in enumerate(tickers)}
    first = min(e for _, e in rows)
    window = sessions[first:last_idx + 1]
    raw = np.asarray(read_outcomes(permit, lambda: close_reader(tickers, window), counters), dtype=float)
    if raw.shape != (len(window), len(tickers)):
        raise ValueError("CLOSE_MATRIX_SHAPE")
    weights = np.zeros((len(rows), len(tickers)))
    entry = np.zeros(len(rows), dtype=int)
    defined = np.ones(len(rows), dtype=bool)
    unresolved = []
    for k, (c, e) in enumerate(rows):
        idx = [col[t] for t in c["heldTickers"]]
        weights[k, idx] = c["heldWeights"]
        entry[k] = e - first
        ends = raw[[e - first, e - first + HORIZON]][:, idx]
        if not (np.isfinite(ends).all() and (ends > 0).all()):
            defined[k] = False
            unresolved.append(c["date"])
    close = forward_fill(raw)
    week_of = iso_week_ordinals(window)
    d, x, s_values = attribute_compounded(close, weights, entry, defined, week_of)
    if len(unresolved) > MAX_UNRESOLVED_SHARE * len(rows):
        result = {"status": NOT_EVALUABLE, "reason": "MORE_THAN_10_PCT_UNRESOLVED_DATES", "definedWeeks": int(defined.sum())}
    else:
        result = evaluate(d, x, int(defined.sum()), counters)
    result.update({"maturedDefinedCohorts": len(rows), "unresolvedCohorts": len(unresolved), "unresolvedDates": unresolved,
                   "calendarWeeks": int(len(d)), "signalDateMean": float(np.nanmean(s_values)) if defined.any() else None,
                   "units": "fraction per 63 sessions, $1 long / $1 short; SPY cancels because weights sum to zero within sector"})
    return result
