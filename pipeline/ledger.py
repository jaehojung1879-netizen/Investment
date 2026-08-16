"""Immutable paper-signal ledger — the ONLY honest path to 'validated'.

Every build appends today's long-term signals (research view, entry state,
alpha, reference price, benchmark, macro regime, model version) to an
append-only ledger. Records are keyed by (date, ticker); a re-run with a
changed model NEVER overwrites a past record — identity includes date, region,
ticker and modelVersion so a new model cannot rewrite an old model's signal,
forward performance is judged against what the model ACTUALLY said at the time,
not a hindsight-revised version.

Outcomes (21/63/126/252-day forward return, excess vs benchmark, MFE/MAE) are
computed later from prices and stored in a SEPARATE outcomes ledger keyed by the
signal id, leaving the original signals untouched.

In CI this ledger lives on a dedicated ``signal-history`` branch (see
.github/workflows/ledger.yml) so it accumulates without triggering the main
Pages build.

Evaluation metrics (see ``evaluate``) go beyond hit-rate: rank IC, mean excess
return, turnover, MDD, and per-view breakdown — the metrics a real model review
uses.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HORIZONS = [21, 63, 126, 252]


def filter_model_generation(rows: list[dict], model_version: str | None) -> tuple[list[dict], int]:
    """Return only rows produced by one exact model generation.

    The append-only ledgers intentionally retain every historical generation.
    That is useful for audit, but those generations are not statistically
    interchangeable: pooling them would let an older formula validate a newer
    one.  Missing ``modelVersion`` is therefore excluded when a generation is
    requested rather than silently treated as compatible.
    """
    if model_version is None:
        return list(rows), 0
    selected = [row for row in rows if row.get("modelVersion") == model_version]
    return selected, len(rows) - len(selected)


def signal_id(date: str, ticker: str, region: str | None = None,
              model_version: str | None = None) -> str:
    return "|".join(str(v or "UNKNOWN") for v in (date, region, ticker, model_version))


def records_from_payload(payload: dict) -> list[dict]:
    """Extract immutable signal rows from a built payload."""
    provenance = payload.get("provenance") or {}
    default_date = (payload.get("meta") or {}).get("latestDataDate")
    model_version = payload.get("modelVersion") or provenance.get("modelVersion")
    schema_version = payload.get("schemaVersion") or provenance.get("schemaVersion")
    macro = ((payload.get("macroRegime") or {}) or {}).get("regime")
    lt = payload.get("longTerm") or {}
    out: list[dict] = []
    for region, blob in (lt.get("regions") or {}).items():
        # The UI table is capped at 15; validationCrossSection is the complete
        # eligible set required for NEGATIVE/NEUTRAL calls and rank IC.
        rows = blob.get("validationCrossSection") or blob.get("researchTable", [])
        for row in rows:
            row_region = row.get("region") or region
            detail = (payload.get("details", {}).get(row["ticker"], {}) or {})
            date = detail.get("asOf") or default_date
            entry = row.get("entry") or {}
            record = {
                "id": signal_id(date, row["ticker"], row_region, model_version),
                "date": date,
                "ticker": row["ticker"],
                "region": row_region,
                "modelVersion": model_version,
                "schemaVersion": schema_version,
                "longTermResearchView": row.get("longTermResearchView"),
                "alpha": row.get("alpha"),
                "alphaPercentile": row.get("alphaPercentile"),
                "sector": row.get("sector"),
                "marketCap": row.get("marketCap"),
                "refClose": detail.get("lastClose"),
                "benchmark": (payload.get("benchmarks") or {}).get(row_region, payload.get("benchmark")),
                "macroRegime": macro,
            }
            if entry.get("entryState") is not None:
                record["entryState"] = entry["entryState"]
            out.append(record)
    return out


def append_signals(existing: list[dict], new: list[dict]) -> tuple[list[dict], int, int]:
    """Append only rows whose id is not already present. Returns
    (merged, appended, skipped). Existing rows are never mutated."""
    seen = {r["id"] for r in existing}
    appended = 0
    merged = list(existing)
    for r in new:
        if r.get("id") in seen or r.get("date") is None:
            continue
        merged.append(dict(r))
        seen.add(r["id"])
        appended += 1
    return merged, appended, len(new) - appended


def portfolio_record_from_payload(payload: dict) -> dict | None:
    """Extract one immutable model-portfolio signal from a built artifact."""
    portfolio = payload.get("modelPortfolio") or {}
    if portfolio.get("status") in {None, "BLOCKED", "DISABLED"}:
        return None
    provenance = payload.get("provenance") or {}
    date = (payload.get("meta") or {}).get("latestDataDate") or provenance.get("marketAsOf")
    model_version = payload.get("modelVersion") or provenance.get("modelVersion")
    if not date or not model_version:
        return None
    return {
        "id": f"{date}|PORTFOLIO|{model_version}",
        "date": date,
        "modelVersion": model_version,
        "schemaVersion": payload.get("schemaVersion") or provenance.get("schemaVersion"),
        "portfolioStatus": portfolio.get("status"),
        "horizonDays": portfolio.get("horizonDays"),
        "positions": portfolio.get("positions") or [],
        "cashPct": portfolio.get("cashPct"),
        "expectedVolPct": portfolio.get("expectedVolPct"),
        "regime": portfolio.get("regime"),
        "appliedKellyFraction": portfolio.get("appliedKellyFraction"),
        "riskWeightedWeights": portfolio.get("riskWeightedWeights") or {},
        "constrainedKellyWeights": portfolio.get("constrainedKellyWeights") or {},
        "finalWeights": portfolio.get("finalWeights") or {},
        "sectorExposure": portfolio.get("sectorExposure") or {},
        "themeExposure": portfolio.get("themeExposure") or {},
        "regionExposure": portfolio.get("regionExposure") or {},
        "estimatedTurnover": portfolio.get("turnoverPct"),
        "transactionCostPolicy": portfolio.get("transactionCostPolicy") or {},
        "bindingConstraints": portfolio.get("bindingConstraints") or [],
        "benchmarks": payload.get("benchmarks") or {},
    }


def append_portfolio_signals(existing: list[dict], new: list[dict]) -> tuple[list[dict], int, int]:
    """Append portfolio signals without ever replacing the same date/version."""
    return append_signals(existing, new)


def load_jsonl(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: str | Path, rows: list[dict]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")


def compute_outcomes(signals: list[dict], prices: dict[str, pd.DataFrame],
                     benchmarks: dict[str, pd.Series] | None = None) -> list[dict]:
    """For each matured signal compute forward returns, excess vs benchmark,
    and MFE/MAE. Only produces an outcome for a horizon that has fully elapsed
    in the price data — no partial/look-ahead outcomes."""
    benchmarks = benchmarks or {}
    out = []
    for s in signals:
        tk = s["ticker"]
        px = prices.get(tk)
        if px is None or "Close" not in px:
            continue
        close = px["Close"].dropna()
        try:
            entry_idx = close.index.get_indexer([pd.Timestamp(s["date"])], method="ffill")[0]
        except Exception:
            continue
        if entry_idx < 0:
            continue
        entry_px = float(close.iloc[entry_idx])
        bench = benchmarks.get(s.get("benchmark"))
        rec = {"id": s["id"], "date": s["date"], "ticker": tk, "region": s.get("region"),
               "modelVersion": s.get("modelVersion"), "longTermResearchView": s.get("longTermResearchView"),
               "entryState": s.get("entryState"), "macroRegime": s.get("macroRegime"),
               "alpha": s.get("alpha"), "alphaPercentile": s.get("alphaPercentile"), "horizons": {}}
        for h in HORIZONS:
            j = entry_idx + h
            if j >= len(close):
                continue
            path = close.iloc[entry_idx:j + 1]
            fwd = float(close.iloc[j] / entry_px - 1)
            mfe = float(path.max() / entry_px - 1)
            mae = float(path.min() / entry_px - 1)
            excess = None
            if bench is not None:
                b = bench.dropna()
                try:
                    start_date, end_date = close.index[entry_idx], close.index[j]
                    # The benchmark must share the exact start/end calendar
                    # dates. A nearby US session is not a valid KR comparison.
                    if start_date in b.index and end_date in b.index:
                        excess = round(fwd - float(b.loc[end_date] / b.loc[start_date] - 1), 4)
                except Exception:
                    pass
            rec["horizons"][str(h)] = {
                "fwdReturn": round(fwd, 4), "excessReturn": excess,
                "mfe": round(mfe, 4), "mae": round(mae, 4),
            }
        if rec["horizons"]:
            out.append(rec)
    return out


def compute_portfolio_outcomes(signals: list[dict], prices: dict[str, pd.DataFrame],
                               benchmarks: dict[str, pd.Series] | None = None) -> list[dict]:
    """Compute matured portfolio outcomes on a synchronized common calendar."""
    benchmarks = benchmarks or {}
    results = []
    for signal in signals:
        weights = {k: float(v) for k, v in (signal.get("finalWeights") or {}).items() if float(v) > 0}
        if not weights or not signal.get("date"):
            continue
        closes = {
            ticker: prices[ticker]["Close"].dropna()
            for ticker in weights if ticker in prices and "Close" in prices[ticker]
        }
        if set(closes) != set(weights):
            continue
        panel = pd.concat(closes, axis=1, join="inner").dropna()
        try:
            start = panel.index.get_indexer([pd.Timestamp(signal["date"])], method="ffill")[0]
        except Exception:
            continue
        if start < 0:
            continue
        record = {
            "id": signal["id"], "date": signal["date"],
            "modelVersion": signal.get("modelVersion"), "horizons": {},
        }
        for horizon in sorted({21, 63, 126, 252}):
            end = start + horizon
            if end >= len(panel):
                continue
            window = panel.iloc[start:end + 1]
            daily = window.pct_change(fill_method=None).dropna()
            w = pd.Series(weights).reindex(window.columns).fillna(0.0)
            portfolio_daily = daily.mul(w, axis=1).sum(axis=1)
            portfolio_return = float((1.0 + portfolio_daily).prod() - 1.0)

            benchmark_return = 0.0
            benchmark_available = True
            region_exposure = signal.get("regionExposure") or {}
            invested_region = sum(float(v) for v in region_exposure.values())
            for region, exposure_pct in region_exposure.items():
                benchmark_ticker = (signal.get("benchmarks") or {}).get(region)
                series = benchmarks.get(benchmark_ticker)
                if series is None or invested_region <= 0:
                    benchmark_available = False
                    break
                start_date, end_date = window.index[0], window.index[-1]
                if start_date not in series.index or end_date not in series.index:
                    benchmark_available = False
                    break
                region_return = float(series.loc[end_date] / series.loc[start_date] - 1.0)
                benchmark_return += float(exposure_pct) / invested_region * region_return
            if not benchmark_available:
                benchmark_return = None

            equity = (1.0 + portfolio_daily).cumprod()
            drawdown = equity / equity.cummax() - 1.0
            volatility = float(portfolio_daily.std(ddof=1) * np.sqrt(252)) if len(portfolio_daily) > 1 else None
            sharpe = (float(portfolio_daily.mean() / portfolio_daily.std(ddof=1) * np.sqrt(252))
                      if len(portfolio_daily) > 1 and portfolio_daily.std(ddof=1) > 0 else None)
            tail = portfolio_daily.nsmallest(max(1, int(np.ceil(len(portfolio_daily) * 0.05))))
            turnover = float(signal.get("estimatedTurnover") or 0.0) / 100.0
            cost_policy = signal.get("transactionCostPolicy") or {}
            exposures = signal.get("regionExposure") or {}
            invested_region = sum(float(v) for v in exposures.values())
            cost_fallback = not bool(cost_policy and invested_region > 0)
            if cost_fallback:
                transaction_cost = turnover * 0.001
            else:
                weighted_bps = 0.0
                for region, exposure_pct in exposures.items():
                    regional = cost_policy.get(region) or {}
                    if not regional:
                        cost_fallback = True
                        break
                    round_trip_bps = (
                        float(regional.get("commissionBps", 5.0)) * 2.0
                        + float(regional.get("spreadBps", 12.0)) * 2.0
                        + float(regional.get("sellTaxBps", 20.0 if region == "KR" else 3.0))
                    )
                    weighted_bps += float(exposure_pct) / invested_region * round_trip_bps
                transaction_cost = turnover * (0.001 if cost_fallback else weighted_bps / 10_000.0)

            def variant_return(raw_weights: dict) -> float | None:
                if not raw_weights:
                    return None
                vw = pd.Series({k: float(v) for k, v in raw_weights.items()}).reindex(window.columns).fillna(0.0)
                return float((1.0 + daily.mul(vw, axis=1).sum(axis=1)).prod() - 1.0)

            risk_return = variant_return(signal.get("riskWeightedWeights") or {})
            kelly_return = variant_return(signal.get("constrainedKellyWeights") or {})
            excess = portfolio_return - benchmark_return if benchmark_return is not None else None
            record["horizons"][str(horizon)] = {
                "portfolioReturn": round(portfolio_return, 6),
                "benchmarkReturn": round(benchmark_return, 6) if benchmark_return is not None else None,
                "excessReturn": round(excess, 6) if excess is not None else None,
                "costAdjustedExcessReturn": round(excess - transaction_cost, 6) if excess is not None else None,
                "volatility": round(volatility, 6) if volatility is not None else None,
                "sharpe": round(sharpe, 4) if sharpe is not None else None,
                "maxDrawdown": round(float(drawdown.min()), 6),
                "cvar95": round(float(tail.mean()), 6),
                "turnoverPct": signal.get("estimatedTurnover"),
                "transactionCost": round(transaction_cost, 6),
                "transactionCostFallbackUsed": cost_fallback,
                "vsRiskWeightedReturn": round(portfolio_return - risk_return, 6) if risk_return is not None else None,
                "vsKellyReturn": round(portfolio_return - kelly_return, 6) if kelly_return is not None else None,
            }
        if record["horizons"]:
            results.append(record)
    return results


def evaluate_portfolios(outcomes: list[dict], horizon: int = 126) -> dict:
    """Summarize only non-overlapping portfolio vintages."""
    hk = str(horizon)
    rows = [row for row in outcomes if hk in (row.get("horizons") or {})]
    selected = set(_non_overlapping_dates(rows, horizon))
    sample = [row["horizons"][hk] for row in rows if row.get("date") in selected]
    if not sample:
        return {"n": 0, "horizon": horizon, "nonOverlappingDates": 0}
    def mean(key):
        values = [float(row[key]) for row in sample if row.get(key) is not None]
        return round(float(np.mean(values)), 6) if values else None
    return {
        "n": len(sample), "horizon": horizon, "nonOverlappingDates": len(selected),
        "meanPortfolioReturn": mean("portfolioReturn"),
        "meanExcessReturn": mean("excessReturn"),
        "meanCostAdjustedExcessReturn": mean("costAdjustedExcessReturn"),
        "meanVolatility": mean("volatility"), "meanSharpe": mean("sharpe"),
        "worstMaxDrawdown": min((row["maxDrawdown"] for row in sample if row.get("maxDrawdown") is not None), default=None),
        "meanTurnoverPct": mean("turnoverPct"),
        "meanVsRiskWeightedReturn": mean("vsRiskWeightedReturn"),
        "meanVsKellyReturn": mean("vsKellyReturn"),
    }


def _non_overlapping_dates(rows: list[dict], horizon: int) -> list[str]:
    selected: list[pd.Timestamp] = []
    dates = sorted({pd.Timestamp(r["date"]).normalize() for r in rows if r.get("date")})
    for date in dates:
        if not selected or date >= selected[-1] + pd.offsets.BDay(horizon):
            selected.append(date)
    return [d.strftime("%Y-%m-%d") for d in selected]


def _summary(values: list[float]) -> dict:
    return {
        "mean": round(float(np.mean(values)), 3) if values else None,
        "median": round(float(np.median(values)), 3) if values else None,
        "hitRatio": round(float(np.mean([v > 0 for v in values])), 3) if values else None,
    }


def evaluate(outcomes: list[dict], horizon: int = 63) -> dict:
    """Evaluate non-overlapping date x region cross-sections.

    Spearman IC is computed inside each cross-section and aggregated afterwards;
    observations from different markets or dates are never pooled.
    """
    hk = str(horizon)
    rows = [o for o in outcomes if hk in o.get("horizons", {})]
    if not rows:
        return {"n": 0, "horizon": horizon, "crossSections": 0,
                "eligibleDates": 0, "regionIC": {}}
    selected_dates = set(_non_overlapping_dates(rows, horizon))
    sampled = [o for o in rows if o.get("date") in selected_dates]
    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in sampled:
        grouped.setdefault((row.get("date"), row.get("region") or "UNKNOWN"), []).append(row)

    cross_sections = []
    region_values: dict[str, list[float]] = {}
    region_signals: dict[str, int] = {}
    for (date, region), group in sorted(grouped.items()):
        valid = [o for o in group if o.get("alpha") is not None]
        if len(valid) < 3:
            continue
        alphas = pd.Series([o["alpha"] for o in valid], dtype=float)
        fwds = pd.Series([o["horizons"][hk]["fwdReturn"] for o in valid], dtype=float)
        if alphas.nunique() < 2 or fwds.nunique() < 2:
            continue
        ic = float(alphas.rank().corr(fwds.rank(), method="pearson"))
        cross_sections.append({"date": date, "region": region, "ic": round(ic, 6), "n": len(valid)})
        region_values.setdefault(region, []).append(ic)
        region_signals[region] = region_signals.get(region, 0) + len(valid)

    ic_values = [r["ic"] for r in cross_sections]
    excesses = [o["horizons"][hk]["excessReturn"] for o in sampled
                if o["horizons"][hk].get("excessReturn") is not None]
    pos = [o for o in sampled if o.get("longTermResearchView") == "POSITIVE"]
    pos_fwd = [o["horizons"][hk]["fwdReturn"] for o in pos]
    hit = float(np.mean([f > 0 for f in pos_fwd])) if pos_fwd else None
    by_view = {}
    for view in ("POSITIVE", "NEUTRAL", "NEGATIVE"):
        vf = [o["horizons"][hk]["fwdReturn"] for o in sampled
              if o.get("longTermResearchView") == view]
        if vf:
            by_view[view] = {"n": len(vf), "meanFwd": round(float(np.mean(vf)), 4)}

    basket = []
    for date in sorted(selected_dates):
        values = [o["horizons"][hk]["fwdReturn"] for o in pos if o.get("date") == date]
        if values:
            basket.append(float(np.mean(values)))
    mdd = cvar = None
    if basket:
        equity = np.cumprod(1 + np.asarray(basket))
        drawdown = equity / np.maximum.accumulate(equity) - 1
        mdd = float(drawdown.min())
        tail_n = max(1, int(np.ceil(len(basket) * 0.05)))
        cvar = float(np.mean(sorted(basket)[:tail_n]))

    region_ic = {
        region: {**_summary(values), "nDates": len(values),
                 "nSignals": region_signals.get(region, 0)}
        for region, values in region_values.items()
    }
    return {
        "n": len(sampled), "horizon": horizon,
        "rankIC": round(float(np.mean(ic_values)), 3) if ic_values else None,
        "rankICMedian": round(float(np.median(ic_values)), 3) if ic_values else None,
        "rankICHitRatio": round(float(np.mean([v > 0 for v in ic_values])), 3) if ic_values else None,
        "crossSections": len(cross_sections),
        "eligibleDates": len(selected_dates),
        "regionIC": region_ic,
        "meanExcess": round(float(np.mean(excesses)), 4) if excesses else None,
        "meanExcessAfterCost": round(float(np.mean(excesses)) - 0.001, 4) if excesses else None,
        "positiveHitRate": round(hit, 3) if hit is not None else None,
        "mdd": round(mdd, 4) if mdd is not None else None,
        "cvar95": round(cvar, 4) if cvar is not None else None,
        "byView": by_view,
    }


def validation_status(outcomes: list[dict], min_paper_days: int = 126,
                      signals: list[dict] | None = None,
                      model_version: str | None = None) -> dict:
    """Prospective-ledger status.

    ``trackingDays`` and ``maturedObservationDays`` are DIFFERENT quantities and
    are reported separately. The old code derived both from the outcomes file,
    so on a fresh ledger — thousands of signals recorded, none yet matured — the
    dashboard announced "0 days tracked", which is simply false: tracking had
    been running the whole time. Tracking now measures the signal ledger's own
    span, and maturity measures how much of it has completed a horizon.
    """
    outcomes, excluded_outcomes = filter_model_generation(outcomes, model_version)
    filtered_signals, excluded_signals = filter_model_generation(signals or [], model_version)
    signal_dates = sorted({pd.Timestamp(s["date"]).normalize()
                           for s in filtered_signals if s.get("date")})
    outcome_dates = sorted({pd.Timestamp(o["date"]).normalize()
                            for o in outcomes if o.get("date")})
    span_dates = signal_dates or outcome_dates
    tracking_days = len(pd.bdate_range(span_dates[0], span_dates[-1])) if span_dates else 0

    matured_rows = [o for o in outcomes if "126" in (o.get("horizons") or {})]
    matured_dates = sorted({pd.Timestamp(o["date"]).normalize() for o in matured_rows})
    matured_days = (len(pd.bdate_range(matured_dates[0], matured_dates[-1]))
                    if matured_dates else 0)
    matured = len(matured_rows)
    metrics = evaluate(outcomes, horizon=63)
    reasons = []
    if tracking_days < min_paper_days:
        reasons.append(f"paper_history_below_{min_paper_days}_business_days")
    if matured == 0:
        reasons.append("no_126d_matured_signals")
    eligible = tracking_days >= min_paper_days and matured > 0 and metrics.get("crossSections", 0) > 0
    return {
        # paperDays keeps its name for backward compatibility with existing
        # consumers, but now means what it always claimed to: days tracked.
        "paperDays": tracking_days,
        "trackingDays": tracking_days,
        "maturedObservationDays": matured_days,
        "modelVersion": model_version,
        "generationIsolated": model_version is not None,
        "excludedPriorModelSignals": excluded_signals if signals is not None else None,
        "excludedPriorModelOutcomes": excluded_outcomes,
        "signalsRecorded": len(filtered_signals) if signals is not None else None,
        "uniqueDates": len(signal_dates) if signal_dates else len(outcome_dates),
        "maturedUniqueDates": len(matured_dates),
        "firstSignalDate": span_dates[0].strftime("%Y-%m-%d") if span_dates else None,
        "lastSignalDate": span_dates[-1].strftime("%Y-%m-%d") if span_dates else None,
        "maturedSignals": matured,
        "maturedByHorizon": {
            str(h): sum(1 for o in outcomes if str(h) in (o.get("horizons") or {}))
            for h in HORIZONS
        },
        "eligibleDates": metrics.get("eligibleDates", 0),
        "regionIC": metrics.get("regionIC", {}),
        "costAdjustedExcessReturn": metrics.get("meanExcessAfterCost"),
        "MDD": metrics.get("mdd"),
        "CVaR": metrics.get("cvar95"),
        "evidenceClass": "PROSPECTIVE_PAPER",
        "liveValidationEligible": bool(eligible),
        "liveValidated": False,
        "reasons": reasons if not eligible else ["manual_review_required; auto-promotion_disabled"],
    }
