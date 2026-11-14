"""Train-only input repair for three fixed structures; no grid search or ranking.

Real refits require complete source admission and an exact content authorization.
The existing v1 fit/transform functions are reused without changing v1 bytes.
"""
from __future__ import annotations
import json
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from research.ml_strategy_tournament_v1 import tournament as T
from .identity import HERE, cache_read, cache_write, digest, identity, code_identity, environment, write_once
from .vendor.input_pins_328 import verify_public_owner_approval

CONFIG = json.loads((HERE / 'config.json').read_text())
MODELS = {row['id']: next(c for c in T.grid() if c['id'] == row['id']) for row in CONFIG['candidates']}


def frame_sha(frame):
    if frame.duplicated(['date', 'ticker']).any() or not frame.date.is_monotonic_increasing:
        raise ValueError('DUPLICATE_OR_UNSORTED_MODEL_INPUTS')
    cols = [c for c in frame if not c.startswith('_')]
    return hashlib.sha256(frame[cols].to_csv(index=False).encode()).hexdigest()


def training_layers(train):
    cols = [c for c in train if (len(c) > 2 and c[0] in 'ABCDEFHIJ' and c[1:3].isdigit()) or c.startswith('MKT_')]
    coverage = train[cols].notna().mean()
    selected = [c for c in cols if coverage[c] >= CONFIG['refit']['featureCoverageThreshold']]
    market = [c for c in selected if c in T.MARKET_FROM_MATRIX or c.startswith('MKT_')]
    industry = [c for c in selected if c in T.INDUSTRY]
    company = [c for c in selected if c not in market and c not in industry]
    return {'company': company, 'industry': industry, 'market': market}, coverage.to_dict()


def fold_inputs(frame, year, horizon=126):
    train, test = T.fold_split(frame, year, horizon)
    if train.empty:
        raise ValueError('NO_MATURED_TRAINING_ROWS')
    layers, coverage = training_layers(train)
    # Rank each date separately; appending future dates cannot affect old ranks.
    cross = layers['company'] + layers['industry']
    trrank = T.rank_transform(train, cross)
    terank = T.rank_transform(test, cross)
    # Store every actual train-fitted statistic, plus the fixed missing rules.
    market = layers['market']
    med = train[market].median().to_dict()
    mean = train[market].mean().to_dict()
    std = train[market].std().replace(0, 1.).to_dict()
    clean = lambda d: {k: (float(v) if np.isfinite(v) else None) for k, v in d.items()}
    receipt = {'year': year, 'horizon': horizon, 'trainRows': len(train), 'trainDates': int(train.date.nunique()),
               'trainLastExit': str(train[f'exit{horizon}'].max().date()),
               'testFirst': str(test.date.min().date()), 'layers': layers,
               'coverage': clean(coverage), 'marketMedian': clean(med), 'marketMean': clean(mean), 'marketStd': clean(std),
               'missingRules': {'linearCross': 'RANK_MINUS_HALF_NAN_TO_ZERO_WITH_LAYER_MISSING_SHARE',
                                'linearMarket': 'TRAIN_Z_NAN_TO_ZERO_CLIP_5',
                                'LGBM_XGB': 'NATIVE_NAN', 'RF_ET': 'CROSS_RANK_HALF_TRAIN_MARKET_MEDIAN'},
               'featureSelectionBasis': 'MATURED_TRAIN_ROWS_ONLY'}
    return train, test, layers, trrank, terank, receipt


def authorization_gate(packet, approval, sources):
    # A chat request to build this repair is not borrowed Atlas execution approval.
    if sources.get('status') != 'COMPLETE_VERIFIED_SHAREHOLDER_INPUTS':
        raise ValueError('SOURCE_BLOCKED_REAL_REFIT_NOT_RUN')
    if packet.get('code') != code_identity() or packet.get('configSha256') != digest(CONFIG) or packet.get('environment') != environment() or packet.get('sourceAdmissionSha256') != digest(sources):
        raise ValueError('EXACT_PACKET_INPUT_IDENTITY_MISMATCH')
    if not approval or approval.get('packetSha256') != digest(packet) or approval.get('authorized') is not True:
        raise ValueError('EXACT_PACKET_AUTHORIZATION_REQUIRED')
    if packet['candidates'] != CONFIG['candidates'] or packet['allowNewWinner']:
        raise ValueError('CANDIDATE_SCOPE_CHANGED')
    verify_public_owner_approval(approval, 'AUTHORIZE_ML_TOURNAMENT_V2_REFIT ' + digest(packet))


