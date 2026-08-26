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
