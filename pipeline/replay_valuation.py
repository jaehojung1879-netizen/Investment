"""Fixed-window KRW portfolio valuation. Missing open-session marks are failures."""
from __future__ import annotations

from collections import Counter
import math

import numpy as np
import pandas as pd

from . import replay_calendar as RC
from .market_dates import normalize_daily_series

METRIC_VERSION = "calendar-span-daily-krw-rf-v1"


class ValuationData:
    def __init__(self, prices, benchmarks, fx, risk_free, *, through, risk_free_through=None):
        self.prices = {k: normalize_daily_series(v["Close"]).loc[:through]
                       for k,v in prices.items() if v is not None and "Close" in v}
        self.benchmarks = benchmarks
        self.fx = normalize_daily_series(fx).loc[:through] if fx is not None else pd.Series(dtype=float)
        # Policy-rate events: annual simple percent, effective from stated date.
        self.rates = sorted(risk_free, key=lambda r:r["date"])
        self.through = through
        self.risk_free_through = risk_free_through or through
        self._rf_cache = {}

    def marks(self, ticker, region, dates):
        source = self.prices.get(ticker)
        if source is None:
            return None
        opened = RC.sessions(dates[0].strftime("%Y-%m-%d"), dates[-1].strftime("%Y-%m-%d"), region)
        required = dates.intersection(opened)
        observed = source.reindex(required)
        if observed.isna().any() or (observed <= 0).any() or not np.isfinite(observed).all():
            return None
        # Only an official market closure permits last-close marking. An open
        # session with a missing quote was rejected above, before any carry.
        result = source.reindex(source.index.union(dates)).sort_index().ffill().reindex(dates)
        return result.to_numpy(float) if result.notna().all() and (result > 0).all() else None

    def risk_free_path(self, dates):
        key = (str(dates[0]), str(dates[-1]))
        if key in self._rf_cache:
            return self._rf_cache[key]
        if dates[-1].strftime("%Y-%m-%d") > self.risk_free_through:
            return None
        growth = [1.0]
        for left, right in zip(dates, dates[1:]):
            value = growth[-1]
            # Accrue every calendar day, including weekends, with the rate
            # already effective at the beginning of that day. Never backfill.
            for day in pd.date_range(left, right - pd.Timedelta(days=1)):
                known = [r for r in self.rates if r["date"] <= day.strftime("%Y-%m-%d")]
                if not known:
                    return None
                value *= 1 + float(known[-1]["annualRatePct"]) / 100 / 365
            growth.append(value)
        self._rf_cache[key] = np.asarray(growth)
        return self._rf_cache[key]

    def window(self, decision, block):
        date, end = block["date"], block["endDate"]
        reasons = []
        if end > self.through:
            return None, {"status":"HORIZON_NOT_MATURED", "reasons":["HORIZON_NOT_MATURED"]}
        if decision is None:
            return None, {"status":"INCOMPLETE", "reasons":["MISSING_SCHEDULED_SIGNAL"]}
        dates = RC.sessions(date, end, "UNION")
        rf = self.risk_free_path(dates)
        if rf is None:
            reasons.append("MISSING_KRW_RISK_FREE")
        gross = np.zeros(len(dates))
        benchmark = np.zeros(len(dates))
        excess_by_region, weight_by_region, terminal_values = {}, {}, {}
        us = any((decision.get("regionByTicker") or {}).get(t) == "US" for t in decision["weights"])
        fx = self.fx.reindex(dates).to_numpy(float) if us else np.ones(len(dates))
        if us and (not np.isfinite(fx).all() or np.any(fx <= 0)):
            reasons.append("MISSING_USDKRW_FX")
        for ticker, weight in decision["weights"].items():
            region = decision["regionByTicker"].get(ticker)
            if region not in ("KR", "US"):
                reasons.append("UNKNOWN_CURRENCY:" + ticker)
                continue
            p = self.marks(ticker, region, dates)
            b = self.marks(self.benchmarks.get(region), region, dates)
            if p is None:
                reasons.append("MISSING_PRICE_SESSION:" + ticker)
            if b is None:
                reasons.append("MISSING_BENCHMARK_SESSION:" + region)
            if p is None or b is None:
                continue
            currency = fx / fx[0] if region == "US" else 1.0
            stock_growth, bench_growth = p / p[0] * currency, b / b[0] * currency
            terminal_values[ticker] = weight * stock_growth[-1]
            gross += weight * stock_growth
            benchmark += weight * bench_growth
            weight_by_region[region] = weight_by_region.get(region, 0) + weight
            excess_by_region[region] = excess_by_region.get(region, 0) + weight * (stock_growth[-1] - bench_growth[-1])
        if reasons:
            return None, {"status":"INCOMPLETE", "reasons":sorted(set(reasons))}
        cash = 1 - sum(decision["weights"].values())
        if cash < -1e-8:
            raise ValueError("portfolio weights exceed NAV")
        gross += cash * rf
        benchmark += cash * rf
        weights = decision["weights"]
        total = sum(weights.values())
        row = {**decision, "date":date, "endDate":end, "signalDate":block["signalDate"],
               "terminalWeights":{t:float(v/gross[-1]) for t,v in terminal_values.items()},
               "cashWeight":cash, "grossReturn":float(gross[-1] - 1),
               "benchmarkReturn":float(benchmark[-1] - 1),
               "grossExcessReturn":float(gross[-1] - benchmark[-1]),
               "transactionCost":0.0, "turnover":0.0,
               "costAdjustedReturn":float(gross[-1] - 1),
               "costAdjustedExcessReturn":float(gross[-1] - benchmark[-1]),
               "weightByRegion":weight_by_region, "excessByRegion":excess_by_region,
               "top1":max(weights.values(), default=0),
               "top3":sum(sorted(weights.values(), reverse=True)[:3]),
               "effectiveNames":(1 / sum((w / total) ** 2 for w in weights.values()) if total else None),
               "dailyDates":dates.strftime("%Y-%m-%d").tolist(),
               "dailyGrossNav":gross.tolist(), "dailyBenchmarkNav":benchmark.tolist(),
               "dailyRiskFreeNav":rf.tolist(), "metricVersion":METRIC_VERSION,
               "riskFreeReturn":float(rf[-1] - 1),
               "fxReturnsIncluded":True, "baseCurrency":"KRW"}
        return row, {"status":"COMPLETE" if weights else "EMPTY_PORTFOLIO",
                     "reasons":[] if weights else ["EMPTY_PORTFOLIO"], "measured":True}


