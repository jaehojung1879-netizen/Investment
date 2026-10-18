# Native automation handoff and owner activation

Nothing in this PR enables a schedule, registers a Routine, installs an app,
changes GitHub settings, creates a queue ref or dispatches research. Additional
API-key and infrastructure budget: $0.

## Evidence and unresolved access

Inspection on 2026-10-18 KST: existing HTTPS Git `ls-remote origin HEAD` succeeded
at main `80ee1b8`. `gh api repos/...`, PR listing and Issue listing returned
Forbidden. No raw credential was requested. Git authentication does not prove
GitHub API, PR-create or Actions-trigger permission. Repository/organization
protection, App installation/scopes, current PR state, current CI duration and
subscription entitlements cannot be certified from this environment.

Tests workflow: pull_request and selected push branches, contents:read,
concurrency per ref with cancel-in-progress, 60-minute timeout, Python 3.11,
pinned requirements, full history and two pinned source fetches, lint, pytest,
entry-point import/compile checks. Existing manual study workflows retain their
owner gates. No workflow is added or rewritten by this PR.

The roadmap records freeze run 39080239146 failed at Draft PR creation although
hash-freeze work completed; #255 and later dry-run are separate evidence. The
existing seal workflow uses github.token / GH_TOKEN and `gh pr create --draft`.
The integrated portfolio workflow explicitly documents a recovery handoff when
GITHUB_TOKEN cannot create the Draft PR: retain exact pushed seal and let a human
open it. The original failure log cannot currently be read, so its exact error
and current permission state remain unverified. Never infer that a YAML
pull-requests:write declaration overrides the repository/organization setting.
Never rerun a one-shot execution because PR creation failed.

GitHub's GITHUB_TOKEN event-recursion restrictions can prevent downstream runs
for token-generated pushes/PR events. Therefore verify the exact-head Tests run
exists; do not assume PR creation triggers CI. Do not auto-dispatch an alternative
workflow, change token scope or insert a PAT as a workaround.

## Native facilities: prefer existing subscription access

Official references to check using the owner's browser:

- Codex Automations: https://developers.openai.com/codex/app/automations/
- Claude Code Routines: https://code.claude.com/docs/en/routines
- Claude Code GitHub Actions: https://code.claude.com/docs/en/github-actions
- GitHub token events: https://docs.github.com/en/actions/security-for-github-actions/security-guides/automatic-token-authentication

The first two official documentation endpoints returned proxy CONNECT 403 here.
Current availability, cloud persistence, UI field names, persistent-goal support,
GitHub trigger/filter support and plan charging could not be verified. The steps
below specify exact desired configuration and prompts, conditional on verified
native support; they are not a claim that an unavailable feature can be enabled.
Do not install the GitHub Actions integration: it may require API billing and
is not equivalent to a subscription-backed cloud Routine.

## Owner steps, in order

1. Review this Draft PR and policy. If approved, the owner merges it through the
   normal protected PR review process before selecting main for native tasks;
   agents never merge. Resolve access through existing approved
   native integrations. Confirm read Issues/PRs/checks, write task branch and
   Draft PR, and read-only Claude review permissions **without changing them in
   this task**. Review branch protection and the last five Tests start/end times
   to set a realistic existing-allowance budget. If access is insufficient,
   choose the manual handoff below rather than silently widening permissions.
2. Reconcile all existing Issues/open PRs and KR A0 ownership. Create or reuse
   Issues from SEED_QUEUE.md; admit only exact reviewed scopes and real Issue
   numbers/digests. Keep US filing acquisition and actual receipts blocked.
   Initialize the dedicated queue ref with only reviewed queue.json using the
   Journal.save(None, queue) protocol, with at most two existing active items.
   This is a separate explicit activation action; never upload the synthetic
   fixture or overwrite an existing ref. Configure admitted agents to follow
   QUEUE_CONTRACT.md and verify the ref is writable using existing access.
3. In the subscription Codex product, verify that the account has a native
   cloud recurring task/goal that runs when the owner's machine is asleep. If
   supported, select this repository/main and the prepared cloud environment;
   name it `Investment safe queue follow-up`; set a **15-minute interval** only
   if native scheduling and subscription quota support it (otherwise choose the
   nearest supported slower interval). Use the exact prompt below. No new API
   keys. If only desktop-local automations are available, this does not meet
   unattended cloud requirements: keep automation inactive and use manual wakes.
4. In subscription Claude Code cloud Routines, verify GitHub event triggers and
   read-only review access already exist. Name it `Investment independent review`;
   repository `jaehojung1879-netizen/Investment`; filter PR opened, reopened,
   synchronize and ready_for_review events to `automation/task-*` branches.
   Include Draft PRs if the native facility supports them. Use HANDOFFS.md Claude
   prompt; accept only journal REVIEW at the same head with Tests SUCCESS. Store
   the PR/head/reviewer dedupe receipt before sending review. If event filtering,
   Draft coverage or GitHub read-only review cannot be configured, do not pretend
   the event path is reliable: use the periodic fallback or manual review.
5. Configure the **same Codex follow-up** as periodic fallback: every wake reconcile
   existing CI_WAIT runs and REVIEW handoffs even if there was no PR event when
   CI finished. Fetch current source status, commit an idempotent ci_result event,
   then hand off review only once per exact head. Never generate an empty commit
   or rerun CI to manufacture an event. If the native products cannot hand off to
   Claude safely under existing access, leave REVIEW and notify the owner.
6. Run a metadata/synthetic-only activation rehearsal first: duplicate trigger,
   overlapping wake, pending CI, failed CI, interruption and owner-blocked task.
   Confirm at most two claims and one PR per task before admitting real work.
   Owner activates only after reviewing actual platform support and budgets.

### Exact Codex follow-up prompt

> Follow docs/automation/OPERATING_POLICY.md, QUEUE_CONTRACT.md and HANDOFFS.md.
> Reconcile the live queue and existing KR A0/open work before admitting anything.
> Continue every safe independent admitted LOW-risk engineering task, one claim
> per wake, at most two globally. Use the existing checkout, no worktree. Verify
> Issue specification digests. Resume claims after interruption; monitor CI_WAIT
> without rerunning. Record exact PR/head/run/outcome with CAS. Two changed-head
> repairs maximum, then FAILED. After Tests SUCCESS request one independent
> Claude read-only exact-head review; process scoped changes only. Poll existing
> CI/review even without a new PR event. Never merge, execute research, access
> historical outcomes, change specs/seals/production/rights/permissions/secrets,
> spend or write actual receipts. Preserve owner-blocked work and select another
> independent READY item. Stop when no safe task remains or after 60 minutes;
> report the smallest owner decision. Access uncertainty means no new launch.

## Explicit manual alternative

If a native integration cannot safely create a PR, retain the task branch and
exact head plus prepared PR body, and give the owner the GitHub compare URL to
open **one Draft PR** using their existing access. First check whether it already
exists. Owner verifies Tests on that exact head, invokes the read-only Claude
handoff and records the review. No PAT, permission bypass or auto-merge. If no
native cloud scheduled facility is available under the existing subscription,
owner manually starts the same follow-up prompt. That limitation means overnight
automation remains unactivated, not “ready”.
