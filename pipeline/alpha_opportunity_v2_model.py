"""v1's frozen model family, pointed at the v2 net-of-cost targets. Research only.

No estimator, hyperparameter, transform or bootstrap setting changes from v1.
Two things change, both forced by the decision contract rather than chosen:

* the probability head is trained on the NET event `beatBenchmarkNet`
  (R_i - R_b > round-trip cost at the signal date), because the benchmark
  competes for the capital net of the cost of leaving it;
* the uncertainty bootstrap is the same statistic as v1's
  `prediction_uncertainty` (same seed, same moving blocks of whole dates,
  same cluster weights, same 5th/95th quantiles) computed from precomputed
  date indices, so it can finish inside a hosted runner's time limit.
  `tests/test_alpha_opportunity_v2.py` proves the two agree exactly.
"""
from __future__ import annotations

import warnings

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from threadpoolctl import threadpool_limits

from . import alpha_opportunity_model as V1


def as_v1_target(frame):
    """v1's fitting code reads `beatBenchmark`; v2 hands it the NET label."""
    if "beatBenchmarkNet" not in frame:
        raise ValueError("NET_LABEL_REQUIRED")
    out = frame.copy()
    out["beatBenchmark"] = out["beatBenchmarkNet"]
    return out


def fit_heads(train, validation, names, family, spec):
    return V1.fit_heads(as_v1_target(train), validation, names, family, spec)


def prediction_uncertainty(train, validation, names, spec):
    """Training-only moving-block refits of the LINEAR heads (v1 semantics)."""
    cfg = spec["uncertainty"]
    train = as_v1_target(train).reset_index(drop=True)
    dates = sorted(train.date.unique())
    if len(dates) < cfg["minimumTrainingBlocks"] * cfg["blockDates"]:
        return {"status": "DATA_INSUFFICIENT_UNCERTAINTY"}
    positions = train.groupby("date").indices
    by_date = [np.asarray(positions[d]) for d in dates]
    rng = np.random.default_rng(cfg["seed"])
    probability, returns = [], []
    logs = tuple(spec["transforms"]["signedLog1p"])
    for _ in range(cfg["replicates"]):
        draws = V1.block_sample_indices(len(dates), cfg["blockDates"], rng)
        parts = [by_date[i] for i in draws]
        boot = train.iloc[np.concatenate(parts)].copy()
        # Repeated dates are separate clusters, each with total weight 1.
        boot["bootstrapDate"] = np.repeat(np.arange(len(parts)), [len(p) for p in parts])
        if boot.beatBenchmark.nunique() < 2:
            return {"status": "MODEL_UNSTABLE_BOOTSTRAP_ONE_CLASS"}
        weights = V1.date_weights(boot.bootstrapDate)
        transformer = V1.TrainTransformer(names, logs).fit(boot, weights)
        p, m = V1.estimator_pair("LINEAR", spec)
        with threadpool_limits(limits=1), warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            x, v = transformer.transform(boot), transformer.transform(validation)
            p.fit(x, boot.beatBenchmark.astype(int), sample_weight=weights)
            m.fit(x, boot.forwardRelativeReturn, sample_weight=weights)
            probability.append(p.predict_proba(v)[:, 1])
            returns.append(m.predict(v))
    tail = cfg["lowerQuantile"]
    return {"status": "MEASURED", "probabilityLower": np.quantile(probability, tail, axis=0),
            "probabilityUpper": np.quantile(probability, 1 - tail, axis=0),
            "meanLower": np.quantile(returns, tail, axis=0),
            "meanUpper": np.quantile(returns, 1 - tail, axis=0),
            "meanStd": np.std(returns, axis=0, ddof=1)}


def predict_cell(data, schedule, region, horizon, spec, spec_hash):
    """Walk-forward predictions and decisions for one region x horizon cell.

    ``data`` holds only tradable name-dates in eligible region-years, with
    gross labels, net labels and the dated round-trip cost attached. Returns
    (list of prediction frames, fold records, numerical failures). Only the
    LINEAR family produces decisions; the challenger never does.
    """
    import pandas as pd
    from . import alpha_opportunity_v2_decision as D

    names = spec["allowedFeatures"][region][str(horizon)]
    predictions, records, failures, history = [], [], [], []
    started = False
    for fold in V1.folds(as_v1_target(data), schedule, spec):
        record = {k: v for k, v in fold.items() if k not in ("train", "validation")}
        started = started or fold["status"] == "READY"
        records.append({**record, "region": region, "horizon": horizon, "evaluation": started})
        if fold["status"] != "READY":
            continue
        train, valid = fold["train"], fold["validation"]
        residual = V1.matured_residual_scale(
            pd.concat(history, ignore_index=True) if history else pd.DataFrame(), fold["cutoff"])
        for family in ("LINEAR", "SHALLOW_CHALLENGER"):
            try:
                fit = fit_heads(train, valid, names, family, spec)
            except (ConvergenceWarning, FloatingPointError) as exc:
                failures.append({"region": region, "horizon": horizon, "family": family,
                                 "year": fold["year"], "reason": type(exc).__name__})
                continue
            out = valid.copy()
            out["grossExpectedAlpha"] = fit["expectedRelativeReturn"]
            out["expectedRelativeReturn"] = fit["expectedRelativeReturn"]
            out["probabilityNetOutperform"] = fit["probability"]
            out["trainingBaseRate"] = fit["trainingBaseRate"]
            out["trainingMeanReturn"] = fit["trainingMeanReturn"]
            out["omittedFeatures"] = [fit["omittedFeatures"]] * len(out)
            out["missingFeatures"] = [[n for n, v in zip(names, row) if pd.isna(v)]
                                      for row in out.reindex(columns=names).itertuples(index=False)]
            out["family"], out["horizon"], out["trainingCutoff"] = family, horizon, fold["cutoff"]
            out["modelVersion"], out["specSha256"] = spec["modelIds"][region], spec_hash
            out["predictiveResidualRms"] = residual if residual is not None else np.nan
            for key in ("grossExpectedAlphaLower", "grossExpectedAlphaUpper",
                        "probabilityLower", "probabilityUpper"):
                out[key] = np.nan
            out["uncertaintyStatus"] = "NOT_PRIMARY"
            if family == "LINEAR":
                try:
                    u = prediction_uncertainty(train, valid, names, spec)
                except (ConvergenceWarning, FloatingPointError) as exc:
                    u = {"status": "MODEL_UNSTABLE_" + type(exc).__name__}
                out["uncertaintyStatus"] = u["status"]
                if u["status"].startswith("MODEL_UNSTABLE"):
                    failures.append({"region": region, "horizon": horizon, "family": family,
                                     "year": fold["year"], "reason": u["status"]})
                elif u["status"] == "MEASURED":
                    out["grossExpectedAlphaLower"] = u["meanLower"]
                    out["grossExpectedAlphaUpper"] = u["meanUpper"]
                    out["probabilityLower"] = u["probabilityLower"]
                    out["probabilityUpper"] = u["probabilityUpper"]
                decided = pd.DataFrame([D.decide(r, cost=r["roundTripCost"])
                                        for r in out.to_dict("records")], index=out.index)
                for key in decided.columns.drop("roundTripCost"):
                    out[key] = decided[key]
                history.append(out)
            else:
                out["opportunityClass"] = "CHALLENGER_NOT_A_DECISION"
                out["activeOpportunity"] = None
            predictions.append(out)
    return predictions, records, failures
