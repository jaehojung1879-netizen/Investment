"""Auditable constrained Fractional Kelly model portfolio.

The long-term alpha score is deliberately *not* treated as an expected return.
Expected excess returns come only from matured, point-in-time paper-ledger
outcomes.  When that history or the covariance sample is insufficient the
module returns an explicit shadow/fallback state and preserves the existing
inverse-downside-volatility portfolio.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from sklearn.covariance import LedoitWolf
except Exception:  # dependency absence is reported, never silently imputed
    LedoitWolf = None

try:  # scipy is already a transitive dependency of scikit-learn.
    from scipy.optimize import minimize
except Exception:  # pragma: no cover - exercised through fallback tests
    minimize = None


STATUSES = {
    "DISABLED", "SHADOW_INSUFFICIENT_HISTORY", "SHADOW_READY",
    "ACTIVE_PAPER", "ACTIVE_VALIDATED", "OPTIMIZATION_FAILED",
    "FALLBACK_RISK_WEIGHTED", "BLOCKED",
}


def load_json(path: str | Path | None, default):
    if not path:
        return default
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def load_jsonl(path: str | Path | None) -> list[dict]:
    if not path:
        return []
    try:
        return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    except Exception:
        return []


def _bucket(value: float | None, edges: list[float]) -> tuple[float, float] | None:
    if value is None or not np.isfinite(value):
        return None
    for lo, hi in zip(edges[:-1], edges[1:]):
        if lo <= value < hi or (value == edges[-1] and hi == edges[-1]):
            return float(lo), float(hi)
    return None


def _non_overlapping_dates(rows: list[dict], horizon: int) -> list[pd.Timestamp]:
    dates = sorted({pd.Timestamp(r["date"]).normalize() for r in rows if r.get("date")})
    chosen: list[pd.Timestamp] = []
    for date in dates:
        if not chosen or date >= chosen[-1] + pd.offsets.BDay(horizon):
            chosen.append(date)
    return chosen


def _clustered_date_returns(rows: list[dict], horizon: int | None = None) -> pd.Series:
    """One observation per signal date, preventing a large cross-section from
    masquerading as independent history."""
    if not rows:
        return pd.Series(dtype=float)
    def value(row):
        if row.get("_excess") is not None:
            return float(row["_excess"])
        if horizon is not None:
            outcome = (row.get("horizons") or {}).get(str(horizon)) or {}
            if outcome.get("excessReturn") is not None:
                return float(outcome["excessReturn"])
        for outcome in (row.get("horizons") or {}).values():
            if outcome.get("excessReturn") is not None:
                return float(outcome["excessReturn"])
        return np.nan
    frame = pd.DataFrame({
        "date": [pd.Timestamp(r["date"]).normalize() for r in rows],
        "value": [value(r) for r in rows],
    }).dropna(subset=["value"])
    return frame.groupby("date", sort=True)["value"].mean().sort_index()


def _newey_west_stats(values: pd.Series, horizon: int,
                       half_life_days: int | None = None) -> dict:
    """Date-clustered mean with Newey-West/HAC overlap correction.

    Forward returns sampled daily overlap for roughly ``horizon`` sessions and
    behave like an MA(horizon-1) series. Bartlett-kernel HAC with that explicit
    lag is therefore the sampling rule rather than an arbitrary non-overlap
    heuristic. Limited exponential decay may affect the point estimate, never
    increase the effective sample size.
    """
    s = pd.to_numeric(values, errors="coerce").dropna().sort_index()
    n = len(s)
    if not n:
        return {"mean": 0.0, "se": None, "effectiveDates": 0,
                "uniqueDates": 0, "hacLag": 0}
    arr = s.to_numpy(dtype=float)
    if half_life_days and half_life_days > 0 and n > 1:
        age = np.arange(n - 1, -1, -1, dtype=float)
        weights = np.power(0.5, age / float(half_life_days))
        weights /= weights.sum()
        mean = float(weights @ arr)
    else:
        mean = float(arr.mean())
    centered = arr - mean
    lag = min(max(0, int(horizon) - 1), n - 1)
    gamma0 = float(centered @ centered / n)
    long_run = gamma0
    for k in range(1, lag + 1):
        gamma = float(centered[k:] @ centered[:-k] / n)
        long_run += 2.0 * (1.0 - k / (lag + 1.0)) * gamma
    long_run = max(long_run, 0.0)
    se = math.sqrt(long_run / n) if n else None
    effective = n if long_run <= 1e-18 else int(max(1, min(n, math.floor(n * gamma0 / long_run))))
    return {"mean": mean, "se": se, "effectiveDates": effective,
            "uniqueDates": n, "hacLag": lag}


def _effective_sample_size(rows: list[dict], horizon: int) -> tuple[int, int]:
    """Backward-compatible facade returning HAC-effective and unique dates."""
    stats = _newey_west_stats(_clustered_date_returns(rows, horizon), horizon)
    return stats["effectiveDates"], stats["uniqueDates"]


def sample_gate(*, paper_days: int, matured_signals: int, effective_dates: int,
                unique_dates: int, cfg: dict) -> dict:
    """Single sampling gate shared by return estimation and activation."""
    activation = cfg.get("activation") or {}
    thresholds = {
        "paperDays": int(activation.get("minPaperDays", 252)),
        "maturedSignals": int(activation.get("minMaturedSignals", 100)),
        "effectiveDates": int(cfg.get("minEffectiveDates", 30)),
        "uniqueDates": int(cfg.get("minUniqueDates", 63)),
    }
    actual = {
        "paperDays": int(paper_days or 0), "maturedSignals": int(matured_signals or 0),
        "effectiveDates": int(effective_dates or 0), "uniqueDates": int(unique_dates or 0),
    }
    checks = {key: actual[key] >= need for key, need in thresholds.items()}
    return {
        "eligible": all(checks.values()), "checks": checks,
        "actual": actual, "thresholds": thresholds,
        "missing": [key for key, ok in checks.items() if not ok],
        "method": "DATE_CLUSTERED_NEWEY_WEST_HAC",
    }


def estimate_transaction_cost(candidate: dict, cfg: dict) -> dict:
    """Conservative, auditable cost estimate with an explicit fallback."""
    region = candidate.get("region") or "UNKNOWN"
    regional = (cfg.get("transactionCosts") or {}).get(region) or {}
    fallback = not bool(regional)
    commission = float(regional.get("commissionBps", 5.0))
    sell_tax = float(regional.get("sellTaxBps", 20.0 if region == "KR" else 3.0))
    spread = float(candidate.get("liquiditySpreadBps") or regional.get("spreadBps", 12.0))
    turnover = float(regional.get("assumedTurnoverPct", 25.0)) / 100.0
    rebalance_days = max(1, int(regional.get("rebalanceDays", 63)))
    horizon = max(1, int(cfg.get("horizonDays", 126)))
    cycles = max(1.0, horizon / rebalance_days)
    # Commission and spread are paid on entry and exit; sell tax once.
    round_trip_bps = commission * 2.0 + spread * 2.0 + sell_tax
    cost = turnover * round_trip_bps / 10_000.0 * cycles
    return {
        "estimatedCost": cost, "estimatedCostPct": round(cost * 100, 3),
        "assumedTurnoverPct": round(turnover * 100, 2),
        "commissionBps": commission, "sellTaxBps": sell_tax, "spreadBps": spread,
        "rebalanceDays": rebalance_days, "cyclesInHorizon": round(cycles, 2),
        "expectedTradeNotionalKrw": regional.get("expectedTradeNotionalKrw"),
        "fallbackUsed": fallback or candidate.get("liquiditySpreadBps") is None,
    }


def _isotonic_non_decreasing(values: list[float], weights: list[float]) -> list[float]:
    """Small weighted pool-adjacent-violators implementation."""
    blocks = [[float(v), max(float(w), 1.0), [i]] for i, (v, w) in enumerate(zip(values, weights))]
    i = 0
    while i < len(blocks) - 1:
        if blocks[i][0] <= blocks[i + 1][0] + 1e-15:
            i += 1
            continue
        total_w = blocks[i][1] + blocks[i + 1][1]
        pooled = (blocks[i][0] * blocks[i][1] + blocks[i + 1][0] * blocks[i + 1][1]) / total_w
        blocks[i:i + 2] = [[pooled, total_w, blocks[i][2] + blocks[i + 1][2]]]
        i = max(0, i - 1)
    out = [0.0] * len(values)
    for value, _, members in blocks:
        for member in members:
            out[member] = value
    return out


def estimate_expected_returns(candidates: list[dict], outcomes: list[dict],
                              cfg: dict, as_of: str | pd.Timestamp | None = None) -> list[dict]:
    """Estimate cost-adjusted 126d excess returns from matured OOS outcomes.

    Candidate alpha percentiles are used only to select a historical calibration
    bucket; the alpha score itself never enters a return formula.
    """
    horizon = int(cfg.get("horizonDays", 126))
    edges = [float(x) for x in cfg.get("alphaPercentileBuckets", [0, 60, 80, 90, 95, 100])]
    min_eff = int(cfg.get("minEffectiveDates", 30))
    min_dates = int(cfg.get("minUniqueDates", 63))
    prior_strength = float(cfg.get("shrinkagePriorStrength", min_eff))
    half_life = int(cfg.get("timeDecayHalfLifeDays", 504))
    cutoff = pd.Timestamp(as_of).normalize() if as_of is not None else pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()

    matured = []
    for row in outcomes:
        h = (row.get("horizons") or {}).get(str(horizon))
        if not h or h.get("excessReturn") is None or row.get("date") is None:
            continue
        # A stored outcome is still ignored if it would not have matured by the
        # requested as-of date. This makes look-ahead impossible in replays.
        if pd.Timestamp(row["date"]).normalize() + pd.offsets.BDay(horizon) > cutoff:
            continue
        pct = row.get("alphaPercentile")
        if pct is None:
            continue
        enriched = dict(row)
        enriched["_bucket"] = _bucket(float(pct), edges)
        enriched["_excess"] = float(h["excessReturn"])
        matured.append(enriched)

    result = []
    for candidate in candidates:
        target = _bucket(candidate.get("alphaPercentile"), edges)
        region = candidate.get("region") or "UNKNOWN"
        same_region = [r for r in matured if (r.get("region") or "UNKNOWN") == region and r.get("_bucket")]
        rows = [r for r in same_region if r["_bucket"] == target] if target else []
        level = "REGION_ALPHA_BUCKET"

        # Merge adjacent buckets only when the exact bucket is thin. The
        # expansion order is deterministic and remains within the same region.
        if len(rows) < int((cfg.get("activation") or {}).get("minMaturedSignals", 100)) and target:
            centers = sorted({b for b in (_bucket(r.get("alphaPercentile"), edges) for r in same_region) if b},
                             key=lambda b: abs(((b[0] + b[1]) / 2) - ((target[0] + target[1]) / 2)))
            rows = []
            for b in centers:
                rows.extend(r for r in same_region if r["_bucket"] == b)
                eff, ndates = _effective_sample_size(rows, horizon)
                if eff >= min_eff and ndates >= min_dates:
                    break
            level = "REGION_MERGED_ALPHA_BUCKETS"

        clustered = _clustered_date_returns(rows)
        stats = _newey_west_stats(clustered, horizon, half_life_days=half_life)
        eff, ndates = stats["effectiveDates"], stats["uniqueDates"]
        raw = float(stats["mean"])
        cost_detail = estimate_transaction_cost(candidate, cfg)
        cost = float(cost_detail["estimatedCost"])
        net = raw - cost
        shrink = eff / (eff + prior_strength) if eff else 0.0
        paper_days = (len(pd.bdate_range(clustered.index.min(), cutoff)) if len(clustered) else 0)
        gate = sample_gate(paper_days=paper_days, matured_signals=len(rows),
                           effective_dates=eff, unique_dates=ndates, cfg=cfg)
        sufficient = gate["eligible"]
        expected = net * shrink if sufficient else 0.0

        # Recent deterioration receives a transparent 25% haircut, never a boost.
        haircut = 1.0
        if sufficient and len(rows) >= 8:
            ordered = sorted(rows, key=lambda r: r.get("date") or "")
            split = max(1, len(ordered) // 2)
            old_mean = float(np.mean([r["_excess"] for r in ordered[:split]]))
            recent_mean = float(np.mean([r["_excess"] for r in ordered[split:]]))
            if expected > 0 and recent_mean < old_mean:
                haircut = 0.75
                expected *= haircut

        se = stats.get("se")
        ci = None
        if sufficient and se is not None:
            ci = [round(((raw - 1.96 * se - cost) * shrink * haircut) * 100, 3),
                  round(((raw + 1.96 * se - cost) * shrink * haircut) * 100, 3)]
        confidence = "INSUFFICIENT"
        if sufficient:
            confidence = "HIGH" if eff >= max(min_eff * 2, 60) else "MEDIUM"
        sector_counts = pd.Series([r.get("sector") or "UNKNOWN" for r in rows]).value_counts()
        top_sector_share = float(sector_counts.iloc[0] / len(rows)) if len(rows) and len(sector_counts) else None
        market_cap_coverage = (sum(r.get("marketCap") is not None for r in rows) / len(rows)) if rows else 0.0
        lo, hi = target or (None, None)
        result.append({
            "ticker": candidate["ticker"], "region": region, "horizonDays": horizon,
            "expectedExcessReturnPct": round(expected * 100, 3),
            "rawObservedExcessReturnPct": round(raw * 100, 3),
            "estimatedTransactionCostPct": round(cost * 100, 3), "transactionCost": cost_detail,
            "recentPerformanceHaircut": haircut,
            "shrinkageFactor": round(shrink, 4),
            "effectiveSampleSize": eff, "effectiveDates": eff,
            "uniqueDates": ndates, "nonOverlappingDates": len(_non_overlapping_dates(rows, horizon)),
            "hacLag": stats["hacLag"], "confidence": confidence,
            "confidenceIntervalPct": ci, "sampleGate": gate,
            "alphaPercentileBucket": f"{lo:g}-{hi:g}" if lo is not None else None,
            "estimationLevel": level if rows else "NO_MATURED_REGION_HISTORY",
            "distortionDiagnostics": {
                "topSectorSharePct": round(top_sector_share * 100, 1) if top_sector_share is not None else None,
                "marketCapCoveragePct": round(market_cap_coverage * 100, 1),
                "warning": "SECTOR_CONCENTRATION" if top_sector_share is not None and top_sector_share > 0.5 else None,
            },
            "status": "SHADOW" if sufficient else "SHADOW_INSUFFICIENT_HISTORY",
        })
    # Enforce a non-decreasing alpha-bucket calibration within each region.
    for region in sorted({r["region"] for r in result}):
        groups: dict[str, list[dict]] = {}
        for row in result:
            if row["region"] == region and row["status"] == "SHADOW" and row["alphaPercentileBucket"]:
                groups.setdefault(row["alphaPercentileBucket"], []).append(row)
        ordered_buckets = sorted(groups, key=lambda b: float(b.split("-", 1)[0]))
        if len(ordered_buckets) < 2:
            continue
        original = [float(np.mean([r["expectedExcessReturnPct"] for r in groups[b]])) for b in ordered_buckets]
        weights = [max(1, max(int(r["effectiveDates"]) for r in groups[b])) for b in ordered_buckets]
        adjusted = _isotonic_non_decreasing(original, weights)
        deltas = {bucket: after - before for bucket, before, after in zip(ordered_buckets, original, adjusted)}
        violated = any(abs(a - b) > 1e-9 for a, b in zip(original, adjusted))
        for row in result:
            if row["region"] == region and row["alphaPercentileBucket"] in deltas and row["status"] == "SHADOW":
                row["preIsotonicExpectedExcessReturnPct"] = row["expectedExcessReturnPct"]
                row["expectedExcessReturnPct"] = round(row["expectedExcessReturnPct"] + deltas[row["alphaPercentileBucket"]], 3)
                row["monotonicityWarning"] = "BUCKET_MONOTONICITY_REPAIRED" if violated else None
    return result


def _covariance_from_panel(panel: pd.DataFrame, cfg: dict, *, basis: str,
                           region: str | None = None, benchmark: str | None = None) -> tuple[pd.DataFrame | None, dict]:
    lookback = int(cfg.get("covarianceLookbackDays", 504))
    minimum = int(cfg.get("covarianceMinDays", 252))
    panel = panel.dropna().tail(lookback)
    if len(panel) < minimum:
        return None, {"status": "INSUFFICIENT", "reason": "common_return_history_below_minimum",
                      "observations": len(panel), "returnBasis": basis, "region": region,
                      "benchmark": benchmark}
    try:
        if cfg.get("useLedoitWolf", True):
            if LedoitWolf is None:
                return None, {"status": "FAILED", "reason": "ledoit_wolf_dependency_unavailable",
                              "observations": len(panel), "returnBasis": basis, "region": region,
                              "benchmark": benchmark}
            estimator = LedoitWolf().fit(panel.to_numpy(dtype=float))
            matrix = estimator.covariance_ * 252.0
            shrinkage = float(estimator.shrinkage_)
            method = "LEDOIT_WOLF"
        else:
            matrix = panel.cov().to_numpy(dtype=float) * 252.0
            shrinkage = None
            method = "SAMPLE"
        matrix = (matrix + matrix.T) / 2
        eigen_min = float(np.linalg.eigvalsh(matrix).min())
        if eigen_min < 0:
            matrix += np.eye(len(matrix)) * (-eigen_min + 1e-12)
        cov = pd.DataFrame(matrix, index=panel.columns, columns=panel.columns)
        return cov, {"status": "READY", "method": method, "observations": len(panel),
                     "lookbackDays": lookback, "shrinkage": shrinkage,
                     "minEigenvalue": round(float(np.linalg.eigvalsh(matrix).min()), 12),
                     "returnBasis": basis, "region": region, "benchmark": benchmark,
                     "annualization": 252}
    except Exception as exc:
        return None, {"status": "FAILED", "reason": f"covariance_error:{exc.__class__.__name__}",
                      "observations": len(panel), "returnBasis": basis, "region": region,
                      "benchmark": benchmark}


def estimate_covariance(prices: dict, tickers: list[str], cfg: dict) -> tuple[pd.DataFrame | None, dict]:
    """Legacy absolute-return covariance, retained for diagnostics/tests only."""
    lookback = int(cfg.get("covarianceLookbackDays", 504))
    minimum = int(cfg.get("covarianceMinDays", 252))
    series = {}
    for ticker in tickers:
        frame = prices.get(ticker)
        if frame is not None and "Close" in frame:
            s = frame["Close"].astype(float).replace([np.inf, -np.inf], np.nan).dropna()
            if len(s) >= minimum + 1:
                series[ticker] = s.pct_change(fill_method=None)
    if len(series) < 2:
        return None, {"status": "INSUFFICIENT", "reason": "fewer_than_two_price_series", "observations": 0,
                      "returnBasis": "ABSOLUTE_LOCAL_CURRENCY"}
    panel = pd.concat(series, axis=1, join="inner").dropna().tail(lookback)
    return _covariance_from_panel(panel, cfg, basis="ABSOLUTE_LOCAL_CURRENCY")


def estimate_active_covariance(prices: dict, tickers: list[str], benchmark_close: pd.Series | None,
                               cfg: dict, *, region: str, benchmark: str) -> tuple[pd.DataFrame | None, dict]:
    """Region-local active-return covariance matching expected excess returns."""
    if benchmark_close is None:
        return None, {"status": "INSUFFICIENT", "reason": "regional_benchmark_unavailable",
                      "observations": 0, "returnBasis": "REGIONAL_ACTIVE", "region": region,
                      "benchmark": benchmark}
    minimum = int(cfg.get("covarianceMinDays", 252))
    bench = pd.to_numeric(benchmark_close, errors="coerce").dropna().pct_change(fill_method=None)
    series = {}
    for ticker in tickers:
        frame = prices.get(ticker)
        if frame is None or "Close" not in frame:
            continue
        close = pd.to_numeric(frame["Close"], errors="coerce").dropna()
        if len(close) < minimum + 1:
            continue
        stock = close.pct_change(fill_method=None)
        pair = pd.concat([stock.rename("stock"), bench.rename("benchmark")], axis=1, join="inner").dropna()
        if len(pair) >= minimum:
            series[ticker] = pair["stock"] - pair["benchmark"]
    if len(series) < 2:
        return None, {"status": "INSUFFICIENT", "reason": "fewer_than_two_active_return_series",
                      "observations": 0, "returnBasis": "REGIONAL_ACTIVE", "region": region,
                      "benchmark": benchmark}
    panel = pd.concat(series, axis=1, join="inner")
    return _covariance_from_panel(panel, cfg, basis="REGIONAL_ACTIVE", region=region, benchmark=benchmark)


def _exposures(weights: pd.Series, candidates: list[dict], themes: dict) -> tuple[dict, dict, dict]:
    by_ticker = {c["ticker"]: c for c in candidates}
    sector: dict[str, float] = {}
    theme: dict[str, float] = {}
    region: dict[str, float] = {}
    for ticker, weight in weights.items():
        if weight <= 0:
            continue
        c = by_ticker[ticker]
        sec = c.get("sector") or "Unclassified"
        reg = c.get("region") or "UNKNOWN"
        sector[sec] = sector.get(sec, 0.0) + float(weight)
        region[reg] = region.get(reg, 0.0) + float(weight)
        labels = themes.get(ticker) or ["Unclassified"]
        for label in labels:
            theme[label] = theme.get(label, 0.0) + float(weight)
    return sector, theme, region


def _state_multiplier(candidate: dict, cfg: dict) -> float:
    if candidate.get("dataInsufficient") or candidate.get("valueTrap"):
        return 0.0
    if candidate.get("longTermResearchView") != "POSITIVE":
        return 0.0
    state = ((candidate.get("entry") or {}).get("entryState") or candidate.get("entryState") or "WATCH")
    if state in {"EVENT_RISK", "AVOID"}:
        return 0.0
    if state == "WAIT_FOR_PULLBACK":
        return float(cfg.get("waitForPullbackWeightMultiplier", 0.25))
    if state == "WATCH":
        return float(cfg.get("watchWeightMultiplier", 0.5))
    return 1.0


def optimize_fractional_kelly(expected_returns: list[dict], covariance: pd.DataFrame,
                              candidates: list[dict], cfg: dict, applied_fraction: float,
                              themes: dict | None = None, prior_weights: dict | None = None) -> dict:
    """Solve the long-only constrained mean-variance Kelly approximation."""
    themes, prior_weights = themes or {}, prior_weights or {}
    er = {r["ticker"]: r for r in expected_returns}
    by_ticker = {c["ticker"]: c for c in candidates}
    tickers = [c["ticker"] for c in candidates if c["ticker"] in covariance.index and c["ticker"] in er]
    max_names = int(cfg.get("maxNames", 12))
    def sort_key(ticker):
        c, e = by_ticker[ticker], er[ticker]
        downside = (c.get("risk") or {}).get("downsideVolPct")
        return (-(e.get("expectedExcessReturnPct") or 0.0),
                -(c.get("alphaPercentile") or -1.0),
                -(c.get("evidenceCoverage") or 0.0),
                -(c.get("dataCompleteness") or 0.0),
                float(downside) if downside is not None else float("inf"), str(ticker))
    tickers = sorted(tickers, key=sort_key)[:max_names]
    candidates = [by_ticker[t] for t in tickers]
    if len(tickers) < int(cfg.get("minNames", 6)):
        return {"ok": False, "reason": "eligible_names_below_minimum"}
    if minimize is None:
        return {"ok": False, "reason": "scipy_optimizer_unavailable"}

    cov = covariance.loc[tickers, tickers].to_numpy(dtype=float)
    horizon = float(cfg.get("horizonDays", 126))
    mu = np.array([(er[t].get("expectedExcessReturnPct") or 0.0) / 100.0 * (252.0 / horizon) for t in tickers])
    mu_eff = mu * float(applied_fraction)
    name_cap = float(cfg.get("maxPositionWeight", 0.10))
    budget = float(cfg.get("portfolioBudget", 1.0 - float(cfg.get("minCashPct", 10)) / 100.0))
    sector_cap = float(cfg.get("maxSectorWeight", 0.25))
    theme_cap = float(cfg.get("maxThemeWeight", 0.20))
    region_caps = cfg.get("regionCaps") or {}
    turnover_cap = float(cfg.get("maxTurnoverPct", 25)) / 100.0
    penalty = float(cfg.get("turnoverPenalty", 0.002))
    risk_aversion = float(cfg.get("riskAversion", 1.0))
    prior = np.array([max(0.0, float(prior_weights.get(t, 0.0))) for t in tickers])
    has_prior = bool(prior_weights)

    multipliers = np.array([_state_multiplier(c, cfg) for c in candidates])
    bounds = [(0.0, name_cap * float(m)) for m in multipliers]
    if sum(hi for _, hi in bounds) <= 0:
        return {"ok": False, "reason": "no_entry_eligible_positive_names"}

    def objective(w):
        turnover = np.abs(w - prior).sum() if has_prior else 0.0
        return -(mu_eff @ w - 0.5 * risk_aversion * (w @ cov @ w) - penalty * turnover)

    constraints = [{"type": "ineq", "fun": lambda w: budget - w.sum()}]
    sectors = sorted({c.get("sector") or "Unclassified" for c in candidates})
    for sector in sectors:
        idx = np.array([i for i, c in enumerate(candidates) if (c.get("sector") or "Unclassified") == sector])
        constraints.append({"type": "ineq", "fun": lambda w, idx=idx: sector_cap - w[idx].sum()})
    theme_labels = sorted({label for c in candidates for label in (themes.get(c["ticker"]) or ["Unclassified"])
                           if label != "Unclassified"})
    for label in theme_labels:
        idx = np.array([i for i, c in enumerate(candidates) if label in (themes.get(c["ticker"]) or ["Unclassified"])])
        constraints.append({"type": "ineq", "fun": lambda w, idx=idx: theme_cap - w[idx].sum()})
    for region, cap in region_caps.items():
        idx = np.array([i for i, c in enumerate(candidates) if c.get("region") == region])
        if len(idx):
            constraints.append({"type": "ineq", "fun": lambda w, idx=idx, cap=float(cap): cap - w[idx].sum()})
    if has_prior:
        constraints.append({"type": "ineq", "fun": lambda w: turnover_cap * 2.0 - np.abs(w - prior).sum()})

    inv = np.divide(1.0, np.sqrt(np.maximum(np.diag(cov), 1e-10)))
    x0 = inv / inv.sum() * min(budget, sum(hi for _, hi in bounds))
    x0 = np.minimum(x0, np.array([hi for _, hi in bounds]))
    result = minimize(objective, x0, method="SLSQP", bounds=bounds, constraints=constraints,
                      options={"maxiter": 1000, "ftol": 1e-11})
    if not result.success or not np.all(np.isfinite(result.x)):
        return {"ok": False, "reason": "optimization_failed", "detail": str(result.message)[:160]}

    weights = pd.Series(np.maximum(result.x, 0.0), index=tickers)
    try:
        raw = np.linalg.pinv(cov) @ mu
        raw = pd.Series(np.maximum(raw, 0.0) * float(applied_fraction), index=tickers)
    except Exception:
        raw = pd.Series(0.0, index=tickers)
    return {"ok": True, "weights": weights, "unconstrainedWeights": raw,
            "objective": round(float(-result.fun), 8), "iterations": int(result.nit)}


def _cap_portfolio(weights: pd.Series, candidates: list[dict], cfg: dict,
                   themes: dict) -> tuple[pd.Series, list[str]]:
    """Deterministically remove constraint excess; never force it elsewhere."""
    w = weights.clip(lower=0).astype(float).copy()
    bindings: list[str] = []
    name_cap = float(cfg.get("maxPositionWeight", 0.10))
    over = w > name_cap
    if over.any():
        bindings.extend(f"POSITION_CAP:{t}" for t in w[over].index)
        w[over] = name_cap
    group_specs = [
        ("SECTOR_CAP", float(cfg.get("maxSectorWeight", 0.25)), lambda c: [c.get("sector") or "Unclassified"]),
        ("THEME_CAP", float(cfg.get("maxThemeWeight", 0.20)), lambda c: themes.get(c["ticker"]) or ["Unclassified"]),
        ("REGION_CAP", None, lambda c: [c.get("region") or "UNKNOWN"]),
    ]
    by_ticker = {c["ticker"]: c for c in candidates}
    for _ in range(4):
        for prefix, fixed_cap, labels_fn in group_specs:
            groups: dict[str, list[str]] = {}
            for ticker in w.index:
                for label in labels_fn(by_ticker[ticker]):
                    groups.setdefault(label, []).append(ticker)
            for label, names in groups.items():
                if prefix == "THEME_CAP" and label == "Unclassified":
                    continue
                cap = fixed_cap
                if prefix == "REGION_CAP":
                    cap = float((cfg.get("regionCaps") or {}).get(label, 1.0))
                total = float(w[names].sum())
                if cap is not None and total > cap + 1e-10:
                    w[names] *= cap / total
                    key = f"{prefix}:{label}"
                    if key not in bindings:
                        bindings.append(key)
    budget = 1.0 - float(cfg.get("minCashPct", 10)) / 100.0
    if w.sum() > budget:
        w *= budget / float(w.sum())
        bindings.append("MIN_CASH")
    return w, bindings


def blend_with_risk_weighted_portfolio(risk_weights: dict, kelly_weights: dict,
                                        candidates: list[dict], cfg: dict,
                                        themes: dict | None = None,
                                        prior_weights: dict | None = None) -> dict:
    themes, prior_weights = themes or {}, prior_weights or {}
    tickers = [c["ticker"] for c in candidates]
    risk = pd.Series({t: float(risk_weights.get(t, 0.0)) for t in tickers})
    kelly = pd.Series({t: float(kelly_weights.get(t, 0.0)) for t in tickers})
    blend = float(cfg.get("blendWeight", 0.25))
    combined = (1.0 - blend) * risk + blend * kelly
    combined, bindings = _cap_portfolio(combined, candidates, cfg, themes)

    if prior_weights:
        prior = pd.Series({t: float(prior_weights.get(t, 0.0)) for t in tickers})
        turnover = 0.5 * float((combined - prior).abs().sum())
        cap = float(cfg.get("maxTurnoverPct", 25)) / 100.0
        if turnover > cap and turnover > 0:
            combined = prior + (combined - prior) * (cap / turnover)
            combined, more = _cap_portfolio(combined, candidates, cfg, themes)
            bindings.extend(x for x in more if x not in bindings)
            bindings.append("TURNOVER_CAP")
    return {"weights": combined, "bindingConstraints": bindings}


def _candidate_rows(long_term: dict | None) -> list[dict]:
    rows: list[dict] = []
    for region, blob in ((long_term or {}).get("regions") or {}).items():
        source = (blob or {}).get("picks") or []
        for row in source:
            item = dict(row)
            item["region"] = item.get("region") or region
            rows.append(item)
    return rows


def _risk_weights(candidates: list[dict], cfg: dict) -> dict:
    raw = {c["ticker"]: max(0.0, float(c.get("modelSleeveWeightPct") or 0.0) / 100.0) for c in candidates}
    total = sum(raw.values())
    budget = 1.0 - float(cfg.get("minCashPct", 10)) / 100.0
    if total > 0:
        raw = {t: w / total * budget for t, w in raw.items()}
    capped, _ = _cap_portfolio(pd.Series(raw, dtype=float), candidates, cfg, {})
    return capped.to_dict()


def _regime_adjustment(macro_regime: dict | None, cfg: dict) -> tuple[str, float, float, list[str]]:
    macro_regime = macro_regime or {}
    label = macro_regime.get("regime") or "Transition/Low confidence"
    mapping = cfg.get("regimeMultipliers") or {}
    row = mapping.get(label) or mapping.get("Transition/Low confidence") or {}
    multiplier = float(row.get("kellyMultiplier", 0.5))
    warnings = []
    confidence = macro_regime.get("confidence")
    if confidence is not None and float(confidence) < 0.5:
        multiplier *= max(0.5, float(confidence) / 0.5)
        warnings.append("LOW_MACRO_CONFIDENCE_KELLY_HAIRCUT")
    return label, multiplier, float(row.get("minCashPct", cfg.get("minCashPct", 10))), warnings


def _serialize_allocation(weights: pd.Series) -> tuple[dict[str, float], float]:
    """Serialize weights first, then derive cash from those exact values."""
    final_weights = {k: round(float(v), 6) for k, v in weights.items()}
    cash_pct = round((1.0 - sum(final_weights.values())) * 100.0, 6)
    return final_weights, cash_pct


def build_model_portfolio(long_term: dict | None, prices: dict, outcomes: list[dict],
                          cfg: dict | None = None, macro_regime: dict | None = None,
                          themes: dict | None = None, prior_weights: dict | None = None,
                          as_of: str | None = None, blocked: bool = False,
                          validation_status: dict | None = None,
                          benchmarks: dict | None = None,
                          bench_by_region: dict | None = None) -> dict:
    """Top-level assembly from calibrated returns through final blended weights."""
    cfg, themes, prior_weights = cfg or {}, themes or {}, prior_weights or {}
    benchmarks, bench_by_region = benchmarks or {}, bench_by_region or {}
    validation_status = validation_status or {}
    base = float(cfg.get("kellyFraction", 0.25))
    blend = float(cfg.get("blendWeight", 0.25))
    label, regime_mult, regime_cash, warnings = _regime_adjustment(macro_regime, cfg)
    local_cfg = dict(cfg)
    local_cfg["minCashPct"] = max(float(cfg.get("minCashPct", 10)), regime_cash)
    applied = base * regime_mult
    skeleton = {
        "status": "SHADOW_INSUFFICIENT_HISTORY", "method": "BLENDED_CONSTRAINED_FRACTIONAL_KELLY",
        "horizonDays": int(cfg.get("horizonDays", 126)), "baseKellyFraction": base,
        "regime": label, "regimeMultiplier": round(regime_mult, 4),
        "appliedKellyFraction": round(applied, 4), "kellyBlendWeight": blend,
        "riskWeightedBlendWeight": 1.0 - blend, "cashPct": 100.0,
        "expectedVolPct": None, "estimatedMaxDrawdownPct": None, "turnoverPct": 0.0,
        "expectedReturnStatus": "INSUFFICIENT", "fallbackReason": None,
        "kellyApplied": False, "kellyAllocationImpactPct": 0.0,
        "transactionCostPolicy": cfg.get("transactionCosts") or {},
        "positions": [], "riskWeightedWeights": {}, "constrainedKellyWeights": {},
        "finalWeights": {}, "sectorExposure": {}, "themeExposure": {}, "regionExposure": {},
        "constraints": {k: local_cfg.get(k) for k in ("maxPositionWeight", "maxSectorWeight", "maxThemeWeight", "minCashPct", "maxTurnoverPct", "minNames", "maxNames", "regionCaps")},
        "warnings": warnings, "validation": {"eligibleForActivation": False},
        "currencyPolicy": {
            "baseCurrency": (cfg.get("currency") or {}).get("baseCurrency", "KRW"),
            "fxReturnsIncluded": bool((cfg.get("currency") or {}).get("fxReturnsIncluded", False)),
            "fxHedged": bool((cfg.get("currency") or {}).get("fxHedged", False)),
            "riskLayer": "REGION_ALLOCATION_ONLY",
            "warning": "FX_RISK_NOT_IN_ACTIVE_COVARIANCE" if not (cfg.get("currency") or {}).get("fxReturnsIncluded", False) else None,
        },
    }
    if not cfg.get("enabled", True):
        skeleton["status"] = "DISABLED"
        return skeleton
    if blocked:
        skeleton["status"] = "BLOCKED"
        skeleton["warnings"].append("RECOMMENDATIONS_BLOCKED; WEIGHTS_WITHHELD")
        return skeleton

    candidates = sorted(_candidate_rows(long_term), key=lambda c: str(c.get("ticker") or ""))
    if len(candidates) < int(local_cfg.get("minNames", 6)):
        skeleton["fallbackReason"] = "longterm_candidates_below_minimum"
        return skeleton
    risk_weights = _risk_weights(candidates, local_cfg)
    estimates = estimate_expected_returns(candidates, outcomes, local_cfg, as_of=as_of)
    estimate_map = {e["ticker"]: e for e in estimates}
    sufficient = [e for e in estimates if e["status"] == "SHADOW"]
    skeleton["expectedReturnEstimates"] = estimates

    fallback_reason = None
    unconstrained: dict[str, float] = {}
    kelly_weights: dict[str, float] = {}
    covariance_by_region: dict[str, dict] = {}
    covariance_matrices: dict[str, pd.DataFrame] = {}
    if len(sufficient) < int(local_cfg.get("minNames", 6)):
        fallback_reason = "expected_return_history_insufficient"
    else:
        optimization_meta = {}
        min_region_names = int(local_cfg.get("minNamesPerRegion", 3))
        for region in sorted({c.get("region") or "UNKNOWN" for c in candidates}):
            region_candidates = [c for c in candidates
                                 if (c.get("region") or "UNKNOWN") == region
                                 and estimate_map[c["ticker"]]["status"] == "SHADOW"]
            region_estimates = [estimate_map[c["ticker"]] for c in region_candidates]
            risk_budget = sum(float(risk_weights.get(c["ticker"], 0.0)) for c in candidates
                              if (c.get("region") or "UNKNOWN") == region)
            if risk_budget <= 0:
                continue
            if len(region_candidates) < min_region_names:
                fallback_reason = f"{region}:expected_return_history_insufficient"
                break
            benchmark_name = benchmarks.get(region)
            cov, cov_meta = estimate_active_covariance(
                prices, [c["ticker"] for c in region_candidates], bench_by_region.get(region),
                local_cfg, region=region, benchmark=benchmark_name or "UNKNOWN",
            )
            covariance_by_region[region] = cov_meta
            if cov is None:
                fallback_reason = f"{region}:{cov_meta.get('reason') or 'active_covariance_unavailable'}"
                break
            covariance_matrices[region] = cov
            regional_cfg = dict(local_cfg)
            regional_cfg["portfolioBudget"] = min(
                risk_budget, float((local_cfg.get("regionCaps") or {}).get(region, 1.0)))
            regional_cfg["minNames"] = min_region_names
            regional_cfg["maxNames"] = min(int(local_cfg.get("maxNames", 12)), len(region_candidates))
            optimized = optimize_fractional_kelly(
                region_estimates, cov, region_candidates, regional_cfg, applied,
                themes=themes, prior_weights=prior_weights,
            )
            if not optimized.get("ok"):
                skeleton["status"] = "OPTIMIZATION_FAILED"
                fallback_reason = f"{region}:{optimized.get('reason') or 'optimization_failed'}"
                skeleton["warnings"].append(f"OPTIMIZER:{fallback_reason}")
                break
            kelly_weights.update(optimized["weights"].to_dict())
            unconstrained.update(optimized["unconstrainedWeights"].to_dict())
            optimization_meta[region] = {"objective": optimized["objective"],
                                         "iterations": optimized["iterations"],
                                         "portfolioBudget": round(regional_cfg["portfolioBudget"], 6)}
        if not fallback_reason:
            skeleton["optimization"] = optimization_meta
    skeleton["covariance"] = {
        "status": "READY" if covariance_by_region and all(x.get("status") == "READY" for x in covariance_by_region.values()) else "INSUFFICIENT",
        "returnBasis": "REGIONAL_ACTIVE", "regions": covariance_by_region,
        "crossRegionCovarianceUsed": False,
    }

    if fallback_reason:
        final = pd.Series(risk_weights, dtype=float)
        final, bindings = _cap_portfolio(final, candidates, local_cfg, themes)
        skeleton["fallbackReason"] = fallback_reason
        skeleton["warnings"].append("KELLY_NOT_ACTIVATED; EXISTING_RISK_WEIGHTED_PORTFOLIO_RETAINED")
    else:
        blended = blend_with_risk_weighted_portfolio(risk_weights, kelly_weights, candidates,
                                                       local_cfg, themes, prior_weights)
        final, bindings = blended["weights"], blended["bindingConstraints"]
        skeleton["status"] = "SHADOW_READY" if cfg.get("mode", "shadow") == "shadow" else "ACTIVE_PAPER"
        skeleton["expectedReturnStatus"] = "SHADOW"
        skeleton["kellyApplied"] = True

    sector_exp, theme_exp, region_exp = _exposures(final, candidates, themes)
    prior = pd.Series({t: float(prior_weights.get(t, 0.0)) for t in final.index})
    turnover = 0.5 * float((final - prior).abs().sum()) if prior_weights else float(final.sum())
    positions = []
    for candidate in candidates:
        ticker = candidate["ticker"]
        exp = estimate_map.get(ticker, {})
        w = float(final.get(ticker, 0.0))
        position_bindings = [b for b in bindings if b.endswith(f":{ticker}") or
                             (b.startswith("SECTOR_CAP:") and b.split(":", 1)[1] == (candidate.get("sector") or "Unclassified")) or
                             (b.startswith("REGION_CAP:") and b.split(":", 1)[1] == candidate.get("region")) or
                             (b.startswith("THEME_CAP:") and b.split(":", 1)[1] in (themes.get(ticker) or ["Unclassified"]))]
        positions.append({
            "ticker": ticker, "region": candidate.get("region"), "sector": candidate.get("sector") or "Unclassified",
            "themes": themes.get(ticker) or ["Unclassified"], "alphaPercentile": candidate.get("alphaPercentile"),
            "expectedExcessReturnPct": exp.get("expectedExcessReturnPct"),
            "expectedReturnSampleSize": exp.get("effectiveSampleSize", 0),
            "expectedReturnEffectiveDates": exp.get("effectiveDates", 0),
            "expectedReturnUniqueDates": exp.get("uniqueDates", 0),
            "expectedReturnConfidence": exp.get("confidence"),
            "expectedReturnIntervalPct": exp.get("confidenceIntervalPct"),
            "transactionCost": exp.get("transactionCost"),
            "expectedReturnStatus": exp.get("status"),
            "riskLevel": (candidate.get("risk") or {}).get("vol252Pct"),
            "riskWeightedWeightPct": round(float(risk_weights.get(ticker, 0.0)) * 100, 2),
            "unconstrainedKellyWeightPct": (round(float(unconstrained.get(ticker, 0.0)) * 100, 2)
                                                if not fallback_reason else None),
            "constrainedKellyWeightPct": (round(float(kelly_weights.get(ticker, 0.0)) * 100, 2)
                                              if not fallback_reason else None),
            "modelPortfolioWeightPct": round(w * 100, 2),
            "entryState": ((candidate.get("entry") or {}).get("entryState")),
            "kellyAdjustment": ("NOT_APPLIED" if fallback_reason else
                                 "INCREASE" if w > float(risk_weights.get(ticker, 0.0)) + 0.0005 else
                                 "DECREASE" if w < float(risk_weights.get(ticker, 0.0)) - 0.0005 else "UNCHANGED"),
            "bindingConstraints": position_bindings,
        })
    positions.sort(key=lambda p: (-p["modelPortfolioWeightPct"], str(p["ticker"])))
    final_weights, cash_pct = _serialize_allocation(final)
    skeleton.update({
        "cashPct": cash_pct, "turnoverPct": round(turnover * 100, 2),
        "positions": positions, "riskWeightedWeights": {k: round(v, 6) for k, v in risk_weights.items()},
        "constrainedKellyWeights": {k: round(v, 6) for k, v in kelly_weights.items()},
        "finalWeights": final_weights,
        "sectorExposure": {k: round(v * 100, 2) for k, v in sector_exp.items()},
        "themeExposure": {k: round(v * 100, 2) for k, v in theme_exp.items()},
        "regionExposure": {k: round(v * 100, 2) for k, v in region_exp.items()},
        "bindingConstraints": bindings,
    })
    active_variance = 0.0
    for region, cov in covariance_matrices.items():
        common = [t for t in final.index if t in cov.index]
        if common:
            arr = final.loc[common].to_numpy(dtype=float)
            active_variance += max(0.0, float(arr @ cov.loc[common, common].to_numpy() @ arr))
    if active_variance > 0:
        skeleton["expectedVolPct"] = round(math.sqrt(active_variance) * 100, 2)
        skeleton["riskMeasure"] = "REGIONAL_ACTIVE_TRACKING_ERROR"
    risk_series = pd.Series({t: float(risk_weights.get(t, 0.0)) for t in final.index})
    risk_cash = max(0.0, 1.0 - float(risk_series.sum()))
    final_cash = max(0.0, 1.0 - float(final.sum()))
    skeleton["kellyAllocationImpactPct"] = (round(0.5 * (float((final - risk_series).abs().sum())
                                                              + abs(final_cash - risk_cash)) * 100, 2)
                                                    if skeleton["kellyApplied"] else 0.0)
    # Historical drawdown is descriptive (not a forecast) and uses only the
    # same daily close history available at the portfolio calculation time.
    try:
        returns = pd.concat({t: prices[t]["Close"].pct_change(fill_method=None)
                             for t in final.index if t in prices and "Close" in prices[t]},
                            axis=1, join="inner").dropna().tail(int(local_cfg.get("covarianceLookbackDays", 504)))
        common = [t for t in final.index if t in returns.columns]
        if len(returns) and common:
            path = (1.0 + returns[common].mul(final.loc[common], axis=1).sum(axis=1)).cumprod()
            drawdown = path / path.cummax() - 1.0
            skeleton["estimatedMaxDrawdownPct"] = round(float(drawdown.min()) * 100, 2)
    except Exception:
        pass
    total = sum(final_weights.values()) + skeleton["cashPct"] / 100.0
    caps_ok = (
        (not len(final) or float(final.max()) <= float(local_cfg.get("maxPositionWeight", 0.10)) + 1e-8)
        and all(v <= float(local_cfg.get("maxSectorWeight", 0.25)) + 1e-8 for v in sector_exp.values())
        and all(label == "Unclassified" or v <= float(local_cfg.get("maxThemeWeight", 0.20)) + 1e-8
                for label, v in theme_exp.items())
        and all(v <= float((local_cfg.get("regionCaps") or {}).get(label, 1.0)) + 1e-8
                for label, v in region_exp.items())
    )
    activation = local_cfg.get("activation") or {}
    region_ic = validation_status.get("regionIC") or {}
    rank_ic_positive = bool(region_ic) and all((row.get("mean") or 0) > 0 for row in region_ic.values())
    used_estimates = [estimate_map[t] for t in final.index if t in estimate_map]
    weakest_effective = min((int(row.get("effectiveDates") or 0) for row in used_estimates), default=0)
    weakest_unique = min((int(row.get("uniqueDates") or 0) for row in used_estimates), default=0)
    shared_gate = sample_gate(
        paper_days=int(validation_status.get("paperDays") or 0),
        matured_signals=int(validation_status.get("maturedSignals") or 0),
        effective_dates=weakest_effective, unique_dates=weakest_unique, cfg=local_cfg,
    )
    activation_checks = {
        **shared_gate["checks"],
        "positiveCostAdjustedExcess": (validation_status.get("costAdjustedExcessReturn") or 0) > 0,
        "positiveRankIC": rank_ic_positive,
        "noMddDeterioration": validation_status.get("noMddDeterioration") is True,
        "humanApproved": False,
    }
    required = list(shared_gate["checks"].values())
    if activation.get("requirePositiveCostAdjustedExcess", True):
        required.append(activation_checks["positiveCostAdjustedExcess"])
    if activation.get("requirePositiveRankIC", True):
        required.append(activation_checks["positiveRankIC"])
    if activation.get("requireNoMddDeterioration", True):
        required.append(activation_checks["noMddDeterioration"])
    earliest_review = validation_status.get("earliestReviewDate")
    first_signal = validation_status.get("firstSignalDate")
    if not earliest_review and first_signal:
        sessions = max(int(activation.get("minPaperDays", 252)) - 1,
                       int(local_cfg.get("horizonDays", 126)) + int(local_cfg.get("minUniqueDates", 63)) - 1)
        earliest_review = (pd.Timestamp(first_signal) + pd.offsets.BDay(sessions)).strftime("%Y-%m-%d")
    performance_missing = []
    for key in ("positiveCostAdjustedExcess", "positiveRankIC", "noMddDeterioration", "humanApproved"):
        if key != "humanApproved" or cfg.get("mode") == "active":
            if not activation_checks[key]:
                performance_missing.append(key)
    skeleton["validation"] = {
        "weightsPlusCashPct": round(total * 100, 6),
        "nonNegative": bool((final >= -1e-12).all()),
        "finite": bool(np.isfinite(final.to_numpy()).all()),
        "constraintsSatisfied": bool(caps_ok and abs(total - 1.0) <= 1e-6),
        "activationChecks": activation_checks,
        "sampleGate": shared_gate,
        "currentPaperDays": int(validation_status.get("paperDays") or 0),
        "currentMaturedSignals": int(validation_status.get("maturedSignals") or 0),
        "currentEffectiveDates": weakest_effective,
        "currentUniqueDates": weakest_unique,
        "earliestReviewDate": earliest_review,
        "missing": shared_gate["missing"] + performance_missing,
        "eligibleForActivation": bool(required and all(required)),
        "manualReviewRequired": True,
    }
    return skeleton
