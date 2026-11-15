import json

import pytest

from research.corporate_event_readiness_v1.audit import digest, verify


def fixture(tmp_path):
    raw = b"fixed source"
    (tmp_path / "source.txt").write_bytes(raw)
    (tmp_path / "packet-receipts.json").write_text(json.dumps({"files": [
        {"path": "source.txt", "bytes": len(raw), "sha256": digest(raw)}]}))


def test_packet_tamper_and_unreceipted_input(tmp_path):
    fixture(tmp_path)
    assert verify(tmp_path)["status"] == "VERIFIED_BYTES"
    (tmp_path / "source.txt").write_text("changed")
    assert verify(tmp_path)["errors"] == ["DIGEST_MISMATCH:source.txt"]
    (tmp_path / "new.txt").write_text("unexpected")
    assert "UNRECEIPTED:new.txt" in verify(tmp_path)["errors"]


def test_packet_rejects_traversal(tmp_path):
    (tmp_path / "packet-receipts.json").write_text(json.dumps({"files": [{"path": "../outside"}]}))
    with pytest.raises(ValueError, match="INVALID_OR_DUPLICATE"):
        verify(tmp_path)


def test_packet_rejects_symlink(tmp_path):
    fixture(tmp_path)
    (tmp_path / "source.txt").unlink()
    (tmp_path / "source.txt").symlink_to(tmp_path / "not-present")
    assert verify(tmp_path)["errors"] == ["PATH_ESCAPE:source.txt"]
