"""Synthetic tests for the A1/B1 historical outcome harness. No real market data."""
from __future__ import annotations

import json

import numpy as np
import pytest

from research.corporate_event_readiness_v1.cohort.outcome import (
    contract as C, decision as DEC, engine as E, inference as INF, inputs as I, readiness as R,
    run as RUN, study as S, synthetic as SY)


def _slots(market, events, horizon='H126'):
    return E.build_slots(events, horizon, market['sessions'], market['levels'], market['etf'], market['tradable'])


def test_inherited_values_match_registered_spec():
    assert C.verify_registered()['status'] == 'INHERITED_VALUES_MATCH'


def test_registered_closure_untouched():
    spec = json.loads(C.REGISTERED_SPEC.read_text(encoding='utf-8'))
    root = C.COHORT_DIR.parents[2]
    for rel, sha in spec['codeSha256'].items():
        assert C.sha256_file(root / rel) == sha, rel
    for name, sha in spec['inputSha256'].items():
        assert C.sha256_file(C.COHORT_DIR / 'data' / name) == sha, name


def test_planted_edge_is_recovered_exactly_without_noise_or_cost():
    market, events = SY.world(alpha_daily=0.0005, vol=0.0)
    slots, excluded = _slots(market, events)
    assert slots and not excluded
    p = E.simulate(slots, **market, mult=0.0)
    idx = {d: i for i, d in enumerate(market['sessions'])}
    expected = []
    for d in p['dates'][1:]:
        act = [s for s in slots if s.entry < idx[d] <= s.exit]
        expected.append(np.mean([s.q * 0.0005 for s in act]) if act else 0.0)
    assert np.max(np.abs(np.array(p['D'][1:]) - expected)) < 2e-4
    assert 126 * np.mean(p['D']) == pytest.approx(126 * np.mean(expected), rel=0.05)


def test_no_edge_no_noise_gives_near_zero_selection_before_cost():
    # exact on each rebalance day; between rebalances the stock leg and the beta-matched ETF leg
    # drift apart (buy-and-hold is not a daily-rebalanced replication) -- second order, reported.
    market, events = SY.world(alpha_daily=0.0, vol=0.0)
    p = E.simulate(_slots(market, events)[0], **market, mult=0.0)
    assert abs(126 * np.mean(p['D'])) < 2e-3
    assert max(abs(x) for x in p['D']) < 5e-4


def test_costs_scale_and_tax_is_dated():
    market, events = SY.world(alpha_daily=0.0, vol=0.0)
    slots = _slots(market, events)[0]
    d1 = np.mean(E.simulate(slots, **market, mult=1.0)['D'])
    d2 = np.mean(E.simulate(slots, **market, mult=2.0)['D'])
    assert d2 < d1 < 0
    assert d2 == pytest.approx(2 * d1, rel=0.02)
    assert C.sell_tax_bps('2019-06-02') == 30.0 and C.sell_tax_bps('2025-06-01') == 15.0


def test_beta_reads_nothing_after_signal():
    market, events = SY.world()
    e = events[0]
    base = E.estimate_beta(market['levels'][e['ticker']], market['etf'], market['sessions'], e['signalSession'])
    poisoned = {d: (v * 50 if d > e['signalSession'] else v) for d, v in market['levels'][e['ticker']].items()}
    again = E.estimate_beta(poisoned, market['etf'], market['sessions'], e['signalSession'])
    assert base == again and base['pairs'] == 252


def test_q_caps_high_beta_and_negative_beta_is_excluded():
    market, events = SY.world(beta_range=(1.5, 1.5), vol=0.0)
    slots = _slots(market, events)[0]
    assert all(s.q == pytest.approx(1 / s.beta) for s in slots)
    market2, events2 = SY.world(beta_range=(-0.8, -0.8), vol=0.001)
    slots2, excluded = _slots(market2, events2)
    assert not slots2 and set(excluded.values()) == {'NEGATIVE_BETA_NOT_INVESTABLE'}


