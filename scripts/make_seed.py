"""Generate a clearly-labelled SEED data/site-data.json from synthetic prices.

This lets the dashboard render before the first CI run. The numbers are
illustrative only — real values are produced by `python -m pipeline.build`
in GitHub Actions. Run: python3 scripts/make_seed.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import features as F  # noqa: E402
from pipeline import macro as macro_mod  # noqa: E402
from pipeline import model as M  # noqa: E402
from pipeline import risk as risk_mod  # noqa: E402
from pipeline.config import load_config  # noqa: E402


def synth_prices(seed: int, drift: float, n: int, dates) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    ret = rng.normal(drift, 0.013, n)
    ret[int(n * 0.55):int(n * 0.62)] -= 0.012  # a drawdown patch
    close = 100 * np.exp(np.cumsum(ret))
    return pd.DataFrame(
        {
            "Open": close * (1 + rng.normal(0, 0.002, n)),
            "High": close * (1 + np.abs(rng.normal(0, 0.004, n))),
            "Low": close * (1 - np.abs(rng.normal(0, 0.004, n))),
            "Close": close,
            "Volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
        },
        index=dates,
    )


def main() -> int:
    cfg, _ = load_config()
    n = 1700
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)

    bench = synth_prices(99, 0.0003, n, dates)
    vix = pd.Series(17 + 7 * np.abs(np.random.default_rng(7).normal(0, 1, n)), index=dates, name="VIX")
    macro = pd.DataFrame(
        {
            "Treasury_10Y": 4.0 + np.cumsum(np.random.default_rng(1).normal(0, 0.008, n)),
            "Treasury_2Y": 4.2 + np.cumsum(np.random.default_rng(2).normal(0, 0.008, n)),
        },
        index=dates,
    )
    macro["Yield_Curve"] = macro["Treasury_10Y"] - macro["Treasury_2Y"]

    payloads = []
    for i, ticker in enumerate(cfg.tickers):
        price = bench if ticker == cfg.benchmark else synth_prices(10 + i, 0.0004 + i * 0.0001, n, dates)
        bench_close = bench["Close"] if ticker != cfg.benchmark else None
        feat = F.build_features(price, benchmark_close=bench_close, vix=vix, macro=macro)
        feat = F.add_targets(feat, cfg.horizons)
        fcols = F.feature_columns(feat)
        signals = []
        for h in cfg.horizons:
            tc = f"target_{h}d"
            cur = M.current_signal(feat, fcols, tc, cfg.model)
            if cur is None:
                continue
            res = M.walk_forward(feat, fcols, tc, cfg.model, cfg.model.oos_start)
            thr = M.dynamic_threshold(res, cfg.model)
            signals.append(
                {
                    "horizon": h,
                    "probUp": cur["probUp"],
                    "prediction": cur["prediction"],
                    "alert": M.classify_alert(cur["probUp"], thr),
                    "threshold": thr,
                    "oos": M.oos_metrics(res),
                    "backtest": M.backtest(res),
                }
            )
        diag = risk_mod.diagnose(ticker, feat)
        payloads.append(
            {
                "ticker": ticker,
                "asOf": feat.dropna(subset=fcols).index[-1].strftime("%Y-%m-%d"),
                "lastClose": diag["lastClose"],
                "signals": signals,
                "risk": diag,
            }
        )

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "portfolioName": cfg.portfolio_name,
        "primary": cfg.primary,
        "benchmark": cfg.benchmark,
        "horizons": cfg.horizons,
        "seed": True,
        "dataSource": "SEED (예시 데이터) — 첫 CI 실행 전 미리보기. 실제 시장 값이 아닙니다.",
        "macro": macro_mod.summarize(macro, vix),
        "tickers": payloads,
    }
    out = ROOT / "data" / "site-data.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote seed {out} ({len(payloads)} tickers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
