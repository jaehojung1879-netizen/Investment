"""Python/JS integration with isolated invented current-input fixtures."""
import json
import os
from pathlib import Path
import subprocess

from pipeline import current_champion_decisions as C
from test_current_champion_decisions import source

ROOT = Path(__file__).resolve().parents[1]


def test_v3_presentation_and_python_receipt_digest(tmp_path):
    site = source()
    C.publish(site, "a"*64, tmp_path)
    (tmp_path/"site.json").write_text(json.dumps(site))
    environment = dict(os.environ)
    environment["CHAMPION_FIXTURE"] = str(tmp_path)
    result = subprocess.run(["node", "--test", "tests/research_terminal_v3.test.cjs"], cwd=ROOT,
                            env=environment, capture_output=True, text=True, timeout=60, check=False)
    assert result.returncode == 0, result.stdout+result.stderr
