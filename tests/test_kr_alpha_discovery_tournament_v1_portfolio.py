"""kr-alpha-discovery-tournament-v1: covariance shrinkage, the robust fractional-Kelly allocator, the baselines, the self-financing passive-core
ledger, cost accounting and prospective receipts. Synthetic inputs only."""
from __future__ import annotations

import json

import numpy as np
import pytest
from scipy.optimize import minimize

from pipeline import kr_alpha_tournament as T
from pipeline import kr_alpha_tournament_portfolio as P
from pipeline import kr_alpha_tournament_receipts as RC

B = T.BENCHMARK


def _problem(n=6, seed=0):
    rng = np.random.default_rng(seed)
    A = rng.normal(0, 0.02, (300, n))
    cov = np.cov(A, rowvar=False) * 126
    return rng.normal(0.02, 0.02, n), cov, rng.normal(0, 0.001, n)


# --------------------------------------------------------------------------- #
# Covariance
# --------------------------------------------------------------------------- #
def test_ledoit_wolf_is_psd_scaled_and_drops_incomplete_windows():
    rng = np.random.default_rng(1)
    bench = 100 * np.cumprod(1 + rng.normal(0, 0.01, 253))
    closes = {f"S{i}": 50 * np.cumprod(1 + rng.normal(0, 0.02, 253)) for i in range(5)}
    closes["BAD"] = np.r_[np.nan, closes["S0"][1:]]
    r = P.risk_inputs(closes, bench)
    assert r["tickers"] == [f"S{i}" for i in range(5)]
    assert np.all(np.linalg.eigvalsh(r["cov"]) > 0)
    raw = np.cov(np.column_stack([np.diff(closes[t]) / closes[t][:-1] - np.diff(bench) / bench[:-1] for t in r["tickers"]]), rowvar=False) * 126
    off = ~np.eye(5, dtype=bool)
    assert np.abs(r["cov"][off]).sum() <= np.abs(raw[off]).sum() + 1e-12      # shrunk toward the scaled identity
    assert P.risk_inputs(closes, bench[:-1])["tickers"] == []


# --------------------------------------------------------------------------- #
# Allocator
# --------------------------------------------------------------------------- #
def test_allocator_matches_a_brute_force_solver():
    mu, cov, ceb = _problem()
    n = len(mu)
    w0 = np.zeros(n)
    w0[1] = 0.1
    cb, cs = P.unit_costs()
    lower, upper = np.zeros(n), np.full(n, 0.3)
    w, info = P.allocate(mu, cov, ceb, w0, cb, cs, lower, upper)
    assert info["converged"]
    best = -np.inf
    for start in (w0, np.full(n, 0.1), np.zeros(n)):
        res = minimize(lambda x: -P.objective(x, mu, cov, ceb, w0, np.full(n, cb), np.full(n, cs)), start, method="SLSQP",
                       bounds=list(zip(lower, upper)), constraints=[{"type": "ineq", "fun": lambda x: 1 - x.sum()}], options={"ftol": 1e-14, "maxiter": 2000})
        best = max(best, -res.fun)
    assert P.objective(w, mu, cov, ceb, w0, np.full(n, cb), np.full(n, cs)) >= best - 1e-7


def test_no_convincing_opportunity_means_passive():
    mu, cov, ceb = _problem()
    n = len(mu)
    cb, cs = P.unit_costs()
    w, _ = P.allocate(np.full(n, cb * 0.5), cov, np.zeros(n), np.zeros(n), cb, cs, np.zeros(n), np.full(n, 0.3))
    assert np.all(w == 0)
    w, _ = P.allocate(-np.abs(mu), cov, ceb, np.zeros(n), cb, cs, np.zeros(n), np.full(n, 0.3))
    assert np.all(w == 0)


