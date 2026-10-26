"""Unapproved C1c v2 pure design and synthetic receipts. No live/historical writer."""
from __future__ import annotations

import hashlib
import itertools
import math
from numbers import Real
from pathlib import Path

import pandas as pd

from . import kr_market_risk_model as K
from . import market_research_c1c as C
from . import market_research_reentry_structure as R
from . import prospective_receipt_core as P
from . import replay_calendar as RC

STUDY = 'rp1-c1c-prospective-design-v2'
CONTROLS = ('C0', 'C1')
FAMILIES = (R.STRUCTURAL_HYPOTHESIS, R.BREAKOUT_HYPOTHESIS)
ARMS = ('BASE', 'HARD_EXIT', 'REENTRY', 'COMBINED')
HORIZONS = (126, 252)
ORIGINAL_GRID = (.4, .7, 1.)
HARD_EXIT_GRID = (0., .4, .7, 1.)  # NEW interaction, never the original registered grid
FIRST_SIGNAL_FLOOR = '2026-10-30'
MIN_MATURED_WEEKLY = 52
MIN_NONOVERLAPPING = 8


def contract():
    return {'studyId': STUDY, 'status': 'PROPOSED_NOT_REGISTERED_NOT_AUTHORIZED',
        'primaryControl': 'C0', 'auxiliaryControl': 'C1', 'selectControlFromResults': False,
        'families': list(FAMILIES), 'arms': list(ARMS), 'horizons': list(HORIZONS),
        'originalGrid': list(ORIGINAL_GRID), 'newHardExitInteractionGrid': list(HARD_EXIT_GRID),
        'structuralContrast': 'MEMORYLESS_VS_ONE_RUNG_WEEKLY_NOT_A_BREAKOUT',
        'breakoutContrast': 'POST_OUTCOME_SEPARATE_20_SESSION_PRICE_HYPOTHESIS',
        'primaryReading': 'C1_PRIMARY_REPLICA_DIAGNOSTIC_ONLY',
        'investabilityRequires': 'ETF_CASH_ECONOMIC_WITH_INDEPENDENT_SOURCE_ADMISSION',
        'marketDisagreement': 'NO_PROMOTION', 'basisDisagreement': 'BASIS_DEPENDENT_NO_PROMOTION',
        'pastEvidence': {'KR': 'OUTCOME_EXPOSED_DEVELOPMENT_ONLY', 'US': 'OUTCOME_EXPOSED_EXPLORATORY'},
        'firstSignalNotBefore': FIRST_SIGNAL_FLOOR, 'minimumMaturedWeeklyDecisions': MIN_MATURED_WEEKLY,
        'proposedMinimumNonoverlappingBlocks': MIN_NONOVERLAPPING,
        'supportStatus': 'NEW_PROPOSED_FLOOR_NOT_POWER_GUARANTEE_OWNER_REVIEW_REQUIRED',
        'inference': 'NO_PVALUE_OR_SUPPORTED_VERDICT_WITHOUT_REGISTERED_CALIBRATION',
        'historicalExecutionEnabled': False, 'liveWriterEnabled': False, 'productionAllowed': False}


def contract_digest():
    return C.digest(contract())


def implementation_digest():
    paths = [Path(m.__file__) for m in (C, R, K, P, RC, C.U)] + [Path(__file__)]
    return C.digest({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})


def _market(market):
    if market not in ('KR', 'US'):
        raise ValueError('UNKNOWN_MARKET')


def _day(value):
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError('ISO_SESSION_DATE_REQUIRED')
    try:
        day = pd.Timestamp(value)
    except ValueError as exc:
        raise ValueError('ISO_SESSION_DATE_REQUIRED') from exc
    if day.tzinfo is not None or str(day.date()) != value:
        raise ValueError('ISO_SESSION_DATE_REQUIRED')
    return day


def _state(value, allowed):
    if value is None:
        return tuple(allowed)
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value) or value not in allowed:
        raise ValueError('STATE_OUTSIDE_FROZEN_DOMAIN')
    return (int(value),)


