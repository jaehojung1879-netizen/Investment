"""Opportunity and Warning radars learned from the historical OOS ledger.

The question the Core Portfolio answers is "what is a good business to hold".
The question here is a different one:

    Something changed recently. Does that kind of change historically precede
    an asymmetric move over the next 63-126 sessions?

Which is why *change* features carry as much weight as level features. A name
that has been in the 95th alpha percentile for two years is a Core Portfolio
question, not an opportunity — nothing happened. A name that went from the 70th
to the 93rd percentile while relative momentum accelerated and volume surged is
an opportunity, whether or not its absolute rank is the highest on the board.

HOW THIS AVOIDS BEING A CURVE-FIT
---------------------------------
* Every model is scored on walk-forward test blocks it had no part in choosing.
  Family and hyperparameters are picked on the *validation* block only.
* A simple logistic regression is always in the field. If the gradient booster
  cannot beat it out-of-sample, the booster does not ship.
* Everything tried is counted. ``searchLog`` records the number of variants and
  the grid size, because "we tried 200 things and this one worked" is a very
  different claim from "we tried 6".
* The most recent years are sealed (``walkforward.HoldoutGuard``) and scored
  once, at the end.
* ``acceptance_report`` can, and is meant to, return ``accepted=False``. The
  radar then falls back to the transparent rule-based score and says so. A model
  that fails its gates is not quietly shipped with a caveat in a tooltip.

WHAT MATTERS MOST IN THE METRICS
--------------------------------
Not accuracy. A classifier at 54% accuracy that puts genuinely better future
excess returns in its top decile is useful; one at 61% whose deciles are
unordered is not. Decile monotonicity and top-decile realized excess are
therefore the acceptance criteria, and AUC is reported as context.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import quality as quality_mod
from . import walkforward as WF
from .historical_outcomes import EVIDENCE_HISTORICAL

MODEL_SPEC_VERSION = "opportunity-v1"

# Level features: where the name stands right now.
LEVEL_FEATURES = (
    "alphaPercentile", "momentumPercentile", "valuePercentile", "qualityPercentile",
    "lowvolPercentile", "relMomentum", "aboveMA50", "aboveMA200", "rsi14",
    "dist200Pct", "volumeSurge", "realizedVolPct", "downsideVolPct", "cvar95Pct",
    "maxDD252Pct", "mom20Pct", "mom60Pct", "overheatPercentile", "evidenceCoverage",
)
# Change features: what is different from last time. These are the ones the
# opportunity question actually turns on.
CHANGE_FEATURES = (
    "alphaPercentileDelta", "relMomentumDelta", "momentum20Acceleration",
    "momentum60Acceleration", "volumeSurgeDelta", "volRegimeRatio",
    "entryStateImproved", "sectorRotationImproved", "ma200Crossed",
)
FEATURE_COLUMNS = LEVEL_FEATURES + CHANGE_FEATURES

# Targets are compared inside the validation framework, never chosen by peeking
# at which one produced the prettiest test-period equity curve.
TARGET_SPECS = {
    "TARGET_A_POSITIVE_EXCESS_126D": {
        "horizon": 126, "kind": "excess_above", "threshold": 0.0,
        "descriptionKo": "126일 초과수익 > 0",
    },
    "TARGET_B_STRONG_EXCESS_126D": {
        "horizon": 126, "kind": "excess_above", "threshold": 0.05,
        "descriptionKo": "126일 초과수익 > +5%",
    },
    "TARGET_C_TOP_QUINTILE_126D": {
        "horizon": 126, "kind": "cross_section_top", "threshold": 0.20,
        "descriptionKo": "동일 날짜·지역 횡단면에서 126일 초과수익 상위 20%",
    },
    "TARGET_D_ASYMMETRIC_63D": {
        "horizon": 63, "kind": "asymmetric", "threshold": 0.10, "maeFloor": -0.10,
        "descriptionKo": "63일 최대상승폭 > +10% 이면서 최대하락폭 > -10%",
    },
}

WARNING_TARGET_SPECS = {
    "WARN_A_DEEP_UNDERPERFORMANCE_126D": {
        "horizon": 126, "kind": "excess_below", "threshold": -0.05,
        "descriptionKo": "126일 초과수익 < -5%",
    },
    "WARN_B_DRAWDOWN_63D": {
        "horizon": 63, "kind": "drawdown_below", "threshold": -0.15,
        "descriptionKo": "63일 보유 중 최대낙폭 < -15%",
    },
}

RADAR_TIERS = ("VALIDATED_OPPORTUNITY", "EMERGING_OPPORTUNITY", "WATCH")
TIER_KO = {
    "VALIDATED_OPPORTUNITY": "검증된 기회",
    "EMERGING_OPPORTUNITY": "관찰 필요한 변화",
    "WATCH": "관심 목록",
}


# --------------------------------------------------------------------------- #
# Dataset
# --------------------------------------------------------------------------- #
def build_dataset(signals: list[dict], outcomes: list[dict]) -> pd.DataFrame:
    """Join frozen signals to their matured outcomes, one row per observation.

    The join is on signal id. A signal without a matured outcome simply has no
    label yet and is excluded — never imputed, never filled with a partial
    return.
    """
    if not signals or not outcomes:
        return pd.DataFrame()
    by_id = {o.get("id"): o for o in outcomes if o.get("id")}
    rows = []
    for signal in signals:
        outcome = by_id.get(signal.get("id"))
        if not outcome:
            continue
        features = signal.get("features") or {}
        row = {
            "id": signal["id"],
            "date": pd.Timestamp(signal.get("date") or signal.get("asOf")).normalize(),
            "ticker": signal.get("ticker"),
            "region": signal.get("region") or "UNKNOWN",
            "sector": signal.get("sector") or "Unclassified",
            "macroRegime": signal.get("macroRegime"),
            "entryState": signal.get("entryState"),
            "sectorRotation": signal.get("sectorRotation"),
            "evidenceClass": signal.get("evidenceClass") or EVIDENCE_HISTORICAL,
            "pitCoverage": float(((signal.get("pit") or {}).get("pitCoverage")) or 0.0),
            "usableForCalibration": bool((signal.get("pit") or {})
                                          .get("usableForCalibration", True)),
        }
        for column in FEATURE_COLUMNS:
            value = features.get(column)
            row[column] = float(value) if isinstance(value, (int, float)) else np.nan
        for horizon in (21, 63, 126, 252):
            payload = (outcome.get("horizons") or {}).get(str(horizon)) or {}
            row[f"excess_{horizon}"] = payload.get("excessReturn")
            row[f"netExcess_{horizon}"] = payload.get("costAdjustedExcessReturn")
            row[f"mfe_{horizon}"] = payload.get("mfe")
            row[f"mae_{horizon}"] = payload.get("mae")
            row[f"mdd_{horizon}"] = payload.get("maxDrawdown")
        rows.append(row)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["date", "region", "ticker"], kind="mergesort").reset_index(drop=True)


def add_target(frame: pd.DataFrame, target: str,
               specs: dict | None = None) -> pd.DataFrame:
    """Attach the binary label for ``target`` plus the excess return it scores on."""
    specs = specs or {**TARGET_SPECS, **WARNING_TARGET_SPECS}
    spec = specs[target]
    horizon = int(spec["horizon"])
    out = frame.copy()
    excess = pd.to_numeric(out.get(f"excess_{horizon}"), errors="coerce")
    out["targetHorizon"] = horizon
    out["scoreExcess"] = pd.to_numeric(out.get(f"netExcess_{horizon}"), errors="coerce")
    out["grossExcess"] = excess

    # The same decomposition the alpha calibration uses, for the same reason:
    # excess over the BENCHMARK is universe carry plus what the score picked,
    # and only the second is the model's. Measured per date x region, so the
    # carry a model inherits for free on a given day is removed from that day.
    if {"date", "region"} <= set(out.columns):
        out["universeExcess"] = out.groupby(["date", "region"])["scoreExcess"].transform("mean")
        out["scoreSpread"] = out["scoreExcess"] - out["universeExcess"]
    else:
        out["universeExcess"] = np.nan
        out["scoreSpread"] = out["scoreExcess"]

    kind = spec["kind"]
    if kind == "excess_above":
        label = (excess > float(spec["threshold"])).astype(float)
    elif kind == "excess_below":
        label = (excess < float(spec["threshold"])).astype(float)
    elif kind == "cross_section_top":
        # Rank inside each date x region cross-section — never pooled across
        # dates, which would make the label a market-timing signal in disguise.
        ranks = out.groupby(["date", "region"])[f"excess_{horizon}"].rank(pct=True)
        label = (ranks >= 1.0 - float(spec["threshold"])).astype(float)
    elif kind == "asymmetric":
        mfe = pd.to_numeric(out.get(f"mfe_{horizon}"), errors="coerce")
        mae = pd.to_numeric(out.get(f"mae_{horizon}"), errors="coerce")
        label = ((mfe > float(spec["threshold"])) & (mae > float(spec["maeFloor"]))).astype(float)
    elif kind == "drawdown_below":
        mdd = pd.to_numeric(out.get(f"mdd_{horizon}"), errors="coerce")
        label = (mdd < float(spec["threshold"])).astype(float)
    else:
        raise ValueError(f"unknown target kind {kind!r}")

    label[excess.isna()] = np.nan
    out["target"] = label
    return out.dropna(subset=["target"]).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Model zoo
# --------------------------------------------------------------------------- #
def _pipeline(estimator):
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    # Median imputation, not zero: a missing change feature means "no prior
    # observation", and zero would assert "nothing changed", which is a claim.
    #
    # keep_empty_features matters here rather than being a detail. A price-only
    # Phase 1 replay has no fundamentals, so valuePercentile and
    # qualityPercentile are all-NaN; the default would silently drop those
    # columns at fit time and then hit a width mismatch the day a PIT
    # fundamentals feed arrives. Keeping them (constant, hence scaled to zero)
    # makes the feature matrix width stable across phases.
    return make_pipeline(
        SimpleImputer(strategy="median", keep_empty_features=True),
        StandardScaler(), estimator)


def model_zoo(cfg: dict | None = None) -> dict[str, dict]:
    """Candidate families, simplest first. The baseline is not optional."""
    cfg = cfg or {}
    seed = int(cfg.get("randomState", 42))
    zoo: dict[str, dict] = {
        "LOGISTIC_BASELINE": {"family": "logistic", "params": {"C": 1.0}, "baseline": True},
        "LOGISTIC_L2_STRONG": {"family": "logistic", "params": {"C": 0.05}},
        "LOGISTIC_L2_WEAK": {"family": "logistic", "params": {"C": 5.0}},
        "RANDOM_FOREST": {"family": "random_forest",
                          "params": {"n_estimators": 300, "max_depth": 6,
                                     "min_samples_leaf": 50, "random_state": seed}},
        "GRADIENT_BOOSTING": {"family": "gradient_boosting",
                              "params": {"n_estimators": 200, "learning_rate": 0.05,
                                         "max_depth": 3, "subsample": 0.8,
                                         "random_state": seed}},
        "GRADIENT_BOOSTING_SHALLOW": {"family": "gradient_boosting",
                                      "params": {"n_estimators": 120, "learning_rate": 0.05,
                                                 "max_depth": 2, "subsample": 0.8,
                                                 "random_state": seed}},
    }
    if cfg.get("includeLightGbm", True):
        try:
            import lightgbm  # noqa: F401
            zoo["LIGHTGBM"] = {"family": "lightgbm",
                               "params": {"n_estimators": 250, "learning_rate": 0.05,
                                          "max_depth": 4, "num_leaves": 15,
                                          "min_child_samples": 60, "subsample": 0.8,
                                          "colsample_bytree": 0.8, "random_state": seed,
                                          "verbose": -1, "n_jobs": 1}}
        except Exception:
            pass
    return zoo


def build_estimator(family: str, params: dict):
    if family == "logistic":
        from sklearn.linear_model import LogisticRegression
        return _pipeline(LogisticRegression(max_iter=2000, **params))
    if family == "random_forest":
        from sklearn.ensemble import RandomForestClassifier
        return _pipeline(RandomForestClassifier(n_jobs=1, **params))
    if family == "gradient_boosting":
        from sklearn.ensemble import GradientBoostingClassifier
        return _pipeline(GradientBoostingClassifier(**params))
    if family == "lightgbm":
        import lightgbm as lgb
        return _pipeline(lgb.LGBMClassifier(**params))
    raise ValueError(f"unknown model family {family!r}")


def _fit_calibrator(scores: np.ndarray, labels: np.ndarray, method: str = "isotonic"):
    """Map raw scores onto probabilities using validation-block outcomes only.

    A raw gradient-boosting score of 0.87 is not "87% chance". It becomes one
    only after being mapped through outcomes the model did not train on.
    """
    scores = np.asarray(scores, dtype=float)
    labels = np.asarray(labels, dtype=float)
    if len(np.unique(labels)) < 2 or len(scores) < 50:
        return None
    if method == "isotonic":
        from sklearn.isotonic import IsotonicRegression
        model = IsotonicRegression(out_of_bounds="clip", y_min=0.01, y_max=0.99)
        model.fit(scores, labels)
        return model
    from sklearn.linear_model import LogisticRegression
    model = LogisticRegression(max_iter=1000)
    model.fit(scores.reshape(-1, 1), labels)
    return model


def _apply_calibrator(calibrator, scores: np.ndarray) -> np.ndarray:
    scores = np.asarray(scores, dtype=float)
    if calibrator is None:
        return np.clip(scores, 0.01, 0.99)
    if hasattr(calibrator, "predict_proba"):
        return np.clip(calibrator.predict_proba(scores.reshape(-1, 1))[:, 1], 0.01, 0.99)
    return np.clip(calibrator.predict(scores), 0.01, 0.99)


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def decile_table(scores: np.ndarray, excess: np.ndarray, bins: int = 10) -> list[dict]:
    """Mean future excess return by score decile — the metric that decides."""
    frame = pd.DataFrame({"score": scores, "excess": excess}).dropna()
    if len(frame) < bins * 5:
        return []
    frame["decile"] = pd.qcut(frame["score"].rank(method="first"), bins,
                              labels=False, duplicates="drop")
    rows = []
    for decile, group in frame.groupby("decile", sort=True):
        rows.append({
            "decile": int(decile) + 1,
            "n": int(len(group)),
            "meanExcessPct": round(float(group["excess"].mean()) * 100, 3),
            "medianExcessPct": round(float(group["excess"].median()) * 100, 3),
            "hitRatio": round(float((group["excess"] > 0).mean()), 4),
        })
    return rows


def monotonicity(deciles: list[dict]) -> float | None:
    """Spearman correlation between decile index and mean excess return.

    +1 means every step up the score ladder paid more. This is the property the
    portfolio actually consumes; a high AUC with a flat ladder is useless.
    """
    if len(deciles) < 3:
        return None
    x = pd.Series([d["decile"] for d in deciles], dtype=float)
    y = pd.Series([d["meanExcessPct"] for d in deciles], dtype=float)
    if y.nunique() < 2:
        return None
    return round(float(x.rank().corr(y.rank(), method="pearson")), 4)


def _date_clustered(frame: pd.DataFrame, column: str) -> pd.Series:
    return frame.groupby("date")[column].mean().sort_index()


def non_overlapping(series: pd.Series, horizon: int) -> pd.Series:
    """Thin a date-indexed series so consecutive entries do not share a window.

    Needed for anything path-dependent. Compounding daily-sampled 126-day
    forward returns as if they were a sequence of trades double-counts the same
    market moves ~126 times over and produces a drawdown figure that is pure
    arithmetic fiction. Means and hit ratios are unbiased under overlap;
    equity curves, drawdowns and CVaR are not.
    """
    if series is None or not len(series):
        return pd.Series(dtype=float)
    chosen: list[pd.Timestamp] = []
    for stamp in series.index:
        if not chosen or stamp >= chosen[-1] + pd.offsets.BDay(horizon):
            chosen.append(stamp)
    return series.loc[chosen]


def path_statistics(series: pd.Series, horizon: int) -> dict:
    """Drawdown and tail risk from a non-overlapping subsample only."""
    sample = non_overlapping(series, horizon)
    if len(sample) < 3:
        return {"mddPct": None, "cvar95Pct": None, "sharpe": None,
                "nonOverlappingDates": int(len(sample))}
    arr = sample.to_numpy(dtype=float)
    equity = np.cumprod(1.0 + arr)
    drawdown = equity / np.maximum.accumulate(equity) - 1.0
    tail_n = max(1, int(math.ceil(len(arr) * 0.05)))
    sharpe = (float(np.mean(arr) / np.std(arr, ddof=1))
              if len(arr) > 1 and np.std(arr, ddof=1) > 0 else None)
    return {
        "mddPct": round(float(np.min(drawdown)) * 100, 3),
        "cvar95Pct": round(float(np.mean(np.sort(arr)[:tail_n])) * 100, 3),
        "sharpe": round(sharpe, 4) if sharpe is not None else None,
        "nonOverlappingDates": int(len(arr)),
    }


def top_bucket_performance(frame: pd.DataFrame, *, top_pct: float = 0.1,
                           score_column: str = "score",
                           excess_column: str = "scoreExcess",
                           horizon: int | None = None) -> dict:
    """What the top slice actually earned, clustered by date.

    Ranking happens inside each date x region cross-section — a global cutoff
    would just select the easiest dates and call it stock selection.

    Mean and hit ratio use every date. Drawdown, CVaR and Sharpe use only a
    non-overlapping subsample, because those three are path-dependent and
    overlapping horizons would inflate them wildly.
    """
    empty = {"n": 0, "meanExcessPct": None, "hitRatio": None, "mddPct": None,
             "cvar95Pct": None, "dates": 0, "sharpe": None, "nonOverlappingDates": 0}
    work = frame.dropna(subset=[score_column, excess_column]).copy()
    if work.empty:
        return empty
    work["rank"] = work.groupby(["date", "region"])[score_column].rank(pct=True)
    top = work[work["rank"] >= 1.0 - float(top_pct)]
    if top.empty:
        return empty
    if horizon is None:
        horizon = int(work["targetHorizon"].iloc[0]) if "targetHorizon" in work else 126
    series = _date_clustered(top, excess_column)
    arr = series.to_numpy(dtype=float)
    path = path_statistics(series, horizon)

    # Level, carry and spread. The bar this feeds is an ABSOLUTE one, so the
    # split is not cosmetic: on the real ledger a model picking at random earns
    # +1.1% to +2.4% over the benchmark purely as universe carry, which clears
    # a 0.5% "did the edge survive costs" bar without any skill at all.
    carry = spread_mean = None
    if "universeExcess" in work.columns:
        universe = _date_clustered(work.dropna(subset=["universeExcess"]), "universeExcess")
        joined = pd.concat([series.rename("top"), universe.rename("universe")],
                           axis=1).dropna()
        if len(joined):
            carry = float(joined["universe"].mean())
            spread_mean = float((joined["top"] - joined["universe"]).mean())

    level_mean = float(np.mean(arr))
    # The conservative side binds, exactly as in historical_calibration: carry
    # flatters when the universe beat its benchmark, and the spread flatters
    # when it lagged.
    attributable = level_mean if spread_mean is None else min(level_mean, spread_mean)

    return {
        "n": int(len(top)),
        "dates": int(len(series)),
        "meanExcessPct": round(level_mean * 100, 3),
        "universeCarryPct": round(carry * 100, 3) if carry is not None else None,
        "spreadVsUniversePct": (round(spread_mean * 100, 3)
                                if spread_mean is not None else None),
        "attributableExcessPct": round(attributable * 100, 3),
        "attributionKo": ("벤치마크 대비 초과수익에서 유니버스 캐리를 뺀 값이 모델의 기여입니다. "
                           "합격 판정은 둘 중 보수적인 쪽으로 합니다."),
        "medianExcessPct": round(float(np.median(arr)) * 100, 3),
        "hitRatio": round(float(np.mean(arr > 0)), 4),
        "topPct": float(top_pct),
        "horizonDays": int(horizon),
        "pathBasisKo": "낙폭·CVaR·샤프는 겹치지 않는 날짜 표본에서만 계산합니다.",
        **path,
    }


def turnover(frame: pd.DataFrame, *, top_pct: float = 0.1,
             score_column: str = "score") -> float | None:
    """Share of the top bucket replaced between consecutive signal dates."""
    work = frame.dropna(subset=[score_column]).copy()
    if work.empty:
        return None
    work["rank"] = work.groupby(["date", "region"])[score_column].rank(pct=True)
    top = work[work["rank"] >= 1.0 - float(top_pct)]
    members = top.groupby("date")["ticker"].apply(set).sort_index()
    if len(members) < 2:
        return None
    changes = []
    previous = None
    for names in members:
        if previous is not None and (previous or names):
            union = previous | names
            changes.append(len(union - (previous & names)) / max(1, len(union)))
        previous = names
    return round(float(np.mean(changes)), 4) if changes else None


def classification_metrics(y: np.ndarray, p: np.ndarray) -> dict:
    from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
    y = np.asarray(y, dtype=float)
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    if len(np.unique(y)) < 2:
        return {"rocAuc": None, "prAuc": None, "brier": None, "calibrationError": None,
                "baseRate": round(float(np.mean(y)), 4), "n": int(len(y))}
    base = float(np.mean(y))
    return {
        "n": int(len(y)),
        "baseRate": round(base, 4),
        "rocAuc": round(float(roc_auc_score(y, p)), 4),
        "prAuc": round(float(average_precision_score(y, p)), 4),
        "prAucLift": round(float(average_precision_score(y, p)) - base, 4),
        "brier": round(float(brier_score_loss(y, p)), 5),
        "brierSkillScore": round(1.0 - brier_score_loss(y, p) /
                                 max(brier_score_loss(y, np.repeat(base, len(y))), 1e-9), 4),
        "calibrationError": round(float(quality_mod.calibration_error(y, p)), 5),
    }


def precision_at_k(y: np.ndarray, p: np.ndarray, k_pct: float = 0.1) -> float | None:
    order = np.argsort(-np.asarray(p, dtype=float))
    k = max(1, int(len(order) * k_pct))
    chosen = np.asarray(y, dtype=float)[order[:k]]
    return round(float(np.mean(chosen)), 4) if len(chosen) else None


# --------------------------------------------------------------------------- #
# Walk-forward evaluation
# --------------------------------------------------------------------------- #
@dataclass
class VariantResult:
    name: str
    family: str
    params: dict
    target: str
    validation: dict = field(default_factory=dict)
    test: dict = field(default_factory=dict)
    folds: list[dict] = field(default_factory=list)
    predictions: pd.DataFrame | None = None

    def to_dict(self) -> dict:
        return {"name": self.name, "family": self.family, "params": dict(self.params),
                "target": self.target, "validation": self.validation, "test": self.test,
                "folds": self.folds}


def _score_block(estimator, calibrator, block: pd.DataFrame) -> np.ndarray:
    raw = estimator.predict_proba(block[list(FEATURE_COLUMNS)])[:, 1]
    return _apply_calibrator(calibrator, raw)


def evaluate_variant(dataset: pd.DataFrame, folds: list[WF.Fold], *, name: str,
                     family: str, params: dict, target: str,
                     calibration: str = "isotonic",
                     top_pct: float = 0.1) -> VariantResult:
    """Fit on train, calibrate and select on validation, score on test — per fold.

    The estimator never sees a test row before it is scored, and the calibrator
    is fit on the validation block, which the estimator also never trained on.
    """
    fold_rows: list[dict] = []
    predictions: list[pd.DataFrame] = []
    validation_predictions: list[pd.DataFrame] = []

    for fold in folds:
        train = fold.slice(dataset, "train")
        validation = fold.slice(dataset, "validation")
        test = fold.slice(dataset, "test")
        if train.empty or validation.empty or test.empty:
            continue
        if train["target"].nunique() < 2:
            continue
        estimator = build_estimator(family, params)
        estimator.fit(train[list(FEATURE_COLUMNS)], train["target"].astype(int))

        raw_validation = estimator.predict_proba(validation[list(FEATURE_COLUMNS)])[:, 1]
        calibrator = _fit_calibrator(raw_validation, validation["target"].to_numpy(), calibration)
        validation_scores = _apply_calibrator(calibrator, raw_validation)
        test_scores = _score_block(estimator, calibrator, test)

        validation_block = validation.assign(score=validation_scores, fold=fold.index)
        test_block = test.assign(score=test_scores, fold=fold.index)
        validation_predictions.append(validation_block)
        predictions.append(test_block)

        fold_rows.append({
            **fold.to_dict(),
            "trainRows": int(len(train)), "validationRows": int(len(validation)),
            "testRows": int(len(test)),
            "validation": classification_metrics(validation["target"], validation_scores),
            "test": classification_metrics(test["target"], test_scores),
            "testTopBucket": top_bucket_performance(test_block, top_pct=top_pct),
        })

    result = VariantResult(name=name, family=family, params=params, target=target,
                           folds=fold_rows)
    if not predictions:
        return result
    pooled_test = pd.concat(predictions, ignore_index=True)
    pooled_validation = pd.concat(validation_predictions, ignore_index=True)
    result.predictions = pooled_test
    result.validation = _block_summary(pooled_validation, top_pct)
    result.test = _block_summary(pooled_test, top_pct)
    result.test["foldStability"] = _fold_stability(fold_rows)
    return result


def _block_summary(block: pd.DataFrame, top_pct: float) -> dict:
    deciles = decile_table(block["score"].to_numpy(),
                           pd.to_numeric(block["scoreExcess"], errors="coerce").to_numpy())
    return {
        **classification_metrics(block["target"], block["score"]),
        "precisionAtTop10Pct": precision_at_k(block["target"].to_numpy(),
                                              block["score"].to_numpy(), 0.10),
        "deciles": deciles,
        "decileMonotonicity": monotonicity(deciles),
        "topBucket": top_bucket_performance(block, top_pct=top_pct),
        "turnover": turnover(block, top_pct=top_pct),
    }


def _fold_stability(fold_rows: list[dict]) -> dict:
    """Did the edge appear in every fold, or in one lucky one?"""
    means = [((row.get("testTopBucket") or {}).get("meanExcessPct"))
             for row in fold_rows]
    means = [m for m in means if m is not None]
    if not means:
        return {"folds": 0, "positiveFolds": 0, "signAgreement": None, "stable": None}
    positive = sum(1 for m in means if m > 0)
    agreement = positive / len(means)
    return {
        "folds": len(means), "positiveFolds": positive,
        "signAgreement": round(agreement, 3),
        "meanByFoldPct": [round(m, 3) for m in means],
        "worstFoldPct": round(min(means), 3),
        "stable": bool(agreement >= 0.6),
    }


# --------------------------------------------------------------------------- #
# Overfitting diagnostics
# --------------------------------------------------------------------------- #
def deflated_sharpe(observed_sharpe: float | None, n_trials: int, n_obs: int,
                    skew: float = 0.0, kurtosis: float = 3.0) -> float | None:
    """Bailey & Lopez de Prado deflated Sharpe ratio.

    Answers: given that we tried ``n_trials`` variants, how surprising is the
    best Sharpe we found? A high raw Sharpe from a wide search is not evidence.
    """
    if observed_sharpe is None or n_obs < 10 or n_trials < 1:
        return None
    from math import erf, log, sqrt
    normal_cdf = lambda x: 0.5 * (1.0 + erf(x / sqrt(2.0)))  # noqa: E731
    # Expected maximum Sharpe under the null of zero true skill.
    euler = 0.5772156649
    if n_trials > 1:
        z1 = _inv_norm(1.0 - 1.0 / n_trials)
        z2 = _inv_norm(1.0 - 1.0 / (n_trials * math.e))
        expected_max = (1 - euler) * z1 + euler * z2
    else:
        expected_max = 0.0
    denominator = sqrt(max(1e-12, 1.0 - skew * observed_sharpe
                           + (kurtosis - 1.0) / 4.0 * observed_sharpe ** 2))
    statistic = (observed_sharpe - expected_max) * sqrt(max(1, n_obs - 1)) / denominator
    try:
        log(1)  # keep the import used and the intent explicit
    except Exception:  # pragma: no cover
        pass
    return round(float(normal_cdf(statistic)), 4)


def _inv_norm(p: float) -> float:
    """Acklam-style inverse normal CDF, adequate for a diagnostic."""
    from math import log, sqrt
    p = min(max(p, 1e-9), 1 - 1e-9)
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = sqrt(-2 * log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = sqrt(-2 * log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def probability_of_backtest_overfitting(variants: list[VariantResult]) -> dict:
    """Simplified PBO: does the validation-best variant stay best out of sample?

    López de Prado's CSCV, reduced to what the fold structure already provides.
    Split folds into two halves many ways; in each split, pick the variant that
    won on the first half and check its rank on the second. A winner that is
    routinely mid-pack out of sample is a selection artifact.
    """
    scored = [v for v in variants if v.folds]
    if len(scored) < 2:
        return {"available": False, "reason": "fewer_than_two_variants_with_folds"}
    fold_ids = sorted({row["fold"] for v in scored for row in v.folds})
    if len(fold_ids) < 4:
        return {"available": False, "reason": "fewer_than_four_folds"}

    def fold_score(variant: VariantResult, fold_id: int) -> float:
        for row in variant.folds:
            if row["fold"] == fold_id:
                return float((row.get("testTopBucket") or {}).get("meanExcessPct") or 0.0)
        return 0.0

    import itertools
    half = len(fold_ids) // 2
    logits = []
    combos = list(itertools.combinations(fold_ids, half))
    for combo in combos[:64]:
        inside, outside = set(combo), set(fold_ids) - set(combo)
        best = max(scored, key=lambda v: np.mean([fold_score(v, f) for f in inside]))
        outside_scores = sorted(
            ((np.mean([fold_score(v, f) for f in outside]), v.name) for v in scored),
            reverse=True)
        rank = [name for _, name in outside_scores].index(best.name) + 1
        relative = rank / (len(scored) + 1)
        logits.append(1.0 if relative > 0.5 else 0.0)
    pbo = float(np.mean(logits)) if logits else None
    return {
        "available": True,
        "probabilityOfBacktestOverfitting": round(pbo, 4) if pbo is not None else None,
        "splitsEvaluated": len(logits),
        "variantsCompared": len(scored),
        "interpretationKo": "검증 1위 모델이 다른 기간에서도 상위를 유지하는지의 비율 기반 추정치입니다.",
    }


def bootstrap_interval(frame: pd.DataFrame, *, column: str = "scoreExcess",
                       iterations: int = 500, seed: int = 42) -> dict | None:
    """Block bootstrap by date — resampling rows would fake independence."""
    if frame is None or frame.empty:
        return None
    series = _date_clustered(frame.dropna(subset=[column]), column)
    if len(series) < 10:
        return None
    rng = np.random.default_rng(seed)
    arr = series.to_numpy(dtype=float)
    means = [float(np.mean(rng.choice(arr, size=len(arr), replace=True)))
             for _ in range(iterations)]
    return {
        "meanPct": round(float(np.mean(arr)) * 100, 3),
        "ci95Pct": [round(float(np.percentile(means, 2.5)) * 100, 3),
                    round(float(np.percentile(means, 97.5)) * 100, 3)],
        "probabilityPositive": round(float(np.mean(np.array(means) > 0)), 4),
        "iterations": iterations, "blocks": int(len(arr)),
    }


# --------------------------------------------------------------------------- #
# Acceptance gate
# --------------------------------------------------------------------------- #
def acceptance_report(winner: VariantResult | None, baseline: VariantResult | None,
                      *, holdout: dict | None = None, cfg: dict | None = None,
                      pit_coverage: float | None = None) -> dict:
    """The explicit conditions under which this model must NOT ship.

    Failing here is a normal, expected outcome. The system keeps its existing
    rule-based radar and reports the failure rather than shipping a model that
    only worked in-sample.
    """
    cfg = cfg or {}
    min_monotonicity = float(cfg.get("minDecileMonotonicity", 0.6))
    min_top_excess = float(cfg.get("minTopBucketNetExcessPct", 0.5))
    min_pit_coverage = float(cfg.get("minPitCoverage", 0.6))
    max_regime_share = float(cfg.get("maxRegimeSharePct", 80.0))
    max_sector_share = float(cfg.get("maxSectorSharePct", 60.0))

    failures: list[str] = []
    if winner is None or not winner.test:
        return {"accepted": False, "failures": ["no_variant_produced_out_of_sample_results"],
                "checks": {}, "inconclusive": [], "thresholds": {}}

    test = winner.test
    top = test.get("topBucket") or {}
    base_top = ((baseline.test or {}).get("topBucket") or {}) if baseline else {}
    stability = test.get("foldStability") or {}

    def attributable(bucket: dict) -> float:
        """What the model earned, not what the universe handed it.

        Falls back to the level only when no universe series was available;
        `top_bucket_performance` already takes the conservative side of the two.
        """
        value = bucket.get("attributableExcessPct")
        if value is None:
            value = bucket.get("meanExcessPct")
        return -99.0 if value is None else float(value)

    checks = {
        "beatsBaselineOutOfSample": bool(
            baseline is None or attributable(top) > attributable(base_top)),
        "decileMonotonicity": bool((test.get("decileMonotonicity") or -1) >= min_monotonicity),
        # An absolute bar has to be met by an attributable number. Measured
        # against the benchmark, a random pick earns the universe carry — on the
        # production ledger +1.1% to +2.4% per 126 days — and would clear this
        # bar with no skill whatsoever.
        "netExcessSurvivesCost": bool(attributable(top) >= min_top_excess),
        "foldStability": bool(stability.get("stable")),
        "pitCoverageSufficient": bool((pit_coverage or 0.0) >= min_pit_coverage),
        # None = could not be assessed, which is a different fact from "passed".
        # It stays non-blocking (see `share` below) but must not be reported as
        # a pass: the artifact is read by people deciding whether to trust the
        # model, and "we could not tell" is the honest answer.
        "notRegimeConcentrated": None,
        "notSectorConcentrated": None,
        "holdoutHolds": True,
    }
    inconclusive: list[str] = []
    if winner.predictions is not None and not winner.predictions.empty:
        work = winner.predictions.copy()
        work["rank"] = work.groupby(["date", "region"])["score"].rank(pct=True)
        top_rows = work[work["rank"] >= 0.9]

        def share(column: str, unknown: str) -> float | None:
            """Top label's share, ignoring rows that carry no label at all.

            An all-unlabelled column means the check could not be run, which is
            a different fact from "the edge came from one sector". Failing the
            gate on missing labels would make the check a test of data coverage
            and would hide the concentration question rather than answer it.
            """
            if column not in top_rows:
                return None
            labelled = top_rows[column].dropna()
            labelled = labelled[labelled != unknown]
            if not len(labelled):
                return None
            return float(labelled.value_counts(normalize=True).iloc[0]) * 100

        regime_share = share("macroRegime", "UNKNOWN")
        sector_share = share("sector", "Unclassified")
        if regime_share is None:
            inconclusive.append("regimeConcentrationNotAssessable")
        else:
            checks["notRegimeConcentrated"] = bool(regime_share <= max_regime_share)
        if sector_share is None:
            inconclusive.append("sectorConcentrationNotAssessable")
        else:
            checks["notSectorConcentrated"] = bool(sector_share <= max_sector_share)
    if holdout:
        holdout_top = (holdout.get("topBucket") or {})
        checks["holdoutHolds"] = bool(
            attributable(holdout_top) >= min_top_excess
            and (holdout.get("decileMonotonicity") or -1) >= min_monotonicity - 0.2)

    # Only an explicit False blocks. A None was never assessed, and failing the
    # gate on it would turn a concentration check into a data-coverage test.
    for key, ok in checks.items():
        if ok is False:
            failures.append(key)
    return {
        "accepted": not failures,
        "checks": checks,
        "failures": failures,
        "inconclusive": inconclusive,
        "thresholds": {
            "minDecileMonotonicity": min_monotonicity,
            "minTopBucketNetExcessPct": min_top_excess,
            "minPitCoverage": min_pit_coverage,
            "maxRegimeSharePct": max_regime_share,
            "maxSectorSharePct": max_sector_share,
        },
        "policyKo": ("아래 조건 중 하나라도 실패하면 ML 모델을 production에 적용하지 않고 "
                      "기존 규칙 기반 점수를 유지합니다."),
    }


# --------------------------------------------------------------------------- #
# Full training procedure
# --------------------------------------------------------------------------- #
def train(dataset: pd.DataFrame, *, targets: dict | None = None,
          cfg: dict | None = None, guard: WF.HoldoutGuard | None = None,
          zoo: dict | None = None, progress: bool = False) -> dict:
    """Nested walk-forward selection across targets and model families.

    Returns the full record: every variant tried, the winner chosen on
    validation, its out-of-sample test performance, the sealed-holdout score,
    the overfitting diagnostics and the acceptance decision.
    """
    cfg = cfg or {}
    targets = targets or TARGET_SPECS
    zoo = zoo or model_zoo(cfg)
    guard = guard or WF.HoldoutGuard.from_config(cfg)
    top_pct = float(cfg.get("topBucketPct", 0.1))

    if dataset is None or dataset.empty:
        return {"status": "NO_DATA", "accepted": False,
                "reason": "historical_dataset_empty"}

    development = guard.development(dataset)
    if development.empty or development["date"].nunique() < 40:
        return {"status": "INSUFFICIENT_HISTORY", "accepted": False,
                "reason": "fewer_than_40_development_dates",
                "developmentDates": int(development["date"].nunique()) if not development.empty else 0}

    variants: list[VariantResult] = []
    search_log = {"variantsTested": 0, "targetsTested": len(targets),
                  "familiesTested": len(zoo), "gridSize": len(targets) * len(zoo)}

    for target in sorted(targets):
        horizon = int(targets[target]["horizon"])
        labelled = add_target(development, target, targets)
        if labelled.empty or labelled["target"].nunique() < 2:
            continue
        folds = WF.make_folds(
            labelled["date"], train_years=float(cfg.get("trainYears", 3.0)),
            validation_years=float(cfg.get("validationYears", 1.0)),
            test_years=float(cfg.get("testYears", 1.0)),
            horizon_days=horizon, embargo_days=int(cfg.get("embargoDays", 21)),
            mode=cfg.get("foldMode", "expanding"))
        if len(folds) < 2:
            continue
        for name, spec in sorted(zoo.items()):
            result = evaluate_variant(
                labelled, folds, name=name, family=spec["family"],
                params=spec["params"], target=target,
                calibration=cfg.get("calibration", "isotonic"), top_pct=top_pct)
            search_log["variantsTested"] += 1
            if result.test:
                variants.append(result)
                if progress:
                    print(f"  {target} / {name}: "
                          f"val AUC {result.validation.get('rocAuc')} "
                          f"test top {((result.test.get('topBucket') or {}).get('meanExcessPct'))}")

    if not variants:
        return {"status": "NO_VIABLE_VARIANT", "accepted": False,
                "reason": "no_variant_produced_folds", "searchLog": search_log}

    # SELECTION HAPPENS ON VALIDATION ONLY. The test block is scored afterwards
    # and never consulted to pick the winner.
    def validation_key(variant: VariantResult) -> tuple:
        summary = variant.validation or {}
        top = summary.get("topBucket") or {}
        return (round(float(summary.get("decileMonotonicity") or -1), 3),
                float(top.get("meanExcessPct") or -99),
                float(summary.get("prAucLift") or -99))

    winner = max(variants, key=validation_key)
    baseline = next((v for v in variants
                     if v.target == winner.target and v.name == "LOGISTIC_BASELINE"), None)

    # The sealed holdout is opened exactly once, now, after the winner is fixed.
    holdout_summary = None
    holdout_frame = guard.unseal("winner_selected").holdout(dataset, reason=winner.name)
    labelled_holdout = add_target(holdout_frame, winner.target, targets)
    labelled_development = add_target(development, winner.target, targets)
    if (not labelled_holdout.empty and not labelled_development.empty
            and labelled_development["target"].nunique() >= 2):
        estimator = build_estimator(winner.family, winner.params)
        estimator.fit(labelled_development[list(FEATURE_COLUMNS)],
                      labelled_development["target"].astype(int))
        raw_dev = estimator.predict_proba(labelled_development[list(FEATURE_COLUMNS)])[:, 1]
        calibrator = _fit_calibrator(raw_dev, labelled_development["target"].to_numpy(),
                                     cfg.get("calibration", "isotonic"))
        scores = _score_block(estimator, calibrator, labelled_holdout)
        holdout_summary = _block_summary(labelled_holdout.assign(score=scores), top_pct)
        holdout_summary["rows"] = int(len(labelled_holdout))
        holdout_summary["start"] = guard.start.strftime("%Y-%m-%d")

    pit_coverage = float(dataset["pitCoverage"].mean()) if "pitCoverage" in dataset else 0.0
    top = (winner.test or {}).get("topBucket") or {}
    diagnostics = {
        "searchLog": search_log,
        "probabilityOfBacktestOverfitting": probability_of_backtest_overfitting(variants),
        "deflatedSharpe": deflated_sharpe(
            top.get("sharpe"), n_trials=max(1, search_log["variantsTested"]),
            n_obs=int(top.get("dates") or 0)),
        "bootstrap": bootstrap_interval(winner.predictions),
        "foldStability": (winner.test or {}).get("foldStability"),
    }
    acceptance = acceptance_report(winner, baseline, holdout=holdout_summary,
                                   cfg=cfg.get("acceptance"), pit_coverage=pit_coverage)
    return {
        "status": "TRAINED",
        "specVersion": MODEL_SPEC_VERSION,
        "accepted": bool(acceptance["accepted"]),
        "winner": winner.to_dict(),
        "baseline": baseline.to_dict() if baseline else None,
        "holdout": holdout_summary,
        "variants": [v.to_dict() for v in variants],
        "diagnostics": diagnostics,
        "acceptance": acceptance,
        "features": list(FEATURE_COLUMNS),
        "targets": {k: dict(v) for k, v in targets.items()},
        "walkForward": WF.split_summary([], guard),
        "developmentRows": int(len(development)),
        "developmentDates": int(development["date"].nunique()),
        "meanPitCoverage": round(pit_coverage, 4),
    }


# --------------------------------------------------------------------------- #
# Scoring today's cross-section
# --------------------------------------------------------------------------- #
def _feature_value(row: dict, key: str, default: float = 0.0) -> float:
    value = (row or {}).get(key)
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) else default


def _rule_based_score(row: dict) -> float:
    """Transparent opportunity fallback when no accepted model exists.

    Weighted toward change, not level, so it answers the same question the ML
    model is meant to answer. Every term is visible and bounded.
    """
    value = lambda key, default=0.0: _feature_value(row, key, default)  # noqa: E731
    parts = [
        0.20 * np.clip(value("alphaPercentileDelta") / 15.0, -1, 1),
        0.20 * np.clip(value("momentum20Acceleration") / 10.0, -1, 1),
        0.15 * np.clip(value("relMomentumDelta") / 0.05, -1, 1),
        0.10 * np.clip((value("volumeSurge", 1.0) - 1.0) / 0.8, -1, 1),
        0.15 * np.clip(value("entryStateImproved"), -1, 1),
        0.10 * np.clip(value("sectorRotationImproved"), -1, 1),
        0.10 * np.clip((value("alphaPercentile", 50.0) - 50.0) / 50.0, -1, 1),
    ]
    return float(np.clip(0.5 + float(np.sum(parts)) / 2.0, 0.01, 0.99))


def _rule_based_warning_score(row: dict) -> float:
    """Deterioration score — the mirror question, not the opportunity score negated.

    Worth its own function rather than ``1 - opportunity``: the deterioration
    case has terms with no opportunity counterpart. A volatility shock and a
    volume spike into falling prices are both warnings, but neither is simply
    the absence of an opportunity, and a symmetric score would rank a quiet
    stock as dangerous purely for being quiet.
    """
    value = lambda key, default=0.0: _feature_value(row, key, default)  # noqa: E731
    parts = [
        0.20 * np.clip(-value("alphaPercentileDelta") / 15.0, -1, 1),
        0.20 * np.clip(-value("momentum20Acceleration") / 10.0, -1, 1),
        0.15 * np.clip(-value("relMomentumDelta") / 0.05, -1, 1),
        0.15 * np.clip(-value("entryStateImproved"), -1, 1),
        0.10 * np.clip(-value("ma200Crossed"), -1, 1),
        0.10 * np.clip((value("volRegimeRatio", 1.0) - 1.0) / 0.8, -1, 1),
        # Distribution: heavy volume while the price falls.
        0.10 * (1.0 if (value("volumeSurge", 1.0) >= 1.3 and value("mom20Pct") < 0) else 0.0),
    ]
    return float(np.clip(0.5 + float(np.sum(parts)) / 2.0, 0.01, 0.99))


def _distribution_percentile(score: float, reference: np.ndarray | None) -> float | None:
    if reference is None or not len(reference):
        return None
    return round(float((reference <= score).mean()) * 100, 1)


def score_candidates(candidates: list[dict], *, dataset: pd.DataFrame | None = None,
                     spec: dict | None = None, cfg: dict | None = None,
                     kind: str = "opportunity") -> dict:
    """Score today's names, refitting the validated spec on the historical ledger.

    Refitting beats shipping a pickle: the model that scores today is provably
    the family and hyperparameters that survived walk-forward selection, fitted
    on every development row available, with nothing to go stale or fail to
    deserialize.

    ``kind`` selects which question is being scored. The warning radar must use
    the deterioration model and the deterioration fallback — reusing the
    opportunity score for both would make every low-opportunity name look like a
    warning, which is a different and much less useful statement.
    """
    cfg = cfg or {}
    spec = spec or {}
    fallback = _rule_based_warning_score if kind == "warning" else _rule_based_score
    accepted = (bool(spec.get("accepted")) and spec.get("status") == "TRAINED"
                and spec.get("kind", "opportunity") == kind)
    winner = spec.get("winner") or {}
    target = winner.get("target")
    reference: np.ndarray | None = None
    calibration_rows: list[dict] = []

    features = pd.DataFrame([
        {column: c.get("features", {}).get(column) for column in FEATURE_COLUMNS}
        for c in candidates
    ], columns=list(FEATURE_COLUMNS)).apply(pd.to_numeric, errors="coerce")

    scores: np.ndarray
    method = "RULE_BASED_CHANGE_SCORE"
    ml_status = "NOT_TRAINED"
    if accepted and dataset is not None and not dataset.empty and target:
        labelled = add_target(dataset, target, {**TARGET_SPECS, **WARNING_TARGET_SPECS})
        if not labelled.empty and labelled["target"].nunique() >= 2 and len(features):
            estimator = build_estimator(winner["family"], winner.get("params") or {})
            estimator.fit(labelled[list(FEATURE_COLUMNS)], labelled["target"].astype(int))
            raw_in = estimator.predict_proba(labelled[list(FEATURE_COLUMNS)])[:, 1]
            calibrator = _fit_calibrator(raw_in, labelled["target"].to_numpy(),
                                         cfg.get("calibration", "isotonic"))
            reference = _apply_calibrator(calibrator, raw_in)
            raw_live = estimator.predict_proba(features)[:, 1]
            scores = _apply_calibrator(calibrator, raw_live)
            method = f"{winner['family'].upper()}_{target}"
            ml_status = "ACTIVE"
            calibration_rows = _calibration_bands(labelled.assign(score=reference))
        else:
            scores = np.array([fallback(c.get("features") or {}) for c in candidates])
            ml_status = "DATASET_INSUFFICIENT_FOR_REFIT"
    else:
        scores = np.array([fallback(c.get("features") or {}) for c in candidates])
        if spec.get("status") == "TRAINED" and not accepted:
            ml_status = ("REJECTED_BY_ACCEPTANCE_GATE"
                         if spec.get("kind", "opportunity") == kind
                         else "NO_MODEL_FOR_THIS_RADAR")

    rows = []
    for candidate, score in zip(candidates, scores if len(scores) else []):
        rows.append({**candidate, "score": round(float(score) * 100, 1),
                     "rawProbability": round(float(score), 4),
                     "historicalPercentile": _distribution_percentile(float(score), reference)})
    return {
        "rows": rows,
        "kind": kind,
        "method": method,
        "mlStatus": ml_status,
        "target": target,
        "targetDescriptionKo": ((spec.get("targets") or {}).get(target) or {}).get("descriptionKo"),
        "calibrationBands": calibration_rows,
        "evidenceClass": EVIDENCE_HISTORICAL if ml_status == "ACTIVE" else "NONE",
    }


def _calibration_bands(frame: pd.DataFrame, bins: int = 5) -> list[dict]:
    """Observed outcomes by score band — what a score of 90 has meant.

    Published only where the band is thick enough to mean anything; a band with
    twelve observations gets a count and no headline percentage.
    """
    work = frame.dropna(subset=["score", "scoreExcess"]).copy()
    if len(work) < bins * 30:
        return []
    work["band"] = pd.qcut(work["score"].rank(method="first"), bins,
                           labels=False, duplicates="drop")
    out = []
    for band, group in work.groupby("band", sort=True):
        n = int(len(group))
        thick = n >= 100
        out.append({
            "band": int(band) + 1,
            "scoreFrom": round(float(group["score"].min()) * 100, 1),
            "scoreTo": round(float(group["score"].max()) * 100, 1),
            "n": n,
            "uniqueDates": int(group["date"].nunique()),
            "positiveExcessHitRatio": round(float((group["grossExcess"] > 0).mean()), 4) if thick else None,
            "meanExcessPct": round(float(group["scoreExcess"].mean()) * 100, 3) if thick else None,
            "medianExcessPct": round(float(group["scoreExcess"].median()) * 100, 3) if thick else None,
            "worstDecileExcessPct": round(float(group["scoreExcess"].quantile(0.1)) * 100, 3) if thick else None,
            "sampleSufficient": thick,
        })
    return out


# --------------------------------------------------------------------------- #
# Radar assembly
# --------------------------------------------------------------------------- #
def _convergent_signals(features: dict) -> list[str]:
    """Which independent things are pointing the same way right now."""
    def value(key, default=0.0):
        v = features.get(key)
        try:
            f = float(v)
        except (TypeError, ValueError):
            return default
        return f if math.isfinite(f) else default

    signals = []
    if value("alphaPercentileDelta") >= 5:
        signals.append("ALPHA_PERCENTILE_RISING")
    if value("momentum20Acceleration") >= 3:
        signals.append("MOMENTUM_ACCELERATION")
    if value("relMomentumDelta") >= 0.01:
        signals.append("RELATIVE_MOMENTUM_IMPROVING")
    if value("volumeSurge", 1.0) >= 1.3:
        signals.append("VOLUME_SURGE")
    if value("entryStateImproved") > 0:
        signals.append("ENTRY_STATE_UPGRADE")
    if value("sectorRotationImproved") > 0:
        signals.append("SECTOR_ROTATION_IMPROVING")
    if value("ma200Crossed") > 0:
        signals.append("RECLAIMED_MA200")
    return signals


SIGNAL_KO = {
    "ALPHA_PERCENTILE_RISING": "알파 백분위 상승",
    "MOMENTUM_ACCELERATION": "모멘텀 가속",
    "RELATIVE_MOMENTUM_IMPROVING": "상대강도 개선",
    "VOLUME_SURGE": "거래량 급증",
    "ENTRY_STATE_UPGRADE": "진입상태 개선",
    "SECTOR_ROTATION_IMPROVING": "섹터 로테이션 개선",
    "RECLAIMED_MA200": "200일선 회복",
    "VOLUME_SPIKE_ON_DECLINE": "하락 중 거래량 급증",
    "ALPHA_PERCENTILE_FALLING": "알파 백분위 하락",
    "MOMENTUM_DECELERATION": "모멘텀 둔화",
    "RELATIVE_MOMENTUM_DETERIORATING": "상대강도 악화",
    "ENTRY_STATE_DOWNGRADE": "진입상태 악화",
    "LOST_MA200": "200일선 이탈",
    "VOLATILITY_SHOCK": "변동성 급등",
    "SECTOR_ROTATION_DETERIORATING": "섹터 로테이션 악화",
}


def _is_distribution(features: dict) -> bool:
    """Volume surging while price falls is distribution, not opportunity.

    Explicitly separated because a naive "volume + change" score would rank a
    collapsing stock highly for exactly the wrong reason.
    """
    def value(key, default=0.0):
        v = features.get(key)
        try:
            f = float(v)
        except (TypeError, ValueError):
            return default
        return f if math.isfinite(f) else default
    surging = value("volumeSurge", 1.0) >= 1.3
    falling = (value("mom20Pct") < 0 or value("relMomentumDelta") < 0
               or value("momentum20Acceleration") < 0)
    return bool(surging and falling)


def classify_tier(row: dict, *, ml_active: bool, high_score: float,
                  min_signals: int = 3) -> tuple[str, list[str]]:
    """VALIDATED / EMERGING / WATCH, with the reason attached.

    A name cannot be VALIDATED on score alone: the score must be high, several
    independent signals must agree, and the ML layer must have passed its
    acceptance gate. Without validated evidence the best a strong change can
    earn is EMERGING — research only.
    """
    features = row.get("features") or {}
    signals = _convergent_signals(features)
    score = float(row.get("score") or 0.0)
    notes: list[str] = []

    if _is_distribution(features):
        # Heavy volume into a falling price is distribution. It is never an
        # opportunity, no matter how high the change score reads — the score
        # sees "something is moving", which is precisely the ambiguity this
        # guard resolves.
        notes.append("VOLUME_SURGE_WITH_PRICE_DECLINE_NOT_AN_OPPORTUNITY")
        return "WATCH", notes
    if not signals:
        notes.append("NO_RECENT_CHANGE_DETECTED")
        return "WATCH", notes
    if score >= high_score and len(signals) >= min_signals and ml_active:
        return "VALIDATED_OPPORTUNITY", notes
    if score >= high_score and len(signals) >= min_signals:
        notes.append("HISTORICAL_MODEL_NOT_VALIDATED_RESEARCH_ONLY")
        return "EMERGING_OPPORTUNITY", notes
    if len(signals) >= 2:
        notes.append("SIGNAL_CONVERGENCE_BELOW_VALIDATION_BAR")
        return "EMERGING_OPPORTUNITY", notes
    notes.append("SINGLE_SIGNAL_ONLY")
    return "WATCH", notes


def build_radar(candidates: list[dict], *, dataset: pd.DataFrame | None = None,
                spec: dict | None = None, cfg: dict | None = None,
                kind: str = "opportunity", limit: int = 8) -> dict:
    """Region-split radar over today's cross-section."""
    cfg = cfg or {}
    high_score = float(cfg.get("highScoreThreshold", 70.0))
    scored = score_candidates(candidates, dataset=dataset, spec=spec, cfg=cfg, kind=kind)
    ml_active = scored["mlStatus"] == "ACTIVE"
    score_key = "opportunityScore" if kind == "opportunity" else "warningScore"

    by_region: dict[str, list[dict]] = {}
    for row in scored["rows"]:
        if kind == "opportunity":
            tier, notes = classify_tier(row, ml_active=ml_active, high_score=high_score)
        else:
            tier, notes = _warning_tier(row, ml_active=ml_active, high_score=high_score)
        signals = (_convergent_signals(row.get("features") or {}) if kind == "opportunity"
                   else _deterioration_signals(row.get("features") or {}))
        entry = {
            "ticker": row.get("ticker"), "region": row.get("region"),
            "sector": row.get("sector"),
            score_key: row.get("score"),
            "historicalPercentile": row.get("historicalPercentile"),
            "tier": tier,
            "tierKo": (TIER_KO if kind == "opportunity" else WARNING_TIER_KO).get(tier, tier),
            "signals": signals,
            "signalsKo": [SIGNAL_KO.get(s, s) for s in signals],
            "notes": notes,
            "alphaPercentile": (row.get("features") or {}).get("alphaPercentile"),
            "entryState": row.get("entryState"),
            "isCoreHolding": bool(row.get("isCoreHolding")),
        }
        by_region.setdefault(row.get("region") or "UNKNOWN", []).append(entry)

    for region, rows in by_region.items():
        # A warning on something the portfolio actually holds outranks a warning
        # on a name nobody owns, regardless of score.
        rows.sort(key=lambda r: (
            0 if (r["isCoreHolding"] and kind == "warning") else 1,
            -(r[score_key] or 0), str(r["ticker"])))
        by_region[region] = rows[:limit]

    return {
        "kind": kind,
        "regions": by_region,
        "method": scored["method"],
        "mlStatus": scored["mlStatus"],
        "evidenceClass": scored["evidenceClass"],
        "target": scored["target"],
        "targetDescriptionKo": scored["targetDescriptionKo"],
        "calibrationBands": scored["calibrationBands"],
        "highScoreThreshold": high_score,
        "notAGuaranteeKo": ("과거 유사 신호의 결과 분포이며 미래 수익을 보장하지 않습니다."),
    }


