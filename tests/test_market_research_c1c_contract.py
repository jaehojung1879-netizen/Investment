"""Synthetic states/dates only; no vendor, historical value or real ledger."""
import copy
import itertools

import pytest

from pipeline import kr_market_risk_model as K
from pipeline import market_research_c1c as C
from pipeline import market_research_c1c_contract as V
from pipeline import prospective_receipt_core as P
from scripts.check_market_research import fixture


def test_fixed_controls_and_distinct_families():
    c=V.contract()
    assert c['primaryControl']=='C0' and c['auxiliaryControl']=='C1'
    assert not c['selectControlFromResults'] and not c['historicalExecutionEnabled']
    assert 'NOT_POWER_GUARANTEE' in c['supportStatus']
    for base,fam,s,t,f in itertools.product(V.CONTROLS,V.FAMILIES,(0,1),(0,1),(0,1,2)):
        assert V.arm_target(base,fam,'BASE',s,t,f,breakout=True)==(K.rule(base,s,t,f),False)


def test_one_rung_is_not_breakout_and_zero_is_new_interaction():
    original,breakout=V.FAMILIES
    assert V.arm_target('C0',original,'REENTRY',0,0,0,breakout=True,previous=.4)==(.7,False)
    assert V.arm_target('C0',breakout,'REENTRY',0,0,0,breakout=False,previous=.4)==(1.,False)
    assert V.arm_target('C0',original,'COMBINED',0,0,0,breakout=False,previous=0.)==(.4,False)
    assert V.ORIGINAL_GRID==(.4,.7,1.) and V.HARD_EXIT_GRID==(0.,.4,.7,1.)
    for fam in V.FAMILIES:
        assert V.arm_target('C0',fam,'COMBINED',1,1,2,breakout=True,previous=1.)==(0.,False)


@pytest.mark.parametrize('value',[True,.5,3,float('inf'),float('nan'),'1',[],{}])
def test_invalid_domain(value):
    with pytest.raises(ValueError,match='STATE_OUTSIDE'):
        V.arm_target('C0',V.FAMILIES[0],'BASE',0,0,value,breakout=False)


def test_missing_consensus_and_hold():
    fam=V.FAMILIES[0]
    assert V.arm_target('C0',fam,'BASE',None,None,2,breakout=None)==(.4,False)
    with pytest.raises(ValueError,match='FIRST_TARGET'):
        V.arm_target('C0',fam,'BASE',None,None,None,breakout=None)
    assert V.arm_target('C0',fam,'BASE',None,None,None,breakout=None,previous=.7)==(.7,True)


def test_prefix_invariance_and_publication_timing():
    close,plan,states=fixture('US');plan=plan.iloc[:8]
    actual=V.panel_targets(close,states,plan,'US');cut=plan.decisionDate.iloc[4]
    prefix=V.panel_targets(close.loc[:cut],states.loc[:cut],plan.iloc[:5],'US')
    assert prefix==actual[:5] and all(set(r['cells'])==set(V.cell_ids()) for r in actual)
    poison=close.copy();poison.loc[poison.index>cut]*=30
    assert V.panel_targets(poison,states,plan,'US')[:5]==prefix
    late=states.copy();late.loc[plan.decisionDate.iloc[0],'slowKnownAt']='2030-01-01T00:00:00Z'
    with pytest.raises(ValueError,match='NOT_KNOWN'):V.panel_targets(close,late,plan,'US')


def test_complete_contrasts_no_control_selection():
    values={k:float(i%4) for i,k in enumerate(V.cell_ids())}
    out=V.family_contrasts(values)
    assert len(out)==4
    for key,row in out.items():
        assert (row['exit'],row['reentry'],row['interaction'])==(1.,2.,0.)
        assert row['controlRole']==('PRIMARY' if key.startswith('C0/') else 'AUXILIARY_DESCRIPTIVE')
        assert not row['nominationAllowed']
    values.pop(next(iter(values)))
    with pytest.raises(ValueError,match='COMPLETE'):V.family_contrasts(values)


def identity(market='US',economic=True):
    return {'evidenceClass':C.SYNTHETIC,'instrument':('SPY' if market=='US' else '069500.KS') if economic else ('SP500_PRICE_INDEX' if market=='US' else 'KS200_PRICE_INDEX'),
        'returnBasis':'TOTAL_RETURN' if economic else 'PRICE_INDEX','currency':'USD' if market=='US' else 'KRW',
        'cashBasis':'DTB3_PRIOR_KNOWN_ACT360' if market=='US' and economic else 'ZERO',
        'sourceStatus':'SYNTHETIC_HASH_VERIFIED','rightsStatus':'SYNTHETIC_ALLOWED',
        'reconciliationStatus':'SYNTHETIC_PASS','sourceSha256':'1'*64}


@pytest.mark.parametrize('market',['KR','US'])
def test_basis_substitution_and_bad_vendor_fail_closed(market):
    good=identity(market)
    assert not V.synthetic_basis_check(market,'ETF_CASH_ECONOMIC',good)['sourceAdmitted']
    for key,bad in [('returnBasis','PRICE_INDEX'),('instrument','OTHER'),('sourceStatus','BLOCKED_HASH_MISMATCH'),('rightsStatus','UNVERIFIED'),('reconciliationStatus','MISSING')]:
        with pytest.raises(ValueError,match='BLOCKED'):
            V.synthetic_basis_check(market,'ETF_CASH_ECONOMIC',dict(good,**{key:bad}))
    assert V.synthetic_basis_check(market,'C1_PRIMARY_REPLICA',identity(market,False))['status'].startswith('SYNTHETIC')