def test_missing_terminal_consideration_blocks_path_and_admitted_one_completes():
    market, events = SY.world(vol=0.0)
    slots = _slots(market, events)[0]
    s = slots[0]
    cut = market['sessions'][s.entry + 10]
    lv = market['levels'][s.ticker]
    for d in [d for d in lv if d >= cut]:
        del lv[d]
    p = E.simulate(slots, **market)
    assert not p['complete'] and p['failure']['code'] == 'MISSING_RETURN_NO_TERMINAL_CONSIDERATION'
    market['terminal'] = {s.ticker: {'date': cut, 'multiple': 1.0}}
    # after conversion the name is cash; later slots on the same ticker cannot be priced either
    later = [x for x in slots if x.ticker == s.ticker and x.entry > s.entry]
    p2 = E.simulate([x for x in slots if x not in later], **market)
    assert p2['complete']
    res = S.evaluate({'A1': events}, {**market, 'terminal': {}}, pinned_industry={}, draws=99)
    assert res['decisions']['A1']['verdict'] == 'SOURCE_BLOCKED'


def test_untradable_name_keeps_weight_on_rebalance():
    w = {'X': 0.4, E.CASH: 0.6}
    new, cost, _ = E._rebalance(w, {E.ETF: 1.0}, {'X'}, '2020-01-02', 1.0)
    assert new['X'] == pytest.approx(0.4) and new[E.ETF] == pytest.approx(0.6)


def test_bootstrap_is_deterministic_and_synchronized():
    x = np.random.default_rng(1).normal(size=500)
    a = INF.synchronized_bootstrap({'a': x, 'b': 2 * x}, 50, draws=200)
    b = INF.synchronized_bootstrap({'a': x, 'b': 2 * x}, 50, draws=200)
    assert np.array_equal(a['a'], b['a']) and np.allclose(a['b'], 2 * a['a'])
    with pytest.raises(ValueError):
        INF.synchronized_bootstrap({'a': x, 'b': x[:-1]}, 50, draws=10)


def test_holm_and_simultaneous_level():
    assert C.SIMULTANEOUS_LEVEL == pytest.approx(1 - 0.05 / 3)
    assert INF.holm({'A1': 0.01, 'B1': 0.03, 'H3': 1.0}) == {'A1': True, 'B1': False, 'H3': False}
    assert INF.holm({'A1': 0.001, 'B1': 0.02, 'H3': 1.0}) == {'A1': True, 'B1': True, 'H3': False}


def _summary(delta, lo, hi, hac_lo=None):
    return {'delta': delta, 'ciSimultaneous': [lo, hi],
            'hac': {'ciSimultaneous': [hac_lo if hac_lo is not None else lo, hi]},
            'blockSensitivity': {'126': [lo, hi], '504': [lo, hi]}}


def test_decision_order():
    ok = dict(regime={'a': .01}, industry={'b': .02}, matched={'plain': .01})
    assert DEC.decide('A1', blocked=['x'], primary=_summary(.05, .01, .09), cost2x_delta=.04,
                      holm_reject=True, dependence_uncertain=False, **ok)['verdict'] == 'SOURCE_BLOCKED'
    assert DEC.decide('A1', blocked=[], primary=_summary(.01, -.01, .029), cost2x_delta=.0,
                      holm_reject=False, dependence_uncertain=False, **ok)['verdict'] == 'REJECT_ECONOMIC_EFFECT'
    assert DEC.decide('A1', blocked=[], primary=_summary(.02, -.01, .05), cost2x_delta=-.001,
                      holm_reject=False, dependence_uncertain=False, **ok)['verdict'] == 'FAIL_COST_ROBUSTNESS'
    assert DEC.decide('A1', blocked=[], primary=_summary(.05, .01, .09), cost2x_delta=.04,
                      holm_reject=True, dependence_uncertain=False, **ok)['verdict'] == 'DEVELOPMENT_SUPPORT'
    # an unmeasured check can never pass
    v = DEC.decide('A1', blocked=[], primary=_summary(.05, .01, .09), cost2x_delta=.04, holm_reject=True,
                   dependence_uncertain=False, regime={'a': .01}, industry={'b': .02}, matched={'plain': None})
    assert v['verdict'] == 'UNCERTAIN' and 'matchedMeasured' in v['reasons']
    # B1 additionally needs the industry-matched check
    v = DEC.decide('B1', blocked=[], primary=_summary(.05, .01, .09), cost2x_delta=.04, holm_reject=True,
                   dependence_uncertain=False, **ok)
    assert v['verdict'] == 'UNCERTAIN' and 'industryMatchedMeasured' in v['reasons']
    # a negative regime split blocks support
    v = DEC.decide('A1', blocked=[], primary=_summary(.05, .01, .09), cost2x_delta=.04, holm_reject=True,
                   dependence_uncertain=False, regime={'pre': -.01, 'post': .08}, industry={'b': .02},
                   matched={'plain': .01})
    assert v['verdict'] == 'UNCERTAIN' and 'regimeSignKept' in v['reasons']


