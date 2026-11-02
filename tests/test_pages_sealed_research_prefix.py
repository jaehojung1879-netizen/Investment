"""The production fix may change only the build-and-deploy job of pages.yml.

KR Alpha Atlas Phase C v4 seals the WHOLE pages.yml (sha256 d13e2a45...) because its research jobs (matrix-diagnostic and
matrix-formal-owner-only), triggers, permissions and concurrency live in that file. This test reads the seal, never edits
it, and proves mechanically that every byte before `build-and-deploy:` is still the sealed file's bytes, so the research
workflow that the seal protects is unchanged. It does not make the seal pass: the v4 validator still refuses the new
whole-file hash until the owner approves a versioned maintenance exception (docs/operations/pages-state-stabilization.md).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pipeline import kr_alpha_atlas_reproducibility as V4

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ".github/workflows/pages.yml"
BOUNDARY = b"  build-and-deploy:\n"
SEALED_FILE_SHA256 = "d13e2a457072251267a756a8f174dfe2eccdc5458706305fdb917157275e4577"
# sha256 of the sealed file's bytes up to (not including) BOUNDARY, computed from the sealed blob on main 37f8cbf6.
SEALED_PREFIX_SHA256 = "048356c7b43e499b32660ce40c0b1dde9db7e43b33a58fd36df8a4ea51e17b30"
SEALED_PREFIX_BYTES = 5992


def test_the_seal_itself_is_untouched():
    addendum = json.loads((ROOT / V4.ADDENDUM).read_text())
    assert addendum["additionalDependencyHashes"][WORKFLOW] == SEALED_FILE_SHA256
    assert hashlib.sha256((ROOT / V4.ADDENDUM).read_bytes()).hexdigest() == (ROOT / V4.SIDECAR).read_text().strip()
    assert WORKFLOW in V4.ADDITIONAL_FILES
    assert addendum["formalExecutionAuthorized"] is False


def test_every_byte_before_build_and_deploy_is_the_sealed_research_workflow():
    data = (ROOT / WORKFLOW).read_bytes()
    assert data.count(BOUNDARY) == 1
    prefix = data[:data.index(BOUNDARY)]
    assert len(prefix) == SEALED_PREFIX_BYTES
    assert hashlib.sha256(prefix).hexdigest() == SEALED_PREFIX_SHA256


def test_build_and_deploy_is_the_last_job_so_the_prefix_covers_every_research_job():
    text = (ROOT / WORKFLOW).read_text()
    tail = text.split("  build-and-deploy:\n", 1)[1]
    for job in ("  matrix-diagnostic:", "  matrix-formal-owner-only:"):
        assert job in text.split("  build-and-deploy:\n", 1)[0] and job not in tail
    # no further top-level job after build-and-deploy (a two-space key ending in ':' on its own line)
    assert not [line for line in tail.splitlines() if line.startswith("  ") and not line.startswith("   ") and line.endswith(":")]
