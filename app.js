'use strict';

const $ = (sel) => document.querySelector(sel);

const fmt = (v, suffix = '', digits) => {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  const n = typeof v === 'number' && digits !== undefined ? v.toFixed(digits) : v;
  return `${n}${suffix}`;
};

const signedPct = (v) => {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return `${v >= 0 ? '+' : ''}${v}%`;
};

const alertClass = (alert) =>
  alert === 'STRONG BUY' ? 'buy' : alert === 'STRONG SELL' ? 'sell' : 'hold';

const alertLabel = (alert) =>
  alert === 'STRONG BUY' ? '강한 매수' : alert === 'STRONG SELL' ? '강한 매도' : '관망';

const regimeClass = (regime) =>
  regime === 'Bull' ? 'bull' : regime === 'Bear' ? 'bear' : 'transition';

const regimeLabel = (regime) =>
  regime === 'Bull' ? '상승국면' : regime === 'Bear' ? '하락국면' : '전환국면';

// --- Minimal Markdown renderer (headings, lists, tables, bold) ---
const markdownToHtml = (markdown) => {
  const lines = markdown.split('\n');
  let html = '';
  let inList = false;
  let inTable = false;
  const closeList = () => { if (inList) { html += '</ul>'; inList = false; } };
  const closeTable = () => { if (inTable) { html += '</tbody></table>'; inTable = false; } };

  lines.forEach((line) => {
    if (line.startsWith('|') && !line.includes('---')) {
      closeList();
      const cells = line.split('|').slice(1, -1).map((c) => c.trim());
      if (!inTable) { html += '<table><tbody>'; inTable = true; }
      html += `<tr>${cells.map((c) => `<td>${c}</td>`).join('')}</tr>`;
      return;
    }
    if (line.startsWith('|') && line.includes('---')) return;
    closeTable();
    if (line.startsWith('## ')) { closeList(); html += `<h3>${line.slice(3)}</h3>`; }
    else if (line.startsWith('# ')) { closeList(); html += `<h2>${line.slice(2)}</h2>`; }
    else if (line.startsWith('- [ ] ')) {
      if (!inList) { html += '<ul class="checklist">'; inList = true; }
      html += `<li class="check">${line.slice(6)}</li>`;
    } else if (line.startsWith('- ')) {
      if (!inList) { html += '<ul>'; inList = true; }
      html += `<li>${line.slice(2)}</li>`;
    } else if (/^\d+\. /.test(line)) {
      if (!inList) { html += '<ul>'; inList = true; }
      html += `<li>${line.replace(/^\d+\. /, '')}</li>`;
    } else if (line.trim()) { closeList(); html += `<p>${line}</p>`; }
  });
  closeList();
  closeTable();
  return html.replaceAll('**', '');
};

