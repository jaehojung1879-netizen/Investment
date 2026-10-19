# Investment conditional engineering auto-merge — SOLO AI-audit bootstrap

**STATUS: DISARMED / NO MERGES AUTHORIZED.**

Owner policy approved 2026-10-19: only low-risk engineering may EVENTUALLY
auto-merge after independently verified safeguards. No automatic main merge,
no shortcut approval, no execution of sealed research, no live trading.

## Current actual GitHub state (checked 2026-10-19 KST)

- GitHub Ruleset ID 25393965: "Investment Main Protection", ACTIVE,
  targeting the default branch main, with no bypass actors.
- Native PR approval count = 1; stale approvals dismissed; most recent push
  needs approval; review conversations must be resolved.
- Required pytest from the GitHub Actions integration, strict up-to-date
  checks; force pushes and deletion prohibited.
- Repo setting allow_auto_merge is FALSE.
- All current PRs #259 and #262–#266 are research/collector work, NOT
  eligible for the initial devtools-only auto-merge pilot.
- Safety PR #267 is a Draft and cannot be merged under the pilot.
- The newly proposed independent AI gate is NOT running on main. This
  workflow first has to land through the protected PR route.

## Design: AI-independent review without a second human GitHub account

Two agents writing different comments as the SAME GitHub user do not create
an independently authenticated GitHub approval. A free-text comment, PR label,
AI-written file inside the PR, or author-controlled workflow result is NOT
accepted as proof of independent audit.

The alternative uses a trusted, independently provisioned GitHub App identity
that ACTUALLY runs a separate AI diff review. This can be an existing
provider-managed reviewer App; it is NOT necessarily a second human account.
However, installing/configuring one may require owner action. Do not buy
anything, add secrets, grant new permissions, or assume an unverified App can
produce an approval.

Its audit/check contract must be reviewed and demonstrated before trusting it:

1. Independent reviewer obtains the latest PR changed-file diff from GitHub,
   evaluates the exact HEAD, documents findings, and is configured not to
   reuse the author's model output as its entire review.
2. Reviewer posts GitHub check-run named "Investment Independent AI Audit",
   on the exact HEAD, as a **separate pinned App ID** (not GitHub Actions).
3. On a PASS, the App's check run must have:
   - status = completed; conclusion = success.
   - external_id: investment-ai-audit:v1:pr:<PR_NUMBER>:sha:<40_HEX_HEAD>.
   - output.title: INDEPENDENT_DIFF_AUDIT_PASSED.
   - HTTPS details_url showing inspectable independent review evidence.
4. A negative verdict, missing output, old SHA, other PR identity, another App,
   pending result, or changed head MUST fail closed.
5. The trusted-main checker re-fetches the PR and its check runs directly
   through GitHub API. Author-written PR comments or attestations are not
   considered.
6. The same SHA must also have a successful GitHub Actions pytest check.
7. A **separately enforced GitHub Ruleset** must require all three checks
   on protected main: pytest, Investment Independent AI Audit (correct pinned
   App integration), and Investment Auto-merge eligibility (GitHub Actions).
   The trusted-main checker itself CANNOT replace native branch protection.

IMPORTANT: a check signed by an App establishes its GitHub principal and the
reported verdict; it does not mathematically prove that the App used a
different model or performed a competent review. Owner must inspect App
implementation, permissions and review reports during pilot verification.

The trusted App ID is currently intentionally None in
scripts/engineering_pr_gate.py. DO NOT replace None merely to get a PASS.
Pin the real app ID only in a separately reviewed policy change after verifying
its provenance, separate execution, scope, and test coverage.

## Low-risk path allowlist (initial strict pilot)

All of the following are required:

- Open non-Draft PR into main in the same repository.
- Label auto-merge:engineering (opt-in is necessary but NOT sufficient).
- Maximum 8 changed files, 350 changed lines; changed files must have
  inspectable text patches and cannot be removed or renamed.
