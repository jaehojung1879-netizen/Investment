"""The single-use operator authorization matches the sealed spec. Outcome-free: reads no data."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from pipeline import kr_model_portfolio_execution as X

ROOT = Path(__file__).resolve().parents[1]
SPEC_SHA = "563b64ee6f4709a263719669f795ad55e7828e340f082358af1599453253b6fd"
DIAG_SHA = "0fd3baf70d0fbe24e17a9ab2244ea6c3a4d8ac50c0af634a196fe3c3cb885f03"
INPUT_IDENTITY = "233df37ed205cc6b48828121e711417ccf961301dc58aa252430b343db9666a7"
MERGE = "2caea7ba8b5242905c41266410ade5c0c8cadee7"


def record():
    return json.loads((ROOT / X.AUTH_PATH).read_text())


def test_authorization_pins_every_frozen_identity():
    frozen, sha = X.load_spec()
    auth = record()
    assert sha == SPEC_SHA == (ROOT / X.SPEC_PATH).with_suffix(".sha256").read_text().strip()
    assert auth["studyId"] == "kr-model-overlay-portfolio-v1" == X.STUDY
    assert auth["authorizedExecutions"] == 1 and auth["authorizedBy"] == "jung-jaeho"
    assert auth["mergeCommit"] == MERGE
    assert auth["specSha256"] == sha and auth["diagnosticSpecSha256"] == DIAG_SHA == frozen["diagnostics"]["sha256"]
    assert auth["harnessHashes"] == frozen["dependencyHashes"]
    assert auth["inputSnapshotSha256"] == INPUT_IDENTITY
    assert auth["inputArtifact"] == "kr-model-raw-inputs-36844599518" and auth["inputRunId"] == 36844599518


def test_require_authorization_accepts_exact_record_and_refuses_any_moved_identity():
    frozen, sha = X.load_spec()
    identity = {"sha256": INPUT_IDENTITY}
    assert X.require_authorization(frozen, sha, identity, ROOT)["mergeCommit"] == MERGE
    moved = deepcopy(frozen)
    first = sorted(moved["dependencyHashes"])[0]
    moved["dependencyHashes"][first] = "0" * 64
    with pytest.raises(ValueError, match="AUTHORIZATION_IDENTITY_MISMATCH"):
        X.require_authorization(moved, sha, identity, ROOT)
    with pytest.raises(ValueError, match="AUTHORIZATION_IDENTITY_MISMATCH"):
        X.require_authorization(frozen, sha, {"sha256": "1" * 64}, ROOT)
    with pytest.raises(ValueError, match="AUTHORIZATION_IDENTITY_MISMATCH"):
        X.require_authorization(frozen, "2" * 64, identity, ROOT)


def test_authorization_creates_no_result_lock_or_permit():
    # State transition: the formal result is now sealed at RESULT_PATH (it was absent before execution).
    # Everything below, the permit requirement and zero counters, is unchanged.
    assert (ROOT / X.RESULT_PATH).is_file()
    counters = X.Counters()
    assert counters.zero()
    with pytest.raises(ValueError, match="WITHOUT_PERMIT"):
        X.build_labels(None, {}, X.load_spec()[0], 126, counters)
    assert counters.zero()
