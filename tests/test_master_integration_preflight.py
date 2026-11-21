"""Git fixture reads are not production recordings."""
import json
from pathlib import Path
import subprocess

import pytest

from research.master_integration_preflight_v1 import preflight as P


def repo_fixture(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for name in ("champion", "weekly"):
        path = tmp_path / P.SOURCE_PATHS[name]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"generatedAt": "2026-10-30T22:00:00Z"}))
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Fixture", "-c",
                    "user.email=fixture@example.invalid", "commit", "-qm", "fixture"], check=True)
    sha = subprocess.check_output(["git", "-C", str(tmp_path), "rev-parse", "HEAD"]).decode().strip()
    return tmp_path, sha


def test_coherent_bytes_are_not_authorization_or_a_first_receipt(tmp_path):
    repo, sha = repo_fixture(tmp_path)
    before = subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"])
    report = P.inspect_snapshot(repo, sha)
    assert report["sameGeneration"] and report["status"] == "BLOCKED"
    assert report["productionStoreStatus"] == "ABSENT"
    assert report["firstRealReceiptVerified"] is False
    assert report["receiptWrites"] == report["productionWrites"] == report["priceReads"] == 0
    assert report["performance"] is None
    assert before == subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"])
    assert not (repo / P.SOURCE_PATHS["productionStore"]).exists()


def test_pinned_source_not_current_worktree_or_arbitrary_path(tmp_path):
    repo, sha = repo_fixture(tmp_path)
    path = repo / P.SOURCE_PATHS["champion"]
    original = path.read_bytes()
    path.write_bytes(b"changed")
    raw, receipt = P.read_source(repo, sha, P.SOURCE_PATHS["champion"])
    assert raw == original and receipt["status"] == "VERIFIED_LOCAL_BYTES"
    with pytest.raises(ValueError, match="EXACT_SOURCE"):
        P.read_source(repo, "main", P.SOURCE_PATHS["champion"])
    with pytest.raises(ValueError, match="EXACT_SOURCE"):
        P.read_source(repo, sha, "../secret")


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"x":NaN}', b'{"x":1e999}', b'[]'])
def test_invalid_json_source_is_not_admitted(raw):
    with pytest.raises(ValueError):
        P.strict_object(raw)


def test_old_premature_final_is_classified_without_rewriting_history(tmp_path):
    from pipeline import weekly_decision as W
    repo, _ = repo_fixture(tmp_path)
    bad = W.build_receipt({"region":"KR","asOfDate":"2026-10-16"},
                          generated_at="2026-10-16T04:44:48Z",inputs={},evidence={},week_status="FINAL_WEEKLY")
    good = W.build_receipt({"region":"US","asOfDate":"2026-10-16"},
                           generated_at="2026-10-16T22:00:00Z",inputs={},evidence={},week_status="FINAL_WEEKLY")
    path=repo/P.SOURCE_PATHS["weeklyReceipts"]
    raw=W.canonical(bad)+b"\n"+W.canonical(good)+b"\n"
    path.write_bytes(raw)
    subprocess.run(["git","-C",str(repo),"add","."],check=True)
    subprocess.run(["git","-C",str(repo),"-c","user.name=Fixture","-c","user.email=fixture@example.invalid",
                    "commit","-qm","historical fixtures"],check=True)
    sha=subprocess.check_output(["git","-C",str(repo),"rev-parse","HEAD"]).decode().strip()
    report=P.inspect_snapshot(repo,sha)
    assert len(report["verifiedStoredWeeklyReceipts"])==1
    assert len(report["rejectedStoredWeeklyReceipts"])==1
    assert report["sources"]["weeklyReceipts"]["status"]=="VERIFIED_LOCAL_BYTES"
    assert report["status"]=="BLOCKED" and path.read_bytes()==raw


def test_production_workflow_and_scientific_paths_not_modified():
    root = Path(__file__).resolve().parents[1]
    changed = subprocess.check_output([
        "git", "-C", str(root), "diff", "37f8cbf6b1c066f6b3c65235953648d17ebf2f69", "--name-only",
        "--", ".github", "pipeline", "scripts", "data", "research_specs", "docs/results", "AGENTS.md"
    ]).decode().splitlines()
    assert changed == []
