"""KR stock-within-industry anatomy v1 — pure descriptive instruments.

EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY. Every Korean date through the development cutoff is already
outcome-exposed and the industry membership is a reconstruction (`DATA_FOUNDATION_INSUFFICIENT_V4`), so nothing here validates,
selects or promotes anything and nothing here can alter a sealed study.

The decomposition this study reads is an identity on RETURNS:

    stock - market  =  (industry - market)  +  (stock - industry)

and it studies ONLY the second term, with the industry benchmark taken LEAVE-ONE-OUT: the evaluated stock is excluded from the
industry cohort and from the industry weights. (Rank correlations are not additive, so no statistic here pretends the identity
carries over to them.)

No I/O, no network, no model fit, no portfolio. Functions receive frames and return tables. Anatomy helpers
(`kr_factor_anatomy`, `kr_industry_anatomy`, `kr_top120_regime_review`) are REUSED, never copied, where the arithmetic is identical.

Rules that run through every function and are tested on synthetic data:

* THE EVALUATED STOCK NEVER ENTERS ITS OWN BENCHMARK. Peers are the classified members of the stock's industry at the signal date
  minus the stock; their weights are the signal-date market caps of the PEERS only, and the stock's own cap is not used.
* THE COHORT IS FROZEN AT THE SIGNAL DATE. Membership and weights are read once at t and never revisited.
* AN INELIGIBLE STOCK-DATE IS INELIGIBLE, NOT ZERO. Fewer than four other classified peers, an unavailable peer cap weight (cap lens),
  or any peer without a matured return under the accepted terminal discipline yields a status, never a number: no UNKNOWN fill, no
  survivor or successor substitution, no renormalisation over survivors.
* RANKS ARE SIGNAL-TIME AND WITHIN THE SAME DATE AND INDUSTRY. A within-industry percentile uses only the same-date classified
  members of the stock's own industry, before any outcome is attached; ties share the average percentile.
* MISSING IS MISSING. A feature without enough finite peers has no within-industry rank; it is never zero or neutral.
* NOTHING IS TUNED. Every threshold is a module constant frozen in the spec before any outcome exists.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import kr_factor_anatomy as A
from . import kr_industry_anatomy as I
from . import kr_value_quality_catalyst as F

STUDY = "kr-stock-within-industry-anatomy-v1"
SCIENTIFIC_STATUS = "EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY"
RETURN_BASIS = A.RETURN_BASIS
BENCHMARK = I.BENCHMARK
HORIZONS = (63, 126, 252)
PRIMARY_HORIZON = 126
WEIGHT_LENSES = ("CAP_WEIGHTED", "EQUAL_WEIGHT")
PRIMARY_WEIGHT_LENS = "CAP_WEIGHTED"
COMPONENTS = ("STOCK_MINUS_LOO_INDUSTRY", "LOO_INDUSTRY_MINUS_MARKET", "STOCK_MINUS_MARKET")
PRIMARY_COMPONENT = "STOCK_MINUS_LOO_INDUSTRY"
FEATURES = tuple(F.RAW_FEATURES)
FEATURE_LENSES = ("RAW", "WITHIN_INDUSTRY_RANK")
PRIMARY_FEATURE_LENS = "WITHIN_INDUSTRY_RANK"
SENSITIVITIES = ("FULL", "EXCLUDE_SAMSUNG_ELECTRONICS_AND_SK_HYNIX")
EXCLUDED_MEGA_CAPS = tuple(I.EXCLUDED_MEGA_CAPS)
SLICES = ("FULL_SAMPLE", "PRE_2025_COMPLETE_WINDOW", "TOUCHES_2025_OR_LATER")
BENCHMARK_STATES = (1.0, 0.7, 0.4)
ELIGIBLE_MEMBERSHIP_STATUSES = tuple(I.ELIGIBLE_MEMBERSHIP_STATUSES)

MIN_INDUSTRY_MEMBERS = 5      # classified members at the signal date, the evaluated stock included
MIN_PEERS = 4                 # OTHER classified members after excluding the evaluated stock
MIN_RANK_PEERS = 5            # finite feature values inside a date x industry needed for a within-industry percentile
MIN_DATE_CROSS_SECTION = 30   # stocks with finite feature and target needed for a per-date pooled Spearman
MIN_STRATUM_CROSS_SECTION = 15
MIN_GROUP_SIZE = 2            # stocks in each of the top and bottom feature groups of an industry-date
MIN_GROUP_INDUSTRY_N = 3 * MIN_GROUP_SIZE
MIN_INDUSTRIES_PER_DATE = 3   # industries contributing to a date-level equal-industry aggregate
MIN_SLICE_DATES = 26          # valid dates a slice needs before its sign is read as one of the registered views
MIN_VALID_DATES_FOR_LABEL = 52
NEAR_ZERO_IC = 0.01           # |mean rank correlation| below this is not read as a direction
SURVIVES_RATIO = 0.75
WEAKENS_RATIO = 0.25
ANNUAL_MIN_DATES = 13

# (sensitivity, weight lens, horizon, slice): the registered views over which the sign of a feature's pooled association is read.
SIGN_VIEWS = (
    ("FULL", "CAP_WEIGHTED", 126, "FULL_SAMPLE"), ("FULL", "EQUAL_WEIGHT", 126, "FULL_SAMPLE"),
    ("EXCLUDE_SAMSUNG_ELECTRONICS_AND_SK_HYNIX", "CAP_WEIGHTED", 126, "FULL_SAMPLE"),
    ("EXCLUDE_SAMSUNG_ELECTRONICS_AND_SK_HYNIX", "EQUAL_WEIGHT", 126, "FULL_SAMPLE"),
    ("FULL", "CAP_WEIGHTED", 63, "FULL_SAMPLE"), ("FULL", "CAP_WEIGHTED", 252, "FULL_SAMPLE"),
    ("FULL", "CAP_WEIGHTED", 126, "PRE_2025_COMPLETE_WINDOW"), ("FULL", "CAP_WEIGHTED", 126, "TOUCHES_2025_OR_LATER"),
)
MIN_SIGN_VIEWS = 4

QUESTIONS = {
    "Q1_BOOK_TO_MARKET_RETAINS_ASSOCIATION": ("bookToMarketProxy",),
    "Q2_MOMENTUM_AFTER_INDUSTRY_MOMENTUM_REMOVED": ("relative126", "momentum121"),
    "Q3_QUALITY_CASHFLOW_IMPROVEMENT_STOCK_SPECIFIC_OR_INDUSTRY": ("netIncomeToAssets", "ocfToAssets", "negativeAccrualsToAssets",
                                                                   "ocfImprovementToAssets", "ocfYieldProxy", "earningsYieldProxy"),
    "Q4_LIQUIDITY_AFTER_INDUSTRY_CONTROL": ("logAdv60",),
    "Q5_DOWNSIDE_VOLATILITY_REGIME_AFTER_INDUSTRY_NEUTRALISATION": ("negativeDownsideVol126",),
}
FORBIDDEN_OUTPUT_KEY_FRAGMENTS = I.FORBIDDEN_OUTPUT_KEY_FRAGMENTS


# --------------------------------------------------------------------------- #
# Frozen cohorts and the leave-one-out peer set
# --------------------------------------------------------------------------- #
def build_cohorts(membership, exclude=()):
    """dict[(date, industry)] -> {members, n, status, reason}. `membership` has date, ticker, industry, membershipStatus.

    Members are the CLASSIFIED PIT Top120 names of that industry on that date minus the registered sensitivity exclusion (removed
    BEFORE counting and before any ranking). Fewer than MIN_INDUSTRY_MEMBERS -> INELIGIBLE with a reason; never filled."""
    cohorts = {}
    classified = membership[membership.industry.notna()]
    for (date, industry), group in classified.groupby(["date", "industry"], sort=True):
        members = sorted(t for t in group.ticker if t not in exclude)
        eligible = len(members) >= MIN_INDUSTRY_MEMBERS
        cohorts[(date, industry)] = {"date": date, "industry": industry, "members": members, "n": len(members),
                                     "status": "ELIGIBLE" if eligible else "INELIGIBLE",
                                     "reason": None if eligible else "BELOW_MINIMUM_CLASSIFIED_MEMBERS"}
    return cohorts


def peers_of(cohort, ticker):
    """Sorted peers of `ticker` (the cohort minus the stock itself) or None when the stock is not a member of an eligible cohort or
    fewer than MIN_PEERS others remain. The evaluated stock is NEVER in the returned list."""
    if cohort is None or cohort["status"] != "ELIGIBLE" or ticker not in cohort["members"]:
        return None
    peers = [t for t in cohort["members"] if t != ticker]
    return peers if len(peers) >= MIN_PEERS else None


def peer_cap_weights(peers, caps):
    """Signal-date market caps of the PEERS only, normalised over the peers. None when any peer's cap is missing, non-finite or
    non-positive: the cap lens then has no benchmark for this stock (never a partial or renormalised one)."""
    values = {}
    for t in peers:
        v = caps.get(t, np.nan)
        if v is None or not np.isfinite(v) or v <= 0:
            return None
        values[t] = float(v)
    total = math.fsum(values[t] for t in sorted(values))
    return {t: values[t] / total for t in sorted(values)}


def peer_returns(peers, weights, stock_returns):
    """(cap-weighted, equal-weighted) peer return with weights fixed at the signal date. Each is None unless EVERY peer has a finite
    matured return (and, for the cap lens, a weight): no survivor renormalisation."""
    values = {t: stock_returns.get(t, np.nan) for t in peers}
    if any(v is None or not np.isfinite(v) for v in values.values()):
        return None, None
    equal = math.fsum(values[t] for t in sorted(values)) / len(values)
    cap = None if weights is None else math.fsum(weights[t] * values[t] for t in sorted(weights))
    return cap, equal


def stock_targets(ticker, cohort, forward, caps):
    """forward: {ticker: (stockReturn, benchmarkReturn, status)} for this date and horizon; caps: {ticker: signal-date cap}.

    Returns {lens: {'status', 'stock', 'bench', 'loo', 'components': {name: value or None}}}. The three components are defined on
    EXACTLY the same name-dates (the same lens status), so they can be compared without a sample change:
    stock - loo, loo - market and stock - market, which satisfy stock - market = (loo - market) + (stock - loo)."""
    empty = {"stock": None, "bench": None, "loo": None, "components": {c: None for c in COMPONENTS}}
    peers = peers_of(cohort, ticker)
    if peers is None:
        reason = "INELIGIBLE_INDUSTRY_DATE" if cohort is None or cohort["status"] != "ELIGIBLE" or ticker not in cohort["members"] \
            else "INELIGIBLE_FEWER_THAN_FOUR_PEERS"
        return {lens: dict(empty, status=reason) for lens in WEIGHT_LENSES}
    own = forward.get(ticker)
    peer_status = [forward.get(t, (np.nan, np.nan, "MISSING"))[2] for t in peers]
    if own is None or own[2] != "MATURED":
        status = "PENDING" if own is not None and own[2] == "PENDING" else "UNRESOLVED_OWN_RETURN"
        return {lens: dict(empty, status=status) for lens in WEIGHT_LENSES}
    if any(s != "MATURED" for s in peer_status):
        status = "PENDING" if any(s == "PENDING" for s in peer_status) else "UNRESOLVED_PEER_RETURN"
        return {lens: dict(empty, status=status) for lens in WEIGHT_LENSES}
    stock, bench = own[0], own[1]
    if not np.isfinite(stock) or not np.isfinite(bench):
        return {lens: dict(empty, status="UNRESOLVED_BENCHMARK_OR_OWN_RETURN") for lens in WEIGHT_LENSES}
    weights = peer_cap_weights(peers, caps)
    cap_ret, eq_ret = peer_returns(peers, weights, {t: forward[t][0] for t in peers})
    out = {}
    for lens, loo in (("CAP_WEIGHTED", cap_ret), ("EQUAL_WEIGHT", eq_ret)):
        if loo is None:
            status = "INELIGIBLE_CAP_WEIGHT_UNAVAILABLE" if lens == "CAP_WEIGHTED" and weights is None else "UNRESOLVED_PEER_RETURN"
            out[lens] = dict(empty, status=status)
            continue
        out[lens] = {"status": "MATURED", "stock": stock, "bench": bench, "loo": loo,
                     "components": {"STOCK_MINUS_LOO_INDUSTRY": stock - loo, "LOO_INDUSTRY_MINUS_MARKET": loo - bench,
                                    "STOCK_MINUS_MARKET": stock - bench}}
    return out


# --------------------------------------------------------------------------- #
# Signal-time within-industry ranks
# --------------------------------------------------------------------------- #
def within_industry_percentiles(frame, columns=FEATURES + ("marketCap",)):
    """Add `wi_<col>` (average-rank percentile in (0, 1) among the finite values of the SAME date and industry) and `wi_n_<col>`.

    `frame` must contain only the eligible members of eligible industry-dates (date, industry, ticker, <columns>). A group with fewer
    than MIN_RANK_PEERS finite values gets NaN: a thin peer set is not ranked. Nothing outside the group, and nothing after the date,
    enters a percentile; the result does not depend on row order."""
    out = frame.copy().reset_index(drop=True)
    groups = out.groupby(["date", "industry"], sort=False).indices
    for col in columns:
        values = A.clean_numeric(out[col]) if col in out else np.full(len(out), np.nan)
        pct, count = np.full(len(out), np.nan), np.zeros(len(out), dtype=int)
        for index in groups.values():
            part = values[index]
            finite = int(np.isfinite(part).sum())
            count[index] = finite
            if finite >= MIN_RANK_PEERS:
                pct[index] = A.pct_rank(part)
        out["wi_" + col] = pct
        out["wi_n_" + col] = count
    return out


# --------------------------------------------------------------------------- #
# The stock panel
# --------------------------------------------------------------------------- #
def target_column(component, lens, horizon):
    return f"t_{component}_{lens}_{horizon}"


def feature_column(feature, feature_lens):
    return feature if feature_lens == "RAW" else "wi_" + feature


def build_stock_panel(membership, features, forward, windows, *, exclude=(), risk=None):
    """One row per PIT Top120 stock-date, ALL of them (UNKNOWN, unclassified, ineligible and excluded names keep their row and a status).

    membership: date, ticker, industry, membershipStatus. features: date, ticker, marketCap and the FEATURES columns.
    forward: {(date, h): {ticker: (stockReturn, benchmarkReturn, status)}}. windows: {(date, h): (entry, exit)}. risk: {date: multiplier}."""
    cohorts = build_cohorts(membership, exclude)
    value_columns = [c for c in FEATURES + ("marketCap",) if c in features.columns]
    panel = membership.sort_values(["date", "ticker"]).reset_index(drop=True).merge(
        features.drop_duplicates(["date", "ticker"])[["date", "ticker"] + value_columns], on=["date", "ticker"], how="left")
    for col in FEATURES + ("marketCap",):
        if col not in panel:
            panel[col] = np.nan
        panel[col] = A.clean_numeric(panel[col])
    caps_by_date = {}
    for date, ticker, cap in zip(panel.date, panel.ticker, panel.marketCap):
        caps_by_date.setdefault(date, {})[ticker] = cap
    status, reason, size = [], [], []
    for date, ticker, industry, membership_status in zip(panel.date, panel.ticker, panel.industry, panel.membershipStatus):
        cohort = cohorts.get((date, industry)) if isinstance(industry, str) else None
        if ticker in exclude:
            status.append("EXCLUDED_BY_SENSITIVITY"), reason.append("REGISTERED_MEGA_CAP_EXCLUSION")
        elif cohort is None:
            status.append("INELIGIBLE_UNCLASSIFIED"), reason.append(str(membership_status))
        elif cohort["status"] == "ELIGIBLE":
            status.append("ELIGIBLE"), reason.append(None)
        else:
            status.append("INELIGIBLE_BELOW_MINIMUM_INDUSTRY_MEMBERS"), reason.append(cohort["reason"])
        size.append(cohort["n"] if cohort is not None and ticker not in exclude else np.nan)
    panel["status"], panel["reason"], panel["nIndustryMembers"] = status, reason, size
    panel["riskMultiplier"] = [float((risk or {}).get(d, np.nan)) for d in panel.date]
    eligible = panel.status.eq("ELIGIBLE")
    ranked = within_industry_percentiles(panel[eligible])
    for col in FEATURES + ("marketCap",):
        panel["wi_" + col], panel["wi_n_" + col] = np.nan, 0
        panel.loc[eligible, "wi_" + col] = ranked["wi_" + col].to_numpy()
        panel.loc[eligible, "wi_n_" + col] = ranked["wi_n_" + col].to_numpy()
    new = {}
    for h in HORIZONS:
        new[f"entry{h}"] = [windows.get((d, h), (None, None))[0] for d in panel.date]
        new[f"exit{h}"] = [windows.get((d, h), (None, None))[1] for d in panel.date]
        for lens in WEIGHT_LENSES:
            new[f"status_{lens}_{h}"] = ["INELIGIBLE_STOCK_DATE"] * len(panel)
            new[f"loo_{lens}_{h}"] = [np.nan] * len(panel)
            for c in COMPONENTS:
                new[target_column(c, lens, h)] = [np.nan] * len(panel)
        new[f"stock{h}"], new[f"bench{h}"] = [np.nan] * len(panel), [np.nan] * len(panel)
    for i in np.flatnonzero(eligible.to_numpy()):
        date, ticker, industry = panel.at[i, "date"], panel.at[i, "ticker"], panel.at[i, "industry"]
        for h in HORIZONS:
            targets = stock_targets(ticker, cohorts[(date, industry)], forward.get((date, h), {}), caps_by_date.get(date, {}))
            for lens, t in targets.items():
                new[f"status_{lens}_{h}"][i] = t["status"]
                if t["status"] == "MATURED":
                    new[f"stock{h}"][i], new[f"bench{h}"][i], new[f"loo_{lens}_{h}"][i] = t["stock"], t["bench"], t["loo"]
                    for c, v in t["components"].items():
                        new[target_column(c, lens, h)][i] = v
    return pd.concat([panel, pd.DataFrame(new)], axis=1)


# --------------------------------------------------------------------------- #
# Anatomy statistics (per date first, then the mean over dates)
# --------------------------------------------------------------------------- #
def sample_mask(panel, feature, lens, horizon):
    """THE COMMON SAMPLE of one feature, lens and horizon: eligible stock-dates with a matured target AND a finite raw value AND a finite
    within-industry percentile. Both feature lenses and all three components are computed on exactly these rows, so a difference
    between lenses is never a difference of sample."""
    raw, within = A.clean_numeric(panel[feature]), A.clean_numeric(panel["wi_" + feature])
    return (panel.status.eq("ELIGIBLE") & panel[f"status_{lens}_{horizon}"].eq("MATURED")
            & pd.Series(np.isfinite(raw) & np.isfinite(within), index=panel.index))


def pooled_ic_series(panel, feature, feature_lens, component, lens, horizon, extra_mask=None, minimum=MIN_DATE_CROSS_SECTION):
    """date -> Spearman(feature view, target) across the common-sample stocks of that date (>= `minimum` of them)."""
    mask = sample_mask(panel, feature, lens, horizon)
    if extra_mask is not None:
        mask = mask & pd.Series(np.asarray(extra_mask, bool), index=panel.index)
    sub = panel.loc[mask, ["date", feature_column(feature, feature_lens), target_column(component, lens, horizon)]]
    return I.per_date_ic_min(sub, sub.columns[1], sub.columns[2], minimum)


def industry_date_group_spread(x, y, tickers):
    """(mean target of the top k feature stocks) - (mean target of the bottom k) inside ONE industry-date, k = floor(n/3).

    n < MIN_GROUP_INDUSTRY_N (so that each outer group holds at least MIN_GROUP_SIZE stocks) is refused. Stocks are ordered by
    (feature, ticker) so the order is deterministic, and a feature value tied ACROSS a group boundary invalidates the industry-date
    (no arbitrary tie resolution); ties inside a group are harmless. Stocks are equal-weighted inside a group."""
    fx, fy = A.clean_numeric(x), A.clean_numeric(y)
    ok = np.isfinite(fx) & np.isfinite(fy)
    n = int(ok.sum())
    if n < MIN_GROUP_INDUSTRY_N:
        return None
    order = sorted((fx[i], tickers[i], fy[i]) for i in np.flatnonzero(ok))
    k = n // 3
    if k < MIN_GROUP_SIZE or order[k - 1][0] == order[k][0] or order[n - k - 1][0] == order[n - k][0]:
        return None
    return float(math.fsum(o[2] for o in order[n - k:]) / k - math.fsum(o[2] for o in order[:k]) / k)


def per_date_group_spread(sub, feature_col, target_col):
    """date -> equal-INDUSTRY mean of the industry-date spreads, only when at least MIN_INDUSTRIES_PER_DATE industries are valid. A
    large industry therefore never outweighs a small one inside a date, and dates are then equal-weighted by `summarize`."""
    out, used = {}, {}
    for date, g in sub.groupby("date", sort=True):
        spreads = []
        for _, h in g.groupby("industry", sort=True):
            value = industry_date_group_spread(h[feature_col].to_numpy(), h[target_col].to_numpy(), h.ticker.tolist())
            if value is not None:
                spreads.append(value)
        if len(spreads) >= MIN_INDUSTRIES_PER_DATE:
            out[date], used[date] = float(math.fsum(spreads) / len(spreads)), len(spreads)
    return out, used


def per_date_equal_industry_ic(sub, feature_col, target_col):
    """date -> equal-INDUSTRY mean of the within-industry Spearman (n >= MIN_GROUP_INDUSTRY_N per industry-date, >= MIN_INDUSTRIES_PER_DATE
    industries). A Spearman inside one industry is invariant to any within-industry monotone transform, so RAW and WITHIN_INDUSTRY_RANK
    give the identical value here by construction and this statistic is reported once."""
    out, used = {}, {}
    for date, g in sub.groupby("date", sort=True):
        rhos = []
        for _, h in g.groupby("industry", sort=True):
            x, y = A.clean_numeric(h[feature_col]), A.clean_numeric(h[target_col])
            ok = np.isfinite(x) & np.isfinite(y)
            if ok.sum() >= MIN_GROUP_INDUSTRY_N:
                rho = A.spearman(x[ok], y[ok])
                if np.isfinite(rho):
                    rhos.append(rho)
        if len(rhos) >= MIN_INDUSTRIES_PER_DATE:
            out[date], used[date] = float(math.fsum(rhos) / len(rhos)), len(rhos)
    return out, used


def summarize(series, horizon):
    """I.summarize plus the year table restricted to years with at least ANNUAL_MIN_DATES valid dates read as `positiveYearFraction`."""
    out = I.summarize(series, horizon)
    eligible_years = {y: v for y, v in out["byYear"].items() if v["dates"] >= ANNUAL_MIN_DATES}
    out["eligibleYears"] = len(eligible_years)
    out["positiveYearFraction"] = (float(np.mean([v["mean"] > 0 for v in eligible_years.values()])) if eligible_years else None)
    return out


def coverage_row(panel, feature, lens, horizon):
    eligible = panel.status.eq("ELIGIBLE")
    matured = eligible & panel[f"status_{lens}_{horizon}"].eq("MATURED")
    raw, within = A.clean_numeric(panel[feature]), A.clean_numeric(panel["wi_" + feature])
    return {"stockDates": int(len(panel)), "eligibleStockDates": int(eligible.sum()),
            "ineligibleStockDates": int(len(panel) - eligible.sum()),
            "maturedTargets": int(matured.sum()),
            "rawFiniteAmongEligible": int((eligible & np.isfinite(raw)).sum()),
            "withinRankFiniteAmongEligible": int((eligible & np.isfinite(within)).sum()),
            "commonSample": int(sample_mask(panel, feature, lens, horizon).sum())}


def analyze_panel(panel, spec):
    """Descriptive tables for ONE sensitivity panel. Per-date statistics first; no feature, lens or view is preferred."""
    cutoff = spec["developmentCutoff"]
    result = {"coverage": {}, "pooledIc": {}, "slices": {}, "benchmarkStates": {}, "equalIndustryIc": {}, "groupSpread": {},
              "sizeControl": {}}
    for h in HORIZONS:
        for lens in WEIGHT_LENSES:
            for feature in FEATURES:
                result["coverage"][f"{feature}|{lens}|H{h}"] = coverage_row(panel, feature, lens, h)
                mask = sample_mask(panel, feature, lens, h)
                sub = panel[mask]
                for feature_lens in FEATURE_LENSES:
                    for component in COMPONENTS:
                        key = f"{feature}|{feature_lens}|{component}|{lens}|H{h}"
                        result["pooledIc"][key] = summarize(pooled_ic_series(panel, feature, feature_lens, component, lens, h), h)
                    for name in SLICES:
                        slice_mask = I.slice_dates(panel, name, h, cutoff).to_numpy()
                        key = f"{feature}|{feature_lens}|{PRIMARY_COMPONENT}|{lens}|H{h}|{name}"
                        result["slices"][key] = summarize(pooled_ic_series(panel, feature, feature_lens, PRIMARY_COMPONENT, lens, h, slice_mask), h)
                    for state in BENCHMARK_STATES:
                        state_mask = panel.riskMultiplier.astype(float).eq(state).to_numpy()
                        key = f"{feature}|{feature_lens}|{PRIMARY_COMPONENT}|{lens}|H{h}|BENCHMARK_STATE_{state}"
                        result["benchmarkStates"][key] = summarize(pooled_ic_series(panel, feature, feature_lens, PRIMARY_COMPONENT, lens, h, state_mask), h)
                target = target_column(PRIMARY_COMPONENT, lens, h)
                key = f"{feature}|{PRIMARY_COMPONENT}|{lens}|H{h}"
                series, used = per_date_equal_industry_ic(sub, feature, target)
                result["equalIndustryIc"][key] = dict(summarize(series, h), meanIndustriesPerDate=float(np.mean(list(used.values()))) if used else None)
                series, used = per_date_group_spread(sub, feature, target)
                result["groupSpread"][key] = dict(summarize(series, h), meanIndustriesPerDate=float(np.mean(list(used.values()))) if used else None)
        result["sizeControl"][f"logAdv60|H{h}"] = size_control(panel, h)
    return result


def size_control(panel, horizon):
    """Does logAdv60 keep its within-industry association once within-industry SIZE is held roughly fixed? Descriptive only.

    `wi_marketCap` is a CONTEXT variable (the within-industry percentile of the signal-date market cap), not one of the eleven registered
    features. Reported per weight lens: the mean per-date Spearman between the two within-industry ranks (how much of logAdv60 is size),
    and the pooled within-industry logAdv60 association inside the LOWER and UPPER half of within-industry size."""
    out = {}
    for lens in WEIGHT_LENSES:
        mask = sample_mask(panel, "logAdv60", lens, horizon) & panel.wi_marketCap.notna()
        sub = panel[mask]
        overlap = I.per_date_ic_min(sub, "wi_logAdv60", "wi_marketCap", MIN_DATE_CROSS_SECTION)
        halves = {}
        for name, cond in (("LOWER_HALF_BY_WITHIN_INDUSTRY_SIZE", sub.wi_marketCap < 0.5), ("UPPER_HALF_BY_WITHIN_INDUSTRY_SIZE", sub.wi_marketCap >= 0.5)):
            halves[name] = summarize(I.per_date_ic_min(sub[cond], "wi_logAdv60", target_column(PRIMARY_COMPONENT, lens, horizon), MIN_STRATUM_CROSS_SECTION), horizon)
        out[lens] = {"rankOverlapWithWithinIndustrySize": summarize(overlap, horizon), "byWithinIndustrySizeHalf": halves}
    return out


# --------------------------------------------------------------------------- #
# Cross-sensitivity reading: sign views, prior comparison, the five questions
# --------------------------------------------------------------------------- #
def sign_stability(by_view):
    """Descriptive label from the sign of each registered view's pooled mean rank correlation. No magnitude threshold, no choice of view."""
    finite = {k: v for k, v in by_view.items() if v is not None and np.isfinite(v)}
    if len(finite) < MIN_SIGN_VIEWS:
        return {"label": "DATA_INSUFFICIENT", "viewsRead": len(finite), "viewsRegistered": len(by_view)}
    signs = {int(np.sign(v)) for v in finite.values()}
    label = ("POSITIVE_IN_ALL_REGISTERED_VIEWS" if signs == {1} else "NEGATIVE_IN_ALL_REGISTERED_VIEWS" if signs == {-1}
             else "SIGN_DEPENDS_ON_VIEW")
    return {"label": label, "viewsRead": len(finite), "viewsRegistered": len(by_view),
            "positiveViews": int(sum(v > 0 for v in finite.values())), "negativeViews": int(sum(v < 0 for v in finite.values()))}