def arm_target(control, family, arm, slow, transition, fast, *, breakout, previous=None):
    """Domain completion; immediate risk reduction, explicit weekly re-entry memory."""
    if control not in CONTROLS or family not in FAMILIES or arm not in ARMS:
        raise ValueError('UNREGISTERED_CONTROL_FAMILY_OR_ARM')
    if breakout is not None and type(breakout) is not bool:
        raise ValueError('BREAKOUT_BOOLEAN_OR_MISSING_REQUIRED')
    hard, reentry = arm in ('HARD_EXIT', 'COMBINED'), arm in ('REENTRY', 'COMBINED')
    grid = HARD_EXIT_GRID if hard else ORIGINAL_GRID
    if previous is not None and (isinstance(previous, bool) or not isinstance(previous, Real) or previous not in grid):
        raise ValueError('INVALID_PREVIOUS_TARGET')
    answers = set()
    options = (_state(slow, (0, 1)), _state(transition, (0, 1)), _state(fast, (0, 1, 2)))
    for s, t, f in itertools.product(*options):
        desired = 0. if hard and f == 2 else K.rule(control, s, t, f)
        for b in ((False, True) if breakout is None else (breakout,)):
            value = 1. if reentry and family == R.BREAKOUT_HYPOTHESIS and f == 1 and b else desired
            if reentry and family == R.STRUCTURAL_HYPOTHESIS and previous is not None and value > previous:
                value = grid[min(grid.index(previous) + 1, grid.index(value))]
            answers.add(value)
    if len(answers) != 1:
        if previous is None:
            raise ValueError('FIRST_TARGET_UNDETERMINED')
        return float(previous), True
    return float(answers.pop()), False


def cell_ids():
    return tuple(f'{base}/{family}/{arm}' for base, family, arm in itertools.product(CONTROLS, FAMILIES, ARMS))


def panel_targets(close, states, plan, market):
    """Every control/family/arm, on one calendar. No result-selected subset."""
    _market(market)
    C.validate_series(close, market, complete=True)
    C.validate_plan(plan, market)
    if not states.index.is_unique or not states.index.is_monotonic_increasing:
        raise ValueError('INVALID_STATE_PANEL_INDEX')
    previous, out = dict.fromkeys(cell_ids()), []
    for row in plan.itertuples(index=False):
        day = pd.Timestamp(row.decisionDate)
        if day not in close.index:
            raise ValueError('SIGNAL_CLOSE_MISSING')
        label = str(day.date())
        values = states.loc[day] if day in states.index else pd.Series(dtype=object)
        layers = []
        for layer, allowed in (('slow', (0, 1)), ('transition', (0, 1)), ('fast', (0, 1, 2))):
            value = values.get(layer)
            if value is not None and pd.isna(value):
                value = None
            _state(value, allowed)
            if value is not None:
                stamp = values.get(layer + 'KnownAt')
                if stamp is None or pd.isna(stamp) or P.utc(stamp) > C.final_at(label, market):
                    raise ValueError('STATE_NOT_KNOWN_AT_DECISION:' + layer)
                if layer == 'fast' and P.utc(stamp) < C.session_close(label, market):
                    raise ValueError('INTRADAY_FAST_CANNOT_CERTIFY_FINAL_CLOSE')
            layers.append(value)
        breakout = C.prior_high_breakout(close.loc[:day], label, market)
        cells = {}
        for base, family, arm in itertools.product(CONTROLS, FAMILIES, ARMS):
            key = f'{base}/{family}/{arm}'
            value, held = arm_target(base, family, arm, *layers, breakout=breakout, previous=previous[key])
            cells[key] = {'target': value, 'heldForMissing': held}
            previous[key] = value
        out.append({'decisionDate': label, 'executionDate': str(pd.Timestamp(row.executionDate).date()),
            'layers': dict(zip(('slow', 'transition', 'fast'), layers)), 'breakout': breakout, 'cells': cells})
    if not out:
        raise ValueError('NO_SCHEDULED_DECISIONS')
    return out