def test_market_and_basis_disagreement_stop_promotion():
    both={m:{'DIAGNOSTIC':'IMPROVED','ECONOMIC':'IMPROVED'} for m in ['KR','US']}
    assert V.cross_market_verdict(both)['status']=='DESCRIPTIVE_AGREEMENT_ONLY'
    both['US']['ECONOMIC']='NOT_IMPROVED'
    assert V.cross_market_verdict(both)['status']=='BASIS_DEPENDENT_NO_PROMOTION'
    both['US']['DIAGNOSTIC']='NOT_IMPROVED'
    assert V.cross_market_verdict(both)['status']=='MARKET_DISAGREEMENT_NO_PROMOTION'
    both['US']['ECONOMIC']='BLOCKED'
    assert V.cross_market_verdict(both)['status']=='BLOCKED_SOURCE_OR_SUPPORT'
    assert not V.cross_market_verdict(both)['promotionAllowed']


def receipt(market='KR',signal='2026-10-30',previous=None):
    return V.synthetic_receipt(market=market,signal_date=signal,created_at=C.final_at(signal,market).isoformat(),
        authorizing_merge_at='2026-10-26T00:00:00Z',layers={'slow':0,'transition':0,'fast':1},breakout=True,
        source_sha256='1'*64,previous=previous)


@pytest.mark.parametrize('market',['KR','US'])
def test_resigned_allowed_multiplier_and_flags_cannot_bypass_semantics(market):
    good=receipt(market)
    assert V.validate_synthetic_receipts([good])['receipts']==1
    for mutation in [lambda r:r['cells'][next(iter(r['cells']))].update(target=.4),lambda r:r['cells'][next(iter(r['cells']))].update(heldForMissing=True),
                     lambda r:r.update(productionAllowed=True),lambda r:r.update(evidenceClass='PROSPECTIVE_PAPER'),
                     lambda r:r.update(executionDate='2026-11-03'),lambda r:r.update(schemaVersion=2)]:
        bad=copy.deepcopy(good);mutation(bad);bad['receiptSha256']=P.receipt_digest(bad)
        with pytest.raises(ValueError,match='MISMATCH'):V.validate_synthetic_receipts([bad])


def test_numeric_boolean_equality_does_not_replace_byte_identity():
    good=receipt()
    for key,val in [('productionAllowed',0),('schemaVersion',True)]:
        bad=copy.deepcopy(good);bad[key]=val
        assert bad==good
        with pytest.raises(ValueError,match='MISMATCH'):V.validate_synthetic_receipts([bad])
        with pytest.raises(ValueError,match='CONFLICT'):V.append_synthetic([good],bad)


def test_immutable_append_and_safe_resumption():
    a=receipt();rows=V.append_synthetic((),a)
    assert V.append_synthetic(rows,a)==rows
    b=receipt(signal='2026-11-06',previous=a);chain=V.append_synthetic(rows,b)
    assert V.validate_synthetic_receipts(chain)['receipts']==2 and len(b['cells'])==16
    with pytest.raises(ValueError,match='MISMATCH'):V.validate_synthetic_receipts([b])
    bad=copy.deepcopy(b);bad['previousReceiptSha256']='0'*64;bad['receiptSha256']=P.receipt_digest(bad)
    with pytest.raises(ValueError,match='MISMATCH'):V.validate_synthetic_receipts([a,bad])


def test_finality_merge_and_next_open_bounds():
    args=dict(market='KR',signal_date='2026-10-30',authorizing_merge_at='2026-10-26T00:00:00Z',layers={'slow':0,'transition':0,'fast':0},breakout=False,source_sha256='1'*64)
    for stamp in ['2026-10-30T08:59:59Z','2026-11-02T00:00:00Z']:
        with pytest.raises(ValueError,match='WINDOW'):V.synthetic_receipt(**args,created_at=stamp)
    args['authorizing_merge_at']='2026-10-30T00:00:00Z'
    with pytest.raises(ValueError,match='BOUNDARY'):V.synthetic_receipt(**args,created_at='2026-10-30T09:00:00Z')


@pytest.mark.parametrize('market',['KR','US'])
def test_fixed_support_schedule_and_calendar_bounds(market):
    s=V.prospective_schedule(market,'2026-10-26T00:00:00Z')
    assert s['firstSignalDate']=='2026-10-30' and not s['inferenceAllowed']
    for h in s['horizons']:
        assert len(h['blocks'])==8 and h['firstDescriptiveReadoutAt']<h['supportFloorNotBefore']
        for before,after in zip(h['blocks'][:-1],h['blocks'][1:]):assert before['maturityDate']<=after['executionDate']
    with pytest.raises(ValueError,match='CALENDAR_SUPPORT'):V.prospective_schedule(market,'2035-05-01T00:00:00Z')
