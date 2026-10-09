# Workflow inventory — Phase C input amendment

The original inventory and its first addendum are frozen by earlier registrations.
Neither is edited. The existing inventory tests read this separate layer and keep
the same on-disk / ACTIVE / RETIRED consistency requirements.

## ACTIVE

| Workflow | Trigger | Scheduled | Purpose |
| --- | --- | --- | --- |
| `KR Alpha Atlas Phase C input amendment` (`kr-alpha-atlas-phase-c-amended.yml`) | Manual workflow_dispatch, main only, default validate | **No PR, merge or scheduled historical execution** | Versioned outcome-blind source correction using the unchanged v1 scientific functions. validate checks exact identities; preflight reconstructs the full corrected matrix without targets, reports source readiness and cannot lock; execute requires separately committed exact v2 owner approval and full source readiness. Shares the original v1 concurrency group, global permanent lock, result path and artifact namespace: the versions cannot both execute. Current source readiness is **BLOCKED_PRE_OUTCOME** because full-security 006800.KS price refusal lowers H08 coverage below the unchanged Phase B floor. No authorization, lock or real alpha outcome exists. |
