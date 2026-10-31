"""Read-only presentation checks; no real outcome execution."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_four_track_node_contracts():
    result = subprocess.run(['node', '--test', 'tests/four_track_report.test.cjs'], cwd=ROOT,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_report_cli_refuses_repository_output_before_any_read():
    result = subprocess.run(['python', 'scripts/render_four_track_report.py', '--as-of',
        '2026-10-31T00:00:00Z', '--output', str(ROOT / 'not-a-real-report')], cwd=ROOT,
        capture_output=True, text=True, timeout=30)
    assert result.returncode != 0 and 'OUTPUT_INSIDE_REPOSITORY' in result.stderr
    assert not (ROOT / 'not-a-real-report').exists()
