"""Synthetic dates/provenance only; no historical outcome reader is called."""
import copy
import json
from pathlib import Path

import pytest
from pipeline import kr_industry_membership_v2 as V
from scripts.build_kr_industry_membership_v2 import explicit_labels, build, ROOT, SPEC


def fixture():
    issuer=b'issuer classification exact label';identity=b'corporal dated identity'
    sources={V.digest(issuer):issuer,V.digest(identity):identity}
    row={'security_id':'KRX:000001.KS','ticker':'000001.KS','corpCode':'00000001','reported_as_of':'2017-12-31',
         'known_from':'2018-03-30','reported_label':'Manufacturing','reported_code':'12345','subject_scope':'ISSUER',
         'identity_status':'DATED_ISSUER_SECURITY','source_sha256':V.digest(issuer),'source_locator':issuer.decode(),
         'identity_source_sha256':V.digest(identity),'identity_locator':identity.decode(),'taxonomy_version':None,
         'evidence_tier':'DART_EXPLICIT_ISSUER_CLASSIFICATION','receipt_no':'20180330000001'}
    row,reason=V.admit(row,sources,{})
    assert reason is None
    return row,sources


@pytest.mark.parametrize('stamp',['2017-12-31','2018-03-29','2018-03-30'])
def test_public_release_invisible_until_next_signal_day(stamp):
    row,_=fixture();assert V.state_at([row],row['security_id'],stamp)[0] is None


def test_forward_carry_age_and_termination():
    row,_=fixture();state,_=V.state_at([row],row['security_id'],'2020-03-30')
    assert state['classification_age_days']>700
    assert V.state_at([row],row['security_id'],'2020-03-30','2020-01-01')[1]=='IDENTITY_TERMINATED'


def test_later_changed_filing_does_not_backfill():
    row,_=fixture();later=dict(row,known_from='2023-03-30',group_id='Changed',reported_label='Changed')
    assert V.state_at([row,later],row['security_id'],'2020-01-01')[0]['group_id']==row['group_id']
    assert V.state_at([row,later],row['security_id'],'2023-03-30')[0]['group_id']==row['group_id']
    assert V.state_at([row,later],row['security_id'],'2023-03-31')[0]['group_id']=='Changed'


def test_conflict_is_unknown_until_next_unambiguous_public_cohort():
    row,_=fixture();conflict=dict(row,group_id='Conflict')
    assert V.state_at([row,conflict],row['security_id'],'2019-01-01')[1]=='CONFLICTED_PUBLIC_STATE'
    next_row=dict(row,known_from='2019-03-30')
    assert V.state_at([row,conflict,next_row],row['security_id'],'2019-03-31')[0] is not None


@pytest.mark.parametrize('scope',['SUBSIDIARY','SEGMENT','MERGER_PARTY','PRODUCT'])
def test_no_parent_promotion(scope):
    row,sources=fixture();row['subject_scope']=scope
    assert V.admit(row,sources,{})[0] is None


def test_current_map_cannot_admit_history():
    row,sources=fixture();row['evidence_tier']='CURRENT_ONLY_CROSSCHECK'
    assert V.admit(row,sources,{})[0] is None


def test_separate_global_taxonomy_required_and_ambiguous_mapping_closed():
    row,sources=fixture();row['taxonomy_version']='KSIC_TEST'
    assert V.admit(row,sources,{})[1]=='GLOBAL_TAXONOMY_EVIDENCE_UNPROVEN'
    book=b'official codebook';sources[V.digest(book)]=book
    taxonomy={'KSIC_TEST':{'status':'VERIFIED_OFFICIAL_CODEBOOK','source_sha256':V.digest(book),
                          'effective_source_sha256':V.digest(book),'mapping':{'12345':'Manufacturing'}}}
    assert V.admit(row,sources,taxonomy)[0]['standardized']
    taxonomy['KSIC_TEST']['mapping']['12345']='Other'
    assert V.admit(row,sources,taxonomy)[1]=='AMBIGUOUS_TAXONOMY_MAPPING'


def test_unknown_denominator_and_age_none_not_zero():
    criteria=json.loads((ROOT/SPEC/'criteria.json').read_text())
    names=[f'KRX:{n:06d}.KS' for n in range(120)]
    result=V.audit([],{'2018-01-01':names},criteria)
    assert result['nameDates']==120 and len(result['dates'][0]['UNKNOWN'])==120
    assert result['dates'][0]['classificationAgeDays']==[]
    assert result['decision']=='DATA_FOUNDATION_INSUFFICIENT_V2'
    with pytest.raises(ValueError,match='DENOMINATOR'):
        V.audit([],{'2018-01-01':names[:119]},criteria)


def test_explicit_parent_template_not_segment_heuristic():
    assert not explicit_labels('자회사는 한국표준산업분류상 금융업에 해당한다.')
    assert not explicit_labels('삼성전자 반도체 321 제품코드')
    assert explicit_labels('당사는 한국표준산업분류상 전기통신업에 해당한다.')


def test_actual_builder_has_no_outcome_module_access(monkeypatch):
    import builtins
    original_import=builtins.__import__
    forbidden=('portfolio_validation','factor_anatomy','model_overlay','price_adjustment','yfinance')
    def guarded(name,*args,**kwargs):
        assert not any(x in name for x in forbidden)
        return original_import(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',guarded)
    _,audit=build()
    assert audit['signalDates']==610 and audit['nameDates']==73200
    assert audit['everTop120Securities']==260
    assert not audit['historicalOutcomeComputed']
    assert audit['v1Decision']=='DATA_FOUNDATION_INSUFFICIENT_UNDER_V1_STRICT_CONTRACT'


def test_v1_files_independently_preserved():
    assert V.CONTRACT.endswith('_V2')
    assert json.loads((ROOT/'research_specs/kr-industry-membership-foundation-v1.json').read_text())['decision']=='DATA_FOUNDATION_INSUFFICIENT'
    assert Path(ROOT/'scripts/build_kr_industry_membership_foundation.py').exists()


def test_source_hash_changes_fail_closed():
    row,sources=fixture();sources=copy.deepcopy(sources);sources[row['source_sha256']]=b'changed'
    assert V.admit(row,sources,{})[0] is None
