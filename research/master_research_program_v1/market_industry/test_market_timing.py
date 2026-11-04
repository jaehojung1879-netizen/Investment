"""Synthetic tests for the LEVEL / TIMING decomposition. No real market data is read."""
import numpy as np
import pytest

from research.master_research_program_v1.market_industry import market_timing as T


def _random(seed, n=400):
    rng = np.random.default_rng(seed)
    x = rng.choice([1.0, 0.7, 0.4], size=n)
    r_e = rng.normal(0.002, 0.03, size=n)
    r_f = rng.normal(0.0004, 0.0002, size=n)
    return x, r_e, r_f


@pytest.mark.parametrize("seed", range(20))
def test_identity_holds_on_random_data(seed):
    x, r_e, r_f = _random(seed)
    d = T.decompose(x, r_e, r_f, buy_cost=0.0015, sell_cost=0.0045)
    active = np.mean(T.overlay_returns(x, r_e, r_f) - r_e)
    assert abs(active - (d["level"] + d["timing"])) < 1e-14
    static = d["averageExposure"] * r_e + (1 - d["averageExposure"]) * r_f
    assert abs(np.mean(T.overlay_returns(x, r_e, r_f) - static) - d["timing"]) < 1e-14
    assert abs(d["meanActiveNet"] - (d["level"] + d["timing"] - d["meanCost"])) < 1e-14


def test_constant_exposure_has_zero_timing_and_zero_cost():
    _, r_e, r_f = _random(1)
    for level in (1.0, 0.7, 0.4):
        d = T.decompose(np.full(r_e.size, level), r_e, r_f, buy_cost=0.01, sell_cost=0.01)
        assert d["timing"] == pytest.approx(0.0, abs=1e-18)
        assert d["meanCost"] == 0.0
        assert d["exposureChanges"] == 0
        assert d["maxDrawdown"]["overlayGross"] == pytest.approx(d["maxDrawdown"]["staticControl"])


def test_full_exposure_has_zero_level():
    _, r_e, r_f = _random(2)
    d = T.decompose(np.ones(r_e.size), r_e, r_f)
    assert d["level"] == 0.0 and d["meanActiveGross"] == pytest.approx(0.0, abs=1e-18)


def test_perfect_foresight_timing_is_positive_and_beats_matched_static():
    rng = np.random.default_rng(7)
    r_e = rng.normal(0.001, 0.03, size=500)
    r_f = np.zeros(500)
    x = np.where(r_e > 0, 1.0, 0.4)           # knows this period's return in advance (forbidden in practice)
    d = T.decompose(x, r_e, r_f)
    assert d["timing"] > 0
    assert d["maxDrawdown"]["overlayGross"] > d["maxDrawdown"]["staticControl"]


def test_perverse_timing_is_negative():
    rng = np.random.default_rng(8)
    r_e = rng.normal(0.001, 0.03, size=500)
    d = T.decompose(np.where(r_e > 0, 0.4, 1.0), r_e, np.zeros(500))
    assert d["timing"] < 0


def test_lower_level_alone_is_risk_reduction_not_timing():
    # constant 0.4 exposure: shallower drawdown than the ETF, LEVEL negative in a rising market, TIMING exactly zero
    rng = np.random.default_rng(9)
    r_e = rng.normal(0.003, 0.04, size=300)
    d = T.decompose(np.full(300, 0.4), r_e, np.zeros(300))
    mdd = d["maxDrawdown"]
    assert mdd["staticControl"] > mdd["etf"]
    assert T.classify_reading(-0.001, 0.001, mdd["overlayGross"], mdd["staticControl"], mdd["etf"], d["level"]) == "A_ONLY_LEVEL_RISK_REDUCTION"
    assert T.classify_reading(0.0001, 0.002, 0, 0, 0, 0) == "B_TIMING_SUPPORTED"
    assert T.classify_reading(-0.002, -0.0001, 0, 0, 0, 0) == "TIMING_NEGATIVE"


def test_costs_charge_only_changes_and_not_the_build():
    x = np.array([0.4, 0.4, 1.0, 0.7, 0.7])
    c = T.exposure_change_costs(x, buy_cost=0.001, sell_cost=0.002, stress=2.0)
    assert c.tolist() == pytest.approx([0.0, 0.0, 2 * 0.001 * 0.6, 2 * 0.002 * 0.3, 0.0])


def test_max_drawdown_known_path():
    assert T.max_drawdown([0.1, -0.5, 0.2]) == pytest.approx(-0.5)
    assert T.max_drawdown([0.01, 0.02]) == 0.0


def test_newey_west_lag_zero_is_iid_se():
    z = np.random.default_rng(3).normal(size=200)
    nw = T.newey_west_mean(z, 0)
    assert nw["se"] == pytest.approx(np.sqrt(np.var(z) / 200))
    assert T.newey_west_mean(z, 26)["lag"] == 26


def test_inputs_are_validated():
    with pytest.raises(ValueError):
        T.decompose([1.0, 0.7], [0.01], [0.0, 0.0])
    with pytest.raises(ValueError):
        T.decompose([1.0, float("nan")], [0.01, 0.02], [0.0, 0.0])


def test_exposure_at_reads_only_the_past():
    states = [("2026-10-30", 1.0), ("2026-11-06", 0.7)]
    assert T.exposure_at(states, "2026-10-29") is None
    assert T.exposure_at(states, "2026-10-30") == 1.0
    assert T.exposure_at(states, "2026-11-05") == 1.0
    assert T.exposure_at(states, "2026-11-06") == 0.7


def test_future_state_cannot_change_past_exposure():
    past = [("2026-10-30", 1.0), ("2026-11-06", 0.7)]
    starts = ["2026-10-30", "2026-11-02", "2026-11-06", "2026-11-09"]
    before = T.exposure_path(past, starts)
    after = T.exposure_path(past + [("2026-11-13", 0.4), ("2027-01-01", 0.4)], starts)
    assert before == after == [1.0, 1.0, 0.7, 0.7]


def test_duplicate_state_dates_refused():
    with pytest.raises(ValueError):
        T.exposure_at([("2026-10-30", 1.0), ("2026-10-30", 0.7)], "2026-11-01")


def test_sealed_multipliers_are_imported_not_copied():
    from pipeline import kr_market_risk_model as K
    assert T.sealed_mapping_table("C0") == K.mapping_table("C0")
    assert T.sealed_multiplier("C0", None, None, 2) == 0.4
    assert T.sealed_multiplier("C1", None, None, 1) is None      # gated: missing confirmation layers decide it
    assert T.sealed_multiplier("C0", None, None, 1) == 0.7
