"""Feature engineering, ported from the notebook's CELL 4.

Parameterized so it works for any ticker. Macro/VIX features degrade
gracefully (filled with neutral values) when those inputs are unavailable,
so the model can still run on price data alone.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# DAILY, same-day-public macro series that are safe as ML features (no release
# lag). Everything else (monthly/weekly prints) is regime-description only.
ML_MACRO_COLS = {
    "Treasury_10Y", "Treasury_2Y", "Yield_Curve", "FedFunds", "HY_Spread",
    "IG_Spread", "Real_10Y", "Breakeven_10Y", "Broad_Dollar", "WTI",
    "USD_KRW", "Korea_10Y", "Korea_3M", "RRP",
}


def _rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def build_features(
    price: pd.DataFrame,
    benchmark_close: pd.Series | None = None,
    vix: pd.Series | None = None,
    macro: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return a feature frame for a single ticker.

    `price` must contain Open/High/Low/Close/Volume indexed by date.
    """
    data = price.copy()

    # Attach exogenous series aligned on the price index.
    if benchmark_close is not None:
        data["BENCH"] = benchmark_close.reindex(data.index).ffill()
    if vix is not None:
        data["VIX"] = vix.reindex(data.index).ffill()
    if macro is not None:
        # POINT-IN-TIME: only DAILY, same-day-public market series may enter the
        # ML features. Monthly/weekly macro (CPI, PCE, unemployment, payrolls,
        # CFNAI, NFCI, Fed balance sheet, M2, ...) is released with a lag, so
        # ffill+shift(1) would leak a print into the model before it was public.
        # Those series are used ONLY for the current regime description
        # (pipeline.regime, with explicit release lags), never as ML inputs.
        macro_ml = macro[[c for c in macro.columns if c in ML_MACRO_COLS]]
        if len(macro_ml.columns):
            macro_aligned = macro_ml.reindex(data.index).ffill().shift(1)
            for col in macro_aligned.columns:
                data[col] = macro_aligned[col]

    # --- Price features ---
    data["returns"] = data["Close"].pct_change()
    data["log_returns"] = np.log(data["Close"] / data["Close"].shift(1))
    data["high_low_ratio"] = data["High"] / data["Low"]
    data["close_open_ratio"] = data["Close"] / data["Open"]

    # --- Moving averages ---
    for period in [5, 10, 20, 50, 100, 200]:
        data[f"ma{period}"] = data["Close"].rolling(period).mean()
        data[f"ma{period}_ratio"] = data["Close"] / data[f"ma{period}"]

    # --- Volatility ---
    for period in [5, 10, 20, 60]:
        data[f"volatility_{period}d"] = data["returns"].rolling(period).std() * np.sqrt(252)

    # --- Volume ---
    data["volume_ma20"] = data["Volume"].rolling(20).mean()
    data["volume_ratio"] = data["Volume"] / data["volume_ma20"]

    # --- Momentum ---
    for period in [5, 10, 20, 60]:
        data[f"momentum_{period}d"] = data["Close"].pct_change(period)

    # --- RSI ---
    data["rsi_14"] = _rsi(data["Close"], 14)
    data["rsi_28"] = _rsi(data["Close"], 28)

    # --- MACD ---
    ema12 = data["Close"].ewm(span=12).mean()
    ema26 = data["Close"].ewm(span=26).mean()
    data["macd"] = ema12 - ema26
    data["macd_signal"] = data["macd"].ewm(span=9).mean()
    data["macd_diff"] = data["macd"] - data["macd_signal"]

    # --- Bollinger Bands ---
    bb_middle = data["Close"].rolling(20).mean()
    bb_std = data["Close"].rolling(20).std()
    bb_upper = bb_middle + (bb_std * 2)
    bb_lower = bb_middle - (bb_std * 2)
    data["bb_width"] = (bb_upper - bb_lower) / bb_middle
    data["bb_position"] = (data["Close"] - bb_lower) / (bb_upper - bb_lower)

    # --- VIX features (neutral defaults if missing) ---
    if "VIX" not in data:
        data["VIX"] = 20.0
    data["vix_ma20"] = data["VIX"].rolling(20).mean()
    data["vix_ratio"] = data["VIX"] / data["vix_ma20"]
    data["vix_change"] = data["VIX"].pct_change()
    data["vix_short_long"] = data["VIX"] / data["VIX"].rolling(60).mean()

    # --- Relative strength vs benchmark (downside feature) ---
    if "BENCH" in data:
        data["rel_ratio"] = data["Close"] / data["BENCH"]
        data["rel_momentum"] = data["rel_ratio"].pct_change(20)
    else:
        data["rel_ratio"] = 1.0
        data["rel_momentum"] = 0.0

    # --- Macro stress (neutral defaults if missing) ---
    if "Treasury_10Y" not in data:
        data["Treasury_10Y"] = 3.0
    if "Yield_Curve" not in data:
        data["Yield_Curve"] = 0.5
    data["treasury_stress"] = data["Treasury_10Y"] / data["Treasury_10Y"].rolling(60).mean()
    data["yield_curve_change"] = data["Yield_Curve"].diff(20)
    data["risk_score"] = (
        data["vix_ratio"] * 0.4
        + data["vix_short_long"] * 0.3
        + (1 / (data["Yield_Curve"] + 2)) * 0.3
    )

    # --- Market regime ---
    data["ma50_ma200"] = data["ma50"] / data["ma200"]
    data["price_52w_high"] = data["Close"] / data["Close"].rolling(252).max()
    data["price_52w_low"] = data["Close"] / data["Close"].rolling(252).min()

    # --- Calendar ---
    data["month"] = data.index.month
    data["day_of_week"] = data.index.dayofweek
    data["quarter"] = data.index.quarter

    # Drop intermediate helper columns.
    drop_cols = ["volume_ma20", "vix_ma20", "BENCH"]
    data = data.drop(columns=[c for c in drop_cols if c in data.columns])

    return data


def add_targets(data: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    """Add forward returns and binary UP/DOWN targets for each horizon."""
    data = data.copy()
    for h in horizons:
        forward_return = data["Close"].shift(-h) / data["Close"] - 1
        target = pd.Series(np.nan, index=data.index, dtype=float)
        valid = forward_return.notna()
        target.loc[valid] = (forward_return.loc[valid] > 0).astype(float)
        data[f"forward_return_{h}d"] = forward_return
        data[f"target_{h}d"] = target
    return data


def feature_columns(data: pd.DataFrame) -> list[str]:
    """Columns used as model inputs (exclude raw OHLCV and targets)."""
    exclude = {"Open", "High", "Low", "Close", "Volume", "VIX"}
    return [
        c
        for c in data.columns
        if c not in exclude
        and not c.startswith("forward_return")
        and not c.startswith("target_")
    ]
