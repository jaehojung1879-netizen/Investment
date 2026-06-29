'use strict';
const $ = (s) => document.querySelector(s);
const fmt = (v, suf = '', d) => (v === null || v === undefined || Number.isNaN(v)) ? '—' : `${typeof v === 'number' && d !== undefined ? v.toFixed(d) : v}${suf}`;
const sp = (v) => (v === null || v === undefined || Number.isNaN(v)) ? '—' : `${v >= 0 ? '+' : ''}${v}%`;
const pct0 = (v) => fmt((v ?? 0) * 100, '%', 0);
const regCls = (r) => r === 'Bull' ? 'bull' : r === 'Bear' ? 'bear' : 'trans';
const regKo = (r) => r === 'Bull' ? '상승' : r === 'Bear' ? '하락' : '전환';
const mean = (a) => a.length ? a.reduce((x, y) => x + y, 0) / a.length : null;

let NAMES = {};
let DATA = {};
const tkName = (t) => NAMES[t] || t;
const tkSub = (t) => (NAMES[t] ? ` <span class="tk">${t}</span>` : '');
// Clickable ticker name -> detail popover
const tkLink = (t) => `<span class="tklink" data-tk="${t}">${tkName(t)}</span>${tkSub(t)}`;

// Fear & Greed bands
const fgLabel = (s) => s == null ? '—' : s < 25 ? '극도의 공포' : s < 45 ? '공포' : s < 55 ? '중립' : s < 75 ? '탐욕' : '극도의 탐욕';
const fgCls = (s) => s == null ? 'g-trans' : s < 45 ? 'g-bear' : s < 55 ? 'g-trans' : 'g-bull';

// --- Popover explanations ---
const EXPL = {
  trade: ['오늘의 핵심 액션', '매일 자동 구성되는 국내·국외 유니버스를 트레이드 호라이즌(기본 10영업일)으로 스크리닝해, <b>비용을 넘는 기대값(edge)</b>이 양수이고 확신 하한(확률 0.55)·국면(하락장 제외)을 만족하는 종목만 매수 후보로 올립니다. 후보가 없으면 “관망”이 결론입니다.'],
  core: ['내 포트폴리오', '보유 종목은 호라이즌(21·63·126영업일)마다 LightGBM 상승확률을 계산하고, 확률·국면을 종합해 비중 유지/관망/축소 검토 판정을 냅니다. 신호만 보지 말고 lift·국면과 함께 보세요.'],
  macro: ['매크로', 'FRED에서 국외(미국 10Y·2Y·금리차·기준금리·하이일드 스프레드·VIX)와 국내(원/달러·국고채 10Y·3M·금리차)를 받아 위험 플래그를 띄웁니다. 개별 종목보다 먼저 점검합니다.'],
  sentiment: ['공포 · 탐욕 지수', 'CNN 공포·탐욕 지수처럼 <b>실데이터로 시장 심리</b>를 0~100으로 계산합니다. 유니버스에서 200·50일선 위 비중(breadth), 상승국면 비중, 중앙값 모멘텀에 매크로(VIX·신용스프레드·원화 등)를 더해 극도의 공포(0)~극도의 탐욕(100)으로 표시합니다. 탐욕이 과하면 추격 주의, 공포가 과하면 역발상 기회일 수 있습니다.'],
  prob: ['상승확률', '가격·추세·변동성·상대강도·매크로 피처 약 50개를 LightGBM 분류기에 넣어 해당 호라이즌 뒤 종가가 오를 확률을 추정합니다. walk-forward로 재학습하고 <b>학습에 안 쓴 최근 구간</b>으로 isotonic 보정해 확률을 실제 빈도에 맞춥니다.'],
  edge: ['edge (net)', '<code>edge = p·평균상승 + (1−p)·평균하락 − 비용허들</code>. 확률만으로는 비용을 못 넘기 때문에 기대값이 양수일 때만 제안합니다. 국내(KR)는 세금·수수료로 허들이 더 높습니다.'],
  hold: ['보유(hold-until)', '진입일 + 트레이드 호라이즌(영업일)로 잡은 <b>재평가 시점</b>입니다. 그 전에 무효화 조건(종가 MA20 이탈 또는 다음 확률 0.5 미만)이 오면 먼저 청산합니다.'],
  lift: ['lift', '“항상 상승” 기준선 대비 정밀도의 <b>초과분(%p)</b>. lift가 0에 가까우면 동전던지기와 다를 바 없으니 신뢰도를 낮춰 보세요.'],
  oos: ['OOS 정밀도', '표본 외(학습에 안 쓴 2020년 이후) 구간에서 “상승” 예측이 실제 맞은 비율. 같은 구간 백테스트 vs B&H가 음수면 단순 보유만 못한 신호입니다.'],
};
const pop = $('#pop');
let popKey = null;
const showPop = (key, target) => {
  const e = EXPL[key]; if (!e) return;
  if (popKey === key && !pop.hidden) return hidePop();
  popKey = key; pop.innerHTML = `<b>${e[0]}</b><p>${e[1]}</p>`; pop.hidden = false;
  const r = target.getBoundingClientRect(); const w = Math.min(320, window.innerWidth - 24);
  pop.style.width = w + 'px';
  let left = Math.min(r.left + window.scrollX, window.scrollX + window.innerWidth - w - 12);
  pop.style.left = Math.max(window.scrollX + 12, left) + 'px';
  pop.style.top = (r.bottom + window.scrollY + 6) + 'px';
};
const hidePop = () => { pop.hidden = true; popKey = null; };

