# kr-alpha-discovery-tournament-v1 — post-outcome integrity audit

**POST-OUTCOME FORENSIC DIAGNOSTIC. NOT CONFIRMATORY. NOT A RERUN.** The formal development execution is consumed and sealed. This audit changes
no model, target, hyperparameter, recency rule, allocation, cost assumption or data exclusion. It does not touch either execution lock or the sealed
result, and it does not reinterpret the frozen verdict `BLOCKED_BY_DATA_INTEGRITY`. Every number in it is post-outcome forensic evidence about why
paths were incomplete, and nothing else.

## Identities verified (read-only)

| | |
|---|---|
| Latest `main` at audit start | `ad526f28ecae7a6c63b9825afda97c9eb7363f2a` (verified with `git fetch`; equals the handoff value) |
| Formal execution | run `37535814142`, `execute` job `success`, commit `eac50fdf725ac797e5c37044246e2a7ffa9b1e64` |
| Spec SHA-256 | `a8acb44c4b685e06ce7692e44461147110e2e2d32a119adef0dd216476f50e7f` |
| Result artifact | `kr-alpha-discovery-tournament-v1-results-37535814142`, id `11449586098`, `sha256:2079eb4a…ae85` (from the seal provenance and the run's log) |
| Sealed result | `docs/results/kr-alpha-discovery-tournament-v1-result.json`, SHA-256 `4a117ed2…cc5d` (recomputed; matches) |
| Raw input | `kr-model-raw-inputs-36844599518`, id `11157875265`, `sha256:42eeb18b…cce7`, input identity `233df37e…66a7` |
| Locks | both `refs/tags/kr-alpha-discovery-tournament-v1-execution-lock*` are recorded in the seal provenance; the audit workflow re-checks them read-only |

## What the sealed bytes can and cannot answer

`kr_alpha_tournament_portfolio.replay` returns `{"complete": False, "reason": "<PORTFOLIO_MARK_OR_TERMINAL_ECONOMICS_UNRESOLVED>: <ticker>:<day>"}`
for an incomplete path. `kr_alpha_tournament_study.assemble` keeps only the boolean. The run's job log prints only the final verdict line. So the
first failing ticker and session of each incomplete path are recorded **nowhere**: not in the committed result, the manifest, the marker or the
log. They exist only in a re-run of the frozen process. That re-run needs the raw-input artifact, whose KRX market-value store is not in git, and
this authoring environment cannot download Actions artifacts. The audit therefore has two evidence classes, which are never blended:

* **`POST_OUTCOME_MODEL_FREE_DATA_SCAN`** — computed here from the replay-v16 price panels and the PIT Top120 membership on `signal-history`
  (commit `f714d1aa`). The objects are read through `replay_inputs.InputStore` against the manifest digest `f0781292…` that the formal run's
  `load_sources` requires, and each universe shard is checked against its pinned git blob. Committed as
  `docs/results/kr-alpha-discovery-tournament-v1-postoutcome-integrity-audit-model-free-scan.json`. It needs no model and no forecast.
* **`POST_OUTCOME_FORENSIC_RECONSTRUCTION`** — `pipeline/kr_alpha_tournament_postoutcome_integrity_audit.reconstruct`, run by
  `.github/workflows/kr-alpha-discovery-tournament-v1-postoutcome-integrity-audit.yml` on the exact raw-input artifact. It replays the frozen
  functions with tracing wrappers that return exactly what they wrap; a test shows the traced path loop gives byte-identical paths and counters to
  `run_paths`. It attributes nothing unless it first reproduces the sealed `complete`, `paths`, `process`, `prediction`, `evidence`, `verdict` and
  counters (floats within 1e-9); otherwise the status is `RECONSTRUCTION_MISMATCH` with the first divergence. **Not yet run.**

## Established now (model-free scan)

Over the formal replay window — 2,116 KR sessions from the first outer anchor `2018-01-29` to the cutoff `2026-09-14`, 101 outer anchors, 218 names
in the PIT Top120 at some outer signal:

1. **The benchmark 069500.KS has a close on every session.** No path can have failed on the passive leg.
2. **No Top120 name has a mid-series price gap.** Every missing close inside the window comes after a name's last trading date.
3. **Exactly eight terminal end-of-series events fall inside the window, and all eight names are in the 22-name terminated-security inventory.**
   Each is preceded by a pre-delisting **trading suspension** of 12 to 22 sessions: the replay close stays unchanged, with zero volume and zero
   open, high and low.

| Ticker | Name | Suspension starts | Last priced | First unpriced | Last outer anchor before suspension (signal) | Outer anchor during suspension | Termination (reconstruction-v2) | Terminal consideration | Terminal action chain |
|---|---|---|---|---|---|---|---|---|---|
| 000030.KS | 우리은행 | 2019-01-09 | 2019-02-12 | 2019-02-13 | 2018-12-07 (2018-11-30) | 2019-01-10 | SHARE_TRANSFER | BLOCKED | BLOCKED |
| 079440.KS | 오렌지라이프 | 2020-01-22 | 2020-02-13 | 2020-02-14 | 2020-01-20 (2020-01-17) | — | SHARE_EXCHANGE | BLOCKED | BLOCKED |
| 000060.KS | 메리츠화재 | 2023-01-30 | 2023-02-20 | 2023-02-21 | 2023-01-09 (2023-01-06) | 2023-02-09 | SHARE_EXCHANGE | READY | BLOCKED |
| 008560.KS | 메리츠증권 | 2023-04-03 | 2023-04-24 | 2023-04-25 | 2023-03-13 (2023-03-10) | 2023-04-11 | SHARE_EXCHANGE | READY | BLOCKED |
| 003410.KS | 쌍용C&E | 2024-06-21 | 2024-07-08 | 2024-07-09 | 2024-05-24 (2024-05-17) | 2024-06-25 | CASH_SHARE_EXCHANGE | READY | BLOCKED |
| 010620.KS | HD현대미포 | 2025-11-27 | 2025-12-12 | 2025-12-15 | 2025-11-13 (2025-11-07) | 2025-12-12 | MERGER_STOCK | READY | BLOCKED |
| 042670.KS | HD현대인프라코어 | 2025-12-29 | 2026-01-23 | 2026-01-26 | 2025-12-12 (2025-12-05) | 2026-01-15 | MERGER_STOCK | BLOCKED | BLOCKED |
| 012510.KS | 더존비즈온 | 2026-06-26 | 2026-07-14 | 2026-07-15 | 2026-06-23 (2026-06-19) | — | CASH_SHARE_EXCHANGE | READY | BLOCKED |

The first six were in the PIT Top120 at the last outer signal before their suspension. A fresh decision could therefore have bought them. 042670.KS
last ranked in the Top120 in 2023-08 and 012510.KS in 2021-10, so a path could hold either only by carrying it from a much earlier decision. A held
name without a current eligible forecast is targeted to 0 whenever it is executable, which makes that unlikely; only the reconstruction can say.
The inventory's `lastTradingDate` equals the scan's last priced session for all eight (a test checks this).

## The mechanism (from the frozen code, established)

* `kr_integrated_alpha_portfolio_replay.mark_price` returns the observed close. If there is none, it carries the previous mark only when KRX shows a
  zero-volume quote for that session. Otherwise it raises `PORTFOLIO_MARK_OR_TERMINAL_ECONOMICS_UNRESOLVED`.
* The tournament ledger marks every held name at the start of each session, before any trade. A held name is traded only when it has a
  positive-volume KRX quote and an ADV; otherwise it is **deferred** and stays held at its drifted weight.
* The tournament ledger has no terminal-economics path: no consideration, successor or cash-out. The terminal foundation it would need is
  `PARTIALLY_REPAIRED`, with the terminal action chain BLOCKED for all eight names.

So a name held when its suspension starts **cannot be sold**: every rebalance during the suspension defers it. On its first unpriced session there
is no close, and, as the formal run's failure shows, no zero-volume quote to carry. The path stops there. Because the benchmark is complete and no
mid-series gap exists, **the first failure of every incomplete path must be one of the eight sessions in the "First unpriced" column**, by this
mechanism. Classification: **expected conservative behaviour of the registered rule** ("a held name without an observable mark blocks the path"),
meeting an unresolved terminal foundation. The audit found no defect in `mark()` or in the ledger. Two observations sit beside that verdict:

* **The process could not have known.** No registered information class carries a corporate-action or delisting announcement (DART events were
  excluded as not PIT-ready). The terminal label rule (`terminal_ineligible`) is a hindsight LABEL rule that the decider never reads.
* **This is a design gap, not a mark bug.** The frozen ledger has no way to exit a position during a pre-delisting suspension and no way to settle
  it at termination. Any long-only path that holds a terminating Top120 name into its suspension will be blocked under this foundation.

## Q1 — the first failure of each incomplete path

| Path | First failing session | Ticker | Held weight before | Entry / last trade | Mark reason | Mechanism | Known at signal? | Expected or bug |
|---|---|---|---|---|---|---|---|---|
| DECISION_FOCUSED_CHALLENGER:BASE | pending reconstruction | one of the eight above | pending | pending | `PORTFOLIO_MARK_OR_TERMINAL_ECONOMICS_UNRESOLVED: <t>:<d>` | terminal end of series after a trading suspension | not available to the process | expected conservative behaviour (unless the reconstruction shows otherwise) |
| PRIMARY_ROBUST_KELLY:BASE | pending | " | pending | pending | " | " | " | " |
| PRIMARY_ROBUST_KELLY:EXECUTION_DELAY_ONE_SESSION | pending | " | pending | pending | " | " | " | " |
| PRIMARY_ROBUST_KELLY:LIQUIDITY_HAIRCUT_HALF_ADV | pending | " | pending | pending | " | " | " | " |

The reconstruction fills every column for every incomplete path, not only the first. For each path it reports: the first failing session and
ticker; the exact `mark()` reason; the whole held book immediately before the failure (taken from the ledger's own `weights`); the entry trade, the
entry signal, the last weight-changing trade and every deferred sale during the suspension; the decision targets since entry; the KRX quote on the
failure session and on the last priced session; the terminal window and foundation status; the signal-time `tradable` flag; and whether the
hindsight label rule withheld that signal's label. It also gives a terminal-exposure table: every path's held weight in every terminal name at the
suspension start and on the last priced session.

## Q2 — why COST_X2 completed

Established: the benchmark is complete and there are no mid-series gaps. COST_X2 completing therefore means it held **none of the eight names** on
its first unpriced session. Not yet established: whether it never bought the name a BASE path was trapped in (the doubled hurdle of 2 × 0.9% round
trip), or bought and sold it before the suspension. `cost_x2_explanation` reports, for each failure ticker:
* COST_X2's held weight on the failing session and on the suspension start;
* whether, and when, it ever entered that name;
* its decision target at the anchor where the failing path entered, beside BASE's target there;
* its last weight-changing trade.

## Descriptive observation from the sealed bytes (not part of Q1/Q2)

`BASELINE_1_EQUAL_WEIGHT_SLEEVE:BASE` is complete and **identical to the 100% passive path**: 0 active names on every one of 2,116 sessions. Its
admission rule is the primary's own arithmetic, `mu_post > cb + cs` = 0.9% round trip. **No name's shrunk expected incremental return ever cleared
its round-trip cost at any anchor.** The primary paths still held active weight (COST_X2: mean 42.1% active, 14.7 names, annual volatility 18.3%
against the passive 27.6%). That weight therefore depended at least partly on the allocator's covariance terms (`−c_eb` and `Σ`), not on a
forecast that paid its own cost. This is recorded as a fact about the sealed result. It is not a reinterpretation of the verdict, and this audit
computes no decomposition of it.

## Next step

Merge this Draft PR (a human decision) so that GitHub lists the workflow, then dispatch
`KR alpha discovery tournament v1 post-outcome integrity audit` with `audit_ref` = this PR's head SHA. The session that authored this PR cannot
dispatch workflows (its token is refused with HTTP 403). The run prints both audit files to its job log, gzip + base64, so a later change can
commit a compact, hash-referenced record and fill the "pending" cells above. Do not rerun the formal workflow.
