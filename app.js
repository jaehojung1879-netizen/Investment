'use strict';
const $ = (s) => document.querySelector(s);
const fmt = (v, suf = '', d) => (v === null || v === undefined || Number.isNaN(v)) ? '—' : `${typeof v === 'number' && d !== undefined ? v.toFixed(d) : v}${suf}`;
const sp = (v) => (v === null || v === undefined || Number.isNaN(v)) ? '—' : `${v >= 0 ? '+' : ''}${v}%`;
const pct0 = (v) => fmt((v ?? 0) * 100, '%', 0);
const alertCls = (a) => a === 'STRONG BUY' ? 'buy' : a === 'STRONG SELL' ? 'sell' : 'hold';
const alertKo = (a) => a === 'STRONG BUY' ? '강한 매수' : a === 'STRONG SELL' ? '강한 매도' : '관망';
const regCls = (r) => r === 'Bull' ? 'bull' : r === 'Bear' ? 'bear' : 'trans';
const regKo = (r) => r === 'Bull' ? '상승' : r === 'Bear' ? '하락' : '전환';

let NAMES = {};
// Display label: company name (if mapped) with the ticker as secondary.
const tkName = (t) => NAMES[t] || t;
const tkSub = (t) => (NAMES[t] ? `<small class="tk">${t}</small>` : '');

// --- Markdown (headings, lists, checklist, tables, bold) ---
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

// --- Trade ideas ---
const ideaRow = (i) => `
  <div class="idea">
    <div class="idea-top">
      <strong>${tkName(i.ticker)}</strong>${tkSub(i.ticker)}
      <span class="reg ${regCls(i.regime)}">${regKo(i.regime)}</span>
      <span class="edge">edge ${sp(i.edgeNetPct)}</span>
    </div>
    <div class="idea-bar"><i style="width:${Math.round((i.probUp ?? 0) * 100)}%"></i></div>
    <div class="idea-meta">
      <span>확률 <b>${pct0(i.probUp)}</b></span>
      <span>기대 <b>${sp(i.expMovePct)}</b></span>
      <span>보유 <b>~${i.holdUntil}</b> (${i.horizon}D)</span>
    </div>
    <div class="idea-inv muted">${i.invalidation}</div>
  </div>`;

const renderTrade = (d) => {
  const ti = d.tradeIdeas || { KR: [], US: [] };
  $('#tradeMeta').textContent = `보유 ${d.tradeHorizon ?? '—'}영업일 기준 · 비용·확신 게이트 통과분만`;
  const fill = (el, arr) => $(el).innerHTML = (arr && arr.length) ? arr.map(ideaRow).join('') : '<div class="none muted">조건 충족 종목 없음 (관망)</div>';
  fill('#tradeKR', ti.KR); fill('#tradeUS', ti.US);
  const sc = d.screened || [];
  $('#screenTable').innerHTML = `<div class="srow sh"><span>종목</span><span>지역</span><span>확률</span><span>국면</span><span>채택</span></div>` +
    sc.map((s) => `<div class="srow"><span>${tkName(s.ticker)}</span><span>${s.region}</span><span>${pct0(s.probUp)}</span><span class="reg ${regCls(s.regime)}">${regKo(s.regime)}</span><span>${s.qualifies ? '✓' : '·'}</span></div>`).join('');
};

// --- Core holdings ---
const coreCard = (t) => {
  const rows = (t.signals || []).map((s) => {
    const o = s.oos || {}, b = s.backtest || {};
    const lc = o.lift > 0 ? 'pos' : o.lift < 0 ? 'neg' : '';
    return `<div class="cs">
      <div class="cs-l"><span class="hz">${s.horizon}D</span><span class="badge ${alertCls(s.alert)}">${alertKo(s.alert)}</span></div>
      <div class="cs-bar"><i style="width:${Math.round((s.probUp ?? 0) * 100)}%"></i></div>
      <div class="cs-p">${pct0(s.probUp)}</div>
      <div class="cs-m muted">정밀 ${pct0(o.precision)} <em class="${lc}">(${sp(o.lift)})</em> · 연 ${sp(b.annualReturn)} · vsB&H ${sp(b.vsBuyHold)}</div>
    </div>`;
  }).join('');
  return `<article class="cc">
    <header><strong>${tkName(t.ticker)}</strong>${tkSub(t.ticker)}<span class="reg ${regCls(t.risk?.regime)}">${regKo(t.risk?.regime)}</span><span class="price">${fmt(t.lastClose)}</span></header>
    ${rows || '<p class="none muted">데이터 부족</p>'}
  </article>`;
};