const placePop = (target) => {
  const r = target.getBoundingClientRect(); const w = Math.min(340, window.innerWidth - 24);
  pop.style.width = w + 'px';
  let left = Math.min(r.left + window.scrollX, window.scrollX + window.innerWidth - w - 12);
  pop.style.left = Math.max(window.scrollX + 12, left) + 'px';
  pop.style.top = (r.bottom + window.scrollY + 6) + 'px';
};

const showTickerPop = (ticker, target) => {
  const d = DATA.details && DATA.details[ticker];
  if (!d) return;
  const m = (l, v) => `<div><span>${l}</span><b>${v}</b></div>`;
  const grid = [
    m('현재가', fmt(d.lastClose)),
    m('국면', regKo(d.regime)),
    m('10일 상승확률', pct0(d.probUp)),
    m('SMA50/200', `${fmt(d.ma50)} / ${fmt(d.ma200)}`),
    m('RSI(14)', fmt(d.rsi14)),
    m('실현변동성', fmt(d.realizedVol, '%')),
    m('1년 낙폭', fmt(d.maxDrawdown252d, '%')),
    m('상대강도', sp(d.relMomentum)),
    m('60일 모멘텀', sp(d.mom63)),
    m('52주고점 대비', fmt(d.pct52wHigh, '%')),
  ].join('');
  const core = (DATA.core || []).find((c) => c.ticker === ticker);
  const horizons = core ? `<div class="dp-sub">호라이즌별 상승확률</div><div class="dp-h">${core.signals.map((s) => `<span>${s.horizon}D <b>${pct0(s.probUp)}</b></span>`).join('')}</div>` : '';
  const flags = (d.riskFlags && d.riskFlags.length) ? `<div class="dp-flags">${d.riskFlags.map((f) => `<span class="mflag">${f}</span>`).join('')}</div>` : '';
  popKey = 'tk:' + ticker;
  pop.innerHTML = `<div class="dp-head"><b>${tkName(ticker)}</b> <span class="tk">${ticker}</span> <span class="reg ${regCls(d.regime)}">${regKo(d.regime)}</span></div><div class="dp-grid">${grid}</div>${horizons}${flags}`;
  pop.hidden = false; placePop(target);
};

document.addEventListener('click', (e) => {
  const tk = e.target.closest('[data-tk]');
  if (tk) { e.preventDefault(); e.stopPropagation(); if (popKey === 'tk:' + tk.dataset.tk && !pop.hidden) return hidePop(); showTickerPop(tk.dataset.tk, tk); return; }
  const t = e.target.closest('[data-x]');
  if (t) { e.preventDefault(); e.stopPropagation(); showPop(t.dataset.x, t); return; }
  if (!pop.contains(e.target)) hidePop();
});
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') hidePop(); });
window.addEventListener('scroll', hidePop, { passive: true });
const term = (k, l) => `<span class="term" data-x="${k}">${l}</span>`;

