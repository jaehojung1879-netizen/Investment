"""Fixed independent probability/return heads; no search and no production writes."""
from __future__ import annotations

from dataclasses import dataclass
import math
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.exceptions import ConvergenceWarning
from threadpoolctl import threadpool_limits


def date_weights(dates):
    values = pd.Series(dates).reset_index(drop=True)
    if values.isna().any() or values.empty:
        raise ValueError("DATES_REQUIRED")
    return (1.0 / values.groupby(values).transform("size")).to_numpy()


def weighted_quantile(values, weights, q):
    order = np.argsort(values, kind="stable")
    x, w = values[order], weights[order]
    return float(x[min(np.searchsorted(np.cumsum(w), q * w.sum()), len(x)-1)])


@dataclass
class TrainTransformer:
    names: list[str]
    log_features: tuple[str, ...] = ()

    def raw(self, frame):
        data = frame.reindex(columns=self.names).apply(pd.to_numeric, errors="coerce").to_numpy(float)
        data[~np.isfinite(data)] = np.nan
        for j, name in enumerate(self.names):
            if name in self.log_features:
                data[:, j] = np.sign(data[:, j]) * np.log1p(np.abs(data[:, j]))
        return data

    def fit(self, frame, weights):
        data = self.raw(frame)
        self.active = np.isfinite(data).any(axis=0)
        if not self.active.any():
            raise ValueError("DATA_INSUFFICIENT_ALL_FEATURES_MISSING")
        self.omitted = [name for name, active in zip(self.names, self.active) if not active]
        self.center, self.scale = [], []
        for values in data[:, self.active].T:
            ok = np.isfinite(values)
            quantiles = [weighted_quantile(values[ok], weights[ok], q) for q in (.25, .5, .75)]
            self.center.append(quantiles[1])
            self.scale.append(quantiles[2] - quantiles[0] or 1.0)
        return self

    def transform(self, frame):
        data = self.raw(frame)[:, self.active]
        missing = ~np.isfinite(data)
        filled = np.where(missing, np.asarray(self.center), data)
        return np.column_stack(((filled - self.center) / self.scale, missing.astype(float)))


def folds(frame, schedule, spec):
    """Expanding annual folds anchored on the SCHEDULE, never on label coverage."""
    if frame.region.nunique() != 1:
        raise ValueError("REGIONS_MUST_BE_SEPARATE")
    dates = pd.to_datetime(frame.date)
    ends = pd.to_datetime(frame.outcomeEndDate)
    start = pd.Timestamp(spec["walkForward"]["featureStart"])
    for year in sorted({pd.Timestamp(d).year for d in schedule}):
        year_dates = [d for d in schedule if pd.Timestamp(d).year == year]
        cutoff = pd.Timestamp(min(year_dates))
        if cutoff < start + pd.DateOffset(months=spec["walkForward"]["minimumHistoryMonths"]):
            continue
        train = frame.loc[(dates < cutoff) & (ends < cutoff) & frame.labelStatus.eq("MATURED")].copy()
        counts = train.groupby("date").size()
        eligible_dates = counts[counts >= spec["walkForward"]["minimumNamesPerDate"]].index
        train = train.loc[train.date.isin(eligible_dates)]
        test = frame.loc[frame.date.isin(year_dates)].copy()
        reason = None
        if train.date.nunique() < spec["walkForward"]["minimumMaturedDates"]:
            reason = "DATA_INSUFFICIENT_TRAINING_DATES"
        elif train.beatBenchmark.nunique() < 2:
            reason = "DATA_INSUFFICIENT_ONE_CLASS"
        yield {"trainingRows": len(train), "trainingDates": train.date.nunique(),
               "validationRows": len(test),
               "excludedTrainingRows": int(((dates < cutoff) & (ends < cutoff)).sum())-len(train),
               "year": year, "cutoff": str(cutoff.date()), "train": train,
               "validation": test, "status": reason or "READY"}


def estimator_pair(family, spec):
    cfg = spec["models"]
    if family == "LINEAR":
        return LogisticRegression(**cfg["logistic"]), Ridge(**cfg["ridge"])
    if family == "SHALLOW_CHALLENGER":
        return (HistGradientBoostingClassifier(**cfg["histGradientBoosting"]),
                HistGradientBoostingRegressor(**cfg["histGradientBoosting"]))
    raise ValueError("UNREGISTERED_MODEL_FAMILY")


def fit_heads(train, validation, names, family, spec):
    if train.empty or validation.empty or train.region.nunique() != 1 or validation.region.nunique() != 1:
        raise ValueError("EMPTY_OR_MIXED_REGION")
    if train.region.iloc[0] != validation.region.iloc[0]:
        raise ValueError("REGION_MISMATCH")
    if pd.to_datetime(train.outcomeEndDate).max() >= pd.to_datetime(validation.date).min():
        raise ValueError("LABEL_NOT_MATURE_BEFORE_VALIDATION")
    if train.beatBenchmark.nunique() != 2:
        raise ValueError("DATA_INSUFFICIENT_ONE_CLASS")
    weights = date_weights(train.date)
    transformer = TrainTransformer(names, tuple(spec["transforms"]["signedLog1p"]))
    transformer.fit(train, weights)
    x, v = transformer.transform(train), transformer.transform(validation)
    probability, regression = estimator_pair(family, spec)
    with threadpool_limits(limits=1), warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)
        probability.fit(x, train.beatBenchmark.to_numpy(int), sample_weight=weights)
        regression.fit(x, train.forwardRelativeReturn.to_numpy(float), sample_weight=weights)
        p = probability.predict_proba(v)[:, 1]
        mu = regression.predict(v)
    if not np.isfinite(p).all() or not np.isfinite(mu).all():
        raise FloatingPointError("MODEL_UNSTABLE_NONFINITE")
    return {"probability": p, "expectedRelativeReturn": mu,
            "trainingBaseRate": np.average(train.beatBenchmark, weights=weights),
            "trainingMeanReturn": np.average(train.forwardRelativeReturn, weights=weights),
            "omittedFeatures": transformer.omitted}


