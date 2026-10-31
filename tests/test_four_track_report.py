"""Read-only presentation checks; no real outcome execution."""
from pathlib import Path
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
    assert subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT) == before
