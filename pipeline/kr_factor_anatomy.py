"""KR factor anatomy v1 — pure descriptive instruments.

EXPLORATORY / DEVELOPMENT / HYPOTHESIS-GENERATING. Every Korean date through the
2026-09-14 cutoff is already outcome-exposed, so nothing here validates, rescues or
promotes anything. There is no I/O, no network, no model fit and no portfolio in this
module: it receives frames and returns tables.

Three rules run through every function and are tested on synthetic data:

* RANKS ARE SIGNAL-TIME. A name's percentile and bucket are computed from the
  cross-section known at the signal date, BEFORE any outcome is attached. A name whose
  outcome is later withheld still occupies its rank slot; it merely contributes no return.
* DATES ARE WEIGHTED EQUALLY. Every statistic is first a per-date number; the study-level
  figure is the mean over dates, so a date with 120 names never outweighs one with 60.
* NOTHING IS TUNED. Every threshold is read from the frozen spec passed in; no function
  chooses a cutoff, a best factor or a winner.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from . import kr_model_overlay_portfolio as M
from . import kr_model_portfolio_execution as X
from . import kr_value_quality_catalyst as F

# Target statuses of the sealed v1 target (`target_from_sessions`). Literal copies, proved equal to the sealed module's
# own constants by a test: the repository's frozen import-guard tests allow-list which pipeline modules may import the
# `alpha_opportunity` research modules, this module is not on that list, and those tests are pinned by sealed v1.
MATURED, PENDING, UNRESOLVED = "MATURED", "PENDING", "MISSING_FORWARD_PRICE_OR_DELISTING"
digest = X.digest
RETURN_BASIS = "BENCHMARK_RELATIVE_ADJUSTED_INDEX_RETURN_PARTIAL_DISTRIBUTIONS"
DESCRIPTIVE_LABELS = (
    "BROADLY_POSITIVE_HISTORICAL_ASSOCIATION",
    "BROADLY_NEGATIVE_HISTORICAL_ASSOCIATION",
    "UNSTABLE_OR_REGIME_DEPENDENT",
    "CONCENTRATED_IN_SPECIFIC_STRATA",
    "NO_CLEAR_MONOTONIC_PATTERN",
    "DATA_INSUFFICIENT",
)
STATES = ("FUNDAMENTALS_UP_PRICE_UP", "FUNDAMENTALS_UP_PRICE_DOWN",
          "FUNDAMENTALS_DOWN_PRICE_UP", "FUNDAMENTALS_DOWN_PRICE_DOWN")
FORBIDDEN_OUTPUT_KEY_FRAGMENTS = ("promot", "productionready", "bestfactor", "verdict", "passfail", "winnerfactor")


# --------------------------------------------------------------------------- #
# Signal-time ranks
# --------------------------------------------------------------------------- #
def clean_numeric(values):
    """Float array with non-finite values as NaN. Fast path for numeric arrays: this runs per date, per factor."""
    if isinstance(values, pd.Series) and values.dtype.kind in "fiub":
        arr = values.to_numpy(float)
    elif isinstance(values, np.ndarray) and values.dtype.kind in "fiub":
        arr = values.astype(float)
    else:
        arr = pd.to_numeric(pd.Series(list(values) if not isinstance(values, pd.Series) else values), errors="coerce").to_numpy(float)
    return np.where(np.isfinite(arr), arr, np.nan)


def pct_rank(values):
    """Average-rank percentile in (0, 1); NaN stays NaN. Tied values share one percentile,
    so the result does not depend on row order or on any tie-break key."""
    x = clean_numeric(values)
    out = np.full(len(x), np.nan)
    ok = np.isfinite(x)
    if ok.any():
        out[ok] = (rankdata(x[ok], method="average") - 0.5) / ok.sum()
    return out


def bucket(pct, k):
    """0-based bucket from a percentile; -1 where the percentile is missing."""
    p = np.asarray(pct, float)
    out = np.full(len(p), -1, dtype=int)
    ok = np.isfinite(p)
    out[ok] = np.minimum(np.floor(p[ok] * k), k - 1).astype(int)
    return out


def add_signal_time_ranks(frame, columns):
    """Add `<col>__pct` and `<col>__n` (finite names that date) from SAME-DATE values only."""
    out = frame.copy().reset_index(drop=True)
    groups = out.groupby("date", sort=False).indices
    for col in columns:
        values = clean_numeric(out[col])
        pct, count = np.full(len(out), np.nan), np.zeros(len(out), dtype=int)
        for index in groups.values():
            part = values[index]
            pct[index] = pct_rank(part)
            count[index] = int(np.isfinite(part).sum())
        out[col + "__pct"] = pct
        out[col + "__n"] = count
    return out


def spearman(a, b):
    a, b = clean_numeric(a), clean_numeric(b)
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 3:
        return float("nan")
    x, y = rankdata(a[ok]), rankdata(b[ok])
    if np.std(x) == 0 or np.std(y) == 0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


# --------------------------------------------------------------------------- #
# Block-bootstrap uncertainty (repository date-block convention)
# --------------------------------------------------------------------------- #
def moving_block_indices(n_dates, block_length, rng):
    """Moving-block resample of complete date rows, never iid names. Literal copy of the repository convention
    (`alpha_opportunity_model.block_sample_indices`), proved identical for identical seeds by a test."""
    if n_dates < block_length:
        raise ValueError("DATA_INSUFFICIENT_BLOCKS")
    starts = rng.integers(0, n_dates - block_length + 1, size=math.ceil(n_dates / block_length))
    return np.concatenate([np.arange(s, s + block_length) for s in starts])[:n_dates]


def col_nanmean(matrix):
    """Column means over finite entries only, NaN where a column has none; no warnings, fixed summation order."""
    m = np.asarray(matrix, float)
    ok = np.isfinite(m)
    count = ok.sum(axis=0)
    total = np.where(ok, m, 0.0).sum(axis=0)
    return np.divide(total, count, out=np.full(m.shape[1], np.nan), where=count > 0)


def block_interval_columns(matrix, block, cfg):
    """Moving blocks of complete chronological per-date rows, the repository's
    date-block convention, exactly as the v2 evaluation resamples date summaries. Descriptive:
    no calibration claim, no multiplicity adjustment, no decision role."""
    m = np.asarray(matrix, float)
    n = m.shape[0]
    if n < cfg["minimumEvaluationBlocks"] * block:
        return {"status": "DATA_INSUFFICIENT", "dates": n, "blockDates": block}
    rng = np.random.default_rng(cfg["seed"])
    draws = np.empty((cfg["replicates"], m.shape[1]))
    for r in range(cfg["replicates"]):
        draws[r] = col_nanmean(m[moving_block_indices(n, block, rng)])
    tail = cfg["twoSidedTail"]
    point = col_nanmean(m)
    lower, upper = np.nanquantile(draws, tail, axis=0), np.nanquantile(draws, 1 - tail, axis=0)
    return {"status": "DESCRIPTIVE", "dates": n, "blockDates": block, "nonoverlapBlockFloor": n // block,
            "estimate": point.tolist(), "lower": lower.tolist(), "upper": upper.tolist(),
            "level": 1 - 2 * tail, "calibrated": False, "multiplicityAdjusted": False}


# --------------------------------------------------------------------------- #
# Standalone decile anatomy
# --------------------------------------------------------------------------- #
def per_date_factor_stats(frame, col, outcome, cfg):
    """One row per signal date. `frame` carries `<col>__pct`, `<col>__n`, `date`, the outcome
    column (NaN where withheld) and nothing the outcome could have influenced."""
    pct_all = frame[col + "__pct"].to_numpy(float)
    count_all = frame[col + "__n"].to_numpy(int)
    y_all = clean_numeric(frame[outcome])
    rows = []
    for date, index in sorted(frame.groupby("date").indices.items()):
        n_signal = int(count_all[index[0]])
        pct, y = pct_all[index], y_all[index]
        valid = np.isfinite(y) & np.isfinite(pct)
        record = {"date": date, "year": int(date[:4]), "signalNames": n_signal, "outcomeNames": int(valid.sum()),
                  "means": [math.nan] * 10, "medians": [math.nan] * 10, "beat": [math.nan] * 10,
                  "counts": [0] * 10, "spread": math.nan, "rho": math.nan}
        # Rows are processed in (percentile, outcome) order so every float sum is independent of input row order.
        order = np.lexsort((y[valid], pct[valid]))
        pv, yv = pct[valid][order], y[valid][order]
        if n_signal >= cfg["decileMinimumNames"] and valid.any():
            b = bucket(pv, 10)
            yy = yv
            for k in range(10):
                members = yy[b == k]
                record["counts"][k] = int(len(members))
                if len(members):
                    record["means"][k] = float(members.mean())
                    record["medians"][k] = float(np.median(members))
                    record["beat"][k] = float((members > 0).mean())
            if np.isfinite(record["means"][0]) and np.isfinite(record["means"][9]):
                record["spread"] = record["means"][9] - record["means"][0]
        if n_signal >= cfg["rankCorrelationMinimumNames"] and valid.sum() >= cfg["rankCorrelationMinimumNames"]:
            record["rho"] = spearman(pv, yv)
        rows.append(record)
    return rows


def _nanmean(values):
    arr = np.asarray(values, float)
    arr = arr[np.isfinite(arr)]
    return float(arr.mean()) if len(arr) else float("nan")


def year_table(rows, key, cfg):
    years = {}
    for r in rows:
        if np.isfinite(r[key]):
            years.setdefault(r["year"], []).append(r[key])
    table = {str(y): {"dates": len(v), "mean": float(np.mean(v)), "positive": bool(np.mean(v) > 0)}
             for y, v in sorted(years.items())}
    eligible = {y: v for y, v in table.items() if v["dates"] >= cfg["minimumDatesPerYear"]}
    positive = sum(v["positive"] for v in eligible.values())
    return table, {"eligibleYears": len(eligible), "positiveYears": int(positive),
                   "positiveYearFraction": (positive / len(eligible)) if eligible else None}


def leave_best_year_out(rows, key):
    """Drop the one calendar year contributing most in the pooled sign's direction; report whether
    the equal-date mean keeps its sign. The rule is fixed here, before any result exists."""
    values = [(r["year"], r[key]) for r in rows if np.isfinite(r[key])]
    if not values:
        return None
    pooled = float(np.mean([v for _, v in values]))
    totals = {}
    for year, v in values:
        totals[year] = totals.get(year, 0.0) + v
    best = max(totals, key=lambda y: (totals[y] if pooled >= 0 else -totals[y], -y))
    rest = [v for year, v in values if year != best]
    if not rest:
        return None
    remaining = float(np.mean(rest))
    return {"droppedYear": int(best), "meanWithoutYear": remaining,
            "signRetained": bool(np.sign(remaining) == np.sign(pooled) and pooled != 0)}


def factor_anatomy(frame, col, outcome, horizon, spec):
    """All frozen standalone outputs for one factor / horizon / universe / terminal treatment."""
    stats, unc = spec["statistics"], spec["uncertainty"]
    rows = per_date_factor_stats(frame, col, outcome, stats)
    means = np.array([r["means"] for r in rows], float).reshape(-1, 10)
    medians = np.array([r["medians"] for r in rows], float).reshape(-1, 10)
    beat = np.array([r["beat"] for r in rows], float).reshape(-1, 10)
    counts = np.array([r["counts"] for r in rows], int).reshape(-1, 10)
    agg_means = col_nanmean(means) if len(rows) else np.full(10, np.nan)
    agg_medians = col_nanmean(medians) if len(rows) else np.full(10, np.nan)
    agg_beat = col_nanmean(beat) if len(rows) else np.full(10, np.nan)
    spreads = [r["spread"] for r in rows]
    rhos = [r["rho"] for r in rows]
    annual_spread, spread_stability = year_table(rows, "spread", stats)
    annual_rho, rho_stability = year_table(rows, "rho", stats)
    monotonic = spearman(np.arange(10), agg_means) if np.isfinite(agg_means).sum() >= 5 else float("nan")
    block = unc["blockDates"][str(horizon)]
    matrix = np.column_stack([means, np.array(spreads, float), np.array(rhos, float)]) if rows else np.empty((0, 12))
    defined = matrix[~np.isnan(matrix).all(axis=1)] if len(rows) else matrix
    interval = block_interval_columns(defined, block, unc)
    return {
        "factor": col, "horizon": horizon, "returnBasis": RETURN_BASIS,
        "datesWithDeciles": int(np.isfinite(spreads).sum()), "datesWithRankCorrelation": int(np.isfinite(rhos).sum()),
        "datesConsidered": len(rows), "outcomeObservations": int(counts.sum()),
        "decileMeanRelative": agg_means.tolist(), "decileMedianRelative": agg_medians.tolist(),
        "decileBeatBenchmarkFraction": agg_beat.tolist(), "decileObservations": counts.sum(axis=0).tolist(),
        "d10MinusD1": _nanmean(spreads), "meanRankCorrelation": _nanmean(rhos),
        "decileMonotonicity": monotonic if np.isfinite(monotonic) else None,
        "annualD10MinusD1": annual_spread, "annualRankCorrelation": annual_rho,
        "spreadYearStability": spread_stability, "rankCorrelationYearStability": rho_stability,
        "leaveBestYearOut": leave_best_year_out(rows, "spread"),
        "interval": interval,
        "intervalColumns": ["decile1", "decile2", "decile3", "decile4", "decile5", "decile6", "decile7",
                            "decile8", "decile9", "decile10", "d10MinusD1", "rankCorrelation"],
        "perDate": rows,
    }


# --------------------------------------------------------------------------- #
# Strata (size / liquidity)
# --------------------------------------------------------------------------- #
def stratified_association(frame, value, partition, outcome, spec, *, k=5):
    """Within-date, within-stratum association of `value` with the outcome. Strata are SIGNAL-TIME
    quantiles of `partition`; within-stratum halves are SIGNAL-TIME ranks of `value` inside the stratum.
    Reported as mean rank correlation and mean (upper half - lower half) outcome, plus the stratum's own
    mean outcome. Descriptive; no causal reading."""
    stats = spec["statistics"]
    cell_min = stats["strataCellMinimumNames"]
    per = {q: {"rho": [], "halves": [], "level": []} for q in range(k)}
    part_all, val_all, y_all = clean_numeric(frame[partition]), clean_numeric(frame[value]), clean_numeric(frame[outcome])
    for _, index in sorted(frame.groupby("date").indices.items()):
        part = part_all[index]
        if np.isfinite(part).sum() < stats["quintileMinimumNames"]:
            continue
        stratum = bucket(pct_rank(part), k)
        val, y = val_all[index], y_all[index]
        for q in range(k):
            members = (stratum == q) & np.isfinite(val)
            if members.sum() < cell_min:
                continue
            within = pct_rank(val[members])
            ok = np.isfinite(y[members])
            if ok.sum() < cell_min:
                continue
            yy, ww = y[members][ok], within[ok]
            order = np.lexsort((yy, ww))
            yy, ww = yy[order], ww[order]
            per[q]["rho"].append(spearman(ww, yy))
            hi, lo = yy[ww >= 0.5], yy[ww < 0.5]
            if len(hi) and len(lo):
                per[q]["halves"].append(float(hi.mean() - lo.mean()))
            per[q]["level"].append(float(yy.mean()))
    table = {}
    for q in range(k):
        r = per[q]
        table[str(q + 1)] = {"dates": len([x for x in r["rho"] if np.isfinite(x)]),
                             "meanRankCorrelation": _nanmean(r["rho"]) if r["rho"] else None,
                             "meanUpperMinusLowerHalf": _nanmean(r["halves"]) if r["halves"] else None,
                             "meanOutcomeInStratum": _nanmean(r["level"]) if r["level"] else None}
    return {"value": value, "partition": partition, "strata": k, "table": table}


def strata_agreement(table, pooled_sign):
    """How many measured strata share the pooled sign of the rank correlation."""
    measured = [v["meanRankCorrelation"] for v in table.values()
                if v["meanRankCorrelation"] is not None and np.isfinite(v["meanRankCorrelation"])]
    if not measured or pooled_sign == 0:
        return {"measured": len(measured), "agreeing": 0}
    return {"measured": len(measured), "agreeing": int(sum(np.sign(v) == pooled_sign for v in measured))}


# --------------------------------------------------------------------------- #
# Interactions (frozen cutoffs only)
# --------------------------------------------------------------------------- #
def axis_groups(g, col, rule, stats):
    """Signal-time group index per row for one axis: terciles by within-date percentile, or the
    fixed sign rule `value > 0`. -1 = not formed (missing, or too few names that date)."""
    x = clean_numeric(g[col])
    if rule["kind"] == "binaryPositive":
        out = np.full(len(x), -1, dtype=int)
        ok = np.isfinite(x)
        out[ok] = (x[ok] > 0).astype(int)
        return out if ok.sum() >= stats["rankCorrelationMinimumNames"] else np.full(len(x), -1, dtype=int)
    if np.isfinite(x).sum() < stats["tercileMinimumNames"]:
        return np.full(len(x), -1, dtype=int)
    return bucket(pct_rank(x), 3)


def interaction_table(frame, a, b, outcome, spec):
    stats = spec["statistics"]
    rule_a, rule_b = a["rule"], b["rule"]
    per = {}
    for _, g in frame.groupby("date", sort=True):
        ga, gb = axis_groups(g, a["column"], rule_a, stats), axis_groups(g, b["column"], rule_b, stats)
        y = clean_numeric(g[outcome])
        for i, j in {(int(p), int(q)) for p, q in zip(ga, gb) if p >= 0 and q >= 0}:
            sel = (ga == i) & (gb == j) & np.isfinite(y)
            if sel.sum() >= stats["interactionCellMinimumNames"]:
                cell = per.setdefault((i, j), {"mean": [], "beat": [], "names": 0})
                cell["mean"].append(float(np.sort(y[sel]).mean()))
                cell["beat"].append(float((y[sel] > 0).mean()))
                cell["names"] += int(sel.sum())
    cells = {f"{a['column']}={i}|{b['column']}={j}": {"dates": len(v["mean"]), "names": v["names"],
                                                       "meanRelative": float(np.mean(v["mean"])),
                                                       "beatBenchmarkFraction": float(np.mean(v["beat"]))}
             for (i, j), v in sorted(per.items())}
    return {"axisA": {"column": a["column"], "rule": rule_a}, "axisB": {"column": b["column"], "rule": rule_b},
            "cells": cells}


# --------------------------------------------------------------------------- #
# Fundamentals up / price down
# --------------------------------------------------------------------------- #
def four_state_table(frame, up_flag, outcome, *, strata=None, spec=None, mean_columns=()):
    """Four descriptive states from a fundamentals flag (True/False; None = not formed) and the sign of the
    outcome. Shares are per-date then date-equal-weighted. Optional strata add the composition of the
    FUNDAMENTALS_UP_PRICE_DOWN state against all fundamentals-up observations (a lift, never a cause)."""
    per_date, per_year, composition = [], {}, {}
    strata = strata or {}
    for date, g in frame.groupby("date", sort=True):
        up = g[up_flag].to_numpy(object)
        y = clean_numeric(g[outcome])
        ok = np.array([u is not None and not (isinstance(u, float) and math.isnan(u)) for u in up]) & np.isfinite(y)
        if not ok.any():
            continue
        u = np.array([bool(v) for v in up[ok]])
        pos = y[ok] > 0
        masks = {STATES[0]: u & pos, STATES[1]: u & ~pos, STATES[2]: ~u & pos, STATES[3]: ~u & ~pos}
        record = {"date": date, "year": int(date[:4]), "names": int(ok.sum()),
                  "share": {s: float(m.mean()) for s, m in masks.items()},
                  "count": {s: int(m.sum()) for s, m in masks.items()}}
        for col in mean_columns:
            vals = clean_numeric(g[col])[ok]
            record.setdefault("mean", {})[col] = {s: (float(np.nanmean(vals[m])) if m.any() and np.isfinite(vals[m]).any()
                                                      else None) for s, m in masks.items()}
        for name, definition in strata.items():
            x = clean_numeric(g[definition["column"]])
            if np.isfinite(x).sum() < spec["statistics"]["tercileMinimumNames"]:
                continue
            tier = bucket(pct_rank(x), 3)[ok]
            valid = tier >= 0
            up_all, down_up = u & valid, masks[STATES[1]] & valid
            if up_all.sum() == 0 or down_up.sum() == 0:
                continue
            record.setdefault("composition", {})[name] = {
                str(t): {"shareOfFundamentalsUpPriceDown": float((tier[down_up] == t).mean()),
                         "shareOfAllFundamentalsUp": float((tier[up_all] == t).mean())} for t in range(3)}
        per_date.append(record)
    if not per_date:
        return {"status": "DATA_INSUFFICIENT", "dates": 0}
    overall = {s: float(np.mean([r["share"][s] for r in per_date])) for s in STATES}
    for r in per_date:
        per_year.setdefault(r["year"], []).append(r)
    annual = {str(y): {"dates": len(rs), **{s: float(np.mean([r["share"][s] for r in rs])) for s in STATES}}
              for y, rs in sorted(per_year.items())}
    names = {s: int(sum(r["count"][s] for r in per_date)) for s in STATES}
    for name in strata:
        rows = [r["composition"][name] for r in per_date if "composition" in r and name in r["composition"]]
        if rows:
            composition[name] = {str(t): {
                "shareOfFundamentalsUpPriceDown": float(np.mean([r[str(t)]["shareOfFundamentalsUpPriceDown"] for r in rows])),
                "shareOfAllFundamentalsUp": float(np.mean([r[str(t)]["shareOfAllFundamentalsUp"] for r in rows])),
                "dates": len(rows)} for t in range(3)}
    means = {}
    for col in mean_columns:
        means[col] = {s: _nanmean([r["mean"][col][s] for r in per_date if r.get("mean", {}).get(col, {}).get(s) is not None])
                      for s in STATES}
    return {"status": "DESCRIPTIVE", "dates": len(per_date), "shareByState": overall, "observationsByState": names,
            "annual": annual, "compositionOfFundamentalsUpPriceDown": composition, "meanByState": means,
            "causalReading": "NONE"}


# --------------------------------------------------------------------------- #
# Rule-based descriptive labels (never a gate, never a score)
# --------------------------------------------------------------------------- #
def canonical_sign(anatomy):
    """THE frozen canonical direction of a factor: the sign of its equal-date D10-D1. Every strata-agreement check and
    the executive map's `direction` use this one number, never a second sign."""
    spread = anatomy["d10MinusD1"]
    if spread is None or not np.isfinite(spread) or spread == 0:
        return 0
    return 1 if spread > 0 else -1


