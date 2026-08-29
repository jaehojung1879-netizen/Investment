"""Auditable concentrated model portfolio (selection + constrained Kelly).

Two separate decisions, kept separate on purpose:

1. WHICH names are held — ``select_portfolio``. The research layer publishes a
   6–12 name candidate sleeve per region; a portfolio has to answer a narrower
   question, so names are ranked by factor-rank edge per unit of realized
   downside risk and cut to a concentrated target (3–5 by default) under
   per-sector and per-region name limits. That score is a RANKING, never an
   expected return or a forecast Sharpe ratio, and the full cut is published
   with the reason each name was kept or dropped.
2. HOW MUCH of each — ``baseline_weights`` gives conviction-tilted inverse
   downside-volatility weights, which is what the portfolio actually uses until
   Kelly earns its way in.

The long-term alpha score is deliberately *not* treated as an expected return.
Expected excess returns come only from matured, point-in-time paper-ledger
outcomes. When that history or the covariance sample is insufficient the module
keeps the baseline allocation and says so, instead of inventing a mean.
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
    # Kelly is now driven by a posterior over two evidence classes, so "why is
    # it not on yet" has more than one answer. These say which one applies.
    "SHADOW_HISTORICAL_PRIOR", "SHADOW_POSTERIOR_READY",
}

# The baseline allocation used whether or not Kelly activates. It is a RANKING
# rule, never a return forecast: factor-rank edge per unit of realized downside
# risk decides *which* names are held, inverse-downside-vol decides how much.
SELECTION_METHOD = "ALPHA_RANK_PER_DOWNSIDE_RISK"
BASELINE_METHOD = "CONVICTION_TILTED_RISK_PARITY"
NEUTRAL_PERCENTILE = 50.0


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


def _sampling_step_days(index) -> int:
    """Business days between consecutive observations, read off the index."""
    try:
        stamps = pd.DatetimeIndex(index)
    except (TypeError, ValueError):
        return 1
    if len(stamps) < 2 or stamps.isna().any():
        return 1
    days = np.asarray(stamps.values, dtype="datetime64[D]")
    steps = np.busday_count(days[:-1], days[1:])
    steps = steps[steps > 0]
    if not len(steps):
        return 1
    return max(1, int(round(float(np.median(steps)))))


def _hac_lag(values: pd.Series, horizon: int) -> tuple[int, int, bool]:
    """Bartlett bandwidth in units of the SERIES, not of the trading calendar.

    ``horizon`` is a number of trading days, but the series handed to the HAC
    estimator is indexed on the replay grid. On a weekly grid a 126-session
    forward return overlaps about 26 observations, not 126 — so a lag of
    horizon-1 spends 125 lags describing an overlap that spans 25. Those extra
    lags are pure sampling noise, and because the Bartlett sum can only be
    truncated at zero, the noise systematically *shrinks* the estimated long-run
    variance. The t-statistic is then too large and the effective sample size too
    optimistic: on independent weekly data the old convention rejected a true
    null 20-45% of the time at a nominal 10%.

    So the overlap is converted into grid steps first, and then capped at n/4 —
    past that, each lag's autocovariance is an average of a handful of products
    and the estimator stops being informative. When the cap binds the caller is
    told, because a bandwidth-limited standard error is a floor, not a measurement.
    """
    n = len(values)
    if n < 2:
        return 0, 1, False
    step = _sampling_step_days(values.index)
    overlap = int(math.ceil(float(max(int(horizon), 1)) / step))
    wanted = max(0, overlap - 1)
    cap = int(min(max(1, n // 4), n - 1))
    return int(min(wanted, cap)), step, bool(wanted > cap)


def _newey_west_stats(values: pd.Series, horizon: int,
                       half_life_days: int | None = None) -> dict:
    """Date-clustered mean with Newey-West/HAC overlap correction.

    Forward returns overlap for roughly ``horizon`` sessions and behave like an
    MA(overlap-1) series, so Bartlett-kernel HAC at that explicit lag is the
    sampling rule rather than an arbitrary non-overlap heuristic. The lag is
    measured in observations of THIS series — see ``_hac_lag``. Limited
    exponential decay may affect the point estimate, never increase the
    effective sample size.
    """
    s = pd.to_numeric(values, errors="coerce").dropna().sort_index()
    n = len(s)
    if not n:
        return {"mean": 0.0, "se": None, "effectiveDates": 0,
                "uniqueDates": 0, "hacLag": 0,
                "samplingStepDays": 1, "bandwidthLimited": False}
    arr = s.to_numpy(dtype=float)
    if half_life_days and half_life_days > 0 and n > 1:
        age = np.arange(n - 1, -1, -1, dtype=float)
        weights = np.power(0.5, age / float(half_life_days))
        weights /= weights.sum()
        mean = float(weights @ arr)
    else:
        mean = float(arr.mean())
    centered = arr - mean
    lag, step_days, bandwidth_limited = _hac_lag(s, horizon)
    gamma0 = float(centered @ centered / n)
    long_run = gamma0
    for k in range(1, lag + 1):
        gamma = float(centered[k:] @ centered[:-k] / n)
        long_run += 2.0 * (1.0 - k / (lag + 1.0)) * gamma
    long_run = max(long_run, 0.0)
    se = math.sqrt(long_run / n) if n else None
    effective = n if long_run <= 1e-18 else int(max(1, min(n, math.floor(n * gamma0 / long_run))))
    return {"mean": mean, "se": se, "effectiveDates": effective,
            "uniqueDates": n, "hacLag": lag,
            "samplingStepDays": step_days,
            "bandwidthLimited": bandwidth_limited}


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


# How the turnover in a cost estimate was arrived at. The distinction matters
# because the number drives position size: `net = raw - cost` feeds the
# expected excess return that Kelly sizes on, so a turnover assumed lower than
# the strategy's own measured behaviour inflates every candidate.
TURNOVER_MEASURED = "MEASURED_REPLAY_TURNOVER"
TURNOVER_ASSUMED = "CONFIG_ASSUMPTION"
# The region's own measured replacement rate, as opposed to the portfolio-level
# one applied to every region alike. Distinguished because they are different
# quantities, not two estimates of one: see `measured_turnover_by_region`.
TURNOVER_MEASURED_REGIONAL = "MEASURED_REPLAY_TURNOVER_REGIONAL"
# A 3-5 name book split by region holds 2-3 names a side, so one name replaced
# moves the rate 33-50 points. The mean over enough rebalances is still the
# rate; a mean over a handful is one or two swaps wearing a decimal point. Below
# this the region falls back to the portfolio measurement, which is quieter.
MIN_REGIONAL_TURNOVER_REBALANCES = 20
# A replay turnover outside this band is not believable as a rebalance rate and
# is more likely a report from a different definition or a broken path.
TURNOVER_BOUNDS = (1.0, 200.0)


def measured_turnover_pct(portfolio_validation: dict | None,
                          cfg: dict) -> tuple[float | None, str, dict]:
    """What the replay actually turned over, at THIS rebalance frequency.

    config.json assumes 25%. On the replay ledger the production selector
    measured 59.3% at the 63-day horizon, which is also `rebalanceDays` — so
    the cost hurdle every candidate had to clear was 42% of the real one.

    The horizon has to match the rebalance frequency or the number means
    something else: a 21-day path turns over less per rebalance and a 252-day
    path more, and picking whichever exists would make the hurdle a function of
    which horizons happened to mature. No match, no measurement.

    The caller is responsible for the generation check — `build._load_historical
    _evidence` already replaces a report from another replay generation with an
    unavailable stub, which lands here as no measurement rather than as a stale
    one.
    """
    detail: dict = {"turnoverSource": TURNOVER_ASSUMED}
    replay = ((portfolio_validation or {}).get("portfolioReplay") or {})
    selectors = replay.get("selectors") or {}
    blob = selectors.get(SELECTION_METHOD) or {}
    horizons = blob.get("horizons") or {}
    regional = (cfg.get("transactionCosts") or {})
    wanted = {int(row.get("rebalanceDays", 63))
              for row in regional.values() if isinstance(row, dict)} or {63}
    if len(wanted) != 1:
        detail["turnoverNote"] = "REBALANCE_DAYS_DIFFER_BY_REGION"
        return None, TURNOVER_ASSUMED, detail
    horizon = next(iter(wanted))
    path = ((horizons.get(str(horizon)) or horizons.get(horizon) or {}).get("path") or {})
    if not path or path.get("available") is False:
        detail["turnoverNote"] = f"NO_MEASURED_PATH_AT_{horizon}D"
        return None, TURNOVER_ASSUMED, detail
    value = path.get("averageTurnoverPct")
    try:
        value = float(value)
    except (TypeError, ValueError):
        detail["turnoverNote"] = f"NO_MEASURED_PATH_AT_{horizon}D"
        return None, TURNOVER_ASSUMED, detail
    low, high = TURNOVER_BOUNDS
    if not (low <= value <= high):
        detail["turnoverNote"] = "MEASURED_TURNOVER_IMPLAUSIBLE"
        return None, TURNOVER_ASSUMED, detail
    detail = {"turnoverSource": TURNOVER_MEASURED,
              "turnoverMeasuredAtHorizonDays": horizon,
              "turnoverMeasuredFromSelector": SELECTION_METHOD}
    return value, TURNOVER_MEASURED, detail


def measured_turnover_by_region(portfolio_validation: dict | None,
                                cfg: dict) -> dict[str, float]:
    """Each region's own measured replacement rate, where the path measured one.

    This is NOT the portfolio figure split up. `estimate_transaction_cost`
    multiplies its turnover by ONE candidate's position, so the quantity it
    needs is "of the weight held in this region, what share is traded per
    rebalance" — a share of the sleeve, not of the book. The two differ by more
    than bookkeeping: on the replay ledger the portfolio figure is 58.1% while
    the sleeves measure 85.3% (US) and 63.1% (KR), because the book carries cash
    and the position does not.

    That the sleeves differ is established, not read off two point estimates:
    the paired US-KR difference over the 50 shared rebalances is +22.20pp with
    a 95% bootstrap interval of [+9.83, +34.09]pp, and US churned more in 34 of
    them (3 tied). Had the interval spanned zero, one number would have been
    adequate and this function should not exist.

    Same admission rules as the portfolio measurement — production selector, a
    horizon equal to `rebalanceDays`, a plausible value — plus a floor on how
    many rebalances the region was actually measured over.
    """
    _, source, detail = measured_turnover_pct(portfolio_validation, cfg)
    if source != TURNOVER_MEASURED:
        return {}
    horizon = detail["turnoverMeasuredAtHorizonDays"]
    replay = ((portfolio_validation or {}).get("portfolioReplay") or {})
    blob = (replay.get("selectors") or {}).get(SELECTION_METHOD) or {}
    horizons = blob.get("horizons") or {}
    path = ((horizons.get(str(horizon)) or horizons.get(horizon) or {}).get("path") or {})
    by_region = path.get("averageTurnoverPctByRegion") or {}
    counts = path.get("turnoverRebalancesByRegion") or {}
    low, high = TURNOVER_BOUNDS
    out: dict[str, float] = {}
    for region, value in by_region.items():
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if not (low <= value <= high):
            continue
        if int(counts.get(region, 0) or 0) < MIN_REGIONAL_TURNOVER_REBALANCES:
            continue
        out[region] = value
    return out


def with_measured_turnover(cfg: dict, portfolio_validation: dict | None) -> dict:
    """cfg with each region's assumed turnover replaced by the measured one.

    A copy, not a mutation: the config object is shared and a cost assumption
    that silently changed underneath other callers would be its own bug.

    A region gets its OWN measured rate when the replay measured one over enough
    rebalances, because the sleeves do not turn over alike — the US sleeve is
    replaced whole in more than half of rebalances and the Korean one is not.
    Where the region has no usable measurement the portfolio-level figure stands
    in, and where there is none of either the configured assumption survives.
    `turnoverSource` says which of the three each region got, so a hurdle is
    never read as measured when it was inherited or assumed.
    """
    value, source, detail = measured_turnover_pct(portfolio_validation, cfg)
    regional = measured_turnover_by_region(portfolio_validation, cfg)
    out = dict(cfg)
    costs = {}
    for region, row in (cfg.get("transactionCosts") or {}).items():
        row = dict(row) if isinstance(row, dict) else {}
        row.update(detail)
        if region in regional:
            row["assumedTurnoverPct"] = regional[region]
            row["turnoverSource"] = TURNOVER_MEASURED_REGIONAL
            row["turnoverNote"] = None
        elif value is not None:
            row["assumedTurnoverPct"] = value
            # A region measured elsewhere but not here is wearing another
            # sleeve's rate. Silence would read as its own.
            if regional:
                row["turnoverNote"] = "NO_REGIONAL_MEASUREMENT_PORTFOLIO_RATE_USED"
        costs[region] = row
    out["transactionCosts"] = costs
    return out


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
        # Whether that turnover was measured from the replay or assumed by
        # config. It changes the number that gets subtracted from every
        # candidate's expected return, so it is published rather than implied.
        "turnoverSource": regional.get("turnoverSource", TURNOVER_ASSUMED),
        "turnoverNote": regional.get("turnoverNote"),
        "turnoverMeasuredAtHorizonDays": regional.get("turnoverMeasuredAtHorizonDays"),
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
                              cfg: dict, as_of: str | pd.Timestamp | None = None,
                              historical_calibration: dict | None = None,
                              macro_regime: dict | None = None) -> list[dict]:
    """Estimate cost-adjusted 126d excess returns from matured OOS outcomes.

    Candidate alpha percentiles are used only to select a historical calibration
    bucket; the alpha score itself never enters a return formula.

    Two evidence classes may contribute:

    ``outcomes``                 the PROSPECTIVE paper ledger — signals recorded
                                 going forward and left alone until they matured.
    ``historical_calibration``   the HISTORICAL OOS ledger — the same model
                                 replayed against point-in-time data, with the
                                 evidence discount already applied per bucket.

    With no ``historical_calibration`` the behaviour is exactly what it was: a
    thin prospective ledger yields 0 and Kelly stays off. With one, the two are
    combined by precision (``pipeline.evidence.combine``), so an empty
    prospective ledger no longer forces the expected return to 0 — it forces it
    to the discounted historical prior, which is a measured quantity rather than
    an assumption of no edge.
    """
    from . import evidence as evidence_mod

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

        # ---- Posterior over the two evidence classes -----------------------
        # Without a historical calibration this block is inert and the legacy
        # prospective-only estimate above stands unchanged.
        historical_prior = evidence_mod.candidate_prior(
            historical_calibration, region, candidate.get("alphaPercentile"),
            macro_regime=(macro_regime or {}).get("regime"),
            entry_state=((candidate.get("entry") or {}).get("entryState")
                         or candidate.get("entryState")))
        probability_distribution = ((historical_prior or {})
                                    .get("probabilityDistribution"))
        evidence_block = None
        posterior_expected = expected
        posterior_status = "SHADOW" if sufficient else "SHADOW_INSUFFICIENT_HISTORY"
        if historical_prior is not None:
            # Feed the UNSHRUNK cost-adjusted mean and its standard error; the
            # zero-mean prior inside combine() does the shrinking, so a thin
            # sample is not penalized twice.
            prospective_source = None
            if eff > 0 and se is not None:
                prospective_source = {
                    "expectedExcessReturnPct": round(net * haircut * 100, 3),
                    "standardErrorPct": round(float(se) * 100, 4),
                    "effectiveDates": eff, "uniqueDates": ndates,
                    "weight": 1.0, "evidenceClass": "PROSPECTIVE_PAPER",
                }
            evidence_block = evidence_mod.combine(
                historical_prior, prospective_source,
                prior_scale_pct=float(cfg.get("evidencePriorScalePct", 3.0)))
            evidence_block["activation"] = evidence_mod.activation_status(
                historical=historical_prior, prospective=prospective_source,
                min_effective_dates=min_eff, gate_passed=bool(sufficient),
                mode=cfg.get("mode", "shadow"))
            evidence_block["drift"] = evidence_mod.drift_report(
                historical_prior, prospective_source)
            evidence_block["historicalBucket"] = historical_prior.get("bucket")
            evidence_block["historicalQuality"] = historical_prior.get("quality")
            evidence_block["historical"]["probabilityDistribution"] = probability_distribution
            posterior_expected = float(evidence_block["posterior"]["expectedExcessReturnPct"]) / 100.0
            posterior_status = "SHADOW"

        result.append({
            "ticker": candidate["ticker"], "region": region, "horizonDays": horizon,
            "expectedExcessReturnPct": round(posterior_expected * 100, 3),
            "prospectiveOnlyExpectedExcessReturnPct": round(expected * 100, 3),
            "evidence": evidence_block,
            "probabilityDistribution": probability_distribution,
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
            "status": posterior_status,
            "prospectiveGatePassed": bool(sufficient),
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


def _risk_unit(candidate: dict) -> float | None:
    """Realized downside volatility (fraction), falling back to total vol."""
    risk = candidate.get("risk") or {}
    for key in ("downsideVolPct", "vol252Pct"):
        value = risk.get(key)
        if value is not None and float(value) > 0:
            return float(value) / 100.0
    return None


def conviction_scores(candidates: list[dict], cfg: dict) -> list[dict]:
    """Rank candidates by factor-rank edge per unit of realized downside risk.

    This is deliberately NOT an expected return, a Sharpe ratio forecast, or a
    probability. ``alphaPercentile`` is a cross-sectional *rank* produced by the
    research layer; dividing its distance above the median by realized downside
    volatility gives an auditable ordering of "how much rank edge am I paid per
    unit of the risk I actually observed". Evidence coverage and the entry-state
    multiplier can only shrink it, never inflate it.
    """
    selection = cfg.get("selection") or {}
    floor_pct = float(selection.get("minAlphaPercentile", 66))
    units = [u for u in (_risk_unit(c) for c in candidates) if u is not None]
    median_unit = float(np.median(units)) if units else 0.25
    rows = []
    for candidate in candidates:
        percentile = candidate.get("alphaPercentile")
        risk_unit = _risk_unit(candidate) or median_unit
        state_multiplier = _state_multiplier(candidate, cfg)
        evidence = float(candidate.get("evidenceCoverage") or candidate.get("factorCoverage") or 0.0)
        edge = (float(percentile) - NEUTRAL_PERCENTILE) / (100.0 - NEUTRAL_PERCENTILE) if percentile is not None else 0.0
        edge = max(0.0, edge)
        score = edge / max(risk_unit, 0.05) * evidence * state_multiplier
        excluded = []
        if percentile is None or float(percentile) < floor_pct:
            excluded.append("ALPHA_BELOW_SELECTION_FLOOR")
        if state_multiplier <= 0:
            excluded.append("ENTRY_OR_RESEARCH_STATE_BLOCKS_SIZING")
        if evidence <= 0:
            excluded.append("NO_FACTOR_EVIDENCE")
        rows.append({
            "ticker": candidate["ticker"], "region": candidate.get("region") or "UNKNOWN",
            "sector": candidate.get("sector") or "Unclassified",
            "alphaPercentile": percentile,
            "downsideVolPct": round(risk_unit * 100, 1),
            "riskUnitFallback": _risk_unit(candidate) is None,
            "evidenceCoverage": round(evidence, 3),
            "entryStateMultiplier": round(state_multiplier, 3),
            "convictionScore": round(float(score), 4),
            "eligible": not excluded, "exclusionCodes": excluded,
        })
    rows.sort(key=lambda r: (-r["convictionScore"], -(r["alphaPercentile"] or -1),
                             r["downsideVolPct"], str(r["ticker"])))
    return rows


def _select_scored(candidates: list[dict], scored: list[dict], cfg: dict,
                   *, method: str, score_formula_ko: str,
                   not_a_forecast_ko: str) -> tuple[list[dict], dict]:
    """Apply the production name/sector/region constraints to a ranked list.

    The ranking source is deliberately injected while every eligibility and
    diversification rule stays in one place. Production passes conviction
    scores; historical A/B may pass a maturity-safe expected-return ranking.
    This prevents the challenger replay from quietly using looser caps.
    """
    selection = cfg.get("selection") or {}
    target = int(selection.get("targetNames", cfg.get("maxNames", 12)))
    min_names = int(selection.get("minNames", 1))
    per_sector = int(selection.get("maxNamesPerSector", target))
    per_region = int(selection.get("maxNamesPerRegion", target))
    by_ticker = {c["ticker"]: c for c in candidates}

    chosen: list[str] = []
    sector_count: dict[str, int] = {}
    region_count: dict[str, int] = {}
    for row in scored:
        if len(chosen) >= target:
            row.setdefault("exclusionCodes", []).append("BELOW_TARGET_COUNT_CUTOFF")
            continue
        if not row["eligible"]:
            continue
        if sector_count.get(row["sector"], 0) >= per_sector:
            row["exclusionCodes"].append("SECTOR_NAME_LIMIT")
            continue
        if region_count.get(row["region"], 0) >= per_region:
            row["exclusionCodes"].append("REGION_NAME_LIMIT")
            continue
        chosen.append(row["ticker"])
        sector_count[row["sector"]] = sector_count.get(row["sector"], 0) + 1
        region_count[row["region"]] = region_count.get(row["region"], 0) + 1
    selected_set = set(chosen)
    for row in scored:
        row["selected"] = row["ticker"] in selected_set
    meta = {
        "method": method,
        "scoreFormulaKo": score_formula_ko,
        "notAForecastKo": not_a_forecast_ko,
        "targetNames": target, "minNames": min_names,
        "maxNamesPerSector": per_sector, "maxNamesPerRegion": per_region,
        "minAlphaPercentile": float(selection.get("minAlphaPercentile", 66)),
        "consideredCount": len(candidates),
        "eligibleCount": sum(1 for r in scored if r["eligible"]),
        "selectedCount": len(chosen),
        "shortfall": len(chosen) < min_names,
        # Selected names plus the nearest misses: enough to audit the cut
        # without shipping the whole cross-section twice.
        "ranking": [r for r in scored if r["selected"]] + [r for r in scored if not r["selected"]][:8],
    }
    return [by_ticker[t] for t in chosen], meta


def select_portfolio(candidates: list[dict], cfg: dict) -> tuple[list[dict], dict]:
    """Cut the research candidate list down to a portfolio that can be held.

    A 6–12 name research sleeve per region answers "what is interesting". A
    portfolio has to answer "what do I own", so the selection is explicitly
    concentrated and the reason each name did or did not make the cut is kept.
    """
    return _select_scored(
        candidates, conviction_scores(candidates, cfg), cfg,
        method=SELECTION_METHOD,
        score_formula_ko=(
            "(알파 백분위 − 50) ÷ 50 ÷ 하방변동성 × 근거 커버리지 × 진입상태 배율"),
        not_a_forecast_ko=(
            "종목을 고르기 위한 순위 점수이며 기대수익률·샤프비율 예측이 아닙니다."),
    )


def select_portfolio_by_scores(candidates: list[dict], scored: list[dict],
                               cfg: dict, *, method: str) -> tuple[list[dict], dict]:
    """Constraint-identical selector entry point for a named challenger.

    Callers must supply rows with ``ticker``, ``region``, ``sector``, a numeric
    score and an explicit ``eligible`` flag. The function is intentionally not
    connected to production promotion.
    """
    normalized = []
    for row in scored:
        item = dict(row)
        item.setdefault("convictionScore", item.get("score", 0.0))
        item.setdefault("alphaPercentile", None)
        item.setdefault("downsideVolPct", None)
        item.setdefault("evidenceCoverage", 0.0)
        item.setdefault("eligible", False)
        item.setdefault("exclusionCodes", [])
        normalized.append(item)
    normalized.sort(key=lambda r: (-float(r.get("score") or r.get("convictionScore") or 0.0),
                                   str(r.get("ticker") or "")))
    return _select_scored(
        candidates, normalized, cfg, method=method,
        score_formula_ko="만기된 과거 기대 초과수익 ÷ 하방변동성 × 진입상태 배율",
        not_a_forecast_ko=(
            "해당 시점까지 만기된 과거 OOS만 사용한 challenger 순위이며 production을 바꾸지 않습니다."),
    )


def challenger_selection(candidates: list[dict], estimates: list[dict],
                         cfg: dict) -> dict:
    """A/B the production selector against a calibrated-expected-return selector.

    Production (CHAMPION) ranks by ``alpha rank edge / downside risk``. Once the
    historical calibration is trustworthy, an obvious alternative is to rank by
    ``calibrated expected excess return / downside risk`` — an actual return per
    unit of risk rather than a rank per unit of risk.

    That alternative is NOT wired into production here, deliberately. Swapping
    the selector the moment a calibration exists would make the portfolio a
    function of a backtest, which is the failure mode this whole layer is built
    to avoid. What this function does is publish both rankings and their overlap
    so the two can be compared on the same evidence over time; promotion stays a
    human decision gated on both evidence classes agreeing.
    """
    expected = {e["ticker"]: e for e in estimates}
    champion = conviction_scores(candidates, cfg)
    champion_order = [row["ticker"] for row in champion if row["eligible"]]

    challenger_rows = []
    for candidate in candidates:
        ticker = candidate["ticker"]
        estimate = expected.get(ticker) or {}
        mu = estimate.get("expectedExcessReturnPct")
        risk_unit = _risk_unit(candidate)
        if mu is None or risk_unit is None or risk_unit <= 0:
            continue
        state_multiplier = _state_multiplier(candidate, cfg)
        challenger_rows.append({
            "ticker": ticker, "region": candidate.get("region") or "UNKNOWN",
            "expectedExcessReturnPct": mu,
            "downsideVolPct": round(risk_unit * 100, 1),
            "entryStateMultiplier": round(state_multiplier, 3),
            "score": round(float(mu) / (risk_unit * 100) * state_multiplier, 4),
            "evidenceClass": ("POSTERIOR" if (estimate.get("evidence") or {}).get("posterior")
                              else "PROSPECTIVE_ONLY"),
        })
    challenger_rows.sort(key=lambda r: (-r["score"], str(r["ticker"])))
    target = int((cfg.get("selection") or {}).get("targetNames", 5))
    champion_top = champion_order[:target]
    challenger_top = [r["ticker"] for r in challenger_rows][:target]
    overlap = sorted(set(champion_top) & set(challenger_top))
    return {
        "champion": {"method": SELECTION_METHOD, "top": champion_top},
        "challenger": {"method": "CALIBRATED_EXPECTED_RETURN_PER_DOWNSIDE_RISK",
                       "top": challenger_top, "ranking": challenger_rows[:12]},
        "overlapCount": len(overlap), "overlap": overlap,
        "agreementPct": round(100.0 * len(overlap) / max(1, len(champion_top)), 1),
        "inProduction": "champion",
        "promotionPolicyKo": ("challenger는 과거 OOS와 실시간 paper 양쪽에서 명확히 우세할 때만 "
                               "승격 검토 대상이며, calibration이 생겼다는 이유만으로 "
                               "production 선정기를 교체하지 않습니다."),
    }


def baseline_weights(selected: list[dict], cfg: dict,
                     ranking_rows: list[dict] | None = None) -> dict:
    """Conviction-tilted inverse-downside-volatility weights for the held set.

    Inverse downside vol sets the risk-parity base; the conviction *rank* inside
    the selected set applies a bounded linear tilt (0.5x…1.5x) so a higher-ranked
    name is not forced to the same size as the last name in. Nothing here claims
    a return; capital that cannot be placed under the caps stays in cash.
    """
    if not selected:
        return {}
    tilt_range = float((cfg.get("selection") or {}).get("convictionTiltRange", 1.0))
    ranking_rows = ranking_rows or conviction_scores(selected, cfg)
    score_by_ticker = {
        row["ticker"]: float(row.get("score") or row.get("convictionScore") or 0.0)
        for row in ranking_rows
    }
    order = sorted(selected, key=lambda c: (-score_by_ticker.get(c["ticker"], 0.0),
                                             str(c["ticker"])))
    n = len(order)
    raw = {}
    for rank, candidate in enumerate(order):
        risk_unit = _risk_unit(candidate) or 0.25
        tilt = 1.0 if n == 1 else 1.0 + tilt_range * (0.5 - rank / (n - 1))
        raw[candidate["ticker"]] = tilt / max(risk_unit, 0.05)
    total = sum(raw.values())
    budget = 1.0 - float(cfg.get("minCashPct", 10)) / 100.0
    if total > 0:
        raw = {t: w / total * budget for t, w in raw.items()}
    capped, _ = _cap_portfolio(pd.Series(raw, dtype=float), selected, cfg, {})
    return capped.to_dict()


def selection_and_baseline(candidates: list[dict], cfg: dict,
                           macro_regime: dict | None = None, *,
                           scored: list[dict] | None = None,
                           method: str = SELECTION_METHOD) -> dict:
    """Pure production selection + baseline allocation decision.

    Live construction and historical portfolio replay both call this function.
    It owns the macro-implied cash floor, concentrated selection and the
    conviction/ranking-tilted inverse-downside-volatility weights. Kelly is a
    later allocation layer and is deliberately absent here.
    """
    _, _, regime_cash, macro_warnings = _regime_adjustment(macro_regime, cfg)
    local_cfg = dict(cfg)
    local_cfg["minCashPct"] = max(float(cfg.get("minCashPct", 10)), regime_cash)
    if scored is None:
        selected, selection = select_portfolio(candidates, local_cfg)
        ranking = selection.get("ranking") or []
    else:
        selected, selection = select_portfolio_by_scores(
            candidates, scored, local_cfg, method=method)
        ranking = scored
    weights = baseline_weights(selected, local_cfg, ranking_rows=ranking)
    serialized, cash_pct = _serialize_allocation(pd.Series(weights, dtype=float))
    return {
        "selected": selected,
        "selection": selection,
        "rawWeights": weights,
        "weights": serialized,
        "cashPct": cash_pct,
        "appliedMinCashPct": round(float(local_cfg["minCashPct"]), 2),
        "macroWarnings": macro_warnings,
        "method": method,
        "baselineMethod": BASELINE_METHOD,
    }


def concentration_diagnostics(weights: pd.Series, cfg: dict) -> dict:
    """Report the concentration the portfolio actually carries."""
    held = weights[weights > 1e-9].sort_values(ascending=False)
    invested = float(held.sum())
    if invested <= 0:
        return {"names": 0, "effectiveNames": None, "top1WeightPct": None,
                "top3WeightPct": None, "herfindahl": None, "warnings": ["NO_INVESTED_WEIGHT"]}
    share = held / invested
    herfindahl = float((share ** 2).sum())
    effective = 1.0 / herfindahl if herfindahl > 0 else None
    warnings = []
    if len(held) <= 3:
        warnings.append("SINGLE_DIGIT_NAME_COUNT_IDIOSYNCRATIC_RISK")
    if effective is not None and effective < 2.5:
        warnings.append("EFFECTIVE_NAMES_BELOW_2_5")
    if float(share.iloc[0]) > 0.4:
        warnings.append("TOP_NAME_ABOVE_40PCT_OF_EQUITY")
    return {
        "names": int(len(held)),
        "effectiveNames": round(effective, 2) if effective is not None else None,
        "top1WeightPct": round(float(held.iloc[0]) * 100, 2),
        "top3WeightPct": round(float(held.iloc[:3].sum()) * 100, 2),
        "herfindahl": round(herfindahl, 4),
        "basisKo": "유효 종목수 = 1 ÷ 주식비중 허핀달지수",
        "warnings": warnings,
    }


def _regime_adjustment(macro_regime: dict | None, cfg: dict) -> tuple[str, float, float, list[str]]:
    """Translate the macro layer into a Kelly multiplier and a cash floor.

    The dashboard used to publish a macro equity budget (say 20–45%) next to a
    portfolio holding 75% equity, because the cash floor came only from the
    regime table. The published budget's upper bound is now binding, so the two
    layers cannot contradict each other on screen.
    """
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
    cash_floor = float(row.get("minCashPct", cfg.get("minCashPct", 10)))
    equity_range = ((macro_regime.get("riskBudget") or {}).get("equityRangePct") or [])
    if len(equity_range) == 2:
        budget_floor = 100.0 - float(equity_range[1])
        if budget_floor > cash_floor:
            cash_floor = budget_floor
            warnings.append("CASH_FLOOR_SET_BY_MACRO_EQUITY_BUDGET")
    return label, multiplier, cash_floor, warnings


def _probability_gate(estimates: list[dict], candidates: list[dict], cfg: dict) -> dict:
    """Require an audited up/down distribution before Kelly can change weights.

    Expected return and covariance are sufficient mathematical inputs to the
    multivariate Kelly approximation.  They are not sufficient *evidence* for
    this product: the user must also be able to see whether the corresponding
    direction probability was calibrated out of time.  Missing or unreliable
    probability evidence therefore preserves the baseline allocation.
    """
    policy = cfg.get("probabilityCalibration") or {}
    # Backward-compatible for library callers that supply a minimal config;
    # production config opts in explicitly and the artifact publishes the flag.
    required = bool(policy.get("requiredForKelly", False))
    by_region: dict[str, dict] = {}
    expected = {row.get("ticker"): row for row in estimates}
    for region in sorted({c.get("region") or "UNKNOWN" for c in candidates}):
        names = [c.get("ticker") for c in candidates
                 if (c.get("region") or "UNKNOWN") == region]
        distributions = [
            (expected.get(ticker) or {}).get("probabilityDistribution")
            for ticker in names
        ]
        present = [row for row in distributions if row]
        reliable = [row for row in present if row.get("reliabilityEligible")]
        representative = reliable[0] if reliable else (present[0] if present else {})
        eligible = bool(present) and len(present) == len(names) and len(reliable) == len(present)
        statistical_failures = ((representative.get("reliabilityGate") or {}).get("failures") or [])
        integrity_failures = ((representative.get("integrityGate") or {}).get("failures") or [])
        by_region[region] = {
            "eligible": eligible,
            "candidates": len(names),
            "distributionsAvailable": len(present),
            "reliableDistributions": len(reliable),
            "selectedVariant": representative.get("selectedVariant"),
            "audit": representative.get("audit"),
            "failures": (list(dict.fromkeys([*statistical_failures, *integrity_failures]))
                         or (["probability_distribution_missing"] if not present else [])),
        }
    eligible = bool(by_region) and all(row["eligible"] for row in by_region.values())
    return {
        "requiredForKelly": required,
        "eligible": bool(eligible or not required),
        "byRegion": by_region,
        "failures": [region for region, row in by_region.items() if not row["eligible"]],
        "fallbackPolicyKo": ("상승확률이 만기 인지형 워크포워드 감사에서 신뢰도 기준을 "
                             "통과하지 못하면 Kelly 비중은 공개하지 않고 기준 위험가중을 유지합니다."),
    }


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
                          bench_by_region: dict | None = None,
                          historical_calibration: dict | None = None) -> dict:
    """Top-level assembly from calibrated returns through final blended weights."""
    from . import evidence as evidence_mod

    cfg, themes, prior_weights = cfg or {}, themes or {}, prior_weights or {}
    benchmarks, bench_by_region = benchmarks or {}, bench_by_region or {}
    validation_status = validation_status or {}
    base = float(cfg.get("kellyFraction", 0.25))
    blend = float(cfg.get("blendWeight", 0.25))
    label, regime_mult, regime_cash, warnings = _regime_adjustment(macro_regime, cfg)
    local_cfg = dict(cfg)
    local_cfg["minCashPct"] = max(float(cfg.get("minCashPct", 10)), regime_cash)
    macro_equity_range = ((macro_regime or {}).get("riskBudget") or {}).get("equityRangePct")
    applied = base * regime_mult
    skeleton = {
        "status": "SHADOW_INSUFFICIENT_HISTORY", "method": "BLENDED_CONSTRAINED_FRACTIONAL_KELLY",
        "horizonDays": int(cfg.get("horizonDays", 126)), "baseKellyFraction": base,
        "regime": label, "regimeMultiplier": round(regime_mult, 4),
        "macroEquityRangePct": macro_equity_range,
        "appliedMinCashPct": round(float(local_cfg["minCashPct"]), 2),
        "appliedKellyFraction": round(applied, 4), "kellyBlendWeight": blend,
        "riskWeightedBlendWeight": 1.0 - blend, "cashPct": 100.0,
        "expectedVolPct": None, "estimatedMaxDrawdownPct": None, "turnoverPct": 0.0,
        "expectedReturnStatus": "INSUFFICIENT", "fallbackReason": None,
        "probabilityGate": {"requiredForKelly": bool(
            (cfg.get("probabilityCalibration") or {}).get("requiredForKelly", False)),
            "eligible": False, "byRegion": {}, "failures": ["not_evaluated"]},
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

    all_candidates = sorted(_candidate_rows(long_term), key=lambda c: str(c.get("ticker") or ""))
    if len(all_candidates) < int(local_cfg.get("minNames", 6)):
        skeleton["fallbackReason"] = "longterm_candidates_below_minimum"
        return skeleton
    baseline_decision = selection_and_baseline(all_candidates, cfg, macro_regime)
    candidates = baseline_decision["selected"]
    selection_meta = baseline_decision["selection"]
    local_cfg["minCashPct"] = baseline_decision["appliedMinCashPct"]
    skeleton["appliedMinCashPct"] = baseline_decision["appliedMinCashPct"]
    skeleton["selection"] = selection_meta
    skeleton["baselineMethod"] = BASELINE_METHOD
    if not candidates:
        skeleton["fallbackReason"] = "no_candidate_passed_portfolio_selection"
        skeleton["warnings"].append("SELECTION_EMPTY; ALL_CASH")
        return skeleton
    risk_weights = baseline_decision["rawWeights"]
    estimates = estimate_expected_returns(
        candidates, outcomes, local_cfg, as_of=as_of,
        historical_calibration=historical_calibration, macro_regime=macro_regime)
    estimate_map = {e["ticker"]: e for e in estimates}
    sufficient = [e for e in estimates if e["status"] == "SHADOW"]
    skeleton["expectedReturnEstimates"] = estimates
    probability_gate = _probability_gate(estimates, candidates, local_cfg)
    skeleton["probabilityGate"] = probability_gate

    # Evidence layer: which class of evidence is carrying the expected returns,
    # and is the live world still reproducing the backtest?
    region_evidence = {}
    for estimate in estimates:
        block = estimate.get("evidence")
        if block:
            region_evidence.setdefault(estimate["region"], block)
    drift = evidence_mod.portfolio_drift(region_evidence) if region_evidence else None
    if drift and drift.get("detected"):
        # A live shortfall against history shrinks risk. It can never raise it.
        applied *= float(drift["kellyMultiplier"])
        warnings.append("MODEL_DRIFT_KELLY_REDUCED")
    ladder = [block.get("activation") or {} for block in region_evidence.values()]
    weakest = min(ladder, key=lambda a: a.get("ladderIndex", 0)) if ladder else None
    skeleton["kellyEvidence"] = {
        "byRegion": region_evidence,
        "drift": drift,
        "activation": weakest,
        "historicalCalibrationAvailable": bool(
            (historical_calibration or {}).get("available")),
        "evidenceSeparationKo": ("과거 OOS 증거와 실시간 paper 증거는 별도로 집계한 뒤 "
                                  "정밀도 가중으로 결합합니다. 하나로 섞어 보관하지 않습니다."),
    }
    skeleton["appliedKellyFraction"] = round(applied, 4)
    # Published for comparison only — the champion still picks the holdings.
    skeleton["selectionAbTest"] = challenger_selection(candidates, estimates, local_cfg)

    fallback_reason = None
    unconstrained: dict[str, float] = {}
    kelly_weights: dict[str, float] = {}
    covariance_by_region: dict[str, dict] = {}
    covariance_matrices: dict[str, pd.DataFrame] = {}
    # Active covariance is estimated for the held names whether or not Kelly is
    # active: the portfolio's tracking error is reportable from prices alone and
    # should not go dark just because the return ledger is still thin.
    for region in sorted({c.get("region") or "UNKNOWN" for c in candidates}):
        region_tickers = [c["ticker"] for c in candidates if (c.get("region") or "UNKNOWN") == region]
        cov, cov_meta = estimate_active_covariance(
            prices, region_tickers, bench_by_region.get(region), local_cfg,
            region=region, benchmark=benchmarks.get(region) or "UNKNOWN",
        )
        covariance_by_region[region] = cov_meta
        if cov is not None:
            covariance_matrices[region] = cov
    if len(sufficient) < int(local_cfg.get("minNames", 6)):
        fallback_reason = "expected_return_history_insufficient"
    elif probability_gate.get("requiredForKelly") and not probability_gate.get("eligible"):
        fallback_reason = "probability_calibration_unreliable"
        warnings.append("PROBABILITY_GATE_FAILED; KELLY_WITHHELD")
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
            cov = covariance_matrices.get(region)
            if cov is None or not set(c["ticker"] for c in region_candidates) <= set(cov.index):
                cov, cov_meta = estimate_active_covariance(
                    prices, [c["ticker"] for c in region_candidates], bench_by_region.get(region),
                    local_cfg, region=region, benchmark=benchmarks.get(region) or "UNKNOWN",
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
        # Regions are optimized one at a time, so a later region failing leaves
        # an EARLIER region's solved weights sitting in the accumulator. Those
        # weights are not the portfolio — the portfolio fell back — and
        # publishing them would show a Kelly allocation the model is not
        # standing behind. Discard them before serializing.
        #
        # This became reachable the moment expected returns could come from a
        # historical prior: one region having a usable calibration bucket while
        # the other does not is the ordinary case, not an edge case.
        partial = bool(kelly_weights)
        kelly_weights.clear()
        unconstrained.clear()
        final = pd.Series(risk_weights, dtype=float)
        final, bindings = _cap_portfolio(final, candidates, local_cfg, themes)
        skeleton["fallbackReason"] = fallback_reason
        skeleton["warnings"].append("KELLY_NOT_ACTIVATED; EXISTING_RISK_WEIGHTED_PORTFOLIO_RETAINED")
        if partial:
            skeleton["warnings"].append("PARTIAL_REGION_KELLY_SOLUTION_DISCARDED")
        # "Not activated" now has more than one cause, and the difference
        # matters to the reader: no evidence at all is a different situation
        # from a usable historical prior that has not yet been joined by live
        # confirmation.
        activation_code = (weakest or {}).get("code")
        if activation_code in {"HISTORICAL_PRIOR_ONLY", "HISTORICAL_OOS_SUPPORTED"}:
            skeleton["status"] = "SHADOW_HISTORICAL_PRIOR"
    else:
        blended = blend_with_risk_weighted_portfolio(risk_weights, kelly_weights, candidates,
                                                       local_cfg, themes, prior_weights)
        final, bindings = blended["weights"], blended["bindingConstraints"]
        skeleton["status"] = "SHADOW_READY" if cfg.get("mode", "shadow") == "shadow" else "ACTIVE_PAPER"
        skeleton["expectedReturnStatus"] = "SHADOW"
        skeleton["kellyApplied"] = True

    sector_exp, theme_exp, region_exp = _exposures(final, candidates, themes)
    prior = pd.Series({t: float(prior_weights.get(t, 0.0)) for t in final.index})
    # Without a prior production state there is nothing to turn over; the number
    # is the cost of building the book from cash, and is labelled as such.
    turnover = 0.5 * float((final - prior).abs().sum()) if prior_weights else float(final.sum())
    skeleton["turnoverBasis"] = "VS_PRIOR_STATE" if prior_weights else "INITIAL_BUILD"
    ranking_by_ticker = {row["ticker"]: row for row in selection_meta.get("ranking", [])}
    selected_order = [row["ticker"] for row in selection_meta.get("ranking", []) if row.get("selected")]
    positions = []
    for candidate in candidates:
        ticker = candidate["ticker"]
        rank_row = ranking_by_ticker.get(ticker, {})
        exp = estimate_map.get(ticker, {})
        w = float(final.get(ticker, 0.0))
        position_bindings = [b for b in bindings if b.endswith(f":{ticker}") or
                             (b.startswith("SECTOR_CAP:") and b.split(":", 1)[1] == (candidate.get("sector") or "Unclassified")) or
                             (b.startswith("REGION_CAP:") and b.split(":", 1)[1] == candidate.get("region")) or
                             (b.startswith("THEME_CAP:") and b.split(":", 1)[1] in (themes.get(ticker) or ["Unclassified"]))]
        positions.append({
            "ticker": ticker, "region": candidate.get("region"), "sector": candidate.get("sector") or "Unclassified",
            "themes": themes.get(ticker) or ["Unclassified"], "alphaPercentile": candidate.get("alphaPercentile"),
            "factorPercentiles": candidate.get("factorPercentiles") or {},
            "evidenceCoverage": candidate.get("evidenceCoverage"),
            "expectedExcessReturnPct": exp.get("expectedExcessReturnPct"),
            "expectedReturnSampleSize": exp.get("effectiveSampleSize", 0),
            "expectedReturnEffectiveDates": exp.get("effectiveDates", 0),
            "expectedReturnUniqueDates": exp.get("uniqueDates", 0),
            "expectedReturnConfidence": exp.get("confidence"),
            "expectedReturnIntervalPct": exp.get("confidenceIntervalPct"),
            "upProbabilityPct": (exp.get("probabilityDistribution") or {}).get("upProbabilityPct"),
            "downProbabilityPct": (exp.get("probabilityDistribution") or {}).get("downProbabilityPct"),
            "probabilityIntervalPct": (exp.get("probabilityDistribution") or {}).get("probabilityIntervalPct"),
            "averageUpsidePct": (exp.get("probabilityDistribution") or {}).get("averageUpsidePct"),
            "averageDownsidePct": (exp.get("probabilityDistribution") or {}).get("averageDownsidePct"),
            "payoffRatio": (exp.get("probabilityDistribution") or {}).get("payoffRatio"),
            "distributionExpectedExcessReturnPct": ((exp.get("probabilityDistribution") or {})
                                                      .get("distributionExpectedExcessReturnPct")),
            "binaryKellyFraction": (exp.get("probabilityDistribution") or {}).get("binaryKellyFraction"),
            "probabilityContext": {key: (exp.get("probabilityDistribution") or {}).get(key)
                                   for key in ("selectedVariant", "contextUsed", "macroRegime",
                                               "entryState", "fallbackReason", "reliabilityEligible")},
            "historicalAlphaBucket": ((exp.get("evidence") or {}).get("historicalBucket")),
            "probabilityReliabilityStatus": (
                "PASS" if (exp.get("probabilityDistribution") or {}).get("reliabilityEligible")
                else "FAIL_OR_WITHHELD"),
            "transactionCost": exp.get("transactionCost"),
            "expectedReturnStatus": exp.get("status"),
            "riskLevel": (candidate.get("risk") or {}).get("vol252Pct"),
            "convictionScore": rank_row.get("convictionScore"),
            "convictionRank": (selected_order.index(ticker) + 1) if ticker in selected_order else None,
            "selectionRank": (selected_order.index(ticker) + 1) if ticker in selected_order else None,
            "entryMultiplier": rank_row.get("entryStateMultiplier"),
            "downsideVolPct": rank_row.get("downsideVolPct"),
            "thesisKo": candidate.get("thesisKo"),
            "invalidation": candidate.get("invalidation") or [],
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
        "concentration": concentration_diagnostics(final, local_cfg),
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
