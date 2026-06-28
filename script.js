const marketMetrics = [
  { label: 'Trend Score', value: '68/100', tone: 'positive', note: 'MA50이 MA200 위에 있는 중기 우위 구간을 가정한 샘플 지표입니다.' },
  { label: 'Volatility Heat', value: '중립', tone: '', note: 'VIX ratio와 realized volatility가 급격히 확대되는지 별도로 감시합니다.' },
  { label: 'Relative Strength', value: 'QQQ > SPY', tone: 'positive', note: '성장주 상대강도가 유지될 때만 공격적 해석을 허용합니다.' },
  { label: 'Macro Stress', value: '주의', tone: 'warning', note: '2Y/10Y 금리 변화와 수익률 곡선 압력을 리스크 예산에 반영합니다.' },
];

const kpiGrid = document.querySelector('#kpiGrid');
if (kpiGrid) {
  marketMetrics.forEach((metric) => {
    const card = document.createElement('article');
    card.className = `kpi-card ${metric.tone}`.trim();
    card.innerHTML = `<span>${metric.label}</span><strong>${metric.value}</strong><p>${metric.note}</p>`;
    kpiGrid.appendChild(card);
  });
}

document.querySelectorAll('a[href^="#"]').forEach((link) => {
  link.addEventListener('click', (event) => {
    const target = document.querySelector(link.getAttribute('href'));
    if (!target) return;
    event.preventDefault();
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    document.querySelector('#site-menu')?.classList.remove('open');
    document.querySelector('.nav-toggle')?.setAttribute('aria-expanded', 'false');
  });
});

const navToggle = document.querySelector('.nav-toggle');
const siteMenu = document.querySelector('#site-menu');
navToggle?.addEventListener('click', () => {
  const isOpen = siteMenu?.classList.toggle('open');
  navToggle.setAttribute('aria-expanded', String(Boolean(isOpen)));
});
