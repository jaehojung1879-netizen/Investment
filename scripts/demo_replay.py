"""End-to-end exercise of the historical replay stack on SYNTHETIC prices.

WHAT THIS IS AND IS NOT
-----------------------
This is a machinery test, not an investment result. It generates a synthetic
market with a deliberately embedded, weak cross-sectional momentum effect, runs
the real replay -> outcomes -> calibration -> walk-forward ML chain over it, and
prints what came out.

Any number it prints describes the *code*, not the market. No conclusion about
KOSPI or the S&P may be drawn from it. It exists because the real run needs
market data this environment cannot reach, and shipping an untested pipeline
because the network was blocked would be worse than shipping a tested one with
a clearly labelled synthetic fixture.

Usage:
    python scripts/demo_replay.py [--tickers 40] [--years 9] [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import evidence as EV                      # noqa: E402
from pipeline import historical_calibration as HC        # noqa: E402
from pipeline import historical_outcomes as HO           # noqa: E402
from pipeline import historical_replay as HR             # noqa: E402
from pipeline import opportunity as OP                   # noqa: E402
from pipeline import walkforward as WF                   # noqa: E402


def synthetic_market(n_tickers: int, years: int, seed: int = 20240211) -> dict:
    """A market with a small, real, discoverable momentum effect plus noise.

    The effect is intentionally modest (an AR component in returns that a 12-1
    momentum factor can partially detect). If the pipeline reported a huge edge
    here, that would indicate a leak, not a discovery — so a weak effect is the
    more useful test.
    """
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2013-01-02", periods=252 * years)
    market = rng.normal(0.00025, 0.0095, len(index))
    prices: dict[str, pd.DataFrame] = {}

    def frame(returns: np.ndarray, volume_scale: float = 1.0) -> pd.DataFrame:
        close = 100.0 * np.exp(np.cumsum(returns))
        noise = rng.normal(0, 0.0025, len(index))
        return pd.DataFrame({
            "Open": close * (1 + noise), "High": close * 1.008, "Low": close * 0.992,
            "Close": close,
            "Volume": rng.lognormal(14.0, 0.45, len(index)) * volume_scale,
        }, index=index)

    for i in range(n_tickers):
        region = "KR" if i % 2 == 0 else "US"
        beta = 0.65 + 0.7 * rng.random()
        idiosyncratic = rng.normal(0, 0.0135, len(index))
        base = beta * market + idiosyncratic + rng.normal(0.0002, 0.0004)
        # Slow-moving persistence: this is the signal the factor model may find.
        persistence = pd.Series(base).ewm(span=140).mean().to_numpy()
        returns = base + 0.30 * persistence
        prefix = "KR" if region == "KR" else "US"
        suffix = ".KS" if region == "KR" else ""
        prices[f"{prefix}{i:03d}{suffix}"] = frame(returns)

    for benchmark in ("SPY", "^KS200"):
        prices[benchmark] = frame(market, volume_scale=8.0)
    return prices


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", type=int, default=40)
    parser.add_argument("--years", type=int, default=9)
    parser.add_argument("--frequency", default="W", choices=["D", "W", "M"])
    parser.add_argument("--out", default=None, help="write signals/outcomes/report here")
    args = parser.parse_args(argv)

    print("=" * 74)
    print("SYNTHETIC DEMONSTRATION — machinery test, NOT an investment result")
    print("=" * 74)

    prices = synthetic_market(args.tickers, args.years)
    universe = {
        "KR": sorted(t for t in prices if t.startswith("KR")),
        "US": sorted(t for t in prices if t.startswith("US")),
    }
    benchmarks = {"US": "SPY", "KR": "^KS200"}
    cfg_lt = {"minFactorSleeves": 1, "minFinancialCoverage": 0.0,
              "excludeFromRanking": []}

    started = time.time()
    replay = HR.run_replay(prices, universe, benchmarks=benchmarks, cfg_lt=cfg_lt,
                           start=None, frequency=args.frequency,
                           model_version="demo-synthetic")
    signals, diagnostics = replay["signals"], replay["diagnostics"]
    print(f"\n[1] REPLAY  {time.time() - started:.1f}s")
    print(f"    window        {diagnostics['firstDate']} .. {diagnostics['lastDate']}")
    print(f"    replay dates  {diagnostics['replayDates']} ({args.frequency})")
    print(f"    signals       {diagnostics['signalsGenerated']}")
    print(f"    PIT coverage  {diagnostics['meanPitCoverage']}")
    print(f"    survivorship  {diagnostics['survivorshipRisk']} ({diagnostics['survivorshipNote']})")

    started = time.time()
    bench_closes = {name: prices[ticker]["Close"]
                    for name, ticker in (("SPY", "SPY"), ("^KS200", "^KS200"))}
    cost_policy = {"US": {"commissionBps": 5, "spreadBps": 10, "sellTaxBps": 3},
                   "KR": {"commissionBps": 5, "spreadBps": 12, "sellTaxBps": 20}}
    outcomes = HO.compute_outcomes(signals, prices, bench_closes, cost_policy=cost_policy)
    coverage = HO.coverage_summary(signals, outcomes)
    print(f"\n[2] OUTCOMES  {time.time() - started:.1f}s")
    print(f"    matured 126D  {coverage['maturedByHorizon']['126']}")
    print(f"    tracking days {coverage['trackingDays']} vs matured days "
          f"{coverage['maturedObservationDays']}   <- these are different numbers")

    calibration = HC.calibrate(outcomes, horizon=126, diagnostics=diagnostics,
                               cfg={"minEffectiveDates": 20, "shrinkagePriorStrength": 20})
    print(f"\n[3] ALPHA CALIBRATION  available={calibration['available']}")
    for region, blob in sorted((calibration.get("regions") or {}).items()):
        print(f"    {region}: {blob['observations']} obs / {blob['uniqueDates']} dates")
        for row in blob["buckets"]:
            print(f"      {row['bucket']:>7}p  n={row['observations']:<6} eff={row['effectiveDates']:<4}"
                  f" raw={row['meanExcessReturnPct']:+7.2f}%  net={row['costAdjustedMeanExcessReturnPct'] or 0:+7.2f}%"
                  f"  calibrated={row['calibratedExpectedExcessReturnPct']:+7.2f}%"
                  f"  hit={row['positiveHitRatio']}  w={row['evidenceWeight']}"
                  f"  {'USABLE' if row['usable'] else 'thin'}")

    print("\n[4] KELLY EVIDENCE (historical prior with an empty prospective ledger)")
    region_evidence = EV.summarize_region(calibration, {}, min_effective_dates=20,
                                          prior_scale_pct=3.0)
    for region, blob in sorted(region_evidence.items()):
        posterior = blob["posterior"]
        print(f"    {region}: historical {blob['historical']['expectedExcessReturnPct']}%"
              f" (w={blob['historical']['weight']}, eff={blob['historical']['effectiveDates']})"
              f" + prospective {blob['prospective']['expectedExcessReturnPct']}"
              f" -> posterior {posterior['expectedExcessReturnPct']}%"
              f"  [{blob['activation']['labelKo']}]")

    dataset = OP.build_dataset(signals, outcomes)
    print(f"\n[5] ML DATASET  {len(dataset)} rows x {len(OP.FEATURE_COLUMNS)} features")
    holdout_start = pd.Timestamp(dataset["date"].max()) - pd.DateOffset(years=2)
    guard = WF.HoldoutGuard(start=holdout_start.normalize())
    started = time.time()
    trained = OP.train(dataset, cfg={
        "trainYears": 2.5, "validationYears": 1.0, "testYears": 1.0,
        "embargoDays": 21, "includeLightGbm": False,
        "acceptance": {"minTopBucketNetExcessPct": 0.3, "minPitCoverage": 0.5},
    }, guard=guard)
    print(f"    training {time.time() - started:.1f}s  status={trained['status']}")
    if trained.get("status") == "TRAINED":
        winner = trained["winner"]
        test = winner["test"]
        top = test.get("topBucket") or {}
        print(f"    variants tested       {trained['diagnostics']['searchLog']['variantsTested']}")
        print(f"    winner                {winner['name']} / {winner['target']}")
        print(f"    OOS ROC-AUC           {test.get('rocAuc')}   PR-AUC lift {test.get('prAucLift')}")
        print(f"    OOS Brier / ECE       {test.get('brier')} / {test.get('calibrationError')}")
        print(f"    decile monotonicity   {test.get('decileMonotonicity')}")
        print(f"    top-decile net excess {top.get('meanExcessPct')}%  MDD {top.get('mddPct')}%"
              f"  CVaR {top.get('cvar95Pct')}%  turnover {test.get('turnover')}")
        print(f"    fold stability        {(test.get('foldStability') or {}).get('signAgreement')}")
        print(f"    PBO                   {trained['diagnostics']['probabilityOfBacktestOverfitting'].get('probabilityOfBacktestOverfitting')}")
        print(f"    deflated Sharpe       {trained['diagnostics']['deflatedSharpe']}")
        if trained.get("holdout"):
            hold = trained["holdout"]
            print(f"    SEALED HOLDOUT from {hold['start']}: monotonicity {hold.get('decileMonotonicity')}"
                  f", top-decile {((hold.get('topBucket') or {}).get('meanExcessPct'))}%")
        print(f"    baseline comparison   {(trained.get('baseline') or {}).get('name')} -> "
              f"{(((trained.get('baseline') or {}).get('test') or {}).get('topBucket') or {}).get('meanExcessPct')}%")
        print(f"    ACCEPTED              {trained['accepted']}")
        for name, ok in trained["acceptance"]["checks"].items():
            print(f"        {'PASS' if ok else 'FAIL'}  {name}")
        print("    decile ladder (test):")
        for row in (test.get("deciles") or []):
            print(f"        d{row['decile']:<2} n={row['n']:<5} mean {row['meanExcessPct']:+7.3f}%  hit {row['hitRatio']}")

    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "historical-signals.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in signals) + "\n", encoding="utf-8")
        (out / "historical-outcomes.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in outcomes) + "\n", encoding="utf-8")
        report = {"synthetic": True, "diagnostics": diagnostics, "coverage": coverage,
                  "calibration": calibration, "kellyEvidence": region_evidence,
                  "opportunityModel": {k: v for k, v in trained.items() if k != "variants"}}
        (out / "demo-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        print(f"\n    wrote {out}/historical-signals.jsonl, historical-outcomes.jsonl, demo-report.json")

    print("\n" + "=" * 74)
    print("Reminder: synthetic prices. These numbers validate the code path only.")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
