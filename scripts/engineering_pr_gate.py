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
from datetime import datetime

NAME = "Investment Auto-merge eligibility"
AI_AUDIT_NAME = "Investment Independent AI Audit"
AI_AUDIT_TITLE = "INDEPENDENT_DIFF_AUDIT_PASSED"
LABEL = "auto-merge:engineering"
TEST_CHECK_NAME = "pytest"
GITHUB_ACTIONS_APP_ID = 15368
# Deliberately DISARMED. Pin the real externally authenticated review App ID
# only through a separately reviewed, owner-authorized policy change.
TRUSTED_AI_AUDITOR_APP_ID = None
MAX_FILES = 8
MAX_LINES = 350
ALLOW_SOURCE = re.compile(r"^scripts/devtools/[A-Za-z0-9_/-]+\.py$")
ALLOW_TEST = re.compile(r"^tests/test_devtools_[A-Za-z0-9_]+\.py$")
ALLOW_DOC = re.compile(r"^docs/devtools/[A-Za-z0-9_/-]+\.md$")


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
    return max(matching, key=lambda c: (c.get("started_at") or "", c.get("id") or 0))


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


def ci_evidence_reasons(checks: list[dict]) -> list[str]:
    """The same exact-head PR SHA must have successful GitHub Actions pytest."""
    run = _latest(checks, TEST_CHECK_NAME, GITHUB_ACTIONS_APP_ID)
    if run is None:
        return ["CURRENT_HEAD_PYTEST_ABSENT"]
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        return ["CURRENT_HEAD_PYTEST_NOT_SUCCESSFUL"]
    return []


def eligibility_reasons(
    pr: dict, files: list[dict], checks: list[dict],
    *, trusted_app_id: int | None = TRUSTED_AI_AUDITOR_APP_ID,
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
    if head.get("repo", {}).get("full_name") != repo.get("full_name"):
        reasons.append("CROSS_REPOSITORY_PR_NOT_ADMITTED")
    if LABEL not in {x.get("name") for x in pr.get("labels", [])}:
        reasons.append("ENGINEERING_OPT_IN_LABEL_ABSENT")

    if not files or len(files) > MAX_FILES:
        reasons.append("CHANGED_FILES_OUTSIDE_1_TO_8")
    if sum((f.get("changes") or 0) for f in files) > MAX_LINES:
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

    if not isinstance(number, int) or not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        reasons.append("INVALID_PR_OR_HEAD_SHA")
    else:
        reasons.extend(audit_evidence_reasons(number, sha, checks, trusted_app_id))
    reasons.extend(ci_evidence_reasons(checks))
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


def get_head_checks(repo_path: str, sha: str, token: str) -> list[dict]:
    """Never accept a partial API page or status from another commit."""
    payload = api("GET", repo_path + f"/commits/{sha}/check-runs?per_page=100", token)
    runs = payload.get("check_runs")
    if not isinstance(runs, list) or payload.get("total_count", 0) > len(runs):
        raise ValueError("CHECK_RUN_RESULTS_INCOMPLETE")
    if any(x.get("head_sha") != sha for x in runs):
        raise ValueError("CHECK_RUN_HEAD_SHA_MISMATCH")
    return runs


def main() -> int:
    token = os.environ["GITHUB_TOKEN"]
    repository = os.environ["GITHUB_REPOSITORY"]
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as stream:
        event = json.load(stream)
    number = (event.get("pull_request") or {}).get("number")
    if not isinstance(number, int):
        raise ValueError("MISSING_PR_NUMBER")
    base_path = "/repos/" + repository
    pr_path = base_path + f"/pulls/{number}"
    pr = api("GET", pr_path, token)
    if (pr.get("base") or {}).get("repo", {}).get("full_name") != repository:
        raise ValueError("REPOSITORY_MISMATCH")
    files = paginate(pr_path + "/files", token)
    sha = pr["head"]["sha"]
    checks = get_head_checks(base_path, sha, token)
    reasons = eligibility_reasons(pr, files, checks)
    # If the PR was updated after inspection, do not post a green assertion.
    refreshed = api("GET", pr_path, token)
    if refreshed["head"]["sha"] != sha:
        reasons.append("HEAD_SHA_CHANGED_DURING_ASSESSMENT")

    if reasons:
        summary = "Not eligible; NO MERGE.\\n" + "\\n".join("- " + s for s in reasons)
    else:
        summary = (
            "NARROW DEVTOOLS CANDIDATE, NOT A MERGE AUTHORIZATION. "
            "Native protected-main rules must require pytest, an independent AI "
            "audit check from the pinned App, and this exact-head eligibility check. "
            "The repository auto-merge feature must stay OFF until a negative-test "
            "pilot and owner acceptance verify those rules."
        )
    created = api("POST", base_path + "/check-runs", token, {
        "name": NAME,
        "head_sha": sha,
        "status": "completed",
        "conclusion": "failure" if reasons else "success",
        "output": {
            "title": "BLOCKED" if reasons else "PILOT CANDIDATE ONLY",
            "summary": summary[:65000],
        },
    })
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