def test_breadth_is_dynamic_and_caps_and_budget_bind():
    n = 40
    cov = np.eye(n) * 0.01
    cb, cs = P.unit_costs()
    weak, _ = P.allocate(np.r_[0.02, np.zeros(n - 1)], cov, np.zeros(n), np.zeros(n), cb, cs, np.zeros(n), np.full(n, 0.3))
    strong, _ = P.allocate(np.full(n, 0.2), cov, np.zeros(n), np.zeros(n), cb, cs, np.zeros(n), np.full(n, 0.3))
    assert (weak > 0).sum() == 1 and (strong > 0).sum() > 5
    assert strong.sum() <= 1 + 1e-9 and strong.max() <= 0.3 + 1e-12
    capped, _ = P.allocate(np.full(n, 0.2), cov, np.zeros(n), np.zeros(n), cb, cs, np.zeros(n), np.full(n, 0.01))
    assert np.allclose(capped, 0.01)


def test_costs_create_a_hurdle_and_a_no_trade_band():
    cov = np.eye(2) * 0.02
    w_cheap, _ = P.allocate(np.array([0.02, 0.0]), cov, np.zeros(2), np.zeros(2), 0.001, 0.001, np.zeros(2), np.full(2, 0.3))
    w_dear, _ = P.allocate(np.array([0.02, 0.0]), cov, np.zeros(2), np.zeros(2), 0.015, 0.015, np.zeros(2), np.full(2, 0.3))
    assert w_cheap[0] > w_dear[0]
    held = np.array([0.1, 0.0])
    w_hold, _ = P.allocate(np.array([0.004, 0.0]), cov, np.zeros(2), held, 0.006, 0.006, np.zeros(2), np.full(2, 0.3))
    w_flat, _ = P.allocate(np.array([0.004, 0.0]), cov, np.zeros(2), np.zeros(2), 0.006, 0.006, np.zeros(2), np.full(2, 0.3))
    assert w_hold[0] > 0 and w_flat[0] == 0          # selling costs keep a held name a buyer would not open


def test_uncertainty_shrinkage_reduces_weight():
    cov = np.eye(3) * 0.02
    full, _ = P.allocate(np.array([0.04, 0.02, 0.0]), cov, np.zeros(3), np.zeros(3), 0.003, 0.006, np.zeros(3), np.full(3, 0.3))
    shrunk, _ = P.allocate(np.array([0.04, 0.02, 0.0]) * 0.5, cov, np.zeros(3), np.zeros(3), 0.003, 0.006, np.zeros(3), np.full(3, 0.3))
    assert np.all(shrunk <= full + 1e-12) and shrunk.sum() < full.sum()


def test_trade_box_limits_participation_and_holdings():
    lower, upper = P.trade_box(np.array([0.3, 0.0]), [1e9, 1e12], 1e8)
    # held 30% above its 10% liquidity cap: one trade may sell at most 10% of NAV, so it must stay at 20% this time
    assert lower[0] == pytest.approx(0.2) and upper[0] == pytest.approx(0.2) and upper[1] == pytest.approx(0.3)
    lower, upper = P.trade_box(np.array([0.0]), [None], 1e8)
    assert upper[0] == 0.0


def test_baseline_one_uses_the_primary_admission_rule_without_a_new_threshold():
    cb, cs = P.unit_costs()
    w = P.baseline_equal_weight(np.array([cb + cs + 1e-4, cb + cs - 1e-4, 0.5]), cb, cs, np.zeros(3), np.full(3, 0.3))
    assert np.allclose(w, [0.3, 0.0, 0.3])


# --------------------------------------------------------------------------- #
# Ledger
# --------------------------------------------------------------------------- #
class World:
    def __init__(self, n_days=40, missing=None, frozen=None):
        rng = np.random.default_rng(3)
        self.days = [f"2021-01-{i + 1:02d}" if i < 31 else f"2021-02-{i - 30:02d}" for i in range(n_days)]
        self.px = {B: 100 * np.cumprod(1 + rng.normal(0, 0.01, n_days)), "S1": 50 * np.cumprod(1 + rng.normal(0, 0.02, n_days)),
                   "S2": 20 * np.cumprod(1 + rng.normal(0, 0.02, n_days))}
        self.missing, self.frozen = missing or set(), frozen or set()

    def mark(self, t, day, prev):
        if (t, day) in self.missing:
            raise ValueError(P.UNRESOLVED + ": " + t)
        return float(self.px[t][self.days.index(day)])

    def executable(self, t, day):
        return (t, day) not in self.frozen

    def adv(self, t, day):
        return 5e10


