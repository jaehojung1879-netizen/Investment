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

## Prospective accounting repair

`VENDOR_ADJUSTED_CLOSE_FIXED_ORIGIN_RATIO_V1_PREFIX_CHECKED` values each ticker relative to its explicitly dated first
signal-session close in the SAME vendor acquisition. A later common split/dividend rescaling cancels in this ratio;
units and fill `price` fields denote a vendor valuation index, not broker shares or executable price quotes. This is
conditional vendor-adjusted performance, not independent certification of corporate actions or shareholder total return.

Every NAV row retains the valuation marks, origin dates and acquisition digest. A changed origin, missing published
prefix, or non-uniform revision of a previously recorded ratio is refused without rewriting the old NAV. Legacy raw
adjusted-price books are refused for explicit review rather than silently converted or reset; receipt IDs and study ID
are unchanged. The existing offline observations and historical DEVELOPMENT outputs are unchanged.

On restart, both executed and superseded decision IDs are restored, so an older discarded target cannot trade again.
An incomplete fills/NAV checkpoint is refused; this patch does not claim automatic journal crash recovery.

Regression: `python -m pytest -q tests/test_entry_state_shadow_ledger.py tests/test_entry_state_shadow_restart.py`.
Tests compare one acquisition with multiple resumed acquisitions through split/reverse-split/dividend rescalings,
including the real recorder adapter with offline vendor fixtures, dated costs, retained holdings and NAV. They also
cover superseded decisions, non-uniform revisions, missing origins, legacy books and interrupted checkpoints.

## Operating pattern of the scheduled hook (measured on signal-history `7e7effce`, 2026-11-02)

- The hook reads the published `weekly-decisions/latest.json` and champion `latest.json` of the **previous** run. The weekly file is
  rewritten every day; the champion file only when no region is mid-session, so from about Tuesday to Saturday the two are from
  different generations and the observer refuses to pair them (`DIFFERENT_GENERATION_CANNOT_PAIR`). The champion can also be
  `BLOCKED` (e.g. `CONFLICTING_SAME_SESSION_INPUT` after a same-session input changed), as it is in the 11/01 and 11/02 files.
- A new week's decisions are therefore recorded on the first run after a Saturday publication in which both files are READY and from
  one generation (normally Sunday). A refusal on other days concerns **new decisions only**: with a stored ledger the hook still marks
  the stored book against prices and keeps the stored readout (`report.observation.status = REFUSED`, `status = OK`); with no ledger
  yet it writes `status = REFUSED` and the reason.
- Consequence for the first live week: the 10/30 week was READY in the 10/31 files only, so it is recorded only if a hook run happens
  while those files are still current; otherwise recording starts with the week of 2026-11-06.
- `sourceCommit` on a receipt is the **main** commit that ran the workflow (the inputs are not yet committed again when the hook reads
  them), not an immutable signal-history commit. The receipt carries the SHA-256 of every input it read, which can be matched to the
  signal-history blob afterwards; the verification label says the bytes were not authenticated against a Git object at write time.
