"""Historical research bytes and the original v1 record remain immutable.

Owner-approved v2 changes only ordinary numerical installation and the closed
study's read-only diagnostic route. The original 5,992-byte prefix is verified
from Git. Current bytes must equal the exact bounded transformation of #315;
formal execution, triggers, permissions and scientific tests stay protected.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pipeline import kr_alpha_atlas_reproducibility as V4
from pipeline import pages_operational_maintenance as M

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
    data = M.historical(ROOT, WORKFLOW)
    assert data.count(BOUNDARY) == 1
    prefix = data[:data.index(BOUNDARY)]
    assert len(prefix) == SEALED_PREFIX_BYTES
    assert hashlib.sha256(prefix).hexdigest() == SEALED_PREFIX_SHA256
    # v2 changes only the closed diagnostic route, never the formal job.
    current = (ROOT / WORKFLOW).read_bytes()
    assert current == M.pages_variant(M.historical(ROOT, WORKFLOW, M.PARENT))
    assert V4.pages_maintenance_admitted(ROOT)


def test_build_and_deploy_is_the_last_job_so_the_prefix_covers_every_research_job():
    text = (ROOT / WORKFLOW).read_text()
    tail = text.split("  build-and-deploy:\n", 1)[1]
    for job in ("  matrix-diagnostic:", "  matrix-formal-owner-only:"):
        assert job in text.split("  build-and-deploy:\n", 1)[0] and job not in tail
    # no further top-level job after build-and-deploy (a two-space key ending in ':' on its own line)
    assert not [line for line in tail.splitlines() if line.startswith("  ") and not line.startswith("   ") and line.endswith(":")]

# Hard pin the reviewed maintenance record, in addition to its sidecar.
MAINTENANCE_RECORD_SHA256 = "436ce3361d1183fe11db0c931de0cf688dfdd021ac70c7173b8b35a939e25ddf"


def test_versioned_record_matches_the_exact_scoped_maintenance():
    raw = (ROOT / M.PREVIOUS).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == MAINTENANCE_RECORD_SHA256
    assert V4.pages_maintenance_admitted(ROOT)


@pytest.mark.parametrize("target", [
    V4.MAINTENANCE_RECORD, V4.MAINTENANCE_SIDECAR,
    V4.PAGES_WORKFLOW, V4.VERIFIER_MODULE, V4.ADDENDUM
])
def test_maintenance_fails_closed_if_bytes_change(tmp_path, target):
    (tmp_path / '.git').symlink_to(ROOT / '.git')
    paths = {M.RECORD, M.SIDECAR, M.PREVIOUS, M.PREVIOUS.replace('.json', '.sha256'),
             M.PAGES, M.TESTS, M.VERIFIER, M.WORKFLOW_TEST, V4.ADDENDUM, V4.SIDECAR} | M.AUXILIARY
    for rel in paths:
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((ROOT / rel).read_bytes())
    damaged = tmp_path / target
    damaged.write_bytes(damaged.read_bytes() + b"\n# corrupted\n")
    with pytest.raises((ValueError, json.JSONDecodeError)):
        V4.pages_maintenance_admitted(tmp_path)