WARNING_TIER_KO = {
    "CRITICAL_WARNING": "즉시 점검",
    "ELEVATED_WARNING": "악화 관찰",
    "WATCH": "관심 목록",
}


def _deterioration_signals(features: dict) -> list[str]:
    def value(key, default=0.0):
        v = features.get(key)
        try:
            f = float(v)
        except (TypeError, ValueError):
            return default
        return f if math.isfinite(f) else default

    signals = []
    if value("alphaPercentileDelta") <= -5:
        signals.append("ALPHA_PERCENTILE_FALLING")
    if value("momentum20Acceleration") <= -3:
        signals.append("MOMENTUM_DECELERATION")
    if value("relMomentumDelta") <= -0.01:
        signals.append("RELATIVE_MOMENTUM_DETERIORATING")
    if value("entryStateImproved") < 0:
        signals.append("ENTRY_STATE_DOWNGRADE")
    if value("ma200Crossed") < 0:
        signals.append("LOST_MA200")
    if value("volRegimeRatio", 1.0) >= 1.6:
        signals.append("VOLATILITY_SHOCK")
    if value("sectorRotationImproved") < 0:
        signals.append("SECTOR_ROTATION_DETERIORATING")
    if value("volumeSurge", 1.0) >= 1.3 and value("mom20Pct") < 0:
        signals.append("VOLUME_SPIKE_ON_DECLINE")
    return signals


