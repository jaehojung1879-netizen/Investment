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
const tkLink = (t) => `<span class="tklink" data-tk="${t}">${tkName(t)}</span>${tkSub(t)}`;

// --- v2 label maps ---
const VIEW = {
  POSITIVE: ['긍정', 'bull'], NEUTRAL: ['중립', 'trans'],
  NEGATIVE: ['부정', 'bear'], DATA_INSUFFICIENT: ['데이터부족', 'na'],
};
const ENTRY = {
  ACCUMULATE_GRADUALLY: ['분할 매수', 'bull'], WATCH: ['관찰', 'trans'],
  WAIT_FOR_PULLBACK: ['되돌림 대기', 'gold'], EVENT_RISK: ['이벤트 위험', 'bear'], AVOID: ['회피', 'bear'],
};
const REGIME_KO = {
  Goldilocks: '골디락스', Reflation: '리플레이션', Stagflation: '스태그플레이션',
  'Deflation/Slowdown': '디플레·둔화', 'Transition/Low confidence': '전환·저신뢰',
};
const viewBadge = (v) => { const [ko, c] = VIEW[v] || [v, 'trans']; return `<span class="vbadge v-${c}">${ko}</span>`; };
const entryBadge = (e) => { const [ko, c] = ENTRY[e] || [e, 'trans']; return `<span class="ebadge e-${c}">${ko}</span>`; };
const topPct = (p) => p != null ? `상위 ${Math.max(1, Math.round(100 - p))}%` : '—';

const fgLabel = (s) => s == null ? '—' : s < 25 ? '극도의 공포' : s < 45 ? '공포' : s < 55 ? '중립' : s < 75 ? '탐욕' : '극도의 탐욕';
const fgCls = (s) => s == null ? 'g-trans' : s < 45 ? 'g-bear' : s < 55 ? 'g-trans' : 'g-bull';
const regBadgeCls = (s) => s == null ? 'trans' : s < 45 ? 'bear' : s < 55 ? 'trans' : 'bull';

// --- Popover explanations ---
const EXPL = {
  status: ['데이터 상태 · 검증 상태', '<b>runMode</b>(researchOnly·paperTrading·liveValidated)는 사용 방식, <b>dataMode</b>(live·seed·stale·synthetic)는 숫자의 실체를 나타냅니다. liveValidated는 config만으로 부여되지 않고 paper ledger 검증을 거쳐야 합니다. 빌드 커밋 SHA와 marketAsOf/sourceAsOf로 어느 코드가 언제 데이터로 만든 결과인지 추적합니다. 차단(blocked) 상태면 단기·장기 액션과 비중이 모두 숨겨집니다.'],
  regime: ['매크로 국면 · 위험예산', '<b>6축(성장·물가·유동성·금융여건·위험선호·이익/신용)</b>은 진단에 표시하며, 국면 라벨은 성장×물가로 판정하고 금융여건·위험선호로 위험예산만 보정합니다. 지표별 변환과 고정 발표시차를 적용하지만 실제 발표 달력·ALFRED vintage는 사용하지 않습니다. 매크로는 개별 종목 알파에 더하지 않습니다.'],
  consensus: ['전문가 컨센서스', '검증된(verified) 기관 house view만 집계합니다. 단순 평균이 아니라 <b>weighted median + 의견 분산</b>을 계산하고, 기관·연구팀별 최대 한 표로 제한합니다. 기업 IR은 독립 의견으로 취급하지 않습니다(가중치 하향). 원문 검증 전에는 내용을 만들지 않고 “검증 대기”로만 둡니다. 각 합의에는 <b>반대 논거</b>를 함께 표시합니다.'],
  longterm: ['지역별 장기 리서치', 'KR·US를 <b>지역별로 독립 z-score</b> 산출하고(서로 직접 비교하지 않음), 팩터(모멘텀·밸류·퀄리티·저변동)는 <b>섹터 내 중립화</b>합니다. 알파 점수는 <b>신뢰도(팩터·재무 커버리지·소스 품질)로 페널티</b>를 받고, 위험지표·진입상태와 <b>분리 표기</b>됩니다. 3개 슬리브·최소 재무 커버리지 미달은 <b>DATA_INSUFFICIENT</b>로 분류돼 후보에서 제외됩니다.'],
  entry: ['진입상태', '‘좋은 종목’(장기 리서치 관점)과 ‘지금 살 종목’(진입상태)은 다릅니다. 추세(20·50·200일)·200일선 이격·<b>유니버스 내 과열 백분위</b>·변동성 급등·갭·실적 이벤트·섹터 집중도를 반영해 <b>분할매수/관찰/되돌림대기/이벤트위험/회피</b>로 구분합니다. 장기 팩터가 우수해도 과열·이벤트·급변동이면 되돌림 대기 또는 이벤트 위험이 됩니다.'],
  concentration: ['모델 슬리브 집중도', '<b>modelSleeveWeight</b>는 완전 투자된 <b>가상 모델 슬리브</b> 내 비중이며, 개인 포트폴리오 추천 비중이 아닙니다. 8~12종목, 단일종목 상한, 업종 상한, 현금 하한을 지킵니다. 과거의 5종목×20%(사실상 등가중) 구조를 제거했습니다.'],
  paper: ['Paper 성과 (signal ledger)', '오늘부터 생성되는 모든 종목선정 결과를 <b>변경 불가능한 ledger</b>에 누적합니다(과거 결과를 현재 모델로 덮어쓰지 않음). 21/63/126/252영업일 수익률·초과수익·MFE/MAE를 계산하고 hit rate뿐 아니라 <b>rank IC·초과수익</b>으로 평가합니다. 별도 history 브랜치에 저장됩니다. 검증 이력이 충분하기 전에는 “LIVE VALIDATED”라고 하지 않습니다.'],
  trade: ['단기 ML 참고자료', '단기 방향 예측은 동전던지기에 가깝고 수백 종목 스캔은 거짓 양성을 만듭니다. 주 판단은 위 장기 리서치·진입상태이며, 이 섹션은 타이밍 참고로만 보세요.'],
  macro: ['매크로 원지표', 'FRED(국외)·ECOS(국내) 원지표 값만 표시합니다. 국면·위험예산 판정은 상단 6축 방향 엔진이 담당합니다.'],
  sentiment: ['공포·탐욕 (정량 심리)', '유니버스 추세 위 비중·상승국면 비중·중앙값 모멘텀 + 매크로를 가중합한 휴리스틱 지수(확률 아님)입니다.'],
  direction: ['모델 위험예산 나침반', '규칙 기반 자산배분 도구를 합성한 <b>참고용</b> 방향성입니다. 개인의 전체 주식비중을 정하지 않으며, ‘모델 위험예산’으로만 제시합니다.'],
  dualmom: ['듀얼 모멘텀 변형', 'Antonacci GEM에서 영감을 받았으나 자산 메뉴·룩백·방어자산 구성이 달라 <b>정확한 GEM이 아닌 변형</b>입니다. 12개월 절대·상대 모멘텀으로 위험/방어 자산을 고릅니다(후행성 있음).'],
  rotation: ['섹터 로테이션 (RRG)', 'Relative Rotation Graph 근사치. 상대강도 비율·모멘텀으로 섹터 순환을 봅니다.'],
  factor: ['팩터 · 스타일 모멘텀', '모멘텀·가치·퀄리티·저변동·소형주 ETF의 S&P500 대비 초과수익입니다.'],
  flows: ['자금 흐름 (자체 프록시)', '거래량 급증 + 상승 종목. 기관/외국인 실제 수급이 아니라 자체 데이터로 만든 프록시입니다.'],
  indices: ['글로벌 마켓', '주요 지수·환율·원자재를 매 빌드마다 수집합니다. 소스 실패 시 대체 소스로 자동 전환합니다.'],
  prob: ['모델 점수 (보정 확률)', '가격·추세·변동성·매크로 피처를 LightGBM+로지스틱 앙상블에 넣어 보정한 확률입니다. [5%,95%]로 클리핑돼 100%/0%는 불가능합니다.'],
};
const pop = $('#pop');
let popKey = null;
const placePop = (target) => {
  const r = target.getBoundingClientRect(); const w = Math.min(340, window.innerWidth - 24);
  pop.style.width = w + 'px';
  let left = Math.min(r.left + window.scrollX, window.scrollX + window.innerWidth - w - 12);
  pop.style.left = Math.max(window.scrollX + 12, left) + 'px';
  pop.style.top = (r.bottom + window.scrollY + 6) + 'px';
};
const showPop = (key, target) => {
  const e = EXPL[key]; if (!e) return;
  if (popKey === key && !pop.hidden) return hidePop();
  popKey = key; pop.innerHTML = `<b>${e[0]}</b><p>${e[1]}</p>`; pop.hidden = false; placePop(target);
};
const hidePop = () => { pop.hidden = true; popKey = null; };
const term = (k, l) => `<span class="term" data-x="${k}">${l}</span>`;

