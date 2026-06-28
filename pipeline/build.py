"""Orchestrate the pipeline and write the site data artifact.

Run from the repo root:  python3 -m pipeline.build
Outputs: data/site-data.json

Core holdings get the full treatment (walk-forward backtest + multi-horizon
cards). The whole KR/US universe is screened at the trade horizon to produce
ranked daily trade ideas.
"""
from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime, timezone

from . import features as F
from . import macro as macro_mod
from . import model as M
from . import risk as risk_mod
from . import trade as trade_mod
from .config import REPO_ROOT, load_config
from .datafeed import fetch_macro, fetch_prices, fetch_vix

OUT = REPO_ROOT / "data" / "site-data.json"


def core_card(feat, fcols, ticker, cfg, diagnosis):
    """Full multi-horizon signal card + backtest for a held position."""
    signals = []
    for h in cfg.horizons:
        tc = f"target_{h}d"
        current = M.current_signal(feat, fcols, tc, cfg.model)
        if current is None:
            continue
        res = M.walk_forward(feat, fcols, tc, cfg.model, cfg.model.oos_start, h)
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
    return {
        "ticker": ticker,
        "asOf": feat.dropna(subset=fcols).index[-1].strftime("%Y-%m-%d"),
        "lastClose": diagnosis["lastClose"],
        "signals": signals,
        "risk": diagnosis,
    }


def main() -> int:
    cfg, download_universe = load_config()
    print(f"core={cfg.core} | universe={ {k: len(v) for k, v in cfg.universe.items()} } | FRED={cfg.has_fred}")

    prices = fetch_prices(download_universe, cfg.model.history_start)
    vix = fetch_vix(cfg.model.history_start)
    macro = fetch_macro(cfg, cfg.model.history_start)
    benchmark_close = prices[cfg.benchmark]["Close"] if cfg.benchmark in prices else None

    target_horizons = sorted(set(cfg.horizons) | {cfg.trade_horizon})
    all_tickers = list(dict.fromkeys([t for names in cfg.universe.values() for t in names] + cfg.core))

    core_cards = []
    ideas = []
    screened = []

    for ticker in all_tickers:
        if ticker not in prices:
            print(f"  skip {ticker}: no price data")
            continue
        try:
            bench = benchmark_close if ticker != cfg.benchmark else None
            feat = F.build_features(prices[ticker], benchmark_close=bench, vix=vix, macro=macro)
            feat = F.add_targets(feat, target_horizons)
            fcols = F.feature_columns(feat)
            diagnosis = risk_mod.diagnose(ticker, feat)
            region = cfg.region_of(ticker)

            # Trade-horizon screen for everyone.
            th = cfg.trade_horizon
            tsig = M.current_signal(feat, fcols, f"target_{th}d", cfg.model)
            if tsig is not None:
                stats = M.horizon_return_stats(feat, th)
                idea = trade_mod.build_idea(
                    ticker, region, tsig["probUp"], stats, th, tsig["asOf"], diagnosis["regime"]
                )
                screened.append(
                    {
                        "ticker": ticker,
                        "region": region,
                        "probUp": tsig["probUp"],
                        "regime": diagnosis["regime"],
                        "qualifies": idea is not None,
                    }
                )
                if idea is not None:
                    ideas.append(idea)

            if ticker in cfg.core:
                print(f"  core {ticker} ...")
                core_cards.append(core_card(feat, fcols, ticker, cfg, diagnosis))
        except Exception as exc:
            print(f"  error on {ticker}: {exc}")
            traceback.print_exc()

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "portfolioName": cfg.portfolio_name,
        "primary": cfg.primary,
        "benchmark": cfg.benchmark,
        "horizons": cfg.horizons,
        "tradeHorizon": cfg.trade_horizon,
        "dataSource": "Yahoo Finance (prices) + FRED (macro)" if cfg.has_fred else "Yahoo Finance (prices); FRED disabled",
        "tradeIdeas": trade_mod.rank_ideas(ideas),
        "screened": sorted(screened, key=lambda x: x["probUp"], reverse=True),
        "core": core_cards,
        "macro": macro_mod.summarize(macro, vix),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}: {len(core_cards)} core, {len(ideas)} ideas, {len(screened)} screened")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"pipeline failed: {exc}", file=sys.stderr)
        traceback.print_exc()
        if OUT.exists():
            print(f"keeping existing {OUT}", file=sys.stderr)
            sys.exit(0)
        sys.exit(1)