def view_key(feature, view, feature_lens=PRIMARY_FEATURE_LENS):
    sensitivity, lens, h, slice_name = view
    base = f"{feature}|{feature_lens}|{PRIMARY_COMPONENT}|{lens}|H{h}"
    return ("pooledIc", base) if slice_name == "FULL_SAMPLE" else ("slices", base + "|" + slice_name)


def sign_views_for(analysis, feature, feature_lens=PRIMARY_FEATURE_LENS):
    """analysis: {sensitivity: analyze_panel result}. Slice views with fewer than MIN_SLICE_DATES valid dates are not read."""
    views = {}
    for view in SIGN_VIEWS:
        table, key = view_key(feature, view, feature_lens)
        s = analysis[view[0]][table].get(key)
        minimum = MIN_SLICE_DATES if view[3] != "FULL_SAMPLE" else 1
        views["|".join(str(x) for x in view)] = s["mean"] if s and s["validDates"] >= minimum else None
    return sign_stability(views), views


def compare_to_prior(new_mean, reference_mean, new_dates):
    """INTERPRETIVE only. Fixed conventions (NEAR_ZERO_IC, SURVIVES_RATIO, WEAKENS_RATIO), frozen before any outcome, never tests."""
    if new_mean is None or reference_mean is None or new_dates < MIN_VALID_DATES_FOR_LABEL:
        return {"shiftClass": "DATA_INSUFFICIENT", "ratio": None}
    if abs(reference_mean) < NEAR_ZERO_IC:
        return {"shiftClass": "REFERENCE_NEAR_ZERO", "ratio": None}
    if abs(new_mean) < NEAR_ZERO_IC:
        return {"shiftClass": "ABSORBED_TO_NEAR_ZERO", "ratio": float(new_mean / reference_mean)}
    if np.sign(new_mean) != np.sign(reference_mean):
        return {"shiftClass": "CHANGES_SIGN", "ratio": float(new_mean / reference_mean)}
    ratio = float(new_mean / reference_mean)
    cls = "SURVIVES" if ratio >= SURVIVES_RATIO else "WEAKENS_MATERIALLY" if ratio >= WEAKENS_RATIO else "LARGELY_ABSORBED"
    return {"shiftClass": cls, "ratio": ratio}


