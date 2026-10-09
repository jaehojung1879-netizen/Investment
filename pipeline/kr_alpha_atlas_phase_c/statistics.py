"""Date-balanced statistics and calendar-time attribution. No files or outcomes read."""

from __future__ import annotations

import math
from collections import Counter
from functools import lru_cache

import numpy as np
import pandas as pd
from scipy.integrate import quad
from scipy.stats import rankdata

from pipeline.alpha_inference_calibration_v4 import calendar_time_sn_interval
from pipeline.alpha_opportunity_v5_evidence import paired_mse_design, rank_weighted_spread_design
from .contract import digest


def rank_ic(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 3:
        return None
    x, y = rankdata(a[ok]), rankdata(b[ok])
    if np.ptp(x) == 0 or np.ptp(y) == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def percentiles(data, cols=None):
    cols = list(data.values.columns) if cols is None else cols
    # No target or outcome-validity mask is an input to this transform.
    return data.values[cols].groupby(data.rows.date, sort=True).rank(method="average", pct=True)


def nw_summary(series, horizon):
    values = np.array([v for v in series if v is not None and np.isfinite(v)], float)
    n = len(values)
    if not n:
        return {"mean": None, "se": None, "nDates": 0, "status": "BLOCKED"}
    mean = float(values.mean())
    if n < 2:
        return {"mean": mean, "se": None, "nDates": n, "status": "DESCRIPTIVE"}
    z = values - mean
    lag = min(n - 1, max(0, math.ceil(horizon / 5) - 1))
    variance = float(z @ z / n)
    for k in range(1, lag + 1):
        variance += 2 * (1 - k / (lag + 1)) * float(z[k:] @ z[:-k] / n)
    return {
        "mean": mean,
        "se": math.sqrt(max(0, variance) / n),
        "nDates": n,
        "lagObservations": lag,
        "status": "DESCRIPTIVE_NW_ONLY",
    }


@lru_cache(maxsize=16384)
def sn_tail(pivot):
    """Exact scalar Brownian-bridge LIMIT tail, deterministic quadrature (not t/normal).

    Z independent of bridge and Laplace transform of integral bridge^2 is
    sqrt(sqrt(2s)/sinh(sqrt(2s))). Craig's Gaussian tail identity gives this
    integral. Development/asymptotic p; finite-sample small-tail accuracy unproven.
    """
    if pivot <= 0:
        return 1.0
    root = math.sqrt(pivot)

    def integrand(theta):
        if theta <= 0:
            return 0.0
        a = root / math.sin(theta)
        # Stable log(sinh(a)), including arbitrarily large a at theta=0.
        log_sinh = a - math.log(2) + math.log1p(-math.exp(-2 * a)) if a > 20 else math.log(math.sinh(a))
        return math.exp(0.5 * (math.log(a) - log_sinh))

    val, error = quad(integrand, 0, math.pi / 2, epsabs=1e-12, epsrel=1e-10, limit=100)
    if error > 1e-8:
        raise ValueError("SN_TAIL_NUMERICAL_FAILURE")
    return min(1.0, max(0.0, 2 * val / math.pi))


def linear_summary(data, book, designs, scheduled, spec, *, inferential=True):
    """designs: (row indices, weights, signal constant) for each date. All indices
    share the SAME outcome-valid mask. Linear designs telescope exactly.
    """
    records = []
    week_codes, _ = pd.factorize(data.days.to_period("W"))
    n_weeks = int(week_codes.max() + 1)
    d = np.zeros(n_weeks)
    x = np.zeros(n_weeks)
    for date, (ids, weights, constant) in sorted(designs.items()):
        ids = np.asarray(ids, int)
        weights = np.asarray(weights, float)
        if len(ids) == 0 or not np.isfinite(book.relative_increments[ids]).all():
            raise ValueError("UNPRICED_LINEAR_DESIGN")
        if len(weights) != len(ids):
            raise ValueError("DESIGN_ALIGNMENT")
        inc = weights @ book.relative_increments[ids]
        estimate = float(inc.sum() + constant)
        entries = book.entry_positions[ids]
        if np.ptp(entries) != 0:
            raise ValueError("DATE_ENTRY_MISMATCH")
        entry = int(entries[0])
        first = entry + 1
        weeks = week_codes[first : first + book.horizon]
        if len(weeks) != book.horizon:
            raise ValueError("CALENDAR_ATTRIBUTION_TRUNCATION")
        np.add.at(d, weeks, inc)
        np.add.at(x, weeks, 1.0 / book.horizon)
        sw = int(week_codes[data.days.searchsorted(pd.Timestamp(date))])
        d[sw] += constant
        records.append({"date": date, "value": estimate, "names": len(ids)})
    if not np.isclose(d.sum(), math.fsum(r["value"] for r in records), atol=1e-9, rtol=0):
        raise ValueError("CALENDAR_ATTRIBUTION_IDENTITY_BROKEN")
    n = len(records)
    required = spec["level1"]["minDates"]
    share = n / len(scheduled) if len(scheduled) else None
    out = {
        "estimate": None if n == 0 else float(d.sum() / n),
        "nDates": n,
        "nObservations": sum(r["names"] for r in records),
        "scheduledDates": len(scheduled),
        "evaluableShare": share,
        "perDate": records,
        "interval": None,
        "p": None,
        "inferenceStatus": "BLOCKED",
        "calendarWeeks": 0,
    }
    if n == 0:
        return out
    occupied = np.flatnonzero(x > 0)
    first = min(int(week_codes[data.days.searchsorted(pd.Timestamp(records[0]["date"]))]), int(occupied[0]))
    last = int(occupied[-1])
    d, x = d[first : last + 1], x[first : last + 1]
    out["calendarWeeks"] = len(d)
    floor = spec["inference"]["minCalendarWeeks"].get(str(book.horizon))
    if n < required or share < spec["level1"]["minEvaluableShare"]:
        out["inferenceStatus"] = "BLOCKED_INSUFFICIENT_COMMON_SAMPLE"
    elif not inferential or floor is None:
        out["inferenceStatus"] = "DESCRIPTIVE_UNCALIBRATED"
    elif len(d) < floor:
        out["inferenceStatus"] = "BLOCKED_CALIBRATED_DEPTH"
    else:
        interval = calendar_time_sn_interval(
            d, x, spec["inference"]["criticalValue"], spec["inference"]["nearZeroTolerance"]
        )
        out["interval"] = interval
        out["inferenceStatus"] = "BLOCKED_UNDEFINED_SN" if interval is None else "DEVELOPMENT_ASYMPTOTIC_SN"
        if interval is not None:
            pivot = len(d) * d.sum() ** 2 / interval["selfNormalizer"]
            out["p"] = sn_tail(float(pivot))
    return out


def adjust(pvalues, method):
    """Keep every registered hypothesis slot. None / unsupported / blocked => p=1."""
    keys = list(pvalues)
    n = len(keys)
    if n == 0:
        return {}
    p = np.array([1.0 if pvalues[k] is None else pvalues[k] for k in keys], float)
    if not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("INVALID_P_VALUE")
    order = np.argsort(p, kind="stable")
    q = np.ones(n)
    if method == "BY":
        harmonic = sum(1 / i for i in range(1, n + 1))
        sorted_q = np.minimum.accumulate((p[order] * n * harmonic / np.arange(1, n + 1))[::-1])[::-1]
    elif method == "HOLM":
        sorted_q = np.maximum.accumulate(p[order] * np.arange(n, 0, -1))
    else:
        raise ValueError("UNREGISTERED_MULTIPLICITY")
    q[order] = np.minimum(1, sorted_q)
    return dict(zip(keys, q.tolist()))


def group_weights(high, low=None):
    high = np.asarray(high, bool)
    if high.sum() < 3 or (low is not None and np.asarray(low, bool).sum() < 3):
        return None
    w = high.astype(float) / high.sum()
    if low is not None:
        low = np.asarray(low, bool)
        w -= low.astype(float) / low.sum()
    return w


def industry_adjust(data, book, ids, weights):
    """Exact vector LOO transform; expand only pinned signal-time industry cohorts."""
    if not hasattr(data, "_industry_arrays"):
        data._industry_arrays = {}
        for (date, _), group in data.rows.groupby(["date", "industry"]):
            data._industry_arrays.setdefault(date, []).append(
                (group.index.to_numpy(int), group.marketCap.to_numpy(float))
            )
        data._date_arrays = {date: group.index.to_numpy(int) for date, group in data.rows.groupby("date")}
    date = data.rows.date.iat[int(ids[0])]
    all_ids = data._date_arrays[date]
    start = int(all_ids[0])
    out = np.zeros(len(all_ids))
    include = np.zeros(len(all_ids), bool)
    positions = np.asarray(ids, int) - start
    out[positions] = weights
    include[positions] = True
    for group_ids, cap in data._industry_arrays.get(date, []):
        positions = group_ids - start
        w = out[positions].copy()
        if not np.any(w):
            continue
        if not book.table.industryState.iloc[group_ids[w != 0]].eq("VALID").all():
            return None
        denominator = cap.sum() - cap
        transformed = w - cap * (np.sum(w / denominator) - w / denominator)
        out[positions] = transformed
        include[positions] |= transformed != 0
    return all_ids[include], out[include], 0.0


def stability(summary, data, horizon, spec):
    records = summary["perDate"]
    n = len(records)
    years = {}
    for year in sorted({r["date"][:4] for r in records}):
        vals = [r["value"] for r in records if r["date"].startswith(year)]
        years[year] = {
            "dates": len(vals),
            "mean": float(np.mean(vals)),
            "evaluable": len(vals) >= spec["level1"]["minYearDates"],
        }
    half = n // 2
    halves = [float(np.mean([r["value"] for r in part])) if part else None for part in (records[:half], records[half:])]
    evaluable = [v for v in years.values() if v["evaluable"]]
    positive = sum(v["mean"] > 0 for v in evaluable) / len(evaluable) if evaluable else None
    regime = {}
    for state in (0, 1):
        dates = set(
            data.rows.date[
                data.values["I01_kospiTrendVolState"].lt(1) if state else data.values["I01_kospiTrendVolState"].ge(1)
            ]
        )
        vals = [r["value"] for r in records if r["date"] in dates]
        regime["STRESSED" if state else "NORMAL"] = nw_summary(vals, horizon)
    return {
        "years": years,
        "halves": halves,
        "positiveYearShare": positive,
        "marketRegimes": regime,
        "stable": all(v is not None and v > 0 for v in halves) and positive is not None and positive >= 0.60,
    }


def factor_reading(data, book, feature, spec, *, score=None):
    values = data.values[feature["featureId"]] if score is None else score
    pct = values.groupby(data.rows.date).rank(pct=True, method="average")
    direction = feature["expectedDirection"]
    oriented = pct if direction == 1 else 1 - pct
    if feature["featureId"] == "J01_periodicFilingEvent" and score is None:
        oriented = values if direction == 1 else 1 - values
    start, end = feature["usableRange"]
    h = book.horizon
    dates = data.rows.date.to_numpy()
    ticker = data.rows.ticker.to_numpy()
    tier = data.rows.liquidityTier.to_numpy()
    measured = values.notna().to_numpy()
    valid = book.table.state.eq("VALID").to_numpy() & measured
    y = book.table.benchmarkRelative.to_numpy(float)
    iy = book.table.industryRelative.to_numpy(float)
    industry_valid = book.table.industryState.eq("VALID").to_numpy()
    v = values.to_numpy(float)
    p = oriented.to_numpy(float)
    wi = values.groupby([data.rows.date, data.rows.industry]).rank(pct=True, method="average").to_numpy(float)
    if direction == -1:
        wi = 1 - wi
    if feature["featureId"] == "J01_periodicFilingEvent" and score is None:
        wi = values.to_numpy(float) if direction == 1 else 1 - values.to_numpy(float)
    if not hasattr(data, "_date_arrays"):
        data._date_arrays = {d: g.index.to_numpy(int) for d, g in data.rows.groupby("date")}
    if not hasattr(data, "_industry_arrays"):
        data._industry_arrays = {}
        for (d, _), g in data.rows.groupby(["date", "industry"]):
            data._industry_arrays.setdefault(d, []).append((g.index.to_numpy(int), g.marketCap.to_numpy(float)))
    matured = book.table.missingReason.ne("NOT_MATURED_BY_CUTOFF").to_numpy()
    scheduled = [date for date, ids in data._date_arrays.items() if start <= date <= end and matured[ids].any()]
    designs = {k: {} for k in ("tercileSpread", "withinIndustryTercileSpread", "topExcess")}
    ic = []
    wi_ic = []
    counts = []
    liquidity = {"LOW": {}, "MID": {}, "HIGH": {}}
    for date in scheduled:
        all_ids = data._date_arrays[date]
        ids = all_ids[valid[all_ids]]
        counts.append(
            {
                "date": date,
                "preGateMeasured": int(measured[all_ids].sum()),
                "validMeasured": len(ids),
                "lost": int((measured[all_ids] & ~valid[all_ids]).sum()),
            }
        )
        if len(ids) < 30:
            continue
        raw = group_weights(p[ids] >= 2 / 3, p[ids] <= 1 / 3)
        top = group_weights(p[ids] >= 2 / 3)
        if raw is not None:
            designs["tercileSpread"][date] = (ids, raw, 0.0)
            for label in liquidity:
                mask = tier[ids] == label
                weights = group_weights((p[ids] >= 2 / 3) & mask, (p[ids] <= 1 / 3) & mask)
                if weights is not None:
                    liquidity[label][date] = (ids, weights, 0.0)
        if top is not None:
            designs["topExcess"][date] = (ids, top, 0.0)
        ww = group_weights((wi[ids] >= 2 / 3) & industry_valid[ids], (wi[ids] <= 1 / 3) & industry_valid[ids])
        if ww is not None:
            converted = industry_adjust(data, book, ids, ww)
            if converted is not None:
                designs["withinIndustryTercileSpread"][date] = converted
        ic.append(rank_ic(v[ids] * direction, y[ids]))
        per_ind = []
        for group_ids, _ in data._industry_arrays.get(date, []):
            good = group_ids[valid[group_ids] & industry_valid[group_ids]]
            if len(good) >= 5:
                r = rank_ic(v[good] * direction, iy[good])
                if r is not None:
                    per_ind.append(r)
        wi_ic.append(float(np.mean(per_ind)) if per_ind else None)
    summaries = {k: linear_summary(data, book, d, scheduled, spec) for k, d in designs.items()}
    summaries["rankIC"] = nw_summary(ic, h)
    summaries["withinIndustryRankIC"] = nw_summary(wi_ic, h)
    used = valid & np.isin(dates, scheduled)
    return {
        "featureId": feature["featureId"],
        "family": feature["family"],
        "horizon": h,
        "direction": direction,
        "counts": counts,
        "observedSecurities": len(set(ticker[used])),
        "statistics": summaries,
        "stability": stability(summaries["tercileSpread"], data, h, spec),
        "liquidityTiers": {
            k: linear_summary(data, book, d, scheduled, spec, inferential=False) for k, d in liquidity.items()
        },
        "missingnessReasons": dict(Counter(data.reasons.loc[np.isin(dates, scheduled), feature["featureId"]]))
        if data.reasons is not None
        else {},
        "sampleSha256": digest(data.rows.loc[used, ["date", "ticker"]].to_dict("records")),
    }


def matched_comparison(data, book, pbase, palt, scheduled, spec):
    common = np.isfinite(pbase) & np.isfinite(palt) & book.table.state.eq("VALID").to_numpy()
    mse, spread = {}, {}
    samples = []
    for date in scheduled:
        ids = data.rows.index[data.rows.date.eq(date) & common].to_numpy(int)
        if len(ids) < 30:
            continue
        base, alt = np.asarray(pbase)[ids], np.asarray(palt)[ids]
        m = paired_mse_design(base, alt)
        mse[date] = (ids, m.weights - m.weights.mean(), m.signal_term)
        a = rank_weighted_spread_design(alt, data.rows.loc[ids, "ticker"].to_numpy()).weights
        b = rank_weighted_spread_design(base, data.rows.loc[ids, "ticker"].to_numpy()).weights
        spread[date] = (ids, a - b, 0.0)
        samples.extend(ids.tolist())
    return {
        "pairedMseImprovement": linear_summary(data, book, mse, scheduled, spec),
        "pairedRankWeightedSpreadImprovement": linear_summary(data, book, spread, scheduled, spec),
        "commonObservations": len(samples),
        "sampleSha256": digest(data.rows.loc[samples, ["date", "ticker"]].to_dict("records")),
        "identicalEvaluationPopulation": True,
        "identicalPredictionsOnCommonSample": bool(np.array_equal(np.asarray(pbase)[common], np.asarray(palt)[common])),
        "preCommonBase": int(np.isfinite(pbase).sum()),
        "preCommonAlternative": int(np.isfinite(palt).sum()),
    }
