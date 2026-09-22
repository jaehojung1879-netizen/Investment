"""Fundamental-acceleration DISCOVERY study on the sealed ``replay-v16``
ledger -- confirms computability, coverage, orthogonality from the existing
Quality LEVEL factor, and minimal discovery evidence of a forward-return
relationship. NOT a portfolio backtest, NOT a promotion, NOT a weight search.

WHAT THIS STUDY IS
-------------------
``challenger-2-fundamental-acceleration-v1-design.md`` pre-registered the
axis: does the RATE OF CHANGE in a company's own profitability, margins and
growth carry information beyond the Quality sleeve's LEVEL measurement? This
module answers four narrow questions and nothing else:

1. Is the two-consecutive-filing PIT construction actually computable on
   real data, and at what coverage?
2. Is the resulting composite genuinely different information from the
   existing Quality percentile, or a relabelling of it?
3. Is there minimal discovery-stage evidence (standalone and incremental
   Rank IC at the pre-registered 126-trading-day horizon) of a forward-
   return relationship?
4. Is that evidence stable across region and across a fixed chronological
   half-split?

WHAT THIS STUDY IS NOT, ENFORCED BY WHAT IT NEVER CALLS
-----------------------------------------------------------
This module never calls ``kelly_portfolio.select_portfolio_by_scores`` or
``replay_valuation`` -- no portfolio is selected or valued. No factor weight
is searched, no combination with the existing four sleeves is fitted, no
percentile-cutoff or positive-only threshold is tuned, no 3/5/7/10-name
experiment is run, no field is dropped or re-weighted after seeing a result.
The composite formula (sector-neutral z of each of ``roe``/
``operatingMargin``/``profitMargin``/``earningsGrowth``'s filing-over-filing
delta, averaged over whichever of the four are present, minimum three of
four required) is exactly what
``docs/challenger-2-fundamental-acceleration-v1-design.md`` specified before
this module was written, reusing ``longterm.sector_neutral_z`` at its
existing ``winsor=2.5`` default rather than a new normalization.
``debtToEquity`` acceleration is computed and reported as a diagnostic only,
never in the composite, per that same design.

REUSE, NOT REIMPLEMENTATION
------------------------------
The statistical machinery is entirely
``four_factor_signal_attribution_audit.py``'s (``FFA`` below): pooled-
within-region HAC Rank IC (``standalone_ic_series`` + ``pool_region_
summaries``), Holm-Bonferroni correction, the CI-half-width ``se`` recovery
that module's own bugfix introduced (``_with_se_and_p``), and the chronological
half-split (``half_split_dates``). This module adds only what is genuinely
new: the acceleration composite itself, its coverage/orthogonality
diagnostics, a single-predictor incremental-IC residualization (against
Quality alone, not the other three sleeves -- a narrower question than
``four_factor_signal_attribution_audit.py``'s own incremental IC), and the
five-case outcome classification.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import fundamental_acceleration as FA
from . import four_factor_signal_attribution_audit as FFA
from . import historical_outcomes as HO
from . import longterm
from . import pit_data
from . import portfolio_validation as PV
from . import sectors as SECT

VERSION = "fundamental-acceleration-discovery-v1"

PRIMARY_HORIZON = 126
ALL_HORIZONS = (21, 63, 126, 252)
SECONDARY_HORIZONS = tuple(h for h in ALL_HORIZONS if h != PRIMARY_HORIZON)

MIN_NAMES_CROSS_SECTION = FFA.MIN_NAMES_IC  # 5 -- reused, not re-picked
MIN_NAMES_QUINTILE = FFA.MIN_NAMES_QUINTILE  # 15

# Pre-registered failure thresholds -- fixed before any result was computed.
MIN_COVERAGE_RATIO = 0.60
MAX_ORTHOGONALITY_ABS_RHO = 0.70

CASE_A = "A_PROMISING_DISCOVERY_ONLY"
CASE_B = "B_FAIL_REDUNDANCY"
CASE_C = "C_FAIL_COVERAGE"
CASE_D = "D_NO_DISCOVERY_EVIDENCE"
CASE_E = "E_PROMISING_BUT_UNCERTAIN_DISCOVERY"


# --------------------------------------------------------------------------- #
# Candidate table -- one row per signal name-date, acceleration reading only
# --------------------------------------------------------------------------- #
def build_readings(signals: list[dict], store: pit_data.FundamentalStore) -> pd.DataFrame:
    """One row per signal name-date with the raw acceleration reading
    (:func:`fundamental_acceleration.acceleration_reading`) plus the
    identifying fields (`date`, `ticker`, `region`, `sector`) and the
    existing sleeve percentiles this study compares against. This is the
    full candidate universe (every signal row) -- NOT filtered to matured
    outcomes -- because cross-sectional normalization must use the same
    ~20-30 name candidate pool production itself scores on, not a maturity-
    truncated subset of it.
    """
    rows = []
    for signal in signals:
        ticker = signal.get("ticker")
        region = signal.get("region")
        date = signal.get("date")
        if not ticker or not region or not date:
            continue
        reading = FA.acceleration_reading(store, ticker, region, date)
        fp = signal.get("factorPercentiles") or {}
        rows.append({
            "id": signal.get("id"),
            "date": pd.Timestamp(date).normalize(),
            "ticker": ticker,
            "region": region,
            "sector": signal.get("sector") or "Unclassified",
            "qualityPercentile": fp.get("quality"),
            "momentumPercentile": fp.get("momentum"),
            "valuePercentile": fp.get("value"),
            "lowvolPercentile": fp.get("lowvol"),
            "alphaPercentile": signal.get("alphaPercentile"),
            "status": reading["status"],
            "dataSufficient": reading["dataSufficient"],
            "primaryFieldsPresent": reading["primaryFieldsPresent"],
            "deltaRoe": (reading["deltas"] or {}).get("roe"),
            "deltaOperatingMargin": (reading["deltas"] or {}).get("operatingMargin"),
            "deltaProfitMargin": (reading["deltas"] or {}).get("profitMargin"),
            "deltaEarningsGrowth": (reading["deltas"] or {}).get("earningsGrowth"),
            "deltaDebtToEquity": (reading["deltas"] or {}).get("debtToEquity"),
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Composite construction -- sector-neutral z per field, averaged over present
# fields (min 3 of 4), cross-sectional within (date, region), exactly as
# every existing production sleeve is built.
# --------------------------------------------------------------------------- #
def build_composite(readings: pd.DataFrame) -> pd.DataFrame:
    """Adds `compositeZ` and `accelerationPercentile` to `readings`, computed
    within each (date, region) cross-section. Rows that are not
    `dataSufficient` carry `compositeZ = NaN` and are excluded from the
    cross-sectional z/percentile computation they would otherwise pollute.
    """
    out = readings.copy()
    out["compositeZ"] = np.nan
    out["accelerationPercentile"] = np.nan
    delta_columns = ("deltaRoe", "deltaOperatingMargin", "deltaProfitMargin",
                     "deltaEarningsGrowth")
    for (date, region), group in out.groupby(["date", "region"], sort=False):
        eligible = group[group["dataSufficient"]]
        if eligible.empty:
            continue
        z_frames = []
        for column in delta_columns:
            values = eligible[column]
            if values.notna().sum() < 2:
                continue
            z = longterm.sector_neutral_z(values, eligible["sector"], FA.WINSOR)
            z_frames.append(z)
        if not z_frames:
            continue
        composite = pd.concat(z_frames, axis=1).mean(axis=1, skipna=True)
        out.loc[composite.index, "compositeZ"] = composite
        pct = composite.rank(pct=True) * 100.0
        out.loc[pct.index, "accelerationPercentile"] = pct
    return out


# --------------------------------------------------------------------------- #
# Debt-to-equity acceleration -- diagnostic only, never in the composite.
# Sector-exempt exactly as production's own leverage penalty is
# (`longterm.score_cross_section`'s `lev.where(~lev_exempt)`): a structurally
# high-leverage sector (Financials/Utilities/Real Estate/Holding) is masked
# out rather than penalized or rewarded for a debt-to-equity change, so this
# diagnostic never credits or blames those names for it either.
# --------------------------------------------------------------------------- #
def debt_acceleration_diagnostic(readings: pd.DataFrame) -> dict:
    ok = readings[readings["status"] == FA.OK].copy()
    exempt = ok["sector"].isin(SECT.LEVERAGE_EXEMPT_SECTORS)
    masked = ok["deltaDebtToEquity"].where(~exempt)
    non_exempt = masked.dropna()
    return {
        "exemptSectors": sorted(SECT.LEVERAGE_EXEMPT_SECTORS),
        "nonExemptObservations": int(len(non_exempt)),
        "exemptObservationsMasked": int(exempt.sum()),
        "meanDeltaDebtToEquityNonExempt": (round(float(non_exempt.mean()), 6)
                                           if len(non_exempt) else None),
        "note": ("Diagnostic only -- never included in the acceleration composite. "
                 "Exempt-sector names are masked out exactly as production's own "
                 "leverage penalty masks them, never included at a zero/neutral value."),
    }


# --------------------------------------------------------------------------- #
# Stage A -- coverage
# --------------------------------------------------------------------------- #
def coverage_table(readings: pd.DataFrame) -> dict:
    def _summarize(frame: pd.DataFrame) -> dict:
        total = len(frame)
        by_status = frame["status"].value_counts().to_dict()
        sufficient = int(frame["dataSufficient"].sum())
        return {
            "total": total,
            "dataSufficient": sufficient,
            "dataSufficientRatio": round(sufficient / total, 4) if total else None,
            "byStatus": {k: int(v) for k, v in by_status.items()},
        }

    overall = _summarize(readings)
    by_region = {region: _summarize(part)
                for region, part in readings.groupby("region", sort=True)}
    dates = sorted(readings["date"].dropna().unique())
    by_half = {}
    if dates:
        mid = len(dates) // 2
        by_half = {
            "firstHalf": _summarize(readings[readings["date"].isin(dates[:mid])]),
            "secondHalf": _summarize(readings[readings["date"].isin(dates[mid:])]),
        }
    delta_columns = {
        "roe": "deltaRoe", "operatingMargin": "deltaOperatingMargin",
        "profitMargin": "deltaProfitMargin", "earningsGrowth": "deltaEarningsGrowth",
        "debtToEquity": "deltaDebtToEquity",
    }
    by_field = {}
    ok_rows = readings[readings["status"] == FA.OK]
    for field, column in delta_columns.items():
        present = int(ok_rows[column].notna().sum())
        by_field[field] = {
            "presentAmongOkFilingPairs": present,
            "presentPct": (round(present / len(ok_rows) * 100, 3)
                          if len(ok_rows) else None),
        }
    return {
        "overall": overall, "byRegion": by_region, "byTimeHalf": by_half,
        "byField": by_field,
        "meetsMinCoverageRatio": (overall["dataSufficientRatio"] is not None
                                  and overall["dataSufficientRatio"] >= MIN_COVERAGE_RATIO),
        "minCoverageRatio": MIN_COVERAGE_RATIO,
    }


# --------------------------------------------------------------------------- #
# Stage B -- orthogonality against the existing Quality LEVEL factor
# --------------------------------------------------------------------------- #
def orthogonality_table(readings: pd.DataFrame) -> dict:
    """Pooled, time-averaged Spearman(accelerationPercentile, X) for
    X in {quality, momentum, value, lowvol}. Quality is the primary claim
    (this study's own failure criterion); the other three are descriptive
    corroboration only.
    """
    work = readings.dropna(subset=["accelerationPercentile"])
    out = {}
    for column, key in (("qualityPercentile", "quality"), ("momentumPercentile", "momentum"),
                        ("valuePercentile", "value"), ("lowvolPercentile", "lowvol")):
        per_date = []
        for (_date, _region), group in work.groupby(["date", "region"], sort=False):
            usable = group.dropna(subset=["accelerationPercentile", column])
            if len(usable) >= MIN_NAMES_CROSS_SECTION:
                rho = usable["accelerationPercentile"].corr(usable[column], method="spearman")
                if pd.notna(rho):
                    per_date.append(float(rho))
        out[key] = {
            "meanSpearman": round(float(np.mean(per_date)), 4) if per_date else None,
            "medianSpearman": round(float(np.median(per_date)), 4) if per_date else None,
            "observations": len(per_date),
        }
    quality_abs = abs(out["quality"]["meanSpearman"]) if out["quality"]["meanSpearman"] is not None else None
    return {
        "byFactor": out,
        "qualityAbsRho": quality_abs,
        "failsRedundancy": quality_abs is not None and quality_abs >= MAX_ORTHOGONALITY_ABS_RHO,
        "maxOrthogonalityAbsRho": MAX_ORTHOGONALITY_ABS_RHO,
        "note": ("Descriptive momentum/value/lowvol correlations are reported beside the "
                 "primary Quality reading; only Quality's |rho| enters the FAIL_REDUNDANCY "
                 "criterion, per this study's own pre-registered design."),
    }


# --------------------------------------------------------------------------- #
# Outcome frame -- horizon_frame joined to acceleration readings by id
# --------------------------------------------------------------------------- #
def build_outcome_frame(readings_with_composite: pd.DataFrame, outcomes: list[dict],
                        horizon: int) -> pd.DataFrame:
    frame = HO.horizon_frame(outcomes, horizon, cost_adjusted=False)
    if frame.empty:
        return frame
    lookup = readings_with_composite.set_index("id")[
        ["accelerationPercentile", "compositeZ", "qualityPercentile", "dataSufficient"]
    ].to_dict("index")
    frame = frame.copy()
    for column in ("accelerationPercentile", "compositeZ", "qualityPercentile"):
        frame[column] = [
            (lookup.get(identifier) or {}).get(column) for identifier in frame["id"]
        ]
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


# --------------------------------------------------------------------------- #
# Standalone and incremental IC -- reusing FFA's HAC/pooling machinery
# --------------------------------------------------------------------------- #
def standalone_ic_summary(frame: pd.DataFrame, horizon: int) -> dict:
    regions = sorted(frame["region"].dropna().unique())
    by_region = {}
    for region in regions:
        series = FFA.standalone_ic_series(frame, region, "accelerationPercentile")
        by_region[region] = FFA._with_se_and_p(PV._nw_summary(series, horizon))
    pooled = FFA.pool_region_summaries(by_region)
    return {"byRegion": by_region, "pooled": pooled}


def _incremental_ic_series(frame: pd.DataFrame, region: str) -> pd.Series:
    """Residualize `accelerationPercentile` rank against `qualityPercentile`
    rank ALONE (single predictor + intercept), per date, then Spearman the
    residual against forward excess return. Deliberately narrower than
    `four_factor_signal_attribution_audit.py`'s own incremental IC (which
    controls for all three OTHER sleeves) -- this study's incremental
    question is specifically "beyond Quality's level", not "beyond the
    whole existing composite".
    """
    part = frame[frame["region"] == region]
    rows = []
    for date, group in part.groupby("date", sort=True):
        usable = group.dropna(subset=["accelerationPercentile", "qualityPercentile", "excessReturn"])
        if len(usable) < MIN_NAMES_CROSS_SECTION:
            continue
        x = usable["qualityPercentile"].to_numpy(dtype=float)
        y = usable["accelerationPercentile"].to_numpy(dtype=float)
        design = np.column_stack([np.ones(len(usable)), x])
        coef, *_ = np.linalg.lstsq(design, y, rcond=None)
        residual = y - design @ coef
        if np.std(residual) <= 1e-12:
            continue
        ic = pd.Series(residual).corr(pd.Series(usable["excessReturn"].to_numpy()), method="spearman")
        if pd.notna(ic):
            rows.append((date, float(ic)))
    return pd.Series(dict(rows), dtype=float).sort_index()


def incremental_ic_summary(frame: pd.DataFrame, horizon: int) -> dict:
    regions = sorted(frame["region"].dropna().unique())
    by_region = {}
    for region in regions:
        series = _incremental_ic_series(frame, region)
        by_region[region] = FFA._with_se_and_p(PV._nw_summary(series, horizon))
    pooled = FFA.pool_region_summaries(by_region)
    return {"byRegion": by_region, "pooled": pooled}


# --------------------------------------------------------------------------- #
# Quintile diagnostic -- single column, single horizon
# --------------------------------------------------------------------------- #
def quintile_table(frame: pd.DataFrame) -> dict:
    buckets: list[list[float]] = [[] for _ in range(5)]
    for _date, group in frame.groupby("date", sort=True):
        qs = group.dropna(subset=["accelerationPercentile", "excessReturn"])
        if len(qs) < MIN_NAMES_QUINTILE:
            continue
        try:
            bucket = pd.qcut(qs["accelerationPercentile"], 5, labels=False, duplicates="drop")
        except ValueError:
            continue
        for b in sorted(pd.unique(bucket.dropna())):
            b = int(b)
            if b >= 5:
                continue
            selected = qs.loc[bucket == b, "excessReturn"]
            if len(selected):
                buckets[b].append(float(selected.mean()))
    means = [round(float(np.mean(b)), 6) if b else None for b in buckets]
    observations = [len(b) for b in buckets]
    valid = [m for m in means if m is not None]
    mono = None
    if len(valid) >= 2:
        mono = round(sum(b >= a for a, b in zip(valid[:-1], valid[1:], strict=True))
                    / (len(valid) - 1), 3)
    spread = (means[4] - means[0]) if means[0] is not None and means[4] is not None else None
    return {"quintileMeans": means, "observationsPerQuintile": observations,
           "monotonicityScore": mono,
           "q5MinusQ1": round(spread, 6) if spread is not None else None}


# --------------------------------------------------------------------------- #
# Stability -- region sign agreement, fixed chronological half-split
# --------------------------------------------------------------------------- #
def region_stability(standalone: dict) -> dict:
    signs = {region: FFA._sign(row.get("mean")) for region, row in standalone["byRegion"].items()}
    agree = len({s for s in signs.values() if s}) <= 1 and any(signs.values())
    return {"signsByRegion": signs, "agree": agree,
           "label": None if agree else "REGION_SIGN_UNSTABLE"}


def half_split_stability(frame: pd.DataFrame, horizon: int) -> dict:
    first_dates, second_dates = FFA.half_split_dates(frame)
    if first_dates is None:
        return {"firstHalf": None, "secondHalf": None, "agree": None}
    first = frame[frame["date"].isin(first_dates)]
    second = frame[frame["date"].isin(second_dates)]
    out = {}
    signs = []
    for label, part in (("firstHalf", first), ("secondHalf", second)):
        regions = sorted(part["region"].dropna().unique())
        by_region = {region: FFA._with_se_and_p(
            PV._nw_summary(FFA.standalone_ic_series(part, region, "accelerationPercentile"), horizon))
            for region in regions}
        pooled = FFA.pool_region_summaries(by_region)
        out[label] = pooled
        signs.append(FFA._sign(pooled.get("mean")))
    agree = len({s for s in signs if s}) <= 1 and any(signs)
    out["agree"] = agree
    out["label"] = None if agree else "HALF_SIGN_UNSTABLE"
    return out


# --------------------------------------------------------------------------- #
# Quality-level-conditional diagnostic -- descriptive only
# --------------------------------------------------------------------------- #
def quality_conditional_table(frame: pd.DataFrame) -> dict:
    """Within Quality-percentile quintile buckets (fixed, cross-sectional per
    date), median-split the acceleration composite into high/low and compare
    mean forward excess return -- a parameter-free descriptive read of
    whether the acceleration signal adds anything WITHIN a Quality level,
    never a score, ranking or rule.
    """
    out: dict[str, dict] = {}
    for _date, group in frame.groupby("date", sort=True):
        qs = group.dropna(subset=["qualityPercentile", "accelerationPercentile", "excessReturn"])
        if len(qs) < MIN_NAMES_QUINTILE:
            continue
        try:
            qbucket = pd.qcut(qs["qualityPercentile"], 5, labels=False, duplicates="drop")
        except ValueError:
            continue
        for b in sorted(pd.unique(qbucket.dropna())):
            b = int(b)
            sub = qs.loc[qbucket == b]
            if len(sub) < 4:
                continue
            median = sub["accelerationPercentile"].median()
            high = sub.loc[sub["accelerationPercentile"] >= median, "excessReturn"]
            low = sub.loc[sub["accelerationPercentile"] < median, "excessReturn"]
            key = f"qualityQ{b + 1}"
            out.setdefault(key, {"highMeans": [], "lowMeans": []})
            if len(high):
                out[key]["highMeans"].append(float(high.mean()))
            if len(low):
                out[key]["lowMeans"].append(float(low.mean()))
    result = {}
    for key, values in out.items():
        high_mean = float(np.mean(values["highMeans"])) if values["highMeans"] else None
        low_mean = float(np.mean(values["lowMeans"])) if values["lowMeans"] else None
        result[key] = {
            "highAccelerationMeanExcess": round(high_mean, 6) if high_mean is not None else None,
            "lowAccelerationMeanExcess": round(low_mean, 6) if low_mean is not None else None,
            "difference": (round(high_mean - low_mean, 6)
                          if high_mean is not None and low_mean is not None else None),
            "observations": len(values["highMeans"]) + len(values["lowMeans"]),
        }
    return result


# --------------------------------------------------------------------------- #
# Section 26 -- five-case outcome classification, fixed priority order
# --------------------------------------------------------------------------- #
def classify_outcome(*, coverage: dict, orthogonality: dict,
                     standalone_pooled: dict, incremental_pooled: dict) -> dict:
    if not coverage["meetsMinCoverageRatio"]:
        return {"case": CASE_C, "rationale":
                (f"Data-sufficient coverage ratio "
                 f"{coverage['overall']['dataSufficientRatio']} is below the pre-registered "
                 f"minimum {MIN_COVERAGE_RATIO}.")}
    if orthogonality["failsRedundancy"]:
        return {"case": CASE_B, "rationale":
                (f"|Spearman(accelerationPercentile, qualityPercentile)| = "
                 f"{orthogonality['qualityAbsRho']} clears the pre-registered redundancy "
                 f"threshold {MAX_ORTHOGONALITY_ABS_RHO}; the composite reads as a "
                 "relabelling of the existing Quality level factor rather than new "
                 "information.")}

    standalone_mean = standalone_pooled.get("mean")
    incremental_mean = incremental_pooled.get("mean")
    standalone_ci = standalone_pooled.get("ci95")
    incremental_ci = incremental_pooled.get("ci95")

    def _separated_positive(ci):
        return ci is not None and ci[0] is not None and ci[0] > 0

    both_positive = (standalone_mean is not None and standalone_mean > 0
                     and incremental_mean is not None and incremental_mean > 0)
    both_separated = _separated_positive(standalone_ci) and _separated_positive(incremental_ci)

    if both_positive and both_separated:
        return {"case": CASE_A, "rationale":
                ("Standalone and incremental pooled Rank IC are both positive and both "
                 "95% CIs exclude zero in the positive direction. This is DISCOVERY-STAGE "
                 "evidence only -- no promotion, no weight, no portfolio claim follows from "
                 "it; the confirmatory claim rests on the prospective sealed window.")}
    if both_positive:
        return {"case": CASE_E, "rationale":
                ("Standalone and incremental pooled Rank IC point estimates are both "
                 "positive, but at least one 95% CI contains zero -- directionally "
                 "promising but not statistically separated on this sample.")}
    return {"case": CASE_D, "rationale":
            ("Standalone and/or incremental pooled Rank IC point estimates are not both "
             "positive, or the evidence is otherwise mixed. No discovery evidence of a "
             "forward-return relationship beyond the existing Quality level factor on "
             "this sample.")}