// --- Markdown ---
const md2html = (md) => {
  const L = md.split('\n'); let h = '', inUl = false, inT = false;
  const cU = () => { if (inUl) { h += '</ul>'; inUl = false; } };
  const cT = () => { if (inT) { h += '</tbody></table>'; inT = false; } };
  L.forEach((l) => {
    if (l.startsWith('|') && !l.includes('---')) { cU(); const c = l.split('|').slice(1, -1).map((x) => x.trim()); if (!inT) { h += '<table><tbody>'; inT = true; } h += `<tr>${c.map((x) => `<td>${x}</td>`).join('')}</tr>`; return; }
    if (l.startsWith('|') && l.includes('---')) return; cT();
    if (l.startsWith('## ')) { cU(); h += `<h4>${l.slice(3)}</h4>`; }
    else if (l.startsWith('# ')) { cU(); h += `<h3>${l.slice(2)}</h3>`; }
    else if (l.startsWith('- [ ] ')) { if (!inUl) { h += '<ul class="ck">'; inUl = true; } h += `<li class="c">${l.slice(6)}</li>`; }
    else if (l.startsWith('- ')) { if (!inUl) { h += '<ul>'; inUl = true; } h += `<li>${l.slice(2)}</li>`; }
    else if (/^\d+\. /.test(l)) { if (!inUl) { h += '<ul>'; inUl = true; } h += `<li>${l.replace(/^\d+\. /, '')}</li>`; }
    else if (l.trim()) { cU(); h += `<p>${l}</p>`; }
  });
  cU(); cT(); return h.replaceAll('**', '');
};
const loadRules = async () => {
  try { const r = await fetch('docs/investment-philosophy.md', { cache: 'no-store' }); $('#rulesDoc').innerHTML = md2html(await r.text()); }
  catch (e) { $('#rulesDoc').textContent = e.message; }
};

// --- Fear & Greed (hero left) ---
const postureCls = (s) => fgCls(s);
const regBadgeCls = (s) => s == null ? 'trans' : s < 45 ? 'bear' : s < 55 ? 'trans' : 'bull';
const regionLabelKo = { US: '미국', KR: '한국' };
const renderPosture = (sent) => {
  const regs = ['US', 'KR'].map((r) => sent && sent[r]).filter(Boolean);
  const scores = regs.map((r) => r.score).filter((n) => n != null);
  const avg = mean(scores);
  let label = '데이터 없음', read = '';
  if (avg != null) {
    label = fgLabel(avg);
    const detail = regs.map((r) => `${regionLabelKo[r.region]} ${fgLabel(r.score)}(${r.score})`).join(' · ');
    const tail = avg >= 60 ? '탐욕 우위 — 추세 양호하나 추격 과열 주의, 선별 진입.'
      : avg < 45 ? '공포 우위 — 신규 진입 신중, 리스크 관리 우선.'
      : '중립 — 기존 비중 유지, 신규는 고확신만.';
    read = `${detail}. ${tail}`;
  }
  $('#postureLabel').textContent = label;
  const ps = $('#postureScore');
  ps.textContent = avg != null ? Math.round(avg) : '';
  ps.className = 'posture-score reg ' + regBadgeCls(avg);
  const g = $('#postureGauge'); g.className = fgCls(avg); g.style.width = (avg ?? 0) + '%';
  $('#postureRead').textContent = read;
  $('#postureMini').innerHTML = regs.map((r) => `
    <div class="mini">
      <div class="mini-top"><span>${regionLabelKo[r.region]}</span><b>${fgLabel(r.score)} ${r.score}</b></div>
      <div class="gauge"><i class="${fgCls(r.score)}" style="width:${r.score}%"></i></div>
    </div>`).join('');
};

// --- Top picks (hero right) ---
const pickCard = (i, rank) => `
  <article class="pick ${rank === 1 ? 'top' : ''}">
    <span class="rank">#${rank}</span>
    <div class="pick-name"><strong class="tklink" data-tk="${i.ticker}">${tkName(i.ticker)}</strong><span class="reg ${regCls(i.regime)}">${regKo(i.regime)}</span></div>
    <span class="pick-act">${i.region} · 매수 후보</span>
    <div class="pick-conv"><span class="big">${pct0(i.probUp)}</span><span class="lab">${term('prob', '상승확률')}</span></div>
    <div class="pick-meta">
      <span>기대 <b>${sp(i.expMovePct)}</b></span>
      <span data-x="edge">edge <b>${sp(i.edgeNetPct)}</b></span>
      <span>${term('hold', '보유')} <b>~${i.holdUntil}</b></span>
    </div>
    <div class="pick-why">${i.why || ''}</div>
  </article>`;