def direction_measures(anatomy):
    """The three major direction measures and whether they agree. Zero or missing counts as disagreement: a measure
    with no direction cannot corroborate one."""
    def sign(value):
        return 0 if value is None or not np.isfinite(value) or value == 0 else (1 if value > 0 else -1)
    signs = {"d10MinusD1": sign(anatomy["d10MinusD1"]), "decileMonotonicity": sign(anatomy["decileMonotonicity"]),
             "meanRankCorrelation": sign(anatomy["meanRankCorrelation"])}
    values = set(signs.values())
    return {"signs": signs, "consistent": len(values) == 1 and 0 not in values}


def descriptive_label(anatomy, agreement, spec):
    """Rule-based, frozen. First match wins. BROADLY_POSITIVE / BROADLY_NEGATIVE are reachable only when D10-D1, decile
    monotonicity and the mean within-date rank correlation all share one sign; any disagreement among them is
    NO_CLEAR_MONOTONIC_PATTERN, never a direction."""
    cfg = spec["interpretation"]
    if (anatomy["datesWithDeciles"] < cfg["minimumDatesForLabel"] or anatomy["decileMonotonicity"] is None
            or anatomy["spreadYearStability"]["positiveYearFraction"] is None):
        return "DATA_INSUFFICIENT"
    if not direction_measures(anatomy)["consistent"] or abs(anatomy["decileMonotonicity"]) < cfg["monotonicityFloor"]:
        return "NO_CLEAR_MONOTONIC_PATTERN"
    sign = canonical_sign(anatomy)
    fraction = anatomy["spreadYearStability"]["positiveYearFraction"]
    leave = anatomy["leaveBestYearOut"]
    flips = leave is not None and not leave["signRetained"]
    consistent = fraction >= cfg["yearFractionBroad"] if sign > 0 else fraction <= 1 - cfg["yearFractionBroad"]
    if flips or not consistent:
        return "UNSTABLE_OR_REGIME_DEPENDENT"
    if agreement is None or agreement["measured"] < cfg["minimumMeasuredStrata"]:
        return "DATA_INSUFFICIENT"
    if agreement["agreeing"] / agreement["measured"] < cfg["strataAgreementFraction"]:
        return "CONCENTRATED_IN_SPECIFIC_STRATA"
    return "BROADLY_POSITIVE_HISTORICAL_ASSOCIATION" if sign > 0 else "BROADLY_NEGATIVE_HISTORICAL_ASSOCIATION"


