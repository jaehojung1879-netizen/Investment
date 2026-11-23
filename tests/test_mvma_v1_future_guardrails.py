"""Prospective MVMA safeguards tested on synthetic files and prices only.

Never executes the sealed #358 one-shot runner or alters its output files.
"""
from __future__ import annotations

import pytest

from research.market_valuation_macro_overlay_v1 import future_guardrails as F
from research.market_valuation_macro_overlay_v1 import phase2 as P2


def _paths(tmp_path):
    return (tmp_path / "result.json", tmp_path / "monthly.csv",
            tmp_path / "one-shot-claim.txt")


def test_claim_refuses_partially_written_monthly_even_without_result(tmp_path):
    result, monthly, claim = _paths(tmp_path)
    monthly.write_text("one partially written outcome row\n")
    with pytest.raises(F.FutureExecutionRefused, match="ONE_SHOT_ALREADY_SPENT"):
        F.claim_future_one_shot(result, monthly, claim)
    assert not claim.exists()
    assert monthly.read_text() == "one partially written outcome row\n"


def test_claim_is_exclusive_and_persists_if_executor_crashes(tmp_path):
    result, monthly, claim = _paths(tmp_path)
    assert F.claim_future_one_shot(result, monthly, claim) == claim
    assert claim.exists()
    with pytest.raises(F.FutureExecutionRefused, match="ONE_SHOT_ALREADY_SPENT"):
        F.claim_future_one_shot(result, monthly, claim)
    assert claim.exists()  # never auto-clear after a failed attempt


def test_claim_refuses_existing_result_and_namespace_aliasing(tmp_path):
    result, monthly, claim = _paths(tmp_path)
    result.write_text("{}")
    with pytest.raises(F.FutureExecutionRefused, match="ONE_SHOT_ALREADY_SPENT"):
        F.claim_future_one_shot(result, monthly, claim)
    result.unlink()
    with pytest.raises(F.FutureExecutionRefused, match="INVALID_OUTPUT_NAMESPACE"):
        F.claim_future_one_shot(result, result, claim)


def test_dca_parked_bil_entry_fee_is_charged_synthetically():
    dates = ["2024-01-02", "2024-02-01", "2024-03-01"]
    flat = dict.fromkeys(dates, 1.0)
    one_way = 0.001
    original = P2.run_dca("DCA-B", [False, False], dates, flat, flat, one_way, 0.5)
    corrected = F.corrected_dca("DCA-B", [False, False], dates, flat, flat, one_way, 0.5)
    assert original["costPaid"] == pytest.approx(0.001)
    assert corrected["costPaid"] == pytest.approx(0.002)
    assert corrected["terminalValue"] == pytest.approx(1.998)
    assert corrected["parkedAtEnd"] == pytest.approx(0.999)
    assert corrected["terminalValue"] < original["terminalValue"]


def test_dca_release_charges_new_spy_buy_bil_sale_and_rebuy():
    dates = ["2024-01-02", "2024-02-01", "2024-03-01"]
    flat = dict.fromkeys(dates, 1.0)
    out = F.corrected_dca("DCA-C", [False, True], dates, flat, flat, 0.001, 0.5)
    # 0.001 for first-month SPY+BIL buys, then 0.001*(1+2*0.4995) on deployment.
    assert out["costPaid"] == pytest.approx(0.002999)
    assert out["terminalValue"] == pytest.approx(1.997001)
    assert out["parkedAtEnd"] == 0.0


def test_dca_immediate_contributions_match_prior_engine_when_no_bil_buys():
    dates = ["2024-01-02", "2024-02-01", "2024-03-01"]
    spy = dict.fromkeys(dates, 1.0)
    bil = dict.fromkeys(dates, 1.0)
    old = P2.run_dca("DCA-A", [False, False], dates, spy, bil, 0.001, 0.5)
    new = F.corrected_dca("DCA-A", [False, False], dates, spy, bil, 0.001, 0.5)
    for metric in ("terminalValue", "xirr", "costPaid", "parkedAtEnd",
                   "averageParkedShare"):
        assert new[metric] == pytest.approx(old[metric])


@pytest.mark.parametrize("triggers", [[], [None], [False, None]])
def test_future_dca_rejects_missing_trigger_or_empty_window(triggers):
    dates = ["2024-01-02", "2024-02-01", "2024-03-01"]
    flat = dict.fromkeys(dates, 1.0)
    with pytest.raises(ValueError):
        F.corrected_dca("DCA-B", triggers, dates, flat, flat, 0.001, 0.5)