def prior_reference(prior_result, feature, horizon):
    """Mean per-date rank correlation of the SEALED stock-minus-market anatomy (read, never recomputed). None when it has no such cell."""
    cell = (prior_result["universes"]["PIT_TOP120_LARGE_CAP_ANALYSIS_UNIVERSE"]["standalone"]["V1_TERMINAL_DISCIPLINE"]
            .get(feature, {}).get(str(horizon)))
    return None if cell is None else cell.get("meanRankCorrelation")


def prior_comparison(analysis, prior_result):
    """Per feature and horizon (126, 252): the sealed Stock-Market reading (A, different sample), this study's same-sample Stock-Market
    reading (A'), RAW and WITHIN-INDUSTRY readings of Stock - LOO industry (primary cap lens), and the interpretive shift class against A
    and against A'. A' exists only to separate a SAMPLE difference from an INDUSTRY effect; neither reference is preferred."""
    rows, pooled = {}, analysis["FULL"]["pooledIc"]
    for feature in FEATURES:
        for h in (126, 252):
            def b(feature_lens, component, feature=feature, h=h):
                return pooled[f"{feature}|{feature_lens}|{component}|{PRIMARY_WEIGHT_LENS}|H{h}"]
            within, raw = b(PRIMARY_FEATURE_LENS, PRIMARY_COMPONENT), b("RAW", PRIMARY_COMPONENT)
            same = b("RAW", "STOCK_MINUS_MARKET")
            sealed = prior_reference(prior_result, feature, h)
            stability = sign_views_for(analysis, feature)[0]["label"] if h == PRIMARY_HORIZON else None
            rows[f"{feature}|H{h}"] = {
                "sealedStockMinusMarket": sealed, "sameSampleStockMinusMarketRaw": same["mean"],
                "rawStockMinusLooIndustry": raw["mean"], "withinIndustryStockMinusLooIndustry": within["mean"],
                "looIndustryMinusMarketRaw": b("RAW", "LOO_INDUSTRY_MINUS_MARKET")["mean"],
                "validDatesWithin": within["validDates"],
                "shiftVersusSealed": compare_to_prior(within["mean"], sealed, within["validDates"]),
                "shiftVersusSameSample": compare_to_prior(within["mean"], same["mean"], within["validDates"]),
                "signStability": stability}
    return rows


