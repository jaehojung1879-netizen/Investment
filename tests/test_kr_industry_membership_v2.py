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


def _chapter_fixture(chapter_text):
    corp,receipt='00000001','20240319000001'
    main=("<title>사업보고서 (2024.03.19)</title> openCorpInfoNew('"+corp+"',").encode()
    chapter=chapter_text.encode()
    sources={V.digest(main):main,V.digest(chapter):chapter}
    record={'target':{'receiptNos':[receipt],'corpCode':corp,'ticker':'000001.KS','fiscalYear':2023,'identityBasis':'EXACT_STOCK_CODE'},
            'node':{'rcpNo':receipt},'mainResponse':{'sha256':V.digest(main),'status':200},
            'response':{'status':200,'sha256':V.digest(chapter),'url':'https://example.invalid/chapter'}}
    return record,sources


def test_chapter_supplement_uses_the_same_issuer_template_and_dated_identity():
    from scripts.build_kr_industry_membership_v2 import observations_from_chapter
    record,sources=_chapter_fixture('<p>당사는 한국표준산업분류상 전기통신업에 해당한다.</p>')
    rows,reason=observations_from_chapter(record,sources)
    assert reason is None and rows[0]['known_from']=='2024-03-19' and not rows[0]['standardized']
    record,sources=_chapter_fixture('<p>종속회사는 한국표준산업분류상 금융업에 해당한다.</p>')
    assert observations_from_chapter(record,sources)[0]==[]
    record['node']['rcpNo']='20250101000001'
    with pytest.raises(ValueError,match='LATER_RECEIPT'):
        observations_from_chapter(record,sources)


def test_assembler_refuses_a_batch_whose_bytes_do_not_match_the_frozen_plan(tmp_path):
    import hashlib
    from scripts import assemble_kr_industry_v2_sources as A
    inv=tmp_path/'kr-industry-v2-original-inventory-0';src=tmp_path/'kr-industry-v2-original-sources-0'
    inv.mkdir();src.mkdir()
    (inv/'remaining.json').write_text(json.dumps({'batch':0}));(inv/'remaining.json.sha256').write_text('0'*64+'\n')
    with pytest.raises(ValueError,match='FROZEN_BATCH_INVENTORY_MISMATCH'):
        A.assemble(tmp_path,None)
    raw=(inv/'remaining.json').read_bytes();(inv/'remaining.json.sha256').write_text(hashlib.sha256(raw).hexdigest()+'\n')
    (src/'a.gz').write_bytes(b'x')
    (src/'manifest-originals.json').write_text(json.dumps({'planSha256':hashlib.sha256(raw).hexdigest(),'archive':'a.gz','archiveSha256':'bad'}))
    with pytest.raises(ValueError,match='ORIGINAL_SOURCE_ARCHIVE_MISMATCH'):
        A.assemble(tmp_path,None)


def test_taxonomy_evidence_is_derived_from_retained_sources_and_claims_no_version():
    from scripts.build_kr_industry_membership_v2 import taxonomy_evidence
    evidence=taxonomy_evidence(ROOT)
    assert evidence['verifiedOfficialCodebooks']==[] and not evidence['taxonomyVersionEstablished']


def test_committed_v2_state_is_reproduced_from_retained_bytes_and_decision_is_structural():
    import gzip
    observations,audit=build()
    state=ROOT/'data/kr-industry-membership-foundation-v2/state'
    for name,value in (('observations.json.gz',observations),('audit.json.gz',audit)):
        raw=gzip.compress((json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode(),mtime=0)
        assert (state/name).read_bytes()==raw
    assert audit['decision']=='DATA_FOUNDATION_INSUFFICIENT_V2' and audit['acquiredV2Receipts']==2533
    assert audit['chapterSupplement']['frozenTargets']==68 and audit['chapterSupplement']['observations']==29
    assert audit['admittedObservations']==79 and audit['conflictedNameDates']==0
    assert sum(d['classified'] for d in audit['dates'])==2876 and audit['nameDates']==73200
    assert max(d['sufficientGroupCount'] for d in audit['dates'])==0 and not audit['standardizedTaxonomyReady']
    assert audit['terminalNameDates']=={'classified':0,'denominator':2345} and not audit['historicalOutcomeComputed']
