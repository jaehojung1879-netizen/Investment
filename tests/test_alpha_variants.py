"""The variant harness must not leak one variant's alpha into the next.

It mutates the signal list in place — copying 295k signals cost 9.4 GB of a
16 GB box and never finished — so the restore is load-bearing rather than
tidiness. A leak here would silently score the previous variant and every
number downstream would be wrong in a way nothing else would catch.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "compare_alpha_variants", ROOT / "scripts" / "compare_alpha_variants.py")
CAV = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CAV)


def _signals():
    """One date, one region, momentum and lowvol deliberately anti-correlated."""
    return [{
        "id": f"s{i}", "date": "2020-01-06", "region": "US", "ticker": f"T{i}",
        "alphaPercentile": 50.0, "longTermAlphaPercentile": 50.0,
        "alpha": 0.0, "rawAlpha": 0.0,
        "factorPercentiles": {"momentum": float(i * 10), "lowvol": float(90 - i * 10),
                              "value": None, "quality": None},
    } for i in range(10)]


def test_a_variant_is_reverted_when_the_block_ends():
    signals = _signals()
    before = [(row["alphaPercentile"], row["alpha"]) for row in signals]

    with CAV.alpha_variant(signals, "V1_MOMENTUM_ONLY") as applied:
        assert applied is signals
        assert [row["alphaPercentile"] for row in signals] != [b[0] for b in before]

    assert [(row["alphaPercentile"], row["alpha"]) for row in signals] == before


def test_a_variant_is_reverted_even_when_the_body_raises():
    signals = _signals()
    before = [row["alphaPercentile"] for row in signals]

    with pytest.raises(RuntimeError):
        with CAV.alpha_variant(signals, "V1_MOMENTUM_ONLY"):
            raise RuntimeError("replay blew up")

    assert [row["alphaPercentile"] for row in signals] == before


def test_momentum_only_ranks_by_momentum():
    signals = _signals()
    with CAV.alpha_variant(signals, "V1_MOMENTUM_ONLY"):
        order = [row["ticker"] for row in
                 sorted(signals, key=lambda r: -r["alphaPercentile"])]
    assert order[0] == "T9" and order[-1] == "T0"      # T9 has the top momentum


def test_lowvol_only_ranks_the_other_way():
    """The sleeves are anti-correlated in this fixture, so the order must flip."""
    signals = _signals()
    with CAV.alpha_variant(signals, "V2_LOWVOL_ONLY"):
        order = [row["ticker"] for row in
                 sorted(signals, key=lambda r: -r["alphaPercentile"])]
    assert order[0] == "T0" and order[-1] == "T9"


def test_production_is_left_exactly_as_stored():
    signals = _signals()
    for row in signals:
        row["alphaPercentile"] = 77.0
    with CAV.alpha_variant(signals, "V0_PRODUCTION"):
        assert all(row["alphaPercentile"] == 77.0 for row in signals)


def test_alpha_stays_a_monotone_transform_of_the_percentile():
    """The research screen re-ranks on alpha, so the two must not disagree."""
    signals = _signals()
    with CAV.alpha_variant(signals, "V4_MOMENTUM_TILT"):
        by_pct = [r["ticker"] for r in sorted(signals, key=lambda r: -r["alphaPercentile"])]
        by_alpha = [r["ticker"] for r in sorted(signals, key=lambda r: -r["alpha"])]
    assert by_pct == by_alpha


def test_a_name_without_the_needed_sleeves_is_left_alone():
    """A variant may not resurrect a name the replay could not score."""
    signals = _signals()
    signals[3]["factorPercentiles"] = {"momentum": None, "lowvol": None}
    with CAV.alpha_variant(signals, "V1_MOMENTUM_ONLY"):
        assert signals[3]["alphaPercentile"] == 50.0     # untouched original


def test_each_date_and_region_is_ranked_in_its_own_cross_section():
    signals = _signals()
    for row in signals[5:]:
        row["region"] = "KR"

    with CAV.alpha_variant(signals, "V1_MOMENTUM_ONLY"):
        us = [row["alphaPercentile"] for row in signals if row["region"] == "US"]
        kr = [row["alphaPercentile"] for row in signals if row["region"] == "KR"]

    # Each cell is ranked 0-100 on its own, so both reach the top.
    assert max(us) == pytest.approx(100.0)
    assert max(kr) == pytest.approx(100.0)


def test_the_regional_split_is_flagged_as_region_specific():
    """One sample, two regions, a rule picked after seeing both."""
    assert "V5_REGIONAL_SPLIT" in CAV.REGION_VARIANTS
    assert CAV.REGION_VARIANTS["V5_REGIONAL_SPLIT"]["US"] == {"momentum": 1.0}


def test_the_regional_split_uses_a_different_blend_per_region():
    signals = _signals()
    for row in signals[5:]:
        row["region"] = "KR"

    assert CAV._blend_for("V5_REGIONAL_SPLIT", "US") == {"momentum": 1.0}
    assert CAV._blend_for("V5_REGIONAL_SPLIT", "KR") == CAV.BASELINE_BLEND


# --------------------------------------------------------------------------- #
# The percentile-to-z recovery
# --------------------------------------------------------------------------- #
def test_probit_recovers_a_z_blend_far_better_than_a_percentile_blend():
    """The V3 control failed because a percentile blend is not a z blend.

    Production blends sector-neutral z-scores; the ledger only stores their
    percentiles. Blending the percentiles directly returned Sharpe 0.325 where
    production scored 1.094 on the same dates — a percentile throws away
    magnitude, and momentum has a fat cross-sectional tail.

    Build a cross-section with a KNOWN z blend, reduce it to percentiles the way
    the ledger does, and check which reconstruction reproduces the true
    ordering.
    """
    import numpy as np
    from scipy.stats import rankdata

    rng = np.random.default_rng(11)
    n = 400
    # Momentum with a fat tail, low-vol closer to normal: the shape that makes
    # the two reconstructions disagree.
    momentum_z = rng.standard_t(df=3, size=n)
    lowvol_z = rng.normal(size=n)
    truth = 0.6 * momentum_z + 0.4 * lowvol_z

    to_pct = lambda z: rankdata(z) / len(z) * 100
    mom_pct, low_pct = to_pct(momentum_z), to_pct(lowvol_z)

    via_percentile = 0.6 * mom_pct + 0.4 * low_pct
    via_probit = np.array([0.6 * CAV._to_z(m) + 0.4 * CAV._to_z(l)
                           for m, l in zip(mom_pct, low_pct)])

    corr = lambda a, b: float(np.corrcoef(rankdata(a), rankdata(b))[0, 1])
    assert corr(via_probit, truth) > corr(via_percentile, truth)
    assert corr(via_probit, truth) > 0.98


def test_probit_leaves_a_single_sleeve_ordering_untouched():
    """Monotone, so momentum-only must rank identically before and after."""
    signals = _signals()
    with CAV.alpha_variant(signals, "V1_MOMENTUM_ONLY"):
        order = [r["ticker"] for r in sorted(signals, key=lambda r: -r["alphaPercentile"])]
    assert order == [f"T{i}" for i in range(9, -1, -1)]


def test_the_extremes_are_clipped_rather_than_infinite():
    """A 0 or 100 percentile must not become -inf/+inf and poison the blend."""
    import math
    assert math.isfinite(CAV._to_z(0.0))
    assert math.isfinite(CAV._to_z(100.0))
    assert CAV._to_z(0.0) < CAV._to_z(50.0) < CAV._to_z(100.0)


# --------------------------------------------------------------------------- #
# The outcomes carry their own copy of alphaPercentile
# --------------------------------------------------------------------------- #
def _outcomes(signals):
    """Outcome rows as the ledger writes them: alphaPercentile copied across."""
    return [{"id": row["id"], "date": row["date"], "region": row["region"],
             "ticker": row["ticker"], "alphaPercentile": row["alphaPercentile"],
             "horizons": {"126": {"excessReturn": 0.01}}}
            for row in signals]


def test_the_variant_reaches_the_outcomes_not_only_the_signals():
    """`_joined_frame` reads alphaPercentile from the OUTCOMES.

    Rewriting only the signals left every variant reporting production's rank IC
    under its own name — identical to six decimal places across variants, which
    is how it was caught.
    """
    signals = _signals()
    outcomes = _outcomes(signals)

    with CAV.alpha_variant(signals, "V1_MOMENTUM_ONLY", outcomes):
        by_id = {row["id"]: row["alphaPercentile"] for row in signals}
        assert all(row["alphaPercentile"] == by_id[row["id"]] for row in outcomes)
        assert len({row["alphaPercentile"] for row in outcomes}) > 1   # actually varied


def test_the_outcomes_are_restored_too():
    signals = _signals()
    outcomes = _outcomes(signals)
    before = [row["alphaPercentile"] for row in outcomes]

    with CAV.alpha_variant(signals, "V1_MOMENTUM_ONLY", outcomes):
        pass

    assert [row["alphaPercentile"] for row in outcomes] == before


def test_the_outcomes_are_restored_when_the_body_raises():
    signals = _signals()
    outcomes = _outcomes(signals)
    before = [row["alphaPercentile"] for row in outcomes]

    with pytest.raises(RuntimeError):
        with CAV.alpha_variant(signals, "V1_MOMENTUM_ONLY", outcomes):
            raise RuntimeError("replay blew up")

    assert [row["alphaPercentile"] for row in outcomes] == before


def test_an_outcome_without_a_matching_signal_is_left_alone():
    signals = _signals()
    outcomes = _outcomes(signals) + [{"id": "orphan", "alphaPercentile": 42.0}]

    with CAV.alpha_variant(signals, "V1_MOMENTUM_ONLY", outcomes):
        assert outcomes[-1]["alphaPercentile"] == 42.0