def question_readout(analysis, comparison):
    """The five registered questions, each as the registered numbers for its registered features. A readout is a table, not an answer key."""
    full = analysis["FULL"]
    out = {}
    for question, features in QUESTIONS.items():
        entry = {}
        for feature in features:
            h = PRIMARY_HORIZON
            key = f"{feature}|{PRIMARY_FEATURE_LENS}|{PRIMARY_COMPONENT}|{PRIMARY_WEIGHT_LENS}|H{h}"
            stability, views = sign_views_for(analysis, feature)
            entry[feature] = {"primary": full["pooledIc"][key], "signViews": views, "signStability": stability,
                              "priorComparison": comparison.get(f"{feature}|H{h}")}
        if question.startswith("Q4"):
            entry["sizeControl"] = {name: analysis[name]["sizeControl"][f"logAdv60|H{PRIMARY_HORIZON}"] for name in analysis}
        if question.startswith("Q5"):
            f = features[0]
            entry["byBenchmarkState"] = {name: {s: analysis[name]["benchmarkStates"][f"{f}|{PRIMARY_FEATURE_LENS}|{PRIMARY_COMPONENT}|{PRIMARY_WEIGHT_LENS}|H{PRIMARY_HORIZON}|BENCHMARK_STATE_{s}"]
                                                for s in BENCHMARK_STATES} for name in analysis}
        out[question] = entry
    return out