const loadPrinciples = async () => {
  const panel = $('#principlesDoc');
  try {
    const res = await fetch('docs/investment-philosophy.md', { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    panel.innerHTML = markdownToHtml(await res.text());
  } catch (err) {
    panel.textContent = `Markdown을 불러오지 못했습니다: ${err.message}`;
  }
};

// --- ① Signals ---
const renderSignalCard = (t) => {
  const rows = (t.signals || []).map((s) => {
    const oos = s.oos || {};
    const bt = s.backtest || {};
    const lift = oos.lift;
    const liftClass = lift > 0 ? 'pos' : lift < 0 ? 'neg' : '';
    return `
      <div class="sig-row">
        <div class="sig-head">
          <span class="horizon">${s.horizon}D</span>
          <span class="badge ${alertClass(s.alert)}">${alertLabel(s.alert)}</span>
        </div>
        <div class="prob">
          <div class="prob-bar"><i style="width:${Math.round((s.probUp ?? 0) * 100)}%"></i></div>
          <strong>${fmt((s.probUp ?? 0) * 100, '%', 0)}</strong>
          <small>상승확률 · 임계 ${fmt((s.threshold ?? 0) * 100, '%', 0)}</small>
        </div>
        <div class="sig-meta">
          <span>OOS 정밀도 <b>${fmt((oos.precision ?? 0) * 100, '%', 0)}</b> <em class="${liftClass}">(기준 ${fmt((oos.baseline ?? 0) * 100, '%', 0)}, lift ${signedPct(lift)})</em></span>
          <span>백테스트 연 <b>${signedPct(bt.annualReturn)}</b> · Sharpe ${fmt(bt.sharpe, '', 2)} · MDD ${fmt(bt.maxDrawdown, '%')} · vs B&H ${signedPct(bt.vsBuyHold)}</span>
        </div>
      </div>`;
  }).join('');

  return `
    <article class="ticker-card">
      <header>
        <div><h3>${t.ticker}</h3><small>as of ${t.asOf ?? '—'}</small></div>
        <strong class="price">$${fmt(t.lastClose)}</strong>
      </header>
      <div class="sig-rows">${rows || '<p class="empty">신호를 계산할 데이터가 부족합니다.</p>'}</div>
    </article>`;
};

// --- ② Macro ---
const renderMacro = (m) => {
  if (!m || !m.available) {
    return `<div class="macro-empty">${m?.note ?? '매크로 데이터가 없습니다.'}</div>`;
  }
  const stanceMap = { Stable: ['안정', 'ok'], Caution: ['주의', 'warn'], 'Risk-off': ['위험회피', 'bad'] };
  const [stanceKo, stanceCls] = stanceMap[m.stance] || [m.stance, ''];
  const kpis = [
    ['거시 스탠스', stanceKo, m.stance],
    ['10년물', fmt(m.treasury10y, '%'), '미국 국채 10Y'],
    ['2년물', fmt(m.treasury2y, '%'), '미국 국채 2Y'],
    ['장단기 금리차', fmt(m.yieldCurve, '%p'), `21일 ${signedPct(m.yieldCurveChange21d)}`],
    ['VIX', fmt(m.vix), `21일 ${m.vixChange21d >= 0 ? '+' : ''}${fmt(m.vixChange21d)}`],
  ];
  const flags = (m.riskFlags || []).map((f) => `
    <article class="risk-card active"><span>ACTIVE</span><h4>${f.name}</h4><p>${f.message}</p></article>`).join('');
  return `
    <div class="macro-stance ${stanceCls}"><span>Macro stance</span><strong>${stanceKo}</strong></div>
    <div class="kpi-grid">
      ${kpis.map(([l, v, n]) => `<article class="kpi-card"><span>${l}</span><strong>${v}</strong><p>${n}</p></article>`).join('')}
    </div>
    <div class="risk-grid">${flags || '<article class="risk-card"><span>OK</span><h4>거시 리스크</h4><p>활성화된 매크로 경고 없음</p></article>'}</div>`;
};

// --- ③ Risk / regime ---
const renderRiskCard = (t) => {
  const r = t.risk || {};
  const flags = (r.riskFlags || []).map((f) => `<li>${f.message}</li>`).join('');
  const metrics = [
    ['SMA50/200', `${fmt(r.ma50)} / ${fmt(r.ma200)}`],
    ['실현 변동성', fmt(r.realizedVol, '%')],
    ['RSI14', fmt(r.rsi14)],
    ['1년 낙폭', fmt(r.maxDrawdown252d, '%')],
    ['상대강도(20D)', signedPct(r.relMomentum)],
    ['52주 고점 대비', fmt(r.pct52wHigh, '%')],
  ];
  return `
    <article class="regime-card">
      <header>
        <h3>${t.ticker}</h3>
        <span class="regime ${regimeClass(r.regime)}">${regimeLabel(r.regime)}</span>
      </header>
      <div class="regime-metrics">
        ${metrics.map(([l, v]) => `<div><span>${l}</span><b>${v}</b></div>`).join('')}
      </div>
      <ul class="regime-flags ${flags ? '' : 'clean'}">
        ${flags || '<li>활성화된 리스크 플래그 없음</li>'}
      </ul>
    </article>`;
};

const render = (data) => {
  $('#portfolioName').textContent = data.portfolioName || '내 투자 인사이트';
  $('#dataStatus').textContent = `${(data.tickers || []).length}개 종목 · primary ${data.primary || '—'}`;
  $('#dataSource').textContent = data.dataSource || '';
  if (data.generatedAt) {
    const d = new Date(data.generatedAt);
    $('#dataGenerated').textContent = `생성 ${d.toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })} KST`;
  }
  $('#signalCards').innerHTML = (data.tickers || []).map(renderSignalCard).join('') ||
    '<p class="empty">종목 데이터가 없습니다. config.json 과 CI 실행 결과를 확인하세요.</p>';
  $('#macroPanel').innerHTML = renderMacro(data.macro);
  $('#riskGrid').innerHTML = (data.tickers || []).map(renderRiskCard).join('') ||
    '<p class="empty">리스크 데이터가 없습니다.</p>';
};

const loadData = async () => {
  try {
    const res = await fetch('data/site-data.json', { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    render(await res.json());
  } catch (err) {
    $('#dataStatus').textContent = 'Data error';
    $('#dataSource').textContent = err.message;
  }
};

document.querySelectorAll('a[href^="#"]').forEach((link) => {
  link.addEventListener('click', (e) => {
    const target = document.querySelector(link.getAttribute('href'));
    if (!target) return;
    e.preventDefault();
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
});

loadPrinciples();
loadData();