def fit_fixed_fold(frame, year, sid, sources, cache, *, packet, approval):
    if sid not in MODELS or sid.startswith('RULE_'):
        raise ValueError('FIXED_ML_CANDIDATE_REQUIRED')
    train, test, layers, trrank, terank, receipt = fold_inputs(frame, year)
    authorization_gate(packet, approval, sources)
    if sources.get('correctedMatrixSha256') != frame_sha(frame):
        raise ValueError('CORRECTED_MATRIX_CONTENT_IDENTITY_MISMATCH')
    cfg = MODELS[sid]
    key = identity(CONFIG, sources, cfg, receipt)
    path = Path(cache) / (sid + '-' + str(year) + '.json')
    if path.exists():
        return cache_read(path, key)
    scores, _, _, cols = T.fit_predict(cfg, train, test, trrank, terank, layers)
    payload = {'fold': receipt, 'featuresUsed': cols,
               'predictions': [{'date': str(d.date()), 'ticker': t, 'score': float(s)}
                               for d, t, s in zip(test.date, test.ticker, scores)]}
    cache_write(path, key, payload)
    return payload


def rule_scores(frame, year, sid):
    if sid not in ('RULE_INDUSTRY_MOMENTUM', 'RULE_ETF_ONLY'):
        raise ValueError('FIXED_RULE_REQUIRED')
    _, test, layers, _, ranked, receipt = fold_inputs(frame, year)
    # Missing train-admitted required inputs means abstention, not reintroducing future columns.
    if sid == 'RULE_ETF_ONLY':
        return pd.Series(np.nan, index=test.index), receipt
    need = {'H01_industryRelMom126', 'A09_industryRelativeMomentum126'}
    if not need <= set(layers['company'] + layers['industry']):
        return pd.Series(np.nan, index=test.index), {**receipt, 'ruleStatus': 'TRAIN_FEATURES_NOT_READY'}
    return T.rule_score('INDUSTRY_MOMENTUM', ranked), receipt


def execute_refit(corrected_frame, market, source_admission, packet, approval, output):
    """Only fixed candidates. No winner/rank/top-N optimization result exists."""
    authorization_gate(packet, approval, source_admission)
    from . import accounting as A
    from .sources import selections
    saved = selections()
    if set(corrected_frame.ticker) != set(source_admission['matrixTickers']):
        raise ValueError('CORRECTED_MATRIX_POPULATION_IDENTITY_MISMATCH')
    if frame_sha(corrected_frame) != source_admission.get('correctedMatrixSha256'):
        raise ValueError('CORRECTED_MATRIX_CONTENT_IDENTITY_MISMATCH')
    frame = corrected_frame.copy()
    frame['_q'] = T.quality_mask(frame)
    executions = [r['date'] for r in saved['RULE_ETF_ONLY']]
    results = {}
    for candidate in CONFIG['candidates']:
        sid = candidate['id']
        if sid == 'RULE_ETF_ONLY':
            decisions = saved[sid]
            forecasts = []
        else:
            scores = pd.Series(np.nan, index=frame.index)
            forecasts = []
            for year in T.CONFIG['walkForward']['outerFoldYears']:
                test = frame[frame.date.dt.year == year]
                if test.empty:
                    continue
                if sid.startswith('RULE_'):
                    pred, receipt = rule_scores(frame, year, sid)
                    scores.loc[pred.index] = pred
                    forecasts.append({'fold': receipt, 'predictions': [
                        {'date': str(d.date()), 'ticker': t, 'score': float(s) if pd.notna(s) else None}
                        for d, t, s in zip(test.date, test.ticker, pred)]})
                else:
                    payload = fit_fixed_fold(frame, year, sid, source_admission,
                                             Path(output) / 'cache', packet=packet, approval=approval)
                    lookup = {(r['date'], r['ticker']): r['score'] for r in payload['predictions']}
                    scores.loc[test.index] = [lookup[str(d.date()), t] for d, t in zip(test.date, test.ticker)]
                    forecasts.append(payload)
            frame['_s'] = scores
            calib, exits = T.calibration_table(frame, '_s', 126)
            decisions = []
            for execution in executions:
                before = frame.loc[frame.date < pd.Timestamp(execution), 'date']
                signal = before.max()
                subset = frame[frame.date == signal]
                weights, diagnostic = T.decide(subset, '_s', calib, exits, signal, 126,
                                               gate=candidate['view'] == 'gated')
                weights[A.ETF] = 1 - sum(weights.values())
                decisions.append({'date': execution, 'signalDate': str(signal.date()), 'weights': weights,
                                  'decisionDiagnostic': diagnostic})
        book = A.run(market, decisions, capital=CONFIG['initialCapitalKrw'], require_complete=True)
        # All weekly scores/fold inputs, all decisions and complete account events retained.
        write_once(Path(output) / (sid + '-forecasts.json'), forecasts)
        write_once(Path(output) / (sid + '-decisions.json'), decisions)
        write_once(Path(output) / (sid + '-account.json'), book)
        results[sid] = {'status': book['status'], 'newWinnerSelected': False}
    write_once(Path(output) / 'fixed-candidate-results.json', results)
    return results