def family_contrasts(values):
    if not isinstance(values, dict) or set(values) != set(cell_ids()):
        raise ValueError('COMPLETE_SIXTEEN_CELL_POPULATION_REQUIRED')
    if any(isinstance(v, bool) or not isinstance(v, Real) or not math.isfinite(v) for v in values.values()):
        raise ValueError('FINITE_COMMON_METRIC_REQUIRED')
    out = {}
    for base, family in itertools.product(CONTROLS, FAMILIES):
        metrics = {f'S{i}': values[f'{base}/{family}/{arm}'] for i, arm in enumerate(ARMS)}
        out[f'{base}/{family}'] = {**C.factorial(metrics), 'controlRole': 'PRIMARY' if base == 'C0' else 'AUXILIARY_DESCRIPTIVE',
            'metric': 'PAIRED_ANNUAL_LOG_GROWTH', 'nominationAllowed': False}
    return out


def synthetic_basis_check(market, basis, identity):
    """Invented metadata check, NEVER genuine source admission."""
    _market(market)
    if basis not in ('C1_PRIMARY_REPLICA', 'ETF_CASH_ECONOMIC') or not isinstance(identity, dict):
        raise ValueError('UNKNOWN_ASSET_BASIS')
    economic = basis == 'ETF_CASH_ECONOMIC'
    instrument = {('KR', False): 'KS200_PRICE_INDEX', ('US', False): 'SP500_PRICE_INDEX',
        ('KR', True): '069500.KS', ('US', True): 'SPY'}[market, economic]
    required = {'evidenceClass': C.SYNTHETIC, 'instrument': instrument,
        'returnBasis': 'TOTAL_RETURN' if economic else 'PRICE_INDEX', 'currency': 'KRW' if market == 'KR' else 'USD',
        'cashBasis': 'DTB3_PRIOR_KNOWN_ACT360' if economic and market == 'US' else 'ZERO',
        'sourceStatus': 'SYNTHETIC_HASH_VERIFIED', 'rightsStatus': 'SYNTHETIC_ALLOWED', 'reconciliationStatus': 'SYNTHETIC_PASS'}
    if any(identity.get(k) != v for k, v in required.items()) or not P.is_sha256(identity.get('sourceSha256')):
        raise ValueError('ASSET_CASH_IDENTITY_RIGHTS_OR_RECONCILIATION_BLOCKED')
    return {'status': 'SYNTHETIC_BASIS_CHECK_ONLY', 'sourceAdmitted': False, 'basis': basis, 'market': market,
        'instrument': instrument, 'buySellCostRates': C.cost_rates(market, basis)}


def cross_market_verdict(readings):
    if set(readings) != {'KR', 'US'} or any(set(v) != {'DIAGNOSTIC', 'ECONOMIC'} for v in readings.values()):
        raise ValueError('COMPLETE_KR_US_TWO_BASIS_READINGS_REQUIRED')
    values = [v for market in readings.values() for v in market.values()]
    if any(v not in ('IMPROVED', 'NOT_IMPROVED', 'BLOCKED') for v in values):
        raise ValueError('UNKNOWN_DESCRIPTIVE_VERDICT')
    if 'BLOCKED' in values:
        state = 'BLOCKED_SOURCE_OR_SUPPORT'
    elif any(v['DIAGNOSTIC'] != v['ECONOMIC'] for v in readings.values()):
        state = 'BASIS_DEPENDENT_NO_PROMOTION'
    elif readings['KR']['DIAGNOSTIC'] != readings['US']['DIAGNOSTIC']:
        state = 'MARKET_DISAGREEMENT_NO_PROMOTION'
    else:
        state = 'DESCRIPTIVE_AGREEMENT_ONLY'
    return {'status': state, 'promotionAllowed': False, 'scientificApproval': False}


