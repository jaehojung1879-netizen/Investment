const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
globalThis.crypto = require("node:crypto").webcrypto;
const A = require("../app.js");
const dir = process.env.CHAMPION_FIXTURE;
assert.ok(dir, "Set CHAMPION_FIXTURE to isolated Python-engine fixture outputs");
const raw = fs.readFileSync(path.join(dir,"receipts.jsonl"),"utf8");
const latest = JSON.parse(fs.readFileSync(path.join(dir,"latest.json"),"utf8"));
const publication = JSON.parse(fs.readFileSync(path.join(dir,"publication-status.json"),"utf8"));
const site = JSON.parse(fs.readFileSync(path.join(dir,"site.json"),"utf8"));
const records = raw.trim().split("\n").map(JSON.parse);
const bundle = {latest,publication,receipts:records,commit:"b".repeat(40)};
const now = Date.parse("2026-10-12T01:00:00Z");
const clone = structuredClone;

test("Python and JavaScript agree on real engine receipt bytes, decimals and timestamps", async()=>{
  assert.deepEqual(await A.parseChampionReceipts(raw),records);
  const changed=raw.replace("SYN_KR_0","CHANGED");
  await assert.rejects(A.parseChampionReceipts(changed),/다이제스트/);
  await assert.rejects(A.parseChampionReceipts(raw+raw),/식별자/);
});
test("current C1 and C2 preserve exact engine weights, sector constraints and residual substitution",()=>{
  for(const market of ["KR","US"]){
    const s=A.championState(bundle,market,site,now);
    assert.equal(s.state,"READY"); assert.equal(s.receipt.decisions.C1.stockCount,3);
    assert.notEqual(s.receipt.decisions.C1.holdings[0].weightPct,15);
    const html=A.championMarkup(s,"C1",market)+A.championMarkup(s,"C2",market);
    assert.match(html,/CURRENT SELECTED HOLDINGS/); assert.match(html,/연구 전용 PAPER/);
    assert.match(html,/과거 21세션/); assert.match(html,/원천 artifact/);
    assert.match(html,/conviction/);
  }
});
for(const [label,mutate] of [
  ["reranking",r=>r.decisions.C2.holdings.reverse()],
  ["resizing",r=>r.decisions.C2.stockWeights[r.decisions.C2.holdings[0].ticker]=.15],
  ["wrong residual",r=>{r.decisions.C2.weights.EVIL=r.decisions.C2.weights['069500.KS'];delete r.decisions.C2.weights['069500.KS'];}],
  ["missing total",r=>delete r.decisions.C1.stockWeightPct],
  ["phantom position",r=>r.decisions.C1.holdings.push({ticker:"PHANTOM",weightPct:10})],
  ["historical cadence",r=>r.cadence="21_SESSION_ANCHORS_NOT_WEEKLY"],
  ["live promotion",r=>r.liveValidated=true],
  ["wrong region",r=>r.region="US"],
])test(`invalid ${label} blocks current portfolios`,()=>{
  const r=clone(records.find(r=>r.region==="KR")); mutate(r);
  assert.equal(A.validChampionPair(r,"KR"),false);
});
test("missing, stale, seed, blocked and newer regional sessions never carry prior current positions",()=>{
  for(const change of [s=>s.stale=true,s=>s.dataMode="seed",s=>s.recommendationsBlocked=true,
    s=>s.generatedAt="2026-09-01T00:00:00Z",s=>s.indices[0].asOf="2026-10-12"]){
    const s=clone(site);change(s);const state=A.championState(bundle,"KR",s,now);
    assert.equal(state.state,"BLOCKED");assert.doesNotMatch(A.championMarkup(state,"C1","KR"),/SYN_KR_|stockWeights/);
  }
  assert.equal(A.championState(null,"KR",site,now).state,"BLOCKED");
});
test("current regional session gating is independent",()=>{
  const s=clone(site);s.indices[0].asOf="2026-10-12";
  assert.equal(A.championState(bundle,"KR",s,now).state,"BLOCKED");
  assert.equal(A.championState(bundle,"US",s,now).state,"READY");
});
test("missing current regional candidates block C1/C2 without affecting the other region",()=>{
  const s=clone(site);delete s.longTerm.regions.US;
  assert.equal(A.championState(bundle,"US",s,now).state,"BLOCKED");
  assert.equal(A.championState(bundle,"KR",s,now).state,"READY");
});
test("market cards show sourced dates/units and never infer a missing quote from history",()=>{
  const s={dataMode:"live",indices:[{symbol:"^KS11",name:"코스피",region:"KR",last:null,asOf:"2026-10-08",freshnessStatus:"STALE",source:"Recorded source",history:[{date:"2026-10-07",value:100},{date:"2026-10-08",value:101}]},{symbol:"^GSPC",region:"US",last:700}]};
  const html=A.marketMarkup(s,"KR");assert.match(html,/2026-10-08/);assert.match(html,/STALE/);
  assert.match(html,/class="asset-quote">—/);assert.doesNotMatch(html,/GSPC/);
  assert.doesNotMatch(A.marketMarkup({...s,dataMode:"synthetic"},"KR"),/<svg/);
  assert.equal(A.observations([{date:"2026-10-01",value:null},{date:"2026-10-02",value:0}]).length,1);
});
test("market and macro ranges slice only source observations without adding endpoints",()=>{
  const points=[];for(let y=2015;y<=2026;y++)for(let m=1;m<=12;m++)points.push({date:`${y}-${String(m).padStart(2,"0")}-01`,value:y+m});
  for(const range of ["1Y","3Y","5Y","10Y"]){const p=A.rangePoints(points,range,true);assert.ok(p.every(r=>points.includes(r)));}
  assert.ok(A.rangePoints(points,"1Y",true).length<A.rangePoints(points,"10Y",true).length);
  const html=A.chartDetail({name:"CPI",displayNameKo:"소비자물가",valueUnit:"%",transformation:"year_on_year",history:points,frequency:"monthly",source:"https://fred.stlouisfed.org/series/CPIAUCSL",observationDate:"2026-12-01"},"macro","3Y");
  for(const range of ["1Y","3Y","5Y","10Y"])assert.ok(html.includes(`data-context-range="${range}"`));
  assert.match(html,/monthly/);assert.match(html,/year_on_year/);
  assert.doesNotMatch(A.chartDetail({name:"NO_HISTORY",transformedValue:4,history:[]},"macro","1Y"),/<svg/);
});
test("cached official 13F covers all seven original managers with actual reporting/filing dates",()=>{
  const cache=JSON.parse(fs.readFileSync(path.join(__dirname,"../data/institutional_13f_cache.json")));
  const block=A.cachedInstitutions(cache),html=A.institutionalMarkup(block);
  assert.equal(block.managers.length,7);
  for(const manager of block.managers){
    assert.match(html,new RegExp(manager.name.replace(/[.*+?^${}()|[\]\\]/g,"\\$&")));
    const detail=A.managerDetail(manager);assert.ok(detail.includes(manager.reportDate));assert.ok(detail.includes(manager.filingDate));
    assert.ok(detail.includes(manager.cik));assert.match(detail,/오늘의 보유내역이 아닙니다/);assert.match(detail,/주식 수 변화/);
    assert.match(detail,/CACHED_OFFICIAL/);
  }
  assert.match(html,/2026-08-15/);
});
test("NPS fund allocation is separate from NPS 13F and preserves original date/units/rounding",()=>{
  const source=JSON.parse(fs.readFileSync(path.join(__dirname,"../data/national_pension_cache.json")));
  const html=A.npsMarkup(A.cachedNps(source));assert.match(html,/국민연금 전체 기금/);assert.match(html,/13F/);
  assert.match(html,/조 원/);assert.match(html,/2026년 5월 말/);assert.match(html,/CACHED_OFFICIAL/);
  assert.match(html,/29\.4%/);assert.match(html,/35\.2%/);
});
test("missing official cache values remain unavailable and are never promoted to cached holdings",()=>{
  const cache={fetchedAt:"2026-08-15",managers:{missing:{id:"missing",status:"UNAVAILABLE",reportDate:"2026-06-30"}}};
  const block=A.cachedInstitutions(cache);assert.equal(block.managers[0].status,"UNAVAILABLE");
  assert.doesNotMatch(A.institutionalMarkup(block),/USD 0|data-context-kind="manager"/);
  assert.match(A.npsMarkup(A.cachedNps({status:"UNAVAILABLE",asOf:"2026-05-31"})),/미보고/);
});
test("untrusted strings and external filing links cannot execute",()=>{
  const x={name:'<img src=x onerror=alert(1)>',id:'" onmouseover="alert(1)',cik:"0000000001",status:"AVAILABLE",topHoldings:[],filingUrl:"javascript:alert(1)"};
  const html=A.institutionalMarkup({managers:[x]})+A.managerDetail(x);
  assert.doesNotMatch(html,/<img|href="javascript:| onmouseover="/);
  assert.doesNotMatch(A.safeSourceLink("https://evil.example/filing","SEC",["www.sec.gov"]),/href=/);
  assert.doesNotMatch(A.safeSourceLink("https://www.sec.gov@evil.example/","SEC",["www.sec.gov"]),/href=/);
});
test("QQQ remains a separate sourced passive research comparison; official benchmark stays SPY",()=>{
  const report=JSON.parse(fs.readFileSync(path.join(__dirname,"../docs/us-readiness/us-spy-qqq-comparison-v1.json")));
  const html=A.qqqMarkup(report);assert.match(html,/공식 기준과 현재 잔여 ETF는 SPY/);assert.match(html,/외부 총수익/);
  assert.match(html,/19\.838%/);assert.match(html,/14\.740%/);
});
