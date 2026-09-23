"""Two frozen model classes, independent regional annual walk-forward research."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from . import historical_outcomes as HO
from . import kelly_portfolio as KP
from . import regional_alpha_features as F

VERSION = "regional-alpha-model-v1"
HORIZON = 126
SEED = 42
RIDGE_PARAMS = {"alpha": 10.0, "solver": "cholesky"}
HGBR_PARAMS = {"learning_rate": .05, "max_iter": 100, "max_leaf_nodes": 7,
               "min_samples_leaf": 50, "l2_regularization": 10.0,
               "early_stopping": False, "random_state": SEED}
METHODS = ("RIDGE", "HGBR", "HGBR_PRICE_ONLY")
MIN_TRAIN_DATES = 104


def join_outcomes(frame, prices):
    """Derived labels only; existing outcome ledger is never opened for writing."""
    signals = [dict(id=r.outcomeJoinId, date=r.date, ticker=r.ticker,
                    region=r.region, benchmark=r.benchmark) for r in frame.itertuples()]
    outcomes = HO.compute_outcomes(signals, prices,
                                   {t: prices[t]["Close"] for t in F.BENCHMARKS.values()},
                                   horizons=(HORIZON,), evidence_class="DISCOVERY_ONLY")
    labels = []
    benchmark_dates = {t: prices[t].dropna(subset=["Close"]).index.to_numpy(dtype="datetime64[ns]")
                       for t in F.BENCHMARKS.values()}
    for row in outcomes:
        label = row["horizons"].get(str(HORIZON), {})
        # Existing machinery counts observed stock quotes. Require the same
        # endpoint to be exactly 126 regional benchmark sessions after as-of;
        # suspended/missing-price paths cannot silently lengthen the target.
        dates = benchmark_dates[row["benchmark"]]
        start = int(np.searchsorted(dates, np.datetime64(row["date"], "ns")))
        exact_horizon = (start + HORIZON < len(dates)
                         and dates[start] == np.datetime64(row["date"], "ns")
                         and label.get("endDate") == str(pd.Timestamp(dates[start + HORIZON]).date()))
        if exact_horizon and label.get("excessReturn") is not None and label.get("endDate"):
            labels.append(dict(outcomeJoinId=row["id"], futureExcess126=label["excessReturn"],
                               outcomeEndDate=label["endDate"]))
    if not labels:
        raise ValueError("no matured 126D outcomes")
    result = frame.merge(pd.DataFrame(labels), on="outcomeJoinId", how="left", validate="one_to_one")
    result["futureExcessRank126"] = result.groupby(["region", "date"])["futureExcess126"].rank(method="average", pct=True)
    result["target"] = result.futureExcessRank126 - .5
    return result


def date_weights(frame):
    if frame.region.nunique() != 1:
        raise ValueError("pooled US/KR training forbidden")
    return 1.0 / frame.groupby("date")["ticker"].transform("size").to_numpy(float)


def assert_training_cutoff(train, validation_start):
    if train.empty or train.outcomeEndDate.isna().any():
        raise ValueError("training labels unavailable")
    if not (train.outcomeEndDate < validation_start).all():
        raise ValueError("VALIDATION_LABEL_LEAKAGE: trainingOutcomeEndDate >= validationStartDate")
    if not (train.date < validation_start).all():
        raise ValueError("future training feature")


def training_frame(region_frame, validation_start):
    matured = region_frame.loc[region_frame.outcomeEndDate.notna()
                               & (region_frame.outcomeEndDate < validation_start)].copy()
    counts = matured.groupby("date")["ticker"].transform("size")
    matured = matured.loc[counts >= 10].copy()
    # Some names on an old date may mature late (halts). Rank ONLY the labels
    # actually known at this fit cutoff, not all labels ultimately seen later.
    matured["target"] = matured.groupby("date").futureExcess126.rank(method="average", pct=True) - .5
    return matured


def fit_predict(train, validation, names, method):
    if train.region.nunique() != 1 or validation.region.nunique() != 1 or train.region.iloc[0] != validation.region.iloc[0]:
        raise ValueError("separate US/KR models required")
    active = [n for n in names if train[n].notna().any()]
    if not active:
        raise ValueError("no train-visible features")
    omitted = sorted(set(names) - set(active))
    columns = active + [n+"__missing" for n in active]
    x, xv = train[columns].to_numpy(float), validation[columns].to_numpy(float)
    weights = date_weights(train)
    diag = {"activeFeatures": active, "omittedAllMissingTraining": omitted,
            "predictiveColumns": columns, "imputationMedians": None, "scalerMean": None,
            "standardizedCoefficients": None}
    with threadpool_limits(limits=1):
        if method == "RIDGE":
            imputer = SimpleImputer(strategy="median")
            scaler = StandardScaler()
            x = imputer.fit_transform(x)
            xv = imputer.transform(xv)
            x = scaler.fit_transform(x)
            xv = scaler.transform(xv)
            estimator = Ridge(**RIDGE_PARAMS)
            diag.update(imputationMedians=imputer.statistics_.tolist(), scalerMean=scaler.mean_.tolist(),
                        scalerScale=scaler.scale_.tolist())
        else:
            estimator = HistGradientBoostingRegressor(**HGBR_PARAMS)
        estimator.fit(x, train.target.to_numpy(float), sample_weight=weights)
        predictions = estimator.predict(xv)
    if method == "RIDGE":
        diag["standardizedCoefficients"] = dict(zip(columns, estimator.coef_.tolist()))
    return predictions, diag


def walk_forward(frame, manifest):
    predictions, folds = [], []
    for region in ("US", "KR"):
        sub = frame.loc[frame.region.eq(region)].sort_values(["date", "ticker"]).copy()
        if sub.empty:
            continue
        first = pd.Timestamp(sub.date.min())
        for year in sorted(sub.date.str[:4].unique()):
            validation = sub.loc[sub.date.str.startswith(year)].copy()
            start = F.weekly_grid(year+"-01-01", year+"-01-15", region)[0]
            if pd.Timestamp(start) < first + pd.DateOffset(months=36):
                continue
            train = training_frame(sub, start)
            if train.date.nunique() < MIN_TRAIN_DATES:
                continue
            assert_training_cutoff(train, start)
            print(f"fit {region} {year}: {len(train)} training rows", flush=True)
            for method in METHODS:
                names = F.allowed_features(manifest, region, price_only=method == "HGBR_PRICE_ONLY")
                score, diagnostics = fit_predict(train, validation, names, method)
                result = validation.drop(columns=[c for c in validation if c.startswith("raw_") or c.endswith("__missing")]).copy()
                result["predictionScore"] = score
                result["method"] = method
                result["validationYear"] = int(year)
                result["trainingCutoff"] = train.outcomeEndDate.max()
                result["rankPercentile"] = result.groupby("date").predictionScore.rank(method="average", pct=True)
                predictions.append(result)
                folds.append(dict(region=region, model=method, validationYear=int(year),
                                  validationStartDate=start, trainingCutoff=train.outcomeEndDate.max(),
                                  trainRows=len(train), trainDates=train.date.nunique(),
                                  validationRows=len(validation), featureCount=len(names), **diagnostics))
    if not predictions:
        raise ValueError("NOT_EVALUABLE: no region has sufficient annual training history")
    return pd.concat(predictions, ignore_index=True), folds


def hac(series):
    s = pd.to_numeric(series, errors="coerce").dropna().sort_index()
    if not len(s):
        return dict(mean=None, median=None, se=None, pValue=None, ci95=None,
                    containsZero=None, dates=0, effectiveIndependentDates=None,
                    positiveBlockRate=None, hacLag=None, bandwidthLimited=None)
    stats = KP._newey_west_stats(s, HORIZON)
    mean, se = stats["mean"], stats["se"]
    ci = [mean - 1.96 * se, mean + 1.96 * se] if se is not None and len(s) > 1 else None
    return dict(mean=float(mean), median=float(s.median()), se=se if ci else None,
                pValue=(math.erfc(abs(mean/se)/math.sqrt(2)) if se else (1.0 if mean == 0 else None)),
                ci95=ci, containsZero=(ci[0] <= 0 <= ci[1]) if ci else None,
                dates=len(s), effectiveIndependentDates=stats["effectiveDates"],
                positiveBlockRate=float((s > 0).mean()), hacLag=stats["hacLag"],
                bandwidthLimited=stats["bandwidthLimited"])


def per_date(frame, score="predictionScore"):
    rows = []
    for date, group in frame.groupby("date", sort=True):
        available = group.loc[group[score].notna()]
        measured = available.dropna(subset=["futureExcess126"])
        ic, quintiles = None, [None] * 5
        if len(measured) >= 10 and measured[score].nunique() > 1 and measured.futureExcess126.nunique() > 1:
            ic = float(measured[score].corr(measured.futureExcess126, method="spearman"))
        # Buckets determined on all predicted names, BEFORE labels are inspected.
        ranks = available[score].rank(method="average", pct=True)
        q = np.ceil(ranks * 5).clip(1, 5)
        for i in range(1, 6):
            bucket = available.loc[q == i]
            if len(bucket) and bucket.futureExcess126.notna().all():
                quintiles[i-1] = float(bucket.futureExcess126.mean())
        top = available.sort_values([score, "ticker"], ascending=[False, True], kind="mergesort").head(10)
        top_mean = float(top.futureExcess126.mean()) if len(top) == 10 and top.futureExcess126.notna().all() else None
        universe_mean = float(available.futureExcess126.mean()) if len(available) and available.futureExcess126.notna().all() else None
        rows.append(dict(date=date, rankIC=ic, names=len(available), measuredNames=len(measured),
                         labelCoverage=len(measured)/len(available) if len(available) else None,
                         q1=quintiles[0], q2=quintiles[1], q3=quintiles[2], q4=quintiles[3], q5=quintiles[4],
                         q5MinusQ1=quintiles[4]-quintiles[0] if quintiles[0] is not None and quintiles[4] is not None else None,
                         top10Excess=top_mean, universeExcess=universe_mean,
                         top10MinusUniverse=top_mean-universe_mean if top_mean is not None and universe_mean is not None else None))
    result = pd.DataFrame(rows)
    if len(result):
        result.index = pd.to_datetime(result.date)
    return result


def summarize(dates):
    quintiles = [float(dates[f"q{i}"].mean()) if dates[f"q{i}"].notna().any() else None for i in range(1, 6)]
    mono = sum(a < b for a, b in zip(quintiles, quintiles[1:])) / 4 if all(v is not None for v in quintiles) else None
    return dict(rankIC=hac(dates.rankIC), q5MinusQ1=hac(dates.q5MinusQ1),
                quintileMeans=quintiles, monotonicity=mono,
                top10Excess=hac(dates.top10Excess), top10MinusUniverse=hac(dates.top10MinusUniverse),
                dates=len(dates), meanNames=float(dates.names.mean()),
                labelCoverage=float(dates.measuredNames.sum()/dates.names.sum()) if dates.names.sum() else None)


def classify(summary):
    ic, spread = summary["rankIC"], summary["q5MinusQ1"]["mean"]
    frac, mono = summary.get("positiveFoldFraction"), summary["monotonicity"]
    if any(v is None for v in (ic["mean"], ic["ci95"], spread, frac, mono)):
        return "NOT_EVALUABLE"
    if ic["mean"] > 0 and ic["ci95"][0] > 0 and spread > 0 and mono >= .75 and frac >= .7:
        return "STRONG_DISCOVERY_ONLY"
    if ic["mean"] > 0 and spread > 0 and frac > .5 and ic["containsZero"]:
        return "PROMISING_BUT_UNCERTAIN_DISCOVERY"
    return "NO_MODEL_EVIDENCE"


def evaluate(predictions, folds):
    summaries, daily, annual = {}, {}, []
    for (region, method), group in predictions.groupby(["region", "method"], sort=True):
        key = region+"/"+method
        dates = per_date(group)
        summary = summarize(dates)
        fold_means = []
        for year, fold_dates in dates.groupby(dates.index.year):
            row = next(f for f in folds if (f["region"], f["model"], f["validationYear"]) == (region, method, year))
            metrics = summarize(fold_dates)
            annual.append(dict(**row, metrics=metrics))
            fold_means.append(metrics["rankIC"]["mean"])
        valid = [v for v in fold_means if v is not None]
        summary["positiveFoldFraction"] = sum(v > 0 for v in valid) / len(valid) if valid else None
        summary["measurableFolds"] = len(valid)
        summary["allFolds"] = len(fold_means)
        summaries[key], daily[key] = summary, dates
    baselines = {}
    for region in ("US", "KR"):
        group = predictions.loc[predictions.region.eq(region) & predictions.method.eq("HGBR")]
        if group.empty:
            continue
        for name in ("mom6", "mom121", "relative126", "relativeStrengthBreadth52w" if region == "US" else "marketCap"):
            dates = per_date(group, score=name)
            baselines[region+"/"+name] = summarize(dates)
            daily[region+"/"+name] = dates
        baselines[region+"/alphaPercentile"] = {"status": "DATA_LINEAGE_UNRESOLVED: historical sector"}
        baselines[region+("/marketCap" if region == "US" else "/absFxBeta26w")] = {
            "status": "PIT_MARKET_CAP_BASELINE_UNAVAILABLE" if region == "US" else "DATA_LINEAGE_UNRESOLVED: FX publication"}
    comparisons = {}
    for region in ("US", "KR"):
        full = daily.get(region+"/HGBR")
        if full is None:
            continue
        for key, other in daily.items():
            if key.startswith(region+"/") and key != region+"/HGBR":
                shared = pd.concat([full.rankIC, other.rankIC], axis=1, join="inner").dropna()
                comparisons[region+"/HGBR-minus-"+key.split("/")[1]] = hac(shared.iloc[:, 0] - shared.iloc[:, 1])
    classification = {r: classify(summaries[r+"/HGBR"]) if r+"/HGBR" in summaries else "NOT_EVALUABLE" for r in ("US", "KR")}
    return dict(primary=summaries, annual=annual, baselines=baselines,
                pairedICComparisons=comparisons, classification=classification), daily
