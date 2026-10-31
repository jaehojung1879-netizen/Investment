"""Industry-date panel assembly for industry-alpha-kr-next-v1. Pure functions, no I/O.

Membership, frozen cohorts, the past-only industry features and the industry target are the SEALED anatomy's own
functions (`pipeline.kr_industry_anatomy`), imported and called, never copied. This module adds only what that study
did not define: the monthly signal rule, the leader/laggard split and its features, the market-context columns, the
laggard-basket target, and a label-free exposure audit of who the classified cohorts leave out.

Outcome-reading functions take an `OutcomePermit`; nothing else here reads a forward price.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from pipeline import kr_industry_anatomy as I

from . import study as S


@dataclass(frozen=True)
class OutcomePermit:
    """Issued only by `run_study.authorize` (real) or `synthetic_permit` (SYNTHETIC_FIXTURE scope)."""
    scope: str
    specSha256: str


def synthetic_permit():
    return OutcomePermit(scope="SYNTHETIC_FIXTURE", specSha256="SYNTHETIC")


def require_permit(permit):
    if not isinstance(permit, OutcomePermit) or permit.scope not in ("SYNTHETIC_FIXTURE", "AUTHORIZED_HISTORICAL"):
        raise PermissionError("OUTCOME_PERMIT_REQUIRED")


# --------------------------------------------------------------------------- #
# Signal schedule
# --------------------------------------------------------------------------- #
def monthly_signals(weekly_schedule):
    """Last weekly-grid date of each calendar month -> its PIT members. The members are never re-derived."""
    last = {}
    for date in sorted(weekly_schedule):
        last[date[:7]] = date
    return {d: list(weekly_schedule[d]) for d in sorted(last.values())}


# --------------------------------------------------------------------------- #
# Label-free columns this study adds
# --------------------------------------------------------------------------- #
def leader_split(cohort):
    """(leaders, laggards) by signal-date cap weight; None when caps are unavailable or either side is too small."""
    weights = cohort.get("capWeights")
    if cohort.get("status") != "ELIGIBLE" or weights is None:
        return None
    ordered = sorted(weights, key=lambda t: (-weights[t], t))
    k = max(1, math.ceil(S.LEADER_SHARE * len(ordered)))
    leaders, laggards = ordered[:k], ordered[k:]
    if len(leaders) < S.MIN_LEADERS or len(laggards) < S.MIN_LAGGARDS:
        return None
    return leaders, laggards


def _mean(values):
    x = np.asarray(values, float)
    return float(x.mean()) if len(x) and np.isfinite(x).all() else np.nan


def diffusion_features(cohort, past):
    """Leader/laggard columns from past-only trailing values. NaN unless EVERY needed member value is finite."""
    out = {name: np.nan for name in S.DIFFUSION_SIGNAL + ("LAGGARD_MOM_126", "LAGGARD_BREADTH_126", "EX_LEADER_MOM_126")}
    split = leader_split(cohort)
    if split is None:
        return out, None
    leaders, laggards = split
    get = lambda t, k: past.get(t, {}).get(k, np.nan)  # noqa: E731
    bench = {get(t, "bench126") for t in laggards}
    b126 = next(iter(bench)) if len(bench) == 1 else np.nan
    out["LEADER_GAP_63"] = _mean([get(t, "trail63") for t in leaders]) - _mean([get(t, "trail63") for t in laggards])
    out["LAGGARD_MOM_126"] = _mean([get(t, "trail126") for t in laggards]) - b126
    out["LAGGARD_BREADTH_126"] = _mean([get(t, "aboveMA126") for t in laggards])
    w = cohort["capWeights"]
    lag_w = {t: w[t] for t in laggards}
    total = math.fsum(lag_w.values())
    values = [get(t, "trail126") for t in laggards]
    if np.isfinite(values).all() and total > 0:
        out["EX_LEADER_MOM_126"] = math.fsum(lag_w[t] / total * v for t, v in zip(laggards, values)) - b126
    return out, {"leaders": list(leaders), "laggards": list(laggards)}


def market_context(benchmark_close):
    """Past-only market state from the benchmark closes ending AT the signal session (array, oldest first)."""
    c = np.asarray(benchmark_close, float)
    out = {"MKT_RET_126": np.nan, "MKT_VOL_126": np.nan, "MKT_ABOVE_SMA200": np.nan}
    if len(c) >= 127:
        out["MKT_RET_126"] = I.trailing_return(c, len(c) - 1, 126)
        r = I.daily_returns_window(c, len(c) - 1, 126)
        if r is not None:
            out["MKT_VOL_126"] = float(np.std(r, ddof=0) * math.sqrt(I.ANNUALISATION))
    if len(c) >= 200 and np.isfinite(c[-200:]).all() and (c[-200:] > 0).all():
        out["MKT_ABOVE_SMA200"] = float(c[-1] > c[-200:].mean())
    return out


def industry_rows(cohorts, past, panel_values, market_by_date, caps):
    """One row per ELIGIBLE (date, industry): sealed anatomy features + this study's columns. Label-free.

    `caps` maps (date, ticker) -> signal-time cap used only for LOG_INDUSTRY_CAP."""
    rows, splits = [], {}
    for (date, industry), cohort in sorted(cohorts.items()):
        if cohort["status"] != "ELIGIBLE":
            continue
        f = I.industry_features(cohort, past[date], panel_values[date])
        f["HHI"] = cohort["hhi"]
        f["LOG_CONSTITUENT_COUNT"] = math.log(cohort["n"])
        total = [caps.get((date, t), np.nan) for t in cohort["members"]]
        f["LOG_INDUSTRY_CAP"] = math.log(math.fsum(total)) if np.isfinite(total).all() and min(total) > 0 else np.nan
        d, split = diffusion_features(cohort, past[date])
        f.update(d)
        m = market_by_date[date]
        f.update(m)
        trend = m["MKT_ABOVE_SMA200"]
        f["MOM_X_MKT_TREND"] = f["REL_MOM_126"] * trend
        f["BREADTH_X_MKT_TREND"] = f["BREADTH_ABOVE_MA_126"] * trend
        rows.append({"date": date, "industry": industry, "n": cohort["n"], **f})
        if split:
            splits[(date, industry)] = split
    return pd.DataFrame(rows), splits


def intended_blocks(cohorts):
    """The signal-time cohort per eligible (date, industry), the denominator a paired receipt must be sealed on."""
    return {f"{d}|{g}": tuple(c["members"]) for (d, g), c in sorted(cohorts.items()) if c["status"] == "ELIGIBLE"}


def exposure_audit(membership, caps, terminal):
    """Who the classified cohorts leave out, per signal date: counts AND cap shares. Label-free.

    `membership` is `I.membership_table` output; `caps` (date, ticker) -> snapshot cap; `terminal` the set of
    securities later terminated (their economics unresolved). Nothing here is a return."""
    rows = []
    for date, group in membership.groupby("date", sort=True):
        tickers = list(group.ticker)
        cap = {t: caps.get((date, t), np.nan) for t in tickers}
        finite = {t: v for t, v in cap.items() if np.isfinite(v) and v > 0}
        total = math.fsum(finite.values())
        unclassified = [t for t, g in zip(group.ticker, group.industry) if g is None or (isinstance(g, float) and np.isnan(g))]
        term = [t for t in tickers if t in terminal]
        counts = group[group.industry.notna()].groupby("industry").size()
        eligible = counts[counts >= S.MIN_MEMBERS]
        in_eligible = [t for t, g in zip(group.ticker, group.industry) if g in set(eligible.index)]
        share = lambda names: (math.fsum(finite.get(t, 0.0) for t in names) / total) if total > 0 else np.nan  # noqa: E731
        rows.append({"date": date, "members": len(tickers), "membersWithCap": len(finite),
                     "unclassified": len(unclassified), "unclassifiedCapShare": share(unclassified),
                     "terminalLater": len(term), "terminalLaterCapShare": share(term),
                     "terminalLaterClassified": sum(1 for t in term if t not in unclassified),
                     "eligibleIndustries": int(len(eligible)), "inEligibleCohorts": len(in_eligible),
                     "inEligibleCohortCapShare": share(in_eligible)})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Targets (permit required)
# --------------------------------------------------------------------------- #
def industry_and_laggard_targets(cohorts, splits, forward, horizon, permit):
    """forward[(date, horizon)] = {ticker: (stockReturn, benchmarkReturn, status)} built under a permit.

    Industry target = the SEALED `I.industry_targets` (frozen signal-date weights, every member required).
    Laggard target = equal-weight laggard basket minus the same benchmark window, every laggard required."""
    require_permit(permit)
    out = {}
    for (date, industry), cohort in sorted(cohorts.items()):
        if cohort["status"] != "ELIGIBLE":
            continue
        fwd = forward[(date, horizon)]
        t = I.industry_targets(cohort, fwd, horizon)
        rec = {"date": date, "industry": industry,
               "cwRelative": t["CAP_WEIGHTED"]["relative"], "cwStatus": t["CAP_WEIGHTED"]["status"],
               "ewRelative": t["EQUAL_WEIGHT"]["relative"], "ewStatus": t["EQUAL_WEIGHT"]["status"],
               "laggardRelative": None, "laggardStatus": "NO_DIFFUSION_SPLIT"}
        split = splits.get((date, industry))
        if split:
            lag = split["laggards"]
            bench = {fwd[x][1] for x in lag if x in fwd and fwd[x][2] == "MATURED" and np.isfinite(fwd[x][1])}
            vals = [fwd[x][0] if x in fwd and fwd[x][2] == "MATURED" else np.nan for x in lag]
            if np.isfinite(vals).all() and len(bench) == 1:
                rec["laggardRelative"] = float(np.mean(vals)) - next(iter(bench))
                rec["laggardStatus"] = "MATURED"
            else:
                rec["laggardStatus"] = "UNRESOLVED_INCOMPLETE_LAGGARD_BASKET_OR_WINDOW"
        out[(date, industry)] = rec
    return pd.DataFrame(list(out.values()))
