# Workflow inventory — additive 006800 source repair

The three older inventories and their frozen census test remain byte-identical.
The supplemental census covers both GitHub-supported `.yml` and `.yaml` files,
including all four inventory layers, with the same ACTIVE/RETIRED/on-disk rules.
The source-repair workflow uses `.yaml` so the older frozen `.yml` census can
continue validating its original scope without altering a v1/v2 dependency.

## ACTIVE

| Workflow | Trigger | Scheduled | Purpose |
| --- | --- | --- | --- |
| `KR Alpha Atlas Phase C source repair` (`kr-alpha-atlas-phase-c-price-repair.yaml`) | Manual workflow_dispatch, main only, default validate | **No** | Exact-hash v3 source-repair addendum, same v1 scientific executor, concurrency group, permanent global lock and result namespace. Preflight reconstructs the corrected PIT matrix without labels/fits/locks. Execute requires separately committed exact v3 owner approval and original source gates. Older versions remain historically traceable and cannot create a second study opportunity. |
