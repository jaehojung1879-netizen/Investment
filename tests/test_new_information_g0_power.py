"""Synthetic power-contract tests. No labels, returns or price series."""
from math import isclose

import pytest

from research.new_information_g0_v1.power_gate import normalized_mde, scenarios


def test_monotone_effect_threshold():
    assert normalized_mde(20) > normalized_mde(80) > normalized_mde(320)
    assert isclose(normalized_mde(20), 0.6265, rel_tol=0.002)


def test_more_multiplicity_reduces_power():
    assert normalized_mde(40, family_size=3) > normalized_mde(40, family_size=1)


def test_invalid_assumptions_rejected():
    for n in (0, -3, 1):
        with pytest.raises(ValueError):
            normalized_mde(n)
    with pytest.raises(ValueError):
        normalized_mde(80, family_size=0)


def test_scenarios_have_no_pnl_or_signals():
    results = scenarios()
    assert len(results) == 6
    assert not any("return" in str(x).lower() for x in results)
