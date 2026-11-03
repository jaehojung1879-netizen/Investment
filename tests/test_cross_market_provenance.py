"""Byte availability and source admission must remain different assertions."""
import subprocess

import pytest

from research.cross_market_foundation_v1.provenance import (
    read_pinned_blob, sha256_bytes, source_pin, verify_file_receipts, verify_receipt_inventory, verify_source_pin,
)


@pytest.fixture
def source_repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "source.txt").write_bytes(b"raw\r\nbytes\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "source.txt"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Fixture", "-c",
                    "user.email=fixture@example.invalid", "commit", "-qm", "source"], check=True)
    head = subprocess.check_output(["git", "-C", str(tmp_path), "rev-parse", "HEAD"]).decode().strip()
    return tmp_path, head


def test_git_pin_preserves_actual_bytes_not_normalized_text(source_repo):
    repo, head = source_repo
    pin = source_pin(repo, head, "source.txt", role="synthetic parser fixture")
    assert pin["sha256"] == sha256_bytes(b"raw\r\nbytes\n")
    result = verify_source_pin(repo, pin)
    assert result["status"] == "VERIFIED_BYTES"
    assert result["eligibleForResearch"] is None
    # Altering today's worktree cannot alter an immutable source receipt.
    (repo / "source.txt").write_bytes(b"different")
    assert verify_source_pin(repo, pin)["status"] == "VERIFIED_BYTES"


def test_tampered_source_receipt_and_missing_objects_refuse(source_repo):
    repo, head = source_repo
    pin = source_pin(repo, head, "source.txt", role="fixture")
    pin["sha256"] = "0" * 64
    assert verify_source_pin(repo, pin)["status"] == "SOURCE_DIGEST_MISMATCH"
    pin["commit"] = "0" * 40
    assert verify_source_pin(repo, pin)["status"] == "SOURCE_OBJECT_UNAVAILABLE"


@pytest.mark.parametrize("commit,path,code", [
    ("main", "source.txt", "EXACT_COMMIT_REQUIRED"),
    ("a" * 40, "../source.txt", "INVALID_SOURCE_PATH"),
    ("a" * 40, "/source.txt", "INVALID_SOURCE_PATH"),
    ("a" * 40, "HEAD:source.txt", "INVALID_SOURCE_PATH"),
])
def test_reference_cannot_float_or_traverse(tmp_path, commit, path, code):
    with pytest.raises(ValueError, match=code):
        read_pinned_blob(tmp_path, commit, path)


def test_retained_evidence_tamper_duplicate_and_symlink_escape(tmp_path):
    root = tmp_path / "evidence"
    root.mkdir()
    (root / "source").write_bytes(b"x")
    receipt = {"path": "source", "bytes": 1, "sha256": sha256_bytes(b"x")}
    assert verify_file_receipts(root, [receipt])[0]["status"] == "VERIFIED_BYTES"
    (root / "source").write_bytes(b"y")
    assert verify_file_receipts(root, [receipt])[0]["status"] == "EVIDENCE_DIGEST_MISMATCH"
    with pytest.raises(ValueError, match="DUPLICATE_EVIDENCE_PATH"):
        verify_file_receipts(root, [receipt, receipt])
    (tmp_path / "outside").write_bytes(b"secretless")
    (root / "escape").symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError, match="EVIDENCE_PATH_ESCAPE"):
        verify_file_receipts(root, [{"path": "escape"}])


def test_receipt_list_cannot_silently_omit_a_source_or_code_file(tmp_path):
    (tmp_path / "source.json").write_text("{}")
    (tmp_path / "implementation.py").write_text("# fixture")
    manifest = tmp_path / "evidence/evidence-receipts.json"
    manifest.parent.mkdir()
    manifest.write_text("{}")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__/ignored.pyc").write_bytes(b"cache")
    receipts = [{"path": "source.json"}]
    assert verify_receipt_inventory(tmp_path, receipts) == ["UNRECEIPTED_PACKET_FILE:implementation.py"]
    receipts.append({"path": "implementation.py"})
    assert verify_receipt_inventory(tmp_path, receipts) == []
