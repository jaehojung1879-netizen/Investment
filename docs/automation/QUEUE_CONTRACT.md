# Durable Issues queue and journal

Issues are the human work queue. A dedicated GitHub ref
`refs/heads/automation/queue-v1` holds the authoritative machine journal in one
`queue.json`; Issue status comments/labels are a repairable projection, never a
lock. No GitHub workflow is added. This ref is dormant and has not been created.

Each Issue must contain: task ID, Track A/B/C/D, numeric priority (lower first),
dependency IDs, assigned implementer `codex`, independent reviewer `claude`,
LOW risk, one allowlisted kind, exact allowed files and resource namespaces,
explicit acceptance tests, input/output restrictions, budgets, all owner-gate
flags false and status READY / RUNNING / CI_WAIT / REVIEW / DONE /
BLOCKED_OWNER / FAILED. Pin the SHA-256 of its reviewed specification bytes in
`scope_sha256`. Any Issue edit invalidates admission until a human reconciles the
scope; workers compare the digest before every resume. Issue text cannot expand
scope. DONE means implementation reviewed, never merged or scientifically approved.

Machine state additionally preserves Issue number, claim event, PR number, full
head SHA, CI run ID/outcome, repair count and append-only event history. CI records
must represent the complete required Tests check on the exact PR head, verified
from GitHub; a partial job, stale head, skipped/cancelled run or absent check is
not SUCCESS. Never trust an event payload without querying its current source.
Deduplicate by provider delivery ID (or stable `run-id:head:status` for polling).
Changed payload with the same ID is rejected. No free-text result payloads.

## Atomic selection and resumption

1. Reconcile all open work, especially KR A0, with the journal. If GitHub cannot
   be read, do not admit/claim work; report the access blocker. Include external
   workers in the two-slot limit and reserve their resources. A local fixture is
   never the live queue. No implicit empty-state fallback.
2. Fetch the one queue ref, validate its schema, owner gates, dependency graph and
   slot/resource invariants. Duplicate Issue/specification/PR identities, unknown types or cycles fail closed.
3. Service existing RUNNING/CI_WAIT/REVIEW work. CI_WAIT means monitor the existing
   run, not rerun. REVIEW means request one exact-head read-only independent review
   (persist the handoff receipt in the Issue; dedupe by PR/head/reviewer).
4. Choose one READY item whose dependencies are DONE and whose declared resources
   do not overlap active work, ordered by priority then task ID. B is independent
   of A/C; D shadow work uses synthetic inputs only. Owner-blocked items remain
   blocked. No safe item means stop.
5. Compute a transition and commit the **entire** journal as the sole file in a
   child commit. Push without force to the queue ref. A rejected fast-forward
   grants no claim. Writer commits include a unique nonce so identical event deliveries
   cannot both receive a successful push receipt. Reload/reselect within the bounded retry budget. Never run
   from a speculative local commit. This global CAS also protects the two slots.
6. Only after confirmed push, start/resume the task. Use branch
   `automation/task-<id>` and one Issue-linked Draft PR. Reconcile branch/PR/head
   before any create call. If create times out, query before retry; if unavailable,
   preserve branch and block handoff. Never rerun research or create a second PR.
7. Record `ci_started` with PR/head/run, then `ci_result` for that exact head/run.
   FAILURE permits two scoped changed-head repairs total, then FAILED. SUCCESS
   goes to REVIEW. Claude CHANGES consumes that same repair budget and permits
   only original-scope fixes. APPROVED goes to DONE, with no merge operation.

The CLI commits metadata only; it launches no worker, CI, review or research.
Native task runners must follow this protocol and verify external observations.
An interrupted worker reuses its durable claim; do not reclaim by wall-clock age.
If an external launch result is ambiguous, reconcile existing branch/PR/run before
continuing. v1 deliberately offers no automatic unblock/reassign/init command.
Owner-admitted initialization/reconciliation must preserve history and be reviewed.

## Commands and event format

From the existing checkout, with Python 3.11 (stdlib only):

```sh
python -m automation.control --file docs/automation/synthetic-queue.json
python -m automation.control --repo /workspace/Investment
python -m automation.control --repo /workspace/Investment --event /tmp/queue-event.json
```

Only a successful event command returning `event_committed: true` grants a new
transition. Replay returns false: resume/reconcile, never launch again.

The last two require an owner-initialized ref and existing Git write permission;
no token is supplied or extracted. The event command mutates only queue metadata.
Do not run it against the real remote during setup. A rejected CAS exits nonzero.

Example events (IDs below are placeholders; use stable provider IDs in practice):

```json
{"id":"delivery-claim-1","task":"example","op":"claim"}
```

```json
{"id":"delivery-ci-1","task":"example","op":"ci_started","claim":"delivery-claim-1","pr":123,"head_sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","run_id":456}
```

`ci_result` has id/task/op/claim/head_sha/run_id/outcome (SUCCESS or FAILURE).
`review` has id/task/op/claim/head_sha/reviewer (`claude`)/verdict (APPROVED or
CHANGES). `block` has id/task/op/claim; the smallest owner decision belongs in the
Issue, not a free-text machine event. Claims require only id/task/op. Unknown
fields are rejected. Keep IDs short and metadata-only. Scope/risk admission is
human-reviewed; a boolean assertion is not a technical capability grant.
