const formatValue = (value, suffix = '') => {
  if (value === null || value === undefined || Number.isNaN(value)) return 'N/A';
  return `${value}${suffix}`;
};

const markdownToHtml = (markdown) => {
  const lines = markdown.split('\n');
  let html = '';
  let inList = false;
  let inTable = false;

  const closeList = () => {
    if (inList) {
      html += '</ul>';
      inList = false;
    }
  };
  const closeTable = () => {
    if (inTable) {
      html += '</tbody></table>';
      inTable = false;
    }
  };

  lines.forEach((line) => {
    if (line.startsWith('|') && !line.includes('---')) {
      closeList();
      const cells = line.split('|').slice(1, -1).map((cell) => cell.trim());
      if (!inTable) {
        html += '<table><tbody>';
        inTable = true;
      }
      html += `<tr>${cells.map((cell) => `<td>${cell}</td>`).join('')}</tr>`;
      return;
    }
    if (line.startsWith('|') && line.includes('---')) return;
    closeTable();

    if (line.startsWith('## ')) {
      closeList();
      html += `<h3>${line.replace('## ', '')}</h3>`;
    } else if (line.startsWith('# ')) {
      closeList();
      html += `<h2>${line.replace('# ', '')}</h2>`;
    } else if (line.startsWith('- ')) {
      if (!inList) {
        html += '<ul>';
        inList = true;
      }
      html += `<li>${line.replace('- ', '')}</li>`;
    } else if (/^\d+\. /.test(line)) {
      if (!inList) {
        html += '<ul>';
        inList = true;
      }
      html += `<li>${line.replace(/^\d+\. /, '')}</li>`;
    } else if (line.trim()) {
      closeList();
      html += `<p>${line}</p>`;
    }
  });
  closeList();
  closeTable();
  return html.replaceAll('**', '');
};

const loadPhilosophy = async () => {
  const panel = document.querySelector('#philosophyDoc');
  try {
    const response = await fetch('docs/investment-philosophy.md', { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    panel.innerHTML = markdownToHtml(await response.text());
  } catch (error) {
    panel.textContent = `Markdown을 불러오지 못했습니다: ${error.message}`;
  }
};

const renderMarketData = (data) => {
  document.querySelector('#dataStatus').textContent = `${data.symbol} · ${data.latestDate}`;
  document.querySelector('#dataSource').textContent = data.source;

  const metrics = [
    ['Latest Close', `$${formatValue(data.latestClose)}`, '일간 종가 기준'],
    ['Composite Score', `${formatValue(data.composite?.score)}/100`, data.composite?.stance],
    ['SMA 50 / 200', `${formatValue(data.metrics?.sma50)} / ${formatValue(data.metrics?.sma200)}`, '중장기 추세 확인'],
    ['RSI 14', formatValue(data.metrics?.rsi14), '단기 과열/침체 확인'],
    ['Realized Vol 21D', formatValue(data.metrics?.realizedVol21d, '%'), '연율화 변동성'],
    ['QQQ-SPY 63D', formatValue(data.metrics?.relativeStrength63d, '%p'), '상대강도'],
    ['Max DD 252D', formatValue(data.metrics?.maxDrawdown252d, '%'), '최근 1년 최대 낙폭'],
  ];

  document.querySelector('#kpiGrid').innerHTML = metrics.map(([label, value, note]) => `
    <article class="kpi-card">
      <span>${label}</span>
      <strong>${value}</strong>
      <p>${note ?? ''}</p>
    </article>
  `).join('');

  document.querySelector('#decisionCard').innerHTML = `
    <span>Composite stance</span>
    <strong>${data.composite?.stance ?? 'N/A'}</strong>
    <p>${data.composite?.action ?? '데이터 갱신 후 판단합니다.'}</p>
  `;

  document.querySelector('#signalRows').innerHTML = (data.signals ?? []).map((signal) => `
    <div class="table-row">
      <span>${signal.horizon}</span>
      <strong>${formatValue(signal.return, '%')}</strong>
      <span>${signal.view}</span>
    </div>
  `).join('');

  document.querySelector('#riskGrid').innerHTML = (data.riskFlags ?? []).map((flag) => `
    <article class="risk-card ${flag.active ? 'active' : ''}">
      <span>${flag.active ? 'ACTIVE' : 'OK'}</span>
      <h3>${flag.name}</h3>
      <p>${flag.message}</p>
    </article>
  `).join('');
};

const loadMarketData = async () => {
  try {
    const response = await fetch('data/market-data.json', { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderMarketData(await response.json());
  } catch (error) {
    document.querySelector('#dataStatus').textContent = 'Data error';
    document.querySelector('#dataSource').textContent = error.message;
  }
};

document.querySelectorAll('a[href^="#"]').forEach((link) => {
  link.addEventListener('click', (event) => {
    const target = document.querySelector(link.getAttribute('href'));
    if (!target) return;
    event.preventDefault();
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
});

loadPhilosophy();
loadMarketData();
