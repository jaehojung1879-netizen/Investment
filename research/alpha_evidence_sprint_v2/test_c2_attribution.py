"""Synthetic regression tests for c2-fixed-exposure-attribution-v1. No real C2 data is read."""
import math
import random

import pytest

from research.alpha_evidence_sprint_v2 import c2_attribution as A

CASH = {"ZERO": 1.0, "BOK_POLICY_PROXY": 1.002, "BOK_POLICY_PLUS_100BP": 1.0028}


def block(weights, growth, betas, etf=1.03, cash=None, date="2020-01-02"):
    return A.Block(date, "2020-02-03", "2019-12-31", weights, growth, betas, etf, cash or CASH, 21 / 252)


def test_pure_beta_book_has_zero_selection_in_every_cash_scenario():
    # each stock is exactly beta * ETF + (1 - beta) * cash  ->  selection must be 0
    r_e = 0.05
    for name, g in CASH.items():
        r_f = g - 1
        betas = {"A": 0.6, "B": 1.3}
        growth = {t: 1 + b * r_e + (1 - b) * r_f for t, b in betas.items()}
        res = A.attribute_block(block({"A": 0.3, "B": 0.2}, growth, betas, etf=1 + r_e, cash={name: g}))
        assert abs(res.by_cash[name]["selection"]) < 1e-12
        # exposure = s*(b-1)*(R_E-R_F) with b the weighted sleeve beta
        b = (0.3 * 0.6 + 0.2 * 1.3) / 0.5
        assert res.by_cash[name]["exposure"] == pytest.approx(0.5 * (b - 1) * (r_e - r_f), abs=1e-12)


def test_planted_alpha_is_recovered_exactly():
    betas = {"A": 0.8}
    growth = {"A": 1 + 0.8 * 0.02 + 0.2 * 0.001 + 0.03}   # +3% beyond the beta-matched twin
    res = A.attribute_block(block({"A": 0.5}, growth, betas, etf=1.02, cash={"BOK_POLICY_PROXY": 1.001}))
    assert res.by_cash["BOK_POLICY_PROXY"]["selection"] == pytest.approx(0.5 * 0.03, abs=1e-12)


def test_identity_selection_plus_exposure_equals_c2_minus_etf_on_random_blocks():
    rng = random.Random(7)
    for _ in range(500):
        names = [f"T{i}" for i in range(rng.randint(1, 5))]
        raw = [rng.random() for _ in names]
        s = rng.uniform(0.1, 0.85)
        weights = {t: s * x / sum(raw) for t, x in zip(names, raw)}
        growth = {t: 1 + rng.gauss(0.01, 0.08) for t in names}
        betas = {t: rng.uniform(0.2, 1.6) for t in names}
        res = A.attribute_block(block(weights, growth, betas, etf=1 + rng.gauss(0.01, 0.06)))
        for v in res.by_cash.values():
            assert v["selection"] + v["exposure"] == pytest.approx(res.c2_gross - res.etf, abs=1e-12)


def test_leverage_is_clipped_and_reported_never_silently_used():
    res = A.attribute_block(block({"A": 0.9}, {"A": 1.1}, {"A": 1.5}))
    assert res.clip == "LEVERAGE_REQUIRED_CAPPED_AT_ETF_100" and res.control_equity == 1.0
    res = A.attribute_block(block({"A": 0.9}, {"A": 1.1}, {"A": -0.5}))
    assert res.clip == "NEGATIVE_EXPOSURE_FLOORED_AT_0" and res.control_equity == 0.0


def test_missing_beta_fails_closed_without_numbers():
    res = A.attribute_block(block({"A": 0.3, "B": 0.2}, {"A": 1.1, "B": 1.0}, {"A": 0.9, "B": None}))
    assert res.status == "BETA_UNAVAILABLE:B" and res.by_cash == {} and res.c2_gross is None


def test_all_etf_block_has_nothing_to_attribute():
    res = A.attribute_block(block({}, {}, {}, etf=1.04))
    assert res.status == "ALL_ETF" and all(v["selection"] == 0 for v in res.by_cash.values())


def test_ols_beta_uses_only_joint_finite_pairs_and_refuses_thin_history():
    rng = random.Random(1)
    etf = [rng.gauss(0, 0.01) for _ in range(252)]
    stock = [0.7 * e + rng.gauss(0, 1e-9) for e in etf]
    beta, n = A.ols_beta(stock, etf)
    assert n == 252 and beta == pytest.approx(0.7, abs=1e-6)
    stock_gappy = [None if i % 4 == 0 else s for i, s in enumerate(stock)]
    beta2, n2 = A.ols_beta(stock_gappy, etf)
    assert beta2 is None and n2 == 189           # < 200 joint pairs: never filled, never forced
    assert A.ols_beta([float("nan")] * 252, etf) == (None, 0)


def test_growth_recovery_reproduces_replay_buy_and_hold_and_rejects_successors():
    w, g, cash, gf = {"A": 0.4, "B": 0.25}, {"A": 1.2, "B": 0.9}, 0.35, 1.001
    end = sum(w[t] * g[t] for t in w) + cash * gf
    tw = {t: w[t] * g[t] / end for t in w}
    got = A.growth_from_terminal(w, tw, end - 1, cash, gf)
    assert got == pytest.approx(g, abs=1e-12)
    with pytest.raises(A.AttributionError, match="SUCCESSOR"):
        A.growth_from_terminal(w, {**tw, "C": 0.1}, end - 1, cash, gf)
    with pytest.raises(A.AttributionError, match="IDENTITY"):
        A.growth_from_terminal(w, tw, end - 1 + 0.01, cash, gf)


