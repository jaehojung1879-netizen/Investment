"""Read-only posthoc diagnostics for MVMA #358. Never executes or edits the sealed run.

Run: python -m research.market_valuation_macro_overlay_v1.audit_358_posthoc

Input: the committed monthly ledger, result JSON and protocol. Output: JSON to stdout.
This is an independent *audit counterfactual*, not a new H1/H2 result or re-authorization.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

from . import phase2 as P2
from .vendor import market_timing_pr316 as MT

HERE = Path(__file__).resolve().parent


def worst_12(returns: list[float]) -> float:
    return min(math.prod(1.0 + r for r in returns[i:i + 12]) - 1.0
               for i in range(len(returns) - 11))


def replay_dca(rows: list[dict], rule: str, one_way: float, parked_fraction: float,
               charge_bil_entry: bool) -> dict:
    """Rebuild DCA from archived month-to-month ETF total-return factors only.

    charge_bil_entry=False reproduces sealed #358; True fixes the missing BIL buy fee.
    The sealed run_dca and any actual result file are NOT invoked or altered.
    """
    equity = cash = total_cost = 0.0
    flows: list[tuple[str, float]] = []
    parked_shares: list[float] = []
    for i, row in enumerate(rows):
        if i:
            equity *= 1.0 + float(rows[i - 1]["spyReturn"])
            cash *= 1.0 + float(rows[i - 1]["bilReturn"])
        flows.append((row["execStart"], -1.0))
        triggered = (rule == "DCA-A" or
                     (rule == "DCA-B" and float(row["targetV1"]) == 1.0) or
                     (rule == "DCA-C" and float(row["targetD1"]) == 1.0))
        if triggered:
            fee = one_way * (1.0 + 2.0 * cash)
            equity += 1.0 + cash - fee
            cash = 0.0
        else:
            buy_spy = 1.0 - parked_fraction
            buy_bil = parked_fraction
            fee = one_way * (buy_spy + (buy_bil if charge_bil_entry else 0.0))
            equity += buy_spy * (1.0 - one_way)
            cash += buy_bil * (1.0 - one_way if charge_bil_entry else 1.0)
        total_cost += fee
        parked_shares.append(cash / (equity + cash))

    equity *= 1.0 + float(rows[-1]["spyReturn"])
    cash *= 1.0 + float(rows[-1]["bilReturn"])
    flows.append((rows[-1]["execEnd"], equity + cash))
    return {"terminalValue": equity + cash, "xirr": P2.xirr(flows), "costPaid": total_cost,
            "parkedAtEnd": cash, "averageParkedShare": sum(parked_shares) / len(parked_shares)}


def compare_risk_units(rows: list[dict], result: dict, one_way: float) -> dict:
    """Put both MDD paths on monthly NAV and charge BOTH legs on static drift resets."""
    vm = [float(r["netVM1T"]) for r in rows]
    b0 = [float(r["netB0"]) for r in rows]
    w = float(result["verdicts"]["equalVolatilityStaticWeight"])
    eq_gross, eq_net = [], []
    for i, r in enumerate(rows):
        r_e, r_f = float(r["spyReturn"]), float(r["bilReturn"])
        gross_factor = w * (1.0 + r_e) + (1.0 - w) * (1.0 + r_f)
        drifted = w * (1.0 + r_e) / gross_factor
        # The initial construction and the final period-end liquidation are uncharged,
        # matching the sealed NAV's convention on the other static policies.
        fee = 2 * one_way * abs(w - drifted) if i + 1 < len(rows) else 0.0
        eq_gross.append(gross_factor - 1.0)
        eq_net.append(gross_factor * (1.0 - fee) - 1.0)

    # Do not silently replace a mismatching archived comparator.
    if not math.isclose(MT.max_drawdown(eq_gross),
                        result["verdicts"]["equalVolatilityStaticMaxDrawdownMonthly"], abs_tol=1e-10):
        raise AssertionError("EQUAL_VOL_GROSS_MDD_NOT_REPRODUCED")
    if not math.isclose(worst_12(eq_gross),
                        result["verdicts"]["equalVolatilityStaticWorst12Months"], abs_tol=1e-10):
        raise AssertionError("EQUAL_VOL_GROSS_WORST12_NOT_REPRODUCED")
    vm_mdd, b0_mdd, static_mdd = (MT.max_drawdown(s) for s in (vm, b0, eq_net))
    vm_worst, b0_worst, static_worst = (worst_12(s) for s in (vm, b0, eq_net))
    checks = {"vmMddShallowerThanB0Monthly": vm_mdd > b0_mdd,
              "vmMddShallowerThanEqualVolMonthlyNet": vm_mdd > static_mdd,
              "vmWorst12BetterThanB0": vm_worst > b0_worst,
              "vmWorst12BetterThanEqualVolMonthlyNet": vm_worst > static_worst}
    return {"vmMddMonthly": vm_mdd, "vmMddDailyInSealedReport":
            result["primary"]["policies"]["VM1T"]["net"]["maxDrawdown"],
            "b0MddMonthly": b0_mdd, "equalVolStaticMddMonthlyNet": static_mdd,
            "vmWorst12": vm_worst, "equalVolStaticWorst12Net": static_worst,
            "checks": checks, "allRiskCriteriaMet": all(checks.values()),
            "sealedRiskVerdict": result["verdicts"]["level3RiskPath"]}


def audit(monthly_path: Path = HERE / "results/phase2-us-monthly.csv",
          result_path: Path = HERE / "results/phase2-us-result.json",
          protocol_path: Path = HERE / "protocol.json") -> dict:
    with monthly_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    result = json.loads(result_path.read_text())
    spec = json.loads(protocol_path.read_text())
    if len(rows) != result["primary"]["periods"] or len(rows) != 152:
        raise AssertionError("MONTHLY_WINDOW_MISMATCH")
    one_way = float(spec["costs"]["US"]["oneWayBps"]) / 1e4
    parked_fraction = float(spec["dca"]["parkedFraction"])

    dca = {}
    for rule in ("DCA-A", "DCA-B", "DCA-C"):
        old = replay_dca(rows, rule, one_way, parked_fraction, charge_bil_entry=False)
        source = result["dca"][rule]
        for key, value in old.items():
            if not math.isclose(value, source[key], rel_tol=1e-10, abs_tol=1e-10):
                raise AssertionError(f"SEALED_DCA_NOT_REPRODUCED: {rule}.{key}")
        corrected = replay_dca(rows, rule, one_way, parked_fraction, charge_bil_entry=True)
        dca[rule] = {"sealed": old, "withBilEntryFee": corrected,
                     "deltaTerminal": corrected["terminalValue"] - old["terminalValue"],
                     "deltaXirrPp": 100 * (corrected["xirr"] - old["xirr"])}
    risk = compare_risk_units(rows, result, one_way)
    # #316 COST charges target changes; the sealed NAV also charges monthly drift resets.
    # Expose rather than conceal the resulting gap in annualised arithmetic active return.
    decomposition_active = result["primary"]["decomposition"]["VM1T"]["annualActiveNet"]
    realized_active = result["comparisons"]["VM1T-B0"]["annualMeanNetDifference"]
    attribution = {"decompositionAnnualActiveNet": decomposition_active,
                   "realizedAnnualActiveNetVsB0": realized_active,
                   "driftAndResetResidualAnnualPp": 100 * (realized_active - decomposition_active),
                   "costDefinitionsDiffer": True}
    if risk["allRiskCriteriaMet"] or risk["sealedRiskVerdict"] != "NOT_MET":
        raise AssertionError("RISK_VERDICT_CHANGED_OR_UNEXPECTED")
    return {"stage": "POSTHOC_AUDIT_ONLY_DO_NOT_OVERWRITE_SEALED_RESULT",
            "source": "committed phase2-us-monthly.csv and phase2-us-result.json",
            "months": len(rows), "dca": dca, "risk": risk, "attribution": attribution,
            "primaryHypothesesReexecuted": False, "resultFilesModified": False}


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))
