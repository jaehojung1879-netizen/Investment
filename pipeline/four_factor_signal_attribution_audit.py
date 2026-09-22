"""Attribution audit of the four production alpha sleeves -- NOT a search for a
better combination.

WHAT THIS STUDY IS
-------------------
Production's long-horizon alpha is
``rawAlpha = 0.30 momentum + 0.25 value + 0.25 quality + 0.20 lowvol``,
shrunk by ``alpha = rawAlpha x evidenceCoverage``
(:data:`pipeline.longterm.FACTOR_WEIGHTS`, :func:`pipeline.longterm
.score_cross_section`). ``alpha-calibration-resolution-v1`` measured that,
within a calibration-tied group, the composite's own discarded ordinal
information (``alphaPercentile``) does not predict forward excess
(pairwise concordance ~49%, within-group Spearman ~0). This study asks the
question one level down: of the four sleeves that feed the composite, which
ones carry information about future benchmark-relative return, which are
redundant with each other, and which cannot be assessed at all because the
sealed ledger never stored their raw inputs?

WHAT THIS STUDY IS NOT
-----------------------
No factor weight is changed. No combination is searched. No new Alpha
formula is built from this sample. No portfolio is selected or valued --
this module never calls ``kelly_portfolio.select_portfolio_by_scores`` or
``replay_valuation``; it reads sleeve percentiles and matured
benchmark-relative outcomes directly from the sealed signals/outcomes and
computes cross-sectional rank information coefficients. The result is
DISCOVERY / DIAGNOSTIC EVIDENCE on a ledger already used by ten prior
studies, never FINAL OUT-OF-SAMPLE VALIDATION, and is never used to promote
a selector or relax the Kelly gate.

CONFIRMATORY FAMILY, FIXED BEFORE ANY NUMBER WAS COMPUTED
-----------------------------------------------------------
Exactly four primary hypotheses -- one per sleeve -- tested at
``PRIMARY_HORIZON = 126`` trading days (production's own target horizon and
the horizon the expanding-bucket calibration is itself built on). 21D/63D/
252D are SECONDARY and descriptive only; the horizon that looks best is
never promoted to primary after the fact. The primary confirmatory
statistic is each sleeve's POOLED-WITHIN-REGION aggregate rank IC (see
:func:`pool_region_summaries`); KR-only and US-only readings are reported
beside it as corroboration, never substituted for it, per section 8's
"KR/US never pooled into one ranking" rule -- the pooling combines two
already-computed, independently-estimated regional SUMMARIES, never the
underlying cross-sections.

WHY PROVENANCE IS MEASURED, NOT ASSUMED
------------------------------------------
``lowvol-alpha-separation-v1`` established the discipline this study
repeats at the subfactor level: read the sealed schema before designing
around it. The sealed replay-v16 signal record stores each sleeve's
PERCENTILE (``factorPercentiles``), ``alphaPercentile``, ``rawAlpha`` and
``alpha`` -- but never the raw subfactor inputs
(:data:`pipeline.longterm.RAW_INPUT_COLUMNS`) production computed them
from, with the single exception of Lowvol's one input (realised 252-day
volatility), which survives as ``risk.vol252Pct``. This was verified by
scanning the sealed ledger's own rows (:func:`provenance_inventory`), not
assumed from the production code that writes them: `mom20Pct`/`mom60Pct`/
`relMomentum` DO exist on the record, but they are a DIFFERENT short-horizon
feature computed for the entry/overheat layer, not production's momentum
sleeve inputs (12-1 month and 6-month momentum), and are never substituted
for them.
"""
from __future__ import annotations

from collections import defaultdict
import math

import numpy as np
import pandas as pd
from scipy import stats as sps

from . import historical_outcomes as HO
from . import portfolio_validation as PV

VERSION = "four-factor-signal-attribution-audit-v1"

PRIMARY_HORIZON = 126
ALL_HORIZONS = (21, 63, 126, 252)
SECONDARY_HORIZONS = tuple(h for h in ALL_HORIZONS if h != PRIMARY_HORIZON)
SLEEVES = ("momentum", "value", "quality", "lowvol")

