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
  trade: ['오늘의 핵심 액션', '국내·국외 유니버스를 트레이드 호라이즌(기본 10영업일)으로 스크리닝해, <b>비용을 넘는 기대값(edge)</b>이 양수이고 확신 하한(확률 0.55)·국면(하락장 제외)을 만족하는 종목만 매수 후보로 올립니다. 후보가 없으면 “관망”이 결론입니다.<br><br><b>한계:</b> 수백 종목 동시 스캔은 우연한 고득점(다중검정 거짓양성)을 만듭니다 → 상위 1~2개만, 분산. 유니버스는 현재 상장 종목 기준이라 상장폐지 종목이 빠진 생존편향이 있습니다.'],
  core: ['추적 종목', 'core 목록은 공개 저장소에 수량·평균단가가 없는 관심/추적 종목입니다. 품질 게이트 통과 전 모델 점수는 매매에 사용하지 않습니다.'],
  macro: ['매크로', 'FRED에서 국외(미국 10Y·2Y·금리차·기준금리·하이일드 스프레드·VIX)와 국내(원/달러·국고채 10Y·3M·금리차)를 받아 위험 플래그를 띄웁니다. 개별 종목보다 먼저 점검합니다.'],
  sentiment: ['공포 · 탐욕 지수', 'CNN 공포·탐욕 지수처럼 <b>실데이터로 시장 심리</b>를 0~100으로 계산합니다. 유니버스 200·50일선 위 비중·상승국면 비중·중앙값 모멘텀 + 매크로(VIX·신용스프레드·원화)를 가중합한 <b>휴리스틱 지수</b>(확률이 아님)입니다. 구성 지표가 사실상 모멘텀 한 방향에 겹치므로 종목 확률과 별개의 보조 신호로만 보세요. 탐욕 과열은 추격 주의, 극도의 공포는 역발상 기회일 수 있습니다.'],
  prob: ['모델 점수 / 확률 해석 불가', '가격·추세·변동성·상대강도·매크로 피처 약 50개를 <b>LightGBM(데이터 적합 모델)</b>에 넣어 해당 호라이즌 뒤 상승 확률을 추정합니다. 단순 정규화 점수가 아니라, walk-forward로 재학습하고 <b>학습에 안 쓴 최근 구간으로 isotonic 보정</b>해 실제 상승 빈도에 맞춥니다. 보정 품질은 <b>Brier 점수</b>(낮을수록 좋음, 종목 클릭 시 표시)로 측정합니다. 트리 모델이라 지표 간 상관(모멘텀·RSI 중복)은 모델이 알아서 처리합니다.'],
  brier: ['Brier 점수', '예측 확률과 실제 결과(0/1)의 평균제곱오차입니다. <b>낮을수록 보정이 잘 된 것</b>(0=완벽, 0.25=동전던지기 수준). “확률 67%”가 정규화 점수가 아니라 실제 빈도와 맞는지 보는 지표입니다.'],
  edge: ['edge (net)', '<code>edge = p·평균상승 + (1−p)·평균하락 − 비용허들</code>. 확률만으로는 비용을 못 넘기 때문에 기대값이 양수일 때만 제안합니다. 국내(KR)는 세금·수수료로 허들이 더 높습니다.'],
  hold: ['보유(hold-until)', '진입일 + 트레이드 호라이즌(영업일)로 잡은 <b>재평가 시점</b>입니다. 그 전에 무효화 조건(종가 MA20 이탈 또는 다음 확률 0.5 미만)이 오면 먼저 청산합니다.'],
  lift: ['lift', '“항상 상승” 기준선 대비 정밀도의 <b>초과분(%p)</b>. lift가 0에 가까우면 동전던지기와 다를 바 없으니 신뢰도를 낮춰 보세요.'],
  oos: ['OOS 정밀도', '표본 외(학습에 안 쓴 2020년 이후) 구간에서 “상승” 예측이 실제 맞은 비율. <b>n</b>은 검증 표본 수 — 작을수록 우연일 수 있으니 함께 보세요. 같은 구간 백테스트 vs B&H가 음수면 단순 보유만 못한 신호입니다.'],
  flows: ['자금 흐름 (유동성)', '<b>거래량 급증 + 상승</b> 종목을 지역별로 보여줍니다. 최근 5일 평균 거래량이 60일 평균 대비 몇 배인지(volume surge)로 돈·관심이 어디로 몰리는지 가늠합니다. 가격 모멘텀이 +인 종목만 추립니다. (기관/외국인 실제 수급이나 13F 보유는 별도 데이터 소스가 필요합니다 — 자체 데이터로 만든 프록시입니다.)'],
  direction: ['투자 나침반', '4가지 <b>규칙 기반 자산배분 도구</b>를 하나의 방향성으로 합성합니다: ① 듀얼 모멘텀(12개월 절대+상대 모멘텀, GEM) ② 변동성 타게팅(실현변동성 대비 목표 12%로 주식 노출 기계적 산출) ③ 시장 추세·심리·매크로 ④ KR/US 상대 모멘텀 틸트. 점수 60↑ 확대, 45~60 중립, 45↓ 방어입니다. <b>기계적 참고선이지 투자 조언이 아닙니다</b> — 개인의 위험 성향·현금 흐름에 맞게 조정하세요.'],
  dualmom: ['듀얼 모멘텀 (GEM)', 'Gary Antonacci의 Global Equities Momentum 규칙입니다. <b>절대 모멘텀</b>: 주식의 12개월 수익률이 현금(T-Bill)보다 높을 때만 주식 보유. <b>상대 모멘텀</b>: 미국·선진국·신흥국 중 12개월 수익률 1위를 선택. 허들 미달이면 채권·금 같은 방어자산으로 이동합니다. 단순하지만 대형 하락장 회피에 오랜 실증이 있는 규칙입니다(후행성 있음 — 바닥·천장을 못 맞춥니다).'],
  rotation: ['섹터 로테이션 (RRG)', 'Relative Rotation Graph 방식의 4사분면입니다. 가로축은 <b>상대강도 비율</b>(섹터/벤치마크 상대강도선이 자기 3개월 평균 대비 어디), 세로축은 <b>상대강도 모멘텀</b>(상대강도선의 1개월 변화)입니다. <b>주도</b>(강하고 더 강해짐)→<b>약화</b>(강하지만 식는 중)→<b>부진</b>(약하고 더 약해짐)→<b>개선</b>(약하지만 회복 중) 순으로 시계방향 순환하는 경향이 있어, 돈이 어느 섹터로 도는지 보여줍니다. 공개 산식의 근사치입니다.'],
  factor: ['팩터 · 스타일 모멘텀', '모멘텀(MTUM)·가치(VLUE)·퀄리티(QUAL)·저변동(USMV)·소형주(IWM) ETF의 S&P500 대비 <b>초과수익(1·3·6개월)</b>입니다. 시장이 지금 어떤 성격의 주식에 프리미엄을 주는지 보여줍니다. 예: 저변동·퀄리티 우위면 방어 국면, 모멘텀·소형주 우위면 위험 선호 국면.'],
  size: ['비중 추천 비활성화', '<code>켈리 f* = p − (1−p)/b</code> (b = 평균 상승폭/평균 하락폭). 켈리 기준은 장기 복리 성장을 최대화하는 베팅 비율이지만 확률 추정 오차에 민감해, 관행대로 <b>절반(½켈리)</b>만 쓰고 종목당 10%로 상한을 둡니다. 총 노출은 나침반의 권장 주식 비중 안에서 배분하세요.'],
  indices: ['글로벌 마켓', 'S&P 500 · 나스닥 · 다우 · 필라델피아 반도체 · 코스피 · 코스닥 · 원/달러 · VIX · 비트코인 · 금 · 달러인덱스를 매 빌드마다 수집합니다. <b>1D</b>는 전일 대비, <b>YTD</b>는 연초 대비, <b>고점비</b>는 52주 최고가 대비 거리입니다. 미니 차트는 최근 3개월 추이(상승=녹색, 하락=적색). 기본 소스는 Yahoo Finance이며 실패 시 Stooq로 자동 대체해 지수 데이터가 끊기지 않게 했습니다.'],
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
    m('10일 모델 점수', pct0(d.modelScore ?? d.probUp)),
    m('SMA50/200', `${fmt(d.ma50)} / ${fmt(d.ma200)}`),
    m('RSI(14)', fmt(d.rsi14)),
    m('실현변동성', fmt(d.realizedVol, '%')),
    m('1년 낙폭', fmt(d.maxDrawdown252d, '%')),
    m('상대강도', sp(d.relMomentum)),
    m('60일 모멘텀', sp(d.mom63)),
    m('52주고점 대비', fmt(d.pct52wHigh, '%')),
  ].join('');
  const core = (DATA.core || []).find((c) => c.ticker === ticker);
  const horizons = core ? `<div class="dp-sub">호라이즌별 신호 · 표본 외 검증</div>` + core.signals.map((s) => {
    const o = s.oos || {}, b = s.backtest || {};
    return `<div class="dp-sig"><b>${s.horizon}D · ${pct0(s.modelScore ?? s.probUp)}</b><span class="muted">정밀 ${pct0(o.precision)} (lift ${sp(o.lift)}) · n=${fmt(o.days)} · Brier ${fmt(o.brier, '', 2)} · 연 ${sp(b.annualReturn)} · vsB&H ${sp(b.vsBuyHold)}</span></div>`;
  }).join('') : '';
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

