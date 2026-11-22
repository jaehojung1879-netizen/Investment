"""Synthetic tampering guards for the independent MVMA #358 ledger audit."""
from __future__ import annotations

import csv

import pytest

from research.market_valuation_macro_overlay_v1 import audit_358_ledger_invariants as A


def test_ledger_audit_reproduces_all_policy_compounds_and_h2_without_runner():
    out = A.audit()
    m = out["policyMetricLedgerReconciliation"]
    assert (m["policies"], m["months"], m["days"]) == (7, 152, 4626)
    assert m["verdict"] == "PASS"
    assert m["maxAbsTerminalError"] < 1e-10
    assert m["maxAbsCagrError"] < 1e-12

    h1 = out["h1ForwardAudit"]
    assert (h1["fullyCheckableUsingMonthlyLedger"],
            h1["requiresPostWindowETFPrices"]) == (141, 11)
    assert h1["maxAbsErrorInCheckedRows"] < 1e-10

    h2 = out["h2PosthocHacLagSensitivity"]
    assert h2["registeredLag"] == 0
    assert h2["reconstructedRegisteredH2"] == "PASS"
    assert set(h2["lags"]) == {"0", "1", "3", "6", "12"}
    assert h2["lags"]["0"]["annualMean"] == pytest.approx(0.0003425399656706876, abs=1e-10)
    assert h2["lags"]["0"]["pTwoSided"] == pytest.approx(0.9387543035977153, abs=1e-10)
    assert all(p["pTwoSided"] > 0.05 for p in h2["lags"].values())
    assert h2["role"] == "DESCRIPTIVE_ONLY_NOT_ADDED_TO_HOLM_FAMILY"
    assert out["sealedResultsModified"] is False and out["oneShotExecuted"] is False


def test_dca_preregistered_descriptive_metrics_are_not_all_reported():
    info = A.audit()["dcaPreregOutputCompleteness"]
    assert info["registeredCount"] == 9
    assert info["implementedMetricCount"] == 4
    assert set(info["missing"]) == {
        "time-weighted return", "average cash wait", "cash opportunity cost",
        "worst start cohort", "MDD under identical flows",
    }
    assert info["verdict"] == "INCOMPLETE_DESCRIPTIVE_METRICS"


def _alter_value(tmp_path, field, amount):
    with (A.HERE / "results/phase2-us-monthly.csv").open(newline="") as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames, list(reader)
    rows[0][field] = str(float(rows[0][field]) + amount)
    destination = tmp_path / "tampered-monthly.csv"
    with destination.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return destination


def test_ledger_audit_refuses_tampered_net_return(tmp_path):
    altered = _alter_value(tmp_path, "netB1", 0.01)
    with pytest.raises(AssertionError, match="POLICY_TERMINAL_OR_CAGR_MISMATCH_B1"):
        A.audit(monthly_path=altered)


def test_ledger_audit_refuses_tampered_forward_12m_excess(tmp_path):
    altered = _alter_value(tmp_path, "forward12MExcess", 0.01)
    with pytest.raises(AssertionError, match="FORWARD_12M_MISMATCH_0"):
        A.audit(monthly_path=altered)


def test_ledger_audit_fails_closed_on_nonfinite_numeric_input(tmp_path):
    with (A.HERE / "results/phase2-us-monthly.csv").open(newline="") as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames, list(reader)
    rows[0]["netB1"] = "NaN"
    corrupt = tmp_path / "nan-monthly.csv"
    with corrupt.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(AssertionError, match="NON_FINITE_LEDGER_VALUE_0_netB1"):
        A.audit(monthly_path=corrupt)
