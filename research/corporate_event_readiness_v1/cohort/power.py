"""Outcome-free MDE for the measured independent N, as a FUNCTION of sigma.

No return was read, so sigma (the per-event H-horizon residual-return SD) and
the clustering design effect D are not known: the MDE is published over a
stated grid instead of as one number. Uses the #319 power arithmetic
(``research.next_alpha_research_direction_v1.power``) when it is importable;
the formula is restated here so this packet stands alone on #320.

MDE = (z_{1-alpha/(2m)} + z_power) * sigma * sqrt(D / N), Holm first step m=3.
"""
from __future__ import annotations

from statistics import NormalDist

SIGMA_GRID_PCT = {'H126': (15.0, 20.0, 25.0, 30.0), 'H252': (20.0, 28.0, 35.0, 42.0)}
DESIGN_EFFECTS = (1.0, 2.0, 4.0)
MEE_PP = {'H126': 3.0, 'H252': 4.0}
FAMILY_SIZE = 3


def critical(alpha: float = 0.05, power: float = 0.80, family: int = FAMILY_SIZE) -> float:
    n = NormalDist()
    return n.inv_cdf(1 - alpha / family / 2) + n.inv_cdf(power)


def mde(sigma_pct: float, n: int, design_effect: float) -> float | None:
    if n < 2:
        return None
    return critical() * sigma_pct * (design_effect / n) ** 0.5


def gate(value: float | None, mee: float) -> str:
    if value is None:
        return 'NO_EVENTS'
    if value <= mee:
        return 'POWER_PASS'
    if value <= 2 * mee:
        return 'POWER_MARGINAL'
    return 'POWER_NO_GO'


def power_table(independent: dict) -> dict:
    out = {'status': 'CONDITIONAL_ON_UNMEASURED_SIGMA_AND_DESIGN_EFFECT',
           'formula': 'MDE=(z_{1-.05/6}+z_.80)*sigma*sqrt(D/N)', 'meePp': MEE_PP, 'rows': []}
    for key, desc in sorted(independent.items()):
        horizon = key.rsplit('_', 1)[1]
        n = desc.get('N', 0)
        for sigma in SIGMA_GRID_PCT[horizon]:
            for d in DESIGN_EFFECTS:
                value = mde(sigma, n, d)
                out['rows'].append({'set': key, 'N': n, 'sigmaPct': sigma, 'designEffect': d,
                                    'mdePp': round(value, 2) if value is not None else None,
                                    'gate': gate(value, MEE_PP[horizon])})
    out['valueUpSplit'] = []
    for key, desc in sorted(independent.items()):
        horizon = key.rsplit('_', 1)[1]
        for part in ('preValueUp', 'postValueUp'):
            n = desc.get(part, 0)
            value = mde(SIGMA_GRID_PCT[horizon][1], n, 2.0)
            out['valueUpSplit'].append({'set': key, 'part': part, 'N': n,
                                        'sigmaPct': SIGMA_GRID_PCT[horizon][1], 'designEffect': 2.0,
                                        'mdePp': round(value, 2) if value is not None else None,
                                        'gate': gate(value, MEE_PP[horizon])})
    return out