# --------------------------------------------------------------------------- #
# Mechanical event selection
# --------------------------------------------------------------------------- #
def select_nonoverlapping(events, score, *, descending, count):
    """Mechanical top-N: order by score then (date, ticker); skip any window that overlaps an already
    selected window of the SAME ticker (closed intervals on session dates) so one episode cannot fill the table."""
    if events.empty:
        return events.iloc[0:0]
    order = events.sort_values([score, "date", "ticker"], ascending=[not descending, True, True], kind="mergesort")
    chosen, windows = [], {}
    for row in order.itertuples():
        spans = windows.setdefault(row.ticker, [])
        if any(not (row.exitDate < s or row.entryDate > e) for s, e in spans):
            continue
        spans.append((row.entryDate, row.exitDate))
        chosen.append(row.Index)
        if len(chosen) == count:
            break
    return events.loc[chosen]


def mechanical_event_tables(events, spec):
    n = spec["winnersLosers"]["count"]
    events = events.copy()
    events["absStockReturn"] = events.stockReturn.abs()
    tables = {"largestPositiveStockReturn": select_nonoverlapping(events, "stockReturn", descending=True, count=n),
              "largestNegativeStockReturn": select_nonoverlapping(events, "stockReturn", descending=False, count=n),
              "largestAbsoluteStockReturn": select_nonoverlapping(events, "absStockReturn", descending=True, count=n),
              "benchmarkRelativeWinners": select_nonoverlapping(events, "relativeReturn", descending=True, count=n),
              "benchmarkRelativeLosers": select_nonoverlapping(events, "relativeReturn", descending=False, count=n)}
    if "predictionError" in events and events.predictionError.notna().any():
        scored = events.loc[events.predictionError.notna()]
        tables["largestPositivePredictionError"] = select_nonoverlapping(scored, "predictionError", descending=True, count=n)
        tables["largestNegativePredictionError"] = select_nonoverlapping(scored, "predictionError", descending=False, count=n)
    return tables


