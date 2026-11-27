"""Read-only presentation checks; no real outcome execution."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_four_track_node_contracts():
    result = subprocess.run(['node', '--test', 'tests/four_track_report.test.cjs'], cwd=ROOT,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_report_cli_refuses_repository_output_before_any_read():
    result = subprocess.run([sys.executable, 'scripts/render_four_track_report.py', '--as-of',
        '2026-10-31T00:00:00Z', '--output', str(ROOT / 'not-a-real-report')], cwd=ROOT,
        capture_output=True, text=True, timeout=30)
    assert result.returncode != 0 and 'OUTPUT_INSIDE_REPOSITORY' in result.stderr
    assert not (ROOT / 'not-a-real-report').exists()


def test_reproduction_is_byte_identical_and_does_not_write_research(tmp_path):
    before = subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)
    outputs = [tmp_path / 'first', tmp_path / 'second']
    for output in outputs:
        subprocess.run([sys.executable, 'scripts/render_four_track_report.py', '--as-of',
            '2026-10-31T00:00:00Z', '--output', str(output)], cwd=ROOT,
            capture_output=True, text=True, timeout=60, check=True)
    for name in ['report.json', 'report.md', 'report.html']:
        assert (outputs[0] / name).read_bytes() == (outputs[1] / name).read_bytes()
    summary = next(line for line in (outputs[0] / 'report.md').read_text().splitlines()
                   if line.startswith('|한국 종목 Alpha|'))
    assert 'H126 장중 − 모멘텀 유효쌍 평균:' in summary
    assert 'H126 장중 − ETF 유효쌍 평균:' in summary
    assert subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT) == before


def fixture_git(tmp_path):
    """Serve exact compressed public Git blobs, so CI needs no other PR checkout.

    Only the read-only `git show` calls for these fixtures are intercepted;
    commit/status operations still use real Git. Production uses Git directly.
    """
    directory = tmp_path / 'fixture-bin'
    directory.mkdir()
    wrapper = directory / 'git'
    wrapper.write_text(f'''#!{sys.executable}
import gzip, os, pathlib, sys
args = sys.argv[1:]
if len(args) == 2 and args[0] == 'show':
    commit, _, path = args[1].partition(':')
    if commit == 'e46024ca92be16b5ded9c459797a7027c1d81d23' and path.startswith('research/economic_path_readout_v1/'):
        name = path.rsplit('/', 1)[1]
        if os.environ.get('READOUT_FIXTURE_CORRUPT') == name:
            sys.stdout.buffer.write(b'{{}}')
        else:
            sys.stdout.buffer.write(gzip.decompress((pathlib.Path({str(ROOT / 'tests/fixtures/economic_readout_report_v1')!r}) / (name + '.gz')).read_bytes()))
        sys.exit(0)
os.execv({shutil.which('git')!r}, [{shutil.which('git')!r}, *args])
''')
    wrapper.chmod(0o755)
    return dict(os.environ, PATH=str(directory)+os.pathsep+os.environ['PATH'])


def test_all_formats_agree_on_fixed_real_inputs_units_currency_evidence_and_maturity(tmp_path):
    output = tmp_path / 'actual-source-fixture-report'
    subprocess.run([sys.executable, 'scripts/render_four_track_report.py', '--as-of',
        '2026-11-01T06:00:00Z', '--output', str(output)], cwd=ROOT,
        env=fixture_git(tmp_path), capture_output=True, text=True, timeout=60, check=True)
    report = json.loads((output / 'report.json').read_text())
    saved = report['storedPerformance']
    assert saved['comparisonCount'] == 12
    assert [len(g['comparisonIds']) for g in saved['groups']] == [6, 6]
    html, markdown = [(output / name).read_text() for name in ['report.html', 'report.md']]
    for c in saved['comparisons']:
        assert c['id'] in html and c['id'] in markdown
        for metric in c['metrics']:
            assert metric['display'] in html and metric['display'] in markdown
        for value in [c['candidateInput']['currency'], c['candidateInput']['evidenceClass'],
                      c['candidateInput']['costBasis']]:
            assert value in html and value in markdown
    kr = next(c for c in saved['comparisons'] if c['id'] == 'A/KR/C2-P0')
    assert [m['display'] for m in kr['metrics'][2:5]] == ['+1.8181 pp', '-0.5193 pp', '-0.8804 pp']
    assert kr['metrics'][8]['display'] == '-2.9206 pp'
    us = next(c for c in saved['comparisons'] if c['id'] == 'A/US/C2-P0')
    assert us['candidateInput']['currency'] == 'KRW' and us['candidateInput']['fxReturnsIncluded']
    for text in [html, markdown]:
        assert 'KRW · 환율 포함' in text
        assert 'IMMATURE_AT_AS_OF=46' in text and 'MATURE_TARGET_NO_STORED_ENDPOINT=7' in text
        assert '0.0000 pp' in text and 'QQQ UNAVAILABLE' in text
        assert 'sourceGeneratedAt' not in text  # Human label, never a fabricated timestamp.
    assert saved['sourceGeneratedAt'] is None
    assert report['sources']['economic']['sha256'] == '1267f449b4c2be285f95fa12bfb5f3e093ff05b81c805ff7830bea39343a7431'
    assert report['productionEffect'] == 'NONE' and report['investmentNominations'] == []


def test_cli_corrupt_source_does_not_emit_cached_new_metrics(tmp_path):
    env = fixture_git(tmp_path)
    env['READOUT_FIXTURE_CORRUPT'] = 'results.json'
    output = tmp_path / 'corrupt-source-report'
    subprocess.run([sys.executable, 'scripts/render_four_track_report.py', '--as-of',
        '2026-11-01T06:00:00Z', '--output', str(output)], cwd=ROOT,
        env=env, capture_output=True, text=True, timeout=60, check=True)
    report = json.loads((output / 'report.json').read_text())
    assert report['storedPerformance']['status'] == 'UNKNOWN'
    assert report['sources']['economic']['reason'] == 'SOURCE_HASH_OR_SIZE_MISMATCH'
    assert len(report['tracks']) == 4
    for name in ['report.html', 'report.md']:
        text = (output / name).read_text()
        assert 'UNKNOWN' in text and '+1.8181 pp' not in text