def eligibility_summary(panel):
    """Stock-date denominators. UNKNOWN, unclassified and ineligible names stay counted."""
    n = int(len(panel))
    by_status = panel.status.value_counts().to_dict()
    out = {"stockDates": n, "signalDates": int(panel.date.nunique()) if n else 0, "byStatus": {k: int(v) for k, v in by_status.items()},
           "ineligibleReasons": {k: int(v) for k, v in panel[~panel.status.eq("ELIGIBLE")].reason.value_counts().items()},
           "unknownRetainedInDenominator": int(panel.membershipStatus.eq("UNKNOWN").sum()),
           "targetStatus": {}}
    for h in HORIZONS:
        for lens in WEIGHT_LENSES:
            counts = panel[f"status_{lens}_{h}"].value_counts().to_dict()
            out["targetStatus"][f"{lens}|H{h}"] = {k: int(v) for k, v in counts.items()}
    elig = panel[panel.status.eq("ELIGIBLE")]
    per_date = elig.groupby("date").size() if len(elig) else pd.Series(dtype=int)
    out["eligibleStocksPerDate"] = ({"min": int(per_date.min()), "median": float(per_date.median()), "max": int(per_date.max())} if len(per_date) else None)
    return out


def membership_eligibility(membership, exclude=()):
    """LABEL-FREE stock-date eligibility from membership alone (no price, cap or return): the denominators a readiness audit can publish
    before execution. Cap availability and terminal completeness of the peers are outcome-time facts and are NOT assumed here."""
    cohorts = build_cohorts(membership, exclude)
    status = []
    for rec in membership.itertuples(index=False):
        if rec.ticker in exclude:
            status.append("EXCLUDED_BY_SENSITIVITY")
        elif not isinstance(rec.industry, str):
            status.append("INELIGIBLE_UNCLASSIFIED")
        elif cohorts[(rec.date, rec.industry)]["status"] == "ELIGIBLE":
            status.append("ELIGIBLE")
        else:
            status.append("INELIGIBLE_BELOW_MINIMUM_INDUSTRY_MEMBERS")
    frame = membership.assign(status=status)
    elig = frame[frame.status.eq("ELIGIBLE")]
    per_date = elig.groupby("date").size()
    years = frame.assign(year=frame.date.astype(str).str[:4]).groupby("year").status.apply(lambda s: float((s == "ELIGIBLE").mean())).round(4).to_dict()
    return {"stockDates": int(len(frame)), "signalDates": int(frame.date.nunique()), "byStatus": {k: int(v) for k, v in frame.status.value_counts().items()},
            "eligibleShare": float((frame.status == "ELIGIBLE").mean()),
            "unknownRetainedInDenominator": int(frame.membershipStatus.eq("UNKNOWN").sum()),
            "eligibleStocksPerDate": {"min": int(per_date.min()), "median": float(per_date.median()), "max": int(per_date.max())} if len(per_date) else None,
            "eligibleShareByYear": years,
            "eligibleIndustryDates": int(sum(c["status"] == "ELIGIBLE" for c in cohorts.values())), "industryDates": int(len(cohorts)),
            "datesWithAtLeastMinDateCrossSection": int((per_date >= MIN_DATE_CROSS_SECTION).sum()),
            "eligibleByIndustry": {k: int(v) for k, v in elig.groupby("industry").size().items()}}