def top5_frequency(predictions, spec):
    """Tickers most often inside the sealed v1 top five by prediction rank."""
    n = spec["winnersLosers"]["count"]
    top = predictions.loc[predictions["rank"] <= 5]
    dates = max(int(predictions.date.nunique()), 1)
    counts = top.groupby("ticker").size().rename("topFiveDates").reset_index()
    counts["shareOfPredictionDates"] = counts.topFiveDates / dates
    return counts.sort_values(["topFiveDates", "ticker"], ascending=[False, True], kind="mergesort").head(n)


def case_selection(events, ticker, prediction_col="prediction"):
    """The four fixed extractions for one fixed ticker; None where no row exists."""
    own = events.loc[events.ticker == ticker]
    if own.empty or own[prediction_col].notna().sum() == 0:
        return {"status": "NO_DATA", "ticker": ticker}
    own = own.loc[own[prediction_col].notna() & own.relativeReturn.notna()]
    if own.empty:
        return {"status": "NO_VALID_OUTCOME", "ticker": ticker}
    def pick(column, descending):
        ordered = own.sort_values([column, "date"], ascending=[not descending, True], kind="mergesort")
        return ordered.iloc[0]
    return {"status": "SELECTED", "ticker": ticker,
            "highestPrediction": pick(prediction_col, True), "lowestPrediction": pick(prediction_col, False),
            "largestPositiveError": pick("predictionError", True), "largestNegativeError": pick("predictionError", False)}


