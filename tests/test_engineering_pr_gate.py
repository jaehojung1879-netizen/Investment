"""Synthetic-only unit tests. No API calls, experiments or actual merge actions."""
from __future__ import annotations

import copy
import inspect
import json
import pathlib
import subprocess
import sys

import re

import pytest

from scripts import engineering_pr_gate as G

HEAD = "f" * 40
AUDITOR_ID = 900123  # Fake external GitHub App identity, used ONLY in tests.
TESTS_SUITE = 7001
REPO = "example/Investment"
ROOT = pathlib.Path(__file__).resolve().parents[1]
GATE_WORKFLOW = ROOT / ".github/workflows/engineering-pr-gate.yml"


def pr(**overrides):
    record = {
        "number": 42,
        "state": "open",
        "draft": False,
        "base": {"ref": "main", "repo": {"full_name": "example/Investment"}},
        "head": {"sha": HEAD, "repo": {"full_name": "example/Investment"}},
        "user": {"login": "author"},
        "labels": [{"name": G.LABEL}],
        "changed_files": 2,
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
         "started_at": "2026-10-19T10:00:00Z", "id": 1,
         "check_suite": {"id": TESTS_SUITE}},
        {"name": G.AI_AUDIT_NAME, "app": {"id": AUDITOR_ID},
         "head_sha": HEAD, "status": "completed", "conclusion": "success",
         "started_at": "2026-10-19T10:01:00Z", "id": 2,
         "external_id": G.audit_external_id(42, HEAD),
         "output": {"title": G.AI_AUDIT_TITLE},
         "details_url": "https://audit.example.org/pr/42/sha/" + HEAD},
    ]


def runs():
    return [{"id": 55, "check_suite_id": TESTS_SUITE, "path": G.TESTS_WORKFLOW_PATH,
             "event": "pull_request", "head_sha": HEAD, "name": "Tests"}]


def modes_for(f):
    return {x["filename"]: "100644" for x in f if isinstance(x.get("filename"), str)}


def head_prs():
    return [{"number": 42, "state": "open", "head": {"sha": HEAD}}]


_UNSET = object()


