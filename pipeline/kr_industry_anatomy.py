"""KR industry opportunity anatomy v1 — pure descriptive instruments.

EXPLORATORY_DEVELOPMENT_ON_PARTIALLY_RECONSTRUCTED_KR_HISTORY. Every Korean date through the development cutoff is
already outcome-exposed and the industry membership is a reconstruction (current official KIND anchor plus disclosed
change events, `DATA_FOUNDATION_INSUFFICIENT_V4`), so nothing here validates, selects or promotes anything.

No I/O, no network, no model fit, no portfolio. Functions receive frames and return tables. Anatomy helpers
(`kr_factor_anatomy`, `kr_top120_regime_review`) are REUSED, never copied, where the arithmetic is identical.

Rules that run through every function and are tested on synthetic data:

* THE COHORT IS FROZEN AT THE SIGNAL DATE. Membership is looked up once at t from the reconstruction, weights are the
  signal-date market caps, and neither is revisited during the forward window or the trailing window.
* AN INELIGIBLE INDUSTRY-DATE IS INELIGIBLE, NOT ZERO. Fewer than five classified members, an unavailable cap weight (primary
  lens) or an incomplete forward window yields a status and a reason, never a number. UNKNOWN names are never used to fill a
  cohort, terminal names are never replaced by survivors or successors, and no return is renormalised over the survivors.
* MISSING IS MISSING. A fundamental aggregate needs a frozen share of finite members; otherwise it is NaN.
* NOTHING IS TUNED. Every threshold is a module constant frozen in the spec before any outcome exists.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import kr_factor_anatomy as A
from . import kr_industry_membership_v3 as V3
from . import kr_top120_regime_review as R

STUDY = "kr-industry-opportunity-anatomy-v1"
SCIENTIFIC_STATUS = "EXPLORATORY_DEVELOPMENT_ON_PARTIALLY_RECONSTRUCTED_KR_HISTORY"
RETURN_BASIS = A.RETURN_BASIS
BENCHMARK = "069500.KS"
HORIZONS = (63, 126, 252)
PRIMARY_HORIZON = 126
LENSES = ("CAP_WEIGHTED", "EQUAL_WEIGHT")
PRIMARY_LENS = "CAP_WEIGHTED"
MIN_MEMBERS = 5                    # classified constituents present at the signal date
MIN_FUNDAMENTAL_SHARE = 0.6        # finite members needed (and at least 3) for a fundamental aggregate
MIN_FUNDAMENTAL_COUNT = 3
MIN_CROSS_SECTION = 8              # eligible industries with finite feature and target for a per-date Spearman
MIN_TERCILE_CROSS_SECTION = 9      # three industries per tercile at least
STRATUM_TOP1_SHARE_CUTOFF = 0.35   # fixed concentration stratum boundary
MIN_STRATUM_CROSS_SECTION = 5
TRAILING = (63, 126)
BREADTH_WINDOW = 126
RISK_WINDOW = 126
ANNUALISATION = 252
ELIGIBLE_MEMBERSHIP_STATUSES = ("CURRENT_KRX_KIND_ANCHOR", "VERIFIED_KRX_KIND_CHANGE_EVENT",
                                "RECONSTRUCTED_STABLE_NO_CHANGE_EVENT", "PREFERRED_SHARE_OF_ANCHORED_COMMON",
                                "RETAINED_DART_FALLBACK")
FUNDAMENTAL_COLUMNS = ("bookToMarketProxy", "earningsYieldProxy", "ocfYieldProxy", "netIncomeToAssets", "ocfToAssets",
                       "negativeAccrualsToAssets", "ocfImprovementToAssets", "netIncomeImprovementToAssets")
FEATURES = (
    "REL_MOM_63", "REL_MOM_126",
    "BREADTH_POSITIVE_126", "BREADTH_ABOVE_MA_126", "BREADTH_REL_MOM_POSITIVE_126",
    "DOWNSIDE_VOL_126", "CONSTITUENT_DISPERSION_126",
    "TOP1_CAP_SHARE", "TOP2_CAP_SHARE", "CONSTITUENT_COUNT", "MEDIAN_LOG_ADV60",
) + tuple("MEDIAN_" + c for c in FUNDAMENTAL_COLUMNS)
SENSITIVITIES = ("FULL", "LEAVE_LARGEST_CONSTITUENT_OUT", "EXCLUDE_SAMSUNG_ELECTRONICS_AND_SK_HYNIX")
EXCLUDED_MEGA_CAPS = ("005930.KS", "000660.KS")
STRATA = ("TOP1_CAP_SHARE_LOW", "TOP1_CAP_SHARE_HIGH")
SLICES = ("FULL_SAMPLE", "PRE_2025_COMPLETE_WINDOW", "TOUCHES_2025_OR_LATER", "TOUCHES_2026")
FORBIDDEN_OUTPUT_KEY_FRAGMENTS = A.FORBIDDEN_OUTPUT_KEY_FRAGMENTS + (
    "validated", "proven", "bestfeature", "recommend", "production", "alpha", "passed", "failed")


def norm(text):
    return "".join((text or "").split())


# --------------------------------------------------------------------------- #
# Membership at the signal date
# --------------------------------------------------------------------------- #
def industry_of(intervals, crosswalk, ticker, date):
    """(industry_id, status). UNKNOWN / CONFLICT / unmapped label -> (None, reason). Never a nearest group."""
    ivs = intervals.get(ticker)
    if not ivs:
        return None, "NO_RECONSTRUCTION"
    iv = V3.label_at(ivs, date)
    if iv is None or not iv.get("label"):
        return None, (iv or {}).get("status", "UNKNOWN")
    status = iv.get("reconstruction_status") or iv.get("status")
    if status not in ELIGIBLE_MEMBERSHIP_STATUSES:
        return None, "STATUS_NOT_ELIGIBLE:" + str(status)
    group = crosswalk["mapping"].get(norm(iv["label"]))
    if group is None:
        return None, "UNMAPPED_LABEL"
    return group, status


def membership_table(schedule, intervals, crosswalk, terminated=None):
    """One row per PIT Top120 member per signal date. `terminated` maps ticker -> end date: on or after it the name is UNKNOWN."""
    terminated = terminated or {}
    rows = []
    for date, names in sorted(schedule.items()):
        for ticker in names:
            end = terminated.get(ticker)
            if end and date >= end:
                group, status = None, "IDENTITY_TERMINATED"
            else:
                group, status = industry_of(intervals, crosswalk, ticker, date)
            rows.append({"date": date, "ticker": ticker, "industry": group, "membershipStatus": status})
    return pd.DataFrame(rows, columns=["date", "ticker", "industry", "membershipStatus"])


# --------------------------------------------------------------------------- #
# Cohorts: frozen at the signal date
# --------------------------------------------------------------------------- #
def build_cohorts(membership, caps, *, exclude=(), leave_largest_out=False):
    """dict[(date, industry)] -> cohort record. `caps` has date, ticker, marketCap (signal-date values only).

    Constituents = classified PIT members of that industry on that date, minus the registered sensitivity exclusion.
    Fewer than MIN_MEMBERS (after any exclusion) -> INELIGIBLE with a reason; the cohort is never filled."""
    cap = caps.set_index(["date", "ticker"])["marketCap"] if len(caps) else pd.Series(dtype=float)
    cohorts, classified = {}, membership[membership.industry.notna()]
    total = membership.groupby("date").size()
    for (date, industry), group in classified.groupby(["date", "industry"], sort=True):
        members = sorted(t for t in group.ticker if t not in exclude)
        values = {t: _cap(cap, date, t) for t in members}
        if leave_largest_out and members:
            finite = {t: v for t, v in values.items() if np.isfinite(v)}
            if finite:
                drop = max(sorted(finite), key=lambda t: (finite[t], t))
                members = [t for t in members if t != drop]
                values = {t: values[t] for t in members}
        record = {"date": date, "industry": industry, "members": members, "n": len(members),
                  "classifiedCoverage": len(group) / total[date], "status": "ELIGIBLE", "reason": None,
                  "capWeights": None, "top1": np.nan, "top2": np.nan, "hhi": np.nan, "missingCapShare": np.nan}
        if len(members) < MIN_MEMBERS:
            record.update(status="INELIGIBLE", reason="BELOW_MINIMUM_CLASSIFIED_MEMBERS")
        else:
            usable = {t: v for t, v in values.items() if np.isfinite(v) and v > 0}
            record["missingCapShare"] = 1 - len(usable) / len(members)
            if len(usable) == len(members):
                total_cap = math.fsum(sorted(usable.values()))
                shares = {t: v / total_cap for t, v in usable.items()}
                ordered = sorted(shares.values(), reverse=True)
                record.update(capWeights=shares, top1=ordered[0], top2=ordered[0] + ordered[1],
                              hhi=math.fsum(s * s for s in ordered))
            # the equal-weight lens does not need caps; the cap lens is marked unavailable by capWeights is None
        cohorts[(date, industry)] = record
    return cohorts


def _cap(series, date, ticker):
    try:
        value = series.loc[(date, ticker)]
    except KeyError:
        return np.nan
    return float(value) if np.isfinite(value) else np.nan


# --------------------------------------------------------------------------- #
# Forward target
# --------------------------------------------------------------------------- #
def weighted_return(returns, weights):
    """Sum of w_i r_i with weights fixed at the signal date. Needs EVERY member to have a finite return and a weight:
    no survivor renormalisation. None otherwise."""
    if weights is None or any(not np.isfinite(returns.get(t, np.nan)) for t in weights):
        return None
    return math.fsum(weights[t] * returns[t] for t in sorted(weights))


def equal_return(returns, members):
    if any(not np.isfinite(returns.get(t, np.nan)) for t in members):
        return None
    return math.fsum(returns[t] for t in sorted(members)) / len(members)


def industry_targets(cohort, forward, horizon):
    """forward: {ticker: (stockReturn, benchmarkReturn, status)} for this date and horizon.
    Returns {lens: {'return','benchmark','relative','status'}} - relative = industry return minus the SAME benchmark window."""
    out = {}
    bench = {b for _, b, s in forward.values() if s == "MATURED" and np.isfinite(b)}
    members = cohort["members"]
    stock = {t: (forward[t][0] if t in forward and forward[t][2] == "MATURED" else np.nan) for t in members}
    benchmark = next(iter(bench)) if len(bench) == 1 else None
    for lens in LENSES:
        if cohort["status"] != "ELIGIBLE":
            out[lens] = {"return": None, "benchmark": None, "relative": None, "status": "INELIGIBLE_INDUSTRY_DATE"}
            continue
        if lens == PRIMARY_LENS and cohort["capWeights"] is None:
            out[lens] = {"return": None, "benchmark": None, "relative": None, "status": "INELIGIBLE_CAP_WEIGHT_UNAVAILABLE"}
            continue
        value = weighted_return(stock, cohort["capWeights"]) if lens == PRIMARY_LENS else equal_return(stock, members)
        if value is None or benchmark is None:
            out[lens] = {"return": None, "benchmark": benchmark, "relative": None, "status": "UNRESOLVED_INCOMPLETE_COHORT_OR_WINDOW"}
        else:
            out[lens] = {"return": value, "benchmark": benchmark, "relative": value - benchmark, "status": "MATURED"}
    return out


# --------------------------------------------------------------------------- #
# Past-only features
# --------------------------------------------------------------------------- #
def trailing_return(close, pos, window):
    """Close[pos] / Close[pos - window] - 1 from information at or before pos. NaN when the history is short or invalid."""
    if pos - window < 0 or pos >= len(close):
        return np.nan
    a, z = close[pos - window], close[pos]
    return float(z / a - 1.0) if np.isfinite([a, z]).all() and min(a, z) > 0 else np.nan


def above_moving_average(close, pos, window):
    """1.0 / 0.0 / NaN: Close[pos] above the mean of the last `window` closes ending AT pos (past-only, inclusive of today)."""
    if pos - window + 1 < 0 or pos >= len(close):
        return np.nan
    chunk = close[pos - window + 1:pos + 1]
    return float(close[pos] > chunk.mean()) if np.isfinite(chunk).all() and (chunk > 0).all() else np.nan


def daily_returns_window(close, pos, window):
    if pos - window < 0 or pos >= len(close):
        return None
    c = close[pos - window:pos + 1]
    return c[1:] / c[:-1] - 1.0 if np.isfinite(c).all() and (c > 0).all() else None


def downside_volatility(portfolio_returns):
    """sqrt(mean(min(r, 0)^2)) * sqrt(252) over the trailing window."""
    r = np.asarray(portfolio_returns, float)
    return float(math.sqrt(np.mean(np.minimum(r, 0.0) ** 2)) * math.sqrt(ANNUALISATION))


def median_with_coverage(values):
    """Median of the finite values, only when at least MIN_FUNDAMENTAL_COUNT and MIN_FUNDAMENTAL_SHARE of members are finite."""
    x = A.clean_numeric(values)
    finite = x[np.isfinite(x)]
    if len(finite) < MIN_FUNDAMENTAL_COUNT or len(finite) < MIN_FUNDAMENTAL_SHARE * len(x):
        return np.nan
    return float(np.median(finite))


def industry_features(cohort, past, panel):
    """past: {ticker: {'trail63','trail126','aboveMA126','bench63','bench126','daily'(array or None)}} past-only;
    panel: {ticker: {column: value}} signal-date values (liquidity, PIT fundamentals). Every missing input stays NaN."""
    features = {name: np.nan for name in FEATURES}
    members = cohort["members"]
    features["CONSTITUENT_COUNT"] = float(len(members))
    features["TOP1_CAP_SHARE"], features["TOP2_CAP_SHARE"] = cohort["top1"], cohort["top2"]
    weights = cohort["capWeights"]
    for window in TRAILING:
        values = {t: past.get(t, {}).get(f"trail{window}", np.nan) for t in members}
        bench = {past.get(t, {}).get(f"bench{window}", np.nan) for t in members}
        if weights is not None and all(np.isfinite(values[t]) for t in members) and len(bench) == 1 and np.isfinite(next(iter(bench))):
            features[f"REL_MOM_{window}"] = math.fsum(weights[t] * values[t] for t in sorted(weights)) - next(iter(bench))
    t126 = np.array([past.get(t, {}).get("trail126", np.nan) for t in members], float)
    ma = np.array([past.get(t, {}).get("aboveMA126", np.nan) for t in members], float)
    b126 = np.array([past.get(t, {}).get("bench126", np.nan) for t in members], float)
    if np.isfinite(t126).all():
        features["BREADTH_POSITIVE_126"] = float(np.mean(t126 > 0))
        features["CONSTITUENT_DISPERSION_126"] = float(np.std(t126, ddof=0))
        if np.isfinite(b126).all():
            features["BREADTH_REL_MOM_POSITIVE_126"] = float(np.mean(t126 - b126 > 0))
    if np.isfinite(ma).all():
        features["BREADTH_ABOVE_MA_126"] = float(np.mean(ma))
    daily = [past.get(t, {}).get("daily") for t in members]
    if weights is not None and all(d is not None and len(d) == RISK_WINDOW for d in daily):
        matrix = np.vstack([weights[t] * np.asarray(past[t]["daily"], float) for t in members])
        features["DOWNSIDE_VOL_126"] = downside_volatility(matrix.sum(axis=0))
    adv = np.array([panel.get(t, {}).get("logAdv60", np.nan) for t in members], float)
    features["MEDIAN_LOG_ADV60"] = median_with_coverage(adv)
    for column in FUNDAMENTAL_COLUMNS:
        features["MEDIAN_" + column] = median_with_coverage([panel.get(t, {}).get(column, np.nan) for t in members])
    return features


# --------------------------------------------------------------------------- #
# Anatomy statistics (per date first, then the mean over dates)
# --------------------------------------------------------------------------- #
def per_date_ic(frame, feature, target):
    """date -> Spearman between the feature and the target across the eligible industries with BOTH finite, only when at
    least MIN_CROSS_SECTION industries remain. Dates below that are invalid, never zero."""
    out = {}
    for date, g in frame.groupby("date", sort=True):
        x, y = A.clean_numeric(g[feature]), A.clean_numeric(g[target])
        ok = np.isfinite(x) & np.isfinite(y)
        if ok.sum() >= MIN_CROSS_SECTION:
            rho = A.spearman(x[ok], y[ok])
            if np.isfinite(rho):
                out[date] = rho
    return out


def tercile_spread_for_date(feature_values, target_values, labels):
    """(top tercile mean target) - (bottom tercile mean target), equal-weighted across industries.

    n industries -> k = floor(n/3) in each outer tercile, the middle absorbs the remainder; n < 9 is refused. Industries are
    ordered by (feature, industry id) so the order is deterministic, and if the feature value at a tercile boundary is tied
    ACROSS the boundary the date is INVALID for this feature (no arbitrary tie resolution)."""
    x, y = A.clean_numeric(feature_values), A.clean_numeric(target_values)
    ok = np.isfinite(x) & np.isfinite(y)
    n = int(ok.sum())
    if n < MIN_TERCILE_CROSS_SECTION:
        return None
    order = sorted((x[i], labels[i], y[i]) for i in np.flatnonzero(ok))
    k = n // 3
    if order[k - 1][0] == order[k][0] or order[n - k - 1][0] == order[n - k][0]:
        return None
    return float(np.mean([o[2] for o in order[n - k:]]) - np.mean([o[2] for o in order[:k]]))


def per_date_tercile(frame, feature, target):
    out = {}
    for date, g in frame.groupby("date", sort=True):
        value = tercile_spread_for_date(g[feature].to_numpy(), g[target].to_numpy(), g["industry"].tolist())
        if value is not None:
            out[date] = value
    return out


def newey_west_mean(series, lag):
    """DESCRIPTIVE Bartlett-weighted standard error of the mean of a date series; the overlap lag is read from the horizon."""
    x = np.asarray(list(series), float)
    n = len(x)
    if n < 3:
        return {"mean": float(np.mean(x)) if n else None, "se": None, "n": n}
    d = x - x.mean()
    lag = min(lag, n - 1)
    var = float(np.dot(d, d) / n)
    for k in range(1, lag + 1):
        var += 2 * (1 - k / (lag + 1)) * float(np.dot(d[k:], d[:-k]) / n)
    return {"mean": float(x.mean()), "se": float(math.sqrt(max(var, 0.0) / n)), "n": n}


def summarize(series, horizon):
    """mean, median, sign fraction, valid dates, year table and a descriptive HAC standard error (lag = ceil(h/5))."""
    values = pd.Series(series, dtype=float).sort_index()
    if values.empty:
        return {"validDates": 0, "mean": None, "median": None, "positiveFraction": None, "byYear": {}, "hacSe": None, "effectiveDates": None}
    nonzero = values[values != 0]
    years = values.groupby(values.index.astype(str).str[:4]).agg(["mean", "count"])
    return {"validDates": int(len(values)), "mean": float(values.mean()), "median": float(values.median()),
            "positiveFraction": float((nonzero > 0).mean()) if len(nonzero) else None,
            "byYear": {y: {"mean": float(r["mean"]), "dates": int(r["count"])} for y, r in years.iterrows()},
            "hacSe": newey_west_mean(values.to_numpy(), math.ceil(horizon / 5))["se"],
            "effectiveDates": float(len(values) / max(1.0, horizon / 5))}


def slice_dates(panel, name, horizon, cutoff):
    """Dates whose OUTCOME WINDOW falls in the slice (entry/exit decide it, not the signal year). Reuses the regime review."""
    entry, exit_ = panel["entry" + str(horizon)], panel["exit" + str(horizon)]
    return R.slice_mask(name, entry, exit_, cutoff)


def stratum_frame(frame):
    top = frame["TOP1_CAP_SHARE"]
    return {"TOP1_CAP_SHARE_LOW": frame[top < STRATUM_TOP1_SHARE_CUTOFF], "TOP1_CAP_SHARE_HIGH": frame[top >= STRATUM_TOP1_SHARE_CUTOFF]}


def per_date_ic_min(frame, feature, target, minimum):
    out = {}
    for date, g in frame.groupby("date", sort=True):
        x, y = A.clean_numeric(g[feature]), A.clean_numeric(g[target])
        ok = np.isfinite(x) & np.isfinite(y)
        if ok.sum() >= minimum:
            rho = A.spearman(x[ok], y[ok])
            if np.isfinite(rho):
                out[date] = rho
    return out


def coverage_row(frame, feature, target):
    eligible = frame[frame.status.eq("ELIGIBLE")] if "status" in frame else frame
    return {"industryDates": int(len(frame)), "eligibleIndustryDates": int(len(eligible)),
            "ineligibleIndustryDates": int(len(frame) - len(eligible)),
            "featureFinite": int(np.isfinite(A.clean_numeric(eligible[feature])).sum()),
            "targetFinite": int(np.isfinite(A.clean_numeric(eligible[target])).sum()),
            "bothFinite": int((np.isfinite(A.clean_numeric(eligible[feature])) & np.isfinite(A.clean_numeric(eligible[target]))).sum())}


def assert_no_forbidden_keys(value, path=""):
    if isinstance(value, dict):
        for key, inner in value.items():
            if any(f in str(key).lower().replace("_", "") for f in FORBIDDEN_OUTPUT_KEY_FRAGMENTS):
                raise ValueError("FORBIDDEN_OUTPUT_KEY: " + path + "/" + str(key))
            assert_no_forbidden_keys(inner, path + "/" + str(key))
    elif isinstance(value, (list, tuple)):
        for inner in value:
            assert_no_forbidden_keys(inner, path)


# --------------------------------------------------------------------------- #
# Industry-date panel and the full descriptive analysis
# --------------------------------------------------------------------------- #
def industry_date_panel(cohorts, features, targets, windows):
    """One row per (date, industry). `features[(date, industry)]` -> dict, `targets[(date, industry, h)]` -> lens dict,
    `windows[(date, h)]` -> (entry, exit). Ineligible cohorts keep a row (status, reason) and NaN everywhere else."""
    rows = []
    for (date, industry), c in sorted(cohorts.items()):
        row = {"date": date, "industry": industry, "status": c["status"], "reason": c["reason"], "n": c["n"],
               "classifiedCoverage": c["classifiedCoverage"], "hhi": c["hhi"], "missingCapShare": c["missingCapShare"]}
        row.update({name: np.nan for name in FEATURES})
        if c["status"] == "ELIGIBLE":
            row.update(features.get((date, industry), {}))
        for h in HORIZONS:
            entry, exit_ = windows.get((date, h), (None, None))
            row["entry" + str(h)], row["exit" + str(h)] = entry, exit_
            for lens in LENSES:
                t = targets.get((date, industry, h), {}).get(lens, {"relative": None, "status": "NOT_COMPUTED"})
                row[f"rel_{lens}_{h}"] = np.nan if t["relative"] is None else t["relative"]
                row[f"status_{lens}_{h}"] = t["status"]
        rows.append(row)
    return pd.DataFrame(rows)


def analyze_panel(panel, spec):
    """Descriptive tables for ONE panel (one sensitivity). Per-date statistics first; no feature or lens is preferred."""
    cutoff = spec["developmentCutoff"]
    result = {"coverage": {}, "ic": {}, "tercile": {}, "slices": {}, "strata": {}}
    for h in HORIZONS:
        for lens in LENSES:
            target = f"rel_{lens}_{h}"
            sub = panel[panel.status.eq("ELIGIBLE")]
            for feature in FEATURES:
                key = f"{feature}|{lens}|H{h}"
                result["coverage"][key] = coverage_row(panel, feature, target)
                result["ic"][key] = summarize(per_date_ic(sub, feature, target), h)
                result["tercile"][key] = summarize(per_date_tercile(sub, feature, target), h)
                for name in SLICES:
                    mask = slice_dates(sub, name, h, cutoff)
                    result["slices"][f"{key}|{name}"] = summarize(per_date_ic(sub[mask.to_numpy()], feature, target), h)
                if feature != "TOP1_CAP_SHARE" and lens == PRIMARY_LENS and h == PRIMARY_HORIZON:
                    for stratum, part in stratum_frame(sub).items():
                        result["strata"][f"{key}|{stratum}"] = summarize(per_date_ic_min(part, feature, target, MIN_STRATUM_CROSS_SECTION), h)
    return result


def lens_comparison(panel, h):
    """Descriptive: per-date Spearman between the cap-weighted and equal-weight relative returns of the same industries."""
    sub = panel[panel.status.eq("ELIGIBLE")]
    return summarize(per_date_ic(sub, f"rel_{PRIMARY_LENS}_{h}", f"rel_EQUAL_WEIGHT_{h}"), h)


def eligibility_summary(panel):
    n_dates = int(panel.date.nunique()) if len(panel) else 0
    return {"industryDates": int(len(panel)), "signalDates": n_dates,
            "eligible": int(panel.status.eq("ELIGIBLE").sum()), "ineligible": int((~panel.status.eq("ELIGIBLE")).sum()),
            "ineligibleReasons": panel[~panel.status.eq("ELIGIBLE")].reason.value_counts().to_dict(),
            "eligibleIndustriesPerDate": {"min": int(panel[panel.status.eq("ELIGIBLE")].groupby("date").size().min()),
                                          "median": float(panel[panel.status.eq("ELIGIBLE")].groupby("date").size().median()),
                                          "max": int(panel[panel.status.eq("ELIGIBLE")].groupby("date").size().max())} if panel.status.eq("ELIGIBLE").any() else None,
            "meanClassifiedCoverage": float(panel.classifiedCoverage.mean()) if len(panel) else None}