# --------------------------------------------------------------------------- #
# Exact reconstruction of a sealed v1 prediction (never approximated)
# --------------------------------------------------------------------------- #
_V1_LINEAR_NAMES = tuple(n for n in F.RAW_FEATURES if n not in ("logAdv60", "relative126", "momentum121"))


def reconstruct_prediction(raw, fold, *, archived=None, tolerance=1e-8):
    """Rebuild the transformed row, family scores and per-term linear contributions of one sealed v1 Ridge
    prediction from its fold's transform snapshot. If an archived prediction is supplied and the
    decomposition does not reproduce it to `tolerance`, the result says MISMATCH and carries no contributions."""
    snap = fold["transformSnapshot"]
    names = list(snap["activeNames"])
    center, scale = np.asarray(snap["rawCenter"], float), np.asarray(snap["rawScale"], float)
    standardised, missing = [], []
    for j, name in enumerate(names):
        value = raw.get(name)
        value = float(value) if value is not None and np.isfinite(float(value)) else float("nan")
        if name in _V1_LINEAR_NAMES and np.isfinite(value):
            value = math.copysign(math.log1p(abs(value)), value)
        is_missing = not np.isfinite(value)
        filled = center[j] if is_missing else value
        standardised.append((filled - center[j]) / scale[j])
        missing.append(float(is_missing))
    x = np.asarray(standardised)
    scores = {family: float(np.mean([x[names.index(n)] for n in members if n in names]))
              for family, members in F.FAMILIES.items()}
    interaction = M.FamilyTransformer.interactions({f: np.array([v]) for f, v in scores.items()})[0]
    interaction = (interaction - np.asarray(snap["interactionCenter"])) / np.asarray(snap["interactionScale"])
    z = np.concatenate([x, np.asarray(missing), interaction])
    columns = list(fold["columns"])
    coefficients = np.asarray(fold["coefficients"], float)
    if len(z) != len(columns) or len(coefficients) != len(columns):
        return {"status": "MISMATCH", "reason": "COLUMN_COUNT"}
    contributions = z * coefficients
    prediction = float(fold["intercept"] + contributions.sum())
    out = {"status": "RECONSTRUCTED", "prediction": prediction, "intercept": float(fold["intercept"]),
           "familyScores": scores, "columns": columns, "transformed": dict(zip(columns, z.tolist())),
           "coefficients": dict(zip(columns, coefficients.tolist())),
           "contributions": dict(zip(columns, contributions.tolist())),
           "interactionContributions": {c: float(v) for c, v in zip(columns[-4:], contributions[-4:])}}
    if archived is not None and abs(prediction - float(archived)) > tolerance:
        return {"status": "MISMATCH", "reason": "ARCHIVED_PREDICTION_NOT_REPRODUCED",
                "reconstructed": prediction, "archived": float(archived)}
    return out


