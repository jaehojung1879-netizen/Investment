"""Orchestrate the pipeline and write the site data artifact.

Run from the repo root:  python3 -m pipeline.build
Outputs: data/site-data.json

Core holdings get the full treatment (purged walk-forward backtest + cards).
The whole dynamically-resolved KR/US universe is screened at the trade horizon
for daily trade ideas and for the market-sentiment panel.
"""
from __future__ import annotations

import json
import sys
import time
import traceback
import warnings
from datetime import datetime, timezone

from . import features as F
from . import macro as macro_mod
from . import model as M
from . import risk as risk_mod
from . import sentiment as sentiment_mod
from . import trade as trade_mod
from . import universe as universe_mod
from .config import REPO_ROOT, load_config
from .datafeed import fetch_macro, fetch_prices, fetch_vix

# These are expected for short calibration windows; they don't affect results.
warnings.filterwarnings("ignore", message="The least populated class")
warnings.filterwarnings("ignore", message="Number of classes in training fold")

OUT = REPO_ROOT / "data" / "site-data.json"


def core_card(feat, fcols, ticker, cfg, diagnosis):
    """Full multi-horizon signal card + backtest for a held position."""
    signals = []
    fits = 0
    for h in cfg.horizons:
        tc = f"target_{h}d"
        current = M.current_signal(feat, fcols, tc, cfg.model)
        if current is None:
            continue
        fits += 1
        res = M.walk_forward(feat, fcols, tc, cfg.model, cfg.model.oos_start, h)
        fits += max(0, len(res) // cfg.model.step_size)
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
    card = {
        "ticker": ticker,
        "asOf": feat.dropna(subset=fcols).index[-1].strftime("%Y-%m-%d"),
        "lastClose": diagnosis["lastClose"],
        "signals": signals,
        "risk": diagnosis,
    }
    return card, fits


def run(cfg) -> dict:
    universe, names = universe_mod.resolve(cfg)
    download = list(dict.fromkeys(
        [t for names_ in universe.values() for t in names_] + cfg.core + [cfg.benchmark]
    ))
    print(f"core={cfg.core} | universe={ {k: len(v) for k, v in universe.items()} } | "
          f"download={len(download)} | FRED={cfg.has_fred}")

    prices = fetch_prices(download, cfg.model.history_start)
    vix = fetch_vix(cfg.model.history_start)
    macro = fetch_macro(cfg, cfg.model.history_start)
    benchmark_close = prices[cfg.benchmark]["Close"] if cfg.benchmark in prices else None

    th = cfg.trade_horizon
    target_horizons = sorted(set(cfg.horizons) | {th})
    all_tickers = list(dict.fromkeys([t for names_ in universe.values() for t in names_] + cfg.core))

    core_cards, ideas, screened = [], [], []
    fits = 0
    latest_date = None

    for ticker in all_tickers:
        if ticker not in prices:
            continue
        try:
            bench = benchmark_close if ticker != cfg.benchmark else None
            feat = F.build_features(prices[ticker], benchmark_close=bench, vix=vix, macro=macro)
            feat = F.add_targets(feat, target_horizons)
            fcols = F.feature_columns(feat)
            clean = feat.dropna(subset=fcols)
            if clean.empty:
                continue
            latest_date = max(latest_date, clean.index[-1]) if latest_date else clean.index[-1]
            diagnosis = risk_mod.diagnose(ticker, feat)
            region = cfg.region_of(ticker)

            tsig = M.current_signal(feat, fcols, f"target_{th}d", cfg.model)
            if tsig is not None:
                fits += 1
                stats = M.horizon_return_stats(feat, th)
                idea = trade_mod.build_idea(ticker, region, tsig["probUp"], stats, th, tsig["asOf"], diagnosis["regime"])
                screened.append({
                    "ticker": ticker, "region": region, "probUp": tsig["probUp"],
                    "regime": diagnosis["regime"], "qualifies": idea is not None,
                    "aboveMA50": diagnosis["aboveMA50"], "aboveMA200": diagnosis["aboveMA200"],
                    "mom63": diagnosis["mom63"],
                })
                if idea is not None:
                    ideas.append(idea)

            if ticker in cfg.core:
                print(f"  core {ticker} ...")
                card, cfits = core_card(feat, fcols, ticker, cfg, diagnosis)
                core_cards.append(card)
                fits += cfits
        except Exception as exc:
            print(f"  error on {ticker}: {exc}")

    sentiment = sentiment_mod.summarize(screened, macro, vix)
    # Trim breadth helper fields out of the stored screen table.
    screen_table = [
        {k: r[k] for k in ("ticker", "region", "probUp", "regime", "qualifies")}
        for r in sorted(screened, key=lambda x: x["probUp"], reverse=True)
    ]

    return {
        "portfolioName": cfg.portfolio_name,
        "primary": cfg.primary,
        "benchmark": cfg.benchmark,
        "horizons": cfg.horizons,
        "tradeHorizon": th,
        "names": names,
        "dataSource": "Yahoo Finance (prices) + FRED (macro)" if cfg.has_fred else "Yahoo Finance (prices); FRED disabled",
        "tradeIdeas": trade_mod.rank_ideas(ideas),
        "screened": screen_table,
        "sentiment": sentiment,
        "core": core_cards,
        "macro": macro_mod.summarize(macro, vix),
        "meta": {
            "modelsTrained": fits,
            "universeScreened": len(screened),
            "latestDataDate": latest_date.strftime("%Y-%m-%d") if latest_date is not None else None,
            "fredEnabled": cfg.has_fred,
        },
    }


def main() -> int:
    cfg, _ = load_config()
    t0 = time.time()
    payload = run(cfg)
    payload["generatedAt"] = datetime.now(timezone.utc).isoformat()
    payload["stale"] = False
    payload["meta"]["elapsedSec"] = round(time.time() - t0, 1)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    m = payload["meta"]
    print(f"wrote {OUT}: {len(payload['core'])} core, universe {m['universeScreened']}, "
          f"{m['modelsTrained']} model fits, {m['elapsedSec']}s, data as of {m['latestDataDate']}")
    return 0


def _mark_stale(reason: str) -> None:
    """On hard failure, flag the existing artifact as stale rather than passing
    it off as a fresh successful build."""
    if not OUT.exists():
        return
    try:
        data = json.loads(OUT.read_text(encoding="utf-8"))
        data["stale"] = True
        data.setdefault("meta", {})["buildError"] = reason[:300]
        data["staleCheckedAt"] = datetime.now(timezone.utc).isoformat()
        OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"marked existing {OUT} as STALE: {reason}", file=sys.stderr)
    except Exception as exc:
        print(f"could not mark stale: {exc}", file=sys.stderr)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"pipeline failed: {exc}", file=sys.stderr)
        traceback.print_exc()
        _mark_stale(str(exc))
        # Keep deploy green so the (now clearly-flagged-stale) site still serves.
        sys.exit(0)
