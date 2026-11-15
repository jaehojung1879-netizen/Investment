"""Non-operational candidate-signal interface for corporate events.

Maps one event record to NOT_ADMITTED / EXPLORATORY / PROSPECTIVE_CANDIDATE /
VERIFIED. It never emits a weight, position, target or ticker list for the
operating book: Portfolio D stays KR 0 names / 069500.KS 100% until a
hypothesis is VERIFIED, and VERIFIED needs evidence this repository does not
hold today (registered spec, independent audit, Owner-approved execution,
matured independent prospective sample). Nothing here imports production code.
"""
from __future__ import annotations

from dataclasses import dataclass, field

STATES = ('NOT_ADMITTED', 'EXPLORATORY', 'PROSPECTIVE_CANDIDATE', 'VERIFIED')
HYPOTHESIS_DIRECTION = {'A1': 'POSITIVE_VS_FUNDED_BETA_MATCHED_ETF',
                        'A2': 'COMPARATOR_NO_DIRECTIONAL_CLAIM',
                        'B1': 'POSITIVE_VS_FUNDED_BETA_MATCHED_ETF'}
REQUIRED = ('rcept_no', 'corp_code', 'stock_code', 'family', 'eventType', 'hypothesis', 'receiptDay',
            'entrySession', 'pitGrade')


@dataclass(frozen=True)
class HypothesisEvidence:
    """What is known about a hypothesis as a whole. Defaults are today's facts."""
    registered_spec_sha256: str | None = None
    independent_audit: bool = False
    historical_verdict: str | None = None      # e.g. DEVELOPMENT_SUPPORT, UNCERTAIN, REJECT_ECONOMIC_EFFECT
    prospective_verdict: str | None = None     # only from matured genuine receipts
    price_side_admitted: bool = False          # total return, corporate actions, terminal economics
    notes: tuple = field(default_factory=tuple)


def classify_signal(event: dict, evidence: HypothesisEvidence | None = None) -> dict:
    evidence = evidence or HypothesisEvidence()
    missing = [k for k in REQUIRED if not event.get(k)]
    out = {'state': 'NOT_ADMITTED', 'reasons': [], 'direction': HYPOTHESIS_DIRECTION.get(event.get('hypothesis')),
           'holdingHorizons': ('H126', 'H252'), 'operationalUse': 'NONE',
           'portfolioDDefault': 'KR 0 names / 069500.KS 100%'}
    if missing:
        out['reasons'].append('MISSING:' + ','.join(missing))
        return out
    if event['pitGrade'] not in ('PIT_EXACT', 'DATE_ONLY_CONSERVATIVE'):
        out['reasons'].append('PIT_GRADE_NOT_ADMITTED')
        return out
    if event['hypothesis'] == 'A2':
        out['reasons'].append('COMPARATOR_CLASS_NOT_A_SIGNAL')
        return out
    out['state'] = 'EXPLORATORY'
    out['reasons'].append('SOURCE_GATES_PASSED_OUTCOME_UNTESTED')
    if not (evidence.registered_spec_sha256 and evidence.independent_audit):
        out['reasons'].append('SPEC_NOT_REGISTERED_OR_NOT_AUDITED')
        return out
    if evidence.historical_verdict != 'DEVELOPMENT_SUPPORT':
        out['reasons'].append('NO_HISTORICAL_DEVELOPMENT_SUPPORT')
        return out
    out['state'] = 'PROSPECTIVE_CANDIDATE'
    if evidence.prospective_verdict == 'SUPPORT' and evidence.price_side_admitted:
        out['state'] = 'VERIFIED'
        out['operationalUse'] = 'ELIGIBLE_FOR_SEPARATE_0_TO_5_NAME_IMPLEMENTATION_TEST'
    else:
        out['reasons'].append('NO_MATURED_INDEPENDENT_PROSPECTIVE_SUPPORT')
    return out
