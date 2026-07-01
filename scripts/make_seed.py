"""Exercise the pipeline on synthetic prices and write data/site-data.json.

Dev/preview utility only — numbers are illustrative. Real values come from
`python -m pipeline.build` in CI. Run: python3 scripts/make_seed.py
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
        "USD_KRW": 1350 + np.cumsum(np.random.default_rng(5).normal(0, 1.5, n)),
        "Korea_10Y": 3.3 + np.cumsum(np.random.default_rng(6).normal(0, 0.006, n)),
        "Korea_3M": 3.4 + np.cumsum(np.random.default_rng(8).normal(0, 0.004, n)),
    }, index=dates)
    macro["Yield_Curve"] = macro["Treasury_10Y"] - macro["Treasury_2Y"]

    th = cfg.trade_horizon
    target_h = sorted(set(cfg.horizons) | {th})
    from pipeline import universe as universe_mod
    resolved_universe, resolved_names = universe_mod.resolve(cfg)
    all_t = list(dict.fromkeys([t for names in resolved_universe.values() for t in names] + cfg.core))

    core_cards, ideas, screened, details = [], [], [], {}
    for i, tk in enumerate(all_t):
        price = bench if tk == cfg.benchmark else synth(10 + i, 0.0004 + i * 0.00005, n, dates)
        bclose = bench["Close"] if tk != cfg.benchmark else None
        feat = F.build_features(price, benchmark_close=bclose, vix=vix, macro=macro)
        feat = F.add_targets(feat, target_h)
        fcols = F.feature_columns(feat)
        diag = risk_mod.diagnose(tk, feat)
        region = cfg.region_of(tk)
        tsig = M.current_signal(feat, fcols, f"target_{th}d", cfg.model)
        vsurge = round(1.0 + abs(np.random.default_rng(i).normal(0, 0.4)), 2)
        details[tk] = {"volSurge": vsurge, "region": region, "probUp": tsig["probUp"] if tsig else None, "regime": diag["regime"],
                       "lastClose": diag["lastClose"], "ma50": diag["ma50"], "ma200": diag["ma200"],
                       "rsi14": diag["rsi14"], "realizedVol": diag["realizedVol"], "maxDrawdown252d": diag["maxDrawdown252d"],
                       "relMomentum": diag["relMomentum"], "pct52wHigh": diag["pct52wHigh"],
                       "mom63": round(diag["mom63"] * 100, 1) if diag["mom63"] is not None else None,
                       "riskFlags": [f["message"] for f in diag["riskFlags"]]}
        if tsig is not None:
            stats = M.horizon_return_stats(feat, th)
            idea = trade_mod.build_idea(tk, region, tsig["probUp"], stats, th, tsig["asOf"], diag["regime"], diag)
            screened.append({"ticker": tk, "region": region, "probUp": tsig["probUp"], "regime": diag["regime"],
                             "qualifies": idea is not None, "aboveMA50": diag["aboveMA50"],
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
                             "alert": M.classify_alert(cur["probUp"], thr), "threshold": thr,
                             "oos": M.oos_metrics(res), "backtest": M.backtest(res)})
            core_cards.append({"ticker": tk, "asOf": feat.dropna(subset=fcols).index[-1].strftime("%Y-%m-%d"),
                               "lastClose": diag["lastClose"], "signals": sigs, "risk": diag})

    from pipeline import sentiment as sentiment_mod
    sent = sentiment_mod.summarize(screened, macro, vix)
    screen_table = [{k: r[k] for k in ("ticker", "region", "probUp", "regime", "qualifies")}
                    for r in sorted(screened, key=lambda x: x["probUp"], reverse=True)]
    flows = {}
    for region in ("KR", "US"):
        cand = [{"ticker": r["ticker"], "region": region, "volSurge": r["volSurge"],
                 "mom63": round((r["mom63"] or 0) * 100, 1), "regime": r["regime"]}
                for r in screened if r["region"] == region and r.get("volSurge") and (r.get("mom63") or 0) > 0]
        flows[region] = sorted(cand, key=lambda x: x["volSurge"], reverse=True)[:6]
    from pipeline import indices as indices_mod
    idx_dates = dates[-320:]
    seed_indices = []
    for j, spec in enumerate(indices_mod.SPEC):
        base = [6200, 20300, 44600, 5200, 2800, 850, 1370, 17][j % 8]
        walk = np.cumsum(np.random.default_rng(100 + j).normal(0.0004, 0.01, len(idx_dates)))
        close = pd.Series(base * np.exp(walk), index=idx_dates)
        row = indices_mod.summarize_close(spec, close, "SEED")
        if row:
            seed_indices.append(row)

    payload = {"generatedAt": datetime.now(timezone.utc).isoformat(), "portfolioName": cfg.portfolio_name,
               "primary": cfg.primary, "benchmark": cfg.benchmark, "horizons": cfg.horizons, "tradeHorizon": th,
               "names": resolved_names, "seed": True, "stale": False, "dataSource": "SEED (예시) — 합성 데이터",
               "indices": seed_indices,
               "tradeIdeas": trade_mod.rank_ideas(ideas), "screened": screen_table, "details": details, "flows": flows, "sentiment": sent,
               "core": core_cards, "macro": macro_mod.summarize(macro, vix),
               "meta": {"modelsTrained": 0, "universeScreened": len(screened),
                        "latestDataDate": dates[-1].strftime("%Y-%m-%d"), "fredEnabled": True, "elapsedSec": 0,
                        "tickersRequested": len(all_t), "tickersFetched": len(all_t), "coveragePct": 100.0,
                        "missingSample": [], "indicesFetched": len(seed_indices)}}
    out = ROOT / "data" / "site-data.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}: {len(core_cards)} core, {len(ideas)} ideas, {len(screened)} screened")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
