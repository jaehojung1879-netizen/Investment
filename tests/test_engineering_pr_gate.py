"""Synthetic-only unit tests. No API calls, experiments or actual merge actions."""
from __future__ import annotations

import copy

import pytest

from scripts import engineering_pr_gate as G

HEAD = "f" * 40
AUDITOR_ID = 900123  # Fake external GitHub App identity, used ONLY in tests.


def pr(**overrides):
    record = {
        "number": 42,
        "state": "open",
        "draft": False,
        "base": {"ref": "main", "repo": {"full_name": "example/Investment"}},
        "head": {"sha": HEAD, "repo": {"full_name": "example/Investment"}},
        "user": {"login": "author"},
        "labels": [{"name": G.LABEL}],
    }
    record.update(overrides)
    return record


def files():
    return [
        {"filename": "scripts/devtools/report.py", "status": "added", "patch": "@@ +print(1)", "changes": 10},
        {"filename": "tests/test_devtools_report.py", "status": "added", "patch": "@@ +assert", "changes": 20},
    ]


def checks():
    return [
        {"name": "pytest", "app": {"id": G.GITHUB_ACTIONS_APP_ID},
         "head_sha": HEAD, "status": "completed", "conclusion": "success",
         "started_at": "2026-10-19T10:00:00Z", "id": 1},
        {"name": G.AI_AUDIT_NAME, "app": {"id": AUDITOR_ID},
         "head_sha": HEAD, "status": "completed", "conclusion": "success",
         "started_at": "2026-10-19T10:01:00Z", "id": 2,
         "external_id": G.audit_external_id(42, HEAD),
         "output": {"title": G.AI_AUDIT_TITLE},
         "details_url": "https://audit.example.org/pr/42/sha/" + HEAD},
    ]


def codes(p=None, f=None, c=None, auditor=AUDITOR_ID):
    return G.eligibility_reasons(
        pr() if p is None else p,
        files() if f is None else f,
        checks() if c is None else c,
        trusted_app_id=auditor,
    )


def test_only_narrow_devtools_with_independent_app_audit_and_ci_can_pass():
    assert codes() == []


def test_production_policy_remains_disarmed_even_with_other_checks():
    assert G.TRUSTED_AI_AUDITOR_APP_ID is None
    assert "INDEPENDENT_AI_AUDITOR_NOT_CONFIGURED" in codes(auditor=None)


@pytest.mark.parametrize("changes, reason", [
    ({"draft": True}, "PR_MUST_BE_OPEN_AND_READY_NOT_DRAFT"),
    ({"state": "closed"}, "PR_MUST_BE_OPEN_AND_READY_NOT_DRAFT"),
    ({"base": {"ref": "release", "repo": {"full_name": "example/Investment"}}}, "BASE_MUST_BE_MAIN"),
    ({"head": {"sha": HEAD, "repo": {"full_name": "fork/Investment"}}}, "CROSS_REPOSITORY_PR_NOT_ADMITTED"),
    ({"labels": []}, "ENGINEERING_OPT_IN_LABEL_ABSENT"),
])
def test_pr_gate_refuses_unsafe_metadata(changes, reason):
    assert reason in codes(p=pr(**changes))


@pytest.mark.parametrize("path", [
    "pipeline/kr_market_risk_model.py",
    ".github/workflows/tests.yml",
    "docs/research-program/03-studies-abc-ko.md",
    "AGENTS.md",
    "scripts/collect_krx_daily_prices.py",
    "scripts/engineering_pr_gate.py",
    "tests/test_alpha_model.py",
])
def test_research_collectors_live_code_rules_and_own_gate_excluded(path):
    changed = files() + [{"filename": path, "status": "modified", "patch": "@@", "changes": 5}]
    assert any(x.startswith("PATH_REQUIRES_OWNER_APPROVAL") for x in codes(f=changed))


def test_both_source_and_synthetic_test_required():
    assert "REQUIRE_DEVTOOLS_SOURCE_AND_TEST" in codes(f=files()[:1])
    assert "REQUIRE_DEVTOOLS_SOURCE_AND_TEST" in codes(f=files()[1:])


def test_unreviewable_binary_deletion_rename_and_large_diff_fail():
    changed = files()
    changed[0] = dict(changed[0], patch=None, status="removed", changes=400)
    reasons = codes(f=changed)
    assert any(x.startswith("UNREVIEWABLE_PATCH:") for x in reasons)
    assert any(x.startswith("NON_ADDITIVE_CHANGE:") for x in reasons)
    assert "DIFF_TOO_LARGE_FOR_AUTOMERGE" in reasons


def test_file_count_path_traversal_and_docs_allowlist():
    assert "CHANGED_FILES_OUTSIDE_1_TO_8" in codes(f=[])
    assert "CHANGED_FILES_OUTSIDE_1_TO_8" in codes(f=files() * 5)
    bad = files() + [{"filename": "scripts/devtools/../risk.py", "status": "added", "patch": "@@", "changes": 3}]
    assert "INVALID_FILENAME" in codes(f=bad)
    good = files() + [{"filename": "docs/devtools/usage.md", "status": "added", "patch": "@@", "changes": 5}]
    assert codes(f=good) == []


def test_invalid_pr_sha_fails_closed():
    damaged = pr(head={"sha": "short", "repo": {"full_name": "example/Investment"}})
    assert "INVALID_PR_OR_HEAD_SHA" in codes(p=damaged)


