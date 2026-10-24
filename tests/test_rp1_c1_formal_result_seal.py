"""CI: the formal C1 research artifact is archived byte-exactly without re-executing it."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "docs/research-program/results/rp1-c1-us-exposure-formal-20261024/verify.py"


def test_archived_c1_formal_result_matches_original_artifact():
    completed = subprocess.run(
        [sys.executable, str(VERIFY)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    assert result == {
        "status": "VERIFIED_EXACT_ARTIFACT_BYTES",
        "files": 5,
        "independentChecks": 160,
        "resultDecision": "NO_CANDIDATE_NOMINATED_CONTROL_RETAINED",
        "interpretation": "REPLICATED_CONTROL_RETAINED",
    }
