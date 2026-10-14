"""How much of each US characteristic's cross-sectional ORDERING is not already carried by sector and the other families.

Outcome-blind. Nothing here reads a forward price, return, label, NAV or model output: the inputs are signal-date feature values that
`scripts/audit_us_factor_unique_variation.py` builds with the existing Phase 3 / multifactor feature paths. The statistics answer
"is there distinct characteristic variation left to test?", never "does it predict?". A feature whose rank is 90% explained by its
controls can still predict, and one that is fully unique can be noise.

Definitions, fixed before any data was read (`FAMILIES`, `REPRESENTATIVES`, `ATTRITION_ORDER`):
* within one date, every statistic is computed on the complete cases of the feature, the controls and a sector label;
* values become within-date percentile ranks (average ties) inside that complete-case set, so a monotone transform of a feature
  changes nothing;
* `controlR2` is the OLS R^2 of the feature's rank on sector dummies plus the ranks of one representative of every OTHER family;
  `uniqueShare = 1 - controlR2`. `sectorR2` uses sector dummies alone on the same rows; `ownFamilyR2` uses the ranks of the other
  members of the feature's own family, without sector, and measures within-family duplication;
* a date contributes only with at least `MIN_NAMES` complete cases; dates are equally weighted;
* `noiseFloorR2` = k / (n - 1), the expected R^2 of k regressors that carry nothing (k = control ranks + sector dummies), averaged
  over the same dates. A controlR2 near it means the controls carry essentially none of the feature's ordering.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CONTRACT = "US_FACTOR_UNIQUE_VARIATION_V1"
MIN_NAMES = 100

FAMILIES = {
    "MOMENTUM_TREND": ("mom121", "relative126", "high52Distance", "relativeStrengthBreadth52w"),
    "RISK": ("vol252", "downsideVol252", "beta252", "maxDD252"),
    "SIZE_LIQUIDITY": ("logTradedValue63", "logMarketCapProxy"),
    "PROFITABILITY_ACCRUAL": ("operatingProfitabilityToAssets", "roe", "operatingMargin", "profitMargin"),
    "CASH_QUALITY": ("cashOperatingProfitability", "accrualsToAssets"),
    "VALUE_RECONSTRUCTED_PRICE": ("earningsYield", "bookYield", "fcfYield"),
    "LEVERAGE": ("debtToEquity",),
    "GROWTH_CHANGE": ("earningsGrowth", "revenueGrowthTTM", "delta_roe", "delta_operatingMargin"),
    "INVESTMENT": ("assetGrowthPct", "capexIntensityPct"),
}
# One representative per family is the control for every feature OUTSIDE that family. Chosen on economic grounds and data lineage,
# not on coverage or on anything measured here: the sealed or primary field of each family. The market-cap proxy rests on an
# unverified share-count basis and is never a control (traded value is).
REPRESENTATIVES = {
    "MOMENTUM_TREND": "mom121",
    "RISK": "vol252",
    "SIZE_LIQUIDITY": "logTradedValue63",
    "PROFITABILITY_ACCRUAL": "operatingProfitabilityToAssets",
    "CASH_QUALITY": "cashOperatingProfitability",
    "VALUE_RECONSTRUCTED_PRICE": "earningsYield",
    "LEVERAGE": "debtToEquity",
    "GROWTH_CHANGE": "earningsGrowth",
    "INVESTMENT": "assetGrowthPct",
}
# Order in which families are required jointly in the attrition table: price-only first (no filing needed), then the families
# a first multifactor comparison would need, then the reconstructed-price value family, whose basis is the least verified.
ATTRITION_ORDER = ("MOMENTUM_TREND", "RISK", "SIZE_LIQUIDITY", "PROFITABILITY_ACCRUAL", "CASH_QUALITY", "LEVERAGE",
                   "GROWTH_CHANGE", "INVESTMENT", "VALUE_RECONSTRUCTED_PRICE")

FAMILY_OF = {f: fam for fam, members in FAMILIES.items() for f in members}
FEATURES = tuple(FAMILY_OF)


def finite(value) -> bool:
    return value is not None and isinstance(value, (int, float, np.floating, np.integer)) and bool(np.isfinite(value))


def controls_for(feature: str) -> tuple[str, ...]:
    own = FAMILY_OF[feature]
    return tuple(rep for fam, rep in REPRESENTATIVES.items() if fam != own)


def complete_cases(g: pd.DataFrame, cols) -> pd.DataFrame:
    """Rows where every column in `cols` is a finite number (an empty frame keeps its columns)."""
    mask = np.ones(len(g), dtype=bool)
    for c in cols:
        mask &= np.fromiter((finite(v) for v in g[c]), dtype=bool, count=len(g))
    return g.loc[mask, list(cols) + ["sector"]]


def _r2(y: np.ndarray, x: np.ndarray) -> float | None:
    """OLS R^2 with an intercept; `x` may have zero columns (then R^2 is 0)."""
    total = float(((y - y.mean()) ** 2).sum())
    if total <= 0:
        return None
    design = np.column_stack([np.ones(len(y)), x]) if x.size else np.ones((len(y), 1))
    beta, *_ = np.linalg.lstsq(design, y, rcond=None)
    resid = y - design @ beta
    return max(0.0, min(1.0, 1.0 - float((resid ** 2).sum()) / total))


def _sector_dummies(sectors: pd.Series) -> np.ndarray:
    dummies = pd.get_dummies(sectors.astype(str), drop_first=True, dtype=float)
    return dummies.to_numpy() if dummies.shape[1] else np.empty((len(sectors), 0))


def date_r2(g: pd.DataFrame, feature: str, controls: tuple[str, ...], *, sector: bool) -> tuple[float | None, int]:
    r2, n, _ = date_r2_with_dof(g, feature, controls, sector=sector)
    return r2, n


def date_r2_with_dof(g: pd.DataFrame, feature: str, controls: tuple[str, ...], *, sector: bool) -> tuple[float | None, int, int]:
    """R^2 of the feature's within-date rank on (sector dummies +) control ranks, over the complete cases of all of them."""
    cols = [feature, *controls]
    rows = complete_cases(g, cols)
    if len(rows) < MIN_NAMES or rows[feature].astype(float).nunique() <= 2:
        return None, len(rows), 0
    ranks = rows[cols].astype(float).rank(pct=True)
    parts = [ranks[list(controls)].to_numpy()] if controls else []
    if sector:
        parts.append(_sector_dummies(rows["sector"]))
    x = np.column_stack(parts) if parts else np.empty((len(rows), 0))
    return _r2(ranks[feature].to_numpy(), x), len(rows), int(x.shape[1])


