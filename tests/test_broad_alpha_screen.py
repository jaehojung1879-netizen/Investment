"""Synthetic-only checks of the batch screen. No market data is read."""
import json

import pytest

from research.broad_alpha_screen_v1 import hypotheses as HY
from research.broad_alpha_screen_v1 import screen as S
from research.corporate_event_outcome_v1 import synthetic as SYN

LONG, AVOID = 'K3_SUPPLY_GE_10PCT', 'P2_DILUTION'


def _market(alpha, seed=7, hypothesis=LONG, **kw):
    market, events = SYN.world(n_sessions=3200, n_names=80, n_events=320, alpha_daily=alpha, seed=seed, **kw)
    for e in events:
        e['hypothesis'] = hypothesis
    market = {**market, 'cash': {c: market['cash'] for c in (S.PRIMARY_CASH, *S.CASH_SENSITIVITY)}, 'exceptions': {}}
    return market, {hypothesis: events}


def test_planted_long_edge_is_recovered_and_survives_costs():
    market, events = _market(0.0006)
    r = S.evaluate(events, market, draws=400)
    one = r['hypotheses'][LONG]['H126']
    assert one['selectionDelta']['cost0x'] > one['selectionDelta']['cost1x'] > one['selectionDelta']['cost2x'] > 0.02
    assert one['ciSimultaneous'][0] > 0
    assert r['verdicts'][LONG]['verdict'] == 'EXPLORATORY_SUPPORT_NOT_VERIFIED'
    assert r['promotionEligible'] is False and 'VERIFIED' not in {v['verdict'] for v in r['verdicts'].values()}


def test_no_edge_is_never_called_support_and_empty_hypotheses_are_blocked_not_zero():
    market, events = _market(0.0)
    r = S.evaluate(events, market, draws=400)
    assert r['verdicts'][LONG]['verdict'] in ('INCONCLUSIVE', 'EXPLORATORY_REJECT_ECONOMIC_EFFECT')
    assert r['verdicts']['P1_CAPITAL_RETURN']['verdict'] == 'SOURCE_BLOCKED'
    assert r['holm']['pValues']['P1_CAPITAL_RETURN'] == 1.0 and set(r['holm']['pValues']) == set(HY.PRIMARY_FAMILY)


def test_avoid_signal_is_read_in_its_own_direction():
    market, events = _market(-0.0006, hypothesis=AVOID)
    r = S.evaluate(events, market, draws=400)
    assert r['hypotheses'][AVOID]['H126']['selectionDelta']['cost1x'] < -0.02
    assert r['verdicts'][AVOID]['verdict'] == 'EXPLORATORY_SUPPORT_NOT_VERIFIED'
    market, events = _market(+0.0006, hypothesis=AVOID)        # wrong sign can never support an avoid signal
    assert S.evaluate(events, market, draws=400)['verdicts'][AVOID]['verdict'] != 'EXPLORATORY_SUPPORT_NOT_VERIFIED'


def test_unpriced_window_is_excluded_and_bounded_never_filled():
    market, events = _market(0.0006)
    victim = events[LONG][5]
    lv = market['levels'][victim['ticker']]
    cut = market['sessions'].index(victim['entrySession']) + 40
    for d in market['sessions'][cut:]:
        lv.pop(d, None)
    part = S.partition(events[LONG], 'H126', market)
    assert part['states']['TERMINAL_UNRESOLVED'] >= 1 and victim['ticker'] in part['terminal']
    assert all(s.ticker != victim['ticker'] or S.window_state(s, market)[0] == 'PRICED' for s in part['priced'])
    one = S.evaluate_one(LONG, events[LONG], 'H126', market, 9, {}, draws=200)
    assert one['downsideStressDelta'] < one['selectionDelta']['cost1x']


def test_five_name_cap_never_holds_more_than_five():
    market, events = _market(0.0)
    slots = S.partition(events[LONG], 'H126', market)['priced']
    capped = S.cap_names(slots)
    assert max(sum(1 for k in capped if k.entry <= s.entry < k.exit) for s in capped) <= S.MAX_NAMES


def test_execution_is_refused_without_an_exact_hash_authorization(tmp_path, monkeypatch):
    contract, events = tmp_path / 'contract.json', tmp_path / 'events.jsonl.gz'
    events.write_bytes(b'x')
    contract.write_text(json.dumps({'codeSha256': {}, 'inputs': {'eventsSha256': S.sha(events), 'priceShardSha256': {}}}))
    for name, value in (('CONTRACT', contract), ('EVENTS', events), ('AUTHORIZATION', tmp_path / 'AUTHORIZATION.json'),
                        ('CLAIM', tmp_path / 'claim.json'), ('RESULT', tmp_path / 'result.json')):
        monkeypatch.setattr(S, name, value)
    with pytest.raises(S.Refused, match='NO_OWNER_AUTHORIZATION'):
        S.gate(tmp_path)
    S.AUTHORIZATION.write_text(json.dumps({'phrase': 'APPROVE BROAD_ALPHA_SCREEN_V1 EXPLORATORY_ONE_SHOT deadbeef'}))
    with pytest.raises(S.Refused, match='AUTHORIZATION_DOES_NOT_PIN_THIS_CONTRACT'):
        S.gate(tmp_path)
    S.AUTHORIZATION.write_text(json.dumps({'phrase': S.PHRASE.format(sha=S.sha(contract))}))
    with pytest.raises(S.Refused, match='EXECUTION_CLAIM_NOT_COMMITTED'):
        S.gate(tmp_path)
    S.RESULT.write_text('{}')
    with pytest.raises(S.Refused, match='ONE_SHOT_SPENT'):
        S.gate(tmp_path)


def test_components_are_described_never_judged():
    market, events = _market(0.0006, hypothesis='K2_BUYBACK_NO_CANCEL')
    r = S.evaluate(events, market, draws=200)
    assert r['verdicts']['K2_BUYBACK_NO_CANCEL']['verdict'] == 'SECONDARY_DESCRIPTIVE_NO_VERDICT'


def test_every_hypothesis_has_a_direction_and_a_source_grade():
    assert all(v[0] in (1, -1) and v[1] and v[2] for v in HY.HYPOTHESES.values())
