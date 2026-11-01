# readout-connection-v2: entry-state shadow ledger (#304) → economic-path-readout-v1 (#305)

Separate from #305's fixed-head `research/economic_path_readout_v1/claude-connection.json` (head `d3783d00`, which stays as
it is). Produced by `scripts/run_entry_state_shadow_readout_connection.py` at code commit `61d57508` (see
`connection.json: codeHead / codeSha256`). Three evidence classes, never pooled:

| part | evidence class | what was really computed |
|---|---|---|
| `realInput` | PROSPECTIVE_PAPER shape, **not a signal-history receipt** | the published 2026-10-30 weekly decision (signal-history `f9be595f`, blobs identical to `187aeeda`) and config `37f8cbf6`, recorded by the writer's clock at **2026-11-01T05:44:12Z** (Sunday) into `ledger/` here. Execution session = **2026-11-02** (KR and US), the first session opening after recording. A live vendor fetch served every origin quote (10/30) and nothing after it, so **0 fills, 0 NAV rows**: every strategy is `PENDING_EXECUTION_SESSION`, and the readout reports `NOT_YET_POSSIBLE` rather than a zero return. |
| `historical` | HISTORICAL_DEVELOPMENT | the committed `entry_state_role_etf_residual_v1/nav-daily.csv.gz` through `core.compare`: N=5 both rungs vs 069500.KS / SPY, and QQQ separately. On the KRX∪NYSE grid, so H126/H252 are UNAVAILABLE. |
| `synthetic` | SYNTHETIC | an invented two-week path through the same envelope and core; the calendar verifies as XKRX, and a rerun appends 0 fills / 0 NAV rows. Contract check only. |

`rerun-check.json`: the stored real ledger copied and re-run with the same inputs. 35 receipts already present, 0 appended,
0 conflicts, 0 fills, 0 NAV rows, ledger bytes unchanged.

Envelope (per strategy, `pipeline.entry_state_shadow_ledger.nav_envelope`): region, currency (KRW / USD, local book, no FX),
`calendarPolicy` XKRX / XNYS (regional sessions, not a KR+US common grid), `benchmark.instrument` 069500.KS / SPY / QQQ,
`returnBasis VENDOR_ADJUSTED_CLOSE_FIXED_ORIGIN_RATIO_V1_PREFIX_CHECKED`, `costBasis NET_ALREADY_CHARGED` (each leg once at
fill; the readout deducts nothing), DAILY, sha256 of the three ledger files. Missing price → null, never 0.

Live receipts and fills start only when the hook in `scripts/update_ledger.py` runs in the scheduled ledger workflow on
main (gated by `record_entry_state_shadow.hook_enabled`). This directory does not create, and is not, a live receipt.
Nothing here is evidence of an investment edge.
