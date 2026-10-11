"""Research-only adapter: one forecast set, judged against SPY AND QQQ.

NOT A NEW DISCOVERY CHANNEL
---------------------------
On one date, horizon and eligible universe,

    alpha_SPY(i,t) = R(i,t) - R_SPY(t)
    alpha_QQQ(i,t) = R(i,t) - R_QQQ(t)
    alpha_QQQ(i,t) = alpha_SPY(i,t) - [R_QQQ(t) - R_SPY(t)]

and the bracket is the same number for every security on that date. So within
a date the ordering, the Spearman rank IC and any rank-based top/bottom group
are IDENTICAL under both benchmarks. Swapping the benchmark ticker can never
manufacture stock-picking evidence, and this module computes rank statistics
ONCE and labels them benchmark-invariant rather than reporting them twice as
if they were two findings.

What the benchmark does change is the LEVEL: the expected excess return, the
economic hurdle a selection must clear after costs, the share of names with a
positive sign, and therefore whether replacing an ETF with stocks pays. Those
are reported per benchmark, on one common date mask, with the benchmark spread
carried as its own date-level series — never multiplied into N stock-level
"observations".

Nothing here reads a stock-level outcome to choose a feature, retrains a
model, or writes a production artifact. ``weekly_decision`` and its receipts
do not import it.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .us_dual_benchmark_data import (OFFICIAL_US_BENCHMARK, US_GROWTH_BENCHMARK,
                                     US_MARKET_BENCHMARK)

ROLE_MARKET = "US_MARKET_BENCHMARK"
ROLE_GROWTH = "US_GROWTH_BENCHMARK"
INTEGRITY_PASS = "PASS"

P0_SPY = "P0_SPY"
P0_QQQ = "P0_QQQ"
P1_STOCKS = "P1_STOCKS"
MAX_SELECTED = 5
# Residual policy must be DECLARED by the study; there is no default, so a
# residual cannot be picked after seeing which ETF did better.
RESIDUAL_CHOICES = (US_MARKET_BENCHMARK, US_GROWTH_BENCHMARK, "USD_CASH")


@dataclass(frozen=True)
class BenchmarkIdentity:
    role: str
    ticker: str
    snapshotSha256: str
    basis: str
    vendor: str
    integrityStatus: str
    integrityNotes: tuple = ()

    def __post_init__(self):
        expected = {ROLE_MARKET: US_MARKET_BENCHMARK, ROLE_GROWTH: US_GROWTH_BENCHMARK}
        if expected.get(self.role) != self.ticker:
            raise ValueError(f"BENCHMARK_ROLE_MISMATCH {self.role}={self.ticker}")


@dataclass(frozen=True)
class StudyDesign:
    """Everything a registered study fixes before it reads an outcome."""
    studyId: str
    universeId: str
    horizonSessions: int
    residualAsset: str
    stockRoundTripCostBps: float
    etfRoundTripCostBps: float
    maxSelected: int = MAX_SELECTED
    notes: tuple = field(default_factory=tuple)

    def __post_init__(self):
        if self.residualAsset not in RESIDUAL_CHOICES:
            raise ValueError(f"RESIDUAL_ASSET_NOT_DECLARED: {self.residualAsset!r}")
        if not 0 <= self.maxSelected <= MAX_SELECTED:
            raise ValueError("MAX_SELECTED_OUT_OF_RANGE")
        if self.horizonSessions <= 0:
            raise ValueError("HORIZON_REQUIRED")


# --------------------------------------------------------------------------- #
# Forward returns on one calendar
# --------------------------------------------------------------------------- #
def forward_returns(close: pd.Series, anchors: pd.DatetimeIndex, horizon: int,
                    sessions: pd.DatetimeIndex) -> pd.Series:
    """R over [anchor, anchor + horizon sessions] on ONE session calendar.

    Missing at either end is NaN — never zero, never a nearby close.
    """
    sessions = pd.DatetimeIndex(sessions)
    pos = sessions.get_indexer(anchors)
    out = pd.Series(np.nan, index=anchors, dtype=float)
    for anchor, p in zip(anchors, pos):
        if p < 0 or p + horizon >= len(sessions):
            continue
        start, end = sessions[p], sessions[p + horizon]
        a, b = close.get(start, np.nan), close.get(end, np.nan)
        if np.isfinite(a) and np.isfinite(b) and a > 0 and b > 0:
            out.loc[anchor] = b / a - 1
    return out


def common_date_mask(spy_fwd: pd.Series, qqq_fwd: pd.Series) -> pd.DatetimeIndex:
    """Dates on which BOTH benchmark outcomes exist. One mask for every comparison."""
    both = pd.concat([spy_fwd, qqq_fwd], axis=1).dropna()
    return pd.DatetimeIndex(both.index)


def benchmark_spread(spy_fwd: pd.Series, qqq_fwd: pd.Series) -> pd.Series:
    """R_QQQ(t) - R_SPY(t): one number per date, shared by every security."""
    return (qqq_fwd - spy_fwd).rename("qqqMinusSpy")


def relative_returns(stock_fwd: pd.DataFrame, bench_fwd: pd.Series) -> pd.DataFrame:
    """Rows = dates, columns = securities. NaN stays NaN."""
    return stock_fwd.sub(bench_fwd.reindex(stock_fwd.index), axis=0)


def identity_error(stock_fwd: pd.DataFrame, spy_fwd: pd.Series, qqq_fwd: pd.Series) -> float:
    """max |alpha_QQQ - (alpha_SPY - spread)| over finite cells. Should be ~1e-16."""
    a_spy = relative_returns(stock_fwd, spy_fwd)
    a_qqq = relative_returns(stock_fwd, qqq_fwd)
    implied = a_spy.sub(benchmark_spread(spy_fwd, qqq_fwd).reindex(a_spy.index), axis=0)
    diff = (a_qqq - implied).abs().to_numpy()
    diff = diff[np.isfinite(diff)]
    return float(diff.max()) if diff.size else 0.0


def rank_ic_by_date(predictions: pd.DataFrame, outcome: pd.DataFrame, min_names: int = 5) -> pd.Series:
    """Within-date Spearman between forecast and outcome on the jointly observed names."""
    out = {}
    for date in predictions.index.intersection(outcome.index):
        pair = pd.concat([predictions.loc[date], outcome.loc[date]], axis=1).dropna()
        if len(pair) < min_names:
            continue
        ranks = pair.rank()
        out[date] = float(ranks.iloc[:, 0].corr(ranks.iloc[:, 1]))
    return pd.Series(out, dtype=float).sort_index()


def top_k(predictions: pd.Series, k: int) -> list[str]:
    """Deterministic top-k by forecast; ties broken by ticker. Unpriceable names stay eligible."""
    clean = predictions.dropna()
    order = sorted(clean.items(), key=lambda kv: (-kv[1], kv[0]))
    return [ticker for ticker, _ in order[:k]]


# --------------------------------------------------------------------------- #
# Cost hurdles
# --------------------------------------------------------------------------- #
def replacement_hurdle(design: StudyDesign) -> float:
    """Return a stock book must add over the ETF it REPLACES just to break even.

    Both benchmarks share it: the incremental friction is stock trading minus
    the ETF trading it avoids. It is a fraction of the horizon return.
    """
    return (design.stockRoundTripCostBps - design.etfRoundTripCostBps) / 1e4


def per_benchmark_economics(selected_fwd: pd.DataFrame, spy_fwd: pd.Series, qqq_fwd: pd.Series,
                            hurdle: float) -> dict:
    """Equal-weight selected book, net excess vs each benchmark on the common mask.

    A date on which any selected name has no outcome is NOT measurable: the
    book is not renormalised over survivors and the missing name is not zero.
    """
    mask = common_date_mask(spy_fwd, qqq_fwd)
    rows = selected_fwd.reindex(mask)
    complete = rows.notna().all(axis=1) & (rows.shape[1] > 0)
    book = rows[complete].mean(axis=1)
    out = {"commonDates": int(len(mask)), "measurableDates": int(complete.sum()),
           "unmeasurableDates": int((~complete).sum()), "hurdle": hurdle}
    for label, bench in ((US_MARKET_BENCHMARK, spy_fwd), (US_GROWTH_BENCHMARK, qqq_fwd)):
        net = book - bench.reindex(book.index) - hurdle
        out[label] = {"meanNetExcess": float(net.mean()) if len(net) else None,
                      "positiveNetShare": float((net > 0).mean()) if len(net) else None}
    if len(book):
        spread = benchmark_spread(spy_fwd, qqq_fwd).reindex(book.index)
        out["meanSpreadQqqMinusSpy"] = float(spread.mean())
        out["identityCheck"] = float(abs(out[US_MARKET_BENCHMARK]["meanNetExcess"]
                                         - out[US_GROWTH_BENCHMARK]["meanNetExcess"]
                                         - spread.mean()))
    return out


def paired_evaluation(design: StudyDesign, spy: BenchmarkIdentity, qqq: BenchmarkIdentity,
                      predictions: pd.DataFrame, stock_fwd: pd.DataFrame,
                      spy_fwd: pd.Series, qqq_fwd: pd.Series) -> dict:
    """The adapter's one entry point for a future registered study.

    ``predictions`` must be fixed before ``stock_fwd`` exists; the adapter
    cannot check that, so the study's registration must. It only refuses what
    it can see: mismatched calendars, a missing residual policy, an undeclared
    benchmark integrity state.
    """
    for ident in (spy, qqq):
        if not isinstance(ident, BenchmarkIdentity):
            raise TypeError("BENCHMARK_IDENTITY_REQUIRED")
    mask = common_date_mask(spy_fwd, qqq_fwd)
    preds = predictions.reindex(mask)
    outcome = stock_fwd.reindex(mask)
    ic_spy = rank_ic_by_date(preds, relative_returns(outcome, spy_fwd))
    ic_qqq = rank_ic_by_date(preds, relative_returns(outcome, qqq_fwd))
    max_ic_gap = float((ic_spy - ic_qqq).abs().max()) if len(ic_spy) else 0.0
    selections = {d: top_k(preds.loc[d], design.maxSelected) for d in mask}
    selected = pd.DataFrame({d: outcome.loc[d].reindex(names).reset_index(drop=True)
                             for d, names in selections.items() if names}).T
    economics = per_benchmark_economics(selected, spy_fwd, qqq_fwd, replacement_hurdle(design)) \
        if len(selected) else {"commonDates": int(len(mask)), "measurableDates": 0}
    headline_ok = (spy.integrityStatus == INTEGRITY_PASS and qqq.integrityStatus == INTEGRITY_PASS)
    return {
        "studyId": design.studyId, "universeId": design.universeId,
        "horizonSessions": design.horizonSessions, "residualAsset": design.residualAsset,
        "officialBenchmark": OFFICIAL_US_BENCHMARK,
        "benchmarks": {spy.role: _identity(spy), qqq.role: _identity(qqq)},
        "commonDates": int(len(mask)),
        "rankStatistics": {
            "benchmarkInvariant": True,
            "meanRankIC": float(ic_spy.mean()) if len(ic_spy) else None,
            "datesWithIC": int(len(ic_spy)),
            "maxAbsIcDifferenceAcrossBenchmarks": max_ic_gap,
            "note": "computed once; a benchmark change cannot alter within-date ranks"},
        "economics": economics,
        "inference": {"sameDateClustering": "DATE_LEVEL",
                      "benchmarkSpreadIsDateLevel": True,
                      "note": "per-date book returns are the unit; securities are not pooled across dates"},
        "headlineEligible": headline_ok,
        "headlineBlockers": [f"{i.ticker}:{i.integrityStatus}" for i in (spy, qqq)
                             if i.integrityStatus != INTEGRITY_PASS],
    }


def _identity(ident: BenchmarkIdentity) -> dict:
    return {"ticker": ident.ticker, "snapshotSha256": ident.snapshotSha256, "basis": ident.basis,
            "vendor": ident.vendor, "integrityStatus": ident.integrityStatus,
            "integrityNotes": list(ident.integrityNotes)}


# --------------------------------------------------------------------------- #
# Portfolio alternatives
# --------------------------------------------------------------------------- #
def alternative_paths(design: StudyDesign, dates: pd.DatetimeIndex, period_returns: pd.DataFrame,
                      selections: dict, stock_weight: float) -> dict:
    """Growth of 1 for P0_SPY, P0_QQQ and P1_STOCKS over ONE evaluation population.

    ``period_returns`` has a column per security plus SPY, QQQ and USD_CASH, one
    row per holding period ending at ``dates``. ``selections[date]`` lists 0-5
    names held over the period starting at that date; ``stock_weight`` of the
    book goes to them equally and the rest to the DECLARED residual. A period
    in which a held name has no return ends the path as unmeasurable rather
    than being skipped — skipping would give P1 a different population than P0.
    """
    if not 0 <= stock_weight <= 1:
        raise ValueError("STOCK_WEIGHT_OUT_OF_RANGE")
    required = [US_MARKET_BENCHMARK, US_GROWTH_BENCHMARK, design.residualAsset]
    missing = [c for c in required if c not in period_returns.columns]
    if missing:
        raise ValueError(f"PASSIVE_RETURNS_MISSING {missing}")
    rows = period_returns.reindex(dates)
    if rows[required].isna().any().any():
        raise ValueError("PASSIVE_RETURN_GAP_IN_EVALUATION_POPULATION")
    nav = {P0_SPY: [1.0], P0_QQQ: [1.0], P1_STOCKS: [1.0]}
    status = "COMPLETE"
    for date in dates:
        names = list(selections.get(date, []))
        if len(names) > design.maxSelected:
            raise ValueError("TOO_MANY_SELECTED")
        nav[P0_SPY].append(nav[P0_SPY][-1] * (1 + rows.loc[date, US_MARKET_BENCHMARK]))
        nav[P0_QQQ].append(nav[P0_QQQ][-1] * (1 + rows.loc[date, US_GROWTH_BENCHMARK]))
        residual = rows.loc[date, design.residualAsset]
        if names:
            picks = rows.loc[date, names] if set(names) <= set(rows.columns) else pd.Series(np.nan, index=names)
            if picks.isna().any():
                status = f"UNMEASURABLE_HELD_NAME_AT {date.strftime('%Y-%m-%d')}"
                break
            r = stock_weight * float(picks.mean()) + (1 - stock_weight) * residual
        else:
            r = residual
        nav[P1_STOCKS].append(nav[P1_STOCKS][-1] * (1 + r))
    complete = status == "COMPLETE"
    return {"status": status, "periods": int(len(dates)), "residualAsset": design.residualAsset,
            "finalNav": {k: (round(v[-1], 10) if complete else None) for k, v in nav.items()},
            "samePopulation": True}


def canonical_digest(payload) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False,
                     separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()