def _replay(world, targets, **kw):
    def decide(day, weights, nav):
        return targets.get(day)
    return P.replay(world.days, world.days[0], world.days[-1], world.mark, world.executable, world.adv, decide, **kw)


def test_passive_path_is_exactly_the_benchmark():
    w = World()
    out = _replay(w, {})
    nav = np.array([r["nav"] for r in out["path"]])
    assert np.allclose(nav, w.px[B] / w.px[B][0])


def test_ledger_is_self_financing_and_charges_both_legs():
    before = {B: 1.0}
    adv = {"S1": 5e10}
    out = P.execute(before, {"S1": 0.2}, adv, 1e8)
    k, cost = out["navFactor"], out["costFraction"]
    assert k + cost == pytest.approx(1.0, abs=1e-12)
    expected = 0.2 * k * (T.PORTFOLIO["buyFixedCost"] + T.PORTFOLIO["impactAtOnePercent"] * np.sqrt(0.2 * k * 1e8 / 5e10 / 0.01)) \
        + 0.2 * k * T.PASSIVE_LEG["costEachWay"] + (1.0 - 0.8 * k) * T.PASSIVE_LEG["costEachWay"] - 0.2 * k * T.PASSIVE_LEG["costEachWay"]
    assert cost == pytest.approx(expected, rel=1e-6)
    assert sum(out["weights"].values()) == pytest.approx(1.0) and out["weights"]["S1"] == pytest.approx(0.2)


def test_nav_identity_holds_through_trades():
    w = World()
    out = _replay(w, {w.days[5]: {"S1": 0.25, "S2": 0.1}, w.days[20]: {"S2": 0.3}})
    path = out["path"]
    for prev, cur in zip(path, path[1:]):
        assert cur["nav"] > 0 and cur["activeWeight"] <= 1 + 1e-12
    traded = [p for p in path if p["trade"]]
    assert len(traded) == 2 and all(p["trade"]["costFraction"] > 0 for p in traded)
    assert path[5]["activeNames"] == 2 and path[20]["activeNames"] == 1


def test_a_fully_invested_book_keeps_the_passive_leg_key_and_keeps_valuing():
    """sum w = 1 (passive = 0) is a registered allocator state; the ledger must still read the next session's benchmark return."""
    out = P.execute({B: 1.0}, {"S1": 0.5, "S2": 0.5}, {"S1": 5e10, "S2": 5e10}, 1e8)
    assert out["weights"][B] == 0.0 and sum(out["weights"].values()) == pytest.approx(1.0)
    w = World()
    path = _replay(w, {w.days[5]: {"S1": 0.5, "S2": 0.5}, w.days[20]: {"S1": 0.2}})
    assert path["complete"] and len(path["path"]) == len(w.days)
    assert path["path"][6]["activeWeight"] == pytest.approx(1.0) and path["path"][20]["activeNames"] == 1


def test_allocator_starts_from_a_fully_invested_book_that_rounds_above_one():
    mu, cov, ceb = _problem(n=5, seed=8)
    w0 = np.full(5, 0.2) * (1 + 4e-15)                 # a drifted, renormalised fully invested book: sum w0 = 1 + rounding
    assert w0.sum() > 1.0 + 1e-15
    lower, upper = np.zeros(5), np.full(5, 1.0)
    w, info = P.allocate(mu, cov, ceb, w0, 0.002, 0.004, lower, upper)
    assert w.sum() <= 1.0 + 1e-9 and (w >= 0).all() and np.isfinite(info["objective"])