def _summary(values: list[float], names: list[int]) -> dict | None:
    if not values:
        return None
    a = np.array(values)
    return {"mean": round(float(a.mean()), 3), "p10": round(float(np.quantile(a, .1)), 3), "p90": round(float(np.quantile(a, .9)), 3),
            "dates": len(a), "medianNamesPerDate": float(np.median(names))}


def unique_variation(frame: pd.DataFrame) -> dict:
    """Per feature: sector-only, control and own-family R^2 of its within-date rank, averaged over dates."""
    out = {}
    for feature in FEATURES:
        controls = controls_for(feature)
        own = tuple(m for m in FAMILIES[FAMILY_OF[feature]] if m != feature and m != "logMarketCapProxy")
        acc = {"control": ([], []), "sectorSameRows": ([], []), "ownFamily": ([], [])}
        floors = []
        for _, g in frame.groupby("date"):
            r2, n, k = date_r2_with_dof(g, feature, controls, sector=True)
            if r2 is None:
                continue
            floors.append(k / (n - 1))
            acc["control"][0].append(r2)
            acc["control"][1].append(n)
            # sector alone on exactly the rows the control regression used
            rows = complete_cases(g, [feature, *controls])
            s2, _ = date_r2(rows, feature, (), sector=True)
            if s2 is not None:
                acc["sectorSameRows"][0].append(s2)
                acc["sectorSameRows"][1].append(n)
            if own:
                o2, on = date_r2(g, feature, own, sector=False)
                if o2 is not None:
                    acc["ownFamily"][0].append(o2)
                    acc["ownFamily"][1].append(on)
        control = _summary(*acc["control"])
        out[feature] = {
            "family": FAMILY_OF[feature], "controls": list(controls), "ownFamilyPeers": list(own),
            "controlR2": control, "uniqueShareMean": round(1.0 - control["mean"], 3) if control else None,
            "noiseFloorR2": round(float(np.mean(floors)), 3) if floors else None,
            "sectorR2SameRows": _summary(*acc["sectorSameRows"]), "ownFamilyR2": _summary(*acc["ownFamily"]),
        }
    return out


def attrition(frame: pd.DataFrame) -> list[dict]:
    """Share of eligible member-dates (and names per date) with every representative up to and including each family."""
    ok = {rep: frame[rep].map(finite).astype(bool) for rep in REPRESENTATIVES.values()}
    mask = pd.Series(True, index=frame.index)
    steps = []
    for fam in ATTRITION_ORDER:
        mask = mask & ok[REPRESENTATIVES[fam]]
        per_date = mask.groupby(frame["date"]).sum()
        by_year = mask.groupby(frame["date"].str[:4]).mean()
        steps.append({"addFamily": fam, "requires": REPRESENTATIVES[fam],
                      "jointPct": round(100.0 * float(mask.mean()), 3) if len(mask) else None,
                      "namesPerDate": {"median": float(per_date.median()), "min": int(per_date.min()),
                                       "datesBelow100": int((per_date < 100).sum()), "dates": int(len(per_date))},
                      "jointPctByYear": {y: round(100.0 * float(v), 1) for y, v in by_year.items()}})
    return steps


def availability(frame: pd.DataFrame) -> dict:
    """Marginal availability of every feature on the eligible rows, overall and by year."""
    years = frame["date"].str[:4]
    out = {}
    for feature in FEATURES:
        have = frame[feature].map(finite).astype(bool)
        out[feature] = {"pct": round(100.0 * float(have.mean()), 3),
                        "byYear": {y: round(100.0 * float(v), 1) for y, v in have.groupby(years).mean().items()}}
    return out


def stale_threshold_sensitivity(report_age_days: pd.Series, available: pd.Series, thresholds=(90, 120, 150, 180)) -> dict:
    """Availability a feature would have if its stale rule were tighter, holding every other reason fixed.

    `available` is the feature's availability under the production 180-day rule; tightening can only remove rows, never add them.
    """
    n = len(available)
    out = {}
    for t in thresholds:
        kept = available & report_age_days.le(t).fillna(False)
        out[str(t)] = round(100.0 * float(kept.sum()) / n, 3) if n else None
    return out


def snapshot_age(dates: list[str], snapshot_dates: list[str | None]) -> dict:
    """Age in calendar days of the membership snapshot each weekly signal date resolves to."""
    ages = [(np.datetime64(d) - np.datetime64(s)).astype("timedelta64[D]").astype(int) for d, s in zip(dates, snapshot_dates) if s]
    a = np.array(ages)
    return {"weeks": len(dates), "weeksWithoutSnapshot": sum(1 for s in snapshot_dates if not s),
            "medianDays": float(np.median(a)), "p90Days": float(np.quantile(a, .9)), "maxDays": int(a.max()),
            **{"weeksOver%dDays" % t: int((a > t).sum()) for t in (45, 90, 180, 365)}}
