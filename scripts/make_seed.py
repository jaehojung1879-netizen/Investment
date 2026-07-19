"""Exercise the v2 pipeline on SYNTHETIC prices and write data/site-data.json.

Dev/preview only — every number here is illustrative. Because the data is
synthetic, the artifact is stamped dataMode=synthetic and is
recommendationsBlocked (modelsTrained=0), so the site shows the RESEARCH views,
regime and entry states but WITHHOLDS sleeve weights and short-term ideas — the
honest blocked state. Real values come from `python -m pipeline.build` in CI
(which needs FRED/Yahoo network access + FRED_API_KEY).

Run: python3 scripts/make_seed.py
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

from pipeline import build as B  # noqa: E402
from pipeline import entry as entry_mod  # noqa: E402
from pipeline import expert_consensus as expert_mod  # noqa: E402
from pipeline import features as F  # noqa: E402
from pipeline import longterm as longterm_mod  # noqa: E402
from pipeline import macro as macro_mod  # noqa: E402
from pipeline import model as M  # noqa: E402
from pipeline import provenance as prov_mod  # noqa: E402
from pipeline import regime as regime_mod  # noqa: E402
from pipeline import risk as risk_mod  # noqa: E402
from pipeline import sectors as SECT  # noqa: E402
from pipeline import sentiment as sentiment_mod  # noqa: E402
from pipeline import trade as trade_mod  # noqa: E402
from pipeline.config import load_config  # noqa: E402


def synth(seed, drift, n, dates):
    rng = np.random.default_rng(seed)
    ret = rng.normal(drift, 0.013, n)
    ret[int(n * 0.55):int(n * 0.62)] -= 0.012
    close = 100 * np.exp(np.cumsum(ret))
    return pd.DataFrame(
        {"Open": close * (1 + rng.normal(0, 0.002, n)), "High": close * (1 + np.abs(rng.normal(0, 0.004, n))),
         "Low": close * (1 - np.abs(rng.normal(0, 0.004, n))), "Close": close,
         "Volume": rng.integers(1_000_000, 5_000_000, n).astype(float)}, index=dates)


def synth_fundamentals(ticker, seed):
    rng = np.random.default_rng(seed)
    ey = float(np.clip(rng.normal(0.05, 0.02), 0.01, 0.12))
    return {
        "trailingPE": round(1 / ey, 1), "forwardPE": round(1 / (ey * 1.05), 1),
        "priceToBook": round(float(np.clip(rng.normal(3, 1.5), 0.4, 8)), 2),
        "bookYield": round(float(np.clip(rng.normal(0.3, 0.15), 0.05, 1.2)), 3),
        "fcfYield": round(float(np.clip(rng.normal(0.04, 0.02), -0.02, 0.1)), 3),
        "roe": round(float(np.clip(rng.normal(0.15, 0.08), -0.05, 0.4)), 3),
        "operatingMargin": round(float(np.clip(rng.normal(0.15, 0.08), 0.0, 0.4)), 3),
        "profitMargin": round(float(np.clip(rng.normal(0.1, 0.06), -0.02, 0.3)), 3),
        "debtToEquity": round(float(np.clip(rng.normal(90, 60), 5, 400)), 1),
        "earningsGrowth": round(float(np.clip(rng.normal(0.08, 0.15), -0.3, 0.5)), 3),
        "sector": SECT.sector_of(ticker),
    }


def main() -> int:
    cfg, _ = load_config()
    n = 1700
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    bench = synth(99, 0.0003, n, dates)
    vix = pd.Series(17 + 7 * np.abs(np.random.default_rng(7).normal(0, 1, n)), index=dates, name="VIX")
    macro = pd.DataFrame({
        "Treasury_10Y": 4.0 + np.cumsum(np.random.default_rng(1).normal(0, 0.008, n)),
        "Treasury_2Y": 4.2 + np.cumsum(np.random.default_rng(2).normal(0, 0.008, n)),
        "FedFunds": 4.3 + np.cumsum(np.random.default_rng(3).normal(0, 0.003, n)),
        "HY_Spread": 3.5 + np.cumsum(np.random.default_rng(4).normal(0, 0.01, n)),
        "IG_Spread": 1.2 + np.cumsum(np.random.default_rng(11).normal(0, 0.004, n)),
        "Real_10Y": 1.8 + np.cumsum(np.random.default_rng(12).normal(0, 0.006, n)),
        "Breakeven_10Y": 2.3 + np.cumsum(np.random.default_rng(13).normal(0, 0.004, n)),
        "USD_KRW": 1350 + np.cumsum(np.random.default_rng(5).normal(0, 1.5, n)),
        "Korea_10Y": 3.3 + np.cumsum(np.random.default_rng(6).normal(0, 0.006, n)),
        "Korea_3M": 3.4 + np.cumsum(np.random.default_rng(8).normal(0, 0.004, n)),
    }, index=dates)
    macro["Yield_Curve"] = macro["Treasury_10Y"] - macro["Treasury_2Y"]
    # A few monthly macro series so the regime engine has >1 axis of coverage.
    mdates = pd.date_range(end=dates[-1], periods=60, freq="ME")
    for name, base, slope, sd, sd_seed in [("CFNAI", 0.0, 0.002, 0.2, 21), ("Core_CPI", 300, 0.4, 0.3, 22),
                                           ("Unemployment", 4.0, -0.005, 0.1, 23), ("Payrolls", 155000, 120, 400, 24)]:
        rng = np.random.default_rng(sd_seed)
        macro[name] = pd.Series(base + slope * np.arange(60) + rng.normal(0, sd, 60), index=mdates).reindex(dates).ffill()

    th = cfg.trade_horizon
    target_h = sorted(set(cfg.horizons) | {th})
    from pipeline import universe as universe_mod
    resolved_universe, resolved_names = universe_mod.resolve(cfg)
    all_t = list(dict.fromkeys([t for names in resolved_universe.values() for t in names] + cfg.core))

    core_cards, ideas, screened, details, diags, entry_feats, fundamentals = [], [], [], {}, {}, {}, {}
    for i, tk in enumerate(all_t):
        price = bench if tk == cfg.benchmark else synth(10 + i, 0.0004 + i * 0.00005, n, dates)
        bclose = bench["Close"] if tk != cfg.benchmark else None
        feat = F.build_features(price, benchmark_close=bclose, vix=vix, macro=macro)
        feat = F.add_targets(feat, target_h)
        fcols = F.feature_columns(feat)
        diag = risk_mod.diagnose(tk, feat)
        diags[tk] = diag
        region = cfg.region_of(tk)
        tsig = M.current_signal(feat, fcols, f"target_{th}d", cfg.model)
        vsurge = round(1.0 + abs(np.random.default_rng(i).normal(0, 0.4)), 2)
        entry_feats[tk] = entry_mod.entry_features(feat, volume_surge=vsurge)
        if tk != cfg.benchmark:
            fundamentals[tk] = synth_fundamentals(tk, 700 + i)
        details[tk] = {"volSurge": vsurge, "region": region, "modelScore": tsig["probUp"] if tsig else None,
                       "probUp": None, "regime": diag["regime"], "lastClose": diag["lastClose"],
                       "ma50": diag["ma50"], "ma200": diag["ma200"], "rsi14": diag["rsi14"],
                       "realizedVol": diag["realizedVol"], "maxDrawdown252d": diag["maxDrawdown252d"],
                       "relMomentum": diag["relMomentum"], "pct52wHigh": diag["pct52wHigh"],
                       "mom63": round(diag["mom63"] * 100, 1) if diag["mom63"] is not None else None,
                       "riskFlags": [f["message"] for f in diag["riskFlags"]]}
        if tsig is not None:
            stats = M.horizon_return_stats(feat, th)
            idea = trade_mod.build_idea(tk, region, tsig["probUp"], stats, th, tsig["asOf"], diag["regime"], diag)
            screened.append({"ticker": tk, "region": region, "modelScore": tsig["probUp"], "probUp": None,
                             "regime": diag["regime"], "qualifies": idea is not None, "aboveMA50": diag["aboveMA50"],
                             "aboveMA200": diag["aboveMA200"], "mom63": diag["mom63"], "volSurge": vsurge})
            if idea:
                ideas.append(idea)
        if tk in cfg.core:
            sigs = []
            for h in cfg.horizons:
                cur = M.current_signal(feat, fcols, f"target_{h}d", cfg.model)
                if cur is None:
                    continue
                res = M.walk_forward(feat, fcols, f"target_{h}d", cfg.model, cfg.model.oos_start, h)
                thr = M.dynamic_threshold(res, cfg.model)
                sigs.append({"horizon": h, "probUp": cur["probUp"], "prediction": cur["prediction"],
                             "alert": "PAPER ONLY", "threshold": thr, "oos": M.oos_metrics(res), "backtest": M.backtest(res)})
            core_cards.append({"ticker": tk, "asOf": feat.dropna(subset=fcols).index[-1].strftime("%Y-%m-%d"),
                               "lastClose": diag["lastClose"], "signals": sigs, "risk": diag})

    sent = sentiment_mod.summarize(screened, macro, vix)
    macro_regime = regime_mod.build(macro, vix)
    macro_summary = macro_mod.summarize(macro, vix, macro_regime)
    expert = expert_mod.build()

    screen_table = [{k: r.get(k) for k in ("ticker", "region", "modelScore", "probUp", "regime", "qualifies")}
                    for r in sorted(screened, key=lambda x: x.get("modelScore") or -1, reverse=True)]
    flows = {}
    for region in ("KR", "US"):
        cand = [{"ticker": r["ticker"], "region": region, "volSurge": r["volSurge"],
                 "mom63": round((r["mom63"] or 0) * 100, 1), "regime": r["regime"]}
                for r in screened if r["region"] == region and r.get("volSurge") and (r.get("mom63") or 0) > 0]
        flows[region] = sorted(cand, key=lambda x: x["volSurge"], reverse=True)[:6]

    # Long-term v2. Synthetic => blocked => weights withheld (honest).
    bench_by_region = {"US": bench["Close"], "KR": None}
    long_term = longterm_mod.build(resolved_universe, {tk: (bench if tk == cfg.benchmark else synth(10 + i, 0.0004 + i * 0.00005, n, dates))
                                                       for i, tk in enumerate(all_t)},
                                   fundamentals, diags, cfg_lt=cfg.longterm,
                                   bench_by_region=bench_by_region, blocked=True)
    long_term = B._attach_entry_states(long_term, entry_feats, cfg.longterm)

    from pipeline import indices as indices_mod
    idx_dates = dates[-320:]
    seed_indices = []
    idx_bases = [6200, 20300, 44600, 5200, 2800, 850, 1370, 17, 105000, 3300, 104]
    for j, spec in enumerate(indices_mod.SPEC):
        base = idx_bases[j % len(idx_bases)]
        walk = np.cumsum(np.random.default_rng(100 + j).normal(0.0004, 0.01, len(idx_dates)))
        close = pd.Series(base * np.exp(walk), index=idx_dates)
        row = indices_mod.summarize_close(spec, close, "SEED")
        if row:
            seed_indices.append(row)

    from pipeline import direction as direction_mod
    from pipeline import rotation as rotation_mod
    dir_symbols = [a["ticker"] for a in direction_mod.ASSETS] + list(direction_mod.TILT.values())
    rot_symbols = [t for t, _ in rotation_mod.US_SECTORS + rotation_mod.KR_SECTORS + rotation_mod.FACTORS]
    rot_symbols += [rotation_mod.US_BENCH, rotation_mod.KR_BENCH]
    seed_closes = {}
    for j, sym in enumerate(dict.fromkeys(dir_symbols + rot_symbols)):
        walk = np.cumsum(np.random.default_rng(500 + j).normal(0.0003 + (j % 5) * 0.0001, 0.011, n))
        seed_closes[sym] = pd.Series(100 * np.exp(walk), index=dates)
    direction = direction_mod.build(sentiment=sent, macro_summary=macro_summary, indices=seed_indices, closes=seed_closes)
    rotation = rotation_mod.build(closes=seed_closes)

    payload = {
        "portfolioName": cfg.portfolio_name, "primary": cfg.primary, "benchmark": cfg.benchmark,
        "horizons": cfg.horizons, "tradeHorizon": th, "names": resolved_names,
        "seed": True, "stale": False, "runMode": cfg.run_mode,
        "recommendationsBlocked": True, "blockReasons": ["synthetic_data", "models_trained_zero"],
        "dataSource": "SEED (예시) — 합성 데이터", "indices": seed_indices, "direction": direction,
        "rotation": rotation, "longTerm": long_term, "macroRegime": macro_regime, "expertConsensus": expert,
        "tradeIdeas": {"KR": [], "US": []}, "screened": screen_table, "details": details, "flows": flows,
        "sentiment": sent, "core": core_cards, "macro": macro_summary,
        "meta": {"modelsTrained": 0, "universeScreened": len(screened), "syntheticData": True,
                 "latestDataDate": dates[-1].strftime("%Y-%m-%d"), "sourceAsOf": dates[-1].strftime("%Y-%m-%d"),
                 "fredEnabled": True, "ecosEnabled": False, "macroCoverage": macro_regime.get("coverage"),
                 "elapsedSec": 0, "tickersRequested": len(all_t), "tickersFetched": len(all_t),
                 "coveragePct": 100.0, "coverageFloor": cfg.coverage_floor, "missingSample": [],
                 "indicesFetched": len(seed_indices), "fundamentalsCovered": len(fundamentals)},
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }
    prov_mod.stamp(payload, cfg.run_mode)
    out = ROOT / "data" / "site-data.json"
    out.write_text(B._dumps(payload) + "\n", encoding="utf-8")
    print(f"wrote {out}: {len(core_cards)} core, {len(screened)} screened, "
          f"regime={macro_regime['regime']} (conf {macro_regime['confidence']}), "
          f"longterm regions={list((long_term or {}).get('regions', {}))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
