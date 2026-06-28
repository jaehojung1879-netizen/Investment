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
const tkName = (t) => NAMES[t] || t;
const tkSub = (t) => (NAMES[t] ? `<small class="tk">${t}</small>` : '');

// --- Click-to-popup explanations ---
const EXPL = {
  trade: ['오늘의 트레이드', '국내(KR)·국외(US) 후보 전체를 트레이드 호라이즌(기본 10영업일)으로 스크리닝해, <b>비용을 넘는 기대값(edge)</b>이 양수이고 확신 하한(확률 0.55)·국면(하락장 제외)을 만족하는 종목만 제안합니다. 제안이 없는 날은 관망이 정답입니다.'],
  core: ['보유 종목', '보유 종목은 호라이즌(21·63·126영업일)마다 LightGBM 상승확률·알림과 함께 표본 외(OOS) 정밀도·백테스트를 전체로 계산합니다. 신호를 그대로 따르기보다 lift·vsB&H로 신뢰도를 가늠하세요.'],
  macro: ['매크로', 'FRED에서 국외(미국 10Y·2Y·금리차·기준금리·하이일드 스프레드·VIX)와 국내(원/달러·국고채 10Y·3M·금리차)를 받아 지역별 스탠스와 위험 플래그를 표시합니다. 개별 종목 신호보다 먼저 점검합니다.'],
  sentiment: ['시장 국면(정량 심리)', '구루 인용 대신 <b>실데이터로 시장 방향성</b>을 계산합니다. 유니버스에서 200일·50일선 위 비중(breadth), 상승국면 비중, 중앙값 모멘텀에 매크로(VIX·신용스프레드·원화 등)를 더해 0~100 점수와 강세/중립/약세를 냅니다.'],
  prob: ['상승확률', '가격·추세·변동성·상대강도·매크로 피처 약 50개를 LightGBM 분류기에 넣어 해당 호라이즌 뒤 종가가 오를 확률을 추정합니다. 과거를 늘려가며 재학습하는 walk-forward이고, <b>학습에 쓰지 않은 최근 구간</b>으로 isotonic 보정해 확률이 실제 빈도와 맞도록 교정합니다.'],
  edge: ['edge (net)', '<code>edge = p·평균상승 + (1−p)·평균하락 − 비용허들</code>. 확률만으로는 비용을 못 넘기 때문에, 기대값이 양수일 때만 트레이드로 제안합니다. 국내(KR)는 세금·수수료로 허들이 더 높습니다.'],
  hold: ['보유(hold-until)', '진입일 + 트레이드 호라이즌(영업일)으로 잡은 <b>재평가 시점</b>입니다. 약속이 아니라, 그 전에 무효화 조건(종가 MA20 이탈 또는 다음 확률 0.5 미만)이 오면 먼저 청산합니다.'],
  lift: ['lift', '“항상 상승” 기준선(baseline) 대비 모델 정밀도의 <b>초과분(%p)</b>입니다. 예: 정밀도 70%, 기준선 65% → lift +5%p. <b>lift가 0에 가까우면 동전던지기와 다를 바 없으니 신뢰도를 낮춰</b> 해석하세요.'],
  oos: ['OOS 정밀도', '표본 외(Out-Of-Sample, 학습에 안 쓴 2020년 이후 구간)에서 “상승” 예측이 실제로 맞은 비율입니다. 같은 구간 백테스트의 vs B&H가 음수면 단순 보유만 못한 신호입니다.'],
  breadth: ['breadth(추세 위 비중)', '유니버스 종목 중 200일(또는 50일) 이동평균 위에 있는 종목의 비율입니다. 높을수록 시장 전반이 추세 위 = 강세 환경입니다.'],
};
const pop = $('#pop');
let popKey = null;
const showPop = (key, target) => {
  const e = EXPL[key]; if (!e) return;
  if (popKey === key && !pop.hidden) { hidePop(); return; }
  popKey = key;
  pop.innerHTML = `<b>${e[0]}</b><p>${e[1]}</p>`;
  pop.hidden = false;
  const r = target.getBoundingClientRect();
  const w = Math.min(320, window.innerWidth - 24);
  pop.style.width = w + 'px';
  let left = r.left + window.scrollX;
  left = Math.min(left, window.scrollX + window.innerWidth - w - 12);
  pop.style.left = Math.max(window.scrollX + 12, left) + 'px';
  pop.style.top = (r.bottom + window.scrollY + 6) + 'px';
};
const hidePop = () => { pop.hidden = true; popKey = null; };
document.addEventListener('click', (e) => {
  const t = e.target.closest('[data-x]');
  if (t) { e.preventDefault(); e.stopPropagation(); showPop(t.dataset.x, t); return; }
  if (!pop.contains(e.target)) hidePop();
});
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') hidePop(); });
window.addEventListener('scroll', hidePop, { passive: true });
const term = (key, label) => `<span class="term" data-x="${key}">${label}</span>`;

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

