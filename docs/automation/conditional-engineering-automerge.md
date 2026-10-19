# Conditional engineering auto-merge — safety bootstrap v1

**Status: DISARMED.** This change installs a read-only, fail-closed eligibility
classifier. It does **not** merge any PR, turn on GitHub Auto-merge, change GitHub
Settings, authorize experiments, or alter investment decisions.

## Owner-approved scope and boundary

The owner approved a *principle*: routine low-risk engineering may eventually
be merged without repeated owner clicks, but **only after** protected-branch,
independent-review, and latest-head CI guarantees have been installed and
verified. Approval of this principle does not waive the requirements and does
not authorize a merge now.

Always owner-only: research hypotheses and registered thresholds, sealed input
and execution contracts, C1 formal one-shot execute/lock, historical outcome
reads, data rights and new paid sources, production investment decisions and
allocation, secrets/permissions changes, or changing this merge policy. The
existing `AGENTS.md` invariant forbids unreviewed/direct main changes.

## Current starting state (verified 2026-10-19 KST)

- Public repository, default branch `main`.
- `main` was **unprotected**; no repository ruleset was present.
- Repo setting `allow_auto_merge` was **false**.
- Existing `Tests` workflow runs `pytest` on PRs with read-only contents permission.
- Current #259 and #262–#266 touch research/collection code and are **NOT**
  eligible under the initial low-risk pilot. Passing CI alone does not change this.
- The connected GitHub integration can create branches and Draft PRs, but cannot
  administer repository branch protections. The owner must configure and
  independently verify GitHub Settings in the browser.

## Pilot check behavior

The workflow `.github/workflows/engineering-pr-gate.yml` uses
`pull_request_target` and `pull_request_review` only. It checks out **trusted
main** and never checks out or runs PR contents. It requests the minimum
`contents:read`, `pull-requests:read`, and `checks:write` permissions. Its
script re-fetches the live PR, changed files, and reviews via GitHub's API and
posts `Investment Auto-merge eligibility` **on the actual PR head SHA**.

Eligibility defaults to failure. All of these must hold:

1. Same-repository PR into `main`, **open and non-Draft**.
2. Explicit opt-in label `auto-merge:engineering`.
3. **Only** non-production developer utilities in `scripts/devtools/**/*.py`,
   corresponding synthetic tests `tests/test_devtools_*.py`, and optionally
   `docs/devtools/**/*.md`; at least one source **and** test file.
4. At most 8 files and 350 changed lines; no deletion, renaming, binary or
   otherwise unreviewable patch.
5. A real GitHub `APPROVED` review by an identity **other than the PR author**,
   with the review explicitly attached to the **current head SHA**; later
   `CHANGES_REQUESTED` invalidates that review.

An eligibility PASS only means *candidate under narrow path rules*. It is not
proof of safe semantics, scientific validity, a passing test suite, or the
presence of GitHub branch protection. Other CI and GitHub native rules must be
required independently.

**Security note:** Different language models writing reviews as the *same
GitHub account* are NOT independent GitHub approvers. If every Claude/Codex
PR is authored as `jaehojung1879-netizen`, an independent GitHub review
requires an actually distinct, authorized GitHub identity (human collaborator
or suitably configured reviewer app). Merely posting a Claude/Codex comment
cannot be counted as an `APPROVED` review.

## Required owner-side GitHub setup — BEFORE any merge

**Phase 1 — protect main (no auto-merge):**

In GitHub web UI: Repository → Settings → Rules → Rulesets → New branch
ruleset (or Settings → Branches → Add branch protection rule).

- Target only `main`. Set enforcement **Active**. Avoid bypass actors,
  including administrators where the UI allows.
- Require a pull request before merging, with **at least 1 approval** from a
  distinct authorized GitHub reviewer.
- Dismiss stale approvals on each new push; enable latest-push review and
  conversation resolution if available.
- Require passing **`Tests` / `pytest`** check (choose the precise check
  name and expected GitHub Actions app from the UI, not a guessed label).
- Require up-to-date branches when sensible; prevent force-pushes and branch
  deletions; disallow direct updates to `main`.
- Verify as both repository owner and test contributor that an unapproved PR
  or failed PR **cannot** merge. An admin bypass remaining available is not
  a verified guarantee.

The owner must then independently review and merge **this safety PR** through
the newly protected flow. This is a one-time bootstrap, not permission to
merge any existing research PR.

**Phase 2 — test the trusted gate before making it required:**

Once this safety PR is merged, create a synthetic, low-risk devtools PR and
record:
- It is ineligible while Draft.
- It is ineligible without the opt-in label.
- It is ineligible before a distinct authorized approval on its HEAD.
- It is ineligible on stale approval after a push.
- It is ineligible for `pipeline/`, `docs/research-program/`, `scripts/collect_*`,
  `.github/`, `AGENTS.md`, tests outside the allowlist, and this policy.
- The trusted workflow posts `Investment Auto-merge eligibility` check to
  the correct head SHA, fails as expected, and passes only on all green cases.
- The original Tests workflow independently reports full CI success on that
  exact candidate head SHA.

Then add the *actual* `Investment Auto-merge eligibility` check to main's
**required status checks**, selecting its GitHub Actions source; repeat an
unauthorized-PR negative test. If GitHub doesn't expose that check in rules,
**STOP** and fix the status wiring rather than assuming protection.

**Phase 3 — optional, only after all checks are proven:**

Turn on repository Settings → General → Pull Requests → Allow auto-merge.
Opt in **one** fully checked test PR using native GitHub Auto-merge and verify
it waits until every required check and independent approval succeeds. No
automatic agent dispatch of `enable_auto_merge` is installed by this PR.
An autonomous enabler requires a separate scoped proposal, review and
demonstrated authorization gate; do NOT grant `pull_request_target` write
permission to merge PRs or check out PR code.

## Fail-closed acceptance

- A skipped, missing or errored checker is **not** approval; protected main
  must require the correct exact check.
- CI success by itself never qualifies historical research or data ingestion.
- Draft #259/#262/#263/#264/#265/#266 are never silently auto-promoted.
- If native independent review cannot be arranged with a distinct GitHub
  identity, the system remains *review-and-recommend only* — no auto-merge.
- Store PR URL, exact head SHA, check-run, review identity, Tests result and
  protection-verification evidence before activating any merge delegation.

## Synthetic verification

```bash
python -m pytest -q tests/test_engineering_pr_gate.py
ruff check scripts/engineering_pr_gate.py tests/test_engineering_pr_gate.py
python -m compileall scripts/engineering_pr_gate.py
```
