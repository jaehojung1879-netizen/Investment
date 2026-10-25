"""Verify the Market Research design or run deterministic INVENTED fixtures.

No historical input option, vendor call, approval write, lock or execute route.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import market_research_c1c as C  # noqa: E402
from pipeline import kr_market_risk_model as K  # noqa: E402
from pipeline import replay_calendar as RC  # noqa: E402
from pipeline import rp1_c1_us_exposure as U  # noqa: E402


def fixture(market):
    days = RC.sessions("2018-01-02", "2021-01-15", market)
    i = np.arange(len(days))
    steps = 0.0003 + 0.012 * np.sin(i / 5)
    steps[(i % 180 >= 100) & (i % 180 < 125)] -= 0.025
    steps[(i % 180 >= 125) & (i % 180 < 150)] += 0.025
    close = pd.Series(100 * np.exp(np.cumsum(steps)), index=days)
    plan = C.schedule(close, market, str(days[220].date()), str(days[-1].date()))
    # Invented state vectors exercise policy branches; not claimed to be FAST computed from these invented prices.
    states = pd.DataFrame(index=plan.decisionDate)
    n = np.arange(len(states))
    states["slow"], states["transition"], states["fast"] = n % 2, (n // 2) % 2, n % 3
    for layer in ("slow", "transition", "fast"):
        states[layer + "KnownAt"] = [C.final_at(str(d.date()), market).isoformat() for d in states.index]
    return close, plan, states


def synthetic(market):
    close, plan, states = fixture(market)
    selected = {arm: C.targets(close, states, plan, market, arm).target.tolist() for arm in C.ARMS}
    selected.update(PASSIVE=[1.0] * len(plan), C0_DIAGNOSTIC=K.candidate_targets(states, plan, "C0").target.tolist(),
                    STATIC_40=[0.4] * len(plan), STATIC_70=[0.7] * len(plan))
    prices = close.loc[plan.executionDate.iloc[0]:]
    report = {"market": market, "evidenceClass": C.SYNTHETIC,
              "fixture": "algebraic sine/drop/rebound prices and independently invented state vectors; no historical data",
              "inputDigests": {"inventedPrices": hashlib.sha256(close.to_csv(float_format="%.17g").encode()).hexdigest(),
                               "inventedStates": hashlib.sha256(states.to_csv().encode()).hexdigest(),
                               "calendarSchedule": hashlib.sha256(plan.to_csv(index=False).encode()).hexdigest()},
              "readings": {}}
    for basis in ("C1_PRIMARY_REPLICA", "ETF_CASH_ECONOMIC"):
        cash = pd.Series(0.0, index=close.index)
        if basis == "ETF_CASH_ECONOMIC" and market == "US":
            obs = pd.Series(3.0, index=pd.date_range("2017-12-01", close.index[-1], freq="D"))
            cash = U.cash_interval_returns(obs, close.index)
        gross = {arm: C.replay(prices, plan, values, cash, market, basis, 0, evidence_class=C.SYNTHETIC)
                 for arm, values in selected.items()}
        gross_cagr = {arm: K.annualized(path.nav.iloc[-1], len(path) - 1) for arm, path in gross.items()}
        for stress in (1, 2, 3):
            paths = {arm: C.replay(prices, plan, values, cash, market, basis, stress, evidence_class=C.SYNTHETIC)
                     for arm, values in selected.items()}
            control, passive = paths["S0"], paths["PASSIVE"]
            metrics = {arm: {**C.diagnostics(path, passive, prices, cash),
                             "transitions": C.transition_diagnostics(path, control),
                             "grossCagr": gross_cagr[arm],
                             "costDragCagr": gross_cagr[arm] - K.annualized(path.nav.iloc[-1], len(path) - 1),
                             **C.lifecycle_periods(path, passive)}
                       for arm, path in paths.items()}
            effects = C.factorial({arm: float(np.log(paths[arm].nav.iloc[-1]) * 252 / (len(paths[arm]) - 1)) for arm in C.ARMS})
            report["readings"][basis + ":x" + str(stress)] = {"metrics": metrics, "annualLogGrowthContrasts": effects}
    return report


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, np.generic):
        return clean(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", default="verify", choices=("verify", "synthetic"))
    parser.add_argument("--market", choices=("KR", "US"), default="US")
    args = parser.parse_args(argv)
    try:
        design = C.verify_design(ROOT)
        result = design if args.mode == "verify" else {"status": "SYNTHETIC_TEST_ONLY",
            "historicalExecutionEnabled": False, "productionEffect": "NONE", "synthetic": synthetic(args.market)}
        print(json.dumps(clean(result), ensure_ascii=False, sort_keys=True, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError) as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error), "historicalOutcomeExecutions": 0}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
