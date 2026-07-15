"""LightGBM walk-forward modelling, ported from the notebook.

Per (ticker, horizon) this produces:
  - a walk-forward out-of-sample prediction history (for metrics + backtest)
  - today's calibrated UP-probability (the live signal)
  - a dynamic alert threshold derived from the OOS probability distribution
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import ModelConfig
from . import quality as Q
from .backtest import long_flat_next_open

# NOTE ON PROBABILITIES: class_weight="balanced" is intentionally absent —
# reweighting classes distorts predicted probabilities, and this pipeline's
# whole output is a calibrated probability. Base rates here are ~0.5 anyway.
LGBM_PARAMS = dict(
    n_estimators=100,
    learning_rate=0.05,
    max_depth=5,
    num_leaves=31,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=42,
    verbose=-1,
    n_jobs=-1,
)

# Final guard rails on any published probability. A 10-day directional
# forecast never deserves 0% or 100%; anything outside this band is a
# calibration artifact, not information.
PROB_CLIP = (0.05, 0.95)
# Bayesian shrinkage strength toward the calibration-window base rate
# (pseudo-observations in a Beta-prior sense). Overlapping h-day targets mean
# a 252-row calibration window holds only ~252/h independent outcomes, so the
# calibrated probability is pulled toward the base rate accordingly.
SHRINKAGE_K = 15.0


class _EnsembleModel:
    """Gradient boosting + regularized logistic regression, probability-averaged.

    Averaging two decorrelated model families is the standard institutional
    variance-reduction step: the tree model captures interactions, the linear
    model anchors against tree overfit on ~40 noisy features. Falls back to
    LGBM alone if the linear member fails to fit.
    """

    def __init__(self):
        import lightgbm as lgb

        self._lgbm = lgb.LGBMClassifier(**LGBM_PARAMS)
        self._linear = None

    def fit(self, X, y):
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        self._lgbm.fit(X, y)
        try:
            linear = make_pipeline(
                StandardScaler(),
                LogisticRegression(C=0.1, max_iter=1000),
            )
            linear.fit(X, y)
            self._linear = linear
        except Exception:
            self._linear = None
        return self

    def predict_proba(self, X):
        p = self._lgbm.predict_proba(X)
        if self._linear is not None:
            p = 0.5 * (p + self._linear.predict_proba(X))
        return p


def _new_model():
    return _EnsembleModel()


def shrink_probability(p, base_rate: float, n_eff: float):
    """Shrink a calibrated probability toward the base rate, then clip.

    p* = (n_eff·p + k·base) / (n_eff + k) — a Beta-prior posterior mean with k
    pseudo-observations at the base rate. n_eff is the number of INDEPENDENT
    outcomes backing the calibration (window / horizon for overlapping
    targets). Small evidence ⇒ heavy shrink; the clip keeps any survivor of a
    saturated calibrator inside honest bounds.
    """
    n_eff = max(float(n_eff), 1.0)
    shrunk = (n_eff * np.asarray(p, dtype=float) + SHRINKAGE_K * base_rate) / (n_eff + SHRINKAGE_K)
    return np.clip(shrunk, PROB_CLIP[0], PROB_CLIP[1])


def _fit_calibrator(model, cal_X, cal_y):
    """Platt (sigmoid) calibration on an already-fitted model.

    Sigmoid, not isotonic: isotonic is a step function that maps any score
    beyond the calibration range to exactly 0/1 — with a 252-row window of
    overlapping targets it saturated and the site displayed 100% probabilities.
    Platt's logistic map is smooth and cannot emit 0/1.

    Supports both the modern FrozenEstimator API (sklearn >= 1.6) and the
    legacy cv='prefit' API (sklearn < 1.8).
    """
    from sklearn.calibration import CalibratedClassifierCV

    try:
        from sklearn.frozen import FrozenEstimator

        calibrator = CalibratedClassifierCV(FrozenEstimator(model), method="sigmoid")
    except ImportError:  # pragma: no cover - old sklearn
        calibrator = CalibratedClassifierCV(model, method="sigmoid", cv="prefit")
    calibrator.fit(cal_X, cal_y)
    return calibrator


def _calibrated_proba(model, cal_X, cal_y, target_X):
    """Platt-calibrated UP probabilities; falls back to raw on failure."""
    try:
        if cal_y.nunique() < 2:
            raise ValueError("calibration window has a single class")
        calibrator = _fit_calibrator(model, cal_X, cal_y)
        return calibrator.predict_proba(target_X)[:, 1]
    except Exception:
        return model.predict_proba(target_X)[:, 1]


def walk_forward(
    data: pd.DataFrame,
    feature_cols: list[str],
    target_col: str,
    cfg: ModelConfig,
    oos_start: str,
    horizon: int,
) -> pd.DataFrame:
    """Purged, embargoed expanding-window walk-forward.

    Two leakage fixes vs. the original notebook:
      * Calibration window is HELD OUT of the model's training data, so the
        isotonic map is fit on genuinely out-of-sample scores (the old code
        calibrated on rows the model had already trained on, which collapsed
        probabilities to 0/1).
      * An embargo of `horizon` days separates train/calibration from the test
        block, so the h-day forward-looking target never overlaps the test
        period.
    Only predictions from oos_start onward are stored to bound CI runtime.
    """
    model_frame = data.dropna(subset=feature_cols + [target_col])
    cal_w = cfg.calibration_window
    min_history = cfg.min_train_days + cal_w + horizon
    if len(model_frame) <= min_history + cfg.step_size:
        return pd.DataFrame()

    # Index (positional) of first OOS row inside model_frame.
    oos_mask = np.asarray(model_frame.index >= pd.Timestamp(oos_start))
    if oos_mask.any():
        start_pos = max(min_history, int(np.argmax(oos_mask)))
    else:
        start_pos = min_history

    records: list[dict] = []
    n = len(model_frame)
    for i in range(start_pos, n, cfg.step_size):
        test = model_frame.iloc[i : i + cfg.step_size]
        if len(test) == 0:
            break

        # Purged split in trading-row units:
        # train target observation ends before calibration features start,
        # and calibration target observation ends before test features start.
        test_start = i
        cal_end = test_start - horizon
        cal_start = cal_end - cal_w
        train_end = cal_start - horizon
        if train_end < cfg.min_train_days or cal_start < 0 or cal_end <= cal_start:
            continue
        train = model_frame.iloc[0:train_end]
        cal = model_frame.iloc[cal_start:cal_end]

        model = _new_model()
        model.fit(train[feature_cols], train[target_col])

        prob_cal = _calibrated_proba(model, cal[feature_cols], cal[target_col], test[feature_cols])
        prob_cal = shrink_probability(prob_cal, float(cal[target_col].mean()), cal_w / max(horizon, 1))
        prob_raw = model.predict_proba(test[feature_cols])[:, 1]

        for j, (idx, row) in enumerate(test.iterrows()):
            records.append(
                {
                    "date": idx,
                    "actual": int(row[target_col]),
                    "prob_raw": float(prob_raw[j]),
                    "prob_cal": float(prob_cal[j]),
                    "foldTrainStart": train.index[0].strftime("%Y-%m-%d"),
                    "foldTrainEnd": train.index[-1].strftime("%Y-%m-%d"),
                    "foldCalibrationStart": cal.index[0].strftime("%Y-%m-%d"),
                    "foldCalibrationEnd": cal.index[-1].strftime("%Y-%m-%d"),
                    "foldTestStart": test.index[0].strftime("%Y-%m-%d"),
                    "foldTestEnd": test.index[-1].strftime("%Y-%m-%d"),
                }
            )

    if not records:
        return pd.DataFrame()

    res = pd.DataFrame(records).set_index("date")
    res["pred_cal"] = (res["prob_cal"] >= 0.5).astype(int)
    res = res.join(data[["Close", "Open"]], how="left")
    return res


def _horizon_of(target_col: str) -> int:
    """Extract the horizon (days) from a target column name like 'target_10d'."""
    try:
        return int(target_col.removeprefix("target_").removesuffix("d"))
    except ValueError:
        return 0


def current_signal(
    data: pd.DataFrame,
    feature_cols: list[str],
    target_col: str,
    cfg: ModelConfig,
) -> dict | None:
    """Predict today's calibrated UP-probability.

    The calibration window is held out of training (see walk_forward) so the
    live probability is calibrated out-of-sample rather than in-sample, and an
    embargo of `horizon` rows separates the fit block from the calibration
    block so the fit block's forward-looking targets never overlap it.
    """
    feat = data.dropna(subset=feature_cols)
    if feat.empty:
        return None
    train_all = feat.dropna(subset=[target_col])
    cal_w = cfg.calibration_window
    horizon = _horizon_of(target_col)
    if len(train_all) <= cfg.min_train_days + cal_w + horizon or train_all[target_col].nunique() < 2:
        return None

    fit_part = train_all.iloc[: -(cal_w + horizon)]
    cal = train_all.iloc[-cal_w:]
    if fit_part[target_col].nunique() < 2:
        return None

    model = _new_model()
    model.fit(fit_part[feature_cols], fit_part[target_col])

    latest_X = feat.iloc[[-1]][feature_cols]
    prob_cal = float(_calibrated_proba(model, cal[feature_cols], cal[target_col], latest_X)[0])
    prob_cal = float(shrink_probability(prob_cal, float(cal[target_col].mean()), cal_w / max(horizon, 1)))
    prob_raw = float(model.predict_proba(latest_X)[:, 1][0])

    return {
        "asOf": feat.index[-1].strftime("%Y-%m-%d"),
        "probUp": round(prob_cal, 4),
        "probUpRaw": round(prob_raw, 4),
        "prediction": "UP" if prob_cal >= 0.5 else "DOWN",
    }


def horizon_return_stats(data: pd.DataFrame, horizon: int) -> dict:
    """Historical mean UP/DOWN forward returns at a horizon (for EV scoring)."""
    col = f"forward_return_{horizon}d"
    if col not in data:
        return {"upMean": 0.0, "downMean": 0.0, "baseRate": 0.5}
    fr = data[col].dropna()
    up = fr[fr > 0]
    down = fr[fr <= 0]
    return {
        "upMean": float(up.mean()) if len(up) else 0.0,
        "downMean": float(down.mean()) if len(down) else 0.0,
        "baseRate": float((fr > 0).mean()) if len(fr) else 0.5,
    }


def oos_metrics(res: pd.DataFrame, threshold: float = 0.5) -> dict:
    return Q.evaluate_oos(res, threshold=threshold)


def dynamic_threshold(res: pd.DataFrame, cfg: ModelConfig) -> float:
    if res.empty:
        return cfg.fixed_threshold_fallback
    threshold = float(res["prob_cal"].quantile(cfg.alert_quantile))
    if threshold >= 0.999:
        threshold = cfg.fixed_threshold_fallback
    return round(threshold, 4)


def classify_alert(prob_up: float, threshold: float) -> str:
    if prob_up >= threshold:
        return "STRONG BUY"
    if prob_up <= (1 - threshold):
        return "STRONG SELL"
    return "HOLD"


def backtest(res: pd.DataFrame, commission: float = 5.0, slippage: float = 0.001, initial_capital: float = 100_000.0, region: str = "US") -> dict:
    """Compatibility wrapper: audited next-open long/flat reference strategy."""
    return long_flat_next_open(res, region=region, initial_capital=initial_capital)
