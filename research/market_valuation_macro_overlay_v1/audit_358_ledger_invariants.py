"""MVMA #358 independent ledger/completeness diagnostics (read-only).

This is NOT another Phase 2 run. It reads the sealed monthly ledger/JSON/protocol,
checks mechanical consistency and computes a clearly posthoc HAC lag sensitivity.
No pinned inputs, decisions or outputs are changed.
"""
from __future__ import annotations

import csv
import json
import math
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
POLICIES = ("B0", "B1", "B2", "V1", "M1T", "VM1T", "D1")
H2_LAGS_POSTHOC = (0, 1, 3, 6, 12)
DCA_REPORTED_KEYS = {
    "terminal value": "terminalValue",
    "total contributed": "contributed",
    "XIRR": "xirr",
    "time-weighted return": None,
    "average cash wait": None,
    "deployment ratio": "deploymentRatioAtEnd",
    "cash opportunity cost": None,
    "worst start cohort": None,
    "MDD under identical flows": None,
}


def mean_hac_independent(series: list[float], lag: int) -> dict:
    """Independent Bartlett HAC mean (no vendored #316 call). Two-sided normal p."""
    n = len(series)
    if n < 2 or not 0 <= lag < n:
        raise ValueError("HAC_INVALID_N_OR_LAG")
    mu = sum(series) / n
    centered = [v - mu for v in series]
    long_run = sum(v * v for v in centered) / n
    for k in range(1, lag + 1):
        cross = sum(centered[i] * centered[i - k] for i in range(k, n)) / n
        long_run += 2.0 * (1.0 - k / (lag + 1.0)) * cross
    se = math.sqrt(max(long_run, 0.0) / n)
    if se == 0:
        raise AssertionError("ZERO_HAC_SE")
    return {"lag": lag, "annualMean": 12.0 * mu, "annualSe": 12.0 * se,
            "pTwoSided": math.erfc(abs(mu / se) / math.sqrt(2.0))}


