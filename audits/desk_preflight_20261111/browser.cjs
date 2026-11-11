// Local browser integration only. Network responses replay exact pinned Git blobs.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const assert = require('node:assert/strict');
const target = process.env.AUDIT_TARGET;
const output = process.env.AUDIT_OUTPUT || '/tmp/desk-browser';
fs.mkdirSync(output, {recursive:true});
const pin = process.env.PUBLICATION_PIN || '6398e94feddd4f552910d31b36bc8db0766576af';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH || '/usr/bin/chromium',args:['--no-sandbox']});
 const page=await browser.newPage();
 await page.clock.setFixedTime(new Date(process.env.FIXED_TIME || '2026-11-11T13:00:00Z'));
 const errors=[]; page.on('pageerror',e=>errors.push(e.message));
 await page.route('https://**/*',async route=>{
  const u=new URL(route.request().url());
  if(u.hostname==='api.github.com'&&u.pathname.endsWith('/git/ref/heads/signal-history'))
    return route.fulfill({json:{object:{type:'commit',sha:pin}}});
  if(u.hostname==='api.github.com'&&u.pathname.includes('/git/trees/')) {
    const raw=execFileSync('git',['ls-tree','-r',pin,'--','ledger/research-strategies/current-champion-decisions-v1/'],{cwd:target}).toString();
    const tree=raw.trim().split('\n').filter(Boolean).map(line=>{
      const [meta,file]=line.split('\t'),[mode,type,sha]=meta.split(' ');return {mode,type,sha,path:file};
    });
    return route.fulfill({json:{sha:pin,truncated:false,tree}});
  }
  if(u.hostname==='raw.githubusercontent.com'&&u.pathname.startsWith('/jaehojung1879-netizen/Investment/')){
    const parts=u.pathname.split('/'); const sha=parts[3], file=parts.slice(4).join('/');
    try {const body=execFileSync('git',['show',`${sha}:${file}`],{cwd:target,maxBuffer:32*1024*1024,stdio:['ignore','pipe','pipe']});
      return route.fulfill({body,contentType:file.endsWith('.json')?'application/json':'text/plain'});
    } catch {console.error('Unavailable fixture',sha,file);return route.fulfill({status:404,body:'Unavailable pinned fixture'});}
  }
  return route.abort();
 });
 await page.goto('http://127.0.0.1:8765/');
 if(process.env.CHECK_LEGACY==='1') {
  await page.waitForFunction(()=>document.querySelector('#decisionPanel')?.innerText.includes('KODEX 200 100%')).catch(async e=>{
   fs.writeFileSync(path.join(output,'legacy-failure.txt'),await page.locator('#decisionPanel').innerText());throw e;
  });
  assert((await page.locator('#decisionPanel').innerText()).includes('100%'));
 }
 await page.locator('[data-load-desk]').click();
 await page.waitForSelector('[data-desk-production="KR"]');
 for(const width of [1280,390]){
  await page.setViewportSize({width,height:900});
  for(const market of ['KR','US']){
   await page.locator(`button[data-market="${market}"]`).click();
   await page.waitForSelector(`[data-desk-production="${market}"]`);
   await page.locator('#deskPanel details').evaluateAll(ds=>ds.forEach(d=>d.open=true));
   if(process.env.CHECK_LEGACY==='1') {
    const legacy=await page.locator('#decisionPanel').innerText();
    fs.writeFileSync(path.join(output,`legacy-${market}.txt`),legacy);
    assert(legacy.includes(market==='KR'?'KODEX 200 100%':'SPDR S&P 500 ETF 100%'));
   }
   const text=await page.locator('#deskPanel').innerText();
   assert(text.includes('PIT 오염 — 주 비교 제외'));
   const pickLabel=text.includes('AI 실험 기록 비중')?'TRV · AI 실험 기록 비중 10%':'TRV · 연구 비중 10%';
   assert(text.includes(market==='KR'?'069500.KS 100%':pickLabel));
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   await page.screenshot({path:path.join(output,`${market}-${width}.png`),fullPage:true});
  }
 }
 assert.equal(errors.length,0,JSON.stringify(errors));
 console.log(JSON.stringify({status:'PASS',viewports:[1280,390],regions:['KR','US'],pageErrors:errors,
   limitation:'Local browser with pinned Git response replay; not production Pages deployment.'}));
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