def _prospective_start(market, authorizing_merge_at):
    _market(market)
    merge = P.utc(authorizing_merge_at)
    local = merge.tz_convert('Asia/Seoul' if market == 'KR' else 'America/New_York').date()
    start = max(_day(FIRST_SIGNAL_FLOOR), pd.Timestamp(local) + pd.Timedelta(days=1))
    days = RC.sessions(str(start.date()), str((start + pd.Timedelta(days=20)).date()), market)
    plan = C.U.decision_schedule(days, str(start.date()), str(days[-1].date()), market)
    if plan.empty:
        raise ValueError('CALENDAR_SUPPORT_NOT_AVAILABLE')
    return plan.decisionDate.iloc[0]


def prospective_schedule(market, authorizing_merge_at):
    """Calendar-only DRAFT. Proposed support floors neither authorize nor prove power."""
    start = _prospective_start(market, authorizing_merge_at)
    end = '2035-10-01'  # Preserve pinned 2035 calendar and weekly selector's +45 days.
    days = RC.sessions(str(start.date()), end, market)
    weekly = C.U.decision_schedule(days, str(start.date()), end, market)
    positions = {d: i for i, d in enumerate(days)}
    rows = []
    for horizon in HORIZONS:
        eligible = weekly[weekly.executionDate.map(positions) + horizon < len(days)]
        first52 = eligible.iloc[:MIN_MATURED_WEEKLY]
        if len(first52) != MIN_MATURED_WEEKLY:
            raise ValueError('CALENDAR_SUPPORT_NOT_AVAILABLE')
        diagnostic = days[positions[first52.executionDate.iloc[-1]] + horizon]
        blocks, next_pos = [], 0
        for r in eligible.itertuples(index=False):
            pos = positions[r.executionDate]
            if pos >= next_pos:
                maturity = pos + horizon
                blocks.append({'signalDate': str(r.decisionDate.date()), 'executionDate': str(r.executionDate.date()),
                    'maturityDate': str(days[maturity].date())})
                next_pos = maturity
                if len(blocks) == MIN_NONOVERLAPPING:
                    break
        if len(blocks) != MIN_NONOVERLAPPING:
            raise ValueError('CALENDAR_SUPPORT_NOT_AVAILABLE')
        support_date = max(pd.Timestamp(blocks[-1]['maturityDate']), diagnostic)
        rows.append({'horizon': horizon, 'firstDescriptiveReadoutAt': C.final_at(str(diagnostic.date()), market).isoformat(),
            'supportFloorNotBefore': C.final_at(str(support_date.date()), market).isoformat(), 'blocks': blocks})
    return {'contractSha256': contract_digest(), 'market': market, 'firstSignalDate': str(weekly.decisionDate.iloc[0].date()),
        'minimumMaturedWeeklyDecisions': MIN_MATURED_WEEKLY, 'minimumNonoverlappingBlocks': MIN_NONOVERLAPPING,
        'registrationStatus': 'DRAFT_NOT_AUTHORIZATION', 'inferenceAllowed': False, 'horizons': rows}


