"""Run invented one-step scenarios, never accept historical input paths.

    python -m scripts.run_decision_optionality > /tmp/decision-optionality.json
"""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
import argparse
import hashlib
import json
from pathlib import Path

from pipeline import decision_optionality as D
from pipeline import experiment_workbench as EW
from pipeline import industry_foundation as IF
from pipeline import weekly_decision as W

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = "docs/decision-optionality/protocol-v1.json"


def synthetic_frame(n=6, *, market="US", expected=3.0, before=None, remaining=3.0, radius=0.1, thesis=True):
    """All numbers invented. No real security or calibration is consulted."""
    day = "2026-10-09" if market == "US" else "2026-10-08"
    at = day + ("T21:30:00Z" if market == "US" else "T10:00:00Z")
    source = EW.Source("SYNTHETIC:decision-optionality-v1", "0" * 64, "INVENTED", at, None)
    candidates, observations, forecasts = [], [], []
    names = {f"SYN{i}" for i in range(n)} | (set(before or {}) - {W.BENCHMARKS[market]})
    for ticker in sorted(names):
        key = EW.Key(market, day, f"SYN:{ticker}")
        observations.append(EW.Observation(key, ticker, None, "VERIFIED_SECURITY", at,
                                          "OBSERVED_PROSPECTIVE", source, at, True, None,
                                          f"Sector{ticker}", "DATED", ()))
        forecasts.append(D.RemainingForecast(key, remaining, radius, at, source, thesis,
                                             "NO_SOURCE" if remaining is None or radius is None else None))
    for i in range(n):
        candidates.append({"ticker": f"SYN{i}", "region": market, "sector": f"SectorSYN{i}",
                           "alphaPercentile": 97, "longTermResearchView": "POSITIVE",
                           "evidenceCoverage": 1.0, "risk": {"downsideVolPct": 20.0},
                           "entry": {"entryState": "ACCUMULATE_GRADUALLY"}})
    buckets = [{"bucket": f"{lo}-{hi}", "usable": True, "unusableReason": None,
                "calibratedExpectedExcessReturnPct": expected, "confidenceIntervalPct": [expected - 2, expected + 2],
                "standardErrorPct": 1.0, "effectiveDates": 40, "conservativeBasis": "SYNTHETIC"}
               for lo, hi in ((0, 60), (60, 80), (80, 90), (90, 95), (95, 100))]
    calibration = {"available": True, "horizonDays": 126, "buckets": [0, 60, 80, 90, 95, 100],
                   "regions": {market: {"buckets": buckets, "ordering": {"established": True}}}}
    return D.Frame(market, day, at, tuple(observations), tuple(candidates), calibration,
                   dict(before) if before is not None else {W.BENCHMARKS[market]: 1.0}, tuple(forecasts))


def run_synthetic():
    raw = (ROOT / PROTOCOL).read_bytes()
    pinned = (ROOT / "docs/decision-optionality/protocol-v1.sha256").read_text().split()[0]
    if hashlib.sha256(raw).hexdigest() != pinned:
        raise ValueError("PROTOCOL_CHANGED_REQUIRES_NEW_VERSION")
    scenarios = []
    for market in ("KR", "US"):
        bench = W.BENCHMARKS[market]
        waiting = synthetic_frame(market=market, expected=0.05)
        symmetric = synthetic_frame(1, market=market, before={"SYN0": .15, bench: .85}, remaining=.1)
        drift = synthetic_frame(1, market=market, before={"SYN0": .14, bench: .86})
        boundary = synthetic_frame(market=market, before={**{f"SYN{i}": .15 for i in range(5)}, bench: .25})
        cands = list(boundary.candidates)
        for i in range(4):
            cands[i] = {**cands[i], "risk": {"downsideVolPct": 10 + i}}
        cands[5] = {**cands[5], "risk": {"downsideVolPct": 19.8}}
        boundary = replace(boundary, candidates=tuple(cands))
        designs = [
            ("D1_optional_entry", waiting, ("ETF", "CURRENT", "FORCED_FIVE")),
            ("D2_existing_credit", boundary, ("CURRENT", "NO_CREDIT")),
            ("D3_exit_boundary", symmetric, ("SYMMETRIC", "ASYMMETRIC")),
            ("D4_drift_only", drift, ("CURRENT", "EVENT_ONLY")),
        ]
        for name, frame, policies in designs:
            decisions = {p: D.decide(frame, p, scope="SYNTHETIC") for p in policies}
            if len({d["informationSha256"] for d in decisions.values()}) != 1:
                raise AssertionError("PAIRED_INFORMATION_DIFFERS")
            # Both favorable and unfavorable paths, never used by the decision maker.
            evaluations = {}
            for stock_return in (-.10, .10):
                returns = {o.ticker: stock_return for o in frame.observations} | {bench: .02}
                evaluations[str(stock_return)] = {
                    p: D.evaluate(d, returns, execution_date=d["nextTradingSession"],
                                  end_date="2026-10-16", scope="SYNTHETIC") for p, d in decisions.items()}
            scenarios.append({"id": name, "market": market, "decisions": decisions,
                              "inventedOneIntervalEvaluations": evaluations})
    frequencies = Counter(D.decide(synthetic_frame(n), scope="SYNTHETIC")["stockCount"] for n in range(6))
    return {"protocol": D.VERSION, "protocolSha256": pinned, "status": "SYNTHETIC_MECHANICS_ONLY",
            "recommendation": False, "historicalExecutionAuthorized": False,
            "historicalOutcomeReaderImplemented": False, "historicalModelFitterImplemented": False,
            "dependencies": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in (
                "pipeline/decision_optionality.py", "scripts/run_decision_optionality.py", "pipeline/weekly_decision.py",
                "pipeline/kelly_portfolio.py", "pipeline/benchmark_alpha.py", "pipeline/experiment_workbench.py",
                "pipeline/portfolio_validation.py", "pipeline/replay_calendar.py", "scripts/run_weekly_passive_first_replay.py")},
            "syntheticNameCountFrequencies": {str(n): frequencies[n] for n in range(6)},
            "limitations": ["No historical adapter or execution authorization", "No NAV path, annualization or inferential test",
                            "Unmeasured investor-specific capital-gains/dividend/FX taxes", "Forecasts and returns invented; no model calibration"],
            "scenarios": scenarios, "digest": IF.digest(scenarios)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", action="store_true", help="compact synthetic evidence; no historical inputs")
    args = parser.parse_args()
    report = run_synthetic()
    if args.summary:
        scenarios = []
        for s in report["scenarios"]:
            arms = {}
            for policy, d in s["decisions"].items():
                evs = s["inventedOneIntervalEvaluations"]
                example = evs["0.1"][policy]
                arms[policy] = {"stockCount": d["stockCount"], "actions": [a["action"] for a in d["actions"]],
                                "costFraction": example["costFraction"], "oneWayTurnover": example["oneWayTurnover"],
                                "nameTrades": example["nameTrades"],
                                "stockOrderLegs": example["stockOrderLegs"], "costByCategory": example["costByCategory"],
                                "replacementCostFraction": example["replacementCostFraction"],
                                "netActiveReturnByInventedStockReturn": {r: values[policy]["netActiveReturn"] for r, values in evs.items()}}
            scenarios.append({"id": s["id"], "market": s["market"], "arms": arms})
        report = {**{k: v for k, v in report.items() if k != "scenarios"}, "scenarios": scenarios}
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
