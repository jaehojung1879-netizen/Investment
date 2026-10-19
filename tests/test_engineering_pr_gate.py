"""Synthetic-only unit tests. No API calls, experiments or actual merge actions."""
from __future__ import annotations

import copy
import inspect
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

@pytest.mark.parametrize("name", [G.AI_AUDIT_NAME, G.NAME])
def test_gate_check_name_claimed_by_github_actions_blocks_even_with_real_audit(name):
    # A PR workflow (or devtools test code running with a write token) can post
    # a check named like the auditor's. A Ruleset set to "any source" would
    # accept it, so its presence blocks rather than being silently skipped.
    c = checks() + [{"name": name, "app": {"id": G.GITHUB_ACTIONS_APP_ID}, "head_sha": HEAD,
                     "status": "completed", "conclusion": "success", "id": 50,
                     "external_id": G.audit_external_id(42, HEAD),
                     "output": {"title": G.AI_AUDIT_TITLE},
                     "details_url": "https://forged.example"}]
    # Eligibility is App-signed too, so a GitHub Actions "eligibility" check is
    # exactly the forgery a workflow-editing PR would post.
    assert f"GATE_CHECK_CLAIMED_BY_UNPINNED_APP:{name}" in codes(c=c)


def test_pytest_name_from_another_app_blocks():
    c = checks() + [{"name": "pytest", "app": {"id": 31337}, "head_sha": HEAD,
                     "status": "completed", "conclusion": "success", "id": 51}]
    assert "CHECK_NAME_CLAIMED_BY_NON_ACTIONS_APP:pytest" in codes(c=c)


def test_earlier_app_signed_eligibility_is_not_a_forgery_signal():
    c = checks() + [{"name": G.NAME, "app": {"id": AUDITOR_ID}, "head_sha": HEAD,
                     "status": "completed", "conclusion": "failure", "id": 52}]
    assert codes(c=c) == []


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

    def __init__(self, *, fail_on=None, mutate_pr=None, check_runs=None, pr_fields=None, shared=None):
        self.posts = []
        self.fail_on = fail_on
        self.mutate_pr = mutate_pr
        self.check_runs = checks() if check_runs is None else check_runs
        self.pr_fields = pr_fields or {}
        self.shared = shared or []
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
            record.update(self.pr_fields)
            if self.mutate_pr and self.pr_reads > 1:
                record.update(self.mutate_pr)
            return record
        if "/pulls/42/files" in endpoint:
            return files()
        if "/check-runs" in endpoint:
            return {"total_count": len(self.check_runs), "check_runs": self.check_runs}
        if "/actions/runs" in endpoint:
            return {"total_count": 1, "workflow_runs": runs()}
        if "/commits/" + HEAD + "/pulls" in endpoint:
            return head_prs() + self.shared
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
    monkeypatch.setenv("GITHUB_TOKEN", "synthetic")
    monkeypatch.setenv("GITHUB_REPOSITORY", REPO)
    monkeypatch.setattr(G, "api", fake)
    monkeypatch.setattr(G, "TRUSTED_AI_AUDITOR_APP_ID", AUDITOR_ID)
    monkeypatch.setattr(G.eligibility_reasons, "__kwdefaults__",
                        dict(G.eligibility_reasons.__kwdefaults__, trusted_app_id=AUDITOR_ID))


def test_main_end_to_end_posts_exact_head_check_without_merge(monkeypatch, tmp_path):
    fake = FakeGitHub()
    _run_main(monkeypatch, tmp_path, fake)
    assert G.main(["--pr", "42", "--mode", "final"]) == 0
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
    assert G.main(["--pr", "42", "--mode", "final"]) == 0
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
    G.main(["--pr", "42", "--mode", "final"])
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
        G.main(["--pr", "42", "--mode", "final"])
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
        if grants:
            offenders.append(f"{path.name}: {grants.group(0).strip()}")
    assert offenders == []


def test_gate_is_not_an_actions_workflow_of_this_repository():
    # An Actions-posted eligibility check is forgeable by any PR that edits a
    # workflow, and the sealed research census freezes `.github/workflows`.
    # The auditor App runs this script from trusted main instead.
    for path in sorted((ROOT / ".github/workflows").glob("*.y*ml")):
        assert "engineering_pr_gate" not in path.read_text(), path.name
        assert "engineering-pr-gate" not in path.name


def test_trigger_reader_sees_pull_request_in_both_forms():
    assert _triggers("on: [pull_request, push]\n") == {"pull_request", "push"}
    assert _triggers("on:\n  pull_request:\n  push:\n    branches: [main]\njobs:\n") == {
        "pull_request", "push"}