def synthetic_receipt(*, market, signal_date, created_at, authorizing_merge_at, layers, breakout, source_sha256, previous=None):
    """Fixture-only all-cell receipt. The supplied merge is not an authorization."""
    _market(market)
    day = _day(signal_date)
    if signal_date < str(_prospective_start(market, authorizing_merge_at).date()):
        raise ValueError('SIGNAL_BEFORE_PROSPECTIVE_BOUNDARY')
    days = RC.sessions(signal_date, str((day + pd.Timedelta(days=15)).date()), market)
    if len(days) < 2 or days[0] != day or tuple(day.isocalendar())[:2] == tuple(days[1].isocalendar())[:2]:
        raise ValueError('NOT_WEEKLY_DECISION')
    created = P.utc(created_at)
    import exchange_calendars as xc
    next_open = xc.get_calendar({'KR': 'XKRX', 'US': 'XNYS'}[market], start='1990-01-01', end='2035-12-31').session_open(days[1])
    if not C.final_at(signal_date, market) <= created < next_open:
        raise ValueError('RECEIPT_OUTSIDE_FINALITY_NEXT_OPEN_WINDOW')
    if not isinstance(layers, dict) or set(layers) != {'slow', 'transition', 'fast'} or not P.is_sha256(source_sha256):
        raise ValueError('INVALID_RECEIPT_INPUT_IDENTITY')
    if previous is not None:
        if previous.get('receiptSha256') != P.receipt_digest(previous) or previous.get('contractSha256') != contract_digest():
            raise ValueError('INVALID_PREVIOUS_RECEIPT')
        if previous.get('codeSha256') != implementation_digest():
            raise ValueError('RECEIPT_CHAIN_IMPLEMENTATION_CHANGED')
        if previous['market'] != market or previous['signalDate'] >= signal_date:
            raise ValueError('RECEIPT_CHAIN_MARKET_OR_ORDER')
        if previous['syntheticAuthorizingMergeAt'] != P.utc(authorizing_merge_at).isoformat():
            raise ValueError('RECEIPT_CHAIN_AUTHORIZATION_CHANGED')
    cells = {}
    for base, family, arm in itertools.product(CONTROLS, FAMILIES, ARMS):
        key = f'{base}/{family}/{arm}'
        prior = previous['cells'][key]['target'] if previous else None
        target, held = arm_target(base, family, arm, *(layers[k] for k in ('slow', 'transition', 'fast')), breakout=breakout, previous=prior)
        cells[key] = {'target': target, 'heldForMissing': held}
    receipt = {'schemaVersion': 1, 'studyId': STUDY, 'evidenceClass': C.SYNTHETIC, 'contractSha256': contract_digest(),
        'codeSha256': implementation_digest(), 'market': market, 'signalDate': signal_date, 'executionDate': str(days[1].date()),
        'createdAt': created.isoformat(), 'syntheticAuthorizingMergeAt': P.utc(authorizing_merge_at).isoformat(),
        'layers': layers, 'breakout': breakout, 'cells': cells, 'sourceSha256': source_sha256,
        'previousReceiptSha256': previous['receiptSha256'] if previous else None, 'productionAllowed': False}
    P.scan_for_outcome_keys(receipt)
    return {**receipt, 'receiptSha256': P.receipt_digest(receipt)}


def validate_synthetic_receipts(receipts):
    previous = None
    for receipt in receipts:
        if not isinstance(receipt, dict):
            raise ValueError('INVALID_RECEIPT')
        try:
            expected = synthetic_receipt(market=receipt['market'], signal_date=receipt['signalDate'], created_at=receipt['createdAt'],
                authorizing_merge_at=receipt['syntheticAuthorizingMergeAt'], layers=receipt['layers'], breakout=receipt['breakout'],
                source_sha256=receipt['sourceSha256'], previous=previous)
        except (KeyError, TypeError) as exc:
            raise ValueError('INVALID_RECEIPT_SCHEMA') from exc
        if receipt.get('receiptSha256') != P.receipt_digest(receipt) or P.canonical(receipt) != P.canonical(expected):
            raise ValueError('RECEIPT_SEMANTIC_OR_DIGEST_MISMATCH')
        previous = receipt
    return {'status': 'VALID_SYNTHETIC_CHAIN_ONLY', 'receipts': len(receipts), 'liveWritingAllowed': False}


def append_synthetic(receipts, receipt):
    rows = tuple(receipts)
    validate_synthetic_receipts(rows)
    if not isinstance(receipt, dict):
        raise ValueError('INVALID_RECEIPT')
    for existing in rows:
        if (existing['market'], existing['signalDate']) == (receipt.get('market'), receipt.get('signalDate')):
            if P.canonical(existing) == P.canonical(receipt):
                return rows
            raise ValueError('IMMUTABLE_RECEIPT_KEY_CONFLICT')
    validate_synthetic_receipts((*rows, receipt))
    return (*rows, receipt)