def block_sample_indices(n_dates, block_length, rng):
    """Moving-block resample, never iid name rows. Retain complete date clusters."""
    if n_dates < block_length:
        raise ValueError("DATA_INSUFFICIENT_BLOCKS")
    starts = rng.integers(0, n_dates-block_length+1, size=math.ceil(n_dates/block_length))
    return np.concatenate([np.arange(s, s+block_length) for s in starts])[:n_dates]


def prediction_uncertainty(train, validation, names, spec):
    cfg = spec["uncertainty"]
    dates = sorted(train.date.unique())
    if len(dates) < cfg["minimumTrainingBlocks"] * cfg["blockDates"]:
        return {"status": "DATA_INSUFFICIENT_UNCERTAINTY"}
    rng = np.random.default_rng(cfg["seed"])
    probability, returns = [], []
    for _ in range(cfg["replicates"]):
        draws = block_sample_indices(len(dates), cfg["blockDates"], rng)
        chunks = []
        # Repeated dates are separate bootstrap clusters with the same total weight.
        for j, index in enumerate(draws):
            group = train.loc[train.date.eq(dates[index])].copy()
            group["bootstrapDate"] = j
            chunks.append(group)
        boot = pd.concat(chunks, ignore_index=True)
        if boot.beatBenchmark.nunique() < 2:
            return {"status": "MODEL_UNSTABLE_BOOTSTRAP_ONE_CLASS"}
        weights = date_weights(boot.bootstrapDate)
        transformer = TrainTransformer(names, tuple(spec["transforms"]["signedLog1p"]))
        transformer.fit(boot, weights)
        p, m = estimator_pair("LINEAR", spec)
        with threadpool_limits(limits=1), warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            x, v = transformer.transform(boot), transformer.transform(validation)
            p.fit(x, boot.beatBenchmark.astype(int), sample_weight=weights)
            m.fit(x, boot.forwardRelativeReturn, sample_weight=weights)
            probability.append(p.predict_proba(v)[:, 1])
            returns.append(m.predict(v))
    tail = cfg["lowerQuantile"]
    return {"status": "MEASURED", "probabilityLower": np.quantile(probability, tail, axis=0),
            "probabilityUpper": np.quantile(probability, 1-tail, axis=0),
            "meanLower": np.quantile(returns, tail, axis=0),
            "meanUpper": np.quantile(returns, 1-tail, axis=0),
            "meanStd": np.std(returns, axis=0, ddof=1)}


def opportunity_gate(mu, lower, cost, residual_scale, adv, spec):
    """Economic admissibility, never a target count or a percentile."""
    cfg = spec["investability"]
    required = ("minimumEdge", "concentrationRiskMultiple", "tradeNotional",
                "maximumAdvFraction", "minimumAdv", "slippageBps")
    if any(cfg.get(key) is None for key in required):
        return {"status": "BLOCKED_PREREGISTRATION", "passes": None}
    if not np.isfinite([mu, lower, cost, residual_scale, adv]).all():
        return {"status": "DATA_INSUFFICIENT", "passes": None}
    uncertainty = max(0.0, mu - lower)
    hurdle = (cost + cfg["slippageBps"]/10000 + uncertainty + cfg["minimumEdge"]
              + cfg["concentrationRiskMultiple"] * residual_scale)
    capacity = adv >= cfg["minimumAdv"] and cfg["tradeNotional"] <= cfg["maximumAdvFraction"] * adv
    return {"status": "EVALUATED", "passes": bool(capacity and mu > hurdle),
            "uncertaintyMargin": uncertainty, "economicHurdle": hurdle}


def matured_residual_scale(previous_predictions, cutoff, minimum_dates=26):
    """Past out-of-fold errors only; never in-sample fit errors or future folds."""
    if previous_predictions.empty:
        return None
    data = previous_predictions.loc[
        previous_predictions.outcomeEndDate.lt(cutoff)
        & previous_predictions.date.lt(cutoff)
        & previous_predictions.labelStatus.eq("MATURED")]
    if data.date.nunique() < minimum_dates:
        return None
    error = data.forwardRelativeReturn - data.expectedRelativeReturn
    if not np.isfinite(error).all():
        return None
    return float(np.sqrt(np.average(error**2, weights=date_weights(data.date))))


def dated_round_trip_cost(region, date, spec):
    from .portfolio_validation import _dated_cost_policy
    policy = _dated_cost_policy(spec["transactionCosts"][region], date)
    return (2*policy["commissionBps"] + policy["spreadBps"] + policy["sellTaxBps"])/10000