const renderTopPicks = (d) => {
  const ti = d.tradeIdeas || { KR: [], US: [] };
  const all = [...(ti.KR || []), ...(ti.US || [])].sort((a, b) => (b.edgeNetPct ?? 0) - (a.edgeNetPct ?? 0));
  const top = all.slice(0, 3);
  if (!top.length) {
    $('#topPicks').innerHTML = `<div class="pick-empty"><b>신규 진입 신호 없음 · 관망</b><p class="muted">비용을 넘는 기대값과 확신 하한을 충족하는 종목이 오늘은 없습니다. 무리한 진입보다 대기가 결론입니다.</p></div>`;
    return;
  }
  $('#topPicks').innerHTML = top.map((i, idx) => pickCard(i, idx + 1)).join('');
};

// --- Idea lists ---
const ideaRow = (i) => `
  <div class="idea">
    <div class="idea-top"><strong class="tklink" data-tk="${i.ticker}">${tkName(i.ticker)}</strong>${tkSub(i.ticker)}<span class="reg ${regCls(i.regime)}">${regKo(i.regime)}</span><span class="edge" data-x="edge">edge ${sp(i.edgeNetPct)}</span></div>
    <div class="idea-bar"><i style="width:${Math.round((i.probUp ?? 0) * 100)}%"></i></div>
    <div class="idea-meta"><span>${term('prob', '확률')} <b>${pct0(i.probUp)}</b></span><span>기대 <b>${sp(i.expMovePct)}</b></span><span>${term('hold', '보유')} <b>~${i.holdUntil}</b> (${i.horizon}D)</span></div>
    <div class="idea-why">${i.why || ''}</div>
    <div class="idea-inv">${i.invalidation}</div>
  </div>`;

const renderIdeas = (d) => {
  const ti = d.tradeIdeas || { KR: [], US: [] };
  $('#tradeMeta').textContent = `보유 ${d.tradeHorizon ?? '—'}영업일 기준 · 게이트 통과분만`;
  const fill = (el, arr) => $(el).innerHTML = (arr && arr.length) ? arr.map(ideaRow).join('') : '<div class="none">조건 충족 종목 없음 (관망)</div>';
  fill('#tradeKR', ti.KR); fill('#tradeUS', ti.US);
  const sc = d.screened || [];
  $('#screenCount').textContent = `· ${sc.length}개`;
  $('#screenTable').innerHTML = `<div class="srow sh"><span>종목</span><span>지역</span><span>${term('prob', '확률')}</span><span>국면</span><span>채택</span></div>` +
    sc.map((s) => `<div class="srow"><span>${tkLink(s.ticker)}</span><span>${s.region}</span><span>${pct0(s.probUp)}</span><span class="reg ${regCls(s.regime)}">${regKo(s.regime)}</span><span>${s.qualifies ? '✓' : '·'}</span></div>`).join('');
};

// --- Holdings table ---
const holdingVerdict = (t) => {
  const probs = (t.signals || []).map((s) => s.probUp).filter((n) => n != null);
  const avg = mean(probs); const reg = t.risk?.regime;
  if (reg === 'Bear' || (avg != null && avg < 0.45)) return ['축소 검토', 'sell'];
  if (reg === 'Bull' && avg != null && avg >= 0.6) return ['비중 유지', 'buy'];
  return ['관망', 'hold'];
};
const renderHoldings = (d) => {
  const core = d.core || [];
  const head = `<div class="hrow hh"><span>종목</span><span>현재가</span><span>국면</span><span class="hcol-sig">호라이즌별 상승확률 (21·63·126D)</span><span>판정</span></div>`;
  const rows = core.map((t) => {
    const [vlabel, vcls] = holdingVerdict(t);
    const sigs = (t.signals || []).map((s) => `<div class="h-sig">${s.horizon}D<b>${pct0(s.probUp)}</b><div class="mini-bar"><i style="width:${Math.round((s.probUp ?? 0) * 100)}%"></i></div></div>`).join('');
    return `<div class="hrow">
      <span class="nm tklink" data-tk="${t.ticker}">${tkName(t.ticker)}${tkSub(t.ticker)}</span>
      <span>${fmt(t.lastClose)}</span>
      <span><span class="reg ${regCls(t.risk?.regime)}">${regKo(t.risk?.regime)}</span></span>
      <span class="h-sigs">${sigs || '<span class="muted">데이터 부족</span>'}</span>
      <span class="verdict ${vcls}">${vlabel}</span>
    </div>`;
  }).join('');
  $('#holdingsTable').innerHTML = core.length ? head + rows : '<div class="none">보유 종목 없음</div>';
};

