"""Read committed result blobs, reuse the terminal renderer, write outside repositories.

No model/outcome/collection path. A successful rendering is not a study PASS.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.render_daily_decision_report import safe_output  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--as-of', required=True, help='timezone-aware report viewing/generated timestamp')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        output = safe_output(args.output, ROOT)
    except ValueError as exc:
        parser.error(str(exc))
    program = r'''
    if (!globalThis.crypto) Object.defineProperty(globalThis,'crypto',{value:require('node:crypto').webcrypto});
    const cp=require('node:child_process'),A=require('./app.js');
    (async()=>{
      const read=async(_url,s)=>new Uint8Array(cp.execFileSync('git',['show',s.commit+':'+s.path],
        {env:{...process.env,GIT_NO_LAZY_FETCH:'1'},maxBuffer:16*1024*1024,stdio:['ignore','pipe','pipe']}));
      const report=await A.loadFourTrackReport(read,process.argv[1]);
      report.tracks.forEach(t=>t.metrics.forEach(m=>m.display=A.researchMetricText(m)));
      process.stdout.write(JSON.stringify({report,markup:A.fourTrackMarkup(report)}));
    })().catch(e=>{console.error(e.message);process.exit(1)});
    '''
    result = json.loads(subprocess.check_output(['node', '-e', program, args.as_of], cwd=ROOT, text=True))
    report = result['report']
    report['codeIdentity'] = {
        'gitSha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'workingTreeDirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)),
        'sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                   for name in ['app.js', 'index.html', 'styles.css', 'scripts/render_four_track_report.py']},
    }
    def md(value):
        return str(value).replace('|', r'\|').replace('\n', ' ')
    lines = ['# Investment — 네 연구 트랙 결과', '', f"보고 생성/조회 기준: {report['generatedAt']}",
             f"코드 SHA: {report['codeIdentity']['gitSha']}", '',
             '기존 불변 결과 읽기 전용. 보고서 DONE·CI 성공은 과학적 승인이나 투자 적격이 아니다.', '',
             '| 트랙 | 증거 등급 | 자료 / 연구 | 대표 관측 |', '|---|---|---|---|']
    for track in report['tracks']:
        summary_metrics = [track['metrics'][i] for i in ([0, 2] if track['id'] in {'kr', 'industry'} else [0])]
        summary = '; '.join(m['label']+': '+m['display'] for m in summary_metrics)
        lines.append('|'+ '|'.join(md(v) for v in [track['title'], track['evidenceClass'],
            track['reportStatus']+' / '+track['researchStatus'], summary])+'|')
    for t in report['tracks']:
        lines.extend(['', f"## {t['title']} — PR #{t['pr']}", '', t['hypothesis'], '',
                      f"비교 기준: {t['benchmark']} · 투자 적격 미확인", ''])
        for m in t['metrics']:
            denominator = '' if not m['denominator'] else ' / 표본 '+str(m['denominator'])
            lines.append(f"- {m['label']}: **{m['display']}**{denominator}; `{m['source']}:{m['pointer']}`")
        lines.extend(['',t['context'],'', '한계: '+t['limitations'], '', '차단: '+t['blocker'], '',
                      '다음 결정: '+t['nextDecision'], ''])
        for key in t['sources']:
            s = report['sources'][key]
            lines.append(f"- [{s['path']}](https://github.com/jaehojung1879-netizen/Investment/blob/{s['commit']}/{s['path']}) · commit `{s['commit']}` · SHA256 `{s['sha256']}` · {s['snapshotAt']} · {s['status']}")
    output.mkdir(parents=True, exist_ok=False)
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False, sort_keys=True)+'\n')
    (output / 'report.md').write_text('\n'.join(lines)+'\n')
    html = '<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Investment — 네 연구 트랙</title><style>'
    html += (ROOT / 'styles.css').read_text()+'</style><body><main class="wrap"><section><h1>시장·산업·종목 — 네 연구 트랙</h1>'+'<p class="digest">보고서 코드 SHA '+report['codeIdentity']['gitSha']+' · 작업 트리 변경 '+str(report['codeIdentity']['workingTreeDirty'])+'</p>'+result['markup']+'</section></main></body></html>'
    (output / 'report.html').write_text(html)
    print(json.dumps({'report': str(output / 'report.html'), 'reportStatus': [t['reportStatus'] for t in report['tracks']],
                      'productionEffect': 'NONE', 'historicalOutcomeExecutions': 0}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