const showTickerPop = (ticker, target) => {
  const d = DATA.details && DATA.details[ticker];
  if (!d) return;
  const m = (l, v) => `<div><span>${l}</span><b>${v}</b></div>`;
  const grid = [
    m('현재가', fmt(d.lastClose)), m('국면', regKo(d.regime)),
    m('10일 모델 점수', pct0(d.modelScore ?? d.probUp)), m('SMA50/200', `${fmt(d.ma50)} / ${fmt(d.ma200)}`),
    m('RSI(14)', fmt(d.rsi14)), m('실현변동성', fmt(d.realizedVol, '%')),
    m('1년 낙폭', fmt(d.maxDrawdown252d, '%')), m('상대강도', sp(d.relMomentum)),
    m('60일 모멘텀', sp(d.mom63)), m('52주고점 대비', fmt(d.pct52wHigh, '%')),
  ].join('');
  const flags = (d.riskFlags && d.riskFlags.length) ? `<div class="dp-flags">${d.riskFlags.map((f) => `<span class="mflag">${f}</span>`).join('')}</div>` : '';
  popKey = 'tk:' + ticker;
  pop.innerHTML = `<div class="dp-head"><b>${tkName(ticker)}</b> <span class="tk">${ticker}</span> <span class="reg ${regCls(d.regime)}">${regKo(d.regime)}</span></div><div class="dp-grid">${grid}</div>${flags}`;
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

// =========================================================================
// 1. Data & validation status
// =========================================================================
const chip = (label, value, cls = '') => `<div class="schip ${cls}"><span>${label}</span><b>${value}</b></div>`;
const renderStatus = (d) => {
  const p = d.provenance || {}; const m = d.meta || {};
  const dataMode = d.dataMode || p.dataMode || 'unknown';
  const runMode = d.runMode || p.runMode || 'paperTrading';
  const dmCls = dataMode === 'live' ? 'ok' : 'warn';
  const blocked = d.recommendationsBlocked;
  const chips = [
    chip('runMode', runMode, runMode === 'liveValidated' ? 'ok' : 'info'),
    chip('dataMode', dataMode, dmCls),
    chip('빌드 SHA', p.buildCommitSha || '—', 'info'),
    chip('스키마', p.schemaVersion || d.schemaVersion || '—', 'info'),
    chip('모델', p.modelVersion || d.modelVersion || '—', 'info'),
    chip('marketAsOf', p.marketAsOf || m.latestDataDate || '—'),
    chip('sourceAsOf', p.sourceAsOf || m.sourceAsOf || '—'),
    chip('커버리지', (m.coveragePct != null ? m.coveragePct + '%' : '—') + (m.coverageFloor ? ` / ≥${m.coverageFloor}%` : ''), (m.coveragePct >= (m.coverageFloor || 95)) ? 'ok' : 'warn'),
    chip('매크로 커버리지', m.macroCoverage != null ? Math.round(m.macroCoverage * 100) + '%' : '—', (m.macroCoverage >= 0.5) ? 'ok' : 'warn'),
    chip('모델 학습', (m.modelsTrained || 0) + '회', (m.modelsTrained > 0) ? 'ok' : 'warn'),
    chip('추천 상태', blocked ? '차단(액션·비중 숨김)' : '표시', blocked ? 'bad' : 'ok'),
  ];
  $('#statusPanel').innerHTML = chips.join('') +
    (blocked ? `<div class="status-note bad">⚠️ ${(d.blockReasons || []).join(' · ') || '데이터 안전 차단'} — 이 데이터로 매매하지 마세요.</div>` : '') +
    (dataMode !== 'live' ? `<div class="status-note warn">데이터 모드 <b>${dataMode}</b>: 예시/합성/오래된 데이터입니다. 실데이터 빌드는 Yahoo/FRED 네트워크 + FRED_API_KEY가 필요합니다.</div>` : '');
};

// =========================================================================
// 2. Macro regime & risk budget
// =========================================================================
const axisRow = (a) => {
  const v = a.value; const dirCls = v == null ? 'trans' : v > 0.15 ? 'bull' : v < -0.15 ? 'bear' : 'trans';
  const w = v == null ? 0 : Math.min(50, Math.abs(v) * 50);
  return `<div class="ax-row">
    <span class="ax-name">${a.ko}</span>
    <span class="ax-bar"><i class="${v >= 0 ? 'apos' : 'aneg'}" style="${v >= 0 ? 'left:50%' : 'right:50%'};width:${w}%"></i></span>
    <span class="ax-lab reg ${dirCls}">${a.labelKo}</span>
    <span class="ax-conf muted">커버 ${Math.round((a.coverage ?? 0) * 100)}% · 신선도 ${Math.round((a.freshness ?? 0) * 100)}% · 합의 ${Math.round((a.agreement ?? 0) * 100)}%</span>
  </div>`;
};
const renderRegime = (r) => {
  const host = $('#regimePanel'); const sec = $('#regime');
  if (!r) { sec.hidden = true; return; }
  sec.hidden = false;
  $('#regimeMeta').textContent = `${r.asOf ? '기준 ' + r.asOf + ' · ' : ''}지표 ${r.indicatorCount ?? 0}개 · 커버리지 ${Math.round((r.coverage ?? 0) * 100)}%`;
  const rb = r.riskBudget || {};
  const changed = r.changed ? `<span class="chg">← ${REGIME_KO[r.priorRegime] || r.priorRegime}에서 전환</span>` : '';
  const axesHtml = Object.values(r.axes || {}).map(axisRow).join('');
  const support = (r.supporting || []).map((s) => `<span class="ev ev-pos">${s.name}</span>`).join('') || '<span class="muted">—</span>';
  const contra = (r.contradicting || []).map((s) => `<span class="ev ev-neg">${s.name}</span>`).join('') || '<span class="muted">—</span>';
  host.innerHTML = `
    <div class="regime-head">
      <div class="regime-label reg ${r.regime && r.regime.startsWith('Transition') ? 'trans' : (r.regime === 'Goldilocks' || r.regime === 'Reflation') ? 'bull' : 'bear'}">${REGIME_KO[r.regime] || r.regime}</div>
      <div class="regime-conf">국면 판정 신뢰 <b>${Math.round((r.confidence ?? 0) * 100)}%</b> ${changed}</div>
      ${r.note ? `<div class="status-note warn">${r.note}</div>` : ''}
      ${r.pointInTimeLimitations ? `<div class="status-note info">한계: ${r.pointInTimeLimitations}</div>` : ''}
    </div>
    <div class="regime-axes">${axesHtml}</div>
    <div class="regime-budget">
      <div class="rb-h">위험예산 (매크로 레이어 — 개별 알파에 가산하지 않음)</div>
      <div class="rb-row"><span>주식 노출</span><b>${(rb.equityRangePct || []).join('~')}%</b><span>현금</span><b>${(rb.cashRangePct || []).join('~')}%</b></div>
      <div class="rb-tilt muted">스타일 틸트: ${rb.styleTilt || '—'}</div>
    </div>
    <div class="regime-ev"><div><span class="evh">근거</span>${support}</div><div><span class="evh">반대 근거</span>${contra}</div></div>`;
};

// =========================================================================
// 3. Expert consensus
// =========================================================================
const stanceKo = (s) => s == null ? '—' : s >= 1 ? `강한 긍정 (+${s})` : s > 0 ? `긍정 (+${s})` : s === 0 ? '중립 (0)' : s <= -1 ? `강한 부정 (${s})` : `부정 (${s})`;
const themeCard = (t) => {
  const agr = { high: ['합의 강함', 'bull'], mixed: ['혼재', 'trans'], low: ['의견 갈림', 'bear'] }[t.agreement] || ['—', 'trans'];
  const views = (t.views || []).map((v) => `<div class="cv-view"><span>${v.institution}${v.sourceType === 'companyIR' ? ' <em class="ir">IR</em>' : ''}</span><b>${stanceKo(v.stance)}</b>${v.url ? `<a href="${v.url}" target="_blank" rel="noopener">원문</a>` : ''}</div>`).join('');
  return `<div class="cv-card">
    <div class="cv-top"><b>${t.theme}</b><span class="reg ${agr[1]}">${agr[0]}</span></div>
    <div class="cv-meta">중앙값 스탠스 <b>${stanceKo(t.weightedMedianStance)}</b> · 분산 ${fmt(t.dispersion)} · 기관 ${t.institutionCount}곳</div>
    <div class="cv-views">${views}</div>
    ${t.counterCase ? `<div class="cv-counter">반대 논거: ${t.counterCase}</div>` : ''}
  </div>`;
};
const renderConsensus = (c) => {
  const host = $('#consensusPanel'); const sec = $('#consensus');
  if (!c) { sec.hidden = true; return; }
  sec.hidden = false;
  $('#consensusMeta').textContent = `검증 ${c.verifiedCount ?? 0}건 · STALE ${c.staleCount ?? 0}건`;
  let html = '';
  if (c.themes && c.themes.length) html += c.themes.map(themeCard).join('');
  else html += `<div class="status-note warn">${c.note || '검증된 전문가 의견 없음'}</div>`;
  if (c.awaitingVerification && c.awaitingVerification.length) {
    html += `<div class="cv-await"><div class="rb-h">검증 대기 (원문 확인 후 반영 — 내용 날조 없음)</div>` +
      c.awaitingVerification.map((a) => `<div class="cv-awrow"><span>${a.institution}</span><em>${a.theme || ''}</em>${a.url ? `<a href="${a.url}" target="_blank" rel="noopener">원문</a>` : ''}</div>`).join('') + `</div>`;
  }
  host.innerHTML = html;
};

// =========================================================================
// 4. Region long-term research + 5. entry states
// =========================================================================
const fBar = (label, v) => `<div class="fb"><span>${label}</span><div class="fb-bar"><i style="width:${v ?? 0}%"></i></div><b>${v != null ? v : '—'}</b></div>`;
const prosCons = (p) => {
  const fp = p.factorPercentiles || {}; const risk = p.risk || {};
  const completeness = p.dataCompleteness ?? p.financialCoverage ?? 0;
  const pros = [], cons = [];
  if (fp.momentum >= 66) pros.push(`모멘텀 상위 (${fp.momentum}p)`);
  if (fp.value >= 66) pros.push(`밸류 매력 (${fp.value}p)`);
  if (fp.quality >= 66) pros.push(`퀄리티 우수 (${fp.quality}p)`);
  if (fp.lowvol >= 66) pros.push(`저변동 (${fp.lowvol}p)`);
  if (p.aboveMA200) pros.push('200일선 위 (추세 확인)');
  if (p.alphaPercentile >= 66) pros.push(`섹터중립 알파 ${topPct(p.alphaPercentile)}`);
  if (p.valueTrap) cons.push('가치함정 신호 (싼데 퀄리티·현금흐름 약함)');
  if (completeness < 0.6) cons.push(`데이터 완전성 낮음 (${Math.round(completeness * 100)}%)`);
  if (!p.aboveMA200) cons.push('200일선 아래 (추세 미확인)');
  if (fp.quality != null && fp.quality <= 33) cons.push(`퀄리티 하위 (${fp.quality}p)`);
  if (risk.maxDD252Pct != null && risk.maxDD252Pct <= -25) cons.push(`최근 낙폭 ${risk.maxDD252Pct}%`);
  if (risk.cvar95Pct != null && risk.cvar95Pct >= 4) cons.push(`꼬리위험 CVaR ${risk.cvar95Pct}%`);
  if ((p.entry || {}).overheatPercentile != null && p.entry.overheatPercentile >= 85) cons.push('유니버스 내 과열');
  return { pros: pros.slice(0, 3), cons: cons.slice(0, 3) };
};
const ltRow = (p, blocked = false) => {
  const { pros, cons } = prosCons(p);
  const e = blocked ? {} : (p.entry || {}); const risk = p.risk || {};
  const w = blocked ? null : p.modelSleeveWeightPct;
  const evidence = p.evidenceCoverage ?? p.factorCoverage ?? p.confidence ?? 0;
  const completeness = p.dataCompleteness ?? p.financialCoverage ?? 0;
  const sourceQuality = p.sourceQuality ?? 0;
  const empirical = p.empiricalValidationStatus || 'PENDING_PAPER_HISTORY';
  const invalidation = `알파 백분위가 매도 버퍼(예: 하위 70p) 아래로 하락하거나 재무 커버리지가 기준 미달로 전환되면 후보 제외 · 진입상태가 회피로 바뀌면 신규 편입 중단`;
  return `<div class="lt-item">
    <div class="lt-top">${tkLink(p.ticker)}<span class="muted lt-sec">${p.sectorKo || '미분류'}</span>${viewBadge(p.longTermResearchView)}${entryBadge(e.entryState)}${w != null ? `<span class="edge" data-x="concentration">슬리브 ${w}%</span>` : ''}</div>
    <div class="lt-meta"><span>알파 <b>${topPct(p.alphaPercentile)}</b></span><span>근거 커버리지 <b>${Math.round(evidence * 100)}%</b></span><span>데이터 완전성 <b>${Math.round(completeness * 100)}%</b></span><span>소스 품질 <b>${Math.round(sourceQuality * 100)}%</b></span><span>실증 <b>${empirical === 'PENDING_PAPER_HISTORY' ? '검증 대기' : empirical}</b></span><span>12-1M <b>${sp(p.mom12_1Pct)}</b></span></div>
    <div class="lt-bars">${fBar('모멘텀', p.factorPercentiles?.momentum)}${fBar('밸류', p.factorPercentiles?.value)}${fBar('퀄리티', p.factorPercentiles?.quality)}${fBar('저변동', p.factorPercentiles?.lowvol)}</div>
    <div class="lt-risk muted">위험: 변동성 ${fmt(risk.vol252Pct, '%', 0)} · 하방변동 ${fmt(risk.downsideVolPct, '%', 0)} · 최대낙폭 ${fmt(risk.maxDD252Pct, '%', 0)} · CVaR ${fmt(risk.cvar95Pct, '%', 1)}${risk.beta != null ? ' · β ' + risk.beta : ''}</div>
    ${!blocked && e.reasons && e.reasons.length ? `<div class="lt-entry muted">진입: ${e.reasons.join(' · ')}</div>` : ''}
    <div class="lt-args"><div class="pro"><b>긍정</b>${(pros.length ? pros : ['—']).map((x) => `<span>${x}</span>`).join('')}</div><div class="con"><b>반대</b>${(cons.length ? cons : ['—']).map((x) => `<span>${x}</span>`).join('')}</div></div>
    ${blocked ? '' : `<div class="lt-inval muted">논리 무효화: ${invalidation}</div>`}
  </div>`;
};
const renderLongTerm = (d) => {
  const lt = d.longTerm; const sec = $('#longterm');
  if (!lt || !lt.regions) { sec.hidden = true; return; }
  sec.hidden = false;
  const hm = lt.horizonMonths || [6, 12];
  $('#ltMeta').textContent = `보유 ${hm[0]}~${hm[hm.length - 1]}개월 · ${lt.rebalance || ''} · 재무 커버리지 ${lt.fundamentalsCoverage ?? '—'}%` + (lt.weightsWithheld ? ' · 비중 숨김(차단)' : '');
  const fill = (el, reg) => {
    const r = lt.regions[reg];
    const rows = (r && ((r.picks && r.picks.length) ? r.picks : r.researchTable)) || [];
    let html = d.recommendationsBlocked ? '<div class="status-note info">데이터 검증 전으로 진입 판단을 제공하지 않습니다.</div>' : '';
    html += rows.length ? rows.map((p) => ltRow(p, d.recommendationsBlocked)).join('') : '<div class="none">데이터 부족</div>';
    if (r && r.dataInsufficient && r.dataInsufficient.length) html += `<div class="lt-insuf muted">DATA_INSUFFICIENT (${r.dataInsufficient.length}): 팩터/재무 커버리지 부족으로 후보 제외 — ${r.dataInsufficient.slice(0, 8).map((x) => tkName(x.ticker)).join(', ')}${r.dataInsufficient.length > 8 ? ' 외' : ''}</div>`;
    $(el).innerHTML = html;
  };
  fill('#ltKR', 'KR'); fill('#ltUS', 'US');
  $('#ltCaveats').innerHTML = '⚠️ ' + (lt.caveats || []).join(' · ');
};

// 5. Entry & risk warnings (aggregated)
const renderEntry = (d) => {
  const lt = d.longTerm; const host = $('#entryPanel');
  if (!lt || !lt.regions) { $('#entry').hidden = true; return; }
  $('#entry').hidden = false;
  if (d.recommendationsBlocked) {
    host.innerHTML = '<div class="status-note info">데이터 검증 전으로 진입 판단을 제공하지 않습니다.</div>';
    return;
  }
  const rows = [];
  for (const reg of ['KR', 'US']) {
    const r = lt.regions[reg]; if (!r) continue;
    for (const p of (r.researchTable || [])) rows.push(p);
  }
  const warn = rows.filter((p) => ['WAIT_FOR_PULLBACK', 'EVENT_RISK', 'AVOID'].includes((p.entry || {}).entryState) && p.longTermResearchView !== 'NEGATIVE');
  const buy = rows.filter((p) => (p.entry || {}).entryState === 'ACCUMULATE_GRADUALLY' && p.longTermResearchView === 'POSITIVE');
  const box = (title, arr, empty) => `<div class="entry-col"><div class="col-h">${title}</div>${arr.length ? arr.slice(0, 8).map((p) => `<div class="entry-row">${tkLink(p.ticker)}${viewBadge(p.longTermResearchView)}${entryBadge((p.entry || {}).entryState)}<span class="muted">${((p.entry || {}).reasons || [])[0] || ''}</span></div>`).join('') : `<div class="none">${empty}</div>`}</div>`;
  host.innerHTML = box('장기 긍정 · 지금 분할매수', buy, '해당 종목 없음') +
    box('장기 긍정이나 지금은 대기 (되돌림/이벤트/회피)', warn, '경고 없음');
};

// 6. Concentration
const renderConcentration = (d) => {
  const lt = d.longTerm; const host = $('#concentrationPanel');
  if (!lt || !lt.regions) { $('#concentration').hidden = true; return; }
  $('#concentration').hidden = false;
  const one = (reg) => {
    const r = lt.regions[reg]; if (!r) return `<div><div class="col-h">${reg}</div><div class="none">데이터 없음</div></div>`;
    const exp = r.sectorExposure || {};
    const bars = Object.entries(exp).sort((a, b) => b[1] - a[1]).map(([s, w]) => `<div class="conc-row"><span>${s}</span><div class="conc-bar"><i style="width:${Math.min(100, w * 2)}%"></i></div><b>${w}%</b></div>`).join('') || '<div class="none">슬리브 비중 없음(차단/데이터부족)</div>';
    return `<div><div class="col-h">${reg === 'KR' ? '국내 (KR)' : '국외 (US)'} · 현금 ${r.cashPct != null ? r.cashPct + '%' : '—'}</div>${bars}</div>`;
  };
  host.innerHTML = one('KR') + one('US');
};

// 7. Paper performance
const renderPaper = (d) => {
  const host = $('#paperPanel');
  const pp = d.paperPerformance;
  const vs = d.validationStatus || {};
  if (pp && pp.n) {
    $('#paperMeta').textContent = `누적 ${pp.n}건 · rank IC ${fmt(pp.rankIC)}`;
    host.innerHTML = `<div class="paper-metrics">${Object.entries(pp.byView || {}).map(([v, o]) => `<div class="pm"><span>${(VIEW[v] || [v])[0]}</span><b>${sp((o.meanFwd ?? 0) * 100)}</b><em>n=${o.n}</em></div>`).join('')}</div>`;
  } else {
    $('#paperMeta').textContent = `검증 대기 · paper ${vs.paperDays ?? 0}일 · 성숙 신호 ${vs.maturedSignals ?? 0}개`;
    const regionIc = Object.entries(vs.regionIC || {}).map(([region, x]) => `${region} IC ${x.mean ?? '—'} (날짜 ${x.nDates ?? 0}, 종목 ${x.nSignals ?? 0})`).join(' · ') || '지역별 IC 대기';
    host.innerHTML = `<div class="status-note info"><b>검증 대기</b> — liveValidationEligible=${vs.liveValidationEligible === true ? 'true(수동 검토 필요)' : 'false'}<br>paperDays ${vs.paperDays ?? 0} · maturedSignals ${vs.maturedSignals ?? 0} · eligibleDates ${vs.eligibleDates ?? 0}<br>${regionIc}<br>비용 차감 초과수익 ${vs.costAdjustedExcessReturn ?? '—'} · MDD ${vs.MDD ?? '—'} · CVaR ${vs.CVaR ?? '—'}<br>미달 사유: ${(vs.reasons || ['paper history 누적 중']).join(' · ')}</div>`;
  }
};

// =========================================================================
// 8. Short-term ML ideas (reference only)
// =========================================================================
const ideaRow = (i) => `
  <div class="idea">
    <div class="idea-top"><strong class="tklink" data-tk="${i.ticker}">${tkName(i.ticker)}</strong>${tkSub(i.ticker)}<span class="reg ${regCls(i.regime)}">${regKo(i.regime)}</span><span class="edge" data-x="prob">참고 신호</span></div>
    <div class="idea-bar"><i style="width:${Math.round(((i.modelScore ?? i.probUp) ?? 0) * 100)}%"></i></div>
    <div class="idea-meta"><span>${term('prob', '모델 점수')} <b>${pct0((i.modelScore ?? i.probUp))}</b></span><span>${term('hold', '재평가')} <b>~${i.holdUntil}</b> (${i.horizon}D)</span></div>
    <div class="idea-why">${i.why || ''}</div>
  </div>`;
const renderIdeas = (d) => {
  if (d.recommendationsBlocked) {
    $('#tradeKR').innerHTML = $('#tradeUS').innerHTML = '<div class="none">데이터 안전 차단: 단기 참고 신호도 숨김.</div>';
    $('#tradeMeta').textContent = '차단 · ' + ((d.blockReasons || []).join(' · ') || '데이터 안전');
  } else {
    const ti = d.tradeIdeas || { KR: [], US: [] };
    $('#tradeMeta').textContent = `참고용 · 10영업일`;
    const fill = (el, arr) => $(el).innerHTML = (arr && arr.length) ? arr.map(ideaRow).join('') : '<div class="none">참고 신호 없음</div>';
    fill('#tradeKR', ti.KR); fill('#tradeUS', ti.US);
  }
  const sc = d.screened || [];
  $('#screenCount').textContent = `· ${sc.length}개`;
  $('#screenTable').innerHTML = `<div class="srow sh"><span>종목</span><span>지역</span><span>${term('prob', '모델 점수')}</span><span>국면</span></div>` +
    sc.map((s) => `<div class="srow" data-key="${(s.ticker + ' ' + tkName(s.ticker)).toLowerCase()}"><span>${tkLink(s.ticker)}</span><span>${s.region}</span><span>${pct0(s.modelScore ?? s.probUp)}</span><span class="reg ${regCls(s.regime)}">${regKo(s.regime)}</span></div>`).join('');
  filterScreen();
};

// --- indices tape ---
const nfmt = (v, d) => (v == null || Number.isNaN(v)) ? '—' : v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
const chg = (v, d = 2) => (v == null || Number.isNaN(v)) ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(d)}%`;
const sparkSvg = (vals) => {
  if (!vals || vals.length < 2) return '';
  const w = 116, h = 30, min = Math.min(...vals), max = Math.max(...vals), span = (max - min) || 1;
  const pts = vals.map((v, i) => `${(i / (vals.length - 1) * w).toFixed(1)},${(h - 2 - (v - min) / span * (h - 4)).toFixed(1)}`).join(' ');
  const up = vals[vals.length - 1] >= vals[0];
  return `<svg class="spark ${up ? 'spark-up' : 'spark-down'}" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" aria-hidden="true"><polyline points="${pts}" fill="none" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/></svg>`;
};
const ixTile = (x) => {
  const d1 = x.chg1dPct; const dir = d1 == null ? '' : d1 >= 0 ? 'pos' : 'neg';
  return `<article class="ix" title="${x.symbol} · ${x.asOf ?? ''} · ${x.source ?? ''}"><div class="ix-h"><span class="ix-name">${x.name}</span><span class="ix-reg">${x.region}</span></div><div class="ix-quote"><span class="ix-last">${nfmt(x.last, x.digits ?? 2)}</span><span class="ix-chg ${dir}">${chg(d1)}</span></div>${sparkSvg(x.spark)}<div class="ix-sub"><span>1M <b class="${(x.chg1mPct ?? 0) >= 0 ? 'pos' : 'neg'}">${chg(x.chg1mPct, 1)}</b></span><span>YTD <b class="${(x.ytdPct ?? 0) >= 0 ? 'pos' : 'neg'}">${chg(x.ytdPct, 1)}</b></span><span>고점비 <b>${chg(x.from52wHighPct, 1)}</b></span></div></article>`;
};
const renderIndices = (d) => {
  const sec = $('#indices'); const list = d.indices || [];
  if (!list.length) { sec.hidden = true; return; }
  sec.hidden = false;
  $('#indexTape').innerHTML = list.map(ixTile).join('');
  $('#tapeMeta').textContent = `${list[0].asOf ? '기준 ' + list[0].asOf + ' · ' : ''}미니 차트는 최근 3개월`;
};