# Minimum names in one date-region cross-section before a statistic is
# computed at all. IC matches `portfolio_validation.alpha_diagnostics`'s own
# floor exactly (reused, not re-picked). Quartile/quintile/incremental need
# enough names per bucket / regression degree of freedom to be non-degenerate
# and are set once, before any result was read, never loosened to rescue a
# thin date-region.
MIN_NAMES_IC = 5
MIN_NAMES_QUARTILE = 12
MIN_NAMES_QUINTILE = 15
MIN_NAMES_INCREMENTAL = 12  # 3 predictors + intercept


def _finite(value):
    return PV._finite(value)


# --------------------------------------------------------------------------- #
# Stage 0 -- provenance inventory, measured by scanning the sealed ledger
# --------------------------------------------------------------------------- #
SUBFACTOR_CANDIDATES = {
    "momentum": ("mom121", "mom6"),
    "value": ("earningsYield", "fwdEarningsYield", "bookYield", "fcfYield"),
    "quality": ("roe", "opMargin", "profitMargin", "earningsGrowth", "debtToEquity"),
    "lowvol": ("vol252",),
}
# Where each candidate would live on a signal ROW if it were stored there.
# Everything but vol252 is a top-level key that production's own
# `historical_replay.py` never writes into the signal record (only into the
# transient raw_rows dict used for scoring); vol252 alone survives as
# `risk.vol252Pct`.
_CANDIDATE_PATHS = {
    "mom121": ("mom121",), "mom6": ("mom6",),
    "earningsYield": ("earningsYield",), "fwdEarningsYield": ("fwdEarningsYield",),
    "bookYield": ("bookYield",), "fcfYield": ("fcfYield",),
    "roe": ("roe",), "opMargin": ("opMargin",), "profitMargin": ("profitMargin",),
    "earningsGrowth": ("earningsGrowth",), "debtToEquity": ("debtToEquity",),
    "vol252": ("risk", "vol252Pct"),
}


def _get_path(row: dict, path: tuple[str, ...]):
    cur = row
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def provenance_inventory(signals: list[dict]) -> dict:
    """What the sealed ledger's signal rows actually carry -- measured by
    scanning every row, not assumed from the production code that wrote
    them. Returns AVAILABLE / UNAVAILABLE per subfactor candidate; a subfactor
    audit in this module runs ONLY on candidates this function marks
    available.
    """
    total = len(signals)
    sleeve_present = dict.fromkeys(SLEEVES, 0)
    top_level_present = dict.fromkeys(("alphaPercentile", "rawAlpha", "alpha",
                                       "evidenceCoverage"), 0)
    subfactor_present = dict.fromkeys(_CANDIDATE_PATHS, 0)
    for row in signals:
        fp = row.get("factorPercentiles") or {}
        for sleeve in SLEEVES:
            if fp.get(sleeve) is not None:
                sleeve_present[sleeve] += 1
        if row.get("alphaPercentile") is not None:
            top_level_present["alphaPercentile"] += 1
        if row.get("rawAlpha") is not None:
            top_level_present["rawAlpha"] += 1
        if row.get("alpha") is not None:
            top_level_present["alpha"] += 1
        if (row.get("features") or {}).get("evidenceCoverage") is not None:
            top_level_present["evidenceCoverage"] += 1
        for name, path in _CANDIDATE_PATHS.items():
            if _get_path(row, path) is not None:
                subfactor_present[name] += 1

    subfactor_status: dict[str, dict] = {}
    for sleeve, names in SUBFACTOR_CANDIDATES.items():
        subfactor_status[sleeve] = {}
        for name in names:
            count = subfactor_present[name]
            subfactor_status[sleeve][name] = {
                "presentCount": count,
                "presentPct": round(count / total * 100, 4) if total else None,
                "status": ("AVAILABLE" if count > 0
                           else "UNAVAILABLE_PIT_INPUT_NOT_STORED"),
            }
    return {
        "totalSignals": total,
        "sleeveLevel": {
            sleeve: {"presentCount": sleeve_present[sleeve],
                     "presentPct": (round(sleeve_present[sleeve] / total * 100, 4)
                                    if total else None)}
            for sleeve in SLEEVES
        },
        "topLevel": {key: {"presentCount": value,
                           "presentPct": round(value / total * 100, 4) if total else None}
                     for key, value in top_level_present.items()},
        "subfactorLevel": subfactor_status,
        "note": (
            "AVAILABLE/UNAVAILABLE is measured by scanning every signal row for "
            "the exact key path production's own raw_inputs()/historical_replay.py "
            "would have written it to, not assumed from reading the code. "
            "`mom20Pct`/`mom60Pct`/`relMomentum` exist on the record but are a "
            "DIFFERENT short-horizon feature (entry/overheat layer), never "
            "production's momentum sleeve inputs (mom121, mom6), and are never "
            "substituted for them in this audit."),
    }


