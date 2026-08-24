"""What actually happened after each frozen historical signal.

Signals and outcomes are computed by different code, stored in different files
and joined only by signal id. That separation is not tidiness — it is the reason
a model change can never rewrite history: ``historical-signals.jsonl`` is
append-only and immutable, while ``historical-outcomes.jsonl`` is derived and
may be recomputed as more future arrives.

An outcome is published only when the full horizon has elapsed *in the price
data*. There are no partial 126-day returns extrapolated from 80 days, because
a truncated horizon is systematically biased toward whatever the market did
recently.

The metric set is deliberately wider than "did it go up". A signal that earned
+6% after a -22% intra-period drawdown is not the same signal as one that earned
+6% in a straight line, and a position sizer that cannot tell them apart will
size both wrong.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .market_dates import normalize_daily_series

HORIZONS = (21, 63, 126, 252)

EVIDENCE_HISTORICAL = "HISTORICAL_OOS"
EVIDENCE_PROSPECTIVE = "PROSPECTIVE_PAPER"
EVIDENCE_LIVE = "LIVE_VALIDATED"
EVIDENCE_CLASSES = (EVIDENCE_HISTORICAL, EVIDENCE_PROSPECTIVE, EVIDENCE_LIVE)


def _round(value, digits=6):
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return round(f, digits) if math.isfinite(f) else None


def _series_metrics(path: np.ndarray) -> dict:
    """Risk taken *along the way*, not just the endpoint."""
    if len(path) < 2:
        return {"realizedVol": None, "downsideVol": None, "cvar95": None, "maxDrawdown": None}
    rets = path[1:] / path[:-1] - 1.0
    rets = rets[np.isfinite(rets)]
    if not len(rets):
        return {"realizedVol": None, "downsideVol": None, "cvar95": None, "maxDrawdown": None}
    peak = np.maximum.accumulate(path)
    drawdown = float(np.min(path / peak - 1.0))
    vol = float(np.std(rets, ddof=1) * math.sqrt(252)) if len(rets) > 1 else None
    neg = rets[rets < 0]
    downside = (float(math.sqrt(float(np.mean(neg ** 2))) * math.sqrt(252))
                if len(neg) >= 2 else None)
    tail_n = max(1, int(math.ceil(len(rets) * 0.05)))
    cvar = float(np.mean(np.sort(rets)[:tail_n]))
    return {"realizedVol": vol, "downsideVol": downside, "cvar95": cvar,
            "maxDrawdown": drawdown}


def _round_trip_cost(region: str, cost_policy: dict | None) -> float:
    """One entry + one exit, in return units.

    Deliberately charged in full on a single-name signal: the historical ledger
    exists to answer "was there an edge after paying to take it", and the
    cheapest possible cost assumption is the classic way a backtest keeps an
    edge that trading destroys.
    """
    policy = ((cost_policy or {}).get(region) or {})
    commission = float(policy.get("commissionBps", 5.0))
    spread = float(policy.get("spreadBps", 12.0))
    sell_tax = float(policy.get("sellTaxBps", 20.0 if region == "KR" else 3.0))
    return (commission * 2.0 + spread * 2.0 + sell_tax) / 10_000.0


def benchmark_session_preflight(prices: dict[str, pd.DataFrame],
                                universe: dict[str, list[str]],
                                benchmarks: dict[str, str], *,
                                start: str, end: str | None = None,
                                horizon: int = 126,
                                min_history_rows: int = 273,
                                min_coverage_pct: float = 95.0) -> dict:
    """Check exact regional benchmark sessions before the expensive replay.

    This evaluates every stock window that could mature inside the downloaded
    panel, after the model's minimum-history boundary and within the requested
    replay date range.  It deliberately uses the same normalized dates and
    exact-match rule as :func:`compute_outcomes`.
    """
    start_date = np.datetime64(pd.Timestamp(start).normalize(), "ns")
    end_date = (np.datetime64(pd.Timestamp(end).normalize(), "ns")
                if end else None)
    regions: dict[str, dict] = {}
    failures = []

    for region, tickers in universe.items():
        benchmark = benchmarks.get(region)
        benchmark_frame = prices.get(benchmark) if benchmark else None
        benchmark_dates = np.array([], dtype="datetime64[ns]")
        if benchmark_frame is not None and "Close" in benchmark_frame:
            clean = pd.to_numeric(benchmark_frame["Close"], errors="coerce").dropna()
            if len(clean):
                clean = normalize_daily_series(clean)
                benchmark_dates = clean.index.to_numpy(dtype="datetime64[ns]")

        candidates = matched = 0
        samples: list[dict] = []
        for ticker in tickers:
            frame = prices.get(ticker)
            if frame is None or "Close" not in frame:
                continue
            close = pd.to_numeric(frame["Close"], errors="coerce").dropna()
            if len(close) <= horizon:
                continue
            close = normalize_daily_series(close)
            dates = close.index.to_numpy(dtype="datetime64[ns]")
            first = max(0, int(min_history_rows) - 1)
            last = len(dates) - int(horizon)
            if first >= last:
                continue
            positions = np.arange(first, last)
            starts = dates[positions]
            ends = dates[positions + int(horizon)]
            in_range = starts >= start_date
            if end_date is not None:
                in_range &= starts <= end_date
            starts, ends = starts[in_range], ends[in_range]
            if not len(starts):
                continue
            exact = np.isin(starts, benchmark_dates) & np.isin(ends, benchmark_dates)
            candidates += int(len(exact))
            matched += int(exact.sum())
            if len(samples) < 5:
                for idx in np.flatnonzero(~exact)[:5 - len(samples)]:
                    samples.append({
                        "ticker": ticker,
                        "startDate": pd.Timestamp(starts[idx]).strftime("%Y-%m-%d"),
                        "endDate": pd.Timestamp(ends[idx]).strftime("%Y-%m-%d"),
                        "benchmarkHasStart": bool(np.isin(starts[idx], benchmark_dates)),
                        "benchmarkHasEnd": bool(np.isin(ends[idx], benchmark_dates)),
                    })

        coverage_pct = round(matched / candidates * 100, 4) if candidates else None
        row = {
            "benchmark": benchmark,
            "benchmarkSessions": int(len(benchmark_dates)),
            "candidateWindows": candidates,
            "matchedWindows": matched,
            "missingWindows": max(0, candidates - matched),
            "coveragePct": coverage_pct,
            "missingSamples": samples,
        }
        regions[region] = row
        if candidates <= 0 or coverage_pct is None or coverage_pct < min_coverage_pct:
            failures.append({
                "region": region,
                **row,
                "minimumCoveragePct": float(min_coverage_pct),
                "reason": ("no_candidate_windows" if candidates <= 0
                           else "benchmark_coverage_below_threshold"),
            })

    return {
        "eligible": bool(regions) and not failures,
        "horizon": int(horizon),
        "minimumCoveragePct": float(min_coverage_pct),
        "regions": regions,
        "failures": failures,
    }


def compute_outcomes(signals: list[dict], prices: dict[str, pd.DataFrame],
                     benchmarks: dict[str, pd.Series] | None = None,
                     *, cost_policy: dict | None = None,
                     horizons: tuple[int, ...] = HORIZONS,
                     evidence_class: str = EVIDENCE_HISTORICAL) -> list[dict]:
    """Forward outcomes for matured signals only.

    The benchmark leg is computed on the *same* start and end calendar dates as
    the stock leg. A KR name compared against a US session that happened to be
    nearby is not an excess return, it is a currency-and-timezone artifact.
    """
    benchmarks = benchmarks or {}
    # Converted once. Resolving a signal date against a pandas index costs
    # milliseconds; a decade-long replay produces hundreds of thousands of
    # signals, so a binary search over a sorted NumPy array is the difference
    # between minutes and an hour.
    closes: dict[str, pd.Series] = {}
    arrays: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for ticker, frame in (prices or {}).items():
        if frame is None or "Close" not in frame:
            continue
        series = pd.to_numeric(frame["Close"], errors="coerce").dropna()
        if not len(series):
            continue
        series = normalize_daily_series(series)
        closes[ticker] = series
        arrays[ticker] = (series.index.to_numpy(dtype="datetime64[ns]"),
                          series.to_numpy(dtype=float))
    bench_arrays: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for name, series in benchmarks.items():
        if series is None:
            continue
        clean = pd.to_numeric(series, errors="coerce").dropna()
        if len(clean):
            clean = normalize_daily_series(clean)
            bench_arrays[name] = (clean.index.to_numpy(dtype="datetime64[ns]"),
                                  clean.to_numpy(dtype=float))
    cost_cache: dict[str, float] = {}

    results: list[dict] = []
    for signal in signals:
        ticker = signal.get("ticker")
        entry = arrays.get(ticker)
        date = signal.get("date") or signal.get("asOf")
        if entry is None or not date:
            continue
        stock_dates, stock_close = entry
        entry_idx = int(np.searchsorted(stock_dates, np.datetime64(pd.Timestamp(date).normalize(), "ns"),
                                        side="right")) - 1
        if entry_idx < 0:
            continue
        entry_px = float(stock_close[entry_idx])
        if not math.isfinite(entry_px) or entry_px <= 0:
            continue
        region = signal.get("region") or "UNKNOWN"
        bench = bench_arrays.get(signal.get("benchmark"))
        if region not in cost_cache:
            cost_cache[region] = _round_trip_cost(region, cost_policy)
        cost = cost_cache[region]

        record = {
            "id": signal.get("id"),
            "date": date,
            "asOf": signal.get("asOf") or date,
            "ticker": ticker,
            "region": region,
            "benchmark": signal.get("benchmark"),
            "sector": signal.get("sector"),
            "evidenceClass": evidence_class,
            "modelVersion": signal.get("modelVersion"),
            "replayVersion": signal.get("replayVersion"),
            "featureVersion": signal.get("featureVersion"),
            "dataVersion": signal.get("dataVersion"),
            "alphaPercentile": signal.get("alphaPercentile"),
            "longTermResearchView": signal.get("longTermResearchView"),
            "entryState": signal.get("entryState"),
            "macroRegime": signal.get("macroRegime"),
            "sectorRotation": signal.get("sectorRotation"),
            "pit": signal.get("pit"),
            "transactionCostPct": round(cost * 100, 4),
            "horizons": {},
        }
        for horizon in horizons:
            end_idx = entry_idx + horizon
            if end_idx >= len(stock_close):
                continue           # not matured — no partial outcomes, ever
            path = stock_close[entry_idx:end_idx + 1]
            fwd = float(path[-1] / entry_px - 1.0)
            mfe = float(np.max(path) / entry_px - 1.0)
            mae = float(np.min(path) / entry_px - 1.0)
            metrics = _series_metrics(path)

            benchmark_return = None
            if bench is not None:
                bench_dates, bench_close = bench
                start_date, end_date = stock_dates[entry_idx], stock_dates[end_idx]
                # The benchmark must share the EXACT start and end sessions. A
                # nearby US session is not a valid comparison for a KR name.
                bi = int(np.searchsorted(bench_dates, start_date, side="left"))
                bj = int(np.searchsorted(bench_dates, end_date, side="left"))
                if (bi < len(bench_dates) and bj < len(bench_dates)
                        and bench_dates[bi] == start_date and bench_dates[bj] == end_date
                        and bench_close[bi] > 0):
                    benchmark_return = float(bench_close[bj] / bench_close[bi] - 1.0)
            excess = fwd - benchmark_return if benchmark_return is not None else None
            record["horizons"][str(horizon)] = {
                "absoluteReturn": _round(fwd),
                "benchmarkReturn": _round(benchmark_return),
                "excessReturn": _round(excess),
                "costAdjustedExcessReturn": _round(excess - cost) if excess is not None else None,
                "fwdReturn": _round(fwd),            # ledger-compatible alias
                "mfe": _round(mfe),
                "mae": _round(mae),
                "maxDrawdown": _round(metrics["maxDrawdown"]),
                "realizedVol": _round(metrics["realizedVol"]),
                "downsideVol": _round(metrics["downsideVol"]),
                "cvar95": _round(metrics["cvar95"]),
                "endDate": pd.Timestamp(stock_dates[end_idx]).strftime("%Y-%m-%d"),
            }
        if record["horizons"]:
            results.append(record)
    return results


# --------------------------------------------------------------------------- #
# Aggregation helpers (date-clustered, never one-row-per-name)
# --------------------------------------------------------------------------- #
def horizon_frame(outcomes: list[dict], horizon: int, *,
                  cost_adjusted: bool = False) -> pd.DataFrame:
    """Flatten matured outcomes at one horizon into a tidy frame."""
    key = "costAdjustedExcessReturn" if cost_adjusted else "excessReturn"
    rows = []
    for outcome in outcomes:
        payload = (outcome.get("horizons") or {}).get(str(horizon))
        if not payload or payload.get(key) is None:
            continue
        rows.append({
            "id": outcome.get("id"),
            "date": pd.Timestamp(outcome["date"]).normalize(),
            # A forward label is not observable on the signal date.  Probability
            # calibration uses this timestamp to admit the label only after the
            # full horizon has actually matured.
            "outcomeEndDate": (pd.Timestamp(payload["endDate"]).normalize()
                               if payload.get("endDate") else pd.NaT),
            "ticker": outcome.get("ticker"),
            "region": outcome.get("region") or "UNKNOWN",
            "sector": outcome.get("sector") or "Unclassified",
            "macroRegime": outcome.get("macroRegime"),
            "alphaPercentile": outcome.get("alphaPercentile"),
            "entryState": outcome.get("entryState"),
            "value": float(payload[key]),
            "excessReturn": float(payload["excessReturn"]) if payload.get("excessReturn") is not None else np.nan,
            "costAdjustedExcessReturn": (float(payload["costAdjustedExcessReturn"])
                                          if payload.get("costAdjustedExcessReturn") is not None else np.nan),
            "maxDrawdown": payload.get("maxDrawdown"),
            "cvar95": payload.get("cvar95"),
            "mfe": payload.get("mfe"),
            "mae": payload.get("mae"),
            "pitCoverage": float(((outcome.get("pit") or {}).get("pitCoverage")) or 0.0),
            "usableForCalibration": bool(((outcome.get("pit") or {})
                                          .get("usableForCalibration", True))),
        })
    if not rows:
        return pd.DataFrame(columns=["date", "ticker", "region", "sector", "value"])
    return pd.DataFrame(rows).sort_values(["date", "region", "ticker"], kind="mergesort")


class CoverageAccumulator:
    """Coverage counted one shard at a time.

    The ledger is stored in month shards precisely so a run never has to hold
    all of it at once; a coverage summary that demanded both full lists would
    put it straight back into memory. This keeps only date sets and counters —
    a few hundred dates regardless of how many records pass through.
    """

    def __init__(self, horizon: int = 126):
        self.horizon = horizon
        self.signals_recorded = 0
        self.signal_dates: set[pd.Timestamp] = set()
        self.signals_by_region: dict[str, int] = {}
        self.matured_signals = 0
        self.matured_dates: set[pd.Timestamp] = set()
        self.matured_by_horizon: dict[str, int] = {str(h): 0 for h in HORIZONS}
        self.absolute_by_region_horizon: dict[tuple[str, str], int] = {}
        self.benchmark_by_region_horizon: dict[tuple[str, str], int] = {}
        self.missing_benchmark_samples: dict[tuple[str, str], list[dict]] = {}

    def add_signals(self, signals: list[dict]) -> "CoverageAccumulator":
        for signal in signals:
            self.signals_recorded += 1
            region = signal.get("region") or "UNKNOWN"
            self.signals_by_region[region] = self.signals_by_region.get(region, 0) + 1
            if signal.get("date"):
                self.signal_dates.add(pd.Timestamp(signal["date"]).normalize())
        return self

    def add_outcomes(self, outcomes: list[dict]) -> "CoverageAccumulator":
        target = str(self.horizon)
        for outcome in outcomes:
            horizons = outcome.get("horizons") or {}
            region = outcome.get("region") or "UNKNOWN"
            for key, payload in horizons.items():
                if key in self.matured_by_horizon:
                    self.matured_by_horizon[key] += 1
                if payload.get("absoluteReturn") is not None:
                    pair = (region, key)
                    self.absolute_by_region_horizon[pair] = (
                        self.absolute_by_region_horizon.get(pair, 0) + 1)
                    if payload.get("benchmarkReturn") is not None:
                        self.benchmark_by_region_horizon[pair] = (
                            self.benchmark_by_region_horizon.get(pair, 0) + 1)
                    else:
                        samples = self.missing_benchmark_samples.setdefault(pair, [])
                        if len(samples) < 5:
                            samples.append({
                                "id": outcome.get("id"),
                                "date": outcome.get("date"),
                                "endDate": payload.get("endDate"),
                                "ticker": outcome.get("ticker"),
                                "benchmark": outcome.get("benchmark"),
                            })
            if target in horizons:
                self.matured_signals += 1
                if outcome.get("date"):
                    self.matured_dates.add(pd.Timestamp(outcome["date"]).normalize())
        return self

    def summary(self) -> dict:
        signal_dates = sorted(self.signal_dates)
        matured_dates = sorted(self.matured_dates)
        tracking_days = (len(pd.bdate_range(signal_dates[0], signal_dates[-1]))
                         if signal_dates else 0)
        matured_days = (len(pd.bdate_range(matured_dates[0], matured_dates[-1]))
                        if matured_dates else 0)
        coverage_by_region: dict[str, dict[str, dict]] = {}
        all_pairs = sorted(set(self.absolute_by_region_horizon)
                           | set(self.benchmark_by_region_horizon))
        for region, horizon in all_pairs:
            absolute = self.absolute_by_region_horizon.get((region, horizon), 0)
            matched = self.benchmark_by_region_horizon.get((region, horizon), 0)
            coverage_by_region.setdefault(region, {})[horizon] = {
                "maturedAbsoluteReturns": absolute,
                "matchedBenchmarkReturns": matched,
                "missingBenchmarkReturns": max(0, absolute - matched),
                "coveragePct": round(matched / absolute * 100, 4) if absolute else None,
                "missingSamples": list(
                    self.missing_benchmark_samples.get((region, horizon), [])),
            }
        return {
            "signalsRecorded": self.signals_recorded,
            "signalsByRegion": dict(sorted(self.signals_by_region.items())),
            "uniqueDates": len(signal_dates),
            "trackingDays": tracking_days,
            "firstSignalDate": signal_dates[0].strftime("%Y-%m-%d") if signal_dates else None,
            "lastSignalDate": signal_dates[-1].strftime("%Y-%m-%d") if signal_dates else None,
            "maturedSignals": self.matured_signals,
            "maturedUniqueDates": len(matured_dates),
            "maturedObservationDays": matured_days,
            "lastMaturedSignalDate": (matured_dates[-1].strftime("%Y-%m-%d")
                                      if matured_dates else None),
            "horizon": self.horizon,
            "maturedByHorizon": dict(self.matured_by_horizon),
            "benchmarkCoverageByRegion": coverage_by_region,
        }


def coverage_summary(signals: list[dict], outcomes: list[dict],
                     horizon: int = 126) -> dict:
    """How much evidence exists, counted honestly.

    ``trackingDays`` (calendar span covered) and ``maturedSignals`` (how many
    have a completed horizon) are different numbers and are reported as such.
    Conflating them is what made the old dashboard report "0 days" while
    thousands of signals were already on disk.
    """
    return (CoverageAccumulator(horizon)
            .add_signals(signals)
            .add_outcomes(outcomes)
            .summary())


def benchmark_coverage_gate(coverage: dict, *, horizon: int = 126,
                            min_coverage_pct: float = 95.0) -> dict:
    """Require usable benchmark labels wherever absolute outcomes matured.

    A small number of exact-session misses can be legitimate for halted names,
    so the default is deliberately below 100%.  Zero or materially incomplete
    regional coverage is never allowed to masquerade as a successful replay.
    """
    failures = []
    assessed_regions = []
    regions = sorted(set(coverage.get("signalsByRegion") or {})
                     | set(coverage.get("benchmarkCoverageByRegion") or {}))
    for region in regions:
        horizons = ((coverage.get("benchmarkCoverageByRegion") or {}).get(region)
                    or {})
        row = (horizons or {}).get(str(horizon)) or {}
        absolute = int(row.get("maturedAbsoluteReturns") or 0)
        if absolute <= 0:
            if int((coverage.get("signalsByRegion") or {}).get(region) or 0) > 0:
                failures.append({
                    "region": region,
                    "horizon": int(horizon),
                    "coveragePct": None,
                    "minimumCoveragePct": float(min_coverage_pct),
                    "maturedAbsoluteReturns": 0,
                    "matchedBenchmarkReturns": 0,
                    "missingBenchmarkReturns": 0,
                    "missingSamples": [],
                    "reason": "no_matured_absolute_returns",
                })
            continue
        assessed_regions.append(region)
        pct = row.get("coveragePct")
        if pct is None or float(pct) < float(min_coverage_pct):
            failures.append({
                "region": region,
                "horizon": int(horizon),
                "coveragePct": pct,
                "minimumCoveragePct": float(min_coverage_pct),
                "maturedAbsoluteReturns": absolute,
                "matchedBenchmarkReturns": int(row.get("matchedBenchmarkReturns") or 0),
                "missingBenchmarkReturns": int(row.get("missingBenchmarkReturns") or 0),
                "missingSamples": list(row.get("missingSamples") or []),
            })
    return {
        "eligible": bool(assessed_regions) and not failures,
        "horizon": int(horizon),
        "minimumCoveragePct": float(min_coverage_pct),
        "requiredRegions": regions,
        "assessedRegions": assessed_regions,
        "failures": failures,
        "reason": (None if assessed_regions and not failures
                   else "benchmark_coverage_below_threshold" if failures
                   else "no_matured_regions_to_assess"),
    }
