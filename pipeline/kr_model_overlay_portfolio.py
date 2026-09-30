"""Frozen conservative model; training-only family interactions, annual chronology."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from threadpoolctl import threadpool_limits

from .alpha_opportunity_model import TrainTransformer, date_weights, weighted_quantile
from .kr_value_quality_catalyst import FAMILIES, RAW_FEATURES

INTERACTIONS = ("VALUE_X_QUALITY", "VALUE_X_CATALYST", "QUALITY_X_CATALYST", "VALUE_X_QUALITY_X_CATALYST")


def weekly_dates(start, through):
    """Same regional weekly grid as prior studies; independent of price availability."""
    from .regional_alpha_features import weekly_grid
    return weekly_grid(start, through, "KR")


class FamilyTransformer:
    def fit(self, train, weights):
        self.raw = TrainTransformer(list(RAW_FEATURES), tuple(
            n for n in RAW_FEATURES if n not in ("logAdv60", "relative126", "momentum121")))
        self.raw.fit(train, weights)
        self.active_names = [n for n in RAW_FEATURES if n not in self.raw.omitted]
        if any(not set(names) & set(self.active_names) for names in FAMILIES.values()):
            raise ValueError("MISSING_ENTIRE_TRAINING_FAMILY")
        raw_x = self.raw.transform(train)
        interaction = self.interactions(self.scores(raw_x))
        center, scale = [], []
        for values in interaction.T:
            qs = [weighted_quantile(values, weights, q) for q in (.25, .5, .75)]
            center.append(qs[1])
            scale.append(qs[2] - qs[0] or 1.0)
        self.center, self.scale = np.asarray(center), np.asarray(scale)
        return self

    def scores(self, x):
        # Each available constituent has equal orientation-adjusted contribution;
        # median-imputed missing raw observations contribute zero standardized value.
        return {family: x[:, [self.active_names.index(n) for n in names if n in self.active_names]].mean(axis=1)
                for family, names in FAMILIES.items()}

    @staticmethod
    def interactions(scores):
        # Positive parts: low-value x low-quality must NOT masquerade as cheap AND good.
        v, q, c = (np.maximum(scores[f], 0) for f in ("VALUE", "QUALITY", "CATALYST"))
        return np.column_stack((v*q, v*c, q*c, v*q*c))

    def transform(self, frame):
        x = self.raw.transform(frame)
        scores = self.scores(x)
        interactions = (self.interactions(scores) - self.center) / self.scale
        return np.column_stack((x, interactions)), scores

    @property
    def columns(self):
        return self.active_names + [n + "_missing" for n in self.active_names] + list(INTERACTIONS)


def fit_predict(train, valid, spec, *, challenger=False):
    """Authorized caller owns counters; this function only accepts a matured fold."""
    if train.empty or valid.empty or train.region.unique().tolist() != ["KR"] or valid.region.unique().tolist() != ["KR"]:
        raise ValueError("EMPTY_OR_NON_KR_MODEL_DATA")
    if pd.to_datetime(train.outcomeEndDate).max() >= pd.to_datetime(valid.date).min():
        raise ValueError("TRAINING_ENDPOINT_NOT_STRICTLY_MATURED")
    if set(train.labelStatus) != {"MATURED"}:
        raise ValueError("UNMATURED_TRAINING_LABEL")
    train = train.sort_values(["date", "ticker"]).reset_index(drop=True)
    valid = valid.sort_values(["date", "ticker"]).reset_index(drop=True)
    w = date_weights(train.date)
    transform = FamilyTransformer().fit(train, w)
    x, _ = transform.transform(train)
    z, scores = transform.transform(valid)
    estimator = (HistGradientBoostingRegressor(**spec["model"]["challenger"])
                 if challenger else Ridge(**spec["model"]["ridge"]))
    with threadpool_limits(limits=1):
        estimator.fit(x, train.forwardRelativeReturn.to_numpy(float), sample_weight=w)
        prediction = estimator.predict(z)
    if not np.isfinite(prediction).all():
        raise ValueError("NONFINITE_PREDICTIONS")
    out = valid[["date", "ticker", "region"]].copy()
    for name, output_name in (("sourceFlags", "sourceQualityFlags"), ("missingFeatures", "missingnessFlags")):
        if name in valid:
            out[output_name] = valid[name].tolist()
    out["investabilityFlags"] = [{"tradable": bool(r.get("tradable", False)), "adv60": r.get("adv60"),
                                  "downsideVol126": r.get("downsideVol126")}
                                 for r in valid.to_dict("records")]
    out["prediction"] = prediction
    for family, value in scores.items():
        out[family + "_SCORE"] = value
    out["rank"] = out.groupby("date").prediction.rank(method="first", ascending=False).astype(int)
    contributions = None
    if not challenger:
        contributions = z * estimator.coef_
        if not np.allclose(estimator.intercept_ + contributions.sum(axis=1), prediction, rtol=0, atol=1e-9):
            raise ValueError("LINEAR_DECOMPOSITION_MISMATCH")
        out["interactionContributions"] = [{name: float(v) for name, v in zip(INTERACTIONS, row[-4:])}
                                            for row in contributions]
    return {"predictions": out, "transformer": transform, "estimator": estimator,
            "contributions": contributions, "columns": transform.columns,
            "omittedFeatures": transform.raw.omitted}


def folds(data, schedule, spec):
    cfg = spec["walkForward"]
    dates = pd.to_datetime(data.date)
    ends = pd.to_datetime(data.outcomeEndDate)
    for year in sorted({pd.Timestamp(d).year for d in schedule}):
        scheduled = [d for d in schedule if pd.Timestamp(d).year == year]
        cutoff = min(scheduled)
        if pd.Timestamp(cutoff) < pd.Timestamp(cfg["featureStart"]) + pd.DateOffset(months=cfg["minimumHistoryMonths"]):
            continue
        train = data.loc[(dates < pd.Timestamp(cutoff)) & (ends < pd.Timestamp(cutoff)) & data.labelStatus.eq("MATURED")]
        counts = train.groupby("date").size()
        train = train.loc[train.date.isin(counts[counts >= cfg["minimumNamesPerDate"]].index)]
        valid = data.loc[data.date.isin(scheduled)]
        ready = train.date.nunique() >= cfg["minimumMaturedDates"] and not valid.empty
        yield {"cutoff": cutoff, "year": year, "train": train, "valid": valid,
               "status": "READY" if ready else "DATA_INSUFFICIENT"}
