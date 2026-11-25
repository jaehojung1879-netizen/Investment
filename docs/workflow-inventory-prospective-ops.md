# Workflow inventory — prospective-ops-v1 (additive layer)

The four earlier inventories stay byte-identical. This layer registers the one workflow added by `prospective-ops-v1`.

## ACTIVE

| Workflow | Trigger | Scheduled | Purpose |
| --- | --- | --- | --- |
| `Prospective ops` (`prospective-ops.yml`) | Weekdays 10:40, 12:40, 14:40 UTC (19:40 / 21:40 / 23:40 KST) and manual `workflow_dispatch` (default `status-only`), main only | **Yes** | No AI, no token spend. `corporate-writer` runs the registered pinned `live_run` for `kr-corporate-information-events-v1` only when `scripts/prospective_ops.py guard` returns ALLOW_WRITE (owner-enabled registry flag + single-writer attestation + pinned code + intact remote ledger); then verifies the receipt on the remote ledger. `monitor` always builds the read-only operations status from receipts, uploads it, publishes an overwritten snapshot to `signal-history/ledger/research-ops/`, and fails only when an automation-ENABLED study is MISSED / EXECUTION_FAILED / SOURCE_BLOCKED. Ships with every `automation.enabled` false, so no receipt is written until the owner activates it. |