// --- direction compass ---
const dirSignal = (s) => `<div class="dsig"><div class="dsig-top"><span class="dsig-name">${s.name}</span><span class="reg ${s.cls}">${s.state}</span></div><div class="dsig-detail">${s.detail || ''}</div></div>`;
const dmRow = (r, winner) => { const cell = (v) => `<span class="${(v ?? 0) >= 0 ? 'pos' : 'neg'}">${chg(v, 1)}</span>`; return `<div class="dm-row ${r.ticker === winner ? 'dm-win' : ''}"><span class="dm-name">${r.ticker === winner ? '★ ' : ''}${r.name} <span class="tk">${r.ticker}</span></span><span>${cell(r.ret3mPct)}</span><span>${cell(r.ret6mPct)}</span><span>${cell(r.ret12mPct)}</span></div>`; };
const renderDirection = (dir) => {
  const sec = $('#direction'); if (!dir) { sec.hidden = true; return; }
  sec.hidden = false;
  $('#dirMeta').textContent = '듀얼 모멘텀 변형 · 변동성 · 추세 · 심리 합성 (참고)';
  const vt = dir.volTarget;
  $('#dirVerdict').innerHTML = `<div class="overline">모델 위험예산 방향</div><div class="dir-stance-row"><span class="dir-stance">${dir.stance}</span><span class="posture-score reg ${dir.stanceCls}">${dir.score}</span></div><div class="gauge"><i class="${dir.stanceCls}" style="width:${dir.score}%"></i></div><p class="dir-read">${dir.headline || ''}</p><div class="alloc"><div class="alloc-bar"><i class="eq" style="width:${dir.equityPct}%"></i><i class="cash" style="width:${dir.cashPct}%"></i></div><div class="alloc-legend"><span><i class="dot dot-eq"></i>주식 ${dir.equityPct}%</span><span><i class="dot dot-cash"></i>현금·방어 ${dir.cashPct}%</span></div></div>`;
  $('#dirSignals').innerHTML = (dir.signals || []).map(dirSignal).join('');
  const dm = dir.dualMomentum; const box = document.querySelector('.dm-box');
  if (!dm || !dm.rows || !dm.rows.length) { if (box) box.hidden = true; }
  else { if (box) box.hidden = false; $('#dualMomTable').innerHTML = `<div class="dm-row dm-h2"><span>자산</span><span>3M</span><span>6M</span><span>12M</span></div>` + dm.rows.map((r) => dmRow(r, dm.winner)).join(''); }
};

