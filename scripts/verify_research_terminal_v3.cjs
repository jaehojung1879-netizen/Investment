/* Rendered verification only. No builds, research replays or ledger writes.
 * NODE_PATH points to an external Playwright installation; TERMINAL_RECEIPT_DIR
 * contains readonly P1 bytes from the documented signal-history commit.
 * Synthetic positive-state inputs stay in /tmp and every screenshot labels them.
 * --live uses the managed proxy and verified TLS to check actual publication.
 */
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const http = require("node:http");
const assert = require("node:assert/strict");
const {execFileSync} = require("node:child_process");
const {webcrypto,createHash} = require("node:crypto");
const {chromium,request} = require("playwright");
globalThis.crypto = webcrypto;
const ROOT = path.resolve(__dirname,"..");
const A = require(path.join(ROOT,"app.js"));
const P1_COMMIT = "6a6b7e753814cc9adf56811ca78abdcaef0d69ea";
const NOW = "2026-10-12T01:00:00Z";
const output = process.env.TERMINAL_VERIFICATION_DIR || path.join(os.tmpdir(),"investment-terminal-v3-verification");
const evidence = process.env.TERMINAL_RECEIPT_DIR;
const sha = b=>createHash("sha256").update(b).digest("hex");
const mime = {".html":"text/html",".css":"text/css",".js":"text/javascript",".json":"application/json"};
const clone = structuredClone;
function fixtures(directory) {
  // Deliberately invented prices/indicators. Never presented as real current data.
  execFileSync(process.env.TERMINAL_PYTHON || "python",["-c",`
import json, sys
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'tests'))
from test_current_champion_decisions import source
from pipeline import current_champion_decisions as C
root=Path(sys.argv[1]); site=source()
site['names']={t:'합성 검증 '+t for t in site['details']}
for r in site['indices']:
    r.update(name='합성 검증 '+r['symbol'],region='KR' if r['symbol']=='^KS11' else 'US',last=107.42,
             chg1dPct=.31,source='SYNTHETIC_BROWSER_FIXTURE',unit='fixture index',digits=2,
             sourceUrl='https://finance.yahoo.com/',history=[
                {'date':(date(2025,10,8)+timedelta(days=i)).isoformat(),'value':100+i*.02+(i%15)*.08}
                for i in range(366)])
site['indices'].append({'symbol':'KRW=X','name':'합성 USD/KRW','region':'FX','last':1350,
    'asOf':'2026-10-08','freshnessStatus':'CURRENT','unit':'KRW/USD','source':'SYNTHETIC_BROWSER_FIXTURE',
    'history':[{'date':'2026-09-01','value':1340},{'date':'2026-10-08','value':1350}]})
history=[{'date':date(y,m,1).isoformat(),'value':2+(y-2016)*.01+m*.01}
         for y in range(2016,2027) for m in range(1,13) if date(y,m,1)<=date(2026,10,1)]
indicator={'name':'Treasury10Y','displayNameKo':'합성 검증 · 미 10년 국채','transformedValue':3.2,
    'latestValue':3.2,'observationDate':'2026-10-01','valueUnit':'%','changeUnit':'pp',
    'transformation':'level','transformationKo':'원천 수준 (합성 검증)','frequency':'monthly_fixture',
    'releaseLagBdays':1,'source':'https://fred.stlouisfed.org/series/DGS10','stale':False,
    'history':history,'trendHistory':[], 'guide':{'meaningKo':'합성 UI 검증 값',
    'readKo':'실제 시장 관측이 아닙니다.','cautionKo':'UI fixture — 최초 발표 빈티지 검증 아님'}}
site['macroRegime']['axes']={'growth':{'ko':'성장','indicators':[indicator]},
    'inflation':{'ko':'물가','indicators':[{**indicator,'name':'HeadlineCPI','displayNameKo':'합성 검증 · CPI'}]},
    'liquidity':{'ko':'유동성','indicators':[]}}
site['macroRegime']['pointInTimeLimitations']='UI fixture; not observed macro vintages'
site['macro']={r:{'indicators':[['합성 검증 기준금리','3.25%','SYNTHETIC_BROWSER_FIXTURE']]} for r in ('KR','US')}
cache=json.loads(Path('data/institutional_13f_cache.json').read_text())
site['institutionalHoldings13F']={'fetchedAt':cache['fetchedAt'],'managers':[
    {**m,'status':'CACHED_OFFICIAL','sourceMode':'CACHED_SEC',
     'cacheFetchedAt':m.get('cacheFetchedAt') or m.get('retrievedAt') or cache['fetchedAt']}
    for m in cache['managers'].values()]}
site['nationalPensionService']={**json.loads(Path('data/national_pension_cache.json').read_text()),
    'status':'CACHED_OFFICIAL','sourceMode':'CACHED_NPS'}
(root/'site.json').write_text(json.dumps(site,ensure_ascii=False))
C.publish(site, 'a'*64, root/'research')
`,directory],{cwd:ROOT,stdio:"pipe"});
}
async function main() {
  assert.ok(evidence,"TERMINAL_RECEIPT_DIR must point to actual readonly receipt bytes");
  fs.mkdirSync(output,{recursive:true});
  const temp=fs.mkdtempSync(path.join(os.tmpdir(),"terminal-v3-fixture-"));
  fixtures(temp);
  const p1=Object.fromEntries(["latest.json","publication-status.json","receipts.jsonl"].map(n=>[n,fs.readFileSync(path.join(evidence,n))]));
  assert.equal((await A.parseReceipts(p1["receipts.jsonl"].toString())).length,2);
  const originalSite=JSON.parse(fs.readFileSync(path.join(temp,"site.json")));
  let site=clone(originalSite), researchAvailable=true;
  const stage=path.join(temp,"pages");fs.mkdirSync(stage);
  for(const n of ["index.html","styles.css","app.js"]) fs.copyFileSync(path.join(ROOT,n),path.join(stage,n));
  const server=http.createServer((req,res)=>{
    const pathname=new URL(req.url,"http://localhost").pathname;
    const file=path.join(stage,pathname==="/"?"index.html":pathname.slice(1));
    if(!file.startsWith(stage+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()) {res.writeHead(404);res.end();return;}
    res.writeHead(200,{"Content-Type":mime[path.extname(file)]||"application/octet-stream"});res.end(fs.readFileSync(file));
  });
  await new Promise(r=>server.listen(0,"127.0.0.1",r));
  const url=`http://127.0.0.1:${server.address().port}/`;
  const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||"/usr/bin/chromium",args:["--no-sandbox"]});
  const report={schema:"RESEARCH_TERMINAL_BROWSER_V31",sourceMain:A.SOURCE_COMMIT,
    p1ReceiptCommit:P1_COMMIT,fixtureObservationTime:NOW,browser:await browser.version(),
    sourceKinds:{currentChampion:"SYNTHETIC_ENGINE_FIXTURE",market:"SYNTHETIC_BROWSER_FIXTURE",macro:"SYNTHETIC_BROWSER_FIXTURE",
      officialP1:"UNCHANGED_PINNED_OFFICIAL_RECEIPTS",institutional13F:"UNCHANGED_PINNED_OFFICIAL_CACHE",nps:"UNCHANGED_PINNED_OFFICIAL_CACHE"},
    frontendSha256:Object.fromEntries(["index.html","styles.css","app.js"].map(n=>[n,sha(fs.readFileSync(path.join(stage,n)))])),
    screenshots:[],viewports:[],checks:[],applicationErrors:[],consoleErrors:[],live:{status:"NOT_RUN"}};
  let transport;
  try {
    const context=await browser.newContext({viewport:{width:1280,height:1000}});
    const requested=[];
    await context.route("**/*",async route=>{
      const u=route.request().url();requested.push(u);
      if(u===url+"data/site-data.json") return route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(site)});
      if(u.startsWith(url)) return route.continue();
      if(u.includes("/git/ref/heads/signal-history")) return route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({object:{sha:P1_COMMIT,type:"commit"}})});
      if(u.includes(`/git/trees/${P1_COMMIT}`)) return route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({truncated:false,tree:researchAvailable?["latest.json","publication-status.json","receipts.jsonl"].map(n=>({type:"blob",path:A.CHAMPION_PATH+n})):[]})});
      const n=u.split("/").pop();
      if(u.includes("/ledger/weekly-decisions/") && Object.hasOwn(p1,n)) return route.fulfill({status:200,body:p1[n],contentType:"application/json"});
      if(u.includes(A.CHAMPION_PATH)) return route.fulfill({status:200,contentType:"application/json",body:fs.readFileSync(path.join(temp,"research",n))});
      const s=Object.values(A.SOURCES).find(s=>u.endsWith(`/${A.SOURCE_COMMIT}/${s.path}`));
      if(s) return route.fulfill({status:200,contentType:"application/json",body:fs.readFileSync(path.join(ROOT,s.path))});
      throw new Error("Unexpected dependency: "+u);
    });
    const p=await context.newPage();
    p.on("pageerror",e=>report.applicationErrors.push(e.message));
    p.on("console",m=>{if(m.type()==="error") report.consoleErrors.push(m.text());});
    await p.clock.setFixedTime(new Date(NOW));
    const settled=()=>p.waitForFunction(()=>document.querySelector("#decisionPanel").getAttribute("aria-busy")==="false" && !document.querySelector("#siteStatus").textContent.includes("확인 중"));
    await p.goto(url);await settled();
    await p.evaluate(()=>{
      const b=document.createElement("div");b.id="verificationBanner";
      b.textContent="브라우저 검증: C1/C2·시장·거시 = 합성 fixture / P1·13F·NPS = 고정 원본. 현재 실자료 검증이 아닙니다.";
      b.style.cssText="position:sticky;top:0;z-index:9999;padding:10px 16px;background:#fff4c4;color:#704c08;font:12px/1.5 sans-serif";
      document.body.prepend(b);
    });
    const screenshot=async(name,target)=>{
      if(target) await p.locator(target).scrollIntoViewIfNeeded();else await p.evaluate(()=>scrollTo({top:0,behavior:"instant"}));
      await p.screenshot({path:path.join(output,name)});report.screenshots.push(name);
    };
    const select=async market=>{await p.locator(`button[data-market="${market}"]`).click();await settled();};
    const overflow=async(label,width)=>{
      const b=await p.evaluate(()=>({page:document.documentElement.scrollWidth,viewport:innerWidth}));
      assert.ok(b.page<=b.viewport,`${label} ${width}: page overflow ${JSON.stringify(b)}`);
      report.viewports.push({label,width,pageOverflowPx:b.page-b.viewport});
    };
    for(const width of [375,390,768,1280]) {
      await p.setViewportSize({width,height:width<600?844:1000});
      for(const market of ["KR","US"]) {
        await select(market);await overflow(market,width);
        assert.equal(await p.locator("main section").count(),6);
        assert.equal(await p.locator("[data-current-state=READY]").count(),2);
        assert.equal(await p.locator("[data-portfolio-state]").getAttribute("data-portfolio-state"),"BENCHMARK_ONLY");
        assert.match(await p.locator("#decisionPanel").innerText(),/SYN_/);
        assert.equal(await p.locator("#watchlistPanel .watch-card").count(),5);
        assert.doesNotMatch(await p.locator("#decisionPanel").innerText(),/영수증|원장|production|artifact|payload|digest|conviction/);
        for(const label of ["판단 기준일","자료 관측","게시 시도","검증 상태"]) assert.ok((await p.locator("#decisionPanel").innerText()).includes(label));
        assert.doesNotMatch(await p.locator("#watchlistPanel").innerText(),/SYN_/);
        if(width===1280) await screenshot(`${market.toLowerCase()}-current-1280.png`);
        if(width===390&&market==="KR") await screenshot("mobile-current-390.png");
      }
    }
    assert.ok(!requested.some(u=>u.includes(A.SOURCES.weekly.path)||u.includes(A.SOURCES.anchors.path)||u.includes(A.SOURCES.qqq.path)),"Current/market/13F must not request historical returns");
    report.checks.push("375/390/768/1280px; independent KR/US; unchanged official P1; real Python-generated C1/C2 fixture digest; no historical performance prefetch");
    await select("KR");
    await p.locator('a[href="#market"]').click();await screenshot("market-charts-1280.png","#marketTitle");
    await p.locator('[data-context-kind="index"]').first().click();
    const counts=[];
    for(const range of ["1M","3M","6M","1Y"]) {
      await p.locator(`[data-context-range="${range}"]`).click();
      counts.push(await p.locator("#contextDialog tbody tr").count());
      assert.equal(await p.locator(`[data-context-range="${range}"]`).getAttribute("aria-pressed"),"true");
    }
    assert.ok(counts.every((x,i)=>!i||x>=counts[i-1]));assert.equal(counts.at(-1),366);
    await screenshot("market-detail-1280.png");await p.locator("#closeDialog").click();
    await p.locator('[data-context-kind="macro"]').first().click();
    const macroCounts=[];
    for(const range of ["1Y","3Y","5Y","10Y"]) {
      await p.locator(`[data-context-range="${range}"]`).click();macroCounts.push(await p.locator("#contextDialog tbody tr").count());
    }
    assert.ok(macroCounts.every((x,i)=>!i||x>macroCounts[i-1]));
    await screenshot("macro-detail-1280.png");
    for(const width of [375,390,768,1280]) {await p.setViewportSize({width,height:844});await overflow("macro dialog",width);}
    await p.locator("#closeDialog").click();await p.setViewportSize({width:1280,height:1000});
    await p.locator('a[href="#institutional"]').click();
    assert.equal(await p.locator("#institutionalPanel .manager-card").count(),7);
    assert.match(await p.locator("#npsPanel").innerText(),/1,848\.7조 원/);
    for(const width of [375,390,768,1280]) {await p.setViewportSize({width,height:width<600?844:1000});await overflow("13F/NPS",width);}
    await screenshot("institutional-13f-1280.png","#institutionalTitle");
    await p.locator('[data-context-kind="manager"]').filter({hasText:"보유"}).nth(1).click();
    assert.match(await p.locator("#contextDialog").innerText(),/2026-06-30/);
    assert.match(await p.locator("#contextDialog").innerText(),/실제 제출 2026-08-/);
    assert.match(await p.locator("#contextDialog").innerText(),/CACHED_OFFICIAL/);
    assert.match(await p.locator("#contextDialog").innerText(),/오늘의 보유내역이 아닙니다/);
    await screenshot("13f-manager-holdings-1280.png");
    await p.setViewportSize({width:390,height:844});await overflow("13F detail",390);await screenshot("mobile-13f-390.png");
    await p.locator("#closeDialog").click();
    report.checks.push("Market 1M/3M/6M/1Y and macro 1Y/3Y/5Y/10Y source-only observation counts; all seven official 13F cache filings; NPS scope separation; mobile dialogs");
    await p.setViewportSize({width:1280,height:1000});
    await p.locator('a[href="#performance"]').click();
    await p.waitForFunction(()=>document.querySelector("#performancePanel").getAttribute("aria-busy")==="false");
    assert.match(await p.locator("#performancePanel").innerText(),/12\.507%/);
    assert.match(await p.locator("#performancePanel").innerText(),/12\.043%/);
    await p.locator('[data-study="anchors"]').click();
    await p.waitForFunction(()=>document.querySelector("#performancePanel").getAttribute("aria-busy")==="false");
    for(const value of ["10.395%","14.258%","+1.752%p"]) assert.ok((await p.locator("#performancePanel").innerText()).includes(value));
    await select("US");
    await p.locator("#performancePanel .etf-context summary").waitFor();
    await p.locator("#performancePanel .etf-context summary").click();
    assert.match(await p.locator("#performancePanel").innerText(),/19\.838%/);
    assert.match(await p.locator("#performancePanel").innerText(),/개별 종목 선택 실적 없음/);
    report.checks.push("Original KR historical statistics/cadences preserved; merged QQQ comparison disclosed separately; US no fabricated stock-selection performance");
    for(const [name,mutate] of [["seed",s=>s.seed=true],["withheld",s=>s.longTerm.weightsWithheld=true],["stale",s=>s.generatedAt="2026-09-01T00:00:00Z"],["missing candidates",s=>s.recommendationsBlocked=true]]) {
      site=clone(originalSite);mutate(site);await p.locator("#refresh").click();await settled();
      assert.equal(await p.locator("[data-current-state=READY]").count(),0,name);
      assert.equal(await p.locator("[data-current-strategy=C1] .holding").count(),0,name);
      assert.equal(await p.locator("[data-portfolio-state]").getAttribute("data-portfolio-state"),"BENCHMARK_ONLY");
    }
    site=clone(originalSite);researchAvailable=false;await p.locator("#refresh").click();await settled();
    assert.equal(await p.locator("[data-current-state=READY]").count(),0);
    assert.equal(await p.locator("[data-current-strategy=C1]").getAttribute("data-publication-state"),"NOT_PUBLISHED");
    assert.match(await p.locator("#decisionPanel").innerText(),/투자 판단 미등록/);
    report.checks.push("Seed/stale/withheld/missing/first-publication absence: C1/C2 unavailable with no phantom positions; P1 stays independent");
    assert.deepEqual(report.applicationErrors,[]);assert.deepEqual(report.consoleErrors,[]);
    await context.close();
    if(process.argv.includes("--live")) {
      transport=await request.newContext({proxy:process.env.HTTPS_PROXY?{server:process.env.HTTPS_PROXY}:undefined,timeout:20000});
      const live=await browser.newContext({viewport:{width:1280,height:1000}});
      const requests=[],errors=[];
      await live.route("**/*",async route=>{
        const u=route.request().url();if(u.startsWith(url)&&u!==url+"data/site-data.json") return route.continue();
        const remote=u===url+"data/site-data.json"?"https://jaehojung1879-netizen.github.io/Investment/data/site-data.json":u;
        try {const response=await transport.get(remote);requests.push({url:remote,status:response.status()});await route.fulfill({response});}
        catch(e) {requests.push({url:remote,status:"TRANSPORT_FAILED",reason:e.message});await route.abort("failed");}
      });
      const page=await live.newPage();page.on("pageerror",e=>errors.push({kind:"application",message:e.message}));
      page.on("console",m=>{if(m.type()==="error")errors.push({kind:"browser",message:m.text()});});
      await page.goto(url);
      await page.waitForFunction(()=>document.querySelector("#decisionPanel").getAttribute("aria-busy")==="false" && document.querySelectorAll(".manager-card").length===7);
      const regions={};
      for(const market of ["KR","US"]) {await page.locator(`button[data-market=${market}]`).click();regions[market]={p1:await page.locator("[data-portfolio-state]").getAttribute("data-portfolio-state"),champion:await page.locator("[data-current-strategy=C1]").getAttribute("data-current-state"),publicationState:await page.locator("[data-current-strategy=C1]").getAttribute("data-publication-state"),text:await page.locator("#decisionPanel").innerText()};}
      for(const width of [390,1280]) {
        await page.setViewportSize({width,height:width<600?844:1000});
        const size=await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth}));
        assert.ok(size.scrollWidth<=size.width);report.viewports.push({label:"actual publication",width,pageOverflowPx:size.scrollWidth-size.width});
        await page.evaluate(()=>scrollTo({top:0,behavior:"instant"}));
        const name=`actual-publication-blockers-${width}.png`;await page.screenshot({path:path.join(output,name)});report.screenshots.push(name);
      }
      report.live={status:"OBSERVED_WITH_SOURCE_LIMITATIONS",observedAt:new Date().toISOString(),tlsVerified:true,managedProxyTransport:true,requests,regions,errors};
      assert.equal(errors.filter(e=>e.kind==="application").length,0);
      await live.close();
    }
    report.status="PASS";
    fs.writeFileSync(path.join(output,"browser-verification.json"),JSON.stringify(report,null,2)+"\n");
    console.log(JSON.stringify({status:report.status,screenshots:report.screenshots.length,viewports:report.viewports.length,applicationErrors:report.applicationErrors.length,consoleErrors:report.consoleErrors.length,live:report.live.status,output}));
  } finally {await transport?.dispose();await browser.close();await new Promise(r=>server.close(r));}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
