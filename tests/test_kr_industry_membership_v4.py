import gzip
import json
from pathlib import Path

from pipeline import kr_industry_membership_v3 as V3
from pipeline import kr_industry_membership_v4 as V4

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / 'research_specs/kr-industry-membership-foundation-v4'
STATE = ROOT / 'data/kr-industry-membership-foundation-v4/state'


def load(name):
    return json.loads(gzip.decompress((STATE / name).read_bytes()))


def test_protocol_and_crosswalk_are_frozen_and_name_the_exact_28():
    from scripts.build_kr_industry_membership_v4 import frozen
    protocol, crosswalk = frozen('protocol.json'), frozen('crosswalk.json')
    a = protocol['absentSecurities']
    assert a['count'] == 28 and len(a['terminal22']) == 22 and len(a['nonTerminalPreferred6']) == 6
    assert not protocol['outcomesAllowed'] and crosswalk['frozenBeforeAnyStructuralEvaluation']


def test_every_raw_label_maps_to_exactly_one_group_or_unknown():
    from scripts.build_kr_industry_membership_v4 import frozen
    crosswalk = frozen('crosswalk.json')
    intervals = json.loads(gzip.decompress((ROOT / 'data/kr-industry-membership-foundation-v3/state/intervals.json.gz').read_bytes()))
    raw = {i['label'] for v in intervals.values() for i in v if i['label']}
    assert all(V4.research_group(label, crosswalk) in crosswalk['groups'] for label in raw)
    assert V4.research_group('존재하지 않는 업종', crosswalk) is None  # unmapped is UNKNOWN, never a nearest group
    assert V4.research_group('반도체  제조업', crosswalk) == V4.research_group('반도체 제조업', crosswalk) == 'ELECTRONICS_ELECTRICAL'
    for rename_pair in (('일차전지 및 이차전지 제조업', '일차전지 및 축전지 제조업'), ('자동차 부품 제조업', '자동차 신품 부품 제조업')):
        assert len({V4.research_group(x, crosswalk) for x in rename_pair}) == 1


def test_preferred_share_rule_needs_both_stem_code_and_name():
    labels, names = {'005930': 'A업'}, {'005930': '삼성전자'}
    assert V4.preferred_parent('005935.KS', ['삼성전자우'], labels, names) == '005930'
    assert V4.preferred_parent('005935.KS', ['다른회사우'], labels, names) is None
    assert V4.preferred_parent('005935.KS', ['삼성전자우'], {}, names) is None
    assert V4.preferred_parent('005930.KS', ['삼성전자'], labels, names) is None
    assert V4.preferred_parent('005387.KS', ['현대차2우B'], {'005380': 'x'}, {'005380': '현대자동차'}) is None


def test_official_prefix_semantics_are_not_assumed_without_overlap_proof():
    assert not V4.prove_code_structure([('A업', '116409')], [])['accepted']
    free = [{'section_code': '11', 'division_code': '64', 'class_code': '09', 'class_name': 'A업'}] * 5
    assert not V4.prove_code_structure([('A업', '116409')], free)['accepted']
    five = [{'section_code': '11', 'division_code': '64', 'class_code': f'0{i}', 'class_name': f'L{i}'} for i in range(5)]
    assert V4.prove_code_structure([(f'L{i}', f'11640{i}') for i in range(5)], five)['accepted']
    assert not V4.prove_code_structure([(f'L{i}', f'11640{i}') for i in range(4)] + [('L4', '999999')], five)['accepted']


def test_structure_gates_group_size_and_dominance():
    criteria = json.loads((ROOT / 'research_specs/kr-industry-membership-foundation-v2/criteria.json').read_text())
    ok = V4.structure([{'a': 6, 'b': 6, 'c': 6}], 18, criteria, 0.5)
    assert ok['sufficientGroupsGate'] and ok['fractionGate'] and ok['dominanceGate']
    small = V4.structure([{'a': 1, 'b': 1, 'c': 1, 'd': 1}], 4, criteria, 0.5)
    assert not small['sufficientGroupsGate'] and not small['fractionGate']
    assert not V4.structure([{'a': 9, 'b': 1}], 10, criteria, 0.35)['dominanceGate']
    assert V4.structure([{}], 0, criteria, 0.35)['dates'][0]['fractionInSufficientGroups'] is None  # absence is None, not a share


def test_committed_v4_state_results_and_unknown_preservation():
    audit = load('audit.json.gz')
    assert audit['nameDates'] == 73200 and audit['classifiedNameDates'] + audit['unknownNameDates'] == 73200
    assert audit['absent28']['total'] == 28 and audit['absent28']['resolved'] == 4 and audit['absent28']['unresolved'] == 24
    assert audit['absent28']['terminalResolved'] == 0 and audit['terminal'] == {'classified': 0, 'denominator': 2345}
    assert audit['decision'] == 'DATA_FOUNDATION_INSUFFICIENT_V4' and audit['v3ReconstructionReusedUnchanged']
    assert audit['gates']['terminalCoverage'] is False and audit['gates']['fractionInSufficientGroups'] is False
    assert audit['rawIndustryCount'] == 78 and audit['coarseIndustryCount'] == 14 and audit['unmappedRawLabels'] == []
    assert not audit['historicalOutcomeComputed']
    for ticker, r in audit['absent28']['perSecurity'].items():
        if r['status'] == 'UNKNOWN':
            assert 'reason' in r


def test_raw_classification_is_preserved_beside_research_industry():
    intervals = load('intervals.json.gz')
    v3 = json.loads(gzip.decompress((ROOT / 'data/kr-industry-membership-foundation-v3/state/intervals.json.gz').read_bytes()))
    rows = 0
    for ticker, ivs in intervals.items():
        for iv, old in zip(ivs, v3.get(ticker, [])):
            if iv['label']:
                rows += 1
                assert iv['raw_industry_name'] == iv['label'] and iv['research_industry_id'] and iv['research_industry_name']
    assert rows > 200
    assert intervals['005935.KS'][0]['reconstruction_status'] == 'PREFERRED_SHARE_OF_ANCHORED_COMMON'


def test_terminal_events_are_not_carried_across_identity_breaks():
    iv = V3.reconstruct_intervals('B', [{'effective_date': '2020-03-01', 'before_label': 'A', 'after_label': 'B', 'notice_date': '2020-03-01'}], break_dates=['2019-01-01'])
    assert V3.label_at(iv, '2018-01-01')['label'] is None


def test_v4_builder_has_no_outcome_module_access_and_reproduces_committed_state(monkeypatch):
    import builtins
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        assert not any(x in name for x in ('portfolio_validation', 'factor_anatomy', 'model_overlay', 'price_adjustment', 'yfinance'))
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)
    from scripts import build_kr_industry_membership_v4 as B
    intervals, audit = B.build()
    assert B.canonical(intervals) == (STATE / 'intervals.json.gz').read_bytes()
    assert B.canonical(audit) == (STATE / 'audit.json.gz').read_bytes()


def test_delisted_register_probe_is_one_frozen_request():
    protocol = json.loads((SPEC / 'protocol.json').read_text())
    assert protocol['bounded_probe']['maxRequests'] == 1 and protocol['bounded_probe']['retries'] == 0
    manifest = json.loads((ROOT / 'data/kr-industry-membership-foundation-v4/delisted-register/manifest.json').read_text())
    assert manifest['status'] == 200 and not manifest['historicalOutcomeComputed']