- Changed paths only scripts/devtools/**.py, tests/test_devtools_*.py and
  optional docs/devtools/**.md. Must include devtools source AND tests.
- Neither research, collection, workflow, policy, application, deployment,
  secrets, portfolio, source acquisition, nor gate implementation itself.
- Verified external AI App audit on current PR and HEAD (see above).
- Successful current-SHA GitHub Actions pytest.
- Branch rules must independently enforce checks and review policy.

A success from this classifier is **NOT an instruction to merge**. The
workflow posts a machine check; it has no pull-requests:write permissions
and never calls a merge API.

## Trusted workflow security

.github/workflows/engineering-pr-gate.yml:

- Uses pull_request_target, pull_request_review, workflow_run (Tests
  completion) and the independent AI App's check_run completion to re-evaluate.
- Checks out only trusted main. It never checks out, installs dependencies
  from, or runs code from the PR.
- Fetches current PR/files and exact-head check runs through GitHub API;
  partial pages, wrong SHA, unauthorized App ID, or processing errors
  cannot produce a passing check run.
- Uses least possible permissions: contents:read, pull-requests:read,
  checks:write. No workflow grants merge permissions.
- A missing or failed gate check must be BLOCKING once the rule is enabled.
  Before activation, no automation may interpret a non-required check as safe.

## Mandatory bootstrap steps; current owner review still required

### Step 1 — completed: protect main

The initial Ruleset is active with 1 formal GitHub approval required.
KEEP this intact until alternative checks have actually been proven.

### Step 2 — finish safety PR #267, but DO NOT merge it prematurely

Obtain final HEAD pytest success, independent code/security review, and
negative-case synthetic test evidence. This PR is not auto-merge eligible.

**Bootstrap dependency:** With all PRs authored under the same owner GitHub
login and Ruleset count=1, GitHub's native approval is NOT satisfiable by the
owner or by two AI review comments on that account. Landing #267 while
preserving that rule may require a separate trusted reviewing GitHub App (if
its formal review is accepted by GitHub) or a different human collaborator
for this ONE bootstrap step. No such App/identity is verified today.

Do NOT silently lower approval count, add an admin bypass, or merge with an
exception. If this dependency remains, the whole rollout MUST remain BLOCKED
until the owner authorizes a separately reviewed safe migration procedure.

### Step 3 — prove independent AI App and gate on a synthetic PR

After the safety code lands under protected main:

1. Confirm reviewer App ID, review source, result URL, model independence,
   narrow permissions and audit output tied to PR and exact head SHA.
2. In a strictly synthetic devtools PR, test: missing App; spoofed GitHub
   Actions; wrong App; missing/delayed/failing review; stale SHA; PR mismatch;
   fake review comment; canceled/failed/missing pytest; changed diff; Draft
   PR; wrong path; binary/deleted patch; and stale approvals.
3. Confirm the trust checker runs from main and posts the correct check to
   the exact PR head; verify no checkout of PR code and no PR merge.
4. Add both the named external AI audit check (pinned App integration) and
   the trusted eligibility check (GitHub Actions) as REQUIRED status checks.
5. Verify absence or failure of either check actually blocks a test PR
   even when other tests pass. Do not rely on configuration screenshots alone.
6. Only after that, the owner MAY lower native approval count from 1 to 0.
   Re-run the negative branch protection tests immediately afterward.
7. Keep native auto-merge disabled until a separately accepted one-PR
   low-risk pilot has proved exact-head enforcement and no bypass.

### Step 4 — pilot GitHub native auto-merge, not a custom merge bot

Only after all previous gates are proved:

- Enable GitHub's native Allow auto-merge repository setting (owner action).
- On one clean devtools synthetic PR, enable native Auto-merge; verify it
  waits for all required tests/audit checks and refuses modified HEAD.
- Do not automate calls to enable_auto_merge through this PR.
- Maintain owner-only review for any study contract, C1 one-shot execute,
  past outcomes, production policy, data rights, billing or permissions.

## Synthetic tests

Run:

    python -m pytest -q tests/test_engineering_pr_gate.py
    ruff check scripts/engineering_pr_gate.py tests/test_engineering_pr_gate.py
    python -m compileall scripts/engineering_pr_gate.py

Tests simulate an independent App with a FAKE numeric ID; the real
production App ID remains None and MUST fail-closed. The full existing
Tests workflow (pytest) is separate and still required.

## What an owner should expect right now

- Main protection: yes.
- Draft safety PR: prepared, CI verification ongoing.
- Distinct AI review App: not yet installed/verified.
- End-to-end independent AI audit: NOT verified.
- Required AI audit and eligibility status checks: NOT installed yet.
- Native approval requirement: remains 1.
- Repository Auto-merge: OFF.
- PR merges: NONE performed. Existing research Draft PRs remain unchanged.

**STOP:** no PR, not even this safety PR, is automatically mergeable now.