def codes(p=None, f=None, c=None, auditor=AUDITOR_ID, r=_UNSET, m=_UNSET, h=_UNSET):
    f = files() if f is None else f
    p = pr(changed_files=len(f)) if p is None else p
    return G.eligibility_reasons(
        p, f,
        checks() if c is None else c,
        trusted_app_id=auditor,
        runs=runs() if r is _UNSET else r,
        modes=modes_for(f) if m is _UNSET else m,
        head_prs=head_prs() if h is _UNSET else h,
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
    ({"changed_files": 3}, "CHANGED_FILE_LIST_INCOMPLETE"),
    ({"changed_files": None}, "CHANGED_FILE_LIST_INCOMPLETE"),
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


def _ref(number, repo=REPO):
    return {"number": number, "base": {"repo": {"url": "https://api.github.com/repos/" + repo}}}


def test_gitub_event_recovery_exactly_one_pr():
    assert G.pr_number_from_event({"pull_request": {"number": 42}}, REPO) == 42
    assert G.pr_number_from_event({"workflow_run": {"pull_requests": [_ref(42)]}}, REPO) == 42
    assert G.pr_number_from_event({"check_run": {"pull_requests": [_ref(42)]}}, REPO) == 42
    with pytest.raises(ValueError, match="UNRESOLVED_OR_AMBIGUOUS"):
        G.pr_number_from_event({"workflow_run": {"pull_requests": []}}, REPO)
    with pytest.raises(ValueError, match="UNRESOLVED_OR_AMBIGUOUS"):
        G.pr_number_from_event({"check_run": {"pull_requests": [_ref(42), _ref(43)]}}, REPO)


def test_event_pr_number_from_another_repository_is_not_this_repos_pr():
    # GitHub lists PRs of other repositories sharing the head; their number 7
    # is an unrelated PR here.
    event = {"check_run": {"pull_requests": [_ref(7, "fork/Investment")]}}
    with pytest.raises(ValueError, match="UNRESOLVED_OR_AMBIGUOUS"):
        G.pr_number_from_event(event, REPO)
    mixed = {"check_run": {"pull_requests": [_ref(7, "fork/Investment"), _ref(42)]}}
    assert G.pr_number_from_event(mixed, REPO) == 42
    unattributed = {"workflow_run": {"pull_requests": [{"number": 42}]}}
    with pytest.raises(ValueError, match="UNRESOLVED_OR_AMBIGUOUS"):
        G.pr_number_from_event(unattributed, REPO)


def test_paginated_or_wrong_sha_checks_fail_closed(monkeypatch):
    monkeypatch.setattr(G, "api", lambda *_: {"total_count": 101, "check_runs": [{}]})
    with pytest.raises(ValueError, match="INCOMPLETE"):
        G.get_head_checks("/repos/example/Investment", HEAD, "token")
    monkeypatch.setattr(
        G, "api", lambda *_: {"total_count": 1, "check_runs": [{"head_sha": "0" * 40}]}
    )
    with pytest.raises(ValueError, match="HEAD_SHA_MISMATCH"):
        G.get_head_checks("/repos/example/Investment", HEAD, "token")


def test_check_runs_are_requested_unfiltered_and_fully_paginated(monkeypatch):
    seen = []

    def fake(method, endpoint, token, body=None):
        seen.append(endpoint)
        page = int(endpoint.rsplit("page=", 1)[1])
        batch = [{"head_sha": HEAD, "id": 100 * page + i} for i in range(100 if page == 1 else 20)]
        return {"total_count": 120, "check_runs": batch}

    monkeypatch.setattr(G, "api", fake)
    assert len(G.get_head_checks("/repos/example/Investment", HEAD, "token")) == 120
    # The endpoint defaults to filter=latest (by completed_at), which can hide
    # a queued re-run behind the older success it replaces.
    assert all("filter=all" in e for e in seen) and len(seen) == 2


def test_listing_that_changes_between_pages_fails_closed(monkeypatch):
    def fake(method, endpoint, token, body=None):
        page = int(endpoint.rsplit("page=", 1)[1])
        return {"total_count": 120 if page == 1 else 121,
                "check_runs": [{"head_sha": HEAD}] * (100 if page == 1 else 21)}

    monkeypatch.setattr(G, "api", fake)
    with pytest.raises(ValueError, match="CHANGED_DURING_PAGINATION"):
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


# ---- Independent audit (second reviewer) additions -------------------------

@pytest.mark.parametrize("name", [G.AI_AUDIT_NAME])
def test_audit_name_claimed_by_github_actions_blocks_even_with_real_audit(name):
    # A PR workflow (or devtools test code running with a write token) can post
    # a check named like the auditor's. A Ruleset set to "any source" would
    # accept it, so its presence blocks rather than being silently skipped.
    c = checks() + [{"name": name, "app": {"id": G.GITHUB_ACTIONS_APP_ID}, "head_sha": HEAD,
                     "status": "completed", "conclusion": "success", "id": 50,
                     "external_id": G.audit_external_id(42, HEAD),
                     "output": {"title": G.AI_AUDIT_TITLE},
                     "details_url": "https://forged.example"}]
    assert "AI_AUDIT_CHECK_CLAIMED_BY_UNPINNED_APP" in codes(c=c)


@pytest.mark.parametrize("name", [G.NAME, G.TEST_CHECK_NAME])
def test_eligibility_or_pytest_name_from_another_app_blocks(name):
    c = checks() + [{"name": name, "app": {"id": 31337}, "head_sha": HEAD,
                     "status": "completed", "conclusion": "success", "id": 51}]
    assert f"CHECK_NAME_CLAIMED_BY_NON_ACTIONS_APP:{name}" in codes(c=c)


def test_pytest_job_from_another_workflow_is_not_ci_evidence():
    # Any workflow can define a job called `pytest`; only the Tests workflow's
    # run on this exact head for this PR counts.
    for bad in [
        [dict(runs()[0], path=".github/workflows/probes.yml")],
        [dict(runs()[0], event="push")],
        [dict(runs()[0], head_sha="0" * 40)],
        [dict(runs()[0], check_suite_id=1)],
        [],
        None,
    ]:
        assert "PYTEST_CHECK_NOT_FROM_TESTS_WORKFLOW" in codes(r=bad), bad


def test_later_green_pytest_from_untrusted_suite_cannot_mask_tests_failure():
    c = checks()
    c[0]["conclusion"] = "failure"
    c.append({"name": "pytest", "app": {"id": G.GITHUB_ACTIONS_APP_ID}, "head_sha": HEAD,
              "status": "completed", "conclusion": "success", "id": 60,
              "check_suite": {"id": 9999}})
    assert "PYTEST_CHECK_NOT_FROM_TESTS_WORKFLOW" in codes(c=c)


@pytest.mark.parametrize("mode", ["120000", "160000", None])
def test_symlink_submodule_or_unknown_mode_is_refused(mode):
    f = files()
    m = modes_for(f)
    if mode is None:
        m.pop(f[0]["filename"])
    else:
        m[f[0]["filename"]] = mode
    assert f"NON_REGULAR_FILE:{f[0]['filename']}" in codes(f=f, m=m)
    assert "FILE_MODES_UNVERIFIED" in codes(m=None)


def test_audit_for_another_pr_on_same_sha_cannot_be_reused():
    c = checks()
    c[1]["external_id"] = G.audit_external_id(43, HEAD)
    assert "INDEPENDENT_AI_AUDIT_PR_OR_SHA_MISMATCH" in codes(c=c)


def test_second_open_pr_with_same_head_blocks_eligibility():
    # Check runs belong to the SHA. A green eligibility computed for #42 would
    # also satisfy the required check of #43 (e.g. without the opt-in label).
    shared = head_prs() + [{"number": 43, "state": "open", "head": {"sha": HEAD}}]
    assert "HEAD_SHA_SHARED_WITH_ANOTHER_OPEN_PR" in codes(h=shared)
    assert "HEAD_SHA_PR_ASSOCIATION_UNVERIFIED" in codes(h=None)
    # A closed PR or a stacked PR that merely contains the commit is not shared.
    harmless = head_prs() + [{"number": 43, "state": "closed", "head": {"sha": HEAD}},
                             {"number": 44, "state": "open", "head": {"sha": "a" * 40}}]
    assert codes(h=harmless) == []


def test_old_sha_audit_and_old_sha_pytest_are_rejected_by_api_layer(monkeypatch):
    stale = [dict(x, head_sha="0" * 40) for x in checks()]
    monkeypatch.setattr(G, "api", lambda *_: {"total_count": 2, "check_runs": stale})
    with pytest.raises(ValueError, match="HEAD_SHA_MISMATCH"):
        G.get_head_checks("/repos/example/Investment", HEAD, "token")


def test_file_modes_walk_trees_and_refuse_truncation(monkeypatch):
    trees = {
        "root": [{"path": "scripts", "type": "tree", "sha": "t-s"},
                 {"path": "tests", "type": "tree", "sha": "t-t"}],
        "t-s": [{"path": "devtools", "type": "tree", "sha": "t-d"}],
        "t-d": [{"path": "report.py", "type": "blob", "mode": "120000"}],
        "t-t": [{"path": "test_devtools_report.py", "type": "blob", "mode": "100644"}],
    }

    def fake(method, endpoint, token, body=None):
        if "/git/commits/" in endpoint:
            return {"sha": HEAD, "tree": {"sha": "root"}}
        return {"truncated": False, "tree": trees[endpoint.rsplit("/", 1)[1]]}

    monkeypatch.setattr(G, "api", fake)
    got = G.get_file_modes("/repos/x", HEAD, [f["filename"] for f in files()], "t")
    assert got == {"scripts/devtools/report.py": "120000",
                   "tests/test_devtools_report.py": "100644"}
    monkeypatch.setattr(G, "api", lambda *_: (
        {"sha": HEAD, "tree": {"sha": "root"}} if "/git/commits/" in _[1]
        else {"truncated": True, "tree": []}))
    with pytest.raises(ValueError, match="GIT_TREE_INCOMPLETE"):
        G.get_file_modes("/repos/x", HEAD, ["a/b.py"], "t")


class FakeGitHub:
    """Synthetic API for main(): records every POST; no network."""

    def __init__(self, *, fail_on=None, mutate_pr=None):
        self.posts = []
        self.fail_on = fail_on
        self.mutate_pr = mutate_pr
        self.pr_reads = 0

    def __call__(self, method, endpoint, token, body=None):
        if self.fail_on and self.fail_on in endpoint:
            raise OSError("synthetic outage")
        if method == "POST":
            self.posts.append((endpoint, body))
            return {"id": len(self.posts)}
        if endpoint.endswith("/pulls/42"):
            self.pr_reads += 1
            record = pr(base={"ref": "main", "repo": {"full_name": REPO}},
                        head={"sha": HEAD, "repo": {"full_name": REPO}})
            if self.mutate_pr and self.pr_reads > 1:
                record.update(self.mutate_pr)
            return record
        if "/pulls/42/files" in endpoint:
            return files()
        if "/check-runs" in endpoint:
            return {"total_count": 2, "check_runs": checks()}
        if "/actions/runs" in endpoint:
            return {"total_count": 1, "workflow_runs": runs()}
        if "/commits/" + HEAD + "/pulls" in endpoint:
            return head_prs()
        if "/git/commits/" in endpoint:
            return {"sha": HEAD, "tree": {"sha": "root"}}
        if "/git/trees/" in endpoint:
            key = endpoint.rsplit("/", 1)[1]
            return {"truncated": False, "tree": {
                "root": [{"path": "scripts", "type": "tree", "sha": "s"},
                         {"path": "tests", "type": "tree", "sha": "t"}],
                "s": [{"path": "devtools", "type": "tree", "sha": "d"}],
                "d": [{"path": "report.py", "type": "blob", "mode": "100644"}],
                "t": [{"path": "test_devtools_report.py", "type": "blob", "mode": "100644"}],
            }[key]}
        raise AssertionError("unexpected endpoint " + endpoint)


def _run_main(monkeypatch, tmp_path, fake):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"number": 42}}))
    monkeypatch.setenv("GITHUB_TOKEN", "synthetic")
    monkeypatch.setenv("GITHUB_REPOSITORY", REPO)
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setattr(G, "api", fake)
    monkeypatch.setattr(G, "TRUSTED_AI_AUDITOR_APP_ID", AUDITOR_ID)
    monkeypatch.setattr(G.eligibility_reasons, "__kwdefaults__",
                        dict(G.eligibility_reasons.__kwdefaults__, trusted_app_id=AUDITOR_ID))