def assert_no_forbidden_keys(value, path=""):
    return I.assert_no_forbidden_keys(value, path)


def assert_identity(panel, tolerance=1e-12):
    """stock - market == (loo - market) + (stock - loo) on every matured row of every lens and horizon. Raises on any violation."""
    for h in HORIZONS:
        for lens in WEIGHT_LENSES:
            m = panel[f"status_{lens}_{h}"].eq("MATURED")
            lhs = panel.loc[m, target_column("STOCK_MINUS_MARKET", lens, h)]
            rhs = panel.loc[m, target_column("LOO_INDUSTRY_MINUS_MARKET", lens, h)] + panel.loc[m, target_column("STOCK_MINUS_LOO_INDUSTRY", lens, h)]
            if (lhs - rhs).abs().max() > tolerance if m.any() else False:
                raise ValueError("DECOMPOSITION_IDENTITY_VIOLATED")
    return True


def analyze_all(panels, spec, prior_result):
    """panels: {sensitivity: panel}. Returns the full result. Sensitivities are diagnostics; none is an alternative route."""
    analysis = {name: analyze_panel(p, spec) for name, p in panels.items()}
    comparison = prior_comparison(analysis, prior_result)
    result = {"eligibility": {name: eligibility_summary(p) for name, p in panels.items()}, "analysis": analysis,
              "priorComparison": comparison, "questions": question_readout(analysis, comparison),
              "signViews": {f: sign_views_for(analysis, f)[0] for f in FEATURES}}
    assert_no_forbidden_keys(result)
    return result