def test_a_non_executable_holding_is_deferred_not_sold():
    w = World(frozen={("S1", "2021-01-21")})
    out = _replay(w, {w.days[5]: {"S1": 0.25}, w.days[20]: {}})
    assert out["path"][20]["trade"]["deferred"] == ["S1"] and out["path"][20]["activeNames"] == 1


def test_an_unresolved_held_mark_blocks_the_path():
    w = World(missing={("S1", "2021-01-11")})
    out = _replay(w, {w.days[5]: {"S1": 0.25}})
    assert out["complete"] is False and P.UNRESOLVED in out["reason"]


def test_execution_delay_moves_the_trade_one_session():
    w = World()
    now = _replay(w, {w.days[5]: {"S1": 0.25}})
    later = _replay(w, {w.days[5]: {"S1": 0.25}}, delay=1)
    assert now["path"][5]["trade"] and not later["path"][5]["trade"] and later["path"][6]["trade"]


def test_cost_stress_scales_cost():
    w = World()
    base = _replay(w, {w.days[5]: {"S1": 0.25}})
    x2 = _replay(w, {w.days[5]: {"S1": 0.25}}, stress=2.0)
    assert x2["path"][5]["trade"]["costFraction"] == pytest.approx(2 * base["path"][5]["trade"]["costFraction"], rel=1e-3)


# --------------------------------------------------------------------------- #
# Prospective receipts
# --------------------------------------------------------------------------- #
def _receipt(date="2026-10-16", spec="a" * 64, active=None):
    pred = {"ticker": "005930.KS", "eligible": True, "memberScores": {"m": 0.1}, "rank": 0.9, "expectedIncrementalReturn": 0.02,
            "uncertaintyVariance": 0.0001, "contraction": 0.8, "shrunkExpectedIncrementalReturn": 0.016}
    return RC.build_receipt(as_of_utc=date + "T06:00:00Z", decision_date=date, code_sha="b" * 40, spec_sha=spec, data_identity={"sha256": "c" * 64},
                            training_cutoff="2026-01-09", registry_digest="d" * 64, selected=["m"], ensemble_weights={"m": 1.0}, predictions=[pred],
                            active_portfolio=active if active is not None else {"005930.KS": 0.1}, costs={"buy": 0.0015})


def test_receipt_is_sealed_and_derives_the_passive_weight():
    r = _receipt()
    assert RC.verify_receipt(r) and r["passiveWeight"] == pytest.approx(0.9) and set(r) == set(RC.RECEIPT_FIELDS)
    tampered = dict(r, passiveWeight=0.5)
    with pytest.raises(ValueError, match="ALTERED"):
        RC.verify_receipt(tampered)
    with pytest.raises(ValueError, match="LONG_ONLY"):
        _receipt(active={"x": 0.7, "y": 0.6})


def test_receipt_ledger_is_append_only(tmp_path):
    ledger = tmp_path / "receipts.jsonl"
    assert RC.append(ledger, _receipt("2026-10-16")) == 1
    with pytest.raises(ValueError, match="STRICTLY_AFTER"):
        RC.append(ledger, _receipt("2026-10-16"))
    with pytest.raises(ValueError, match="SPEC_CHANGED"):
        RC.append(ledger, _receipt("2026-11-13", spec="e" * 64))
    assert RC.append(ledger, _receipt("2026-11-13")) == 2
    lines = ledger.read_text().splitlines()
    altered = json.loads(lines[0])
    altered["passiveWeight"] = 0.0
    ledger.write_text(json.dumps(altered) + "\n" + lines[1] + "\n")
    with pytest.raises(ValueError, match="ALTERED"):
        RC.append(ledger, _receipt("2026-12-11"))


def test_receipt_schema_names_every_field():
    schema = json.loads(open("research_specs/kr-alpha-discovery-tournament-v1-receipt.schema.json").read())
    assert set(schema["required"]) == set(RC.RECEIPT_FIELDS)
    assert set(schema["properties"]["predictions"]["items"]["required"]) == set(RC.PREDICTION_FIELDS)
