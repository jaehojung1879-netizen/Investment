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
    core: list[str]
    universe: dict[str, list[str]]  # region -> tickers, e.g. {"US": [...], "KR": [...]}
    benchmark: str
    primary: str
    horizons: list[int]
    trade_horizon: int
    model: ModelConfig
    fred_series: dict[str, str] = field(default_factory=dict)
    fred_api_key: str | None = None

    @property
    def has_fred(self) -> bool:
        return bool(self.fred_api_key)

    def region_of(self, ticker: str) -> str:
        for region, names in self.universe.items():
            if ticker in names:
                return region
        return "KR" if ticker.upper().endswith((".KS", ".KQ")) else "US"


def load_config(path: Path | str = CONFIG_PATH) -> tuple[Config, list[str]]:
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

    universe = raw.get("universe", {"US": raw.get("tickers", ["QQQ"]), "KR": []})
    universe = {region: list(dict.fromkeys(names)) for region, names in universe.items()}
    core = list(dict.fromkeys(raw.get("core", universe.get("US", ["QQQ"])[:3])))
    benchmark = raw.get("benchmark", "SPY")
    primary = raw.get("primary", core[0] if core else "QQQ")

    # Every distinct ticker we need price data for (universe + core + benchmark).
    all_tickers = [t for names in universe.values() for t in names] + core + [benchmark]
    download_universe = list(dict.fromkeys(all_tickers))

    return Config(
        portfolio_name=raw.get("portfolioName", "Investment Insight"),
        core=core,
        universe=universe,
        benchmark=benchmark,
        primary=primary,
        horizons=raw.get("horizons", [21, 63, 126]),
        trade_horizon=raw.get("tradeHorizon", 10),
        model=model,
        fred_series=raw.get("fred", {}).get("series", {}),
        fred_api_key=os.environ.get("FRED_API_KEY"),
    ), download_universe