def test_dependence_check_flags_disagreement():
    s = _summary(.05, .01, .09)
    assert INF.dependence_uncertain(s) is False
    s['blockSensitivity']['504'] = [-.01, .1]
    assert INF.dependence_uncertain(s) is True


def test_null_world_does_not_produce_support():
    market, events = SY.world(alpha_daily=0.0, seed=3)
    res = S.evaluate({'A1': events, 'B1': []}, market, pinned_industry={'A1': 'IND_A'}, draws=199)
    assert res['decisions']['A1']['verdict'] != 'DEVELOPMENT_SUPPORT'
    assert res['promotionEligible'] is False and res['portfolioStep'] == 'NOT_REACHED'


def test_strong_edge_passes_every_gate_except_unmeasured_matching():
    market, events = SY.world(alpha_daily=0.003, seed=5, n_events=120, n_names=80, vol=0.01)
    res = S.evaluate({'A1': events, 'B1': []}, market, pinned_industry={'A1': 'IND_B'}, draws=499)
    d = res['decisions']['A1']
    assert d['verdict'] == 'UNCERTAIN'
    assert set(d['reasons']) <= {'matchedMeasured', 'matchedSignKept', 'regimeMeasured', 'regimeSignKept'}
    assert res['horizons']['H126']['books']['A1x1']['ciSimultaneous'][0] > 0


def test_matching_needs_three_peers_and_industry():
    ev = {'id': 'e', 'industry': 'X', **{f: 0.0 for f in E.MATCH_FIELDS}}
    cands = [{'id': f'p{i}', 'industry': 'X' if i < 2 else 'Y', **{f: float(i) for f in E.MATCH_FIELDS}}
             for i in range(5)]
    assert E.match_peers(ev, cands, exact_industry=False) == ['p0', 'p1', 'p2']
    assert E.match_peers(ev, cands, exact_industry=True) is None


def test_two_way_cluster_requires_clusters():
    assert E.two_way_cluster_mean([1.0, 2.0], ['a', 'a'], [1, 2])['se'] is None
    r = E.two_way_cluster_mean([1.0, 2.0, 0.5, 3.0], ['a', 'b', 'c', 'd'], [1, 2, 3, 4])
    assert r['se'] is not None and r['mean'] == pytest.approx(1.625)


def test_readiness_reads_no_market_and_is_byte_stable(monkeypatch):
    def boom(*a, **k):
        raise AssertionError('outcome path touched')
    for name in ('simulate', 'estimate_beta', 'build_slots', 'slot_holding_return'):
        monkeypatch.setattr(E, name, boom)
    monkeypatch.setattr(S, 'evaluate', boom)
    doc = R.build()
    assert doc['outcomesRead'] == 0 and doc['priceValuesRead'] == 0
    raw = json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + '\n'
    assert raw == RUN.READINESS.read_text(encoding='utf-8')
    assert doc['sets']['A1_H126']['independentEvents'] == 323
    assert doc['sets']['B1_H126']['independentEvents'] == 464