// --- rotation ---
const QUAD = { '주도': { cls: 'q-lead', color: 'var(--green)' }, '약화': { cls: 'q-weak', color: 'var(--gold)' }, '개선': { cls: 'q-impr', color: 'var(--accent)' }, '부진': { cls: 'q-lag', color: 'var(--red)' } };
const rrgSvg = (sectors) => {
  const W = 400, H = 300, pad = 10, cx = W / 2, cy = H / 2;
  const maxX = Math.max(2, ...sectors.map((s) => Math.abs(s.rsRatio))) * 1.25, maxY = Math.max(2, ...sectors.map((s) => Math.abs(s.rsMom))) * 1.25;
  const X = (v) => cx + (v / maxX) * (W / 2 - pad), Y = (v) => cy - (v / maxY) * (H / 2 - pad);
  const dots = sectors.map((s) => { const x = X(s.rsRatio), y = Y(s.rsMom), c = (QUAD[s.quadrant] || {}).color || 'var(--muted)'; const anchor = x > W - 60 ? 'end' : 'start'; return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4.5" fill="${c}" fill-opacity="0.9"><title>${s.name} · ${s.quadrant}</title></circle><text x="${(x + (anchor === 'end' ? -7 : 7)).toFixed(1)}" y="${(y + 3.5).toFixed(1)}" text-anchor="${anchor}" class="rrg-lb">${s.name}</text>`; }).join('');
  return `<svg viewBox="0 0 ${W} ${H}" class="rrg"><rect x="${cx}" y="0" width="${cx}" height="${cy}" class="rrg-q rrg-q-lead"/><rect x="${cx}" y="${cy}" width="${cx}" height="${cy}" class="rrg-q rrg-q-weak"/><rect x="0" y="0" width="${cx}" height="${cy}" class="rrg-q rrg-q-impr"/><rect x="0" y="${cy}" width="${cx}" height="${cy}" class="rrg-q rrg-q-lag"/><line x1="0" y1="${cy}" x2="${W}" y2="${cy}" class="rrg-ax"/><line x1="${cx}" y1="0" x2="${cx}" y2="${H}" class="rrg-ax"/>${dots}</svg>`;
};
const rrgChips = (sectors) => sectors.map((s) => `<span class="rchip ${(QUAD[s.quadrant] || {}).cls || ''}">${s.name} <b>${s.quadrant}</b> <em>${chg(s.ret3mPct, 1)}</em></span>`).join('');
const renderRegionRrg = (el, region) => { const host = $(el); if (!region || !region.sectors || !region.sectors.length) { host.innerHTML = '<div class="none">데이터 없음</div>'; return; } host.innerHTML = rrgSvg(region.sectors) + `<div class="rrg-chips">${rrgChips(region.sectors)}</div>`; };
const factorRow = (f) => { const v = f.ex3mPct ?? 0, w = Math.min(50, Math.abs(v) * 6); return `<div class="frow"><span class="f-name">${f.name} <span class="tk">${f.ticker}</span></span><span class="f-bar"><i class="${v >= 0 ? 'fpos' : 'fneg'}" style="${v >= 0 ? 'left:50%' : 'right:50%'};width:${w}%"></i></span><span class="f-nums">3M <b class="${v >= 0 ? 'pos' : 'neg'}">${chg(f.ex3mPct, 1)}</b></span></div>`; };
const renderRotation = (rot) => {
  const sec = $('#rotation'); if (!rot || (!rot.US && !rot.KR && !(rot.factors || []).length)) { sec.hidden = true; return; }
  sec.hidden = false; $('#rotMeta').textContent = `${rot.asOf ? '기준 ' + rot.asOf : ''}`;
  renderRegionRrg('#rrgUS', rot.US); renderRegionRrg('#rrgKR', rot.KR);
  const fp = $('#factorPanel');
  if ((rot.factors || []).length) { fp.hidden = false; $('#factorBars').innerHTML = rot.factors.map(factorRow).join(''); } else fp.hidden = true;
};

// --- flows ---
const flowRow = (f) => `<div class="flow"><span class="flow-tk tklink" data-tk="${f.ticker}">${tkName(f.ticker)}</span><span class="reg ${regCls(f.regime)}">${regKo(f.regime)}</span><span class="flow-surge">거래량 <b>×${fmt(f.volSurge)}</b></span><span class="flow-mom">모멘텀 <b>${sp(f.mom63)}</b></span></div>`;
const renderFlows = (d) => { const fl = d.flows || { KR: [], US: [] }; const fill = (el, arr) => $(el).innerHTML = (arr && arr.length) ? arr.map(flowRow).join('') : '<div class="none">두드러진 자금 유입 없음</div>'; fill('#flowsKR', fl.KR); fill('#flowsUS', fl.US); };

// --- macro / sentiment display panels ---
const region = (title, kpis, badge) => `<div class="region"><div class="region-h"><h4>${title}</h4>${badge || ''}</div><div class="kpi">${kpis}</div></div>`;
const kpiItems = (arr) => (arr || []).map(([l, v, n]) => `<div><span>${l}</span><b>${v}</b><em>${n ?? ''}</em></div>`).join('');
const renderMacro = (m) => {
  if (!m || !m.available) { $('#macroPanel').innerHTML = `<div class="none">${m?.note ?? '매크로 비활성'}</div>`; return; }
  $('#macroPanel').innerHTML = region('국외 (US)', kpiItems(m.US?.indicators)) + region('국내 (KR)', kpiItems(m.KR?.indicators));
};
const sentBadge = (r) => `<span class="reg ${regBadgeCls(r.score)}">${r.fearGreed || r.label} ${r.score}</span>`;
const renderSentiment = (s) => {
  if (!s) { $('#sentimentPanel').innerHTML = '<div class="none">데이터 없음</div>'; return; }
  const one = (title, r) => r ? region(title, kpiItems(r.components), sentBadge(r)) : region(title, '', '');
  $('#sentimentPanel').innerHTML = one('국외 (US)', s.US) + one('국내 (KR)', s.KR);
};

// --- master render ---
const render = (d) => {
  DATA = d; NAMES = d.names || {};
  $('#portfolioName').textContent = d.portfolioName || 'Investment Research';
  const p = d.provenance || {};
  $('#dataStatus').textContent = `· ${(d.runMode || 'paperTrading')} · ${(d.dataMode || p.dataMode || 'live')}${d.seed ? ' · SEED' : ''}`;
  const m = d.meta || {};
  $('#dataMeta').textContent = [m.latestDataDate ? `데이터 ${m.latestDataDate}` : '', p.buildCommitSha ? `빌드 ${p.buildCommitSha}` : '', m.coveragePct != null ? `커버리지 ${m.coveragePct}%` : ''].filter(Boolean).join(' · ');
  if (d.generatedAt) $('#dataGenerated').textContent = '생성 ' + new Date(d.generatedAt).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' }) + ' KST';
  const sb = $('#staleBanner');
  if (d.recommendationsBlocked || d.stale || d.seed || (d.dataMode && d.dataMode !== 'live')) {
    sb.hidden = false; sb.classList.add('warn');
    sb.innerHTML = `<b>⚠️ 이 데이터로 매매하지 마세요 — 액션·비중 차단 (dataMode: ${d.dataMode || (d.seed ? 'seed' : 'stale')})</b><br><span>${(d.blockReasons || []).join(' · ') || ''}${m.latestDataDate ? ' · 마지막 데이터 ' + m.latestDataDate : ''}</span>`;
  } else { sb.hidden = true; sb.classList.remove('warn'); }
  renderStatus(d);
  renderIndices(d);
  renderRegime(d.macroRegime);
  renderConsensus(d.expertConsensus);
  renderLongTerm(d);
  renderEntry(d);
  renderConcentration(d);
  renderPaper(d);
  renderIdeas(d);
  renderDirection(d.direction);
  renderRotation(d.rotation);
  renderFlows(d);
  renderMacro(d.macro);
  renderSentiment(d.sentiment);
};

const loadData = async () => {
  try { const r = await fetch('data/site-data.json', { cache: 'no-store' }); if (!r.ok) throw new Error(`HTTP ${r.status}`); render(await r.json()); }
  catch (e) { $('#dataStatus').textContent = 'data error: ' + e.message; }
};
const filterScreen = () => {
  const q = ($('#screenSearch')?.value || '').trim().toLowerCase();
  const rows = document.querySelectorAll('#screenTable .srow:not(.sh)'); let shown = 0;
  rows.forEach((r) => { const hit = !q || (r.dataset.key || '').includes(q); r.style.display = hit ? '' : 'none'; if (hit) shown++; });
  const empty = $('#screenEmpty'); if (empty) empty.hidden = shown !== 0;
};
$('#screenSearch')?.addEventListener('input', filterScreen);
document.querySelectorAll('.nav a[href^="#"]').forEach((a) => a.addEventListener('click', (e) => { const t = document.querySelector(a.getAttribute('href')); if (!t) return; e.preventDefault(); t.scrollIntoView({ behavior: 'smooth', block: 'start' }); }));
loadRules(); loadData();
