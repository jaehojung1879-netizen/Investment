"""Orchestrate the pipeline and write the site data artifact.

Run from the repo root:  python3 -m pipeline.build
Outputs: data/site-data.json

Core holdings get the full treatment (purged walk-forward backtest + cards).
The whole dynamically-resolved KR/US universe is screened at the trade horizon
for daily trade ideas and for the market-sentiment panel.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import sys
import time
import traceback
import warnings
from datetime import datetime, timezone
from numbers import Integral, Real

from . import direction as direction_mod
from . import features as F
from . import indices as indices_mod
from . import macro as macro_mod
from . import model as M
from . import risk as risk_mod
from . import rotation as rotation_mod
from . import sentiment as sentiment_mod
from . import trade as trade_mod
from . import quality as quality_mod
from . import universe as universe_mod
from .config import REPO_ROOT, load_config
from .datafeed import fetch_macro, fetch_prices, fetch_vix

# These are expected for short calibration windows; they don't affect results.
warnings.filterwarnings("ignore", message="The least populated class")
warnings.filterwarnings("ignore", message="Number of classes in training fold")

OUT = REPO_ROOT / "data" / "site-data.json"
AUDIT_OUT = REPO_ROOT / "data" / "audit.json"


def _json_default(obj):
    """Last-resort encoder so a stray pandas/NumPy value can never break the
    build (and block the Pages deploy) the way a raw Timestamp once did.

    The pipeline should hand plain Python types to ``json.dumps``; anything that
    slips through — a ``Timestamp``, ``datetime``, NumPy scalar, or array — is
    coerced here to a JSON-safe form instead of raising ``TypeError``.
    """
    # pandas Timestamp / NaT and stdlib datetime/date all expose isoformat().
    if isinstance(obj, (_dt.datetime, _dt.date)):
        return obj.isoformat()
    isoformat = getattr(obj, "isoformat", None)
    if callable(isoformat):
        try:
            return isoformat()
        except Exception:
            pass
    item = getattr(obj, "item", None)  # NumPy scalar -> native Python scalar
    if callable(item):
        try:
            return obj.item()
        except Exception:
            pass
    tolist = getattr(obj, "tolist", None)  # NumPy array / pandas Index/Series
    if callable(tolist):
        try:
            return obj.tolist()
        except Exception:
            pass
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


def _json_sanitize(obj):
    """Recursively replace non-finite floats (NaN/±Inf) with ``None``.

    We serialize with ``allow_nan=False`` so the artifact is strictly valid
    JSON (the site's ``JSON.parse`` rejects the bare ``NaN`` token). A NaN metric
    means "not available", so ``null`` is the honest representation — and letting
    one slip through would otherwise abort the write and block the Pages deploy.
    Integers and booleans are left untouched; other objects fall through to
    ``_json_default`` at encode time.
    """
    if isinstance(obj, dict):
        return {k: _json_sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_sanitize(v) for v in obj]
    # Real, non-integer numbers (Python float, NumPy float32/64, ...).
    if isinstance(obj, Real) and not isinstance(obj, (bool, Integral)):
        try:
            f = float(obj)
        except (TypeError, ValueError):
            return obj
        return f if math.isfinite(f) else None
    return obj


def _dumps(payload) -> str:
    return json.dumps(_json_sanitize(payload), ensure_ascii=False, indent=2, allow_nan=False, default=_json_default)


def volume_surge(price) -> float | None:
    """Recent 5-day average volume vs the trailing 60-day average.

    A reading > 1 means money/attention is rushing in relative to normal — a
    crude but self-contained proxy for where liquidity is rotating.
    """
    if "Volume" not in price:
        return None
    vol = price["Volume"].dropna()
    if len(vol) < 60:
        return None
    recent = vol.iloc[-5:].mean()
    base = vol.iloc[-60:].mean()
    if not base or base <= 0:
        return None
    return round(float(recent / base), 2)


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
                "alert": "PAPER ONLY",
                "threshold": threshold,
                "oos": M.oos_metrics(res, threshold),
                "backtest": M.backtest(res, region=cfg.region_of(ticker)),
                "foldAudit": res[[c for c in res.columns if c.startswith("fold")]].drop_duplicates().to_dict("records") if not res.empty else [],
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

    # Core + benchmark need full history (walk-forward back to 2020); the broad
    # screening universe only needs a few years, so fetch it on a shorter window
    # to keep downloads fast for a large list.
    core_set = list(dict.fromkeys(cfg.core + [cfg.benchmark]))
    universe_only = [t for t in download if t not in core_set]
    prices = fetch_prices(core_set, cfg.model.history_start)
    prices.update(fetch_prices(universe_only, cfg.model.screen_history_start))
    missing = [t for t in download if t not in prices]
    coverage = round(100 * len(prices) / len(download), 1) if download else 0.0
    missing_core = [t for t in cfg.core if t not in prices]
    if missing_core or coverage < 95:
        raise RuntimeError(f"critical price coverage failure: coverage={coverage}%, missing_core={missing_core[:10]}")
    vix = fetch_vix(cfg.model.history_start)
    macro = fetch_macro(cfg, cfg.model.history_start)

    # Market tape (S&P 500 / NASDAQ / KOSPI / ...). Never let it kill a build.
    try:
        market_indices = indices_mod.fetch()
    except Exception as exc:
        print(f"  warning: index tape failed: {exc}")
        market_indices = []
    benchmark_close = prices[cfg.benchmark]["Close"] if cfg.benchmark in prices else None

    th = cfg.trade_horizon
    target_horizons = sorted(set(cfg.horizons) | {th})
    all_tickers = list(dict.fromkeys([t for names_ in universe.values() for t in names_] + cfg.core))

    core_cards, ideas, screened = [], [], []
    details = {}
    audit = {"folds": {}, "oos": {}, "eligibility": {}, "warnings": ["PAPER_ONLY=true", "survivorship_bias_unresolved", "macro_vintage_revision_bias_possible"]}
    fits = 0
    latest_date = None
    errors = []

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
            vsurge = volume_surge(prices[ticker])

            tsig = M.current_signal(feat, fcols, f"target_{th}d", cfg.model)
            details[ticker] = {
                "volSurge": vsurge,
                "region": region,
                "modelScore": tsig["probUp"] if tsig else None,
                "probUp": None,
                "regime": diagnosis["regime"],
                "lastClose": diagnosis["lastClose"],
                "ma50": diagnosis["ma50"], "ma200": diagnosis["ma200"],
                "rsi14": diagnosis["rsi14"], "realizedVol": diagnosis["realizedVol"],
                "maxDrawdown252d": diagnosis["maxDrawdown252d"],
                "relMomentum": diagnosis["relMomentum"], "pct52wHigh": diagnosis["pct52wHigh"],
                "mom63": round(diagnosis["mom63"] * 100, 1) if diagnosis["mom63"] is not None else None,
                "riskFlags": [f["message"] for f in diagnosis["riskFlags"]],
            }
            if tsig is not None:
                fits += 1
                stats = M.horizon_return_stats(feat, th)
                tres = M.walk_forward(feat, fcols, f"target_{th}d", cfg.model, cfg.model.oos_start, th)
                threshold = M.dynamic_threshold(tres, cfg.model)
                quality = M.oos_metrics(tres, threshold)
                audit["oos"][ticker] = quality
                if not tres.empty:
                    audit["folds"][ticker] = tres[[c for c in tres.columns if c.startswith("fold")]].drop_duplicates().to_dict("records")
                idea = trade_mod.build_idea(ticker, region, tsig["probUp"], stats, th, tsig["asOf"], diagnosis["regime"], diagnosis, quality)
                screened.append({
                    "ticker": ticker, "region": region, "modelScore": tsig["probUp"], "probUp": None,
                    "qualityGrade": quality.get("qualityGrade", "REJECT"), "eligible": quality.get("eligible", False),
                    "eligibilityReasons": quality.get("eligibilityReasons", []),
                    "regime": diagnosis["regime"], "qualifies": idea is not None,
                    "aboveMA50": diagnosis["aboveMA50"], "aboveMA200": diagnosis["aboveMA200"],
                    "mom63": diagnosis["mom63"], "volSurge": vsurge,
                })
                if idea is not None:
                    ideas.append(idea)

            if ticker in cfg.core:
                print(f"  core {ticker} ...")
                card, cfits = core_card(feat, fcols, ticker, cfg, diagnosis)
                core_cards.append(card)
                fits += cfits
        except Exception as exc:
            msg = f"{ticker}: {exc}"
            errors.append(msg)
            print(f"  error on {ticker}: {exc}")

    sentiment = sentiment_mod.summarize(screened, macro, vix)
    macro_summary = macro_mod.summarize(macro, vix)

    # Direction compass + sector/factor rotation are additive tools; a failed
    # download must never take the whole build down with it.
    try:
        direction = direction_mod.build(sentiment=sentiment, macro_summary=macro_summary,
                                        indices=market_indices)
    except Exception as exc:
        print(f"  warning: direction compass failed: {exc}")
        direction = None
    try:
        rotation = rotation_mod.build()
    except Exception as exc:
        print(f"  warning: rotation failed: {exc}")
        rotation = None
    # Trim breadth helper fields out of the stored screen table.
    screen_table = [
        {k: r.get(k) for k in ("ticker", "region", "modelScore", "probUp", "regime", "qualifies", "eligible", "qualityGrade", "eligibilityReasons")}
        for r in sorted(screened, key=lambda x: x.get("modelScore") or -1, reverse=True)
    ]

    # Money-flow proxy: where is liquidity rotating? Volume surging into names
    # that are also rising (positive momentum), ranked per region.
    flows = {}
    for region in ("KR", "US"):
        cand = [
            {"ticker": r["ticker"], "region": region,
             "volSurge": r["volSurge"], "mom63": round((r["mom63"] or 0) * 100, 1),
             "regime": r["regime"]}
            for r in screened
            if r["region"] == region and r.get("volSurge") and (r.get("mom63") or 0) > 0
        ]
        flows[region] = sorted(cand, key=lambda x: x["volSurge"], reverse=True)[:6]

    eligible_count = sum(1 for r in screened if r.get("eligible"))
    payload = {
        "portfolioName": cfg.portfolio_name,
        "primary": cfg.primary,
        "benchmark": cfg.benchmark,
        "horizons": cfg.horizons,
        "tradeHorizon": th,
        "names": names,
        "dataSource": "Yahoo Finance (prices) + FRED (macro)" if cfg.has_fred else "Yahoo Finance (prices); FRED disabled",
        "indices": market_indices,
        "direction": direction,
        "rotation": rotation,
        "tradeIdeas": trade_mod.rank_ideas(ideas),
        "recommendationsBlocked": True,
        "paperOnly": True,
        "screened": screen_table,
        "details": details,
        "flows": flows,
        "sentiment": sentiment,
        "core": core_cards,
        "macro": macro_summary,
        "meta": {
            "modelsTrained": fits,
            "universeScreened": len(screened),
            "latestDataDate": latest_date.strftime("%Y-%m-%d") if latest_date is not None else None,
            "fredEnabled": cfg.has_fred,
            "tickersRequested": len(download),
            "tickersFetched": len(prices),
            "coveragePct": coverage,
            "missingSample": missing[:10],
            "indicesFetched": len(market_indices),
            "eligibleSignals": eligible_count,
            "paperOnly": True,
            "survivorshipBias": "unresolved_current_constituents_only",
            "coreErrors": errors,
            "pipelineErrors": errors,
        },
    }
    blocked, reasons = quality_mod.recommendations_blocked(payload)
    payload["recommendationsBlocked"] = blocked or True
    payload["blockReasons"] = sorted(set(reasons + ["paper_only_default", "live_recommendations_disabled_pending_validation"]))
    payload["audit"] = audit
    return payload


def main() -> int:
    cfg, _ = load_config()
    t0 = time.time()
    payload = run(cfg)
    payload["generatedAt"] = datetime.now(timezone.utc).isoformat()
    payload["stale"] = False
    payload["meta"]["elapsedSec"] = round(time.time() - t0, 1)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(_dumps(payload) + "\n", encoding="utf-8")
    AUDIT_OUT.write_text(_dumps({"generatedAt": payload["generatedAt"], "meta": payload["meta"], "audit": payload.get("audit", {}), "blockReasons": payload.get("blockReasons", [])}) + "\n", encoding="utf-8")
    m = payload["meta"]
    print(f"wrote {OUT}: {len(payload['core'])} core, universe {m['universeScreened']}, "
          f"coverage {m['coveragePct']}%, indices {m['indicesFetched']}, "
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
        OUT.write_text(_dumps(data) + "\n", encoding="utf-8")
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
        # Hard failures must stop CI/Pages deployment.
        sys.exit(1)
