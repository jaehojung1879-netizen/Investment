"""One bounded replay of weekly-passive-first-v1 against its passive benchmark.

Protocol: research_specs/weekly-passive-first-v1.json ("historicalComparisonProtocol"),
committed before this script computed anything. Paths P0, P1, C1, C2 per region.

Read-only on the sealed ledger; refuses to write inside it or overwrite a result.
No vendor calls, no sealed writes, no production promotion. The result is
POST_OUTCOME_EXPOSED_EXPLORATORY_PORTFOLIO_REPLAY evidence and never a validation.

    python scripts/run_weekly_passive_first_replay.py <ledger_dir> \
        --regional-paths docs/results/regional-standalone-paths.json.gz \
        --output docs/results/weekly-passive-first-v1-replay.json
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import multiprocessing as mp
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import benchmark_alpha as BA                  # noqa: E402
from pipeline import historical_calibration as HC           # noqa: E402
from pipeline import historical_store as HS                 # noqa: E402
from pipeline import portfolio_validation as PV             # noqa: E402
from pipeline import provenance                              # noqa: E402
from pipeline import replay_calendar as RC                   # noqa: E402
from pipeline import replay_inputs as RI                     # noqa: E402
from pipeline import replay_valuation as RV                  # noqa: E402
from pipeline import weekly_decision as W                    # noqa: E402
from pipeline.config import load_config                      # noqa: E402

REGIONS = ("KR", "US")
HORIZON = W.EDGE_HORIZON_SESSIONS
SPEC = ROOT / W.SPEC_PATH
_OUTCOMES: list[dict] = []
_DIAG: dict = {}
_CAL_CFG: dict = {}


def _guard(path, ledger: Path) -> Path:
    resolved = Path(path).resolve()
    if resolved == ledger.resolve() or ledger.resolve() in resolved.parents:
        raise ValueError("research output must be outside the sealed ledger")
    if resolved.exists():
        raise FileExistsError(f"refusing to overwrite {resolved}; this replay runs once")
    return resolved


def _no_probability(*_args, **_kwargs):
    # The rule reads only regions/buckets/ordering; the probability block is
    # independent of them (verified against a full production call in main()).
    return {"reliabilityGate": {}, "regions": {}}


def _calibrate(outcomes: list[dict]) -> dict:
    original = HC.probability_mod.calibrate
    HC.probability_mod.calibrate = _no_probability
    try:
        return HC.calibrate(outcomes, horizon=HORIZON, diagnostics=_DIAG, cfg=_CAL_CFG,
                            buckets=_CAL_CFG["buckets"], cost_adjusted=_CAL_CFG["costAdjusted"],
                            require_pit=_CAL_CFG["requirePit"])
    finally:
        HC.probability_mod.calibrate = original


def _compact(cal: dict) -> dict:
    keep = ("bucket", "usable", "unusableReason", "calibratedExpectedExcessReturnPct",
            "confidenceIntervalPct", "standardErrorPct", "conservativeBasis", "effectiveDates")
    return {"available": bool(cal.get("available")), "horizonDays": cal.get("horizonDays"),
            "buckets": cal.get("buckets"),
            "regions": {r: {"ordering": {k: v for k, v in (b.get("ordering") or {}).items()
                                         if not isinstance(v, (dict, list))},
                            "buckets": [{k: row.get(k) for k in keep} for row in b["buckets"]]}
                        for r, b in (cal.get("regions") or {}).items()}}


def _end(outcome: dict) -> str | None:
    return ((outcome.get("horizons") or {}).get(str(HORIZON)) or {}).get("endDate")


def _anchor_calibration(signal_date: str) -> tuple[str, dict]:
    matured = [o for o in _OUTCOMES if (_end(o) or "9999") <= signal_date]
    if not matured:
        return signal_date, {"available": False, "reason": "NO_MATURED_OUTCOMES", "regions": {}}
    return signal_date, _compact(_calibrate(matured))


# --------------------------------------------------------------------------- #
# Path accounting
# --------------------------------------------------------------------------- #
def _leg_cost(prior: dict, weights: dict, regions: dict, as_of: str, benchmarks: set) -> tuple[float, float, int]:
    cost = turnover = 0.0
    trades = 0
    for ticker in sorted(set(prior) | set(weights)):
        delta = float(weights.get(ticker, 0.0)) - float(prior.get(ticker, 0.0))
        if abs(delta) < 1e-12:
            continue
        region = regions.get(ticker)
        if region not in REGIONS:
            raise ValueError(f"no region for traded ticker {ticker}")
        side = "buy" if delta > 0 else "sell"
        cost += abs(delta) * W.trade_cost_fraction(region, as_of, is_benchmark=ticker in benchmarks,
                                                   side=side)
        turnover += abs(delta)
        if ticker not in benchmarks and (float(prior.get(ticker, 0)) == 0 or float(weights.get(ticker, 0)) == 0):
            trades += 1
    return cost, turnover / 2, trades


def account(rows: list[dict], benchmarks: set) -> dict:
    """Chain valuation rows into a cost-adjusted daily NAV, with attribution."""
    nav = gross_nav = 1.0
    dates, net_series, gross_series = [], [], []
    prior: dict = {}
    regions: dict = {}
    costs, turnovers, trades = [], [], 0
    contributions = defaultdict(float)
    block_returns, names, bench_weights = [], [], []
    for index, row in enumerate(rows):
        regions.update(row.get("regionByTicker") or {})
        regions.update(row.get("terminalRegionByTicker") or {})
        cost, turnover, n_trades = _leg_cost(prior, row["weights"], regions, row["date"], benchmarks)
        costs.append(cost)
        turnovers.append(turnover if index else 0.0)
        trades += n_trades
        start = nav * (1 - cost)
        daily = np.asarray(row["dailyGrossNav"], dtype=float)
        skip = 0 if index == 0 else 1
        dates.extend(row["dailyDates"][skip:])
        net_series.extend((start * daily[skip:]).tolist())
        gross_series.extend((gross_nav * daily[skip:]).tolist())
        growth = 1 + float(row["grossReturn"])
        for ticker, weight in row["weights"].items():
            terminal = float((row.get("terminalWeights") or {}).get(ticker, 0.0)) * growth
            contributions[ticker] += start * (terminal - float(weight))
        block_returns.append(((start * growth) / nav - 1, float(row["benchmarkReturn"])))
        names.append(sum(1 for t in row["weights"] if t not in benchmarks))
        bench_weights.append(sum(w for t, w in row["weights"].items() if t in benchmarks))
        nav = start * growth
        gross_nav *= growth
        prior = {t: float(w) for t, w in (row.get("terminalWeights") or {}).items()}
    return {"dates": dates, "nav": net_series, "grossNav": gross_series, "costs": costs,
            "turnovers": turnovers, "nameTrades": trades, "contributions": dict(contributions),
            "blockReturns": block_returns, "names": names, "benchmarkWeights": bench_weights}


def _drawdown(values: np.ndarray) -> float:
    peak = np.maximum.accumulate(values)
    return float((values / peak - 1).min())


def metrics(path: dict, passive: dict | None, rows: list[dict], initial: float) -> dict:
    nav = np.asarray(path["nav"], dtype=float)
    gross = np.asarray(path["grossNav"], dtype=float)
    years = RV.span_years(rows[0]["date"], rows[-1]["endDate"])
    daily = nav[1:] / nav[:-1] - 1
    cagr = nav[-1] ** (1 / years) - 1
    gross_cagr = gross[-1] ** (1 / years) - 1
    downside = daily[daily < 0]
    out = {
        "startDate": rows[0]["date"], "endDate": rows[-1]["endDate"], "years": round(years, 4),
        "blocks": len(rows), "sessions": len(nav),
        "initialCapitalKrw": initial, "finalValueKrw": round(initial * float(nav[-1])),
        "cumulativeGrossReturnPct": round((gross[-1] - 1) * 100, 3),
        "cumulativeNetReturnPct": round((nav[-1] - 1) * 100, 3),
        "cagrPct": round(cagr * 100, 3), "grossCagrPct": round(gross_cagr * 100, 3),
        "annualizedCostDragPct": round((gross_cagr - cagr) * 100, 3),
        "totalCostPctOfNav": round(sum(path["costs"]) * 100, 3),
        "maxDrawdownPct": round(_drawdown(nav) * 100, 3),
        "annualizedVolatilityPct": round(float(daily.std(ddof=1)) * math.sqrt(252) * 100, 3),
        "annualizedDownsideVolatilityPct": round(float(np.sqrt((downside ** 2).mean())) * math.sqrt(252) * 100, 3)
        if len(downside) else None,
        "oneWayTurnoverPerYear": round(sum(path["turnovers"]) / years, 3),
        "nameTrades": path["nameTrades"],
        "averageNamesHeld": round(float(np.mean(path["names"])), 3),
        "zeroNameBlockSharePct": round(100 * sum(1 for n in path["names"] if n == 0) / len(rows), 2),
        "averageBenchmarkWeightPct": round(100 * float(np.mean(path["benchmarkWeights"])), 2),
    }
    frame = pd.Series(nav, index=pd.to_datetime(path["dates"]))
    years_out = {}
    for year, values in frame.groupby(frame.index.year):
        before = frame[frame.index.year < year]
        base = float(before.iloc[-1]) if len(before) else float(frame.iloc[0])
        years_out[str(year)] = round((float(values.iloc[-1]) / base - 1) * 100, 3)
    out["calendarYearReturnPct"] = years_out
    half = len(rows) // 2
    split_date = rows[half]["date"]
    first = frame[frame.index <= pd.Timestamp(split_date)]
    second = frame[frame.index >= pd.Timestamp(split_date)]
    out["halves"] = {
        "splitDate": split_date,
        "firstHalfCagrPct": round(((first.iloc[-1] / first.iloc[0]) ** (1 / RV.span_years(rows[0]["date"], split_date)) - 1) * 100, 3),
        "secondHalfCagrPct": round(((second.iloc[-1] / second.iloc[0]) ** (1 / RV.span_years(split_date, rows[-1]["endDate"])) - 1) * 100, 3),
    }
    if passive is not None:
        p_nav = np.asarray(passive["nav"], dtype=float)
        if passive["dates"] != path["dates"]:
            raise ValueError("passive and strategy paths are on different sessions")
        p_cagr = p_nav[-1] ** (1 / years) - 1
        # Active return per block against the PASSIVE path's own block return,
        # never a row's matched benchmark (C1's is diluted by its cash).
        active = [s - b for (s, _), (b, _) in zip(path["blockReturns"], passive["blockReturns"])]
        arithmetic = float(np.mean(active)) * len(rows) / years
        out["benchmarkCagrPct"] = round(p_cagr * 100, 3)
        out["excessCagrPp"] = round((cagr - p_cagr) * 100, 3)
        out["arithmeticActiveReturnPpPerYear"] = round(arithmetic * 100, 3)
        out["geometricMinusArithmeticPp"] = round(((cagr - p_cagr) - arithmetic) * 100, 3)
        p_frame = pd.Series(p_nav, index=frame.index)
        out["excessByCalendarYearPp"] = {}
        for year in years_out:
            mask = p_frame.index.year == int(year)
            base_idx = np.where(p_frame.index.year < int(year))[0]
            pb = float(p_frame.iloc[base_idx[-1]]) if len(base_idx) else float(p_frame.iloc[0])
            p_ret = float(p_frame[mask].iloc[-1]) / pb - 1
            out["excessByCalendarYearPp"][year] = round(years_out[year] - p_ret * 100, 3)
    contributions = sorted(path["contributions"].items(), key=lambda kv: -abs(kv[1]))
    out["topContributions"] = [{"ticker": t, "navUnits": round(v, 5)} for t, v in contributions[:10]]
    return out


def weekly_nav(path: dict) -> list[list]:
    frame = pd.Series(path["nav"], index=pd.to_datetime(path["dates"]))
    weekly = frame.groupby(frame.index.to_period("W")).last()
    last_dates = frame.groupby(frame.index.to_period("W")).apply(lambda s: s.index[-1])
    return [[d.strftime("%Y-%m-%d"), round(float(v), 6)] for d, v in zip(last_dates, weekly)]


# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    global _OUTCOMES, _DIAG, _CAL_CFG
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger_dir")
    parser.add_argument("--regional-paths", default=str(ROOT / "docs/results/regional-standalone-paths.json.gz"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--calibration-cache", default=None)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args(argv)
    ledger = Path(args.ledger_dir)
    output = _guard(args.output, ledger)
    spec = json.loads(SPEC.read_text())
    if spec["policyVersion"] != W.POLICY_VERSION or spec["rule"]["nameWeight"] != W.NAME_WEIGHT:
        raise ValueError("module and frozen spec disagree")
    cfg, _ = load_config()
    replay_cfg = cfg.historical_replay or {}
    _CAL_CFG = {"minEffectiveDates": int(replay_cfg.get("minEffectiveDates", 30)),
                "shrinkagePriorStrength": float(replay_cfg.get("shrinkagePriorStrength", 30)),
                "minOrderingTStat": float(replay_cfg.get("minOrderingTStat", HC.DEFAULT_MIN_ORDERING_T)),
                "minOrderingEffectiveDates": int(replay_cfg.get(
                    "minOrderingEffectiveDates", HC.DEFAULT_MIN_ORDERING_EFFECTIVE_DATES)),
                "buckets": replay_cfg.get("alphaPercentileBuckets", HC.DEFAULT_BUCKETS),
                "costAdjusted": bool(replay_cfg.get("costAdjusted", True)),
                "requirePit": bool(replay_cfg.get("requirePitQuality", True))}
    started = time.time()
    store = RI.InputStore(ledger, provenance.REPLAY_VERSION, provenance.DATA_VERSION)
    manifest = store.manifest()
    if not manifest or provenance.REPLAY_VERSION != "replay-v16":
        raise ValueError("requires sealed replay-v16 inputs")
    expected_input = spec["historicalComparisonProtocol"]["inputs"].split("sha256 ")[1].split(",")[0]
    if manifest["sha256"] != expected_input:
        raise ValueError("frozen input manifest differs from the one the protocol names")
    regional = json.loads(gzip.decompress(Path(args.regional_paths).read_bytes()))
    content = {k: v for k, v in regional.items() if k != "sha256"}
    if RI.digest(content) != regional["sha256"] or regional["provenance"]["inputSha256"] != manifest["sha256"]:
        raise ValueError("regional standalone paths hash or lineage mismatch")

    print("loading outcomes and diagnostics", flush=True)
    _OUTCOMES = HS.load(ledger, HS.OUTCOMES, provenance.REPLAY_VERSION)
    _DIAG = json.loads((ledger / "historical-diagnostics.json").read_text())
    calendar = [b for b in RC.schedule(replay_cfg.get("start", RC.ORIGIN), manifest["through"],
                                       PV.HEADLINE_HORIZON, replay_cfg.get("frequency", "W"))
                if b["endDate"] <= manifest["through"]]
    print(f"{len(calendar)} blocks; {len(_OUTCOMES)} outcomes", flush=True)

    # Point-in-time calibrations, one per anchor.
    cache_path = Path(args.calibration_cache) if args.calibration_cache else None
    if cache_path and cache_path.exists():
        cached = json.loads(cache_path.read_text())
        calibrations = cached["calibrations"]
    else:
        dates = [b["signalDate"] for b in calendar]
        with mp.get_context("fork").Pool(args.workers) as pool:
            calibrations = dict(pool.imap_unordered(_anchor_calibration, dates))
        if cache_path:
            cache_path.write_text(json.dumps({"calibrations": calibrations}, sort_keys=True))
    # The stubbed calibrate must reproduce production's bucket output.
    full_production = HC.calibrate(_OUTCOMES, horizon=HORIZON, diagnostics=_DIAG, cfg=_CAL_CFG,
                                   buckets=_CAL_CFG["buckets"], cost_adjusted=_CAL_CFG["costAdjusted"],
                                   require_pit=_CAL_CFG["requirePit"])
    if _compact(full_production) != _compact(_calibrate(_OUTCOMES)):
        raise ValueError("calibration without the probability block differs from production")
    final_calibration = _compact(full_production)
    print(f"calibrations ready {time.time() - started:.0f}s", flush=True)

    frozen = RI.unpack(store.load(manifest, valuation_only=True))
    valuation = RV.ValuationData(
        frozen["prices"], cfg.benchmarks, frozen["fx"], frozen["risk_free"],
        through=manifest["through"], risk_free_through=frozen["risk_free_source"]["verifiedThrough"],
        corporate_actions=frozen.get("corporate_actions"))
    print("loading projected signals", flush=True)
    signals = HS.load(ledger, HS.SIGNALS, provenance.REPLAY_VERSION, project=HS.audit_projection)
    contexts = BA._contexts(signals, cfg.longterm)
    del signals

    benchmarks = set(W.BENCHMARKS.values())
    result_regions = {}
    for region in REGIONS:
        bench = W.BENCHMARKS[region]
        sealed_rows = {r["date"]: r for r in regional["regional"][region]}
        rows = {"P0": [], "P1": [], "C1": [], "C2": []}
        failures = {k: [] for k in rows}
        decisions = []
        incumbents: set[str] = set()
        for block in calendar:
            signal = block["signalDate"]
            candidates = [c for c in (contexts.get(signal) or ([], {}))[0] if c.get("region") == region]
            decision = W.decide(region, candidates, calibrations.get(signal), signal, incumbents)
            ordering = ((calibrations.get(signal) or {}).get("regions") or {}).get(region, {}).get("ordering", {})
            decisions.append({"date": block["date"], "signalDate": signal,
                              "stockCount": decision["stockCount"],
                              "holdings": [h["ticker"] for h in decision["holdings"]],
                              "orderingEstablished": bool(ordering.get("established")),
                              "candidates": len(candidates)})
            plans = {"P0": {bench: 1.0},
                     "P1": dict(decision["weights"])}
            sealed = sealed_rows.get(block["date"])
            if sealed is None:
                failures["C1"].append({"date": block["date"], "reason": "SEALED_BLOCK_MISSING"})
                failures["C2"].append({"date": block["date"], "reason": "SEALED_BLOCK_MISSING"})
            else:
                stock = {t: float(w) for t, w in sealed["weights"].items()}
                plans["C2"] = {**stock, bench: max(0.0, 1 - sum(stock.values()))}
                rows["C1"].append(sealed)
            for key, weights in plans.items():
                weights = {t: w for t, w in weights.items() if w > 1e-12}
                row, diag = valuation.window(
                    {"date": block["date"], "replayDate": signal, "weights": weights,
                     "regionByTicker": {t: region for t in weights}, "selector": key}, block)
                if row is None:
                    failures[key].append({"date": block["date"], **diag})
                else:
                    rows[key].append(row)
            incumbents = {h["ticker"] for h in decision["holdings"]}
        paths, complete = {}, {}
        for key, path_rows in rows.items():
            complete[key] = not failures[key] and len(path_rows) == len(calendar)
            paths[key] = account(path_rows, benchmarks) if complete[key] else None
        summaries = {}
        for key in rows:
            if paths[key] is None:
                summaries[key] = {"available": False, "status": "PARTIAL",
                                  "failures": failures[key][:10], "failureCount": len(failures[key])}
                continue
            if key == "C1" and paths[key]["dates"] != paths["P0"]["dates"]:
                raise ValueError("sealed C1 sessions differ from the replay calendar")
            summaries[key] = {"available": True, **metrics(
                paths[key], None if key == "P0" else paths["P0"], rows[key],
                spec["historicalComparisonProtocol"]["initialCapitalKrw"])}
        result_regions[region] = {
            "benchmark": bench,
            "headlineEligible": region == "KR",
            "status": ("DEFINITION_INTERNAL_REPLAY_V16" if region == "KR"
                       else "SURVIVORSHIP_BIASED_PARTIAL"),
            "benchmarkDefinition": "BENCHMARK_DEFINITION_REPLAY_V16_NOT_RECONCILED" if region == "KR"
            else "REPLAY_V16_SPY_IN_KRW",
            "baseCurrency": "KRW", "fxReturnsIncluded": region == "US",
            "paths": summaries,
            "weeklyNav": {k: weekly_nav(p) for k, p in paths.items() if p is not None},
            "decisions": decisions,
            "anchorsWithOrderingEstablished": sum(d["orderingEstablished"] for d in decisions),
            "anchorsWithStocks": sum(1 for d in decisions if d["stockCount"]),
        }
        print(region, {k: (v.get("cagrPct"), v.get("excessCagrPp")) for k, v in summaries.items()}, flush=True)

    report = {
        "id": "weekly-passive-first-v1-replay", "policyVersion": W.POLICY_VERSION,
        "evidenceClass": "POST_OUTCOME_EXPOSED_EXPLORATORY_PORTFOLIO_REPLAY",
        "promotionEligible": False, "liveValidated": False,
        "specSha256": hashlib.sha256(SPEC.read_bytes()).hexdigest(),
        "inputManifestSha256": manifest["sha256"], "through": manifest["through"],
        "regionalPathsSha256": regional["sha256"],
        "calendar": {"blocks": len(calendar), "first": calendar[0], "last": calendar[-1],
                     "cadence": "21_SESSION_ANCHORS_NOT_WEEKLY"},
        "candidatePool": "PV._research_candidates(price_proxy=True), the convention every replay-v16 portfolio harness uses",
        "finalAnchorCalibration": final_calibration,
        "regions": result_regions,
        "runtimeSec": round(time.time() - started),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n")
    print(f"wrote {output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