def test_main_end_to_end_posts_exact_head_check_without_merge(monkeypatch, tmp_path):
    fake = FakeGitHub()
    _run_main(monkeypatch, tmp_path, fake)
    assert G.main() == 0
    assert len(fake.posts) == 1
    endpoint, body = fake.posts[0]
    assert endpoint == f"/repos/{REPO}/check-runs"
    assert body["head_sha"] == HEAD and body["conclusion"] == "success"
    assert body["external_id"] == f"investment-eligibility:v1:pr:42:sha:{HEAD}"


def test_production_main_stays_blocked_with_disarmed_auditor(monkeypatch, tmp_path):
    fake = FakeGitHub()
    _run_main(monkeypatch, tmp_path, fake)
    monkeypatch.setattr(G.eligibility_reasons, "__kwdefaults__",
                        dict(G.eligibility_reasons.__kwdefaults__, trusted_app_id=None))
    assert G.main() == 0
    body = fake.posts[0][1]
    assert body["conclusion"] == "failure"
    assert "INDEPENDENT_AI_AUDITOR_NOT_CONFIGURED" in body["output"]["summary"]
    assert "\\n" not in body["output"]["summary"]  # real line breaks, not literal "\n"


@pytest.mark.parametrize("mutation", [
    {"labels": []}, {"draft": True}, {"head": {"sha": "a" * 40, "repo": {"full_name": REPO}}},
    {"changed_files": 3},
])
def test_pr_changed_during_assessment_posts_failure(monkeypatch, tmp_path, mutation):
    fake = FakeGitHub(mutate_pr=mutation)
    _run_main(monkeypatch, tmp_path, fake)
    G.main()
    body = fake.posts[-1][1]
    assert body["conclusion"] == "failure" and body["head_sha"] == HEAD
    assert "PR_CHANGED_DURING_ASSESSMENT" in body["output"]["summary"]