def audit(monthly_path: Path = HERE / "results/phase2-us-monthly.csv",
          result_path: Path = HERE / "results/phase2-us-result.json",
          protocol_path: Path = HERE / "protocol.json") -> dict:
    with monthly_path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    result = json.loads(result_path.read_text())
    spec = json.loads(protocol_path.read_text())
    p = result["primary"]
    n = len(rows)
    if not n == p["periods"] == spec["calendar"]["evaluationWindowUS"]["months"] == 152:
        raise AssertionError("WINDOW_INCONSISTENT")

    for i, row in enumerate(rows):
        if not (row["decisionDate"] < row["execStart"] < row["execEnd"]):
            raise AssertionError(f"EXECUTION_DATE_ORDER_{i}")
        if i and row["execStart"] != rows[i - 1]["execEnd"]:
            raise AssertionError(f"EXECUTION_GAP_{i}")
    if rows[0]["execStart"] != p["firstExecution"] or rows[-1]["execEnd"] != p["lastExecution"]:
        raise AssertionError("EXECUTION_ENDPOINT_MISMATCH")

    days = (date.fromisoformat(rows[-1]["execEnd"])
            - date.fromisoformat(rows[0]["execStart"])).days
    terminal_errors = {}
    cagr_errors = {}
    for policy in POLICIES:
        terminal = math.prod(1.0 + float(r["net" + policy]) for r in rows)
        stored = p["policies"][policy]["net"]
        cagr = terminal ** (365.25 / days) - 1.0
        t_error = terminal - stored["terminalValue"]
        c_error = cagr - stored["cagr"]
        if abs(t_error) > 1e-10 or abs(c_error) > 1e-12:
            raise AssertionError(f"POLICY_TERMINAL_OR_CAGR_MISMATCH_{policy}")
        terminal_errors[policy] = t_error
        cagr_errors[policy] = c_error

    # The 152-row ledger only includes the main window's 152 monthly returns.
    # The last 11 H1 forward-12M outcomes need post-window ETF returns not in this CSV.
    horizon = spec["hypotheses"][0]["horizonMonths"]
    if horizon != 12:
        raise AssertionError("PRIMARY_H1_HORIZON_CHANGED")
    forward_reconciled = 0
    max_forward_error = 0.0
    for i in range(n - horizon + 1):
        window = rows[i:i + horizon]
        fwd_spy = math.prod(1.0 + float(r["spyReturn"]) for r in window) - 1.0
        fwd_bil = math.prod(1.0 + float(r["bilReturn"]) for r in window) - 1.0
        error = abs(fwd_spy - fwd_bil - float(rows[i]["forward12MExcess"]))
        if error > 1e-10:
            raise AssertionError(f"FORWARD_12M_MISMATCH_{i}")
        max_forward_error = max(max_forward_error, error)
        forward_reconciled += 1

    # Independently reconstruct #316 H2 target-change COST and net TIMING series.
    weights = [float(r["targetVM1T"]) for r in rows]
    wbar = sum(weights) / n
    one_way = float(spec["costs"]["US"]["oneWayBps"]) / 1e4
    timing = []
    for i, (row, weight) in enumerate(zip(rows, weights)):
        excess = float(row["spyReturn"]) - float(row["bilReturn"])
        prior = weights[i - 1] if i else weight
        cost = 2.0 * one_way * abs(weight - prior)
        timing.append((weight - wbar) * excess - cost)
    h2 = {str(lag): mean_hac_independent(timing, lag) for lag in H2_LAGS_POSTHOC}
    saved = p["H2"]
    if any((
        abs(h2["0"]["annualMean"] - saved["annualTimingNetOfCost"]) > 1e-10,
        abs(h2["0"]["annualSe"] - saved["seAnnual"]) > 1e-10,
        abs(h2["0"]["pTwoSided"] - saved["pTwoSided"]) > 1e-10,
    )):
        raise AssertionError("H2_LAG_ZERO_NOT_REPRODUCED")
    if min(v["pTwoSided"] for v in h2.values()) <= spec["inference"]["multipleTesting"]["alpha"]:
        raise AssertionError("H2_SENSITIVITY_UNEXPECTEDLY_SIGNIFICANT")

    dca = result["dca"]
    if set(spec["dca"]["metrics"]) != set(DCA_REPORTED_KEYS):
        raise AssertionError("DCA_REGISTERED_FIELDS_CHANGED")
    available = []
    missing = []
    for label, key in DCA_REPORTED_KEYS.items():
        if key is not None and all(key in dca[rule] for rule in ("DCA-A", "DCA-B", "DCA-C")):
            available.append(label)
        else:
            missing.append(label)

    return {
        "stage": "READ_ONLY_POSTHOC_AUDIT_NOT_A_NEW_HYPOTHESIS_TEST",
        "policyMetricLedgerReconciliation": {
            "policies": len(POLICIES), "months": n, "days": days,
            "maxAbsTerminalError": max(abs(v) for v in terminal_errors.values()),
            "maxAbsCagrError": max(abs(v) for v in cagr_errors.values()),
            "verdict": "PASS",
        },
        "h1ForwardAudit": {
            "horizonMonths": horizon, "fullyCheckableUsingMonthlyLedger": forward_reconciled,
            "requiresPostWindowETFPrices": n - forward_reconciled,
            "maxAbsErrorInCheckedRows": max_forward_error,
            "verdict": "PASS_CHECKED_ROWS_POST_WINDOW_TAIL_NOT_VERIFIED_HERE",
        },
        "h2PosthocHacLagSensitivity": {
            "registeredLag": spec["inference"]["hac"]["lagMonthlyPolicy"],
            "reconstructedRegisteredH2": "PASS",
            "lags": h2,
            "role": "DESCRIPTIVE_ONLY_NOT_ADDED_TO_HOLM_FAMILY",
        },
        "dcaPreregOutputCompleteness": {
            "registeredCount": len(spec["dca"]["metrics"]),
            "implementedMetricCount": len(available),
            "reported": available,
            "missing": missing,
            "verdict": "INCOMPLETE_DESCRIPTIVE_METRICS",
        },
        "sealedResultsModified": False,
        "oneShotExecuted": False,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))
