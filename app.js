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
const REGIME_GUIDE = {
  Goldilocks: {
    one: '성장은 빨라지고 물가는 둔화되는, 위험자산에 가장 우호적인 조합입니다.',
    watch: '기업이익과 고용의 개선이 이어지는지, 물가 둔화가 멈추지 않는지 확인합니다.',
    risk: '좋은 뉴스가 이미 가격에 많이 반영됐거나 물가가 다시 뛰면 빠르게 리플레이션으로 이동할 수 있습니다.',
  },
  Reflation: {
    one: '경기 회복·성장 가속과 물가 상승 압력이 동시에 나타나는 국면입니다.',
    watch: '실물·가치·에너지 업종이 상대적으로 유리할 수 있지만 장기금리와 원가 부담을 함께 봐야 합니다.',
    risk: '물가만 오르고 성장이 꺾이면 스태그플레이션으로 악화될 수 있습니다.',
  },
  Stagflation: {
    one: '성장은 둔화하는데 물가 압력은 커지는, 주식과 채권 모두 까다로운 국면입니다.',
    watch: '퀄리티·저변동·현금흐름과 실물자산 방어력을 우선 확인합니다.',
    risk: '에너지 충격, 임금·서비스 물가, 신용 스프레드 확대가 핵심 위험입니다.',
  },
  'Deflation/Slowdown': {
    one: '성장과 물가가 함께 둔화하는 국면으로 경기민감 자산의 이익 기대가 약해질 수 있습니다.',
    watch: '장기채·퀄리티 방어가 상대적으로 유리할 수 있지만 신용 악화를 확인해야 합니다.',
    risk: '침체가 깊어질 경우 실적 하향과 디폴트 위험이 커집니다.',
  },
  'Transition/Low confidence': {
    one: '성장·물가 신호가 엇갈리거나 데이터 신뢰가 낮아 국면을 단정하지 않는 상태입니다.',
    watch: '한 번의 숫자보다 다음 2~3회 발표에서 같은 방향이 이어지는지 확인합니다.',
    risk: '확신이 낮은 구간에서 과도한 자산배분 변경을 피합니다.',
  },
};
const INDEX_GUIDE = {
  '^KS11': '한국 유가증권시장 대표 지수입니다. 대형 수출주와 반도체 비중이 커 원/달러, 글로벌 제조업, 메모리 업황의 영향을 크게 받습니다.',
  '^KQ11': '한국 성장주·중소형주 비중이 큰 시장 지수입니다. 금리와 유동성, 바이오·2차전지·IT 투자심리에 민감합니다.',
  '^GSPC': '미국 대형주 500개를 담은 대표 지수입니다. 미국 기업이익과 글로벌 위험선호의 핵심 기준입니다.',
  '^IXIC': '기술·성장주 비중이 높은 나스닥 종합지수입니다. 장기금리와 AI·반도체 이익 기대에 민감합니다.',
  '^DJI': '미국 우량 대형주 30개로 구성된 가격가중 지수입니다. 전통 산업과 경기민감주의 흐름을 함께 봅니다.',
  '^SOX': '미국 상장 주요 반도체 기업 지수입니다. AI 투자, 메모리·파운드리 업황, 공급망 사이클을 빠르게 반영합니다.',
  '^VIX': 'S&P 500 옵션이 반영하는 향후 약 30일 기대 변동성입니다. 높을수록 시장 불안이 크지만 방향 예측값은 아닙니다.',
  'KRW=X': '1달러를 사는 데 필요한 원화입니다. 상승은 원화 약세, 하락은 원화 강세를 뜻합니다.',
  'DX-Y.NYB': '주요 통화 대비 미국 달러의 강도를 나타냅니다. 강달러는 글로벌 유동성과 신흥시장에 부담이 될 수 있습니다.',
  'BTC-USD': '비트코인의 미국 달러 가격입니다. 24시간 거래돼 주식시장 휴장 중 위험선호 변화도 반영합니다.',
  'GC=F': '국제 금 선물 가격입니다. 실질금리, 달러, 안전자산 수요의 영향을 받습니다.',
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
  consensus: ['전문가 컨센서스', '공식 원문을 사람이 확인한 기관 전망은 <b>검증 완료</b>로 요약·집계하고, 새로 발견됐지만 아직 검토하지 않은 자료도 숨기지 않고 <b>모니터링 중</b>으로 분리해 보여줍니다. 집계는 weighted median과 의견 분산을 사용하며, 기관·연구팀별 최대 한 표만 반영합니다.'],
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
  indices: ['글로벌 마켓', '하루 두 번 자동 빌드하고 열린 화면도 15분마다 새 배포 데이터를 확인합니다. 코스피·코스닥은 Yahoo와 FinanceDataReader를 교차 확인하며, 가능한 글로벌 지표는 Stooq를 보조 수집원으로 사용합니다. 각 카드의 날짜·최신 상태를 확인하고 클릭하면 1년 추이와 세부 설명을 볼 수 있습니다.'],
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
  const ixRange = e.target.closest('[data-index-range]');
  if (ixRange) { e.preventDefault(); setIndexRange(ixRange.dataset.indexRange); return; }
  const ix = e.target.closest('[data-index-symbol]');
  if (ix) { e.preventDefault(); showIndexDialog(ix.dataset.indexSymbol); return; }
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
  const mh = d.marketDataHealth || {};
  const dataMode = d.dataMode || p.dataMode || 'unknown';
  const runMode = d.runMode || p.runMode || 'paperTrading';
  const dmCls = dataMode === 'live' ? 'ok' : 'warn';
  const blocked = d.recommendationsBlocked;
  const chips = [
    chip('데이터 모드', dataMode, dmCls),
    chip('시장 기준일', p.marketAsOf || m.latestDataDate || '—'),
    chip('시장 지표', `${mh.current ?? m.indicesCurrent ?? '—'}/${mh.fetched ?? m.indicesFetched ?? '—'} 최신`, mh.status === 'CURRENT' ? 'ok' : 'warn'),
    chip('커버리지', (m.coveragePct != null ? m.coveragePct + '%' : '—') + (m.coverageFloor ? ` / ≥${m.coverageFloor}%` : ''), (m.coveragePct >= (m.coverageFloor || 95)) ? 'ok' : 'warn'),
    chip('매크로 커버리지', m.macroCoverage != null ? Math.round(m.macroCoverage * 100) + '%' : '—', (m.macroCoverage >= 0.5) ? 'ok' : 'warn'),
    chip('추천 상태', blocked ? '차단(액션·비중 숨김)' : '표시', blocked ? 'bad' : 'ok'),
  ];
  const technical = [
    chip('runMode', runMode, runMode === 'liveValidated' ? 'ok' : 'info'),
    chip('빌드 SHA', p.buildCommitSha || '—', 'info'),
    chip('스키마', p.schemaVersion || d.schemaVersion || '—', 'info'),
    chip('모델', p.modelVersion || d.modelVersion || '—', 'info'),
    chip('sourceAsOf', p.sourceAsOf || m.sourceAsOf || '—'),
    chip('모델 학습', (m.modelsTrained || 0) + '회', (m.modelsTrained > 0) ? 'ok' : 'warn'),
  ].join('');
  $('#statusPanel').innerHTML = chips.join('') +
    `<details class="status-tech"><summary>감사·모델 세부정보</summary><div>${technical}</div></details>` +
    (mh.status && mh.status !== 'CURRENT' ? `<div class="status-note warn">시장 데이터 일부가 늦습니다. 지수별 카드의 관측일과 수집원을 확인하세요.${(mh.staleCritical || []).length ? ` 오래된 핵심 지수: ${mh.staleCritical.join(', ')}` : ''}</div>` : '') +
    (blocked ? `<div class="status-note bad">⚠️ ${(d.blockReasons || []).join(' · ') || '데이터 안전 차단'} — 이 데이터로 매매하지 마세요.</div>` : '') +
    (dataMode !== 'live' ? `<div class="status-note warn">데이터 모드 <b>${dataMode}</b>: 예시/합성/오래된 데이터입니다. 실데이터 빌드는 Yahoo/FRED 네트워크 + FRED_API_KEY가 필요합니다.</div>` : '');
};

