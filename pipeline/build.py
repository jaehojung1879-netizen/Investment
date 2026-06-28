"""Orchestrate the pipeline and write the site data artifact.

Run from the repo root:  python3 -m pipeline.build
Outputs: data/site-data.json
"""
from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from . import features as F
from . import macro as macro_mod
from . import model as M
from . import risk as risk_mod
from .config import REPO_ROOT, load_config
from .datafeed import fetch_macro, fetch_prices, fetch_vix

OUT = REPO_ROOT / "data" / "site-data.json"


def build_ticker(ticker, price, benchmark_close, vix, macro, cfg):
    feat = F.build_features(price, benchmark_close=benchmark_close, vix=vix, macro=macro)
    feat = F.add_targets(feat, cfg.horizons)
    feature_cols = F.feature_columns(feat)

    signals = []
    for h in cfg.horizons:
        target_col = f"target_{h}d"
        current = M.current_signal(feat, feature_cols, target_col, cfg.model)
        if current is None:
            continue
        res = M.walk_forward(feat, feature_cols, target_col, cfg.model, cfg.model.oos_start)
        threshold = M.dynamic_threshold(res, cfg.model)
        signals.append(
            {
                "horizon": h,
                "probUp": current["probUp"],
                "prediction": current["prediction"],
                "alert": M.classify_alert(current["probUp"], threshold),
                "threshold": threshold,
                "oos": M.oos_metrics(res),
                "backtest": M.backtest(res),
            }
        )

    diagnosis = risk_mod.diagnose(ticker, feat)
    as_of = feat.dropna(subset=feature_cols).index[-1].strftime("%Y-%m-%d")
    return {
        "ticker": ticker,
        "asOf": as_of,
        "lastClose": diagnosis["lastClose"],
        "signals": signals,
        "risk": diagnosis,
    }


def main() -> int:
    cfg, download_universe = load_config()
    print(f"Tickers: {cfg.tickers} | benchmark: {cfg.benchmark} | FRED: {cfg.has_fred}")

    prices = fetch_prices(download_universe, cfg.model.history_start)
    vix = fetch_vix(cfg.model.history_start)
    macro = fetch_macro(cfg, cfg.model.history_start)
    benchmark_close = prices[cfg.benchmark]["Close"] if cfg.benchmark in prices else None

    ticker_payloads = []
    for ticker in cfg.tickers:
        if ticker not in prices:
            print(f"  skip {ticker}: no price data")
            continue
        try:
            print(f"  modelling {ticker} ...")
            bench = benchmark_close if ticker != cfg.benchmark else None
            ticker_payloads.append(
                build_ticker(ticker, prices[ticker], bench, vix, macro, cfg)
            )
        except Exception as exc:
            print(f"  error modelling {ticker}: {exc}")
            traceback.print_exc()

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "portfolioName": cfg.portfolio_name,
        "primary": cfg.primary,
        "benchmark": cfg.benchmark,
        "horizons": cfg.horizons,
        "dataSource": "Yahoo Finance (prices) + FRED (macro)" if cfg.has_fred else "Yahoo Finance (prices); FRED disabled (no key)",
        "macro": macro_mod.summarize(macro, vix),
        "tickers": ticker_payloads,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(ticker_payloads)} tickers)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # keep a stale artifact rather than failing the deploy
        print(f"pipeline failed: {exc}", file=sys.stderr)
        traceback.print_exc()
        if OUT.exists():
            print(f"keeping existing {OUT}", file=sys.stderr)
            sys.exit(0)
        sys.exit(1)