def _warning_tier(row: dict, *, ml_active: bool, high_score: float) -> tuple[str, list[str]]:
    features = row.get("features") or {}
    signals = _deterioration_signals(features)
    score = float(row.get("score") or 0.0)
    notes: list[str] = []
    trend_broken = "LOST_MA200" in signals
    entry_downgraded = "ENTRY_STATE_DOWNGRADE" in signals
    if entry_downgraded and trend_broken:
        notes.append("ENTRY_DOWNGRADE_WITH_TREND_BREAKDOWN")
        return "CRITICAL_WARNING", notes
    if score >= high_score and len(signals) >= 2:
        if not ml_active:
            notes.append("HISTORICAL_MODEL_NOT_VALIDATED_RESEARCH_ONLY")
        return "CRITICAL_WARNING" if len(signals) >= 3 else "ELEVATED_WARNING", notes
    if len(signals) >= 2:
        return "ELEVATED_WARNING", notes
    if not signals:
        notes.append("NO_DETERIORATION_DETECTED")
    return "WATCH", notes


# --------------------------------------------------------------------------- #
# Historical analogues (explainability, NOT a predictor)
# --------------------------------------------------------------------------- #
ANALOGUE_FEATURES = (
    "alphaPercentile", "momentumPercentile", "relMomentum", "alphaPercentileDelta",
    "momentum20Acceleration", "volumeSurge", "dist200Pct", "rsi14",
)