// =========================================================================
// 2. Macro regime & risk budget
// =========================================================================
const macroNumber = (v, unit = '') => {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  const digits = Math.abs(v) >= 100 ? 0 : 2;
  return `${Number(v).toLocaleString('ko-KR', { maximumFractionDigits: digits })}${unit ? ' ' + unit : ''}`;
};
const trendSvg = (series, references = [], opts = {}) => {
  const width = opts.width || 560, height = opts.height || 150;
  const pad = { l: 42, r: 14, t: 12, b: 25 };
  const clean = (series || []).map((s) => ({
    ...s,
    points: (s.points || []).filter((p) => p && Number.isFinite(Number(p.value)) && p.date),
  })).filter((s) => s.points.length);
  if (!clean.length) return '<div class="chart-none">추이 데이터가 아직 없습니다.</div>';
  const allPoints = clean.flatMap((s) => s.points);
  const times = allPoints.map((p) => new Date(`${p.date}T00:00:00Z`).getTime());
  const values = allPoints.map((p) => Number(p.value)).concat((references || []).map((r) => Number(r.value)).filter(Number.isFinite));
  const minT = Math.min(...times), maxT = Math.max(...times), timeSpan = maxT - minT || 1;
  let minV = Math.min(...values), maxV = Math.max(...values);
  const valueSpan = maxV - minV || Math.max(Math.abs(maxV), 1);
  minV -= valueSpan * 0.12; maxV += valueSpan * 0.12;
  const x = (date) => pad.l + ((new Date(`${date}T00:00:00Z`).getTime() - minT) / timeSpan) * (width - pad.l - pad.r);
  const y = (value) => pad.t + ((maxV - Number(value)) / (maxV - minV || 1)) * (height - pad.t - pad.b);
  const grid = [0, 0.5, 1].map((f) => {
    const yy = pad.t + f * (height - pad.t - pad.b);
    const val = maxV - f * (maxV - minV);
    return `<line x1="${pad.l}" y1="${yy.toFixed(1)}" x2="${width - pad.r}" y2="${yy.toFixed(1)}" class="chart-grid"/><text x="${pad.l - 6}" y="${(yy + 3).toFixed(1)}" text-anchor="end" class="chart-axis">${macroNumber(val)}</text>`;
  }).join('');
  const refLines = (references || []).map((r) => {
    const yy = y(r.value);
    return `<line x1="${pad.l}" y1="${yy.toFixed(1)}" x2="${width - pad.r}" y2="${yy.toFixed(1)}" class="chart-ref"><title>${r.labelKo || r.value}</title></line>`;
  }).join('');
  const lines = clean.map((s, idx) => {
    const points = s.points.map((p) => `${x(p.date).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ');
    return `<polyline points="${points}" class="chart-line chart-line-${idx}" vector-effect="non-scaling-stroke"><title>${s.label || ''}</title></polyline>`;
  }).join('');
  const first = allPoints.reduce((a, b) => a.date < b.date ? a : b);
  const last = allPoints.reduce((a, b) => a.date > b.date ? a : b);
  const dateLabel = (v) => v ? v.slice(2, 7).replace('-', '.') : '';
  return `<svg class="trend-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${opts.aria || '기간별 추이 차트'}">${grid}${refLines}${lines}<text x="${pad.l}" y="${height - 5}" class="chart-axis">${dateLabel(first.date)}</text><text x="${width - pad.r}" y="${height - 5}" text-anchor="end" class="chart-axis">${dateLabel(last.date)}</text></svg>`;
};
const indicatorTrend = (i) => {
  const lines = [{ label: i.historyLabelKo || i.displayNameKo, points: i.history || [] }];
  if (i.trendHistory && i.trendHistory.length) lines.push({ label: i.trendLabelKo || '추세', points: i.trendHistory });
  const legend = lines.filter((x) => x.points.length).map((x, idx) => `<span><i class="chart-key chart-key-${idx}"></i>${x.label}</span>`).join('');
  return `<div class="indicator-chart">${trendSvg(lines, i.referenceLines || [], { width: 520, height: 132, aria: `${i.displayNameKo || i.name} 추이` })}<div class="chart-legend">${legend}</div></div>`;
};
const indicatorCard = (i, axis) => {
  const contribution = i.axisContribution ?? 0;
  const cls = contribution > 0 ? 'bull' : contribution < 0 ? 'bear' : 'trans';
  const stale = i.stale ? '<span class="ax-stale">STALE</span>' : '';
  const isReturn = i.transformation === 'three_month_price_return';
  const transformed = isReturn && i.transformedValue != null ? i.transformedValue * 100 : i.transformedValue;
  const change = isReturn && i.change != null ? i.change * 100 : i.change;
  return `<article class="ax-signal">
    <div class="ax-signal-top"><div><b>${i.displayNameKo || i.name}</b><small>${i.name}</small></div><span class="reg ${cls}">${axis.ko} ${i.axisContributionKo || (contribution > 0 ? '긍정' : contribution < 0 ? '부정' : '중립')}</span></div>
    <p class="ax-method">${i.transformationKo || i.transformation || '최근 변화'}</p>
    <p class="ax-reading">${i.signalSummaryKo || '세부 판정 설명은 다음 빌드에서 제공됩니다.'}</p>
    ${indicatorTrend(i)}
    <dl class="ax-numbers">
      <div><dt>변환값</dt><dd>${macroNumber(transformed, i.valueUnit)}</dd></div>
      <div><dt>최근 변화</dt><dd>${macroNumber(change, i.changeUnit)}</dd></div>
      ${i.annualized3m != null ? `<div><dt>3개월 연율</dt><dd>${macroNumber(i.annualized3m, '%')}</dd></div>` : ''}
      <div><dt>장기 z</dt><dd>${macroNumber(i.zscore)}</dd></div>
    </dl>
    <details class="indicator-guide">
      <summary>이 지표는 무엇을 뜻하나?</summary>
      <div><p><b>정의</b>${i.guide?.meaningKo || '여러 국면 근거 중 하나로 사용하는 경제 지표입니다.'}</p><p><b>읽는 법</b>${i.guide?.readKo || i.transformationKo || ''}</p><p><b>투자에서</b>${i.guide?.useKo || `${axis.ko} 축의 보조 근거로 봅니다.`}</p><p><b>주의</b>${i.guide?.cautionKo || '단일 지표만으로 시장 방향을 단정하지 않습니다.'}</p></div>
    </details>
    <div class="ax-source"><span>관측 ${i.observationDate || '—'} · 발표시차 ${i.releaseLagBdays ?? '—'}영업일 · 경과 ${i.freshnessDays ?? '—'}일 ${stale}</span>${i.source ? `<a href="${i.source}" target="_blank" rel="noopener">원자료</a>` : ''}</div>
  </article>`;
};
const axisRow = (a, key) => {
  const v = a.value; const dirCls = v == null ? 'trans' : v > 0.15 ? 'bull' : v < -0.15 ? 'bear' : 'trans';
  const w = v == null ? 0 : Math.min(50, Math.abs(v) * 50);
  const direct = key === 'growth' || key === 'inflation';
  const indicators = (a.indicators || []).map((i) => indicatorCard(i, a)).join('') || '<div class="ax-none">사용 가능한 지표가 없습니다.</div>';
  return `<details class="ax-detail" ${direct ? 'open' : ''}>
    <summary><div class="ax-row">
      <span class="ax-name">${a.ko}</span>
      <span class="ax-bar"><i class="${v >= 0 ? 'apos' : 'aneg'}" style="${v >= 0 ? 'left:50%' : 'right:50%'};width:${w}%"></i></span>
      <span class="ax-lab reg ${dirCls}">${a.labelKo}</span>
      <span class="ax-conf muted">점수 ${v == null ? '—' : Number(v).toFixed(2)} · 커버 ${Math.round((a.coverage ?? 0) * 100)}% · 신선도 ${Math.round((a.freshness ?? 0) * 100)}% · 합의 ${Math.round((a.agreement ?? 0) * 100)}%</span>
      <span class="ax-toggle">${direct ? '판정에 직접 사용' : '위험예산 보조'} · ${a.nIndicators ?? 0}개 ▾</span>
    </div></summary>
    <div class="ax-signals">${indicators}</div>
  </details>`;
};
const regimeDecisionCard = (r) => {
  const d = r.regimeDecision || {};
  const g = d.growth || (r.axes || {}).growth || {};
  const i = d.inflation || (r.axes || {}).inflation || {};
  const summary = d.summaryKo || '성장과 물가 축의 방향·신뢰도를 조합해 국면을 판단합니다.';
  return `<div class="regime-decision">
    <div><span class="rb-h">왜 이 국면인가</span><b>${summary}</b></div>
    <div class="decision-axes">
      <span>성장 <b>${g.labelKo || '데이터 부족'} ${g.value == null ? '' : `(${Number(g.value).toFixed(2)})`}</b><em>신뢰 ${Math.round((g.confidence ?? 0) * 100)}%</em></span>
      <span>물가 <b>${i.labelKo || '데이터 부족'} ${i.value == null ? '' : `(${Number(i.value).toFixed(2)})`}</b><em>신뢰 ${Math.round((i.confidence ?? 0) * 100)}%</em></span>
    </div>
    <p>${d.confidenceRuleKo || '국면 신뢰도는 성장·물가 중 낮은 축 신뢰도입니다.'} · 방향 중립구간 ±${d.thresholds?.directionAbsMin ?? 0.15} · 최소 신뢰 ${Math.round((d.thresholds?.minimumConfidence ?? 0.34) * 100)}%</p>
    <small>${d.matrixKo || '성장×물가 조합으로 네 국면을 판정하며, 한 축이 중립이면 전환으로 보류합니다.'}</small>
  </div>`;
};
const regimeGuideCard = (r) => {
  const key = r.regime || 'Transition/Low confidence';
  const g = REGIME_GUIDE[key] || REGIME_GUIDE['Transition/Low confidence'];
  const cell = (regime, growth, inflation) => `<div class="cycle-cell ${key === regime ? 'active' : ''}"><span>${growth} 성장 · ${inflation} 물가</span><b>${REGIME_KO[regime] || regime}</b></div>`;
  return `<div class="regime-guide">
    <div class="rg-copy"><span>지금 국면을 한 문장으로</span><h3>${g.one}</h3><p><b>볼 것</b>${g.watch}</p><p><b>핵심 위험</b>${g.risk}</p></div>
    <div class="cycle-wrap"><div class="cycle-caption">성장 × 물가 국면 지도</div><div class="cycle-grid">${cell('Goldilocks', '가속', '둔화')}${cell('Reflation', '가속', '가속')}${cell('Deflation/Slowdown', '둔화', '둔화')}${cell('Stagflation', '둔화', '가속')}</div><small>강조된 칸이 현재 판정입니다. 신호가 엇갈리면 전환·저신뢰로 보류합니다.</small></div>
  </div>`;
};
const renderRegime = (r) => {
  const host = $('#regimePanel'); const sec = $('#regime');
  if (!r) { sec.hidden = true; return; }
  sec.hidden = false;
  $('#regimeMeta').textContent = `${r.asOf ? '기준 ' + r.asOf + ' · ' : ''}지표 ${r.indicatorCount ?? 0}개 · 커버리지 ${Math.round((r.coverage ?? 0) * 100)}%`;
  const rb = r.riskBudget || {};
  const changed = r.changed ? `<span class="chg">← ${REGIME_KO[r.priorRegime] || r.priorRegime}에서 전환</span>` : '';
  const axesHtml = Object.entries(r.axes || {}).map(([key, axis]) => axisRow(axis, key)).join('');
  const support = (r.supporting || []).map((s) => `<span class="ev ev-pos">${s.name}</span>`).join('') || '<span class="muted">—</span>';
  const contra = (r.contradicting || []).map((s) => `<span class="ev ev-neg">${s.name}</span>`).join('') || '<span class="muted">—</span>';
  host.innerHTML = `
    <div class="regime-head">
      <div class="regime-label reg ${r.regime && r.regime.startsWith('Transition') ? 'trans' : (r.regime === 'Goldilocks' || r.regime === 'Reflation') ? 'bull' : 'bear'}">${r.regimeDecision?.displayLabelKo || REGIME_KO[r.regime] || r.regime}</div>
      <div class="regime-conf">국면 판정 신뢰 <b>${Math.round((r.confidence ?? 0) * 100)}%</b> ${changed}</div>
      ${r.note ? `<div class="status-note warn">${r.note}</div>` : ''}
      ${r.pointInTimeLimitations ? `<div class="status-note info">한계: ${r.pointInTimeLimitations}</div>` : ''}
    </div>
    ${regimeGuideCard(r)}
    ${regimeDecisionCard(r)}
    <div class="regime-axes">${axesHtml}</div>
    <div class="regime-lower">
      <div class="regime-budget">
        <div class="rb-h">위험예산 (매크로 레이어 — 개별 알파에 가산하지 않음)</div>
        <div class="rb-row"><span>주식 노출</span><b>${(rb.equityRangePct || []).join('~')}%</b><span>현금</span><b>${(rb.cashRangePct || []).join('~')}%</b></div>
        <div class="rb-tilt muted">스타일 틸트: ${rb.styleTilt || '—'}</div>
      </div>
      <div class="regime-ev"><div><span class="evh">근거</span>${support}</div><div><span class="evh">반대 근거</span>${contra}</div></div>
    </div>`;
};

// =========================================================================
// 3. Expert consensus
// =========================================================================
const stanceKo = (s) => s == null ? '—' : s >= 1 ? `강한 긍정 (+${s})` : s > 0 ? `긍정 (+${s})` : s === 0 ? '중립 (0)' : s <= -1 ? `강한 부정 (${s})` : `부정 (${s})`;
const THEME_KO = {
  'AI/Semiconductors': 'AI·반도체', 'US Growth': '미국 성장', 'Rates/Inflation': '금리·물가',
  'Credit Quality': '신용 품질', Korea: '한국 경제',
};
const themeCard = (t) => {
  const agr = { high: ['합의 강함', 'bull'], mixed: ['혼재', 'trans'], low: ['의견 갈림', 'bear'], insufficient: ['1개 기관·합의 불가', 'trans'] }[t.agreement] || ['—', 'trans'];
  const views = (t.views || []).map((v) => `<div class="cv-view"><div><span>${v.institution}${v.sourceType === 'companyIR' ? ' <em class="ir">IR</em>' : ''}</span><small>공식 원문 검토 완료 · ${v.publishedAt ? v.publishedAt.slice(0, 10) : '발행일 미상'}${v.ageDays != null ? ` · ${v.ageDays}일 경과` : ''}</small></div><b>${stanceKo(v.stance)}</b>${v.url ? `<a href="${v.url}" target="_blank" rel="noopener">공식 원문 ↗</a>` : ''}${v.summary ? `<p>${v.summary}</p>` : ''}</div>`).join('');
  return `<div class="cv-card">
    <div class="cv-top"><div><span class="cv-verified">검증 완료</span><b>${THEME_KO[t.theme] || t.theme}</b></div><span class="reg ${agr[1]}">${agr[0]}</span></div>
    <div class="cv-meta">중앙값 스탠스 <b>${stanceKo(t.weightedMedianStance)}</b> · 분산 ${fmt(t.dispersion)} · 기관 ${t.institutionCount}곳</div>
    <div class="cv-views">${views}</div>
    ${t.counterCase ? `<div class="cv-counter">반대 논거: ${t.counterCase}</div>` : ''}
  </div>`;
};
const MISSING_FIELD_KO = { publishedAt: '발행일', verifiedAt: '검증일', stance: '방향 점수', summary: '검증 요약', verified: '검증 승인' };
const awaitingCard = (a) => {
  const missing = a.missingFields || ['publishedAt', 'verifiedAt', 'stance', 'summary', 'verified'];
  const risks = (a.risks || []).map((x) => `<span>${x}</span>`).join('') || '<span>등록 없음</span>';
  const signposts = (a.signposts || []).map((x) => `<span>${x}</span>`).join('') || '<span>등록 없음</span>';
  return `<article class="cv-pending">
    <div class="cv-pending-head"><div><b>${a.institution}</b><small>${a.theme || '주제 미분류'} · ${a.horizon || '기간 미정'}</small></div><span>${a.statusKo || '원문 검증 대기'}</span></div>
    <p class="cv-title">${a.title || '기관 전망 원문'}</p>
    <div class="cv-missing"><b>컨센서스 제외 사유</b>${missing.map((x) => `<em>${MISSING_FIELD_KO[x] || x} 없음</em>`).join('')}</div>
    <div class="cv-watch"><div><b>검증할 위험요인</b>${risks}</div><div><b>확인할 지표</b>${signposts}</div></div>
    ${a.url ? `<a class="cv-source" href="${a.url}" target="_blank" rel="noopener">공식 원문 확인 →</a>` : ''}
  </article>`;
};
const renderConsensus = (c) => {
  const host = $('#consensusPanel'); const sec = $('#consensus');
  if (!c) { sec.hidden = true; return; }
  sec.hidden = false;
  const candidates = c.candidateCount ?? (c.awaitingVerification || []).length + (c.verifiedCount || 0) + (c.staleCount || 0);
  $('#consensusMeta').textContent = `검증 ${c.verifiedCount ?? 0}/${candidates}건 · 대기 ${c.awaitingCount ?? (c.awaitingVerification || []).length}건 · STALE ${c.staleCount ?? 0}건`;
  let html = '';
  if (c.themes && c.themes.length) html += `<div class="cv-method"><b>검증된 공식 전망 ${c.verifiedCount ?? 0}건</b><span>스탠스는 위험자산 관점 -2(방어적)~+2(건설적) 척도입니다. 요약은 원문을 대체하지 않으며, 기관 수가 1곳이면 ‘합의’로 보지 않습니다.</span></div>` + c.themes.map(themeCard).join('');
  else html += `<div class="cv-empty">
    <div><span>검증 커버리지</span><b>${Math.round((c.verificationCoverage ?? 0) * 100)}%</b></div>
    <section><h3>검증된 컨센서스가 아직 없는 이유</h3><p>${c.note || '등록 후보가 모두 원문 검증 전이라 방향을 집계하지 않습니다.'}</p><small>빈 화면이나 수집 오류가 아닙니다. 미검증 자료의 스탠스를 추정하지 않는 안전장치입니다.</small></section>
    <ol>${(c.verificationStepsKo || ['공식 원문과 발행일 확인', '스탠스·요약 기록', 'verified=true 승인', '기관 중복 제거 후 집계']).map((x) => `<li>${x}</li>`).join('')}</ol>
  </div>`;
  if (c.awaitingVerification && c.awaitingVerification.length) {
    html += `<div class="cv-await"><div class="cv-await-title"><b>새 자료 모니터링 중 ${c.awaitingVerification.length}건</b><span>숨기지 않고 보여주되, 원문 검토 전에는 컨센서스 수치에 넣지 않습니다.</span></div><div class="cv-pending-grid">${c.awaitingVerification.map(awaitingCard).join('')}</div></div>`;
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

// 5. Auditable model portfolio (risk-weighted base + shadow Fractional Kelly)
const renderModelPortfolio = (d) => {
  const mp = d.modelPortfolio; const sec = $('#modelPortfolio'); const host = $('#modelPortfolioPanel');
  if (!mp) { sec.hidden = true; return; }
  sec.hidden = false;
  const status = mp.status || 'SHADOW_INSUFFICIENT_HISTORY';
  $('#modelPortfolioMeta').textContent = `${status} · 현금 ${mp.cashPct != null ? mp.cashPct + '%' : '—'} · Kelly ${mp.appliedKellyFraction != null ? (mp.appliedKellyFraction * 100).toFixed(1) + '%' : '—'}`;
  if (d.recommendationsBlocked || status === 'BLOCKED') {
    host.innerHTML = '<div class="status-note bad">데이터 안전 차단 상태입니다. 모델 비중과 행동성 설명을 표시하지 않습니다.</div>';
    return;
  }
  const shadow = status.startsWith('SHADOW') || status === 'OPTIMIZATION_FAILED';
  const chips = [
    chip('상태', status, status === 'SHADOW_READY' ? 'info' : 'warn'),
    chip('방법', '위험가중 75% + Kelly 25%', 'info'),
    chip('현금', mp.cashPct != null ? `${mp.cashPct}%` : '—'),
    chip('예상 변동성', mp.expectedVolPct != null ? `${mp.expectedVolPct}%` : '—'),
    chip('회전율', mp.turnoverPct != null ? `${mp.turnoverPct}%` : '—'),
    chip('기대수익 검증', mp.expectedReturnStatus || 'INSUFFICIENT', mp.expectedReturnStatus === 'SHADOW' ? 'info' : 'warn'),
  ].join('');
  const rows = (mp.positions || []).filter((p) => p.modelPortfolioWeightPct > 0);
  const table = rows.length ? `<div class="mp-table"><div class="mp-row mp-head"><span>종목</span><span>지역</span><span>알파</span><span>기대 초과수익</span><span>위험</span><span>기존</span><span>Kelly</span><span>최종</span><span>진입</span><span>제약</span></div>${rows.map((p) => {
    const bindings = (p.bindingConstraints || []).map((x) => x.replaceAll('_', ' ')).join(' · ') || '없음';
    return `<div class="mp-row"><span>${tkLink(p.ticker)}</span><span>${p.region || '—'}</span><span>${topPct(p.alphaPercentile)}</span><span>${p.expectedReturnStatus === 'SHADOW' ? sp(p.expectedExcessReturnPct) : '검증 대기'}<small>n=${p.expectedReturnSampleSize || 0}</small></span><span>${p.riskLevel != null ? p.riskLevel + '%' : '—'}</span><span>${fmt(p.riskWeightedWeightPct, '%', 1)}</span><span>${fmt(p.constrainedKellyWeightPct, '%', 1)}</span><span><b>${fmt(p.modelPortfolioWeightPct, '%', 1)}</b></span><span>${p.entryState || '—'}</span><span class="mp-why">${bindings}</span></div>`;
  }).join('')}</div>` : '<div class="none">표시할 투자 비중 없음 — 기존 위험가중 방식 또는 현금으로 fallback</div>';
  const exposure = (title, values) => `<div class="mp-exp"><b>${title}</b>${Object.entries(values || {}).sort((a, b) => b[1] - a[1]).map(([k, v]) => `<span>${k}<em>${v}%</em></span>`).join('') || '<span>데이터 없음</span>'}</div>`;
  const reason = mp.fallbackReason ? `<div class="status-note warn"><b>Fallback:</b> ${mp.fallbackReason}<br>검증되지 않은 기대수익을 만들지 않고 기존 역하방변동성 포트폴리오를 유지합니다.</div>` : '';
  host.innerHTML = `<div class="mp-chips">${chips}</div>${reason}${shadow ? '<div class="status-note info">검증 이력이 충분하지 않아 Kelly 비중은 실험적 shadow 결과로만 표시됩니다. 현재 기본 포트폴리오는 기존 역하방변동성 방식입니다.</div>' : ''}${table}<div class="mp-exposures">${exposure('지역', mp.regionExposure)}${exposure('업종', mp.sectorExposure)}${exposure('테마', mp.themeExposure)}</div><p class="caveat muted">이 비중은 개인 투자자의 자산규모·소득·부채·투자기간을 반영한 개인화 투자 권고가 아니라, 가상 모델 포트폴리오 내부의 연구용 비중입니다.</p>`;
};

// 6. Entry & risk warnings (aggregated)
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
let ACTIVE_INDEX = null;
let INDEX_RANGE = '1Y';
const INDEX_RANGES = { '1M': 22, '3M': 66, '6M': 132, '1Y': 260 };
const ixFresh = (x) => {
  const cls = x.freshnessStatus === 'CURRENT' ? 'current' : x.freshnessStatus === 'DELAYED' ? 'delayed' : 'stale';
  return `<span class="ix-fresh ${cls}"><i></i>${x.freshnessLabelKo || '상태 미상'} · ${x.asOf || '—'}</span>`;
};
const ixTile = (x) => {
  const d1 = x.chg1dPct; const dir = d1 == null ? '' : d1 >= 0 ? 'pos' : 'neg';
  return `<button type="button" class="ix" data-index-symbol="${x.symbol}" aria-label="${x.name} 상세 차트 열기" title="${x.symbol} · ${x.asOf ?? ''} · ${x.source ?? ''}"><div class="ix-h"><span class="ix-name">${x.name}</span><span class="ix-reg">${x.region}</span></div><div class="ix-quote"><span class="ix-last">${nfmt(x.last, x.digits ?? 2)}</span><span class="ix-chg ${dir}">${chg(d1)}</span></div>${sparkSvg(x.spark)}<div class="ix-sub"><span>1M <b class="${(x.chg1mPct ?? 0) >= 0 ? 'pos' : 'neg'}">${chg(x.chg1mPct, 1)}</b></span><span>YTD <b class="${(x.ytdPct ?? 0) >= 0 ? 'pos' : 'neg'}">${chg(x.ytdPct, 1)}</b></span><span>고점비 <b>${chg(x.from52wHighPct, 1)}</b></span></div>${ixFresh(x)}<span class="ix-open">상세 추이 보기 →</span></button>`;
};
const renderIndices = (d) => {
  const sec = $('#indices'); const list = d.indices || [];
  if (!list.length) { sec.hidden = true; return; }
  sec.hidden = false;
  $('#indexTape').innerHTML = list.map(ixTile).join('');
  const h = d.marketDataHealth || {};
  const status = h.status === 'CURRENT' ? '전체 최신' : h.status === 'DELAYED' ? '일부 지연' : '확인 필요';
  $('#tapeMeta').textContent = `${status} · 최신 ${h.current ?? '—'}/${h.fetched ?? list.length} · 카드 클릭 시 1년 추이`;
};
const indexDialogMarkup = (x) => {
  const points = (x.history || []).slice(-(INDEX_RANGES[INDEX_RANGE] || 260));
  const first = points[0]?.value, last = points[points.length - 1]?.value;
  const rangeChange = first != null && last != null && Number(first) !== 0 ? (Number(last) / Number(first) - 1) * 100 : null;
  const rangeButtons = Object.keys(INDEX_RANGES).map((r) => `<button type="button" data-index-range="${r}" class="${INDEX_RANGE === r ? 'active' : ''}">${r}</button>`).join('');
  const sourceList = (x.sourcesChecked || [x.source]).filter(Boolean).join(' · ');
  return `<div class="ix-dialog-head"><div><span class="overline">${x.region} · ${x.symbol}</span><h2>${x.name}</h2><p>${INDEX_GUIDE[x.symbol] || '시장 수준과 추세를 보여주는 주요 지표입니다.'}</p></div><div class="ix-dialog-quote"><b>${nfmt(x.last, x.digits ?? 2)}</b><span class="${(rangeChange ?? 0) >= 0 ? 'pos' : 'neg'}">${INDEX_RANGE} ${chg(rangeChange, 1)}</span></div></div>
    <div class="ix-range" aria-label="차트 기간">${rangeButtons}</div>
    <div class="ix-big-chart">${trendSvg([{ label: x.name, points }], [], { width: 900, height: 300, aria: `${x.name} ${INDEX_RANGE} 가격 추이` })}</div>
    <div class="ix-kpis"><div><span>1일</span><b class="${(x.chg1dPct ?? 0) >= 0 ? 'pos' : 'neg'}">${chg(x.chg1dPct)}</b></div><div><span>1개월</span><b class="${(x.chg1mPct ?? 0) >= 0 ? 'pos' : 'neg'}">${chg(x.chg1mPct)}</b></div><div><span>연초 대비</span><b class="${(x.ytdPct ?? 0) >= 0 ? 'pos' : 'neg'}">${chg(x.ytdPct)}</b></div><div><span>52주 고점 대비</span><b>${chg(x.from52wHighPct)}</b></div><div><span>200일선</span><b>${x.above200d == null ? '—' : x.above200d ? '위 · 상승 추세' : '아래 · 약세 추세'}</b></div></div>
    <div class="ix-data-note">${ixFresh(x)}<span>현재 소스 <b>${x.source || '—'}</b></span><span>교차 확인 <b>${sourceList || '—'}</b></span><span>영업일 지연 <b>${x.freshnessBdays ?? '—'}일</b></span></div>`;
};
const showIndexDialog = (symbol) => {
  const x = (DATA.indices || []).find((row) => row.symbol === symbol);
  const dialog = $('#indexDialog'); const body = $('#indexDialogBody');
  if (!x || !dialog || !body) return;
  ACTIVE_INDEX = x; INDEX_RANGE = '1Y';
  body.innerHTML = indexDialogMarkup(x);
  if (typeof dialog.showModal === 'function') dialog.showModal(); else dialog.setAttribute('open', '');
};
const setIndexRange = (range) => {
  if (!ACTIVE_INDEX || !INDEX_RANGES[range]) return;
  INDEX_RANGE = range;
  const body = $('#indexDialogBody');
  if (body) body.innerHTML = indexDialogMarkup(ACTIVE_INDEX);
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
  renderModelPortfolio(d);
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

const loadData = async (force = false) => {
  const button = $('#refreshData');
  if (button) { button.disabled = true; button.textContent = '확인 중…'; }
  try {
    const url = `data/site-data.json${force ? `?t=${Date.now()}` : ''}`;
    const r = await fetch(url, { cache: 'no-store' });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    render(await r.json());
    if (button) button.textContent = '최신 데이터 확인';
  } catch (e) {
    $('#dataStatus').textContent = 'data error: ' + e.message;
    if (button) button.textContent = '다시 확인';
  } finally {
    if (button) button.disabled = false;
  }
};
const filterScreen = () => {
  const q = ($('#screenSearch')?.value || '').trim().toLowerCase();
  const rows = document.querySelectorAll('#screenTable .srow:not(.sh)'); let shown = 0;
  rows.forEach((r) => { const hit = !q || (r.dataset.key || '').includes(q); r.style.display = hit ? '' : 'none'; if (hit) shown++; });
  const empty = $('#screenEmpty'); if (empty) empty.hidden = shown !== 0;
};
$('#screenSearch')?.addEventListener('input', filterScreen);
$('#refreshData')?.addEventListener('click', () => loadData(true));
$('#indexDialogClose')?.addEventListener('click', () => $('#indexDialog')?.close());
$('#indexDialog')?.addEventListener('click', (e) => { if (e.target.id === 'indexDialog') e.target.close(); });
document.querySelectorAll('.nav a[href^="#"]').forEach((a) => a.addEventListener('click', (e) => {
  const t = document.querySelector(a.getAttribute('href')); if (!t) return;
  e.preventDefault();
  if (t.tagName === 'DETAILS') t.open = true;
  t.scrollIntoView({ behavior: 'smooth', block: 'start' });
}));
loadRules(); loadData();
window.setInterval(() => loadData(false), 15 * 60 * 1000);