def test_packet_verifies_and_detects_code_change(monkeypatch):
    state = RUN.verify()
    assert state['problems'] == [] and state['status'] == 'PREPARED_BLOCKED_BY_SOURCE'
    assert state['packetSha256'] == RUN.PACKET.with_suffix('.sha256').read_text().split()[0]
    real = RUN.harness_hashes()
    monkeypatch.setattr(RUN, 'harness_hashes', lambda: {**real, 'x': '0'})
    assert 'HARNESS_CODE_CHANGED' in RUN.verify()['problems']


def test_execute_refuses_without_authorization_and_with_blocked_sources(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise AssertionError('market read')
    monkeypatch.setattr(RUN, '_load_admitted', boom)
    with pytest.raises(RUN.Refused):
        RUN.execute(None, None, tmp_path / 'r.json')
    state = RUN.verify()
    spec = json.loads(RUN.PACKET.read_text())['registeredSpec']['sha256']
    auth = tmp_path / 'auth.json'
    auth.write_text(json.dumps({'phrase': 'APPROVE something else', 'packetSha256': state['packetSha256'],
                                'registeredSpecSha256': spec}))
    with pytest.raises(RUN.Refused):
        RUN.execute(auth, None, tmp_path / 'r.json')
    auth.write_text(json.dumps({'phrase': RUN.PHRASE.format(spec=spec, packet=state['packetSha256']),
                                'packetSha256': state['packetSha256'], 'registeredSpecSha256': spec}))
    with pytest.raises(RUN.Refused) as exc:
        RUN.execute(auth, tmp_path / 'missing.json', tmp_path / 'r.json')
    assert exc.value.code == 2
    assert not (tmp_path / 'r.json').exists()


def test_admission_refuses_wrong_basis_and_digest(tmp_path):
    f = tmp_path / 'tr.json'
    f.write_text('{}')
    import hashlib
    good = hashlib.sha256(f.read_bytes()).hexdigest()
    m = tmp_path / 'm.json'
    m.write_text(json.dumps({'components': {
        'stockTotalReturn': {'basis': 'PRICE_ONLY', 'path': 'tr.json', 'sha256': good,
                             'rights': I.RIGHTS, 'independentAudit': 'x'},
        'investableKrwCash': {'basis': 'REALIZED_CASH_PAYOFF', 'path': 'tr.json', 'sha256': '0' * 64,
                              'rights': I.RIGHTS, 'independentAudit': 'x'},
        'tradability': {'basis': 'KRX_VOLUME_PRESENCE', 'path': 'tr.json', 'sha256': good,
                        'rights': I.RIGHTS, 'independentAudit': 'x'}}}))
    st = I.admit(m)['components']
    assert st['stockTotalReturn'] == 'SOURCE_BLOCKED:BASIS_NOT_ADMISSIBLE'
    assert st['investableKrwCash'] == 'SOURCE_BLOCKED:DIGEST_MISMATCH'
    assert st['tradability'] == 'ADMITTED'


def test_market_ex_date_rule_reproduces_reported_year_end_dates_and_flags_repo_candidate():
    from pipeline import replay_calendar
    from research.corporate_event_readiness_v1.cohort.dividends import ex_date_candidate
    from research.corporate_event_readiness_v1.cohort.outcome import ex_date as X
    sessions = [d.date().isoformat() for d in replay_calendar.sessions('2012-01-01', '2024-12-31', 'KR')]
    for e in X.EVIDENCE:
        got = X.market_ex_date(e['recordDate'], sessions)
        assert got['lastSessionOnOrBeforeRecord'] == e['lastSession']
        assert got['exDate'] == e['reportedExDate']
        # the #320 candidate is one session late on a non-session record date
        assert ex_date_candidate(e['recordDate'], True, sessions)['exDateCandidate'] != e['reportedExDate']
    # on a session record date both rules agree: ex-date = one session before
    assert X.market_ex_date('2023-03-31', sessions)['exDate'] == '2023-03-30'
    assert ex_date_candidate('2023-03-31', True, sessions)['exDateCandidate'] == '2023-03-30'
    assert X.market_ex_date('2012-01-02', sessions)['tier'] == 'CALENDAR_TOO_SHORT'