# --------------------------------------------------------------------------- #
# Endpoint semantics (must equal v1's target; checked against it, never replacing it)
# --------------------------------------------------------------------------- #
def endpoint_returns(sessions, prices, benchmark, ticker, date, horizon, through):
    """Stock and benchmark returns separately, same rule as `target_from_sessions`: entry = next KR session
    close strictly after the signal date, exit = `horizon` further sessions, exact endpoints only. The returns
    are of the replay `Close` column, i.e. the ADJUSTED INDEX with partial observed distributions."""
    days = pd.DatetimeIndex(sessions)
    pos = days.searchsorted(pd.Timestamp(date), side="right")
    if pos + horizon >= len(days):
        raise ValueError("CALENDAR_TOO_SHORT")
    entry, exit_ = days[pos], days[pos + horizon]
    out = {"entryDate": str(entry.date()), "exitDate": str(exit_.date()), "stockReturn": None,
           "benchmarkReturn": None, "relativeReturn": None, "status": PENDING, "returnBasis": RETURN_BASIS}
    if exit_ > pd.Timestamp(through):
        return out
    out["status"] = UNRESOLVED
    values = []
    for name in (ticker, benchmark):
        frame = prices.get(name)
        if frame is None or entry not in frame.index or exit_ not in frame.index:
            return out
        a, z = frame.loc[entry, "Close"], frame.loc[exit_, "Close"]
        if not np.isfinite([a, z]).all() or min(a, z) <= 0:
            return out
        values.append(float(z / a - 1.0))
    out.update(stockReturn=values[0], benchmarkReturn=values[1], relativeReturn=values[0] - values[1], status=MATURED)
    return out