# --------------------------------------------------------------------------- #
# Frame assembly -- built on historical_outcomes.horizon_frame, the same
# PIT-matured outcome frame every other study in this line reads
# --------------------------------------------------------------------------- #
_EXTRA_COLUMNS = ("momentum", "value", "quality", "lowvol", "rawAlpha", "alpha",
                  "evidenceCoverage", "vol252Raw")


def build_frame(signals: list[dict], outcomes: list[dict], horizon: int) -> pd.DataFrame:
    """One row per matured (id, horizon) observation.

    `historical_outcomes.horizon_frame` supplies date/region/sector/
    alphaPercentile/excessReturn exactly as `portfolio_validation
    ._joined_frame` reuses it; this function adds the sleeve percentiles,
    rawAlpha/alpha, evidenceCoverage and the Lowvol sleeve's one PIT-available
    raw input (vol252) that `_joined_frame` does not carry.
    """
    frame = HO.horizon_frame(outcomes, horizon, cost_adjusted=False)
    if frame.empty:
        return frame
    lookup: dict[str, dict] = {}
    for row in signals:
        sid = row.get("id")
        if sid is None:
            continue
        fp = row.get("factorPercentiles") or {}
        lookup[sid] = {
            "momentum": _finite(fp.get("momentum")),
            "value": _finite(fp.get("value")),
            "quality": _finite(fp.get("quality")),
            "lowvol": _finite(fp.get("lowvol")),
            "rawAlpha": _finite(row.get("rawAlpha")),
            "alpha": _finite(row.get("alpha")),
            "evidenceCoverage": _finite((row.get("features") or {}).get("evidenceCoverage")),
            "vol252Raw": _finite((row.get("risk") or {}).get("vol252Pct")),
        }
    frame = frame.copy()
    for column in _EXTRA_COLUMNS:
        frame[column] = [(lookup.get(identifier) or {}).get(column)
                         for identifier in frame["id"]]
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


# --------------------------------------------------------------------------- #
# Primary metric -- cross-sectional Rank IC by date x region
# --------------------------------------------------------------------------- #
def standalone_ic_series(frame: pd.DataFrame, region: str, column: str) -> pd.Series:
    """Per-date Spearman(column, excessReturn) within ONE region's own
    cross-section -- the exact pattern `portfolio_validation.alpha_diagnostics`
    uses for `alphaPercentile`, generalized to any sleeve column and reused
    rather than reimplemented from scratch.
    """
    part = frame[frame["region"] == region]
    rows = []
    for date, group in part.groupby("date", sort=True):
        usable = group.dropna(subset=[column, "excessReturn"])
        if len(usable) >= MIN_NAMES_IC:
            ic = usable[column].corr(usable["excessReturn"], method="spearman")
            if pd.notna(ic):
                rows.append((date, float(ic)))
    return pd.Series(dict(rows), dtype=float).sort_index()


def _p_value(mean, se) -> float | None:
    if mean is None or se is None or se <= 0:
        return None
    z = abs(mean) / se
    return float(2.0 * sps.norm.sf(z))


def _with_se_and_p(summary: dict) -> dict:
    """`portfolio_validation._nw_summary` reports the 95% CI but not `se`
    directly. Every HAC summary this module pools through
    `pool_region_summaries` needs `se` recovered from the CI half-width
    first -- centralized here so every caller (`sleeve_ic_table`,
    `incremental_ic_table`, `quartile_spread_table`) attaches it the same
    way, rather than each reimplementing it and risking one silently
    omitting it (which `pool_region_summaries` would then read as
    'this region has no usable estimate' and drop).
    """
    ci = summary.get("ci95")
    summary["se"] = round((ci[1] - ci[0]) / (2 * 1.96), 8) if ci else None
    summary["rawPValue"] = _p_value(summary.get("mean"), summary.get("se"))
    return summary


