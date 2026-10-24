"""Invented documents verify that source tampering cannot masquerade as recovery."""
import base64
import gzip
import json
from pathlib import Path
import subprocess

import pytest
from .source_inventory import BASE, inspect, sha
from .. import run as R


def fixture(root, *, corrupt_archive=False, corrupt_section=False):
    directory = Path(root) / BASE / "synthetic"
    directory.mkdir(parents=True)
    text = "2019년 자회사 분할비율 0.6392187:0.3607813".encode()
    digest = sha(text)
    archive = gzip.compress(json.dumps({digest: base64.b64encode(text + (b"TAMPER" if corrupt_section else b"")).decode()}).encode())
    (directory / "originals.json.gz").write_bytes(archive + (b"TAMPER" if corrupt_archive else b""))
    record = {"target": {"ticker": "009830.KS", "fiscalYear": 2019, "receiptNos": ["SYNTHETIC"]},
              "sections": [{"sha256": digest}], "responses": []}
    other = {**record, "target": {**record["target"], "ticker": "012450.KS"}}
    (directory / "manifest-originals.json").write_text(json.dumps({"archive": "originals.json.gz",
        "archiveSha256": sha(archive), "records": [record, other]}))


@pytest.mark.parametrize("where", ["archive", "section"])
def test_tampered_source_blocks_inventory(tmp_path, where):
    fixture(tmp_path, corrupt_archive=where == "archive", corrupt_section=where == "section")
    with pytest.raises(ValueError, match="DIGEST_MISMATCH"):
        inspect(tmp_path)


def test_unrelated_ratio_is_visible_but_never_becomes_entitlement(tmp_path):
    fixture(tmp_path)
    report = inspect(tmp_path)
    assert report["sections"][0]["mentions"][0]["term"] == "분할비율"
    assert report["status"] == "BLOCKED" and not report["entitlementCertified"]
    assert report["newReturnCalculations"] == report["quoteReads"] == 0


def test_missing_archives_do_not_generate_a_successful_source_review(tmp_path):
    with pytest.raises(ValueError, match="REQUIRED_STORED_ISSUER_SOURCES_MISSING"):
        inspect(tmp_path)


def test_every_original_manifest_artifact_is_tracked_not_only_present_locally():
    manifest = json.loads((R.HERE / "results/manifest.json").read_bytes())
    for name in manifest["filesSha256"]:
        path = str((R.HERE / name).relative_to(R.ROOT))
        tracked = subprocess.check_output(["git", "ls-files", "--", path], cwd=R.ROOT, text=True).strip()
        assert tracked == path, "MANIFEST_ARTIFACT_NOT_COMMITTED:" + path