// --- Global market tape (S&P 500 / NASDAQ / KOSPI ...) ---
const nfmt = (v, d) => (v === null || v === undefined || Number.isNaN(v)) ? '—'
  : v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
const chg = (v, d = 2) => (v === null || v === undefined || Number.isNaN(v)) ? '—'
  : `${v >= 0 ? '+' : ''}${v.toFixed(d)}%`;
const sparkSvg = (vals) => {
  if (!vals || vals.length < 2) return '';
  const w = 116, h = 30, min = Math.min(...vals), max = Math.max(...vals), span = (max - min) || 1;
  const pts = vals.map((v, i) =>
    `${(i / (vals.length - 1) * w).toFixed(1)},${(h - 2 - (v - min) / span * (h - 4)).toFixed(1)}`).join(' ');
  const up = vals[vals.length - 1] >= vals[0];
  return `<svg class="spark ${up ? 'spark-up' : 'spark-down'}" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" aria-hidden="true"><polyline points="${pts}" fill="none" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/></svg>`;
};
const ixTile = (x) => {
  const d1 = x.chg1dPct;
  const dir = d1 == null ? '' : d1 >= 0 ? 'pos' : 'neg';
  return `<article class="ix" title="${x.symbol} · ${x.asOf ?? ''} · ${x.source ?? ''}">
    <div class="ix-h"><span class="ix-name">${x.name}</span><span class="ix-reg">${x.region}</span></div>
    <div class="ix-quote"><span class="ix-last">${nfmt(x.last, x.digits ?? 2)}</span><span class="ix-chg ${dir}">${chg(d1)}</span></div>
    ${sparkSvg(x.spark)}
    <div class="ix-sub">
      <span>1M <b class="${(x.chg1mPct ?? 0) >= 0 ? 'pos' : 'neg'}">${chg(x.chg1mPct, 1)}</b></span>
      <span>YTD <b class="${(x.ytdPct ?? 0) >= 0 ? 'pos' : 'neg'}">${chg(x.ytdPct, 1)}</b></span>
      <span>고점비 <b>${chg(x.from52wHighPct, 1)}</b></span>
    </div>
  </article>`;
};
const renderIndices = (d) => {
  const sec = $('#indices');
  const list = d.indices || [];
  if (!list.length) { sec.hidden = true; return; }
  sec.hidden = false;
  $('#indexTape').innerHTML = list.map(ixTile).join('');
  const asOf = list[0].asOf;
  $('#tapeMeta').textContent = `${asOf ? '기준 ' + asOf + ' · ' : ''}미니 차트는 최근 3개월`;
};