def pool_region_summaries(region_summaries: dict[str, dict]) -> dict:
    """Fixed-effect inverse-variance combination of independently-HAC-estimated
    regional means -- reused off-the-shelf statistics, not a method invented
    for this study.

    A single re-run of `kelly_portfolio._newey_west_stats` on a naively
    concatenated two-region series was considered and rejected: two regions
    can share a calendar date, and `_sampling_step_days` filters non-positive
    gaps when estimating the HAC step, so a same-day cross-region pair would
    be silently dropped from the LAG estimate while both rows still count in
    the VARIANCE term -- a mismatch between what the lag describes and what
    the sample contains. Inverse-variance pooling combines the two regions'
    own already-computed mean/SE pairs, each estimated entirely within its
    own region, so no cross-section is ever merged across KR/US -- only the
    two summary numbers are.
    """
    usable = [(row["mean"], row["se"]) for row in region_summaries.values()
              if row.get("mean") is not None and row.get("se") is not None]
    if not usable:
        return {"mean": None, "se": None, "ci95": None,
                "method": "INVERSE_VARIANCE_FIXED_EFFECT", "regionsUsed": 0}
    # A region whose IC series happens to have zero sampling variance (every
    # cross-section agreed exactly) is INFINITELY informative under inverse-
    # variance weighting, not uninformative: its own mean is reported as the
    # pooled answer rather than silently dropped for having a falsy `se`.
    zero_se = [(m, se) for m, se in usable if se == 0]
    if zero_se:
        mean = zero_se[0][0]
        return {"mean": round(mean, 6), "se": 0.0, "ci95": [round(mean, 6), round(mean, 6)],
                "rawPValue": None, "method": "INVERSE_VARIANCE_FIXED_EFFECT",
                "regionsUsed": len(zero_se)}
    weights = [1.0 / (se ** 2) for _, se in usable]
    total_w = sum(weights)
    mean = sum(m * w for (m, _), w in zip(usable, weights, strict=True)) / total_w
    se = math.sqrt(1.0 / total_w)
    p = _p_value(mean, se)
    return {
        "mean": round(mean, 6), "se": round(se, 6),
        "ci95": [round(mean - 1.96 * se, 6), round(mean + 1.96 * se, 6)],
        "rawPValue": round(p, 6) if p is not None else None,
        "method": "INVERSE_VARIANCE_FIXED_EFFECT", "regionsUsed": len(usable),
    }


def sleeve_ic_table(frame: pd.DataFrame, horizon: int, *, column_map=None) -> dict:
    """Per-region and pooled Rank IC summary for every sleeve at one horizon.

    `column_map` lets the same function score an alternate column (e.g. a
    raw subfactor) under a sleeve's name; default is the sleeve's own
    stored percentile column.
    """
    column_map = column_map or {sleeve: sleeve for sleeve in SLEEVES}
    regions = sorted(frame["region"].dropna().unique())
    out: dict[str, dict] = {}
    for sleeve, column in column_map.items():
        by_region: dict[str, dict] = {}
        for region in regions:
            series = standalone_ic_series(frame, region, column)
            by_region[region] = _with_se_and_p(PV._nw_summary(series, horizon))
        pooled = pool_region_summaries(by_region)
        out[sleeve] = {"byRegion": by_region, "pooled": pooled}
    return out


def holm_bonferroni(pvalues: dict[str, float | None]) -> dict[str, float | None]:
    """Standard Holm step-down adjustment over the primary confirmatory
    family. Never applied to subfactor / secondary-horizon readings."""
    items = sorted(((k, v) for k, v in pvalues.items() if v is not None),
                   key=lambda kv: kv[1])
    m = len(items)
    adjusted: dict[str, float | None] = dict.fromkeys(pvalues, None)
    running_max = 0.0
    for i, (key, p) in enumerate(items):
        running_max = max(running_max, min(1.0, (m - i) * p))
        adjusted[key] = round(running_max, 6)
    return adjusted


