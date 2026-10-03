from dataclasses import replace
import gzip
import json
from pathlib import Path
import pytest
from pipeline import kr_industry_membership as K
from scripts import collect_kr_industry_membership_sources as C
from scripts import build_kr_industry_membership_foundation as B

ROOT = Path(__file__).resolve().parents[1]
CRITERIA = json.loads((ROOT / B.CRITERIA).read_text())


def candidate(**changes):
    raw = b'SYNTHETIC dated classification proof'
    proof = {'source_sha256': K.sha256(raw), 'locator': raw.decode()}
    c = dict(security_id='KRX:000001.KS', ticker='000001.KS', region='KR', taxonomy_id='KSIC_DIVISION_2_DIGIT',
             taxonomy_version='SYNTHETIC_V1', industry_id='SYNTHETIC_GROUP', valid_from='2020-01-01', valid_to='2021-01-01',
             source_date='2020-01-01', release_date='2020-01-02', known_to=None, source='SYNTHETIC', source_sha256=K.sha256(raw),
             evidence_kind='DATED_ASSIGNMENT', source_kind='DART_CONTEMPORANEOUS_ASSIGNMENT',
             subject_scope='SUBJECT_SECURITY', identity_status='EXACT_DATED_SECURITY_ISSUER')
    for field in ('identity_provenance', 'taxonomy_version_evidence', 'economic_interval_evidence', 'release_date_evidence', 'codebook_evidence'):
        c[field] = proof
    c.update(changes)
    return c, raw


def row(**changes):
    c, raw = candidate(**changes)
    result, reasons = K.admit_assignment(c, raw, {K.sha256(raw): raw})
    assert not reasons
    return result


@pytest.mark.parametrize('field', ['source_kind', 'subject_scope', 'identity_status', 'identity_provenance',
                                   'taxonomy_version_evidence', 'economic_interval_evidence', 'release_date_evidence', 'codebook_evidence'])
def test_missing_proof_never_promotes(field):
    c, raw = candidate(**{field: None})
    r, reasons = K.admit_assignment(c, raw, {K.sha256(raw): raw})
    assert r is None and reasons


def test_hash_current_backfill_and_wrong_security_are_refused():
    c, raw = candidate()
    with pytest.raises(ValueError):
        K.admit_assignment(c, b'CHANGED', {K.sha256(raw): raw})
    for change in ({'evidence_kind': 'CURRENT_SNAPSHOT_ONLY'}, {'security_id': 'KRX:999999.KS'}, {'industry_id': 'UNKNOWN'}):
        c, raw = candidate(**change)
        r, reasons = K.admit_assignment(c, raw, {K.sha256(raw): raw})
        assert r is None and reasons


def test_review_flags_require_exact_retained_unique_locators():
    c, raw = candidate(codebook_evidence='verified')
    assert K.admit_assignment(c, raw, {K.sha256(raw): raw})[0] is None
    c, raw = candidate()
    assert K.admit_assignment(c, raw, {})[0] is None
    proof = {'source_sha256': K.sha256(raw), 'locator': 'absent'}
    c['codebook_evidence'] = proof
    assert K.admit_assignment(c, raw, {K.sha256(raw): raw})[0] is None
    c, raw = candidate()
    raw += raw
    c['source_sha256'] = K.sha256(raw)
    for field in ('identity_provenance', 'taxonomy_version_evidence', 'economic_interval_evidence', 'release_date_evidence', 'codebook_evidence'):
        c[field] = {'source_sha256': K.sha256(raw), 'locator': 'SYNTHETIC dated classification proof'}
    assert K.admit_assignment(c, raw, {K.sha256(raw): raw})[0] is None


def test_korean_source_encoding_is_explicit():
    c, _ = candidate()
    raw = '합성 업종 증거'.encode('euc-kr')
    proof = {'source_sha256': K.sha256(raw), 'locator': '합성 업종 증거', 'encoding': 'euc-kr'}
    c['source_sha256'] = K.sha256(raw)
    for field in ('identity_provenance', 'taxonomy_version_evidence', 'economic_interval_evidence', 'release_date_evidence', 'codebook_evidence'):
        c[field] = proof
    assert K.admit_assignment(c, raw, {K.sha256(raw): raw})[0] is not None
    c['identity_provenance'] = {**proof, 'encoding': 'utf-8'}
    assert K.admit_assignment(c, raw, {K.sha256(raw): raw})[0] is None


def test_bitemporal_visibility_expiry_and_version_conflicts():
    r = row(known_to='2020-01-10')
    for date in ['2019-12-31', '2020-01-02', '2020-01-11', '2021-01-01']:
        assert K.resolve([r], r.security_id, date, r.taxonomy_id)[0] is None
    assert K.resolve([r], r.security_id, '2020-01-03', r.taxonomy_id)[0] == r
    assert K.resolve([r, replace(r, industry_id='SYNTHETIC_OTHER')], r.security_id, '2020-01-03', r.taxonomy_id)[0] is None
    r2 = replace(r, taxonomy_version='SYNTHETIC_V2')
    assert K.resolve([r, r2], r.security_id, '2020-01-03', r.taxonomy_id)[1] == 'CONFLICTING_TAXONOMY_VERSIONS'


