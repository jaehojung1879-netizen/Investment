"""Registered decision order (spec ``decisionOrder``; Owner contract D).

1 SOURCE_BLOCKED -> 2 REJECT_ECONOMIC_EFFECT (simultaneous upper < MEE) /
FAIL_COST_ROBUSTNESS (2x point <= 0) -> 3 DEVELOPMENT_SUPPORT (every gate) ->
4 UNCERTAIN. A gate that was not measured can never pass. The function reads
only the summaries it is handed; it cannot select a horizon, split or threshold.
"""
from __future__ import annotations

from . import contract as C

VERDICTS = ('NOT_RUN_POWER_NO_GO', 'SOURCE_BLOCKED', 'REJECT_ECONOMIC_EFFECT', 'FAIL_COST_ROBUSTNESS',
            'DEVELOPMENT_SUPPORT', 'UNCERTAIN')


def decide(hypothesis: str, *, blocked: list[str], primary: dict | None, cost2x_delta: float | None,
           holm_reject: bool | None, dependence_uncertain: bool | None, regime: dict | None,
           industry: dict | None, matched: dict | None) -> dict:
    """``regime``/``industry``/``matched`` map check name -> point estimate (None = unmeasured)."""
    mee = C.MEE[C.PRIMARY_HORIZON]
    if blocked or primary is None:
        return {'verdict': 'SOURCE_BLOCKED', 'reasons': sorted(blocked) or ['PRIMARY_NOT_COMPUTED']}
    upper = primary['ciSimultaneous'][1]
    if upper < mee:
        return {'verdict': 'REJECT_ECONOMIC_EFFECT', 'reasons': [f'SIMULTANEOUS_UPPER<{mee}']}
    if cost2x_delta is None or cost2x_delta <= 0:
        return {'verdict': 'FAIL_COST_ROBUSTNESS', 'reasons': ['COST_2X_POINT<=0']}
    gates = {
        'holm': bool(holm_reject),
        'simultaneousLowerAboveZero': primary['ciSimultaneous'][0] > 0,
        'pointAtLeastMee': primary['delta'] >= mee,
        'cost2xPositive': cost2x_delta > 0,
        'dependenceConsistent': dependence_uncertain is False,
    }
    for name, checks in (('regime', regime), ('industry', industry), ('matched', matched)):
        values = list((checks or {}).values())
        gates[f'{name}Measured'] = bool(values) and all(v is not None for v in values)
        gates[f'{name}SignKept'] = gates[f'{name}Measured'] and all(v > 0 for v in values)
    if hypothesis == 'B1':
        gates['industryMatchedMeasured'] = (matched or {}).get('industryMatched') is not None
    failed = sorted(k for k, ok in gates.items() if not ok)
    if not failed:
        return {'verdict': 'DEVELOPMENT_SUPPORT', 'gates': gates, 'reasons': []}
    return {'verdict': 'UNCERTAIN', 'gates': gates, 'reasons': failed}