// --- Macro / sentiment panels ---
const stanceBadge = (s) => {
  const m = { Stable: ['안정', 'bull'], Caution: ['주의', 'trans'], 'Risk-off': ['위험회피', 'bear'] };
  const [ko, cls] = m[s] || [s, 'trans']; return `<span class="reg ${cls}">${ko}</span>`;
};
const region = (title, kpis, badge, flags) => `
  <div class="region"><div class="region-h"><h4>${title}</h4>${badge}</div>
    <div class="kpi">${kpis}</div>
    ${flags !== undefined ? `<div class="mflags">${flags || '<span class="muted">경고 없음</span>'}</div>` : ''}
  </div>`;
const kpiItems = (arr) => (arr || []).map(([l, v, n]) => `<div><span>${l}</span><b>${v}</b><em>${n ?? ''}</em></div>`).join('');
const renderMacro = (m) => {
  if (!m || !m.available) { $('#macroPanel').innerHTML = `<div class="none">${m?.note ?? '매크로 비활성'}</div>`; return; }
  $('#macroPanel').innerHTML =
    region('국외 (US)', kpiItems(m.US?.indicators), stanceBadge(m.US?.stance), (m.US?.riskFlags || []).map((f) => `<span class="mflag">${f}</span>`).join('')) +
    region('국내 (KR)', kpiItems(m.KR?.indicators), stanceBadge(m.KR?.stance), (m.KR?.riskFlags || []).map((f) => `<span class="mflag">${f}</span>`).join(''));
};
const sentBadge = (r) => `<span class="reg ${regBadgeCls(r.score)}">${r.fearGreed || r.label} ${r.score}</span>`;
const renderSentiment = (s) => {
  if (!s) { $('#sentimentPanel').innerHTML = '<div class="none">데이터 없음</div>'; return; }
  const one = (title, r) => r ? region(title, kpiItems(r.components), sentBadge(r)) : region(title, '', '');
  $('#sentimentPanel').innerHTML = one('국외 (US)', s.US) + one('국내 (KR)', s.KR);
};

const render = (d) => {
  DATA = d; NAMES = d.names || {};
  $('#portfolioName').textContent = d.portfolioName || 'Investment Insight';
  $('#dataStatus').textContent = `· ${(d.core || []).length} 보유${d.seed ? ' · SEED' : ''}`;
  const m = d.meta || {};
  $('#dataMeta').textContent = [
    m.latestDataDate ? `데이터 ${m.latestDataDate}` : '',
    m.universeScreened ? `유니버스 ${m.universeScreened}` : '',
    m.modelsTrained ? `모델 ${m.modelsTrained}회 학습` : '',
  ].filter(Boolean).join(' · ');
  if (d.generatedAt) $('#dataGenerated').textContent = '생성 ' + new Date(d.generatedAt).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' }) + ' KST';
  const sb = $('#staleBanner');
  if (d.stale) { sb.hidden = false; sb.textContent = `⚠️ 데이터 갱신 실패 — 이전 빌드 결과입니다${m.buildError ? ' (' + m.buildError + ')' : ''}`; } else sb.hidden = true;
  renderPosture(d.sentiment);
  renderTopPicks(d);
  renderIdeas(d);
  renderHoldings(d);
  renderMacro(d.macro);
  renderSentiment(d.sentiment);
};

const loadData = async () => {
  try { const r = await fetch('data/site-data.json', { cache: 'no-store' }); if (!r.ok) throw new Error(`HTTP ${r.status}`); render(await r.json()); }
  catch (e) { $('#dataStatus').textContent = 'data error: ' + e.message; }
};
document.querySelectorAll('.nav a[href^="#"]').forEach((a) => a.addEventListener('click', (e) => {
  const t = document.querySelector(a.getAttribute('href')); if (!t) return; e.preventDefault(); t.scrollIntoView({ behavior: 'smooth', block: 'start' });
}));
loadRules(); loadData();