def test_script_is_stdlib_only_and_runs_without_repository_imports():
    # The auditor runner fetches this single file from trusted main and runs bare python3.
    imports = re.findall(r"^(?:from|import) ([a-z_.]+)", inspect.getsource(G), re.M)
    assert set(imports) <= {"__future__", "argparse", "json", "os", "re", "sys", "urllib.request"}
    out = subprocess.run([sys.executable, "-I", "-c",
                          "import runpy; runpy.run_path(%r)" % str(ROOT / "scripts/engineering_pr_gate.py")],
                         capture_output=True, text=True, env={"PATH": ""})
    assert "ModuleNotFoundError" not in out.stderr


@pytest.mark.parametrize("argv", [[], ["--pr", "0", "--mode", "final"], ["--pr", "-1", "--mode", "final"],
                                  ["--pr", "x", "--mode", "final"], ["--pr", "42"], ["--pr", "42", "--mode", "merge"]])
def test_main_requires_a_positive_pr_number(monkeypatch, argv):
    monkeypatch.setattr(G, "api", lambda *_: pytest.fail("no API call before the PR is known"))
    with pytest.raises((SystemExit, ValueError)):
        G.main(argv)


# ---- Bootstrap order: preflight -> independent review -> final ----------------
# Requiring the audit's success before the review could run made a first audit
# impossible. Preflight carries every guard except that one and can never post
# a green eligibility check; only final, after the App-signed audit, can.

AUDIT = 1  # index of the audit check in checks()


def no_audit():
    return [c for i, c in enumerate(checks()) if i != AUDIT]


def preflight(**kw):
    return G.preflight_reasons(pr(changed_files=len(kw.get("f", files()))), kw.get("f", files()),
                               kw.get("c", checks()), trusted_app_id=AUDITOR_ID, runs=runs(),
                               modes=modes_for(kw.get("f", files())), head_prs=head_prs())


def test_first_audit_absence_permits_review_start_but_never_merge_eligibility():
    assert preflight(c=no_audit()) == []
    assert "PINNED_APP_AI_AUDIT_ABSENT" in codes(c=no_audit())
    assert G.final_eligibility_reasons is G.eligibility_reasons


@pytest.mark.parametrize("mutation, final_reason", [
    ({"conclusion": "failure"}, "INDEPENDENT_AI_AUDIT_NOT_SUCCESSFUL"),
    ({"status": "in_progress", "conclusion": None}, "INDEPENDENT_AI_AUDIT_NOT_SUCCESSFUL"),
    ({"external_id": G.audit_external_id(43, HEAD)}, "INDEPENDENT_AI_AUDIT_PR_OR_SHA_MISMATCH"),
    ({"external_id": G.audit_external_id(42, "0" * 40)}, "INDEPENDENT_AI_AUDIT_PR_OR_SHA_MISMATCH"),
])
def test_bad_audit_is_irrelevant_to_preflight_and_fatal_to_final(mutation, final_reason):
    c = checks()
    c[AUDIT].update(mutation)
    assert preflight(c=c) == []
    assert final_reason in codes(c=c)


def test_audit_from_wrong_app_blocks_preflight_too():
    c = checks()
    c[AUDIT]["app"] = {"id": 111}
    assert "GATE_CHECK_CLAIMED_BY_UNPINNED_APP:" + G.AI_AUDIT_NAME in preflight(c=c)


@pytest.mark.parametrize("path", ["pipeline/kr_market_risk_model.py", ".github/workflows/tests.yml",
                                  "scripts/engineering_pr_gate.py", "AGENTS.md"])
def test_blocked_paths_fail_preflight_so_no_review_is_spent(path):
    f = files() + [{"filename": path, "status": "modified", "patch": "@@", "changes": 1}]
    assert any(r.startswith("PATH_REQUIRES_OWNER_APPROVAL") for r in preflight(f=f))


