'use strict';

const md2html = (md) => {
  const lines = md.split('\n');
  let html = '';
  let inList = false;
  const closeList = () => { if (inList) { html += '</ul>'; inList = false; } };
  lines.forEach((line) => {
    if (line.startsWith('## ')) { closeList(); html += `<h2>${line.slice(3)}</h2>`; }
    else if (line.startsWith('# ')) { closeList(); html += `<h1>${line.slice(2)}</h1>`; }
    else if (line.startsWith('- ')) { if (!inList) { html += '<ul>'; inList = true; } html += `<li>${line.slice(2)}</li>`; }
    else if (/^\d+\. /.test(line)) { if (!inList) { html += '<ul>'; inList = true; } html += `<li>${line.replace(/^\d+\. /, '')}</li>`; }
    else if (line.trim()) { closeList(); html += `<p>${line}</p>`; }
  });
  closeList();
  return html.replaceAll('**', '');
};

fetch('docs/investment-philosophy.md', { cache: 'no-store' })
  .then((response) => {
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.text();
  })
  .then((text) => { document.querySelector('#rulesDoc').innerHTML = md2html(text); })
  .catch(() => { document.querySelector('#rulesDoc').textContent = '상세 문서를 불러오지 못했습니다. 잠시 후 다시 확인해 주세요.'; });