# --------------------------------------------------------------------------- #
# Secondary: quartile spread, quintile monotonicity, redundancy, incremental
# IC -- computed in one pass per region to avoid re-grouping the frame
# --------------------------------------------------------------------------- #
def cross_section_pass(frame: pd.DataFrame, region: str) -> dict:
    """One pass over `region`'s own date cross-sections, collecting the raw
    per-date artifacts every secondary diagnostic aggregates from."""
    part = frame[frame["region"] == region]
    corr_frames: list[pd.DataFrame] = []
    incremental_rows: dict[str, list[tuple]] = {sleeve: [] for sleeve in SLEEVES}
    quartile_rows: dict[str, list[tuple]] = {sleeve: [] for sleeve in SLEEVES}
    quintile_means: dict[str, list[list[float]]] = {
        sleeve: [[] for _ in range(5)] for sleeve in SLEEVES}

    for date, group in part.groupby("date", sort=True):
        redund = group.dropna(subset=list(SLEEVES))
        if len(redund) >= MIN_NAMES_IC:
            corr_frames.append(redund[list(SLEEVES)].corr(method="spearman"))

        inc = group.dropna(subset=[*SLEEVES, "excessReturn"])
        if len(inc) >= MIN_NAMES_INCREMENTAL:
            values = inc[list(SLEEVES)].to_numpy(dtype=float)
            excess = inc["excessReturn"].to_numpy(dtype=float)
            for i, sleeve in enumerate(SLEEVES):
                others = [j for j in range(4) if j != i]
                design = np.column_stack([np.ones(len(inc)), values[:, others]])
                target = values[:, i]
                coef, *_ = np.linalg.lstsq(design, target, rcond=None)
                residual = target - design @ coef
                if np.std(residual) > 1e-12:
                    ic = pd.Series(residual).corr(pd.Series(excess), method="spearman")
                    if pd.notna(ic):
                        incremental_rows[sleeve].append((date, float(ic)))

        for sleeve in SLEEVES:
            qs = group.dropna(subset=[sleeve, "excessReturn"])
            if len(qs) >= MIN_NAMES_QUARTILE:
                hi, lo = qs[sleeve].quantile(0.75), qs[sleeve].quantile(0.25)
                top = qs.loc[qs[sleeve] >= hi, "excessReturn"]
                bottom = qs.loc[qs[sleeve] <= lo, "excessReturn"]
                if len(top) and len(bottom):
                    quartile_rows[sleeve].append((date, float(top.mean() - bottom.mean())))
            if len(qs) >= MIN_NAMES_QUINTILE:
                try:
                    bucket = pd.qcut(qs[sleeve], 5, labels=False, duplicates="drop")
                except ValueError:
                    continue
                for b in sorted(pd.unique(bucket.dropna())):
                    b = int(b)
                    if b >= 5:
                        continue
                    selected = qs.loc[bucket == b, "excessReturn"]
                    if len(selected):
                        quintile_means[sleeve][b].append(float(selected.mean()))

    return {
        "corrFrames": corr_frames,
        "incrementalRows": incremental_rows,
        "quartileRows": quartile_rows,
        "quintileMeans": quintile_means,
    }


def redundancy_matrix(corr_frames: list[pd.DataFrame]) -> dict:
    """Time-average the per-date 4x4 sleeve correlation matrices."""
    if not corr_frames:
        return {"available": False}
    per_pair: dict[tuple, list] = defaultdict(list)
    for frame in corr_frames:
        for a in SLEEVES:
            for b in SLEEVES:
                value = frame.loc[a, b] if a in frame.index and b in frame.columns else None
                if value is not None and pd.notna(value):
                    per_pair[(a, b)].append(float(value))
    table = {a: {} for a in SLEEVES}
    for a in SLEEVES:
        for b in SLEEVES:
            values = per_pair.get((a, b)) or []
            table[a][b] = {
                "mean": round(float(np.mean(values)), 4) if values else None,
                "median": round(float(np.median(values)), 4) if values else None,
                "p10": round(float(np.percentile(values, 10)), 4) if values else None,
                "p90": round(float(np.percentile(values, 90)), 4) if values else None,
                "observations": len(values),
            }
    return {"available": True, "matrix": table}