// --- Macro (two regions: US / KR) ---
const stanceBadge = (stance) => {
  const map = { Stable: ['안정', 'bull'], Caution: ['주의', 'trans'], 'Risk-off': ['위험회피', 'bear'] };
  const [ko, cls] = map[stance] || [stance, 'trans'];
  return `<span class="reg ${cls}">${ko}</span>`;
};
const macroRegion = (title, r) => {
  if (!r) return '';
  const kpis = (r.indicators || []).map(([l, v, n]) => `<div><span>${l}</span><b>${v}</b><em>${n ?? ''}</em></div>`).join('');
  const flags = (r.riskFlags || []).map((f) => `<span class="mflag">${f}</span>`).join('');
  return `<div class="macro-region">
    <div class="macro-region-head"><h3>${title}</h3>${stanceBadge(r.stance)}</div>
    <div class="kpi">${kpis}</div>
    <div class="mflags">${flags || '<span class="muted">경고 없음</span>'}</div>
  </div>`;
};
const renderMacro = (m) => {
  if (!m || !m.available) { $('#macroPanel').innerHTML = `<div class="none muted">${m?.note ?? '매크로 비활성'}</div>`; return; }
  $('#macroPanel').innerHTML = macroRegion('국외 (US)', m.US) + macroRegion('국내 (KR)', m.KR);
};

// --- Risk / regime ---
const riskCard = (t) => {
  const r = t.risk || {};
  const flags = (r.riskFlags || []).map((f) => `<li>${f.message}</li>`).join('');
  const m = [['SMA50/200', `${fmt(r.ma50)}/${fmt(r.ma200)}`], ['변동성', fmt(r.realizedVol, '%')], ['RSI', fmt(r.rsi14)], ['1Y낙폭', fmt(r.maxDrawdown252d, '%')], ['상대강도', sp(r.relMomentum)], ['52H대비', fmt(r.pct52wHigh, '%')]];
  return `<article class="rc">
    <header><strong>${tkName(t.ticker)}</strong>${tkSub(t.ticker)}<span class="reg ${regCls(r.regime)}">${regKo(r.regime)}</span></header>
    <div class="rm">${m.map(([l, v]) => `<div><span>${l}</span><b>${v}</b></div>`).join('')}</div>
    <ul class="rf ${flags ? '' : 'clean'}">${flags || '<li>플래그 없음</li>'}</ul>
  </article>`;
};

const render = (d) => {
  NAMES = d.names || {};
  $('#portfolioName').textContent = d.portfolioName || 'Investment Insight';
  const seedTag = d.seed ? ' · SEED' : '';
  $('#dataStatus').textContent = `${(d.core || []).length} 보유 · primary ${d.primary || '—'}${seedTag}`;
  if (d.generatedAt) $('#dataGenerated').textContent = new Date(d.generatedAt).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' }) + ' KST';
  $('#dataSource').textContent = d.dataSource || '';
  renderTrade(d);
  $('#coreCards').innerHTML = (d.core || []).map(coreCard).join('') || '<p class="none muted">보유 종목 없음</p>';
  renderMacro(d.macro);
  $('#riskGrid').innerHTML = (d.core || []).map(riskCard).join('') || '<p class="none muted">데이터 없음</p>';
};

const loadData = async () => {
  try { const r = await fetch('data/site-data.json', { cache: 'no-store' }); if (!r.ok) throw new Error(`HTTP ${r.status}`); render(await r.json()); }
  catch (e) { $('#dataStatus').textContent = 'data error: ' + e.message; }
};

document.querySelectorAll('a[href^="#"]').forEach((a) => a.addEventListener('click', (e) => {
  const t = document.querySelector(a.getAttribute('href')); if (!t) return; e.preventDefault(); t.scrollIntoView({ behavior: 'smooth', block: 'start' });
}));

loadRules(); loadData();
