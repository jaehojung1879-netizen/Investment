"""Frozen execution parameters, copied from the registered spec and the Owner
C0/C1/C2/D contract (Issue #292 comment 6671600416), and verified against the
registered spec on every load.

Nothing here is tuned. Where the contract leaves an engineering detail open the
choice is listed in ``ENGINEERING_CHOICES`` so the Owner reviews it BEFORE any
outcome exists; none of them was chosen from a result (none exists).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import MappingProxyType

from pipeline.benchmark_alpha import REALISTIC_COSTS

REPO = Path(__file__).resolve().parents[2]
COHORT_DIR = REPO / 'research' / 'corporate_event_readiness_v1' / 'cohort'
REGISTERED_SPEC = COHORT_DIR / 'kr-corporate-information-events-v1-candidate.json'
STUDY_ID = 'kr-corporate-information-events-v1'

HORIZONS = MappingProxyType({'H126': 126, 'H252': 252})
PRIMARY_HORIZON = 'H126'
MEE = MappingProxyType({'H126': 0.03, 'H252': 0.04})       # arithmetic delta_H = H*alpha, total capital
PRIMARY_HYPOTHESES = ('A1', 'B1')
FAMILY_SLOTS = ('A1_CAPITAL_ALLOCATION_CANCELLATION', 'B1_LARGE_SUPPLY_CONTRACT',
                'H3_INSIDER_NOT_RUN_P_EQUALS_1')
FWER = 0.05
SIMULTANEOUS_LEVEL = 1 - FWER / len(FAMILY_SLOTS)            # 98.333...% two-sided
BOOTSTRAP = MappingProxyType({'draws': 9999, 'seed': 319320,
                              'block': MappingProxyType({'H126': 252, 'H252': 504}),
                              'sensitivityBlocks': MappingProxyType({'H126': (126, 504),
                                                                     'H252': (252, 756)})})
HAC_LAG = MappingProxyType({'H126': 125, 'H252': 251})
BETA = MappingProxyType({'windowReturns': 252, 'minPairs': 200})
COST_MULTIPLIERS = (1.0, 2.0, 3.0)
VALUE_UP = '2024-02-26'
RECENT_CONCENTRATION = ('2025-01-01', '2026-12-31')
BENCHMARK = '069500.KS'

_KR = REALISTIC_COSTS['KR']
COSTS = MappingProxyType({
    'source': 'pipeline/benchmark_alpha.py REALISTIC_COSTS[KR] (dated sell-tax schedule)',
    'stockCommissionBps': float(_KR['commissionBps']),
    'stockHalfSpreadBps': float(_KR['spreadBps']) / 2,
    'sellTaxSchedule': tuple((row['effectiveDate'], float(row['sellTaxBps']))
                             for row in _KR['sellTaxSchedule']),
    'etfCommissionBps': float(_KR['commissionBps']),
    'etfHalfSpreadBps': float(_KR['spreadBps']) / 2,
    'etfSellTaxBps': 0.0,      # pipeline/weekly_decision.py ETF_SELL_TAX_BPS['KR']
    'cashBps': 0.0,
    'status': 'MODEL_COST_NO_REAL_FILLS',
})

ENGINEERING_CHOICES = (
    'Calendar = union over A1/B1/A2 of first entry session .. last H-exit session per horizon (one joint '
    'calendar so the bootstrap is synchronized); a session outside a book\'s own span, or with an empty '
    'book, holds 069500.KS 100% in BOTH books (D_t = 0) and stays in the mean (total-capital basis).',
    'Rebalance only at the close of a session where the active slot set changes; otherwise drift.',
    'Equal target capital per active slot; slot = q stock + (1-q) cash vs q*beta ETF + (1-q*beta) cash, '
    'q = 1/max(1,beta) fixed at entry.',
    'A name not tradable (zero volume) on a rebalance close keeps its drifted weight; the rest of the '
    'book is rescaled around it. An event whose entry session is not tradable is a pre-trade eligibility '
    'failure (not held), counted.',
    'Costs: stock buy = commission + half spread, sell adds the dated transaction tax; ETF each way = '
    'commission + half spread, no tax; cash free. 2x/3x scale every friction and the tax.',
    'A held name with no level and no admitted terminal consideration makes the path incomplete '
    '(paired outcome None -> SOURCE_BLOCKED); it is never zero-filled or last-priced.',
    'Beta: OLS of stock on 069500.KS daily total returns over the 252 returns ending at the SIGNAL '
    'session, >= 200 joint pairs; beta < 0 or unestimable -> not investable, counted.',
    'Bootstrap: synchronized (non-circular) moving blocks over the joint calendar, basic CI on the '
    'centred mean, two-sided p = (1 + #|m*-m| >= |m|)/(B+1).',
    'Dependence check: UNCERTAIN_DEPENDENCE when the sign of the simultaneous lower bound differs '
    'between the primary bootstrap, Bartlett HAC normal interval and either sensitivity block.',
    'Regime checks (point estimates on event subsets): pre/post Value-up by entry date, and the book '
    'without entries in 2025-01-01..2026-12-31. Industry check: the book without the PIT research '
    'industry holding the most events (pinned outcome-free in the readiness file).',
    'Matched check: 3 nearest non-event peers on standardized log mcap, B/M, 12-1 momentum, 21-session '
    'return, beta, exact PIT industry first (B1 mandatory). Measured iff a two-way (issuer x entry-week) '
    'clustered SE exists.',
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_registered() -> dict:
    """Refuse when the inherited values above disagree with the registered spec."""
    spec = json.loads(REGISTERED_SPEC.read_text(encoding='utf-8'))
    problems = []
    if spec.get('studyId') != STUDY_ID:
        problems.append('STUDY_ID')
    if spec['fixedSplits']['valueUp'] != VALUE_UP:
        problems.append('VALUE_UP')
    if tuple(spec['fixedSplits']['recentConcentration']) != RECENT_CONCENTRATION:
        problems.append('RECENT_CONCENTRATION')
    if tuple(spec['hypothesisFamily']['slots']) != FAMILY_SLOTS:
        problems.append('FAMILY_SLOTS')
    inf = spec['inference']['primary']
    for token in ('252 sessions (H126)', '504 (H252)', 'B=9999', 'seed 319320'):
        if token not in inf:
            problems.append(f'INFERENCE:{token}')
    if 'lag 125/251' not in spec['inference']['secondary']:
        problems.append('HAC_LAG')
    if 'MEE 3pp (H126), 4pp (H252' not in spec['primaryEstimand']:
        problems.append('MEE')
    if '069500.KS' not in spec['primaryEstimand']:
        problems.append('BENCHMARK')
    if problems:
        raise ValueError('INHERITED_VALUE_CHANGED:' + ','.join(problems))
    return {'registeredSpecSha256': sha256_file(REGISTERED_SPEC), 'status': 'INHERITED_VALUES_MATCH'}


def sell_tax_bps(day: str) -> float:
    eff = [bps for start, bps in COSTS['sellTaxSchedule'] if start <= day]
    return eff[-1]