def test_preflight_has_every_final_guard_except_the_audit_itself():
    # Whatever final refuses for a reason other than the audit, preflight refuses too.
    cases = [dict(p=pr(labels=[])), dict(p=pr(draft=True)), dict(r=[]), dict(h=head_prs() + [
        {"number": 43, "state": "open", "head": {"sha": HEAD}}]), dict(m=None)]
    audit_codes = {"PINNED_APP_AI_AUDIT_ABSENT", "INDEPENDENT_AI_AUDIT_NOT_SUCCESSFUL",
                   "INDEPENDENT_AI_AUDIT_PR_OR_SHA_MISMATCH", "INDEPENDENT_AI_AUDIT_CONTRACT_NOT_CONFIRMED",
                   "INDEPENDENT_AI_AUDIT_REPORT_URL_ABSENT", "INDEPENDENT_AI_AUDITOR_NOT_CONFIGURED",
                   "GITHUB_ACTIONS_IS_NOT_AN_INDEPENDENT_AI_AUDITOR"}
    for case in cases:
        final = codes(**case)
        p_ = case.get("p", pr())
        f_ = files()
        pre = G.preflight_reasons(dict(p_, changed_files=len(f_)), f_, checks(), trusted_app_id=AUDITOR_ID,
                                  runs=case.get("r", runs()), modes=case.get("m", modes_for(f_)),
                                  head_prs=case.get("h", head_prs()))
        assert set(final) - audit_codes == set(pre), case


def test_post_check_refuses_a_success_outside_final():
    with pytest.raises(AssertionError, match="ONLY_FINAL"):
        G.post_check("/repos/x", "t", 42, HEAD, [])


def test_main_preflight_without_audit_posts_nothing_and_exits_zero(monkeypatch, tmp_path):
    fake = FakeGitHub(check_runs=no_audit())
    _run_main(monkeypatch, tmp_path, fake)
    assert G.main(["--pr", "42", "--mode", "preflight"]) == 0
    assert fake.posts == []  # no green eligibility exists before the audit


def test_main_final_without_audit_posts_failure(monkeypatch, tmp_path):
    fake = FakeGitHub(check_runs=no_audit())
    _run_main(monkeypatch, tmp_path, fake)
    assert G.main(["--pr", "42", "--mode", "final"]) == 0
    body = fake.posts[-1][1]
    assert body["conclusion"] == "failure" and "PINNED_APP_AI_AUDIT_ABSENT" in body["output"]["summary"]


@pytest.mark.parametrize("change", [
    dict(pr_fields={"labels": []}),                                            # opt-in label removed
    dict(shared=[{"number": 43, "state": "open", "head": {"sha": HEAD}}]),     # head newly shared
    dict(pr_fields={"draft": True}),                                           # back to Draft
])
def test_stale_success_is_overwritten_by_the_next_preflight_after_metadata_change(monkeypatch, tmp_path, change):
    # Same SHA, so GitHub keeps the earlier green check attached to it: the
    # runner's next poll must replace it with a failure.
    first = FakeGitHub()
    _run_main(monkeypatch, tmp_path, first)
    assert G.main(["--pr", "42", "--mode", "final"]) == 0
    assert first.posts[-1][1]["conclusion"] == "success"
    later = FakeGitHub(**change)
    _run_main(monkeypatch, tmp_path, later)
    assert G.main(["--pr", "42", "--mode", "preflight"]) == 3
    endpoint, body = later.posts[-1]
    assert body["conclusion"] == "failure" and body["head_sha"] == HEAD


def test_final_on_a_new_head_cannot_reuse_the_old_heads_audit(monkeypatch, tmp_path):
    new_head = "a" * 40
    old = checks()
    stale = [dict(c, head_sha=new_head) for c in old]  # the API returns the new head's checks
    stale[AUDIT]["external_id"] = G.audit_external_id(42, HEAD)  # audit was for the old head
    fake = FakeGitHub(check_runs=stale, pr_fields={"head": {"sha": new_head, "repo": {"full_name": REPO}}})
    _run_main(monkeypatch, tmp_path, fake)
    monkeypatch.setattr(G, "get_file_modes", lambda *_: modes_for(files()))
    monkeypatch.setattr(G, "get_head_workflow_runs", lambda *_: [dict(runs()[0], head_sha=new_head)])
    fake_prs = [{"number": 42, "state": "open", "head": {"sha": new_head}}]
    original = fake.__call__

    def routed(method, endpoint, token, body=None):
        if endpoint.endswith(f"/commits/{new_head}/pulls?per_page=100&page=1"):
            return fake_prs
        return original(method, endpoint, token, body)
    monkeypatch.setattr(G, "api", routed)
    assert G.main(["--pr", "42", "--mode", "final"]) == 0
    body = fake.posts[-1][1]
    assert body["head_sha"] == new_head and body["conclusion"] == "failure"
    assert "INDEPENDENT_AI_AUDIT_PR_OR_SHA_MISMATCH" in body["output"]["summary"]