def historical_analogues(candidate: dict, dataset: pd.DataFrame | None, *,
                         horizon: int = 126, k: int = 40,
                         same_region: bool = True) -> dict | None:
    """The closest past setups and what happened next.

    A research and explainability tool, deliberately not wired into sizing.
    Features are standardized before distances are taken (otherwise a
    percentile on 0-100 would drown a ratio on 0-2), and matching is restricted
    to the same region so a KR setup is not explained by US analogues.
    """
    if dataset is None or dataset.empty:
        return None
    columns = [c for c in ANALOGUE_FEATURES if c in dataset.columns]
    if not columns:
        return None
    pool = dataset
    if same_region and candidate.get("region"):
        pool = pool[pool["region"] == candidate["region"]]
    excess_column = f"excess_{horizon}"
    if excess_column not in pool.columns:
        return None
    pool = pool.dropna(subset=[excess_column])
    pool = pool.dropna(subset=columns, how="all")
    if len(pool) < k * 2:
        return None

    values = pool[columns].apply(pd.to_numeric, errors="coerce")
    mu, sigma = values.mean(), values.std(ddof=0).replace(0, 1.0)
    scaled = ((values - mu) / sigma).fillna(0.0)
    target = pd.Series({c: (candidate.get("features") or {}).get(c) for c in columns},
                       dtype=float)
    target_scaled = ((target - mu) / sigma).fillna(0.0)
    distance = np.sqrt(((scaled - target_scaled) ** 2).sum(axis=1))
    nearest = pool.loc[distance.nsmallest(k).index]
    outcomes = pd.to_numeric(nearest[excess_column], errors="coerce").dropna()
    if outcomes.empty:
        return None
    return {
        "matches": int(len(outcomes)),
        "uniqueDates": int(nearest["date"].nunique()),
        "horizonDays": horizon,
        "meanExcessPct": round(float(outcomes.mean()) * 100, 2),
        "medianExcessPct": round(float(outcomes.median()) * 100, 2),
        "positiveExcessRatio": round(float((outcomes > 0).mean()), 3),
        "worstDecileExcessPct": round(float(outcomes.quantile(0.1)) * 100, 2),
        "bestDecileExcessPct": round(float(outcomes.quantile(0.9)) * 100, 2),
        "meanDistance": round(float(distance.nsmallest(k).mean()), 3),
        "sampleSufficient": bool(len(outcomes) >= 30 and nearest["date"].nunique() >= 10),
        "disclaimerKo": ("과거 유사 국면의 결과 분포입니다. 유사 사례가 미래 결과를 "
                          "보장하지 않으며 설명·리서치 목적으로만 제공합니다."),
    }
