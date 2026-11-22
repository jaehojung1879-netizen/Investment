"""Read-only targeted audit of MVMA PR #358; never invokes the sealed one-shot runner.

Two narrow regressions are documented here:
* Level-3 risk uses mixed daily/monthly drawdown units in the sealed verdict,
  but the all-conditions verdict remains NOT_MET when units are made comparable.
* The separately reported DCA parking path omits the BIL entry trade cost.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pytest

from research.market_valuation_macro_overlay_v1 import phase2 as P2
from research.market_valuation_macro_overlay_v1.vendor import market_timing_pr316 as MT

ROOT = Path(__file__).resolve().parents[1]
MVMA = ROOT / "research/market_valuation_macro_overlay_v1"


def test_level3_drawdown_frequency_mismatch_does_not_flip_verdict():
    """A daily-vs-monthly comparison fails where the comparable monthly check passes."""
    result = json.loads((MVMA / "results/phase2-us-result.json").read_text())
    with (MVMA / "results/phase2-us-monthly.csv").open(newline="") as handle:
        months = list(csv.DictReader(handle))
    assert len(months) == result["primary"]["periods"] == 152

    vm_monthly = np.array([float(r["netVM1T"]) for r in months])
    b0_monthly = np.array([float(r["netB0"]) for r in months])
    vm_mdd_monthly = MT.max_drawdown(vm_monthly)
    equal_vol_mdd_monthly = result["verdicts"]["equalVolatilityStaticMaxDrawdownMonthly"]
    vm_mdd_daily = result["primary"]["policies"]["VM1T"]["net"]["maxDrawdown"]

    # The sealed verdict compares vm_mdd_daily against equal_vol_mdd_monthly.
    assert vm_mdd_daily < equal_vol_mdd_monthly < vm_mdd_monthly
    assert vm_mdd_monthly > MT.max_drawdown(b0_monthly)

    # On the common monthly unit the MDD hurdle passes, but worst-12M still fails.
    vm_worst12 = result["primary"]["policies"]["VM1T"]["net"]["worst12Months"]
    static_worst12 = result["verdicts"]["equalVolatilityStaticWorst12Months"]
    assert vm_worst12 < static_worst12
    assert result["verdicts"]["level3RiskPath"] == "NOT_MET"
    assert result["verdicts"]["promotionEligible"] is False


@pytest.mark.xfail(
    reason="KNOWN_DCA_COST_GAP: parking 50% in BIL omits its entry one-way cost",
    strict=True,
)
def test_dca_parking_pays_both_spy_and_bil_entry_costs():
    """Minimal counterexample: flat markets, two 1-unit contributions, 10bp per buy leg."""
    dates = ["2024-01-02", "2024-02-01", "2024-03-01"]
    flat = dict.fromkeys(dates, 1.0)
    one_way = 0.001
    outcome = P2.run_dca("DCA-B", [False, False], dates, flat, flat, one_way, 0.5)

    # Correct: 2 contributions * (0.5 SPY buy + 0.5 BIL buy) * 10bp = 0.002.
    # Current sealed code charges only the 0.5 SPY purchase: 0.001.
    assert outcome["costPaid"] == pytest.approx(0.002)


def test_posthoc_dca_fee_correction_matches_sealed_results_before_adjustment():
    """An isolated audit recovers every sealed DCA metric before changing BIL entry fees."""
    from research.market_valuation_macro_overlay_v1 import audit_358_posthoc as AUD

    out = AUD.audit()
    assert out["primaryHypothesesReexecuted"] is False
    assert out["resultFilesModified"] is False
    assert out["months"] == 152
    assert out["dca"]["DCA-A"]["deltaTerminal"] == pytest.approx(0.0, abs=1e-12)
    assert out["dca"]["DCA-A"]["deltaXirrPp"] == pytest.approx(0.0, abs=1e-12)

    b, c = out["dca"]["DCA-B"], out["dca"]["DCA-C"]
    assert b["withBilEntryFee"]["terminalValue"] == pytest.approx(383.860322517858, abs=1e-6)
    assert c["withBilEntryFee"]["terminalValue"] == pytest.approx(360.805132024698, abs=1e-6)
    assert b["deltaXirrPp"] == pytest.approx(-0.000508810013, abs=1e-7)
    assert c["deltaXirrPp"] == pytest.approx(-0.001259668248, abs=1e-7)
    for rule in ("DCA-B", "DCA-C"):
        assert out["dca"][rule]["withBilEntryFee"]["costPaid"] > out["dca"][rule]["sealed"]["costPaid"]
        assert out["dca"][rule]["deltaTerminal"] < 0


def test_posthoc_matched_risk_uses_net_static_and_one_common_frequency():
    from research.market_valuation_macro_overlay_v1 import audit_358_posthoc as AUD

    risk = AUD.audit()["risk"]
    assert risk["vmMddMonthly"] == pytest.approx(-0.202992168878, abs=1e-10)
    assert risk["equalVolStaticMddMonthlyNet"] == pytest.approx(-0.207128873467, abs=1e-10)
    assert risk["equalVolStaticWorst12Net"] == pytest.approx(-0.163465632754, abs=1e-10)
    assert risk["checks"] == {
        "vmMddShallowerThanB0Monthly": True,
        "vmMddShallowerThanEqualVolMonthlyNet": True,
        "vmWorst12BetterThanB0": True,
        "vmWorst12BetterThanEqualVolMonthlyNet": False,
    }
    assert risk["allRiskCriteriaMet"] is False
    assert risk["sealedRiskVerdict"] == "NOT_MET"


def test_posthoc_cost_definition_gap_is_reported_not_attributed_to_timing():
    from research.market_valuation_macro_overlay_v1 import audit_358_posthoc as AUD

    a = AUD.audit()["attribution"]
    assert a["costDefinitionsDiffer"] is True
    assert a["driftAndResetResidualAnnualPp"] == pytest.approx(-0.001755503788, abs=1e-9)
    assert abs(a["driftAndResetResidualAnnualPp"]) < 0.01


@pytest.mark.xfail(
    reason="KNOWN_PARTIAL_OUTPUT_GATE: MONTHLY may exist after a crash while RESULT is absent",
    strict=True,
)
def test_one_shot_gate_refuses_partial_monthly_output_before_result(tmp_path, monkeypatch):
    """The executor writes MONTHLY before RESULT, but only RESULT is checked before run."""
    from research.market_valuation_macro_overlay_v1 import execute_phase2 as EX

    orphan = tmp_path / "phase2-us-monthly.csv"
    orphan.write_text("decisionDate,forward12MExcess\\n2024-08-30,0.1\\n")
    monkeypatch.setattr(EX, "MONTHLY", orphan)
    monkeypatch.setattr(EX, "RESULT", tmp_path / "phase2-us-result.json")
    monkeypatch.setattr(EX, "AUTHORIZATION", tmp_path / "missing-authorization.json")

    # Must refuse on the substantive MONTHLY output BEFORE reading authorization.
    # Sealed implementation currently only checks RESULT, so this is expected to fail.
    with pytest.raises(EX.ExecutionRefused, match="ONE_SHOT_ALREADY_SPENT"):
        EX.verify_authorization()
