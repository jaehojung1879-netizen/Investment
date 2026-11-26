"""MVMA-v1 point-in-time features and pre-registered policies (synthetic inputs only)."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from research.market_valuation_macro_overlay_v1 import features as F
from research.market_valuation_macro_overlay_v1 import signals as S


def month_ends(n, start=date(2000, 1, 31)):
    out, y, m = [], start.year, start.month
    for _ in range(n):
        nxt = date(y + m // 12, m % 12 + 1, 1)
        out.append(nxt - timedelta(days=1))
        y, m = nxt.year, nxt.month
    return out


# ------------------------------------------------------------------ as-of / publication

def test_asof_ignores_values_not_yet_effective():
    obs = [F.Observation(date(2020, 1, 31), date(2020, 2, 10), 1.0),
           F.Observation(date(2020, 2, 29), date(2020, 3, 10), 2.0)]
    assert F.asof(obs, date(2020, 2, 9)) is None
    assert F.asof(obs, date(2020, 2, 10)).value == 1.0
    assert F.asof(obs, date(2020, 3, 9)).value == 1.0
    assert F.asof(obs, date(2020, 3, 10)).value == 2.0


def test_publication_delay_of_one_day_moves_only_later_decisions():
    decisions = month_ends(6)
    obs = [F.Observation(d, d, float(i)) for i, d in enumerate(decisions)]
    base = F.decision_series(obs, decisions)
    delayed = [F.Observation(o.observation_date, o.effective_at + timedelta(days=1), o.value) if i == 3 else o
               for i, o in enumerate(obs)]
    moved = F.decision_series(delayed, decisions)
    assert moved[:3] == base[:3]
    assert moved[3] == base[2]          # the delayed print is not yet usable on its own decision date
    assert moved[4:] == base[4:]


def test_later_revision_does_not_rewrite_recorded_history():
    decisions = month_ends(4)
    obs = [F.Observation(decisions[0], decisions[0], 10.0)]
    first = F.decision_series(obs, decisions)
    revised = obs + [F.Observation(decisions[0], decisions[2], 99.0)]   # same period, revised later
    second = F.decision_series(revised, decisions)
    assert second[:2] == first[:2] == [10.0, 10.0]
    assert second[2:] == [99.0, 99.0]


# ------------------------------------------------------------------ valuation

def test_price_to_earnings_missing_for_nonpositive_earnings():
    assert F.price_to_earnings(100.0, 5.0) == 20.0
    assert F.price_to_earnings(100.0, 0.0) is None
    assert F.price_to_earnings(100.0, -1.0) is None
    assert F.price_to_earnings(None, 5.0) is None


def test_trailing_mean_excludes_current_and_requires_54_of_60():
    values = [10.0] * 60 + [1.0]
    assert F.trailing_mean_prior(values, 60) == 10.0
    assert F.valuation_discount(values, 60) == pytest.approx(-0.9)
    assert F.valuation_cheap(values, 60) is True
    assert F.trailing_mean_prior(values, 59) is None          # fewer than 60 prior decisions
    holes = [None] * 7 + [10.0] * 53 + [12.0]
    assert F.trailing_mean_prior(holes, 60) is None            # 53 < 54 measured
    holes = [None] * 6 + [10.0] * 54 + [12.0]
    assert F.valuation_cheap(holes, 60) is False


def test_future_contamination_cannot_change_past_signals():
    rng = np.random.default_rng(7)
    values = list(15 + rng.standard_normal(200))
    before = [F.valuation_cheap(values, i) for i in range(200)]
    poisoned = values[:120] + [1e9] * 80
    after = [F.valuation_cheap(poisoned, i) for i in range(200)]
    assert after[:120] == before[:120]


def test_earnings_stable_compares_with_three_decisions_ago():
    eps = [1.0, 2.0, 3.0, 3.0, 1.0, None]
    assert F.earnings_stable(eps, 2) is None
    assert F.earnings_stable(eps, 3) is True
    assert F.earnings_stable(eps, 4) is False      # 1.0 < 2.0
    assert F.earnings_stable(eps, 5) is None


# ------------------------------------------------------------------ credit

def test_percentile_matches_numpy_type7():
    rng = np.random.default_rng(3)
    sample = list(rng.standard_normal(57))
    assert F.percentile_linear(sample, 75.0) == pytest.approx(float(np.percentile(sample, 75.0)))


def test_credit_stress_needs_high_level_and_recent_widening():
    calm = [1.0 + 0.001 * i for i in range(60)]
    assert F.credit_stress(calm + [5.0], 60) is True
    rising_then_easing = calm[:-3] + [6.0, 6.0, 6.0] + [5.0]   # high but narrower than 3 decisions ago
    assert F.credit_stress(rising_then_easing, 60) is False
    assert F.credit_stress(calm + [1.0], 60) is False
    assert F.credit_stress(calm[:59] + [5.0], 59) is None       # not enough history


def test_credit_stress_reads_prior_values_only():
    rng = np.random.default_rng(11)
    spreads = list(2 + rng.standard_normal(150).cumsum() * 0.05)
    before = [F.credit_stress(spreads, i) for i in range(150)]
    after = [F.credit_stress(spreads[:100] + [50.0] * 50, i) for i in range(150)]
    assert after[:100] == before[:100]


# ------------------------------------------------------------------ drawdown

def test_drawdown_window_inclusive_and_missing_session_is_missing():
    closes = [100.0] * 251 + [79.0]
    assert F.drawdown_from_high(closes, 251) == pytest.approx(-0.21)
    assert F.deep_drawdown(closes, 251) is True
    assert F.deep_drawdown([100.0] * 251 + [81.0], 251) is False
    assert F.drawdown_from_high([100.0] * 250 + [79.0], 250) is None
    gap = [100.0] * 200 + [None] + [100.0] * 50 + [79.0]
    assert F.drawdown_from_high(gap, 251) is None


# ------------------------------------------------------------------ Shiller lag

@pytest.mark.parametrize("decision,expected", [((2024, 10), (2024, 6)), ((2024, 9), (2024, 3)),
                                               ((2024, 7), (2024, 3)), ((2024, 6), (2023, 12)),
                                               ((2024, 1), (2023, 9))])
def test_shiller_earnings_read_only_at_quarter_end_four_months_back(decision, expected):
    idx = F.shiller_earnings_effective_month(F.month_index(*decision))
    assert F.month_from_index(idx) == expected
    assert F.month_from_index(idx)[1] in (3, 6, 9, 12)
    assert F.month_index(*decision) - idx >= F.SHILLER_EARNINGS_LAG_MONTHS


# ------------------------------------------------------------------ policies

def test_static_policies_and_bounds():
    for name, weight in S.STATIC_POLICIES.items():
        path = S.target_path(name, [{}] * 5)
        assert path["targets"] == [weight] * 5 and path["holds"] == 0


def test_vm1_priority_one_beats_valuation():
    assert S.determined_target("VM1", {"cheap": True, "earningsStable": False, "creditStress": True}) == 0.6
    assert S.determined_target("VM1", {"cheap": True, "earningsStable": True, "creditStress": False}) == 1.0
    assert S.determined_target("VM1", {"cheap": False, "earningsStable": True, "creditStress": False}) == 0.8
    assert S.determined_target("VM1", {"cheap": True, "earningsStable": True, "creditStress": True}) == 0.8


def test_determined_answer_is_not_missing():
    # deteriorating + stressed fixes 0.6 whatever valuation is
    assert S.determined_target("VM1", {"cheap": None, "earningsStable": False, "creditStress": True}) == 0.6
    # cheap unknown with stable & calm could be 1.0 or 0.8 -> undetermined
    assert S.determined_target("VM1", {"cheap": None, "earningsStable": True, "creditStress": False}) is None
    # not cheap makes 1.0 impossible; stress unknown with stable earnings is always 0.8
    assert S.determined_target("VM1", {"cheap": False, "earningsStable": True, "creditStress": None}) == 0.8
    assert S.determined_target("M1", {"earningsStable": None, "creditStress": False}) is None
    assert S.determined_target("V1", {"cheap": None}) is None


def test_target_path_holds_previous_and_starts_at_middle_weight():
    states = [{"cheap": None}, {"cheap": True}, {"cheap": None}, {"cheap": False}]
    path = S.target_path("V1", states)
    assert path["targets"] == [0.8, 1.0, 1.0, 0.6]
    assert path["holds"] == 2 and path["firstDetermined"] == 1
    assert all(0.0 <= w <= 1.0 for w in path["targets"])


def test_every_dynamic_rule_only_emits_registered_weights():
    from itertools import product
    for name, (rule, inputs) in S.RULES.items():
        for combo in product((False, True), repeat=len(inputs)):
            assert rule(dict(zip(inputs, combo))) in S.WEIGHTS, name