// --- Investment direction compass ---
const dirSignal = (s) => `
  <div class="dsig">
    <div class="dsig-top"><span class="dsig-name">${s.name}</span><span class="reg ${s.cls}">${s.state}</span></div>
    <div class="dsig-detail">${s.detail || ''}</div>
  </div>`;
const dmRow = (r, winner) => {
  const cell = (v) => `<span class="${(v ?? 0) >= 0 ? 'pos' : 'neg'}">${chg(v, 1)}</span>`;
  return `<div class="dm-row ${r.ticker === winner ? 'dm-win' : ''}">
    <span class="dm-name">${r.ticker === winner ? '★ ' : ''}${r.name} <span class="tk">${r.ticker}</span></span>
    <span>${cell(r.ret3mPct)}</span><span>${cell(r.ret6mPct)}</span><span>${cell(r.ret12mPct)}</span>
  </div>`;
};
const renderDirection = (dir) => {
  const sec = $('#direction');
  if (!dir) { sec.hidden = true; return; }
  sec.hidden = false;
  $('#dirMeta').textContent = '듀얼 모멘텀 · 변동성 타게팅 · 추세 · 심리 · 매크로 합성';
  const vt = dir.volTarget;
  $('#dirVerdict').innerHTML = `
    <div class="overline">지금의 방향</div>
    <div class="dir-stance-row"><span class="dir-stance">${dir.stance}</span><span class="posture-score reg ${dir.stanceCls}">${dir.score}</span></div>
    <div class="gauge"><i class="${dir.stanceCls}" style="width:${dir.score}%"></i></div>
    <p class="dir-read">${dir.headline || ''}</p>
    <div class="alloc">
      <div class="alloc-bar"><i class="eq" style="width:${dir.equityPct}%"></i><i class="cash" style="width:${dir.cashPct}%"></i></div>
      <div class="alloc-legend"><span><i class="dot dot-eq"></i>주식 ${dir.equityPct}%</span><span><i class="dot dot-cash"></i>현금·방어 ${dir.cashPct}%</span></div>
    </div>
    ${vt ? `<p class="dir-note">변동성 타게팅: 실현 ${vt.realizedVolPct}% vs 목표 ${vt.targetVolPct}% → 노출 상한 ${vt.suggestedExposurePct}%</p>` : ''}`;
  $('#dirSignals').innerHTML = (dir.signals || []).map(dirSignal).join('');
  const dm = dir.dualMomentum;
  const box = document.querySelector('.dm-box');
  if (!dm || !dm.rows || !dm.rows.length) { if (box) box.hidden = true; }
  else {
    if (box) box.hidden = false;
    $('#dualMomTable').innerHTML =
      `<div class="dm-row dm-h2"><span>자산</span><span>3M</span><span>6M</span><span>12M</span></div>` +
      dm.rows.map((r) => dmRow(r, dm.winner)).join('') +
      `<div class="dm-note muted">★ 12개월 수익률 기준 선호 자산 · 현금(T-Bill) 허들 ${dm.cash12mPct != null ? chg(dm.cash12mPct, 1) : '—'} ${dm.equitiesWin ? '통과 → 주식 우위' : '미달 → 방어자산 우위'}</div>`;
  }
};