@pytest.mark.parametrize("outage", ["/check-runs?", "/actions/runs", "/git/trees/", "/pulls/42/files"])
def test_api_error_overwrites_an_earlier_green_with_failure(monkeypatch, tmp_path, outage):
    # Without this, a crash leaves the previous evaluation's success as the
    # latest eligibility check on the SHA.
    fake = FakeGitHub(fail_on=outage)
    _run_main(monkeypatch, tmp_path, fake)
    with pytest.raises(OSError):
        G.main()
    endpoint, body = fake.posts[-1]
    assert body["conclusion"] == "failure" and body["head_sha"] == HEAD
    assert "GATE_ERROR_FAILED_CLOSED:OSError" in body["output"]["summary"]


def test_gate_source_contains_no_merge_approval_or_write_to_pr():
    src = inspect.getsource(G)
    for forbidden in ("/merge", "auto_merge", "enablePullRequestAutoMerge",
                      '"PUT"', '"PATCH"', '"DELETE"', "/reviews", "/comments"):
        assert forbidden not in src
    assert src.count('api("POST"') == 1  # only the check-run post


# ---- Workflow trust boundary ------------------------------------------------
# Read as text: pyyaml is not a dependency of the Tests workflow.

PR_CODE_TRIGGERS = ("pull_request", "pull_request_review", "pull_request_review_comment")


