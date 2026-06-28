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

LGBM_PARAMS = dict(
    n_estimators=100,
    learning_rate=0.05,
    max_depth=5,
    num_leaves=31,
    subsample=0.8,
    colsample_bytree=0.8,
    class_weight="balanced",
    random_state=42,
    verbose=-1,
    n_jobs=-1,
)


def _new_model():
    import lightgbm as lgb

    return lgb.LGBMClassifier(**LGBM_PARAMS)


def _fit_calibrator(model, cal_X, cal_y):
    """Isotonic calibration on an already-fitted model.

    Supports both the modern FrozenEstimator API (sklearn >= 1.6) and the
    legacy cv='prefit' API (sklearn < 1.8).
    """
    from sklearn.calibration import CalibratedClassifierCV

    try:
        from sklearn.frozen import FrozenEstimator

        calibrator = CalibratedClassifierCV(FrozenEstimator(model), method="isotonic")
    except ImportError:  # pragma: no cover - old sklearn
        calibrator = CalibratedClassifierCV(model, method="isotonic", cv="prefit")
    calibrator.fit(cal_X, cal_y)
    return calibrator


def _calibrated_proba(model, cal_X, cal_y, target_X):
    """Isotonic-calibrated UP probabilities; falls back to raw on failure."""
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

        # Embargo `horizon` rows, then hold out the calibration window.
        cal_end = i - horizon
        cal_start = cal_end - cal_w
        if cal_start <= cfg.min_train_days:
            continue
        train = model_frame.iloc[0:cal_start]
        cal = model_frame.iloc[cal_start:cal_end]

        model = _new_model()
        model.fit(train[feature_cols], train[target_col])

        prob_cal = _calibrated_proba(model, cal[feature_cols], cal[target_col], test[feature_cols])
        prob_raw = model.predict_proba(test[feature_cols])[:, 1]

        for j, (idx, row) in enumerate(test.iterrows()):
            records.append(
                {
                    "date": idx,
                    "actual": int(row[target_col]),
                    "prob_raw": float(prob_raw[j]),
                    "prob_cal": float(prob_cal[j]),
                }
            )

    if not records:
        return pd.DataFrame()

    res = pd.DataFrame(records).set_index("date")
    res["pred_cal"] = (res["prob_cal"] >= 0.5).astype(int)
    res = res.join(data[["Close", "Open"]], how="left")
    return res


def current_signal(
    data: pd.DataFrame,
    feature_cols: list[str],
    target_col: str,
    cfg: ModelConfig,
) -> dict | None:
    """Predict today's calibrated UP-probability.

    The calibration window is held out of training (see walk_forward) so the
    live probability is calibrated out-of-sample rather than in-sample.
    """
    feat = data.dropna(subset=feature_cols)
    if feat.empty:
        return None
    train_all = feat.dropna(subset=[target_col])
    cal_w = cfg.calibration_window
    if len(train_all) <= cfg.min_train_days + cal_w or train_all[target_col].nunique() < 2:
        return None

    fit_part = train_all.iloc[:-cal_w]
    cal = train_all.iloc[-cal_w:]
    if fit_part[target_col].nunique() < 2:
        return None

    model = _new_model()
    model.fit(fit_part[feature_cols], fit_part[target_col])

    latest_X = feat.iloc[[-1]][feature_cols]
    prob_cal = float(_calibrated_proba(model, cal[feature_cols], cal[target_col], latest_X)[0])
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


def oos_metrics(res: pd.DataFrame) -> dict:
    from sklearn.metrics import precision_score, f1_score, brier_score_loss

    if res.empty:
        return {}
    actual = res["actual"]
    pred = res["pred_cal"]
    baseline = float(actual.mean())
    precision = float(precision_score(actual, pred, zero_division=0))
    return {
        "days": int(len(res)),
        "precision": round(precision, 4),
        "baseline": round(baseline, 4),
        "lift": round((precision - baseline) * 100, 2),
        "f1": round(float(f1_score(actual, pred, zero_division=0)), 4),
        "brier": round(float(brier_score_loss(actual, res["prob_cal"])), 4),
    }


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


def backtest(
    res: pd.DataFrame,
    commission: float = 5.0,
    slippage: float = 0.001,
    initial_capital: float = 100_000.0,
) -> dict:
    """Long/flat backtest on the calibrated signal with realistic costs."""
    if res.empty or len(res) < 2:
        return {}

    df = res.dropna(subset=["Close", "Open"]).copy()
    if len(df) < 2:
        return {}

    capital = float(initial_capital)
    position = 0
    shares = 0.0
    entry_price = 0.0
    values: list[dict] = []
    n_trades = 0
    OVERFLOW = 1e15

    closes = df["Close"].values
    opens = df["Open"].values
    signals = df["pred_cal"].values
    index = df.index

    for i in range(len(df)):
        signal = signals[i]
        close = closes[i]
        next_open = opens[i + 1] if i < len(df) - 1 else close

        if position == 0 and signal == 1:
            entry_price = next_open * (1 + slippage)
            shares = (capital - commission) / entry_price
            capital -= commission
            position = 1
            n_trades += 1
        elif position == 1 and signal == 0:
            exit_price = next_open * (1 - slippage)
            pnl = (exit_price - entry_price) * shares
            capital = capital + shares * entry_price + pnl - commission
            position = 0
            shares = 0.0

        value = capital + shares * close if position == 1 else capital
        if value > OVERFLOW:
            value = initial_capital
            break
        values.append({"date": index[i], "value": value, "position": position})

    if position == 1:
        exit_price = closes[-1] * (1 - slippage)
        pnl = (exit_price - entry_price) * shares
        capital = capital + shares * entry_price + pnl - commission

    pv = pd.DataFrame(values).set_index("date")
    total_return = (capital - initial_capital) / initial_capital
    years = max((index[-1] - index[0]).days / 365.25, 1e-9)
    annual = (1 + total_return) ** (1 / years) - 1 if total_return > -1 else -1.0

    pv["returns"] = pv["value"].pct_change()
    std = pv["returns"].std()
    sharpe = float(pv["returns"].mean() / std * np.sqrt(252)) if std and std > 0 else 0.0
    pv["peak"] = pv["value"].cummax()
    max_dd = float(((pv["value"] - pv["peak"]) / pv["peak"]).min())

    bh_return = (closes[-1] - closes[0]) / closes[0]
    bh_annual = (1 + bh_return) ** (1 / years) - 1

    return {
        "annualReturn": round(float(annual) * 100, 2),
        "sharpe": round(sharpe, 2),
        "maxDrawdown": round(max_dd * 100, 2),
        "numTrades": int(n_trades),
        "buyHoldAnnual": round(float(bh_annual) * 100, 2),
        "vsBuyHold": round((float(annual) - float(bh_annual)) * 100, 2),
    }
