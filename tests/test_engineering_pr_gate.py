"""Synthetic-only safety tests for the trusted engineering merge eligibility check."""
from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.engineering_pr_gate import eligibility_reasons

HEAD = "f" * 40


def pr(**overrides):
    data = {
        "state": "open",
        "draft": False,
        "base": {"ref": "main", "repo": {"full_name": "example/Investment"}},
        "head": {"sha": HEAD, "repo": {"full_name": "example/Investment"}},
        "user": {"login": "author"},
        "labels": [{"name": "auto-merge:engineering"}],
    }
    data.update(overrides)
    return data


def files():
    return [
        {"filename": "scripts/devtools/report.py", "status": "added", "patch": "@@ +print(1)", "changes": 10},
        {"filename": "tests/test_devtools_report.py", "status": "added", "patch": "@@ +assert", "changes": 20},
    ]


def reviews(sha=HEAD, reviewer="independent", state="APPROVED"):
    return [{"user": {"login": reviewer}, "state": state, "commit_id": sha,
             "submitted_at": "2026-10-19T08:00:00Z", "id": 100}]


def codes(p=None, f=None, r=None):
    return eligibility_reasons(
        pr() if p is None else p,
        files() if f is None else f,
        reviews() if r is None else r,
    )


def test_only_narrow_devtools_change_with_distinct_sha_approval_is_eligible():
    assert codes() == []


@pytest.mark.parametrize("change,code", [
    ({"draft": True}, "PR_MUST_BE_OPEN_AND_READY_NOT_DRAFT"),
    ({"state": "closed"}, "PR_MUST_BE_OPEN_AND_READY_NOT_DRAFT"),
    ({"base": {"ref": "release", "repo": {"full_name": "example/Investment"}}}, "BASE_MUST_BE_MAIN"),
    ({"head": {"sha": HEAD, "repo": {"full_name": "fork/Investment"}}}, "CROSS_REPOSITORY_PR_NOT_ADMITTED"),
    ({"labels": []}, "ENGINEERING_OPT_IN_LABEL_ABSENT"),
])
def test_owner_and_pr_gates_fail_closed(change, code):
    assert code in codes(p=pr(**change))


@pytest.mark.parametrize("file,expected", [
    ("pipeline/kr_market_risk_model.py", "PATH_REQUIRES_OWNER_APPROVAL"),
    (".github/workflows/tests.yml", "PATH_REQUIRES_OWNER_APPROVAL"),
    ("docs/research-program/03-studies-abc-ko.md", "PATH_REQUIRES_OWNER_APPROVAL"),
    ("AGENTS.md", "PATH_REQUIRES_OWNER_APPROVAL"),
    ("scripts/collect_krx_daily_prices.py", "PATH_REQUIRES_OWNER_APPROVAL"),
    ("tests/test_alpha_model.py", "PATH_REQUIRES_OWNER_APPROVAL"),
])
def test_research_operations_workflows_and_sealed_paths_not_auto_eligible(file, expected):
    changed = files() + [{"filename": file, "status": "modified", "patch": "@@", "changes": 5}]
    assert any(x.startswith(expected) for x in codes(f=changed))


def test_modifying_the_guard_itself_is_not_eligible():
    changed = files() + [{"filename": "scripts/engineering_pr_gate.py", "status": "modified", "patch": "@@", "changes": 2}]
    assert any(x.startswith("PATH_REQUIRES_OWNER_APPROVAL") for x in codes(f=changed))


def test_no_tests_or_no_source_is_not_eligible():
    assert "REQUIRE_DEVTOOLS_SOURCE_AND_TEST" in codes(f=files()[:1])
    assert "REQUIRE_DEVTOOLS_SOURCE_AND_TEST" in codes(f=files()[1:])


def test_stale_or_self_approval_never_counts():
    assert "INDEPENDENT_GITHUB_APPROVAL_ON_EXACT_HEAD_REQUIRED" in codes(r=reviews(sha="e" * 40))
    assert "INDEPENDENT_GITHUB_APPROVAL_ON_EXACT_HEAD_REQUIRED" in codes(r=reviews(reviewer="author"))
    assert "INDEPENDENT_GITHUB_APPROVAL_ON_EXACT_HEAD_REQUIRED" in codes(r=[])


def test_latest_review_status_supersedes_older_approval():
    later = reviews() + [{"user": {"login": "independent"}, "state": "CHANGES_REQUESTED",
                          "commit_id": HEAD, "submitted_at": "2026-10-19T09:00:00Z", "id": 101}]
    assert "INDEPENDENT_GITHUB_APPROVAL_ON_EXACT_HEAD_REQUIRED" in codes(r=later)


def test_unreviewable_binary_delete_rename_and_large_diff_fail_closed():
    changed = files()
    changed[0] = dict(changed[0], patch=None, status="removed", changes=400)
    reasons = codes(f=changed)
    assert any(x.startswith("UNREVIEWABLE_PATCH:") for x in reasons)
    assert any(x.startswith("NON_ADDITIVE_CHANGE:") for x in reasons)
    assert "DIFF_TOO_LARGE_FOR_AUTOMERGE" in reasons


def test_no_files_and_many_files_fail_closed():
    assert "CHANGED_FILES_OUTSIDE_1_TO_8" in codes(f=[])
    assert "CHANGED_FILES_OUTSIDE_1_TO_8" in codes(f=files() * 5)


def test_path_traversal_not_admitted_even_with_approved_review():
    changed = files() + [{"filename": "scripts/devtools/../risk.py", "status": "added", "patch": "@@", "changes": 3}]
    assert "INVALID_FILENAME" in codes(f=changed)


def test_docs_plus_source_plus_test_is_eligible():
    changed = files() + [{"filename": "docs/devtools/usage.md", "status": "added", "patch": "@@", "changes": 5}]
    assert codes(f=changed) == []