def incremental_ic_table(incremental_rows: dict[str, list[tuple]], horizon: int) -> dict:
    out = {}
    for sleeve, rows in incremental_rows.items():
        series = pd.Series(dict(rows), dtype=float).sort_index() if rows else pd.Series(dtype=float)
        out[sleeve] = _with_se_and_p(PV._nw_summary(series, horizon))
    return out


def quartile_spread_table(quartile_rows: dict[str, list[tuple]], horizon: int) -> dict:
    out = {}
    for sleeve, rows in quartile_rows.items():
        series = pd.Series(dict(rows), dtype=float).sort_index() if rows else pd.Series(dtype=float)
        summary = _with_se_and_p(PV._nw_summary(series, horizon))
        summary["hitRatePct"] = (round(float((series > 0).mean() * 100), 2)
                                 if len(series) else None)
        out[sleeve] = summary
    return out


def quintile_monotonicity_table(quintile_means: dict[str, list[list[float]]]) -> dict:
    out = {}
    for sleeve, buckets in quintile_means.items():
        means = [round(float(np.mean(b)), 6) if b else None for b in buckets]
        observations = [len(b) for b in buckets]
        valid = [m for m in means if m is not None]
        mono = None
        if len(valid) >= 2:
            mono = round(sum(b >= a for a, b in zip(valid[:-1], valid[1:], strict=True))
                        / (len(valid) - 1), 3)
        spread = (means[4] - means[0]) if means[0] is not None and means[4] is not None else None
        out[sleeve] = {
            "quintileMeans": means, "observationsPerQuintile": observations,
            "monotonicityScore": mono,
            "q5MinusQ1": round(spread, 6) if spread is not None else None,
        }
    return out


# --------------------------------------------------------------------------- #
# Time stability -- one chronological split fixed on the full sample, never
# tuned per sleeve or region
# --------------------------------------------------------------------------- #
def half_split_dates(frame: pd.DataFrame) -> tuple:
    dates = sorted(frame["date"].dropna().unique())
    if not dates:
        return None, None
    mid = len(dates) // 2
    return dates[:mid], dates[mid:]


def half_sample_ic(frame: pd.DataFrame, region: str, sleeve: str,
                   first_dates, second_dates, horizon: int) -> dict:
    first = frame[frame["date"].isin(first_dates)]
    second = frame[frame["date"].isin(second_dates)]
    return {
        "firstHalf": PV._nw_summary(standalone_ic_series(first, region, sleeve), horizon),
        "secondHalf": PV._nw_summary(standalone_ic_series(second, region, sleeve), horizon),
    }


def _sign(mean) -> str | None:
    if mean is None:
        return None
    if mean > 0:
        return "POSITIVE"
    if mean < 0:
        return "NEGATIVE"
    return "ZERO"


# --------------------------------------------------------------------------- #
# Section 15 classification -- descriptive, never a deletion recommendation
# --------------------------------------------------------------------------- #
def classify_sleeve(*, standalone_pooled: dict, incremental_pooled: dict,
                    region_signs: list[str | None], half_signs: list[str | None]) -> dict:
    """Map one sleeve's measured evidence onto the four pre-specified cases.

    Never recommends deleting a sleeve (section 15's own instruction); the
    classification is descriptive and the caller must read the rationale
    alongside it, not the label alone.
    """
    standalone_sign = _sign(standalone_pooled.get("mean"))
    incremental_sign = _sign(incremental_pooled.get("mean"))
    region_agree = len(set(s for s in region_signs if s)) <= 1 and any(region_signs)
    half_agree = len(set(s for s in half_signs if s)) <= 1 and any(half_signs)

    standalone_mag = abs(standalone_pooled.get("mean") or 0.0)
    incremental_mag = abs(incremental_pooled.get("mean") or 0.0)
    incremental_near_zero = incremental_mag < max(0.2 * standalone_mag, 1e-6)

    if not region_agree or not half_agree:
        case = "D_UNSTABLE_REGIME_DEPENDENT"
        rationale = ("Sign disagrees across KR/US and/or first/second half; recorded as "
                     "possibly conditional, not classified as independent or redundant.")
    elif standalone_sign == "POSITIVE" and incremental_sign == "POSITIVE" and not incremental_near_zero:
        case = "A_INDEPENDENT_USEFUL_SIGNAL"
        rationale = "Standalone and incremental IC both positive, with region/time sign agreement."
    elif standalone_sign == "POSITIVE" and incremental_near_zero:
        case = "B_REDUNDANT_SIGNAL"
        rationale = ("Standalone IC positive but incremental IC collapses toward zero once the "
                     "other three sleeves are controlled for -- the other sleeves already carry "
                     "this information.")
    elif standalone_sign == "NEGATIVE" and incremental_sign == "NEGATIVE":
        case = "C_POTENTIALLY_HARMFUL_WRONG_SIGN"
        rationale = ("Standalone and incremental IC both negative and the sign persists across "
                     "region/time -- reported as a finding, NOT a recommendation to remove the "
                     "sleeve, which needs an independent sample to confirm.")
    else:
        case = "D_UNSTABLE_REGIME_DEPENDENT"
        rationale = "Standalone/incremental signs disagree or evidence is otherwise mixed."
    return {"case": case, "rationale": rationale, "standaloneSign": standalone_sign,
            "incrementalSign": incremental_sign, "regionSignsAgree": region_agree,
            "halfSignsAgree": half_agree}


