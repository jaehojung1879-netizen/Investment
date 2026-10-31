'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
if (!globalThis.crypto) Object.defineProperty(globalThis,'crypto',{value:require('node:crypto').webcrypto});
const A=require('../app.js');

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
