const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
globalThis.crypto=require('node:crypto').webcrypto;
const A=require('../app.js'),dir=process.env.CHAMPION_FIXTURE;
const site=JSON.parse(fs.readFileSync(path.join(dir,'site.json')));
const receipts=fs.readFileSync(path.join(dir,'receipts.jsonl'),'utf8').trim().split('\n').map(JSON.parse);
const bundle={receipts,latest:JSON.parse(fs.readFileSync(path.join(dir,'latest.json'))),publication:JSON.parse(fs.readFileSync(path.join(dir,'publication-status.json'))),commit:'a'.repeat(40)};
const now=Date.parse('2026-10-12T01:00:00Z');

test('Korean display translation leaves signed source values unchanged',()=>{
  const original=structuredClone(bundle);
  for(const m of ['KR','US']) for(const strategy of ['C1','C2']) {
    const html=A.championMarkup(A.championState(bundle,m,site,now),strategy,m);
    assert.doesNotMatch(html,/영수증|원장|production|artifact|payload|conviction/);
    for(const word of ['판단 기준일','자료 관측','게시 시도','검증 상태','연구 전용','미선정','기록 무결성 검증값']) assert.ok(html.includes(word),word);
    assert.ok(html.includes(bundle.receipts.find(r=>r.region===m).digest));
    assert.match(html,/게시 시도<\/dt><dd>미확인/,'Observation time must not impersonate an unrecorded publication time');
  }
  assert.deepEqual(bundle,original);
});
test('missing publication, transport failure, rejected publication and integrity failure stay distinct',()=>{
  for(const [code,label] of [['NOT_PUBLISHED','투자 판단 미등록'],['FETCH_FAILED','게시 조회 실패'],['INTEGRITY_FAILED','데이터 검증 실패'],['INCOMPLETE_PUBLICATION','게시 자료 누락']]) {
    const state=A.championState(null,'KR',null,now,{code});
    assert.equal(state.publicationState,code);
    const html=A.championMarkup(state,'C1','KR');assert.ok(html.includes(label));
    assert.doesNotMatch(html,/class="holding|SYN_|100<small|2026-10-08/);
  }
  assert.equal(A.championState({...bundle,publication:{status:'REFUSED'}},'KR',site,now).publicationState,'PUBLICATION_REFUSED');
  assert.equal(A.championState(bundle,'KR',null,now).publicationState,'INPUT_UNVERIFIED');
});
test('published zero-stock decisions show zero only from a verified record',()=>{
  const r=structuredClone(bundle.receipts.find(r=>r.region==='KR'));
  for(const d of Object.values(r.decisions)) {d.holdings=[];d.stockCount=0;d.stockWeights={};d.stockWeightPct=0;d.residualWeightPct=100;d.weights={[d.residualAsset]:1};d.status='NO_ELIGIBLE_STOCKS';}
  assert.equal(A.validChampionPair(r,'KR'),true);
  const html=A.championMarkup({state:'READY',receipt:r,freshness:{observedSession:r.asOfDate}},'C1','KR');
  assert.match(html,/편입 조건을 충족한 개별 종목이 없습니다/);assert.match(html,/100\.00%/);
});
test('loader verifies complete tree before declaring not published; refusal-only records are visible',async()=>{
  const original=globalThis.fetch;
  const reply=value=>({ok:true,arrayBuffer:async()=>Buffer.from(JSON.stringify(value))});
  try {
    globalThis.fetch=async()=>reply({truncated:false,tree:[]});
    await assert.rejects(A.loadResearchPublication('a'.repeat(40)),e=>e.code==='NOT_PUBLISHED');
    globalThis.fetch=async()=>reply({truncated:true,tree:[]});
    await assert.rejects(A.loadResearchPublication('a'.repeat(40)),e=>e.code!=='NOT_PUBLISHED');
    globalThis.fetch=async url=>reply(url.includes('git/trees')?{truncated:false,tree:[{type:'blob',path:A.CHAMPION_PATH+'publication-status.json'}]}:{status:'REFUSED'});
    globalThis.fetch=async url=>reply(url.includes('git/trees')?{truncated:false,tree:[{type:'blob',path:A.CHAMPION_PATH+'latest.json'}]}:{});
    await assert.rejects(A.loadResearchPublication('a'.repeat(40)),e=>e.code==='INCOMPLETE_PUBLICATION');
    globalThis.fetch=async url=>reply(url.includes('git/trees')?{truncated:false,tree:[{type:'blob',path:A.CHAMPION_PATH+'publication-status.json'}]}:{status:'REFUSED'});
    const refused=await A.loadResearchPublication('a'.repeat(40));assert.equal(refused.publication.status,'REFUSED');
  } finally {globalThis.fetch=original;}
});
test('presentation and read-only audit do not alter scientific or publication code',()=>{
  const {execFileSync}=require('node:child_process');
  const {createHash}=require('node:crypto');
  // Explicit owner session-safety fix; only these two replacement bytes change.
  const safety=JSON.parse(fs.readFileSync(path.join(__dirname,'../docs/weekly-session-integrity-v1-pins.json')));
  assert.deepEqual(Object.keys(safety.files).sort(),['pipeline/weekly_decision.py','pipeline/weekly_publish.py']);
  for(const file of ['pipeline/current_champion_decisions.py','pipeline/kelly_portfolio.py','pipeline/weekly_decision.py','pipeline/weekly_publish.py','config.json','.github/workflows/tests.yml','.github/workflows/pages.yml','.github/workflows/ledger.yml']) {
    if(safety.files[file]) {
      assert.equal(createHash('sha256').update(fs.readFileSync(path.join(__dirname,'..',file))).digest('hex'),safety.files[file]);
      continue;
    }
    assert.deepEqual(fs.readFileSync(path.join(__dirname,'..',file)),execFileSync('git',['show',`${A.SOURCE_COMMIT}:${file}`]));
  }
  const audit=fs.readFileSync(path.join(__dirname,'../scripts/audit_research_terminal_publication.cjs'),'utf8');
  assert.doesNotMatch(audit,/writeFile|appendFile|execFile|spawn|fetch\(|load_market_values|forward_return|pipeline\//);
});
test('read-only audit verifies Git blob bytes and rejects mismatched or truncated input',async()=>{
  const os=require('node:os'),{createHash}=require('node:crypto');
  const {audit}=require('../scripts/audit_research_terminal_publication.cjs');
  const input=fs.mkdtempSync(path.join(os.tmpdir(),'terminal-v31-audit-synthetic-'));
  const commit='a'.repeat(40),treeSha='b'.repeat(40),tree={sha:treeSha,truncated:false,tree:[]};
  try {
    fs.writeFileSync(path.join(input,'commit.json'),JSON.stringify({sha:commit,commit:{tree:{sha:treeSha}}}));
    const raw=JSON.stringify({receiptId:'SYN_AUDIT',digest:await A.sha256(A.canonicalReceiptLine('{"receiptId":"SYN_AUDIT"}'))})+'\n';
    for(const [name,local,bytes] of [['latest.json','p1-latest.json','{}'],['publication-status.json','p1-publication.json','{}'],['receipts.jsonl','p1-receipts.jsonl',raw]]) {
      const buffer=Buffer.from(bytes);fs.writeFileSync(path.join(input,local),buffer);
      tree.tree.push({type:'blob',path:'ledger/weekly-decisions/'+name,sha:createHash('sha1').update(Buffer.concat([Buffer.from(`blob ${buffer.length}\0`),buffer])).digest('hex')});
    }
    const treeFile=path.join(input,'tree.json');fs.writeFileSync(treeFile,JSON.stringify(tree));
    const before=fs.readFileSync(path.join(input,'p1-receipts.jsonl'));
    const r=await audit(input,commit,A.SOURCE_COMMIT,now);assert.equal(r.research.status,'NOT_PUBLISHED');assert.equal(r.p1.digestVerifiedRecords,1);
    assert.deepEqual(fs.readFileSync(path.join(input,'p1-receipts.jsonl')),before);
    fs.appendFileSync(path.join(input,'p1-receipts.jsonl'),' ');await assert.rejects(audit(input,commit,A.SOURCE_COMMIT,now),/Git blob mismatch/);
    tree.truncated=true;fs.writeFileSync(treeFile,JSON.stringify(tree));await assert.rejects(audit(input,commit,A.SOURCE_COMMIT,now),/Incomplete/);
  } finally {fs.rmSync(input,{recursive:true,force:true});}
});

test('regional operational reason codes stay in expandable evidence',()=>{
  const b=structuredClone(bundle);b.latest.regions.KR.status='BLOCKED';b.latest.regions.KR.reasonCodes=['CONFLICTING_SAME_SESSION_INPUT'];
  const state=A.championState(b,'KR',site,now),html=A.championMarkup(state,'C1','KR');
  assert.equal(state.publicationState,'REGIONAL_BLOCKED');
  assert.match(html,/판단 생성 차단/);assert.doesNotMatch(html.split('<details>')[0],/CONFLICTING_SAME_SESSION_INPUT/);
  assert.match(html.split('<details>')[1],/CONFLICTING_SAME_SESSION_INPUT/);assert.doesNotMatch(html,/class="holding|SYN_/);
});


test('C2 archived research is shown separately from a blocked CURRENT observation',()=>{
  const b=structuredClone(bundle);
  b.latest.regions.KR.status='BLOCKED';
  b.latest.regions.KR.reasonCodes=['CONFLICTING_SAME_SESSION_INPUT'];
  const current=A.championState(b,'KR',site,now);
  assert.equal(current.state,'BLOCKED');
  assert.doesNotMatch(A.championMarkup(current,'C2','KR'),/class="holding"/);
  const archive=A.archivedChampionSnapshot(b,'KR',now);
  assert.equal(archive.state,'PAST_RESEARCH_RECEIPT');
  assert.equal(archive.receipt.asOfDate, b.receipts.find(r=>r.region==='KR').asOfDate);
  const html=A.archivedChampionMarkup(archive,'KR');
  assert.match(html,/과거.*CHAMPION/);
  assert.match(html,/현재 판단이나 매수 추천이 아닙니다/);
  assert.match(html,/data-research-role="PAST_RECORD_ONLY"/);
  assert.match(html,/잔여 지수/);
  assert.match(html,/기록 해시/);
  const positions=archive.receipt.decisions.C2;
  assert.equal(Object.values(positions.weights).reduce((sum,x)=>sum+x,0),1);
  for(const hold of positions.holdings) {
    assert.ok(html.includes(hold.ticker));
    assert.ok(html.includes(A.fmt(hold.weightPct,2).split('.')[0]));
  }
  assert.ok(html.includes(archive.receipt.asOfDate));
  assert.ok(!A.championMarkup(current,'C2','KR').includes(archive.receipt.asOfDate));
});

test('archived C2 refuses missing, refused, future and semantically forged history',()=>{
  assert.equal(A.archivedChampionSnapshot(null,'KR',now),null);
  assert.equal(A.archivedChampionSnapshot({...bundle,publication:{status:'REFUSED'}},'KR',now),null);
  assert.equal(A.archivedChampionSnapshot({...bundle,commit:'main'},'KR',now),null);
  const invalid=structuredClone(bundle);
  invalid.receipts.find(r=>r.region==='KR').decisions.C2.stockWeights={};
  assert.equal(A.archivedChampionSnapshot(invalid,'KR',now),null);
  const future=structuredClone(bundle);
  future.receipts.find(r=>r.region==='KR').generatedAt='2030-01-01T00:00:00Z';
  assert.equal(A.archivedChampionSnapshot(future,'KR',now),null);
  const missing=structuredClone(bundle);
  missing.receipts=missing.receipts.filter(r=>r.region!=='KR');
  assert.equal(A.archivedChampionSnapshot(missing,'KR',now),null);
  assert.doesNotMatch(A.archivedChampionMarkup(null,'KR'),/class="holding"/);
});

test('archived C2 escapes names and cannot turn a recorded paper receipt into approval',()=>{
  const b=structuredClone(bundle),r=b.receipts.find(x=>x.region==='KR');
  r.decisions.C1.holdings[0].name='<svg onload=alert(1)>';
  r.decisions.C2.holdings[0].name='<svg onload=alert(1)>';
  const result=A.archivedChampionSnapshot(b,'KR',now);
  assert.equal(result.state,'PAST_RESEARCH_RECEIPT');
  const html=A.archivedChampionMarkup(result,'KR');
  assert.doesNotMatch(html,/<svg onload/);
  assert.match(html,/&lt;svg/);
  assert.doesNotMatch(html,/data-current-state="READY"/);
  assert.match(html,/21거래일/);
  assert.match(html,/현재 판단이나 매수 추천이 아닙니다/);
});