def assert_pit_membership(panel, memberships):
    """Every analysed row must be a member of that date's PIT cross-section; nothing is added from today's list."""
    for date, group in panel.groupby("date"):
        snapshot = memberships.on(date)
        if snapshot is None or not set(group.ticker) <= set(snapshot["members"]):
            raise ValueError("NON_PIT_ROW_IN_ANALYSIS_PANEL: " + date)
    return True


# --------------------------------------------------------------------------- #
# Universes
# --------------------------------------------------------------------------- #
def universe_mask(panel, name, spec):
    """A = the PIT membership rows themselves (no other signal-time filter). B = A plus exactly the v1 stock
    eligibility conditions of `kr_concentrated_portfolio.eligible`."""
    if name == "PIT_TOP120_LARGE_CAP_ANALYSIS_UNIVERSE":
        return pd.Series(True, index=panel.index)
    if name == "PIT_TOP120_V1_INVESTABLE_ANALYSIS_UNIVERSE":
        cfg = spec["universes"]["PIT_TOP120_V1_INVESTABLE_ANALYSIS_UNIVERSE"]["v1Constraints"]
        adv, vol = clean_numeric(panel.adv60), clean_numeric(panel.downsideVol126)
        return (panel.coreFamilyObserved.fillna(False).astype(bool) & panel.tradable.fillna(False).astype(bool)
                & np.isfinite(adv) & (adv >= cfg["minimumAdvKrw"])
                & np.isfinite(vol) & (vol >= cfg["minimumDownsideVol"]))
    raise ValueError("UNREGISTERED_UNIVERSE")


