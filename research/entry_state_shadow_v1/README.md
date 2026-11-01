# entry-state shadow (PROSPECTIVE PAPER) — observations and ledger dry run

- `observation-20261030-v2-not-reproducible-by-its-commit.json` — the file PR #304 committed at `fcf67e31`, kept byte-identical
  (moved from `docs/results/`). The `scripts/entry_state_shadow_observation.mjs` at that commit throws
  `ReferenceError: x is not defined` on the real 2026-10-30 inputs (signal-history `187aeeda`, config `37f8cbf6`), so this file
  was not produced by the code it was committed with. Its schema (e.g. `configurationCommit`, `selectionRule`) is not that
  code's output either. Do not cite it as reproducible.
- `observation-20261030-v3.json` — the same inputs through the fixed observer (`ENTRY_STATE_SHADOW_CARDINALITY_V3`), Git-object
  verified, sha256 `ec618c8c1139513b2fe05a75411c88f636774c13a9152287c487781e79073a93`. Scenario grid 0,1,2,3,4,5,10; no permanent
  combined KR+US maximum; current research policy `PASSIVE_NO_DEFENSIBLE_EDGE` (0 stocks, 100% ETF) in both regions.
- `ledger-dryrun-20261030/` — what `scripts/record_entry_state_shadow.py` appends for that observation (offline, no prices).
  Recorded 2026-11-01T01:44:36Z, before the 2026-11-02 KR/US opens, so its execution session is 2026-11-02. It is NOT a
  signal-history receipt: no fill, NAV or return exists. Live receipts start only once the hook runs in the scheduled
  paper-ledger workflow on main.
