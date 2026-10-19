"""Fail-closed engineering PR gate, designed for a trusted-main workflow.

This script never merges, approves, checks out, or executes pull-request code.
Native GitHub branch protection and independently produced AI audit evidence
are REQUIRED before allowing any unattended merge. The independent auditor
must be a separate pinned GitHub App, not an author-controlled PR comment.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request

NAME = "Investment Auto-merge eligibility"
AI_AUDIT_NAME = "Investment Independent AI Audit"
AI_AUDIT_TITLE = "INDEPENDENT_DIFF_AUDIT_PASSED"
LABEL = "auto-merge:engineering"
TEST_CHECK_NAME = "pytest"
# The only workflow whose `pytest` job is evidence. Any workflow can name a job
# `pytest`, so the check is bound to its check suite's workflow file.
TESTS_WORKFLOW_PATH = ".github/workflows/tests.yml"
GITHUB_ACTIONS_APP_ID = 15368
# Deliberately DISARMED. Pin the real externally authenticated review App ID
# only through a separately reviewed, owner-authorized policy change.
TRUSTED_AI_AUDITOR_APP_ID = None
MAX_FILES = 8
MAX_LINES = 350
ALLOW_SOURCE = re.compile(r"^scripts/devtools/[A-Za-z0-9_/-]+\.py$")
ALLOW_TEST = re.compile(r"^tests/test_devtools_[A-Za-z0-9_]+\.py$")
ALLOW_DOC = re.compile(r"^docs/devtools/[A-Za-z0-9_/-]+\.md$")
# Regular blobs only. A symlink (120000) at an allowlisted path can point at
# content outside the allowlist, and a submodule (160000) has no reviewable text.
REGULAR_FILE_MODES = {"100644", "100755"}


def audit_external_id(pr_number: int, sha: str) -> str:
    """An attester must bind its report to both PR identity and exact head."""
    return f"investment-ai-audit:v1:pr:{pr_number}:sha:{sha}"


def _latest(checks: list[dict], name: str, app_id: int) -> dict | None:
    matching = [
        c for c in checks
        if c.get("name") == name
        and (c.get("app") or {}).get("id") == app_id
    ]
    if not matching:
        return None
    # A queued replacement check may have started_at=None. Ordering by
    # started_at would incorrectly prefer an older SUCCESS over the new
    # pending check. GitHub check-run IDs identify creation order.
    # Unverifiable IDs must not resurrect an earlier passing check.
    if any(type(c.get("id")) is not int or c["id"] <= 0 for c in matching):
        return None
    return max(matching, key=lambda c: c["id"])


def audit_evidence_reasons(
    number: int, sha: str, checks: list[dict], trusted_app_id: int | None
) -> list[str]:
    """External GitHub App assertion; no human/self account or text fallback."""
    if not isinstance(trusted_app_id, int) or trusted_app_id <= 0:
        return ["INDEPENDENT_AI_AUDITOR_NOT_CONFIGURED"]
    if trusted_app_id == GITHUB_ACTIONS_APP_ID:
        return ["GITHUB_ACTIONS_IS_NOT_AN_INDEPENDENT_AI_AUDITOR"]
    run = _latest(checks, AI_AUDIT_NAME, trusted_app_id)
    if run is None:
        return ["PINNED_APP_AI_AUDIT_ABSENT"]
    reasons = []
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        reasons.append("INDEPENDENT_AI_AUDIT_NOT_SUCCESSFUL")
    if run.get("external_id") != audit_external_id(number, sha):
        reasons.append("INDEPENDENT_AI_AUDIT_PR_OR_SHA_MISMATCH")
    if (run.get("output") or {}).get("title") != AI_AUDIT_TITLE:
        reasons.append("INDEPENDENT_AI_AUDIT_CONTRACT_NOT_CONFIRMED")
    if not isinstance(run.get("details_url"), str) or not run["details_url"].startswith("https://"):
        reasons.append("INDEPENDENT_AI_AUDIT_REPORT_URL_ABSENT")
    return reasons


def impersonation_reasons(checks: list[dict], trusted_app_id: int | None) -> list[str]:
    """A gate check name claimed by an unexpected App is a forgery signal.

    The selection below ignores such checks, but a Ruleset whose required check
    is configured with "any source" would not, so their presence blocks.
    """
    reasons = []
    for c in checks:
        app = (c.get("app") or {}).get("id")
        name = c.get("name")
        if name == AI_AUDIT_NAME and app != trusted_app_id:
            reasons.append("AI_AUDIT_CHECK_CLAIMED_BY_UNPINNED_APP")
        elif name in (NAME, TEST_CHECK_NAME) and app != GITHUB_ACTIONS_APP_ID:
            reasons.append(f"CHECK_NAME_CLAIMED_BY_NON_ACTIONS_APP:{name}")
    return sorted(set(reasons))


def ci_evidence_reasons(
    checks: list[dict], sha: str | None = None, runs: list[dict] | None = None
) -> list[str]:
    """The exact head must have a successful pytest from the Tests workflow.

    `runs` are the GitHub Actions workflow runs on the head SHA. Every Actions
    `pytest` check must belong to a Tests run triggered by `pull_request` on
    this SHA; a `pytest` job from any other workflow is refused, not ignored.
    """
    actions_pytest = [
        c for c in checks
        if c.get("name") == TEST_CHECK_NAME
        and (c.get("app") or {}).get("id") == GITHUB_ACTIONS_APP_ID
    ]
    run = _latest(checks, TEST_CHECK_NAME, GITHUB_ACTIONS_APP_ID)
    if run is None:
        return ["CURRENT_HEAD_PYTEST_ABSENT"]
    reasons = []
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        reasons.append("CURRENT_HEAD_PYTEST_NOT_SUCCESSFUL")
    trusted_suites = {
        r.get("check_suite_id") for r in (runs or [])
        if r.get("path") == TESTS_WORKFLOW_PATH
        and r.get("event") == "pull_request"
        and isinstance(sha, str) and r.get("head_sha") == sha
        and type(r.get("check_suite_id")) is int
    }
    for c in actions_pytest:
        if (c.get("check_suite") or {}).get("id") not in trusted_suites:
            reasons.append("PYTEST_CHECK_NOT_FROM_TESTS_WORKFLOW")
            break
    return reasons


def file_mode_reasons(files: list[dict], modes: dict[str, str] | None) -> list[str]:
    """Every changed path must be a regular blob at the head commit."""
    if modes is None:
        return ["FILE_MODES_UNVERIFIED"]
    return [
        f"NON_REGULAR_FILE:{f.get('filename')}"
        for f in files
        if modes.get(f.get("filename")) not in REGULAR_FILE_MODES
    ]


def shared_head_reasons(number: int, sha: str, head_prs: list[dict] | None) -> list[str]:
    """Check runs attach to a SHA, not to a PR.

    If two open PRs share one head, a green eligibility check computed for one
    satisfies the other's required check (e.g. one without the opt-in label).
    """
    if head_prs is None:
        return ["HEAD_SHA_PR_ASSOCIATION_UNVERIFIED"]
    others = {
        p.get("number") for p in head_prs
        if p.get("state") == "open" and (p.get("head") or {}).get("sha") == sha
    } - {number}
    return ["HEAD_SHA_SHARED_WITH_ANOTHER_OPEN_PR"] if others else []


def eligibility_reasons(
    pr: dict, files: list[dict], checks: list[dict],
    *, trusted_app_id: int | None = TRUSTED_AI_AUDITOR_APP_ID,
    runs: list[dict] | None = None,
    modes: dict[str, str] | None = None,
    head_prs: list[dict] | None = None,
) -> list[str]:
    """Narrow allowlist plus independently authenticated AI audit and CI."""
    reasons: list[str] = []
    head = pr.get("head") or {}
    base = pr.get("base") or {}
    repo = base.get("repo") or {}
    sha = head.get("sha")
    number = pr.get("number")
    if pr.get("state") != "open" or pr.get("draft") is not False:
        reasons.append("PR_MUST_BE_OPEN_AND_READY_NOT_DRAFT")
    if base.get("ref") != "main":
        reasons.append("BASE_MUST_BE_MAIN")
    if (head.get("repo") or {}).get("full_name") != repo.get("full_name"):
        reasons.append("CROSS_REPOSITORY_PR_NOT_ADMITTED")
    if LABEL not in {x.get("name") for x in pr.get("labels", [])}:
        reasons.append("ENGINEERING_OPT_IN_LABEL_ABSENT")

    if not files or len(files) > MAX_FILES:
        reasons.append("CHANGED_FILES_OUTSIDE_1_TO_8")
    # The file listing is paginated and capped by GitHub; it must account for
    # every file the PR itself says it changes.
    if type(pr.get("changed_files")) is not int or pr["changed_files"] != len(files):
        reasons.append("CHANGED_FILE_LIST_INCOMPLETE")
    if any(type(f.get("changes")) is not int or f["changes"] < 0 for f in files):
        reasons.append("UNVERIFIABLE_CHANGE_COUNT")
    elif sum(f["changes"] for f in files) > MAX_LINES:
        reasons.append("DIFF_TOO_LARGE_FOR_AUTOMERGE")
    has_source = has_test = False
    for f in files:
        name = f.get("filename", "")
        if not isinstance(name, str) or any(
            seg in (".", "..", "") for seg in name.split("/")
        ):
            reasons.append("INVALID_FILENAME")
            continue
        if f.get("status") not in {"added", "modified"}:
            reasons.append(f"NON_ADDITIVE_CHANGE:{name}")
        if not isinstance(f.get("patch"), str):
            reasons.append(f"UNREVIEWABLE_PATCH:{name}")
        if ALLOW_SOURCE.fullmatch(name):
            has_source = True
        elif ALLOW_TEST.fullmatch(name):
            has_test = True
        elif not ALLOW_DOC.fullmatch(name):
            reasons.append(f"PATH_REQUIRES_OWNER_APPROVAL:{name}")
    if not (has_source and has_test):
        reasons.append("REQUIRE_DEVTOOLS_SOURCE_AND_TEST")
    reasons.extend(file_mode_reasons(files, modes))

    if not isinstance(number, int) or not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        reasons.append("INVALID_PR_OR_HEAD_SHA")
    else:
        reasons.extend(audit_evidence_reasons(number, sha, checks, trusted_app_id))
        reasons.extend(shared_head_reasons(number, sha, head_prs))
    reasons.extend(impersonation_reasons(checks, trusted_app_id))
    reasons.extend(ci_evidence_reasons(checks, sha, runs))
    return reasons


def api(method: str, endpoint: str, token: str, body: dict | None = None):
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "User-Agent": "investment-trusted-merge-guard-v2",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    data = json.dumps(body).encode("utf-8") if body is not None else None
    if data is not None:
        headers["Content-Type"] = "application/json"
    with urllib.request.urlopen(
        urllib.request.Request(
            "https://api.github.com" + endpoint,
            data=data,
            headers=headers,
            method=method,
        ), timeout=25
    ) as response:
        return json.load(response)


def paginate(endpoint: str, token: str) -> list[dict]:
    items: list[dict] = []
    for page in range(1, 12):
        sep = "&" if "?" in endpoint else "?"
        result = api("GET", endpoint + sep + f"per_page=100&page={page}", token)
        if not isinstance(result, list):
            raise ValueError("EXPECTED_PAGINATED_LIST")
        items.extend(result)
        if len(result) < 100:
            return items
    raise ValueError("PAGINATION_LIMIT_REACHED_FAIL_CLOSED")


def paginate_envelope(endpoint: str, key: str, token: str) -> list[dict]:
    """Collect an {total_count, <key>: [...]} listing; never a partial one."""
    items: list[dict] = []
    total = None
    for page in range(1, 12):
        sep = "&" if "?" in endpoint else "?"
        payload = api("GET", endpoint + sep + f"per_page=100&page={page}", token)
        batch = payload.get(key) if isinstance(payload, dict) else None
        count = payload.get("total_count") if isinstance(payload, dict) else None
        if not isinstance(batch, list) or type(count) is not int:
            raise ValueError("CHECK_RUN_RESULTS_INCOMPLETE")
        if total is None:
            total = count
        elif count != total:
            raise ValueError("LISTING_CHANGED_DURING_PAGINATION")
        items.extend(batch)
        if len(items) >= total or not batch:
            break
    if total is None or len(items) != total:
        raise ValueError("CHECK_RUN_RESULTS_INCOMPLETE")
    return items


def get_head_checks(repo_path: str, sha: str, token: str) -> list[dict]:
    """Never accept a partial API page or status from another commit.

    `filter=all`: the endpoint's default `filter=latest` selects by
    completed_at, so a queued re-run (completed_at=None) could be hidden behind
    the older success it replaces. The gate orders by check-run id itself.
    """
    runs = paginate_envelope(
        repo_path + f"/commits/{sha}/check-runs?filter=all", "check_runs", token
    )
    if any(x.get("head_sha") != sha for x in runs):
        raise ValueError("CHECK_RUN_HEAD_SHA_MISMATCH")
    return runs


def get_head_workflow_runs(repo_path: str, sha: str, token: str) -> list[dict]:
    runs = paginate_envelope(
        repo_path + f"/actions/runs?head_sha={sha}", "workflow_runs", token
    )
    if any(x.get("head_sha") != sha for x in runs):
        raise ValueError("WORKFLOW_RUN_HEAD_SHA_MISMATCH")
    return runs


def get_file_modes(repo_path: str, sha: str, paths: list[str], token: str) -> dict[str, str]:
    """Git modes of `paths` at commit `sha`, by walking non-recursive trees."""
    trees: dict[str, dict[str, dict]] = {}

    def tree(directory: str, tree_sha: str) -> dict[str, dict]:
        if directory not in trees:
            payload = api("GET", repo_path + f"/git/trees/{tree_sha}", token)
            if payload.get("truncated") is not False or not isinstance(payload.get("tree"), list):
                raise ValueError("GIT_TREE_INCOMPLETE")
            trees[directory] = {e.get("path"): e for e in payload["tree"]}
        return trees[directory]

    commit = api("GET", repo_path + f"/git/commits/{sha}", token)
    root = (commit.get("tree") or {}).get("sha")
    if commit.get("sha") != sha or not isinstance(root, str):
        raise ValueError("GIT_COMMIT_UNRESOLVED")
    modes: dict[str, str] = {}
    for path in paths:
        parts = path.split("/")
        entries = tree("", root)
        directory = ""
        for segment in parts[:-1]:
            entry = entries.get(segment)
            if entry is None or entry.get("type") != "tree":
                break
            directory = directory + "/" + segment
            entries = tree(directory, entry["sha"])
        else:
            entry = entries.get(parts[-1])
            if entry is not None and entry.get("type") == "blob":
                modes[path] = entry.get("mode")
    return modes


def pr_number_from_event(event: dict, repository: str) -> int:
    direct = (event.get("pull_request") or {}).get("number")
    if isinstance(direct, int):
        return direct
    payload = event.get("workflow_run") or event.get("check_run") or {}
    # `pull_requests` can list PRs of OTHER repositories that share the head;
    # their numbers mean a different PR here.
    suffix = "/repos/" + repository
    numbers = {
        x.get("number") for x in (payload.get("pull_requests") or [])
        if str(((x.get("base") or {}).get("repo") or {}).get("url", "")).endswith(suffix)
    }
    if len(numbers) != 1 or not all(isinstance(x, int) for x in numbers):
        raise ValueError("EVENT_PR_ID_UNRESOLVED_OR_AMBIGUOUS")
    return next(iter(numbers))


def pr_fingerprint(pr: dict) -> tuple:
    """Everything eligibility reads from the PR record itself."""
    return (
        (pr.get("head") or {}).get("sha"),
        pr.get("state"),
        pr.get("draft"),
        (pr.get("base") or {}).get("ref"),
        pr.get("changed_files"),
        tuple(sorted(str(x.get("name")) for x in pr.get("labels", []))),
    )


def post_check(base_path: str, token: str, number: int, sha: str, reasons: list[str]) -> dict:
    if reasons:
        summary = "Not eligible; NO MERGE.\n" + "\n".join("- " + s for s in reasons)
    else:
        summary = (
            "NARROW DEVTOOLS CANDIDATE, NOT A MERGE AUTHORIZATION. "
            "Native protected-main rules must require pytest, an independent AI "
            "audit check from the pinned App, and this exact-head eligibility check. "
            "The repository auto-merge feature must stay OFF until a negative-test "
            "pilot and owner acceptance verify those rules."
        )
    return api("POST", base_path + "/check-runs", token, {
        "name": NAME,
        "head_sha": sha,
        "external_id": f"investment-eligibility:v1:pr:{number}:sha:{sha}",
        "status": "completed",
        "conclusion": "failure" if reasons else "success",
        "output": {
            "title": "BLOCKED" if reasons else "PILOT CANDIDATE ONLY",
            "summary": summary[:65000],
        },
    })


def main() -> int:
    token = os.environ["GITHUB_TOKEN"]
    repository = os.environ["GITHUB_REPOSITORY"]
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as stream:
        event = json.load(stream)
    number = pr_number_from_event(event, repository)
    base_path = "/repos/" + repository
    pr_path = base_path + f"/pulls/{number}"
    pr = api("GET", pr_path, token)
    if ((pr.get("base") or {}).get("repo") or {}).get("full_name") != repository:
        raise ValueError("REPOSITORY_MISMATCH")
    sha = pr["head"]["sha"]
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("INVALID_HEAD_SHA")
    try:
        files = paginate(pr_path + "/files", token)
        checks = get_head_checks(base_path, sha, token)
        runs = get_head_workflow_runs(base_path, sha, token)
        modes = get_file_modes(
            base_path, sha,
            [f["filename"] for f in files if isinstance(f.get("filename"), str)], token,
        )
        head_prs = paginate(base_path + f"/commits/{sha}/pulls", token)
        reasons = eligibility_reasons(
            pr, files, checks, runs=runs, modes=modes, head_prs=head_prs
        )
        # If the PR changed after inspection, do not post a green assertion.
        refreshed = api("GET", pr_path, token)
        if pr_fingerprint(refreshed) != pr_fingerprint(pr):
            reasons.append("PR_CHANGED_DURING_ASSESSMENT")
    except Exception as exc:
        # A crash must not leave an EARLIER green check as the latest result on
        # this SHA. Overwrite it with a failure, then still fail the job.
        post_check(base_path, token, number, sha, [f"GATE_ERROR_FAILED_CLOSED:{type(exc).__name__}"])
        raise
    created = post_check(base_path, token, number, sha, reasons)
    print(json.dumps({
        "pr": number,
        "head": sha,
        "eligibility": not reasons,
        "reasons": reasons,
        "check_run_id": created.get("id"),
    }, ensure_ascii=False))
    return 0  # Independent posted check carries the denial status.


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        # An absent check must block a correctly configured required-check rule.
        # Never print credentials, HTTP headers, or untrusted exception text.
        print(f"MERGE_GUARD_FAILED_CLOSED: {type(exc).__name__}", file=sys.stderr)
        sys.exit(1)