def test_turnover_split_separates_replaced_names_from_retargeted_weights():
    prior = {"A": 0.3, "B": 0.2, "069500.KS": 0.5}
    target = {"A": 0.25, "C": 0.2, "069500.KS": 0.55}
    replaced, retargeted = A.turnover_split(prior, target, "069500.KS")
    assert replaced == pytest.approx((0.2 + 0.2) / 2)
    assert retargeted == pytest.approx((0.05 + 0.05) / 2)


def test_cost_uses_side_and_etf_flag_and_scales_with_multiplier():
    def fn(as_of, side, is_etf):
        return (0.0010 if side == "buy" else 0.0030) * (0.5 if is_etf else 1.0)
    prior, target = {"A": 0.2, "069500.KS": 0.8}, {"B": 0.2, "069500.KS": 0.8}
    assert A.trade_cost(prior, target, "069500.KS", fn, "2020-01-02") == pytest.approx(0.2 * 0.001 + 0.2 * 0.003)
    assert A.trade_cost(prior, target, "069500.KS", fn, "2020-01-02", 3.0) == pytest.approx(3 * 0.0008)


def test_jensen_split_is_an_exact_identity():
    rng = random.Random(3)
    c = [rng.gauss(0.01, 0.05) for _ in range(155)]
    b = [rng.gauss(0.01, 0.06) for _ in range(155)]
    j = A.jensen_split(c, b, 13.7)
    assert j["arithmeticActive"] + j["jensen"] == pytest.approx(j["logGrowthGap"], abs=1e-12)


def test_windows_and_drawdown():
    assert A.windows([0.1, -0.1, 0.1], 2) == pytest.approx([1.1 * 0.9 - 1, 0.9 * 1.1 - 1])
    assert A.max_drawdown([1.0, 1.2, 0.9, 1.3]) == pytest.approx(0.9 / 1.2 - 1)
    assert A.cagr(A.chain([0.21]), 2.0) == pytest.approx(0.1, abs=1e-12)


def test_newey_west_matches_iid_variance_at_lag_zero_and_refuses_tiny_samples():
    xs = [1.0, 2.0, 3.0, 4.0]
    nw = A.newey_west(xs, 0)
    assert nw["se"] == pytest.approx(math.sqrt(1.25 / 4))
    assert A.newey_west([1.0, 2.0], 5)["mean"] is None


def test_verdict_needs_all_three_cash_scenarios_to_agree():
    good = {"mean": 0.02, "ci95": [0.001, 0.04], "mean2x": 0.01}
    assert A.verdict({k: good for k in A.CASH_SCENARIOS}) == "SELECTION_SURVIVES_FIXED_EXPOSURE"
    mixed = dict.fromkeys(A.CASH_SCENARIOS, good) | {"ZERO": {"mean": 0.01, "ci95": [-0.01, 0.03], "mean2x": 0.0}}
    assert A.verdict(mixed) == "NO_SELECTION_EVIDENCE_CI_CONTAINS_ZERO"
    assert A.verdict({"ZERO": good}) == "SOURCE_OR_SAMPLE_INSUFFICIENT"
    bad = {"mean": -0.02, "ci95": [-0.04, -0.001], "mean2x": -0.03}
    assert A.verdict({k: bad for k in A.CASH_SCENARIOS}) == "SELECTION_NEGATIVE_AFTER_FIXED_EXPOSURE"
    # a positive 1x interval that does not survive 2x cost is not a survival
    weak = {"mean": 0.004, "ci95": [0.0001, 0.008], "mean2x": -0.001}
    assert A.verdict({k: weak for k in A.CASH_SCENARIOS}) == "NO_SELECTION_EVIDENCE_CI_CONTAINS_ZERO"


def test_summarize_end_to_end_on_a_synthetic_path_without_alpha():
    rng = random.Random(11)
    results, c2, etf, ctrl = [], [], [], {k: [] for k in A.CASH_SCENARIOS}
    for i in range(155):
        r_e = rng.gauss(0.008, 0.05)
        betas = {"A": 0.7, "B": 0.9}
        growth = {t: 1 + b * r_e + (1 - b) * 0.001 + rng.gauss(0, 0.02) for t, b in betas.items()}
        res = A.attribute_block(block({"A": 0.35, "B": 0.25}, growth, betas, etf=1 + r_e,
                                      cash={k: 1.001 for k in A.CASH_SCENARIOS}, date=f"b{i}"))
        results.append(res)
        c2.append(res.c2_gross)
        etf.append(r_e)
        for k in A.CASH_SCENARIOS:
            ctrl[k].append(res.by_cash[k]["control"])
    out = A.summarize(results, c2, ctrl, etf, 155 * 21 / 252, 12.0)
    assert out["attributed"] == 155 and out["betaUnavailable"] == 0
    assert len(out["c2"]["h126"]) == 150 and len(out["c2"]["h252"]) == 144
    per = {k: {**v["selectionAnnualized"], "mean2x": v["selectionAnnualized"]["mean"]}
           for k, v in out["scenarios"].items()}
    assert A.verdict(per) == "NO_SELECTION_EVIDENCE_CI_CONTAINS_ZERO"
