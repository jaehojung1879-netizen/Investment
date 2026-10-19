"""Fail-closed, trusted-base PR eligibility check for a very narrow devtools pilot.

This is NOT a merger and does not certify research validity. The necessary
additional GitHub branch rules (pytest, independent approval, no bypass) must
be enabled by the owner before this check can be used for any auto-merge.
Run ONLY from trusted main via pull_request_target / pull_request_review.
Never check out a pull request when running this script.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

NAME = "Investment Auto-merge eligibility"
LABEL = "auto-merge:engineering"
MAX_FILES = 8
MAX_LINES = 350
ALLOW_SOURCE = re.compile(r"^scripts/devtools/[A-Za-z0-9_/-]+\.py$")
ALLOW_TEST = re.compile(r"^tests/test_devtools_[A-Za-z0-9_]+\.py$")
ALLOW_DOC = re.compile(r"^docs/devtools/[A-Za-z0-9_/-]+\.md$")


def eligibility_reasons(pr: dict, files: list[dict], reviews: list[dict]) -> list[str]:
    """Deterministic, conservative classifier; unrecognized states are ineligible."""
    reasons: list[str] = []
    head = pr.get("head") or {}
    base = pr.get("base") or {}
    repo = pr.get("base", {}).get("repo") or {}
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
        if not isinstance(name, str) or any(seg in (".", "..", "") for seg in name.split("/")):
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

    author = ((pr.get("user") or {}).get("login") or "").lower()
    sha = head.get("sha")
    latest_by_reviewer: dict[str, dict] = {}
    for r in sorted(reviews, key=lambda v: (v.get("submitted_at") or "", v.get("id") or 0)):
        login = ((r.get("user") or {}).get("login") or "").lower()
        if login:
            latest_by_reviewer[login] = r
    has_independent_current_approval = any(
        login != author and r.get("state") == "APPROVED"
        and r.get("commit_id") == sha
        for login, r in latest_by_reviewer.items()
    )
    if not has_independent_current_approval:
        reasons.append("INDEPENDENT_GITHUB_APPROVAL_ON_EXACT_HEAD_REQUIRED")
    return reasons


def api(method: str, endpoint: str, token: str, body: dict | None = None):
    url = "https://api.github.com" + endpoint
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "User-Agent": "investment-trusted-merge-guard-v1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    data = json.dumps(body).encode("utf-8") if body is not None else None
    if data is not None:
        headers["Content-Type"] = "application/json"
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers, method=method), timeout=25) as response:
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
    if pr["base"]["repo"]["full_name"] != repository:
        raise ValueError("REPOSITORY_MISMATCH")
    files = paginate(pr_path + "/files", token)
    reviews = paginate(pr_path + "/reviews", token)
    reasons = eligibility_reasons(pr, files, reviews)
    # Ensure our decision is tied to the current PR head, not a raced push.
    refreshed = api("GET", pr_path, token)
    if refreshed["head"]["sha"] != pr["head"]["sha"]:
        reasons.append("HEAD_SHA_CHANGED_DURING_ASSESSMENT")

    summary = (
        "Not eligible; no merge performed.\n" + "\n".join("- " + s for s in reasons)
        if reasons else
        "NARROW DEVTOOLS CANDIDATE ONLY. This is not a merge, a research approval, "
        "or evidence that branch protection/CI is configured. Native protected-branch "
        "pytest and independent-review rules must also pass."
    )
    created = api("POST", base_path + "/check-runs", token, {
        "name": NAME,
        "head_sha": pr["head"]["sha"],
        "status": "completed",
        "conclusion": "failure" if reasons else "success",
        "output": {
            "title": "BLOCKED" if reasons else "ELIGIBLE FOR PROTECTED-BRANCH REVIEW",
            "summary": summary[:65000],
        },
    })
    print(json.dumps({
        "pr": number,
        "head": pr["head"]["sha"],
        "eligibility": not reasons,
        "reasons": reasons,
        "check_run_id": created.get("id"),
    }, ensure_ascii=False))
    return 0  # The independently posted check conclusion is the required status.


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        # Failure must NEVER emit an eligible check. Missing check blocks a
        # correctly protected branch. Do not print token or HTTP request headers.
        print(f"MERGE_GUARD_FAILED_CLOSED: {type(exc).__name__}", file=sys.stderr)
        sys.exit(1)
