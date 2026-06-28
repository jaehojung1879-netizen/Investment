"""Load configuration from config.json and the environment.

The FRED API key is read from the FRED_API_KEY environment variable only.
Never hardcode it: in CI it is injected from a GitHub Actions secret.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config.json"


@dataclass
class ModelConfig:
    min_train_days: int = 252
    step_size: int = 21
    calibration_window: int = 252
    oos_start: str = "2020-01-01"
    alert_quantile: float = 0.80
    fixed_threshold_fallback: float = 0.70
    history_start: str = "2010-01-01"


@dataclass
class Config:
    portfolio_name: str
    tickers: list[str]
    benchmark: str
    primary: str
    horizons: list[int]
    model: ModelConfig
    fred_series: dict[str, str] = field(default_factory=dict)
    fred_api_key: str | None = None

    @property
    def has_fred(self) -> bool:
        return bool(self.fred_api_key)


def load_config(path: Path | str = CONFIG_PATH) -> Config:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    model_raw = raw.get("model", {})
    model = ModelConfig(
        min_train_days=model_raw.get("minTrainDays", 252),
        step_size=model_raw.get("stepSize", 21),
        calibration_window=model_raw.get("calibrationWindow", 252),
        oos_start=model_raw.get("oosStart", "2020-01-01"),
        alert_quantile=model_raw.get("alertQuantile", 0.80),
        fixed_threshold_fallback=model_raw.get("fixedThresholdFallback", 0.70),
        history_start=model_raw.get("historyStart", "2010-01-01"),
    )

    tickers = list(dict.fromkeys(raw.get("tickers", ["QQQ"])))  # de-dup, keep order
    benchmark = raw.get("benchmark", "SPY")
    primary = raw.get("primary", tickers[0] if tickers else "QQQ")

    # Make sure the benchmark price series is always downloaded even if it is
    # not one of the tracked tickers.
    download_universe = list(dict.fromkeys(tickers + [benchmark]))

    return Config(
        portfolio_name=raw.get("portfolioName", "Investment Insight"),
        tickers=tickers,
        benchmark=benchmark,
        primary=primary,
        horizons=raw.get("horizons", [21, 63, 126]),
        model=model,
        fred_series=raw.get("fred", {}).get("series", {}),
        fred_api_key=os.environ.get("FRED_API_KEY"),
    ), download_universe
