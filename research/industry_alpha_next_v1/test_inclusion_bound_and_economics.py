"""Bounded inclusion and long-only economics. Synthetic only; no market data or outcome is read."""
import json

import numpy as np
import pytest

from . import industry_economics as E
from . import inclusion_bound as B


def _adjust(mode, names, returns):
    industries = list(returns)
    weights = np.array([0.3, 0.2, -0.1, -0.4])
    return B.placement_adjustment({"m": names}, mode)("m", "c", industries, weights, returns)


RETURNS = {"G0": 0.01, "G1": -0.02, "G2": 0.03, "G3": 0.0}


def test_the_bound_is_never_above_the_true_placement_and_narrows_with_evidence():
    rng = np.random.default_rng(0)
    for _ in range(200):
        true_g = f"G{rng.integers(4)}"
        cands = [true_g] + [g for g in rng.permutation(list(RETURNS)) if g != true_g]
        names = [(true_g, cands, float(rng.normal(0, 0.08)), bool(rng.random() < 0.2))]
        true = _adjust("TRUE", names, RETURNS)
        k2, k3, full = (_adjust(m, names, RETURNS) for m in ("BOUND_K2", "BOUND_K3", "BOUND_ALL"))
        assert full <= k3 + 1e-15 and k3 <= k2 + 1e-15 and k2 <= true + 1e-15
        assert _adjust("DROP", names, RETURNS) == 0.0


def test_a_terminal_name_without_consideration_enters_at_minus_100_percent_unless_resolved():
    names = [("G0", ["G0"], 0.05, True)]
    w0 = 0.3
    assert _adjust("TRUE", names, RETURNS) == pytest.approx(w0 * B.SHARE_IF_PLACED * (-1.0 - RETURNS["G0"]))
    resolved = _adjust("BOUND_ALL_TERMINAL_RESOLVED", names, RETURNS)
    assert resolved > _adjust("BOUND_ALL", names, RETURNS)


def test_committed_inclusion_screen_reads_no_outcome_and_matches_its_exposure_inputs():
    out = json.loads((B.C.HERE / "inclusion-bound-screen.json").read_text())
    assert out["historicalOutcomesRead"] == 0 and out["evidenceClass"].startswith("SYNTHETIC")
    exposure = out["realExposure"]
    assert exposure["securities"] == 16 and exposure["memberMonths"] == sum(exposure["byYear"].values())
    assert out["assumptions"]["unknownPerDate"] == exposure["perDate"]["median"]
    for cell in out["rejectionRates"].values():
        assert set(cell) == set(B.MODES)


def test_long_only_book_never_shorts_respects_the_cap_and_keeps_active_weights_balanced():
    rng = np.random.default_rng(1)
    for _ in range(100):
        w = E.A.centred_rank_weights(rng.standard_normal(E.INDUSTRIES))
        book, active = E.long_only(w)
        assert book.min() >= -1e-12 and active.max() <= E.ACTIVE_CAP + 1e-12
        assert abs(active.sum()) < 1e-12 and abs(book.sum() - 1) < 1e-12
        assert np.abs(active).sum() <= E.ACTIVE_GROSS + 1e-12


def test_a_beta_tilt_has_a_raw_spread_and_no_intercept_and_pure_selection_survives():
    rows_beta, rows_pure = [], []
    for rep in range(40):
        rows_beta.append(E.evaluate(E.world(np.random.default_rng(rep), 306, 0.0, signal="BETA")))
        rows_pure.append(E.evaluate(E.world(np.random.default_rng(1000 + rep), 306, E._m(0.20))))
    assert np.median([r["spreadPctYr"] for r in rows_beta]) > 0.5
    assert abs(np.median([r["alphaPctYr"] for r in rows_beta])) < 0.5 < np.median([r["marketBeta"] for r in rows_beta]) * 10
    assert np.median([r["alphaPctYr"] for r in rows_pure]) > 1.0


def test_costs_follow_the_dated_kr_sell_tax_schedule():
    trade = {"G0": 0.2, "G1": 0.8}
    prior = {"G0": 0.8, "G1": 0.2}
    cand = [{"ticker": k, "region": "KR"} for k in trade]
    cfg = E.BA.cost_config({})
    early = E.PV._turnover_cost(trade, prior, cand, cfg, as_of="2016-06-30")["cost"]
    late = E.PV._turnover_cost(trade, prior, cand, cfg, as_of="2025-06-30")["cost"]
    assert early > late > 0


def test_committed_economics_screen_is_synthetic_and_complete():
    out = json.loads((B.C.HERE / "industry-economics-screen.json").read_text())
    assert out["historicalOutcomesRead"] == 0 and out["evidenceClass"].startswith("SYNTHETIC")
    assert {k.split("_", 1)[1] for k in out["cells"]} == set(E.SCENARIOS)
