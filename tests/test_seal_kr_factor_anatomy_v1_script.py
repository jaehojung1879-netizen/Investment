"""Infrastructure tests for the temporary kr-factor-anatomy-v1 sealing path (synthetic archives only).

This file and the helper script are removed on the result-seal branch."""
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "seal" / "seal_kr_factor_anatomy_v1.py"
WORKFLOW = ROOT / ".github" / "workflows" / "seal-kr-factor-anatomy-v1.yml"
spec_ = importlib.util.spec_from_file_location("seal_script", SCRIPT)
S = importlib.util.module_from_spec(spec_)
spec_.loader.exec_module(S)


def fake_zip(path, manifest_over=None, drop=None, tamper=None):
    anatomy, report = b'{"x": 1}\n', b"# report\n"
    manifest = {"studyId": S.STUDY, "specSha256": S.SPEC_SHA256, "inputIdentitySha256": S.INPUT_IDENTITY_SHA256,
                "scientificStatus": S.SCIENTIFIC_STATUS,
                "files": {"anatomy.json": S.sha256_bytes(anatomy), "report.md": S.sha256_bytes(report)}}
    manifest.update(manifest_over or {})
    members = {"anatomy.json": anatomy if not tamper else b"changed", "report.md": report,
               "manifest.json": (json.dumps(manifest, sort_keys=True) + "\n").encode()}
    if drop:
        members.pop(drop)
    with zipfile.ZipFile(path, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)
    return members


def test_workflow_is_dispatch_only_main_only_with_the_exact_identities_and_no_merge():
    text = WORKFLOW.read_text()
    assert "workflow_dispatch:" in text and "pull_request" not in text and "schedule" not in text and "push:" not in text
    assert "contents: write" in text and "pull-requests: write" in text and "actions: read" in text
    for token in ("11207962601", "f8020bdac9878f523091881d129e3c414234012c17e1fd61e1e49b6d6538b80f",
                  "research/kr-factor-anatomy-v1-result-seal", "gh pr create --draft", "refs/heads/main"):
        assert token in text
    assert "gh pr merge" not in text and "--auto" not in text and "pulls/" not in text
    assert text.index("sha256sum artifact.zip") < text.index("seal --archive")


def test_constants_match_the_handoff_and_the_committed_spec():
    assert S.ARCHIVE_SHA256 == "f8020bdac9878f523091881d129e3c414234012c17e1fd61e1e49b6d6538b80f"
    assert (S.RUN_ID, S.ARTIFACT_ID) == (36960496371, 11207962601)
    assert (ROOT / S.SPEC_SIDECAR).read_text().strip() == S.SPEC_SHA256
    S.check_main_state(ROOT)


def test_script_imports_no_anatomy_or_portfolio_code():
    tree = ast.parse(SCRIPT.read_text())
    modules = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    modules |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert modules & {m for m in modules if m and m.startswith("pipeline")} == {"pipeline.alpha_opportunity_spec"}


def test_archive_digest_is_checked_before_anything_is_extracted(tmp_path):
    fake_zip(tmp_path / "a.zip")
    with pytest.raises(SystemExit, match="ARCHIVE_SHA256_MISMATCH"):
        S.verify_archive(tmp_path / "a.zip")
    assert not (tmp_path / "out").exists()


def test_extract_verifies_manifest_provenance_and_file_hashes(tmp_path):
    members = fake_zip(tmp_path / "a.zip")
    verified = S.extract_and_verify(tmp_path / "a.zip", tmp_path / "w")
    assert verified["manifest"]["scientificStatus"] == S.SCIENTIFIC_STATUS
    for i, (over, code) in enumerate((({"specSha256": "0" * 64}, "MANIFEST_MISMATCH: specSha256"),
                       ({"inputIdentitySha256": "0" * 64}, "MANIFEST_MISMATCH: inputIdentitySha256"),
                       ({"scientificStatus": "VALIDATED"}, "MANIFEST_MISMATCH: scientificStatus"),
                       ({"studyId": "other"}, "MANIFEST_MISMATCH: studyId"))):
        fake_zip(tmp_path / "b.zip", manifest_over=over)
        with pytest.raises(SystemExit, match=code):
            S.extract_and_verify(tmp_path / "b.zip", tmp_path / f"w{i}")
    fake_zip(tmp_path / "c.zip", tamper=True)
    with pytest.raises(SystemExit, match="MANIFEST_FILE_HASH_MISMATCH: anatomy.json"):
        S.extract_and_verify(tmp_path / "c.zip", tmp_path / "wc")
    fake_zip(tmp_path / "d.zip", drop="report.md")
    with pytest.raises(SystemExit, match="MISSING_REQUIRED_FILE: report.md"):
        S.extract_and_verify(tmp_path / "d.zip", tmp_path / "wd")
    assert members


def test_seal_copies_exact_bytes_and_records_provenance(tmp_path):
    members = fake_zip(tmp_path / "a.zip")
    verified = S.extract_and_verify(tmp_path / "a.zip", tmp_path / "w")
    root = tmp_path / "repo"
    prov = S.seal(tmp_path / "w", root, "2026-10-02T00:00:00Z", verified)
    for name, destination in S.DESTINATIONS.items():
        assert (root / destination).read_bytes() == members[name]
        assert prov["committedFiles"][destination]["sha256"] == S.sha256_bytes(members[name])
    assert prov["statisticsRecomputed"] is False and prov["artifactArchiveSha256"] == S.ARCHIVE_SHA256
    assert json.loads((root / S.PROVENANCE).read_text()) == prov


def test_metadata_must_match_exactly():
    good = {"id": S.ARTIFACT_ID, "name": S.ARTIFACT_NAME, "expired": False, "digest": "sha256:" + S.ARCHIVE_SHA256,
            "workflow_run": {"id": S.RUN_ID, "head_sha": S.EXECUTION_SHA}}
    assert S.check_artifact_metadata(good)
    for key, value, code in (("id", 1, "ID_OR_NAME"), ("name", "x", "ID_OR_NAME"), ("expired", True, "EXPIRED"),
                             ("digest", "sha256:" + "0" * 64, "DIGEST"),
                             ("workflow_run", {"id": 1, "head_sha": S.EXECUTION_SHA}, "RUN"),
                             ("workflow_run", {"id": S.RUN_ID, "head_sha": "0" * 40}, "EXECUTION_SHA")):
        with pytest.raises(SystemExit, match=code):
            S.check_artifact_metadata({**good, key: value})