def test_no_ai_app_cannot_be_replaced_by_plain_gh_actions():
    assert "GITHUB_ACTIONS_IS_NOT_AN_INDEPENDENT_AI_AUDITOR" in codes(
        auditor=G.GITHUB_ACTIONS_APP_ID
    )


@pytest.mark.parametrize("mutation, expected", [
    ({"app": {"id": 111}}, "PINNED_APP_AI_AUDIT_ABSENT"),
    ({"status": "in_progress"}, "INDEPENDENT_AI_AUDIT_NOT_SUCCESSFUL"),
    ({"conclusion": "failure"}, "INDEPENDENT_AI_AUDIT_NOT_SUCCESSFUL"),
    ({"external_id": G.audit_external_id(43, HEAD)}, "INDEPENDENT_AI_AUDIT_PR_OR_SHA_MISMATCH"),
    ({"external_id": G.audit_external_id(42, "0" * 40)}, "INDEPENDENT_AI_AUDIT_PR_OR_SHA_MISMATCH"),
    ({"output": {"title": "review requested"}}, "INDEPENDENT_AI_AUDIT_CONTRACT_NOT_CONFIRMED"),
    ({"details_url": "http://unsafe.example"}, "INDEPENDENT_AI_AUDIT_REPORT_URL_ABSENT"),
])
def test_independent_audit_rejects_spoofed_stale_incomplete_evidence(mutation, expected):
    fake = checks()
    fake[1].update(mutation)
    assert expected in codes(c=fake)


def test_plain_text_or_self_authored_review_cannot_pass():
    fake = checks()[:1]  # PR comments and author reviews are not accepted inputs.
    assert "PINNED_APP_AI_AUDIT_ABSENT" in codes(c=fake)


def test_latest_reviewer_result_wins_over_old_success():
    c = checks()
    bad = copy.deepcopy(c[1])
    bad.update({"id": 3, "started_at": "2026-10-19T10:05:00Z", "conclusion": "failure"})
    c.append(bad)
    assert "INDEPENDENT_AI_AUDIT_NOT_SUCCESSFUL" in codes(c=c)


def test_latest_pytest_failure_overrides_old_success():
    c = checks()
    c.append({"name": "pytest", "app": {"id": G.GITHUB_ACTIONS_APP_ID},
              "status": "completed", "conclusion": "failure",
              "started_at": "2026-10-19T10:06:00Z", "id": 4})
    assert "CURRENT_HEAD_PYTEST_NOT_SUCCESSFUL" in codes(c=c)


def test_no_pytest_or_incomplete_pytest_refused():
    assert "CURRENT_HEAD_PYTEST_ABSENT" in codes(c=checks()[1:])
    c = checks()
    c[0]["status"] = "in_progress"
    assert "CURRENT_HEAD_PYTEST_NOT_SUCCESSFUL" in codes(c=c)


def test_gitub_event_recovery_exactly_one_pr():
    assert G.pr_number_from_event({"pull_request": {"number": 42}}) == 42
    assert G.pr_number_from_event({"workflow_run": {"pull_requests": [{"number": 42}]}}) == 42
    assert G.pr_number_from_event({"check_run": {"pull_requests": [{"number": 42}]}}) == 42
    with pytest.raises(ValueError, match="UNRESOLVED_OR_AMBIGUOUS"):
        G.pr_number_from_event({"workflow_run": {"pull_requests": []}})
    with pytest.raises(ValueError, match="UNRESOLVED_OR_AMBIGUOUS"):
        G.pr_number_from_event({"check_run": {"pull_requests": [{"number": 42}, {"number": 43}]}})


def test_paginated_or_wrong_sha_checks_fail_closed(monkeypatch):
    monkeypatch.setattr(G, "api", lambda *_: {"total_count": 101, "check_runs": [{}]})
    with pytest.raises(ValueError, match="INCOMPLETE"):
        G.get_head_checks("/repos/example/Investment", HEAD, "token")
    monkeypatch.setattr(
        G, "api", lambda *_: {"total_count": 1, "check_runs": [{"head_sha": "0" * 40}]}
    )
    with pytest.raises(ValueError, match="HEAD_SHA_MISMATCH"):
        G.get_head_checks("/repos/example/Investment", HEAD, "token")


def test_queued_reviewer_check_blocks_older_pass():
    c = checks()
    c.append({"name": G.AI_AUDIT_NAME, "app": {"id": AUDITOR_ID},
              "head_sha": HEAD, "status": "queued", "conclusion": None,
              "started_at": None, "id": 9})
    assert "INDEPENDENT_AI_AUDIT_NOT_SUCCESSFUL" in codes(c=c)


def test_queued_pytest_check_blocks_older_pass():
    c = checks()
    c.append({"name": "pytest", "app": {"id": G.GITHUB_ACTIONS_APP_ID},
              "head_sha": HEAD, "status": "queued", "conclusion": None,
              "started_at": None, "id": 10})
    assert "CURRENT_HEAD_PYTEST_NOT_SUCCESSFUL" in codes(c=c)


def test_missing_diff_change_count_blocks_eligibility():
    f = files()
    f[0].pop("changes")
    assert "UNVERIFIABLE_CHANGE_COUNT" in codes(f=f)


def test_missing_api_count_blocks_eligibility(monkeypatch):
    monkeypatch.setattr(G, "api", lambda *_: {"check_runs": [{"head_sha": HEAD}]})
    with pytest.raises(ValueError, match="INCOMPLETE"):
        G.get_head_checks("/repos/example/Investment", HEAD, "token")
