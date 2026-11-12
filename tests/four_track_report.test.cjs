'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
if (!globalThis.crypto) Object.defineProperty(globalThis,'crypto',{value:require('node:crypto').webcrypto});
const A=require('../app.js');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib');
const fixture=name=>zlib.gunzipSync(fs.readFileSync(path.join(__dirname,'fixtures/economic_readout_report_v1',name+'.gz')));
const economicDocs=()=>({economic:JSON.parse(fixture('results.json')),economicPins:JSON.parse(fixture('source-pins.json')),
  economicPlan:JSON.parse(fixture('readout-plan.json')),economicReadme:fixture('README.md').toString()});
const storedReader=async(_url,s)=>fixture(s.path==='research/historical_alpha_discovery_v1/results/summary.json'
  ? 'kr-summary.json' : s.path.split('/').at(-1));
const VIEWED_AT='2026-11-01T06:00:00Z';

test('UNKNOWN differs from an explicitly measured zero; arrays retain units',()=>{
  const docs={s:{zero:0,missing:null,range:[-.08,.16],bad:true}};
  assert.equal(A.researchMetric(docs,'s','/zero','x','%',100).value,0);
  for(const path of ['/missing','/absent','/bad']) assert.equal(A.researchMetric(docs,'s',path,'x','%',100).value,null);
  assert.deepEqual(A.researchMetric(docs,'s','/range','CI','pp',100).value,[-8,16]);
  assert.equal(A.researchMetricText({value:null,unit:'%'}),'UNKNOWN');
  assert.equal(A.researchMetricText({value:0,unit:'%'}),'0 %');
  assert.equal(A.researchPointer({a:{'x/y':2}},'/a/x~1y'),2);
  assert.equal(A.researchPointer({},'/__proto__/constructor'),null);
});
test('projection keeps conditional H126 comparisons distinct and absent full NAV null',()=>{
  const docs={kr:{intradayVsMomentum:Array(18).fill(null),pairedComparisons:Array(18).fill(null),portfolios:Array(54).fill(null)}};
  docs.kr.intradayVsMomentum[17]={meanBlockExcess:.02,validPairs:19,scheduledBlocks:24,descriptiveYearBootstrap95:[-.08,.16]};
  docs.kr.pairedComparisons[17]={meanBlockExcess:-.005,validPairs:20,scheduledBlocks:24,descriptiveYearBootstrap95:[-.06,.06]};
  docs.kr.portfolios[2]={complete:false,metrics:null};
  const before=structuredClone(docs),t=A.fourTrackProjection(docs)[0];
  assert.equal(t.metrics[0].value,2);assert.deepEqual(t.metrics[0].denominator,[19,24]);
  assert.equal(t.metrics[2].value,-.5);assert.deepEqual(t.metrics[2].denominator,[20,24]);
  assert.deepEqual(t.metrics.slice(4,7).map(m=>m.value),[null,null,null]);
  assert.equal(t.evidenceClass,'OBSERVED_HISTORICAL');assert.equal(t.researchStatus,'BLOCKED');
  assert.deepEqual(docs,before);
});
test('design cells are never historical economics or a source approval',()=>{
  const c={primaryControl:'C0',auxiliaryControl:'C1',families:['structural','post-result-breakout'],arms:['BASE','HARD_EXIT','REENTRY','COMBINED']};
  const t=A.fourTrackProjection({market:c})[2];
  assert.equal(t.metrics[0].value,16);assert.equal(t.historicalCagr,null);assert.equal(t.economicVerdict,null);
  assert.equal(t.evidenceClass,'SYNTHETIC_OR_DESIGN');assert.equal(t.researchStatus,'NOT TESTED');
  assert.equal(A.fourTrackProjection({market:{...c,families:[]}})[2].metrics[0].value,null);
});
test('missing sources produce UNKNOWN rather than canned anchor numbers or study success',async()=>{
  const r=await A.loadFourTrackReport(async()=>{throw new Error('offline')},'2026-10-31T00:00:00Z');
  assert.equal(r.tracks.length,4);assert.ok(r.tracks.every(t=>t.reportStatus==='BLOCKED'&&t.investmentQualified===false));
  assert.ok(r.tracks.flatMap(t=>t.metrics).every(m=>m.value===null));
  assert.ok(r.tracks.every(t=>t.evidenceClass==='UNVERIFIED_OR_BLOCKED'));
  const html=A.fourTrackMarkup(r);
  assert.match(html,/UNKNOWN/);assert.doesNotMatch(html,/1\.99|23,939|0\.136/);
  assert.match(html,/투자 승인이나 연구 성공이 아닙니다/);
  assert.deepEqual(r.investmentNominations,[]);assert.equal(r.productionEffect,'NONE');
});
test('source corruption and recomputed caller bytes cannot replace pinned result files',async()=>{
  const r=await A.loadFourTrackReport(async()=>Buffer.from('{"cagr":999,"modelFits":999}'),'2026-10-31T00:00:00Z');
  assert.ok(Object.values(r.sources).every(s=>s.status==='UNAVAILABLE_OR_UNVERIFIED'));
  assert.ok(r.tracks.flatMap(t=>t.metrics).every(m=>m.value===null));
  assert.ok(Object.isFrozen(A.RESEARCH_TRACK_SOURCES));
  for(const s of Object.values(A.RESEARCH_TRACK_SOURCES)) {
    assert.ok(Object.isFrozen(s));assert.match(s.commit,/^[0-9a-f]{40}$/);assert.match(s.sha256,/^[0-9a-f]{64}$/);
    assert.throws(()=>{s.sha256='0'.repeat(64)},TypeError);
  }
});
test('future source snapshots are refused before reading and report clock needs timezone',async()=>{
  let reads=0;
  const r=await A.loadFourTrackReport(async()=>{reads++;throw new Error('must not read')},'2000-01-01T00:00:00Z');
  assert.equal(reads,0);assert.ok(r.tracks.every(t=>t.reportStatus==='BLOCKED'));
  await assert.rejects(A.loadFourTrackReport(async()=>new Uint8Array(),'2026-10-31'),/TIMEZONE/);
});
test('rendered text is escaped, and legacy C2/current CHAMPION remains a separate cohort',()=>{
  const tracks=A.fourTrackProjection({});tracks[0].title='<script>alert(1)</script>';
  const sources=structuredClone(A.RESEARCH_TRACK_SOURCES);
  const r={schema:'FOUR_TRACK_RESULTS_V1',generatedAt:'2026-10-31T00:00:00Z',sources,tracks};
  const html=A.fourTrackMarkup(r);assert.doesNotMatch(html,/<script>/);assert.match(html,/&lt;script&gt;/);
  assert.match(html,/C2 과거 재현·Oct23 CHAMPION paper·Market C는 각각 다른 연구/);
  assert.match(html,/OBSERVED_HISTORICAL/);assert.match(html,/SYNTHETIC_OR_DESIGN/);assert.match(html,/UNVERIFIED_OR_BLOCKED/);
});
test('US date-held count is a count, distinct from unknown/full admission',()=>{
  const docs={us:{filings:{records:23940,tickers:753,bothDatesFullyValid:23939,withheld:[{id:'SYN_DATE_HELD'}]},fiscalShardReview:{retained:23935},outcomeReads:0,modelFits:0}};
  const t=A.fourTrackProjection(docs)[1];
  assert.equal(t.metrics.find(m=>m.label==='날짜 근거 보류').value,1);
  assert.equal(t.metrics.find(m=>m.label==='정식 WID 모델 적합').value,0);
  assert.equal(t.metrics.find(m=>m.label==='원천 승인 구성원-주').value,null);
  assert.equal(t.evidenceClass,'UNVERIFIED_OR_BLOCKED');
});
test('an economic decision criterion is not an observed economic verdict',()=>{
  const t=A.fourTrackProjection({market:{economicExperimentProposal:{economicTolerances:{fixture:'criterion-only'}}}})[2];
  assert.equal(t.economicVerdict,null);assert.equal(t.historicalCagr,null);
});