def _triggers(text):
    """Event names under the top-level `on:` block (or an inline `on:` list)."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^(on|\"on\"|'on'|true):", line):
            inline = line.split(":", 1)[1].strip()
            if inline:
                return set(re.findall(r"[a-z_]+", inline))
            found = set()
            for nxt in lines[i + 1:]:
                if nxt and not nxt.startswith((" ", "#")):
                    break
                m = re.match(r"^  ([a-z_]+):", nxt)
                if m:
                    found.add(m.group(1))
            return found
    raise AssertionError("no on: block")


def _top_permissions(text):
    lines = text.splitlines()
    i = next(i for i, x in enumerate(lines) if x.startswith("permissions:"))
    perms = {}
    for nxt in lines[i + 1:]:
        m = re.match(r"^  ([a-z-]+):\s*([a-z]+)", nxt)
        if not m:
            break
        perms[m.group(1)] = m.group(2)
    return perms


def test_gate_workflow_uses_only_default_branch_triggers():
    triggers = _triggers(GATE_WORKFLOW.read_text())
    assert triggers == {"pull_request_target", "workflow_run", "check_run"}
    assert not triggers & set(PR_CODE_TRIGGERS)


def test_gate_workflow_least_privilege_pinned_and_never_checks_out_pr():
    text = GATE_WORKFLOW.read_text()
    assert _top_permissions(text) == {"actions": "read", "checks": "write",
                                      "contents": "read", "pull-requests": "read"}
    # Exactly one job-free permissions block.
    assert len(re.findall(r"^\s*permissions:", text, re.M)) == 1
    uses = re.findall(r"^\s*(?:- )?uses:\s*(\S+)", text, re.M)
    assert len(uses) == 1 and re.fullmatch(r"actions/checkout@[0-9a-f]{40}", uses[0])
    assert re.search(r"^\s+ref: main$", text, re.M)
    assert re.search(r"^\s+persist-credentials: false$", text, re.M)
    for forbidden in ("github.event.pull_request.head", "refs/pull", "head_ref",
                      "pip install", "setup-python"):
        assert forbidden not in text


def test_gate_concurrency_is_one_queue_per_pr_for_every_trigger():
    text = GATE_WORKFLOW.read_text()
    group = text[text.index("concurrency:"):text.index("cancel-in-progress")]
    for expr in ("github.event.pull_request.number",
                 "github.event.workflow_run.pull_requests[0].number",
                 "github.event.check_run.pull_requests[0].number"):
        assert expr in group
    assert "check_run.id" not in group and "workflow_run.id" not in group


def test_no_pr_executing_workflow_can_forge_check_runs_or_statuses():
    # Devtools tests are allowlisted and RUN in the Tests workflow. If any
    # workflow running PR code held checks/statuses write, that code could post
    # a green `Investment Auto-merge eligibility` or `pytest` as GitHub Actions.
    offenders = []
    for path in sorted((ROOT / ".github/workflows").glob("*.y*ml")):
        text = path.read_text()
        grants = re.search(r"^\s*(checks|statuses):\s*write|write-all", text, re.M)
        runs_pr_code = bool(_triggers(text) & set(PR_CODE_TRIGGERS))
        if runs_pr_code and not re.search(r"^permissions:", text, re.M):
            offenders.append(f"{path.name}: no top-level permissions (repository default applies)")
        if grants and (runs_pr_code or path != GATE_WORKFLOW):
            offenders.append(f"{path.name}: {grants.group(0).strip()}")
    assert offenders == []


def test_trigger_reader_sees_pull_request_in_both_forms():
    assert _triggers("on: [pull_request, push]\n") == {"pull_request", "push"}
    assert _triggers("on:\n  pull_request:\n  push:\n    branches: [main]\njobs:\n") == {
        "pull_request", "push"}


def test_script_is_stdlib_only_and_runs_without_repository_imports():
    # The workflow sparse-checks-out this single file and runs bare python3.
    imports = re.findall(r"^(?:from|import) ([a-z_.]+)", inspect.getsource(G), re.M)
    assert set(imports) <= {"__future__", "json", "os", "re", "sys", "urllib.request"}
    out = subprocess.run([sys.executable, "-I", "-c",
                          "import runpy; runpy.run_path(%r)" % str(ROOT / "scripts/engineering_pr_gate.py")],
                         capture_output=True, text=True, env={"PATH": ""})
    assert "ModuleNotFoundError" not in out.stderr