# --------------------------------------------------------------------------- #
# EvidenceCoverage audit -- descriptive, never a primary confirmatory claim
# --------------------------------------------------------------------------- #
def evidence_coverage_audit(frame: pd.DataFrame) -> dict:
    work = frame.dropna(subset=["rawAlpha", "alpha", "evidenceCoverage"])
    rank_corr = []
    for date, group in work.groupby(["date", "region"]):
        usable = group.dropna(subset=["rawAlpha", "alpha"])
        if len(usable) >= MIN_NAMES_IC:
            ic = usable["rawAlpha"].corr(usable["alpha"], method="spearman")
            if pd.notna(ic):
                rank_corr.append(float(ic))
    coverage = frame["evidenceCoverage"].dropna()
    low_high_vol = {}
    covered = frame.dropna(subset=["evidenceCoverage", "excessReturn"])
    if len(covered) >= 20:
        quartiles = pd.qcut(covered["evidenceCoverage"], 4, labels=False, duplicates="drop")
        for q in sorted(pd.unique(quartiles.dropna())):
            sel = covered.loc[quartiles == q, "excessReturn"]
            low_high_vol[f"q{int(q) + 1}"] = {
                "meanEvidenceCoverage": round(
                    float(covered.loc[quartiles == q, "evidenceCoverage"].mean()), 4),
                "excessReturnSd": round(float(sel.std(ddof=1)), 6) if len(sel) > 1 else None,
                "excessReturnMean": round(float(sel.mean()), 6) if len(sel) else None,
                "observations": int(len(sel)),
            }
    return {
        "rawAlphaVsAlphaRankSpearman": {
            "mean": round(float(np.mean(rank_corr)), 4) if rank_corr else None,
            "observations": len(rank_corr),
        },
        "evidenceCoverageDistribution": {
            "mean": round(float(coverage.mean()), 4) if len(coverage) else None,
            "median": round(float(coverage.median()), 4) if len(coverage) else None,
            "sd": round(float(coverage.std(ddof=1)), 4) if len(coverage) > 1 else None,
            "p10": round(float(coverage.quantile(.1)), 4) if len(coverage) else None,
            "p90": round(float(coverage.quantile(.9)), 4) if len(coverage) else None,
        },
        "byEvidenceCoverageQuartile": low_high_vol,
        "note": ("Descriptive only, NOT part of the primary confirmatory family. "
                 "evidenceCoverage weighting is never changed or removed by this study."),
    }


# --------------------------------------------------------------------------- #
# Missingness / coverage
# --------------------------------------------------------------------------- #
def coverage_report(frame: pd.DataFrame) -> dict:
    out = {}
    for region in sorted(frame["region"].dropna().unique()):
        part = frame[frame["region"] == region]
        out[region] = {
            sleeve: {
                "usableObservations": int(part[sleeve].notna().sum()),
                "totalObservations": int(len(part)),
                "missingRatePct": (round((1 - part[sleeve].notna().mean()) * 100, 3)
                                   if len(part) else None),
            }
            for sleeve in SLEEVES
        }
    return out
