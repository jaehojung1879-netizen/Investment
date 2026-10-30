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
from pipeline import market_research_c1c_contract as V  # noqa: E402
from pipeline import market_research_c1c_decisions as Q  # noqa: E402


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


def synthetic_v2(market):
    """Small invented fixture only; all controls/families/bases/costs, no file input."""
    close, plan, states = fixture(market)
    plan = plan.iloc[:8].copy()
    close = close.loc[:plan.executionDate.iloc[-1]].copy()
    panel = V.panel_targets(close, states, plan, market)
    prices = close.loc[plan.executionDate.iloc[0]:]
    results, matched, contrasts, readouts, reentry, auxiliary, auxiliary_contrasts = {}, {}, {}, {}, {}, {}, {}
    for basis in ("C1_PRIMARY_REPLICA", "ETF_CASH_ECONOMIC"):
        economic = basis == "ETF_CASH_ECONOMIC"
        identity = {"evidenceClass": C.SYNTHETIC,
            "instrument": ("SPY" if market == "US" else "069500.KS") if economic else ("SP500_PRICE_INDEX" if market == "US" else "KS200_PRICE_INDEX"),
            "returnBasis": "TOTAL_RETURN" if economic else "PRICE_INDEX", "currency": "USD" if market == "US" else "KRW",
            "cashBasis": "DTB3_PRIOR_KNOWN_ACT360" if economic and market == "US" else "ZERO",
            "sourceStatus": "SYNTHETIC_HASH_VERIFIED", "rightsStatus": "SYNTHETIC_ALLOWED",
            "reconciliationStatus": "SYNTHETIC_PASS", "sourceSha256": hashlib.sha256(close.to_csv().encode()).hexdigest()}
        V.synthetic_basis_check(market, basis, identity)
        cash = pd.Series(0.0, index=prices.index)
        if economic and market == "US":
            # Invent the observations, reuse the real lag/staleness and actual
            # calendar-day convention rather than labelling a per-session
            # constant as ACT/360 (weekends must accrue three days).
            rates = pd.Series(3.0, index=pd.date_range(close.index[0] - pd.Timedelta(days=35), close.index[-1], freq="D"))
            cash = U.cash_interval_returns(rates, close.index).reindex(prices.index)
        for cell in V.cell_ids():
            selected = [row["cells"][cell]["target"] for row in panel]
            for stress in (1, 2, 3):
                path = C.replay(prices, plan, selected, cash, market, basis, stress, evidence_class=C.SYNTHETIC)
                results[f"{basis}/x{stress}/{cell}"] = {"fundedNetReturn": float(path.nav.iloc[-1] - 1),
                    "netAnnualLogGrowth": float(np.log(path.nav.iloc[-1]) * 252 / (len(path) - 1)),
                    "entryFee": float(path.entryFee.sum()), "liquidationFee": float(path.liquidationFee.sum())}
        if economic:
            support = {"windowMatured": True, "intendedIntervals": len(prices) - 1, "observedIntervals": len(prices) - 1}
            reconstructed = Q.synthetic_from_inputs(close, states, plan, cash, market, basis, 1,
                evidence_class=C.SYNTHETIC, support=support,
                cash_basis="US_SYNTHETIC_DTB3_PRIOR_KNOWN_ACT360" if market == "US" else None,
                episodes=({"episodeId": "FIXED_INVENTED_WINDOW_NOT_FITTED",
                    "startDate": str(prices.index[2].date()), "troughDate": str(prices.index[10].date()),
                    "endDate": str(prices.index[20].date())},))
            matched, readouts, reentry = (reconstructed[k] for k in ("diagnostics", "readouts", "reentryContrasts"))
            auxiliary, auxiliary_contrasts = (reconstructed[k] for k in ("auxiliaryC1Diagnostics", "auxiliaryC1VsC0"))
        for stress in (1, 2, 3):
            contrasts[f"{basis}/x{stress}"] = V.family_contrasts({cell: results[f"{basis}/x{stress}/{cell}"]["netAnnualLogGrowth"]
                                                              for cell in V.cell_ids()})
    signal = "2026-10-30"
    receipt = V.synthetic_receipt(market=market, signal_date=signal, created_at=C.final_at(signal, market).isoformat(),
        authorizing_merge_at="2026-10-26T00:00:00Z", layers={"slow": 0, "transition": 0, "fast": 1},
        breakout=True, source_sha256="1" * 64)
    return {"status": "SYNTHETIC_PREPARATION_ONLY", "market": market, "evidenceClass": C.SYNTHETIC,
        "empiricalSupport": "NOT_TESTED", "sourceAdmitted": False, "productionAllowed": False,
        "historicalOutcomeExecutions": 0, "contract": V.contract(), "panel": panel,
        "allCellsBasesCosts": results, "pairedFamilyContrasts": contrasts, "matchedExposureSmokeChecks": matched,
        "c0FixedDescriptiveReadouts": readouts,
        "c0ReentryDirectionReadouts": reentry,
        "auxiliaryC1Diagnostics": auxiliary, "auxiliaryC1VsC0": auxiliary_contrasts,
        "prospectiveDraft": V.prospective_schedule(market, "2026-10-26T00:00:00Z"),
        "receipt": receipt, "receiptValidation": V.validate_synthetic_receipts([receipt])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", default="verify", choices=("verify", "synthetic", "synthetic-v2"))
    parser.add_argument("--market", choices=("KR", "US"), default="US")
    args = parser.parse_args(argv)
    try:
        design = C.verify_design(ROOT)
        if args.mode == "verify":
            result = design
        elif args.mode == "synthetic-v2":
            result = synthetic_v2(args.market)
        else:
            result = {"status": "SYNTHETIC_TEST_ONLY", "historicalExecutionEnabled": False,
                "productionEffect": "NONE", "synthetic": synthetic(args.market)}
        print(json.dumps(clean(result), ensure_ascii=False, sort_keys=True, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError) as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error), "historicalOutcomeExecutions": 0}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