# --------------------------------------------------------------------------- #
# Structural classification gate
# --------------------------------------------------------------------------- #
def structural_status(spec, root):
    """PASSED only if the spec itself pins a classification document that exists byte-for-byte. A document
    present on disk that the spec does not pin is refused: a list may not appear after outcomes exist."""
    block = spec["structuralClassification"]
    path = Path(root) / block["classificationPath"]
    if block["status"] != "PASSED":
        if path.exists():
            raise ValueError("UNPINNED_STRUCTURAL_CLASSIFICATION_PRESENT")
        return {"status": block["status"], "subgroupTables": "DATA_FOUNDATION_REQUIRED"}
    if not path.is_file() or digest(json.loads(path.read_text())) != block["classificationSha256"]:
        raise ValueError("STRUCTURAL_CLASSIFICATION_MISSING_OR_CHANGED")
    return {"status": "PASSED", "classificationSha256": block["classificationSha256"]}


def apply_exclusion(panel, tickers):
    """Mechanical leave-out; the removed names are returned too so the exclusion is auditable."""
    drop = panel.ticker.isin(set(tickers))
    return panel.loc[~drop], panel.loc[drop]


def assert_no_forbidden_keys(value, path=""):
    """Outputs may not carry promotion/PASS/FAIL/best-factor semantics anywhere in their key space."""
    if isinstance(value, dict):
        for key, item in value.items():
            if any(fragment in str(key).lower().replace("_", "") for fragment in FORBIDDEN_OUTPUT_KEY_FRAGMENTS):
                raise ValueError("FORBIDDEN_OUTPUT_KEY: " + path + "/" + str(key))
            assert_no_forbidden_keys(item, path + "/" + str(key))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            assert_no_forbidden_keys(item, path + "[" + str(i) + "]")
    return True