// --- Trade ideas ---
const ideaRow = (i) => `
  <div class="idea">
    <div class="idea-top">
      <strong>${tkName(i.ticker)}</strong>${tkSub(i.ticker)}
      <span class="reg ${regCls(i.regime)}">${regKo(i.regime)}</span>
      <span class="edge" data-x="edge">edge ${sp(i.edgeNetPct)}</span>
    </div>
    <div class="idea-bar"><i style="width:${Math.round((i.probUp ?? 0) * 100)}%"></i></div>
    <div class="idea-meta">
      <span>${term('prob', '확률')} <b>${pct0(i.probUp)}</b></span>
      <span>기대 <b>${sp(i.expMovePct)}</b></span>
      <span>${term('hold', '보유')} <b>~${i.holdUntil}</b> (${i.horizon}D)</span>
    </div>
    <div class="idea-inv muted">${i.invalidation}</div>
  </div>`;

const renderTrade = (d) => {
  const ti = d.tradeIdeas || { KR: [], US: [] };
  $('#tradeMeta').textContent = `보유 ${d.tradeHorizon ?? '—'}영업일 기준 · 비용·확신 게이트 통과분만`;
  const fill = (el, arr) => $(el).innerHTML = (arr && arr.length) ? arr.map(ideaRow).join('') : '<div class="none muted">조건 충족 종목 없음 (관망)</div>';
  fill('#tradeKR', ti.KR); fill('#tradeUS', ti.US);
  const sc = d.screened || [];
  $('#screenCount').textContent = `· ${sc.length}개`;
  $('#screenTable').innerHTML = `<div class="srow sh"><span>종목</span><span>지역</span><span>${term('prob', '확률')}</span><span>국면</span><span>채택</span></div>` +
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
      <div class="cs-m muted">${term('oos', '정밀')} ${pct0(o.precision)} <em class="${lc}" data-x="lift">(${sp(o.lift)})</em> · 연 ${sp(b.annualReturn)} · vsB&H ${sp(b.vsBuyHold)}</div>
    </div>`;
  }).join('');
  return `<article class="cc">
    <header><strong>${tkName(t.ticker)}</strong>${tkSub(t.ticker)}<span class="reg ${regCls(t.risk?.regime)}">${regKo(t.risk?.regime)}</span><span class="price">${fmt(t.lastClose)}</span></header>
    ${rows || '<p class="none muted">데이터 부족</p>'}
  </article>`;
};

// --- Macro (US / KR) ---
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

// --- Market sentiment (US / KR) ---
const scoreCls = (s) => s >= 60 ? 'bull' : s < 40 ? 'bear' : 'trans';
const sentLabel = (l) => l;
const sentimentRegion = (title, r) => {
  if (!r) return `<div class="macro-region"><div class="macro-region-head"><h3>${title}</h3></div><div class="none muted">데이터 없음</div></div>`;
  const comps = (r.components || []).map(([l, v, n]) => `<div><span>${l}</span><b>${v}</b><em>${n ?? ''}</em></div>`).join('');
  return `<div class="macro-region">
    <div class="macro-region-head"><h3>${title}</h3><span class="reg ${scoreCls(r.score)}">${sentLabel(r.label)} ${r.score}</span></div>
    <div class="gauge"><i class="${scoreCls(r.score)}" style="width:${r.score}%"></i></div>
    <div class="kpi">${comps}</div>
  </div>`;
};
const renderSentiment = (s) => {
  if (!s) { $('#sentimentPanel').innerHTML = '<div class="none muted">데이터 없음</div>'; return; }
  $('#sentimentPanel').innerHTML = sentimentRegion('국외 (US)', s.US) + sentimentRegion('국내 (KR)', s.KR);
};

const render = (d) => {
  NAMES = d.names || {};
  $('#portfolioName').textContent = d.portfolioName || 'Investment Insight';
  const seedTag = d.seed ? ' · SEED' : '';
  $('#dataStatus').textContent = `${(d.core || []).length} 보유 · primary ${d.primary || '—'}${seedTag}`;
  const m = d.meta || {};
  $('#dataMeta').textContent = [
    m.latestDataDate ? `데이터 ${m.latestDataDate}` : '',
    m.universeScreened ? `유니버스 ${m.universeScreened}` : '',
    m.modelsTrained ? `모델 ${m.modelsTrained}회 학습` : '',
    m.elapsedSec ? `${m.elapsedSec}s` : '',
  ].filter(Boolean).join(' · ');
  if (d.generatedAt) $('#dataGenerated').textContent = '생성 ' + new Date(d.generatedAt).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' }) + ' KST';
  const sb = $('#staleBanner');
  if (d.stale) { sb.hidden = false; sb.textContent = `⚠️ 데이터 갱신 실패 — 아래는 이전 빌드 결과입니다${m.buildError ? ' (' + m.buildError + ')' : ''}`; }
  else sb.hidden = true;
  renderTrade(d);
  $('#coreCards').innerHTML = (d.core || []).map(coreCard).join('') || '<p class="none muted">보유 종목 없음</p>';
  renderMacro(d.macro);
  renderSentiment(d.sentiment);
};

const loadData = async () => {
  try { const r = await fetch('data/site-data.json', { cache: 'no-store' }); if (!r.ok) throw new Error(`HTTP ${r.status}`); render(await r.json()); }
  catch (e) { $('#dataStatus').textContent = 'data error: ' + e.message; }
};

document.querySelectorAll('a[href^="#"]').forEach((a) => a.addEventListener('click', (e) => {
  const t = document.querySelector(a.getAttribute('href')); if (!t) return; e.preventDefault(); t.scrollIntoView({ behavior: 'smooth', block: 'start' });
}));

loadRules(); loadData();
