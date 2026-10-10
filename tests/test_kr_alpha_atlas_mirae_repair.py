"""Invented-price source guards plus exact-byte real evidence metadata only."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from pipeline import kr_alpha_atlas_mirae_repair as R
from pipeline import kr_alpha_atlas_phase_c_amendment as V2
from pipeline import kr_industry_anatomy as I
from pipeline import kr_industry_anatomy_execution as IE
from pipeline import kr_value_quality_catalyst as VQ
from pipeline.kr_alpha_atlas_phase_c import contract, labels, synthetic

ROOT = Path(__file__).resolve().parents[1]


def invented_quotes():
    # Deliberately no real prices. Known entitlement changes only quotation units.
    days = ['2018-01-22','2018-01-23','2018-01-24','2026-03-13','2026-03-16','2026-03-17']
    return {'rawQuotes':[{'date':d,'open':100.,'high':110.,'low':90.,'close':100.,'volume':1000.} for d in days],
            'registeredPartialEvents':[{'date':'2026-03-16','dividend':10.,'split':1.9}],
            'quarantinedSessions':['2018-01-23'],
            'stockDividendEvent':{'exDate':'2026-03-16','cashKrwPerCommonShare':10.,'commonSharesPerCommonShare':0.1}}


def test_published_v1_v2_and_all_scientific_choices_remain_exact():
    original, parent, effective = contract.load(), V2.load(), R.load()
    assert contract.file_hash(ROOT/contract.SPEC)==V2.ORIGINAL_SHA
    assert contract.file_hash(ROOT/V2.AMENDMENT)==R.PARENT_SHA
    allowed = {'version','registrationAmendmentId','phaseBIdentity','lifecycle',
               'sourceLimitations','inputIntegrityAmendment','dependencyHashes'}
    for key in set(parent)-allowed:
        assert effective[key]==parent[key]
    assert len(effective['eligibleFeatures'])==38
    assert sum(len(f['registeredHorizons']) for f in effective['eligibleFeatures'])==73
    assert contract.model_groups(effective)==contract.model_groups(original)
    assert effective['targets']==parent['targets']
    assert effective['benchmarkIntegrity']==parent['benchmarkIntegrity']
    assert effective['benchmarkIntegrity']['claimGate']=='VERIFIED'
    assert effective['lifecycle']['lockPrefix']==original['lifecycle']['lockPrefix']==V2.GLOBAL_LOCK
    assert effective['lifecycle']['resultPath']==original['lifecycle']['resultPath']
    assert effective['lifecycle']['artifactPrefix']==original['lifecycle']['artifactPrefix']
    assert effective['lifecycle']['authorizationPath']==R.AUTHORIZATION
    assert not (ROOT/R.AUTHORIZATION).exists()


def test_official_source_receipts_and_boundary_policy_metadata_only():
    # No real price reconstruction or return calculation in CI.
    q=R.read_correction(ROOT)
    assert q['quarantinedSessions']==['2018-01-23']
    assert q['rightsEvent']['valueOrAdjustmentFactor'] is None
    assert q['rightsEvent']['shareClass']=='NEW_NONCONVERTIBLE_PREFERRED_00680K_NOT_COMMON_006800'
    assert q['rightsEvent']['allocationPerOldShare']==0.1979557317
    assert q['stockDividendEvent']['commonSharesPerCommonShare']==0.0073206
    receipt=json.loads((ROOT/R.BASE/'source-diagnostic.json').read_text())
    assert receipt['basisStatus'].startswith('VERIFIED_CONNECTED_RAW_PRICE_SEGMENTS')
    assert receipt['sourceRows']==3364
    assert receipt['event2018']['firstUnregisteredQuoteScaleChange']=='2018-01-23'
    assert receipt['event2018']['priorReportLargestResidualDate']=='2018-03-28'
    assert receipt['event2026']['singleRegisteredCashFactor']!=receipt['event2026']['correctedPartialIndexFactor']
    assert all(receipt[k]==0 for k in ['realHistoricalAlphaOutcomeReads','realForwardLabels','realHistoricalModelFits',
                                      'realPortfolioBacktests','formalExecutionDispatches','permanentExecutionLocksCreated'])


def test_cash_and_stock_entitlements_are_distinct_and_not_duplicated():
    out=R.reconstruct(invented_quotes())
    # Cash once, stock entitlement once; cash never alters share-volume units.
    assert out.loc['2026-03-16','Close']==pytest.approx(100*1.1/.9)
    assert out.loc['2026-03-16','Volume']==pytest.approx(1000/1.1)
    assert out.loc['2026-03-13','Close']==100
    assert out.loc['2026-03-13','Volume']==1000
    assert out.loc['2026-03-16','High']/out.loc['2026-03-16','Low']==pytest.approx(110/90)
    assert out.loc['2026-03-16','Close']!=pytest.approx(100/.9**2)


def test_unvalued_right_is_not_a_payoff_or_a_bridge():
    out=R.reconstruct(invented_quotes())
    assert out.loc['2018-01-23',['Open','High','Low','Close']].isna().all()
    assert out.loc['2018-01-24','Close']==100
    assert out.loc['2018-01-23','Volume']==1000  # Raw non-price source retained.
    days=pd.to_datetime(['2018-01-22','2018-01-23','2018-01-24'])
    assert not R.window_valid(out,days,2,3)
    assert R.window_valid(out,days,2,1)


def test_future_corporate_action_cannot_rewrite_earlier_source_prefix():
    q=invented_quotes();a=R.reconstruct(q)
    changed=deepcopy(q);changed['stockDividendEvent']['commonSharesPerCommonShare']=0.9
    changed['stockDividendEvent']['cashKrwPerCommonShare']=70
    b=R.reconstruct(changed)
    pd.testing.assert_frame_equal(a.loc[:'2026-03-13'],b.loc[:'2026-03-13'])


@pytest.mark.parametrize('change',[{'low':0},{'high':99},{'volume':0},{'close':float('nan')}])
def test_invalid_raw_ohlcv_is_refused_without_filling(change):
    q=invented_quotes();q['rawQuotes'][2].update(change)
    with pytest.raises(ValueError,match='INVALID_RAW_KRX_OHLCV'):
        R.reconstruct(q)


def test_endpoint_only_industry_reader_cannot_cross_intermediate_source_gap():
    days=pd.bdate_range('2018-01-19',periods=4)
    frame=pd.DataFrame({'Close':[100.,101.,np.nan,102.]},index=days)
    # Legacy endpoints alone would admit this invented gap.
    assert np.isfinite(I.trailing_return(frame.Close.to_numpy(),3,3))
    with R.source_window_guards():
        assert IE.past_arrays({R.TICKER:frame},R.TICKER,days,3,3) is None
        assert IE.past_arrays({'SYN_OTHER':frame},'SYN_OTHER',days,3,3) is not None
        assert IE.past_arrays({R.TICKER:frame},R.TICKER,days,3,0).tolist()==[102.]


def test_value_quality_endpoint_reader_refuses_gap_but_keeps_accounting():
    days=IE.RC.sessions('2017-01-01','2018-02-02','KR')
    frame=pd.DataFrame({'Close':np.ones(len(days))*100},index=days)
    frame.loc['2018-01-23','Close']=np.nan
    fake={'relative126':1.,'momentum121':2.,'bookToMarketProxy':3.,'accountingProvenance':{'status':'VISIBLE'}}
    fake.update({k:fake.get(k) for k in VQ.RAW_FEATURES})
    with patch.object(VQ,'feature_at',return_value=fake),R.source_window_guards():
        out=VQ.feature_at(R.TICKER,'2018-02-02',[],None,frame,frame)
    assert out['relative126'] is None
    # The 12-minus-1-month window ends BEFORE the quarantine, so it stays usable.
    assert out['momentum121']==2.
    assert out['bookToMarketProxy']==3.
    assert out['accountingProvenance']=={'status':'VISIBLE'}


def test_raw_non_price_capacity_and_accounting_are_not_blanket_masked():
    days=pd.bdate_range('2017-01-02','2018-02-02')
    values={'D01_volumeSurge5_60':1.,'E03_capacityMedianTradedValue60':1e10,'E01_amihudIlliquidity60':2.}
    inner=SimpleNamespace(calendar=days,basis_cause=lambda d,n:None,
                          features_at=lambda d:(dict(values),{}))
    wrapped=R.SourceBoundaryBars(inner)
    out,reason=wrapped.features_at('2018-02-02')
    assert out['D01_volumeSurge5_60']==1.
    assert out['E03_capacityMedianTradedValue60']==1e10
    assert 'E01_amihudIlliquidity60' not in out
    assert reason['E01_amihudIlliquidity60']=='UNCONFIRMED_CORPORATE_ACTION_IN_WINDOW'
    assert wrapped.basis_cause('2018-02-02',127)=='UNCONFIRMED_CORPORATE_ACTION_IN_WINDOW'
    assert wrapped.basis_cause('2018-02-02',2) is None


def test_same_frozen_label_engine_rejects_synthetic_holding_window_with_source_boundary():
    data=synthetic.market(names=8)
    spec=contract.load()
    first=data.rows.iloc[0]; entry,exit_pos,_=labels.window_sessions(data.days,first.date,21,spec['developmentCutoff'])
    ticker=first.ticker
    data.closes[ticker][entry+5]=np.nan
    book=labels.build_labels(data,21,spec['developmentCutoff'],labels.synthetic_permit(data),labels.Counters())
    assert book.table.iloc[0]['missingReason']=='MISSING_OR_INVALID_PRICE_WINDOW'
    assert book.table.iloc[0]['gross'] is None or np.isnan(book.table.iloc[0]['gross'])
    group=data.rows.date.eq(first.date)&data.rows.industry.eq(first.industry)
    assert book.table.loc[group,'industryState'].eq('BLOCKED').all()


@pytest.mark.parametrize('field,value',[
    ('globalOneShotLock','refs/tags/second-chance'),
    ('sameStudyId','a-new-study'),('formalExecutionAuthorized',True),
    ('correctedMatrixDigest','0'*64),
])
def test_mutated_repair_registration_is_rejected_even_with_a_rewritten_sidecar(tmp_path,field,value):
    meta=json.loads((ROOT/R.ADDENDUM).read_text());meta[field]=value
    p=tmp_path/'mutated.json';p.write_bytes(contract.canonical(meta))
    side=tmp_path/'mutated.sha256';side.write_text(contract.file_hash(p))
    with patch.object(R,'ADDENDUM',str(p)),patch.object(R,'SIDECAR',str(side)):
        with pytest.raises(ValueError):R.load()


def test_absent_fresh_owner_approval_stops_before_preparation_and_claim(tmp_path):
    github=SimpleNamespace(main=lambda:'invented-main',claim=lambda *a:pytest.fail('claimed'),
                           previous_results=lambda p:False,locks=lambda p:[])
    with patch.object(R.subprocess,'check_output',side_effect=[b'invented-main',b'']),patch.object(R,'prepare',side_effect=AssertionError('prepared')):
        with pytest.raises(ValueError,match='SOURCE_REPAIR_AUTHORIZATION_ABSENT'):
            R.formal(work=tmp_path/'formal-not-created',github=github)
    assert not (tmp_path/'formal-not-created').exists()


def test_complete_synthetic_study_uses_the_same_repaired_contract(tmp_path):
    report=synthetic.complete_study(R.load(),tmp_path)
    assert report['status']=='SYNTHETIC_ONLY'
    assert report['featureHorizonTests']==73
    assert report['familyComparisons']==30
    assert report['interactions']==6
    assert report['noRealInvestmentEvidence']
    assert report['counters']['realOutcomeReads']==report['counters']['realLabels']==report['counters']['realModelFits']==0