// --- Sector rotation (RRG quadrants) + factor momentum ---
const QUAD = {
  '주도': { cls: 'q-lead', color: 'var(--green)' },
  '약화': { cls: 'q-weak', color: 'var(--gold)' },
  '개선': { cls: 'q-impr', color: 'var(--accent)' },
  '부진': { cls: 'q-lag', color: 'var(--red)' },
};
const rrgSvg = (sectors) => {
  const W = 400, H = 300, pad = 10;
  const cx = W / 2, cy = H / 2;
  const maxX = Math.max(2, ...sectors.map((s) => Math.abs(s.rsRatio))) * 1.25;
  const maxY = Math.max(2, ...sectors.map((s) => Math.abs(s.rsMom))) * 1.25;
  const X = (v) => cx + (v / maxX) * (W / 2 - pad);
  const Y = (v) => cy - (v / maxY) * (H / 2 - pad);
  const dots = sectors.map((s) => {
    const x = X(s.rsRatio), y = Y(s.rsMom), c = (QUAD[s.quadrant] || {}).color || 'var(--muted)';
    const anchor = x > W - 60 ? 'end' : 'start';
    return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4.5" fill="${c}" fill-opacity="0.9"><title>${s.name} · ${s.quadrant} · RS비율 ${s.rsRatio} · RS모멘텀 ${s.rsMom}</title></circle>
      <text x="${(x + (anchor === 'end' ? -7 : 7)).toFixed(1)}" y="${(y + 3.5).toFixed(1)}" text-anchor="${anchor}" class="rrg-lb">${s.name}</text>`;
  }).join('');
  return `<svg viewBox="0 0 ${W} ${H}" class="rrg" role="img" aria-label="섹터 로테이션 사분면">
    <rect x="${cx}" y="0" width="${cx}" height="${cy}" class="rrg-q rrg-q-lead"/>
    <rect x="${cx}" y="${cy}" width="${cx}" height="${cy}" class="rrg-q rrg-q-weak"/>
    <rect x="0" y="0" width="${cx}" height="${cy}" class="rrg-q rrg-q-impr"/>
    <rect x="0" y="${cy}" width="${cx}" height="${cy}" class="rrg-q rrg-q-lag"/>
    <line x1="0" y1="${cy}" x2="${W}" y2="${cy}" class="rrg-ax"/>
    <line x1="${cx}" y1="0" x2="${cx}" y2="${H}" class="rrg-ax"/>
    <text x="${W - 8}" y="14" text-anchor="end" class="rrg-ql" fill="var(--green)">주도</text>
    <text x="${W - 8}" y="${H - 6}" text-anchor="end" class="rrg-ql" fill="var(--gold)">약화</text>
    <text x="8" y="14" class="rrg-ql" fill="var(--accent)">개선</text>
    <text x="8" y="${H - 6}" class="rrg-ql" fill="var(--red)">부진</text>
    ${dots}
  </svg>`;
};
const rrgChips = (sectors) => sectors.map((s) =>
  `<span class="rchip ${(QUAD[s.quadrant] || {}).cls || ''}" title="RS비율 ${s.rsRatio} · RS모멘텀 ${s.rsMom}">${s.name} <b>${s.quadrant}</b> <em>${chg(s.ret3mPct, 1)}</em></span>`).join('');
const renderRegionRrg = (el, region) => {
  const host = $(el);
  if (!region || !region.sectors || !region.sectors.length) { host.innerHTML = '<div class="none">데이터 없음</div>'; return; }
  host.innerHTML = rrgSvg(region.sectors) + `<div class="rrg-chips">${rrgChips(region.sectors)}</div>`;
};
const factorRow = (f) => {
  const v = f.ex3mPct ?? 0;
  const w = Math.min(50, Math.abs(v) * 6);
  return `<div class="frow">
    <span class="f-name">${f.name} <span class="tk">${f.ticker}</span></span>
    <span class="f-bar"><i class="${v >= 0 ? 'fpos' : 'fneg'}" style="${v >= 0 ? 'left:50%' : 'right:50%'};width:${w}%"></i></span>
    <span class="f-nums">1M <b class="${(f.ex1mPct ?? 0) >= 0 ? 'pos' : 'neg'}">${chg(f.ex1mPct, 1)}</b> · 3M <b class="${v >= 0 ? 'pos' : 'neg'}">${chg(f.ex3mPct, 1)}</b> · 6M <b class="${(f.ex6mPct ?? 0) >= 0 ? 'pos' : 'neg'}">${chg(f.ex6mPct, 1)}</b></span>
  </div>`;
};
const renderRotation = (rot) => {
  const sec = $('#rotation');
  if (!rot || (!rot.US && !rot.KR && !(rot.factors || []).length)) { sec.hidden = true; return; }
  sec.hidden = false;
  $('#rotMeta').textContent = `${rot.asOf ? '기준 ' + rot.asOf + ' · ' : ''}가로: 상대강도 비율 · 세로: 상대강도 모멘텀`;
  renderRegionRrg('#rrgUS', rot.US);
  renderRegionRrg('#rrgKR', rot.KR);
  const fp = $('#factorPanel');
  if ((rot.factors || []).length) { fp.hidden = false; $('#factorBars').innerHTML = rot.factors.map(factorRow).join(''); }
  else fp.hidden = true;
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
// OOS quality badge: informational, not a gate — shows how well the model has
// actually predicted this ticker out-of-sample (grade from pipeline/quality.py).
const qBadge = (q) => {
  q = q || {};
  const g = q.qualityGrade;
  if (g === 'A' || g === 'B') return `<span class="qbadge g${g.toLowerCase()}" title="OOS 검증 통과 · lift ${q.lift ?? '—'}%p · BSS ${q.brierSkillScore ?? '—'}">검증 ${g}</span>`;
  return `<span class="qbadge gx" title="OOS 품질 게이트 미통과 — 참고용 신호">미검증</span>`;
};

const pickCard = (i, rank) => `
  <article class="pick ${rank === 1 ? 'top' : ''}">
    <span class="rank">#${rank}</span>
    <div class="pick-name"><strong class="tklink" data-tk="${i.ticker}">${tkName(i.ticker)}</strong><span class="reg ${regCls(i.regime)}">${regKo(i.regime)}</span>${qBadge(i.quality)}</div>
    <span class="pick-act">${i.region} · 매수 후보</span>
    <div class="pick-conv"><span class="big">${pct0((i.modelScore ?? i.probUp))}</span><span class="lab">${term('prob', '모델 점수')}</span></div>
    <div class="pick-meta">
      <span>기대 <b>${sp((i.expMovePct ?? i.estimatedNetEdgePct))}</b></span>
      <span data-x="edge">edge <b>${sp((i.estimatedNetEdgePct ?? i.edgeNetPct))}</b></span>
      ${i.suggestedWeightPct != null ? `<span data-x="size">비중 <b>~${i.suggestedWeightPct}%</b></span>` : ''}
      <span>${term('hold', '보유')} <b>~${i.holdUntil}</b></span>
    </div>
    <div class="pick-why">${i.why || ''}</div>
  </article>`;

const renderTopPicks = (d) => {
  if (d.recommendationsBlocked) { $('#topPicks').innerHTML = `<div class="pick-empty danger"><b>매매 사용 금지 · 추천 차단</b><p class="muted">${(d.blockReasons||[]).join(' · ')}</p></div>`; return; }
  const ti = d.tradeIdeas || { KR: [], US: [] };
  const all = [...(ti.KR || []), ...(ti.US || [])].sort((a, b) => ((b.estimatedNetEdgePct ?? b.edgeNetPct) ?? 0) - ((a.estimatedNetEdgePct ?? a.edgeNetPct) ?? 0));
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
    <div class="idea-top"><strong class="tklink" data-tk="${i.ticker}">${tkName(i.ticker)}</strong>${tkSub(i.ticker)}<span class="reg ${regCls(i.regime)}">${regKo(i.regime)}</span>${qBadge(i.quality)}<span class="edge" data-x="edge">edge ${sp((i.estimatedNetEdgePct ?? i.edgeNetPct))}</span></div>
    <div class="idea-bar"><i style="width:${Math.round(((i.modelScore ?? i.probUp) ?? 0) * 100)}%"></i></div>
    <div class="idea-meta"><span>${term('prob', '모델 점수')} <b>${pct0((i.modelScore ?? i.probUp))}</b></span><span>기대 <b>${sp((i.expMovePct ?? i.estimatedNetEdgePct))}</b></span>${i.suggestedWeightPct != null ? `<span data-x="size">비중 <b>~${i.suggestedWeightPct}%</b></span>` : ''}<span>${term('hold', '보유')} <b>~${i.holdUntil}</b> (${i.horizon}D)</span></div>
    <div class="idea-why">${i.why || ''}</div>
    <div class="idea-inv">${i.invalidation}</div>
  </div>`;

const renderIdeas = (d) => {
  if (d.recommendationsBlocked) {
    $('#tradeKR').innerHTML = $('#tradeUS').innerHTML = '<div class="none">데이터 안전 차단 상태: 추천이 일시 중지됐습니다.</div>';
    $('#tradeMeta').textContent = '추천 차단 · ' + ((d.blockReasons || []).join(' · ') || '데이터 안전');
  } else {
    const ti = d.tradeIdeas || { KR: [], US: [] };
    $('#tradeMeta').textContent = `보유 ${d.tradeHorizon ?? '—'}영업일 기준 · 확률·기대값 통과분`;
    const fill = (el, arr) => $(el).innerHTML = (arr && arr.length) ? arr.map(ideaRow).join('') : '<div class="none">조건 충족 종목 없음 (관망)</div>';
    fill('#tradeKR', ti.KR); fill('#tradeUS', ti.US);
  }
  const sc = d.screened || [];
  $('#screenCount').textContent = `· ${sc.length}개`;
  $('#screenTable').innerHTML = `<div class="srow sh"><span>종목</span><span>지역</span><span>${term('prob', '모델 점수')}</span><span>국면</span><span>채택</span></div>` +
    sc.map((s) => `<div class="srow" data-key="${(s.ticker + ' ' + tkName(s.ticker)).toLowerCase()}"><span>${tkLink(s.ticker)}</span><span>${s.region}</span><span>${pct0(s.modelScore ?? s.probUp)}</span><span class="reg ${regCls(s.regime)}">${regKo(s.regime)}</span><span>${s.qualifies ? '✓' : '·'}</span></div>`).join('');
  filterScreen();
};

// --- Holdings table ---
// Regime-led: a stock in a clear uptrend is never tagged 축소 just because a
// noisy short-horizon probability dipped.
const holdingVerdict = (t) => {
  const probs = (t.signals || []).map((s) => s.modelScore ?? s.probUp).filter((n) => n != null);
  if (DATA.recommendationsBlocked) return ['검증 미달', 'hold'];
  const avg = mean(probs); const reg = t.risk?.regime;
  if (reg === 'Bull') return (avg != null && avg >= 0.55) ? ['비중 유지', 'buy'] : ['유지 · 관찰', 'hold'];
  if (reg === 'Bear') return (avg != null && avg >= 0.6) ? ['관망', 'hold'] : ['축소 검토', 'sell'];
  if (avg != null && avg >= 0.6) return ['비중 유지', 'buy'];
  if (avg != null && avg < 0.4) return ['축소 검토', 'sell'];
  return ['관망', 'hold'];
};
const renderHoldings = (d) => {
  const core = d.core || [];
  const head = `<div class="hrow hh"><span>종목</span><span>현재가</span><span>국면</span><span class="hcol-sig">호라이즌별 모델 점수 (21·63·126D)</span><span>판정</span></div>`;
  const rows = core.map((t) => {
    const [vlabel, vcls] = holdingVerdict(t);
    const sigs = (t.signals || []).map((s) => `<div class="h-sig">${s.horizon}D<b>${pct0(s.modelScore ?? s.probUp)}</b><div class="mini-bar"><i style="width:${Math.round(((s.modelScore ?? s.probUp) ?? 0) * 100)}%"></i></div></div>`).join('');
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

// --- Money flow (liquidity) ---
const flowRow = (f) => `
  <div class="flow">
    <span class="flow-tk tklink" data-tk="${f.ticker}">${tkName(f.ticker)}</span>
    <span class="reg ${regCls(f.regime)}">${regKo(f.regime)}</span>
    <span class="flow-surge">거래량 <b>×${fmt(f.volSurge)}</b></span>
    <span class="flow-mom">모멘텀 <b>${sp(f.mom63)}</b></span>
  </div>`;
const renderFlows = (d) => {
  const fl = d.flows || { KR: [], US: [] };
  const fill = (el, arr) => $(el).innerHTML = (arr && arr.length) ? arr.map(flowRow).join('') : '<div class="none">두드러진 자금 유입 없음</div>';
  fill('#flowsKR', fl.KR); fill('#flowsUS', fl.US);
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
  $('#dataStatus').textContent = `· ${(d.core || []).length} 추적 · ${d.paperOnly ? 'PAPER ONLY' : 'LIVE'}${d.seed ? ' · SEED' : ''}`;
  const m = d.meta || {};
  $('#dataMeta').textContent = [
    m.latestDataDate ? `데이터 ${m.latestDataDate}` : '',
    m.universeScreened ? `유니버스 ${m.universeScreened}` : '',
    m.coveragePct != null ? `커버리지 ${m.coveragePct}%` : '',
    m.modelsTrained ? `모델 ${m.modelsTrained}회 학습` : '',
  ].filter(Boolean).join(' · ');
  if (d.generatedAt) $('#dataGenerated').textContent = '생성 ' + new Date(d.generatedAt).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' }) + ' KST';
  const sb = $('#staleBanner');
  if (d.recommendationsBlocked || d.stale || d.seed || (m.coveragePct != null && m.coveragePct < 95) || (m.modelsTrained||0) === 0) {
    sb.hidden = false; sb.classList.add('warn');
    sb.innerHTML = `<b>⚠️ 이 데이터로 매매하지 마세요 — 추천/확률/비중 차단</b><br><span>${(d.blockReasons || []).join(' · ') || '품질 게이트 미통과'}${m.latestDataDate ? ' · 마지막 데이터 ' + m.latestDataDate : ''}</span>`;
  } else { sb.hidden = true; sb.classList.remove('warn'); }
  renderIndices(d);
  renderDirection(d.direction);
  renderRotation(d.rotation);
  renderPosture(d.sentiment);
  renderTopPicks(d);
  renderIdeas(d);
  renderHoldings(d);
  renderFlows(d);
  renderMacro(d.macro);
  renderSentiment(d.sentiment);
};

const loadData = async () => {
  try { const r = await fetch('data/site-data.json', { cache: 'no-store' }); if (!r.ok) throw new Error(`HTTP ${r.status}`); render(await r.json()); }
  catch (e) { $('#dataStatus').textContent = 'data error: ' + e.message; }
};
// Screening search/filter
const filterScreen = () => {
  const q = ($('#screenSearch')?.value || '').trim().toLowerCase();
  const rows = document.querySelectorAll('#screenTable .srow:not(.sh)');
  let shown = 0;
  rows.forEach((r) => {
    const hit = !q || (r.dataset.key || '').includes(q);
    r.style.display = hit ? '' : 'none';
    if (hit) shown++;
  });
  const empty = $('#screenEmpty'); if (empty) empty.hidden = shown !== 0;
};
$('#screenSearch')?.addEventListener('input', filterScreen);

document.querySelectorAll('.nav a[href^="#"]').forEach((a) => a.addEventListener('click', (e) => {
  const t = document.querySelector(a.getAttribute('href')); if (!t) return; e.preventDefault(); t.scrollIntoView({ behavior: 'smooth', block: 'start' });
}));
loadRules(); loadData();
