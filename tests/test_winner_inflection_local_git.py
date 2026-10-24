"""Real Git repositories with invented bytes; no historical payloads or network."""

import json
import os
from pathlib import Path
import subprocess

import pytest

from pipeline import industry_foundation as IF
from pipeline import winner_inflection_admission as A
from pipeline import winner_inflection_local_git as L
from scripts import inspect_experiment_sources as S


def git(root, *args, **kw):
    return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.DEVNULL, **kw)


@pytest.fixture
def repos(tmp_path, monkeypatch):
    donor, target = tmp_path / "donor", tmp_path / "target"
    donor.mkdir()
    target.mkdir()
    git(donor, "init", "-q")
    git(target, "init", "--bare", "-q")
    manifest = {"components": {"price/2020-01": ["a" * 64]}}
    sha = IF.digest(manifest)
    manifest["sha256"] = sha
    paths = [f"ledger/fundamentals/us/finnhub-{y}.jsonl.gz" for y in range(2011, 2022)]
    paths += [S.MEMBERS, S.SECTORS, S.US_IDENTITY, "ledger/replay-inputs/objects/" + "a" * 64 + ".json.gz"]
    for i, p in enumerate(paths):
        q = donor / p
        q.parent.mkdir(parents=True, exist_ok=True)
        q.write_text(f"INVENTED UNOPENED PAYLOAD {i}\n")
    p = donor / S.MANIFEST
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(manifest))
    git(donor, "add", ".")
    git(
        donor,
        "-c",
        "user.name=SYNTHETIC",
        "-c",
        "user.email=syn@example.invalid",
        "commit",
        "-qm",
        "invented metadata recovery",
    )
    commit = git(donor, "rev-parse", "HEAD", text=True).strip()
    monkeypatch.setattr(S, "SOURCE_COMMIT", commit)
    monkeypatch.setattr(S, "CODE_BASE", commit)
    spec = json.loads((Path(__file__).resolve().parents[1] / A.SPEC_PATH).read_text())
    spec.update(sourceCommit=commit, metadataCommit=commit, sourceManifestSha256=sha)

    def validate(raw):
        value = json.loads(raw)
        if IF.digest({k: v for k, v in value.items() if k != "sha256"}) != sha:
            raise ValueError("MANIFEST_CHANGED")

    return donor, target, commit, paths, spec, validate


def test_recovery_of_metadata_does_not_admit_missing_payloads(repos):
    donor, target, commit, paths, spec, validate = repos
    before = A.source_preflight(target, spec)
    assert before["reason"] == "PINNED_COMMIT_METADATA_MISSING"
    report = L.restore_metadata(target, donor, [commit], commit, S.MANIFEST, validate)
    assert report["marketPayloadBlobsCopied"] == report["networkRequests"] == report["outcomeReads"] == 0
    assert report["manifestBlobs"] == 1 and report["authorizationGranted"] is False
    objects = git(target, "cat-file", "--batch-all-objects", "--batch-check=%(objecttype)", text=True).splitlines()
    assert objects.count("blob") == 1
    assert set(objects) <= {"blob", "commit", "tree"}
    after = A.source_preflight(target, spec)
    assert after["status"] == "BLOCKED"
    assert after["requiredObjects"] == after["missingObjects"] == len(paths) == 15
    for p in paths:
        oid = git(donor, "rev-parse", commit + ":" + p, text=True).strip()
        assert L.object_type(target, oid) is None


def test_existing_local_payloads_become_addressable_without_source_retrieval(repos):
    donor, target, commit, paths, spec, validate = repos
    # Only invented opaque blobs placed in target before its commit/tree bindings.
    for p in paths:
        git(target, "hash-object", "-w", "--stdin", input=(donor / p).read_bytes())
    assert A.source_preflight(target, spec)["reason"] == "PINNED_COMMIT_METADATA_MISSING"
    L.restore_metadata(target, donor, [commit], commit, S.MANIFEST, validate)
    after = A.source_preflight(target, spec)
    assert after["status"] == "READY" and after["missingObjects"] == 0
    assert after["payloadReads"] == 0
    # Git readiness never resolves legal/identity review or grants execution.
    review = json.loads((Path(__file__).resolve().parents[1] / A.REVIEW_PATH).read_text())
    result = A.preflight(target, spec, review)
    assert result["status"] == "BLOCKED" and any("rights" in r for r in result["reasons"])


def test_invalid_manifest_does_not_write_any_target_object(repos):
    donor, target, commit, _, _, _ = repos

    def refuse(_):
        raise ValueError("MANIFEST_CHANGED")

    with pytest.raises(ValueError, match="MANIFEST_CHANGED"):
        L.restore_metadata(target, donor, [commit], commit, S.MANIFEST, refuse)
    assert L.object_type(target, commit) is None


def test_partial_clone_cannot_fetch_even_if_git_ignores_environment_guard(repos, tmp_path):
    donor, _, commit, paths, spec, _ = repos
    git(donor, "config", "uploadpack.allowFilter", "true")
    clone = tmp_path / "partial"
    git(tmp_path, "clone", "--bare", "--filter=blob:none", "--no-local", donor.as_uri(), str(clone))
    marker = tmp_path / "transport-attempts"
    hook = tmp_path / "deny-upload-pack"
    hook.write_text('#!/bin/sh\nprintf FETCH >> "' + str(marker) + '"\nexit 99\n')
    hook.chmod(0o700)
    git(clone, "config", "remote.origin.uploadpack", str(hook))
    missing = git(donor, "rev-parse", commit + ":" + paths[0], text=True).strip()
    env = {k: v for k, v in os.environ.items() if k != "GIT_NO_LAZY_FETCH"}
    with L.local_view(clone) as view:
        assert not git(view, "remote", text=True).strip()
        assert L.object_type(view, commit) == "commit"
        result = subprocess.run(
            ["git", "-C", str(view), "cat-file", "-e", missing], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        assert result.returncode != 0 and not marker.exists()
    assert A.source_preflight(clone, spec)["status"] == "BLOCKED"
    assert not marker.exists()
    # Positive control proves the simulated promisor transport really is armed.
    subprocess.run(
        ["git", "-C", str(clone), "cat-file", "-e", missing], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    assert marker.exists()


def test_worktree_alternate_view_uses_shared_object_store_without_refs(repos, tmp_path):
    donor, _, commit, _, _, _ = repos
    work = tmp_path / "worktree"
    git(donor, "worktree", "add", "--detach", str(work), commit)
    with L.local_view(work) as view:
        assert L.object_type(view, commit) == "commit"
        assert git(view, "for-each-ref", text=True) == ""


def test_no_remote_or_source_loader_is_called_on_missing_commit(repos, monkeypatch):
    _, target, _, _, spec, _ = repos

    class Refused:
        def __init__(self, *_):
            pytest.fail("payload loader constructed without local commit")

    monkeypatch.setattr(S, "Sources", Refused)
    assert A.source_preflight(target, spec)["reason"] == "PINNED_COMMIT_METADATA_MISSING"


def test_new_metadata_guard_is_pinned_by_owner_request():
    assert "pipeline/winner_inflection_local_git.py" in A.CLOSURE