def coverage(statuses, minimum):
    counts = Counter(row["status"] for row in statuses)
    eligible = len(statuses) - counts["HORIZON_NOT_MATURED"]
    complete = sum(r.get("measured", r["status"] == "COMPLETE") for r in statuses)
    pct = complete / eligible * 100 if eligible else None
    reasons = Counter(reason.split(":")[0] for row in statuses
                      if row["status"] not in ("HORIZON_NOT_MATURED", "EMPTY_PORTFOLIO", "COMPLETE") for reason in row["reasons"])
    return {"totalDecisions":len(statuses), "eligibleDecisions":eligible,
            "completeOutcomes":complete, "notMaturedDecisions":counts["HORIZON_NOT_MATURED"],
            "droppedDecisions":eligible - complete, "completenessPct":pct,
            "minimumCompletenessPct":minimum, "sufficientForPath":pct is not None and pct >= minimum,
            "droppedByReason":dict(reasons), "statusCounts":dict(counts),
            "blocks":statuses}


def span_years(first, last):
    return (pd.Timestamp(last) - pd.Timestamp(first)).days / 365.2425


def daily_statistics(rows):
    """Chain daily buy-and-hold NAV; charge trading cost at each entry.

    Unknown intervals may not be joined or treated as flat cash. A full-path
    headline is withheld when even one scheduled matured block is missing.
    """
    nav = bench = rf_level = 1.0
    points = [{"date":rows[0]["date"], "nav":1.0, "benchmarkNav":1.0, "riskFreeNav":1.0}]
    last = rows[0]["date"]
    cost_events = []
    for row in rows:
        if row["date"] != last:
            return {"available":False, "reason":"non_contiguous_fixed_blocks"}
        cost = float(row["transactionCost"])
        if not 0 <= cost < 1:
            raise ValueError("invalid transaction cost fraction")
        # Invest the remaining NAV after costs with exactly the target weights.
        base = nav * (1 - cost)
        cost_events.append(base)
        for i in range(1, len(row["dailyDates"])):
            points.append({"date":row["dailyDates"][i],
                           "nav":base * row["dailyGrossNav"][i],
                           "benchmarkNav":bench * row["dailyBenchmarkNav"][i],
                           "riskFreeNav":rf_level * row["dailyRiskFreeNav"][i]})
        nav, bench, rf_level = (points[-1][k] for k in ("nav","benchmarkNav","riskFreeNav"))
        last = row["endDate"]
    p, b, rf = (np.array([x[k] for x in points]) for k in ("nav","benchmarkNav","riskFreeNav"))
    returns, br, rr = (v[1:] / v[:-1] - 1 for v in (p,b,rf))
    years = span_years(points[0]["date"], points[-1]["date"])
    periods = len(returns) / years
    excess, over_rf = returns - br, returns - rr
    sd = float(np.std(over_rf, ddof=1)) if len(returns)>1 else 0
    downside = float(np.sqrt(np.mean(np.minimum(over_rf, 0) ** 2)))
    peak = 1.0
    mdd = 0.0
    events = {row["date"]:event for row,event in zip(rows,cost_events)}
    for point in points:
        peak = max(peak, point["nav"])
        point["drawdownPct"] = (point["nav"] / peak - 1) * 100
        mdd = min(mdd, point["drawdownPct"])
        if point["date"] in events:
            mdd = min(mdd, (events[point["date"]] / peak - 1) * 100)
    def annual(growth):
        return (growth ** (1/years) - 1) * 100 if growth > 0 else -100.0
    stamps = np.array([np.datetime64(x["date"]) for x in points])
    def rolling(n):
        out = {}
        for i, point in enumerate(points):
            cutoff = pd.Timestamp(point["date"]) - pd.DateOffset(years=n)
            idx = int(np.searchsorted(stamps, np.datetime64(cutoff.date())))
            if idx >= i:
                continue
            span = span_years(points[idx]["date"], point["date"])
            if span < n * .99:
                continue
            val = ((p[i]/p[idx]) ** (1/span) - (b[i]/b[idx]) ** (1/span)) * 100
            out[point["date"][:7]] = {"date":point["date"], "firstDate":points[idx]["date"],
                                     "calendarYears":span, "annualizedExcessPct":round(val,3)}
        return list(out.values())
    te = float(np.std(excess, ddof=1)) if len(excess)>1 else 0
    result = {"available":True, "calendarYears":years, "observationsPerYear":periods,
              "cagrPct":annual(p[-1]), "benchmarkCagrPct":annual(b[-1]),
              "annualizedExcessPct":annual(p[-1])-annual(b[-1]),
              "sharpe":float(over_rf.mean()/sd*math.sqrt(periods)) if sd else None,
              "sortino":float(over_rf.mean()/downside*math.sqrt(periods)) if downside else None,
              "mddPct":mdd, "mddBasis":"DAILY_UNION_SESSIONS_WITH_ENTRY_COSTS",
              "annualizedRealizedVolPct":float(np.std(returns,ddof=1)*math.sqrt(periods)*100) if len(returns)>1 else None,
              "annualizedDownsideVolPct":downside*math.sqrt(periods)*100,
              "trackingErrorPct":te*math.sqrt(periods)*100,
              "informationRatio":float(excess.mean()/te*math.sqrt(periods)) if te else None,
              "cvar95Pct":float(np.sort(returns)[:max(1,math.ceil(len(returns)*.05))].mean()*100),
              "riskFreeBasis":"BOK_POLICY_RATE_PROXY_ACT_365_DAILY",
              "riskFreeReturnPct":(rf[-1]-1)*100, "baseCurrency":"KRW", "fxReturnsIncluded":True,
              "pathMethod":"FIXED_COMMON_SESSION_BLOCKS_DAILY_KRW_NAV",
              "metricVersion":METRIC_VERSION, "directlyComparableToLegacy":False,
              "rolling3YAnnualizedExcess":rolling(3), "rolling5YAnnualizedExcess":rolling(5), "nav":points}
    return {k:round(v,6) if isinstance(v,float) and math.isfinite(v) else v for k,v in result.items()}
