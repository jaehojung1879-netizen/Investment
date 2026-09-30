"""The single-use operator authorization matches the reviewed harness. Outcome-free: reads no data."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import alpha_opportunity_v5_diagnostics as D  # noqa: E402
from pipeline import alpha_opportunity_v5_execution as X  # noqa: E402
from scripts import execute_alpha_opportunity_model_v5 as CLI  # noqa: E402

PATH = ROOT / "research_specs/alpha-opportunity-model-v5-execution-authorization.json"
SPEC_SHA = (ROOT / "research_specs/alpha-opportunity-model-v5.sha256").read_text().strip()
DIAG_SHA = (ROOT / "research_specs/alpha-opportunity-model-v5-diagnostics-v1.sha256").read_text().strip()


def test_authorization_pins_spec_diagnostics_and_every_harness_file():
    record = json.loads(PATH.read_text())
    assert record["authorizedExecutions"] == 1 and record["authorizedBy"].strip()
    assert record["specSha256"] == SPEC_SHA and record["diagnosticSpecSha256"] == DIAG_SHA
    assert set(record["harnessFiles"]) == set(X.HARNESS_FILES)
    assert D.load_diagnostic_spec(expected_hash=DIAG_SHA) is not None


def test_the_harness_accepts_this_authorization_and_refuses_a_moved_harness_file():
    identity = X.harness_file_hashes(ROOT)
    none_committed = ROOT / "does-not-exist-result.json"
    assert CLI.verify_authorization(PATH, spec_sha256=SPEC_SHA, harness_files=identity,
                                    diagnostic_spec_sha256=DIAG_SHA, committed_result=none_committed)
    moved = dict(identity, **{X.HARNESS_FILES[0]: "0" * 64})
    with pytest.raises(CLI.Refusal, match="AUTHORIZATION_DOES_NOT_MATCH"):
        CLI.verify_authorization(PATH, spec_sha256=SPEC_SHA, harness_files=moved,
                                 diagnostic_spec_sha256=DIAG_SHA, committed_result=none_committed)