test('pinned real readout shows all 12 comparisons and KR C2 conflicting horizons without scaling or cost deductions',async()=>{
  const r=await A.loadFourTrackReport(storedReader,VIEWED_AT),p=r.storedPerformance;
  assert.equal(p.status,'READ_ONLY_STORED_RESULTS');assert.equal(p.comparisonCount,12);
  assert.deepEqual(p.groups.map(g=>g.comparisonIds.length),[6,6]);
  const c=p.comparisons.find(c=>c.id==='A/KR/C2-P0');
  assert.deepEqual(c.metrics.slice(2,5).map(m=>m.display),['+1.8181 pp','-0.5193 pp','-0.8804 pp']);
  assert.equal(c.metrics[8].display,'-2.9206 pp');
  assert.equal(c.metrics[0].value,economicDocs().economic.comparisons[1].scopes.FULL.candidate.cagrPct);
  assert.equal(c.candidateInput.costBasis,'NET_ALREADY_CHARGED');
  const html=A.fourTrackMarkup(r);
  assert.equal((html.match(/data-stored-comparison=/g)||[]).length,12);
  for(const m of c.metrics) assert.ok(html.includes(m.display));
  assert.match(html,/전체 CAGR 우위가 모든 달력 6\/12개월 구간의 우위를 뜻하지 않습니다/);
  assert.match(html,/주간 관측 MDD는 일별 MDD가 아니며 H126\/H252는 UNAVAILABLE/);
  assert.match(html,/재차감 없음/);assert.match(html,/원본 생성 시각 UNKNOWN/);
  assert.match(html,/차단된 별도 비교 90개/);assert.equal(r.productionEffect,'NONE');
  assert.deepEqual(r.investmentNominations,[]);
});
test('US stored C2 is KRW with FX, QQQ unavailable, and C1 study IDs cannot become Market C1',async()=>{
  const r=await A.loadFourTrackReport(storedReader,VIEWED_AT),p=r.storedPerformance;
  const c=p.comparisons.find(c=>c.id==='A/US/C2-P0');
  assert.equal(c.candidateInput.currency,'KRW');assert.equal(c.candidateInput.fxReturnsIncluded,true);
  assert.equal(p.qqq.status,'UNAVAILABLE');assert.equal(c.candidateInput.notMarketC1FormalStudy,true);
  const html=A.storedPerformanceMarkup(p,r.sources);
  assert.match(html,/KRW · 환율 포함/);assert.doesNotMatch(html,/USD/);
  assert.match(html,/Market C1 정식 연구와 다릅니다/);
  assert.match(html,/SURVIVORSHIP_BIASED_PARTIAL/);
  assert.equal(p.sourceGeneratedAt,null);
});
test('each missing/corrupt authenticated source isolates UNKNOWN to new section; old KR remains readable',async()=>{
  for(const key of ['economic','economicPins','economicPlan','economicReadme']) {
    for(const corruption of [false,true]) {
      const r=await A.loadFourTrackReport(async(url,s)=>{
        if(s.path===A.RESEARCH_TRACK_SOURCES[key].path) {
          if(corruption) return Buffer.from('{}');
          throw new Error('unavailable');
        }
        return storedReader(url,s);
      },VIEWED_AT);
      assert.equal(r.storedPerformance.status,'UNKNOWN');
      assert.equal(r.sources[key].reason,corruption?'SOURCE_HASH_OR_SIZE_MISMATCH':'SOURCE_READ_FAILED');
      assert.equal(r.tracks[0].reportStatus,'DONE');assert.notEqual(r.tracks[0].metrics[0].value,null);
      assert.deepEqual(r.storedPerformance.comparisons,[]);
      const html=A.fourTrackMarkup(r);
      assert.match(html,/UNKNOWN/);assert.ok(html.includes(r.sources[key].reason));
      assert.doesNotMatch(html,/\+1\.8181/);
    }
  }
});
test('measured zero, explicit null, missing, invalid and unsupported fields retain different reasons',()=>{
  const docs=economicDocs(),before=structuredClone(docs),p=A.storedPerformanceProjection(docs);
  assert.deepEqual(docs,before);
  const zero=p.comparisons.find(c=>c.id==='A/US/P1-P0').metrics[2];
  assert.equal(zero.value,0);assert.equal(zero.status,'MEASURED');assert.equal(zero.display,'0.0000 pp');
  assert.equal(A.storedMetric(null,'null').reason,'NULL_IN_STORED_RESULT');
  assert.equal(A.storedMetric(undefined,'missing').reason,'MISSING_IN_STORED_RESULT');
  for(const v of [NaN,Infinity,false,'0']) assert.equal(A.storedMetric(v,'bad').reason,'INVALID_IN_STORED_RESULT');
  const c=docs.economic.comparisons[1];c.scopes.FULL.cagrGapPp=null;
  delete c.scopes.FULL.windows.CALENDAR_6M.meanExcessReturnPp;
  const changed=A.storedPerformanceProjection(docs).comparisons[1];
  assert.equal(changed.metrics[2].value,null);assert.match(changed.metrics[2].display,/NULL/);
  assert.match(changed.metrics[3].display,/MISSING/);
  assert.match(changed.details.find(d=>d.label==='H126 표본').display,/UNAVAILABLE.*REQUIRES_VERIFIED_COMPLETE_DAILY_SESSION_PATH/);
});
test('actual window maturity and missing endpoint counts are preserved without inventing zeroes or independent trials',()=>{
  const docs=economicDocs(),p=A.storedPerformanceProjection(docs),c=p.comparisons[1];
  const original=docs.economic.comparisons[1].scopes.FULL.windows.CALENDAR_12M;
  assert.deepEqual(c.windowAccounting.find(w=>w.key==='CALENDAR_12M').statusCounts,original.statusCounts);
  assert.deepEqual(original.statusCounts,{MEASURED:662,MATURE_TARGET_NO_STORED_ENDPOINT:7,IMMATURE_AT_AS_OF:46});
  assert.match(c.details.find(d=>d.label==='CALENDAR_12M 표본').display,/IMMATURE_AT_AS_OF=46/);
  assert.match(c.details.find(d=>d.label==='CALENDAR_12M 표본').display,/비중첩 시간 블록 13 \(독립성 증명 아님\)/);
  const html=A.storedPerformanceMarkup(p);
  assert.match(html,/BEYOND_STORED_PATH_MATURITY_UNKNOWN/);assert.match(html,/미성숙/);
});
test('inconsistent contracts/pins fail closed and unknown cost is never certified net',()=>{
  for(const mutate of [
    d=>{d.economic.comparisons.pop()},
    d=>{d.economic.sourcePins.mainCommit='0'.repeat(40)},
    d=>{d.economic.comparisons[1].candidateInput.currency='USD'},
    d=>{d.economic.comparisons[1].candidateInput.hashes.x='1'.repeat(64)},
    d=>{d.economic.comparisons[1].units='FRACTIONS'},
  ]) {
    const d=economicDocs();mutate(d);assert.equal(A.storedPerformanceProjection(d).status,'UNKNOWN');
  }
  const d=economicDocs();d.economic.comparisons[1].candidateInput.costBasis='UNKNOWN';
  const c=A.storedPerformanceProjection(d).comparisons[1];
  assert.match(c.details.find(d=>d.label==='후보 비용 기준').display,/UNKNOWN · 순수익으로 인증하지 않음/);
});
test('source strings in saved-path details cannot inject markup',()=>{
  const d=economicDocs();d.economic.comparisons[1].candidateInput.strategyMeaning='<script>alert(1)</script>';
  const html=A.storedPerformanceMarkup(A.storedPerformanceProjection(d));
  assert.doesNotMatch(html,/<script>/);assert.match(html,/&lt;script&gt;/);
});