def test_unknown_names_stay_in_all_coverage_and_continuity_denominators():
    r = row()
    schedule = {d: [r.security_id, 'KRX:000002.KS'] for d in ['2020-01-03', '2020-01-10']}
    a = K.coverage([r], schedule, r.taxonomy_id, CRITERIA)
    assert a['annual'][0]['universeNameDates'] == 4
    assert a['annual'][0]['coverageFraction'] == .5
    assert a['adjacentContinuityFraction'] == .5
    assert a['dates'][0]['missingSecurityIds'] == ['KRX:000002.KS']
    empty = K.coverage([], schedule, r.taxonomy_id, CRITERIA)
    assert empty['dates'][0]['coverageFraction'] == 0
    assert empty['dates'][0]['classifiedFractionInSufficientGroups'] is None
    assert empty['adjacentContinuityFraction'] == 0


def test_group_size_and_outcome_blind_priority():
    rows = [row(ticker=f'{i:06d}.KS', security_id=f'KRX:{i:06d}.KS', industry_id=f'SYNTHETIC_{i // 5}') for i in range(15)]
    schedule = {d: [r.security_id for r in rows] for d in ['2020-01-03', '2020-01-10']}
    ready = K.coverage(rows, schedule, rows[0].taxonomy_id, CRITERIA)
    assert ready['decision'] == 'READY_FOR_INDUSTRY_ANATOMY'
    blocked = K.coverage(rows[:-1], schedule, rows[0].taxonomy_id, CRITERIA)
    assert 'GROUP_SIZE_OR_GROUP_COVERAGE_BELOW_FLOOR' in blocked['failedCriteria']
    audits = [{'taxonomy_id': t, 'decision': 'DATA_FOUNDATION_INSUFFICIENT'} for t in CRITERIA['candidateTaxonomiesInPriorityOrder']]
    audits[1] = ready
    assert K.select_taxonomy(audits, CRITERIA) == 'KSIC_DIVISION_2_DIGIT'


def test_strictly_prior_ranked_top120_no_current_union():
    old = [f'{i:06d}.KS' for i in range(120)]
    new = [f'{i:06d}.KS' for i in range(1, 121)]
    schedule, provenance = K.top120_schedule({'snapshots': [{'date': '2020-01-01', 'members': old}, {'date': '2020-01-10', 'members': new}]}, start='2020-01-10', through='2020-01-13')
    assert schedule['2020-01-10'] == ['KRX:' + t for t in old]
    assert provenance['2020-01-10'] == '2020-01-01'
    with pytest.raises(ValueError, match='FULL_TOP120'):
        K.top120_schedule({'snapshots': [{'date': '2020-01-01', 'members': old[:119]}]})


def test_source_markers_are_reading_list_and_output_is_never_overwritten(tmp_path, monkeypatch):
    markers, codes = C.classification_markers('자회사 한국표준산업분류 C261'.encode())
    assert markers and codes == ['C261']
    c, raw = candidate(subject_scope='SUBSIDIARY')
    assert K.admit_assignment(c, raw, {K.sha256(raw): raw})[0] is None
    def forbidden(*args, **kwargs):
        raise AssertionError('No network call authorized by this test')
    monkeypatch.setattr(C.Collector, 'request', forbidden)
    p = tmp_path / 'plan.json'
    p.write_text(json.dumps({'contract': 'KR_INDUSTRY_SOURCE_ACQUISITION_PLAN_V1', 'historicalOutcomeComputed': False, 'targets': []}))
    with pytest.raises(FileExistsError):
        C.collect(p, tmp_path, 0)


def test_real_source_hashes_and_full_universe_audits_reproduce_without_contact(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Offline audit contacted a source')
    monkeypatch.setattr(C.Collector, 'request', forbidden)
    B.verify_closure()
    mapping, audit, signals = B.build()
    assert mapping == B.read(ROOT, B.DATA + '/membership.json')
    assert audit == B.read(ROOT, 'docs/kr-industry-membership-foundation-v1-audit.json')
    assert signals == json.loads(gzip.decompress((ROOT / B.DATA / 'signal-date-audits.json.gz').read_bytes()))
    assert audit['everTop120Securities'] == 260
    assert audit['researchUniverseNameDates'] == audit['researchSignalDates'] * 120
    for a in signals['candidateAudits']:
        for d in a['dates']:
            assert d['universeCount'] == 120
            assert d['classifiedCount'] + len(d['missingSecurityIds']) == 120
        assert a['membershipSha256'] == mapping['membershipSha256']
    assert not any(audit[k] for k in ['historicalOutcomeComputed', 'modelFitPerformed', 'portfolioResultComputed', 'priorStudyRerun'])
