# B-H1 prospective outcome contract — owner-review draft

**OWNER_REVIEW_DRAFT_NOT_REGISTERED. All D1–D8 approvals are pending.** This document
freezes recommendations for review, not an authorization. It neither changes nor
registers `rp1-b-h1-state-v1`. The machine-readable proposal is
[`proposals/rp1-b-h1-outcome-v1-owner-draft.json`](proposals/rp1-b-h1-outcome-v1-owner-draft.json).
No production effect, historical strategy execution, new B hypothesis, state
recalibration, workflow dispatch or activation. Independent of PR #289, Market C,
and the industry research lane; all additions have B-H1-specific paths.

## Deadline and evidence

The first LIVE signal is **2026-10-30**, executed at the **2026-11-02 close**.
Execution is session 0; H63 is **2027-02-02**, final at **09:00:00 UTC / 18:00 KST**.
The separately approved outcome contract must be merged **strictly before
2027-02-02T09:00:00Z**. Equality misses the deadline. This is the registered
`prospective_receipt_core.maturity_close_utc` finality clock, not a vendor-row clock.
Plan to merge earlier; holidays/provider failures never extend this deadline.
If missed, this cohort cannot be rescued by a later contract or a shifted origin.

Read-only evidence at signal-history `187aeeda839dd4863bf9432eabb1595581bc7782`:

- `receipts.jsonl`: one LIVE `PROSPECTIVE_PAPER` row, digest
  `9ab0fd5625cc62d072be5e595512fb5123bdb2088060b3cd5c9fb153e2aeb354`.
- Registered state-spec SHA-256:
  `eb480513e2e89b5c10b265c3ddfeeb41987a37b0451481a0408c400ba98784af`.
- Coverage reports `integrity: VERIFIED`, zero matured blocks; outcomes report
  `BLOCKED_OUTCOME_CONTRACT_NOT_REGISTERED`, `computed: false`. Aggregate `OK` means
  recorder process success, never outcome authorization.
- The registered validator independently rechecked the row digest, legs, state,
  timing, calendar, source identity and chain. Frozen code/dependency hashes and
  conformance digest also verified. No raw index rows or stock outcomes were read.
- Receipt first committed at `3532d92f06673f008a4e880fe9e320ce848f9b9c`,
  2026-10-31T05:48:01Z, before the next open. Its anchor
  `6bb0fd4e2a51cec4da7a872de879af3bfd307962` is an ancestor of the observed HEAD.
  The only committed receipt version and current bytes agree. Verification details
  and synthetic smoke counts are in `proposals/rp1-b-h1-outcome-v1-verification.json`.

## Complete D1–D8 decision matrix

Every row is **RECOMMENDED / OWNER APPROVAL PENDING**, including descriptive-only
inference and the finite stopping schedule. None is implicitly approved by this draft.

| ID (registered decision) | Exact recommended definition | Owner decision / deviation |
|---|---|---|
| **D1_ELIGIBLE_POPULATION** | Latest preserved PIT KRX Top120 membership snapshot with snapshot date and original availability strictly before the signal's KST date, from `ledger/universe/kr`; no current membership or rank-121 replacement. Apply Study A's actual `rp1_kr_a0.eligibility`: common share explicitly verified, issuer identity present, exclude FINANCIALS, price as of signal, all 20 KRX sessions ending at signal traded, median traded value over 60 KRX sessions ending at signal ≥ KRW 1bn, dated industry group with ≥5 otherwise eligible members including the name itself. Compute group counts before momentum-window exclusions. Publish every exclusion and denominator. | Approve full Study A inheritance: the short D1 description omitted its financial/identity/five-member rules. Official traded value or a separately approved named basis is required; do not silently use a close×volume proxy. |
| **D2_MOMENTUM_DEFINITION** | Call unchanged `longterm.momentum_12_1` on **273 complete consecutive pinned KRX sessions ending at the signal** (`MIN_HISTORY=273`): literal `close.iloc[-21] / close.iloc[-252] - 1`. With signal at index 0 these endpoints are t−20 and t−251. Prove all 273 slots first; the function's `dropna()` must never compress a window. Exclude a name with any untraded/invalid/missing session; never fill or replace. | Approve literal existing function, not a newly shifted t−21/t−252 formula. Preserve the existing `datafeed.fetch_prices` default: Yahoo auto-adjusted Close as served at signal time, including only then-known actions; no later dividend/action revisions in features. Archive that signal vintage or mark selection unavailable. |
| **D3_SPREAD_CONSTRUCTION** | Rank eligible finite momenta descending, ticker ascending for ties. For N names use k=floor(N/3); first k are long, last k short, middle unused; k=0 means unavailable. Freeze IDs and weights before any outcome join. Each side is equal-weighted at entry and held without rebalance for H63; S_b=mean(R_long)−mean(R_short), gross, KRW, no funding/borrow assumptions or investability claim. Estimand Δ=mean(S_other)−mean(S_adverse), so B-H1 predicts Δ>0. Each block has equal weight. | Approve rounding/tie policy and this gross research comparison. No production short book, benchmark substitution, fitted signal or ranking by future priceability. |
| **D4_RETURN_BASIS_AND_TERMINATIONS** | R_i=TR_i(maturity close)/TR_i(entry close)−1, same named vendor and one timestamped batch manifest for all selected names at the single evaluation. Proposed source: Yahoo Finance chart close + split/dividend events via pinned `yfinance==0.2.65`; gross cash dividends reinvested ex-date, splits once, no dividend double count. Adjustment/event reconciliation and source-use permission are explicit prerequisites; `Adj Close` alone does not prove total return. Preserve batch hash, symbol/issuer mapping, events, basis, entry/exit sessions and exact endpoint evidence. No fallback vendor. Suspended/absent/invalid volume or close at entry or maturity is unpriced; no next traded day, carry, zero, ETF return, exclusion or renormalization. Delisting requires cited dated cash/share consideration: cash earns zero KRW interest from payment to maturity, share exchanges follow the verified ratio and successor dividends/valuation through the same maturity; unresolved economics or dividend basis withhold the paired block and the primary state comparison (p=1). | **Explicit change to the D4 recommendation:** the common §4 two-reading imputation is written for a US S=1 vs S=0 signal, not this four-way signed state/leg contrast. It cannot certify a held portfolio with unresolved consideration under AGENTS. Recommend the stricter missing-selected-name gate; no invented “plausible” bounds or favorable sign claim. Vendor rights/TR certification remain evidence blockers, not owner-waivable data facts. |
| **D5_BLOCK_ORIGIN** | Confirm existing geometry: origin **2026-11-02**, entries at KRX positions 0,63,126,…; each maturity at entry+63. The shared endpoint is a valuation boundary, not an overlapping daily return. Assign the last **scheduled** weekly signal strictly before entry. Use precisely its immutable LIVE receipt. Missing state or selection does not restart, shift or fill the block. Entry/exit are next-session and maturity closes, never signal close. | Approve pending geometry unchanged. No annual/calendar reorigin, nearest available receipt or later favorable state. |
| **D6_INFERENCE** | **DESCRIPTIVE_ONLY_UNCALIBRATED_KR_H63; p_B-H1=1.** Keep Holm α=.05 family (B-H1,B-H2); B-H2 remains p=1 here. Six blocks per state is necessary, not calibration. No CI/p-value/support claim from H21/H126/H252 or US H63. One independent synthetic-only H63 **state-contrast** calibration would be needed for inference; merely adding a horizon to v4's rank-weighted-spread cells does not calibrate this estimator. | Approve descriptive-only for this version. The feasibility smoke below is not formal calibration; any inferential successor needs a separately frozen/approved protocol before outcomes, never an outcome-driven upgrade. |
| **D7_MISSING_WEEKS** | No receipt for exact scheduled week → `unobserved`; receipt with adverse=None → `undetermined`. Neither enters either state. Count and retain all such blocks on the original schedule. No backfill, forward-fill, neighboring state, post-signal input or recomputation. Selection-evidence absence is separately `SELECTION_EVIDENCE_UNAVAILABLE`, not a fabricated state or survivor universe. | Approve missingness accounting separately from the minimum six blocks and outcome-priceability gate. |
| **D8_FIRST_EVALUATION** | One finite prospective schedule, blocks 1–20. At each maturity, after 09:00 UTC, a metadata-only readiness check counts authenticated states; no outcome values. From block 12 onward choose the first boundary at which both compared states have ≥6 matured blocks **with already authenticated signal-time selections**. At that one boundary obtain outcomes once and publish descriptive state means and Δ only if all selected economics are resolved. No interim returns, effect-dependent stopping or subsequent re-look in v1. If readiness never qualifies, close at block 20 (2031-12-16 09:00 UTC) as descriptive/insufficient, p=1, with no outcome download. If outcome basis/priceability blocks that single look, close blocked; no favorable-block substitution. | Approve one-look stopping rule and 20-block cap. The earliest possible 6+6 boundary is **2029-11-23 09:00 UTC** (block 12), not the first maturity. Unknown state proportions and missing selections can delay or prevent it. |

## Signal-time evidence and immutable receipt boundary

The existing receipt contains no stock cross-section or selections. This draft
does not assert that the 2026-10-30 stock population/features are recoverable.
Do not reconstruct them with today's adjusted prices, industry classification or
survivor list. The first receipt remains valid state evidence even if the first
block has no admissible selection evidence.

Before registration, implementation review must prove archived membership,
identity, industry, traded-value and price-feature bytes and their original
availability. A reconstruction from independently preserved pre-signal inputs is
labelled **late selection reconstruction**, never a signal-time selection receipt.
It is admissible only under this separately approved policy and with no post-signal
selection input; without that proof the block is unavailable. This task reads no
real cross-section and performs no reconstruction. A new selection sidecar may be
recorded only under separately approved outcome-contract code, within the existing
signal-close/next-open window, with its own append-only chain and receipt digest.
Never extend or rewrite the original state receipt or its spec in place.

A future LIVE evaluator must derive registration from the exact approved spec's
first-parent main merge, verify its digest, owner decisions, code/runtime/input
pins, deadline, containment and receipt publication ancestry. Caller-supplied
`REGISTERED`, `OK`, `PASS`, calibration summaries and self-rehashed payloads confer
no authority. It must verify every state row and git anchor before using a state,
bind a frozen selection to that row's digest, and check PIT vintages independently
of outcome data. Outcome inputs may include only entry-to-maturity economics,
fetched at the single scheduled look; they must never feed selection or state.
Outcome records are separate and keyed by (contract digest, state receipt digest,
selection digest, entry, horizon); duplicate/conflicting grading is refused.
No writer in this draft touches any ledger or downloads market data.

The draft's `live_gate` is unconditionally closed, even for a forged approval.
Its SYN-only arithmetic probes are not a deployable LIVE evaluator. Existing
`rp1_b_h1_state.outcome_gate` remains blocked; changing its status is rejected.
Thus the verified LIVE path currently cannot evaluate or backfill at all. A future
evaluator's end-to-end provenance gates require separate implementation/review;
these probes do not pretend to verify a component that does not exist yet.

Receipt immutability is enforced against ordinary append/rewrite/truncation by the
registered hash chain and git anchors, not by cryptographic protection from a
repository administrator rewriting all history. The registered force-push limit
still applies; keep the original Actions run `41172346854` digest log independently.

## H63 synthetic feasibility, not certification

The existing approved v4/v5 engine supplies seeded null DGPs, calendar-time
attribution, the SN interval (U1=66.57), and exact Clopper–Pearson calibration
decisions. Reuse that code without changing its sealed specs or results. Its
approved rank-weighted spread is not the tercile **difference of state means**;
the prospective sample is sparse H63 blocks with state imbalance/endogeneity.

`python -m scripts.check_rp1_b_h1_outcome_draft` tests a new independent development
cell family: H63, 120 invented names, 12 blocks, exactly 6 per state, alternating
and clustered states, all six inherited DGPs, 48 replicates/cell, seed 2026103101.
It checks exact additive calendar attribution of the signed state contrast and
calls the unchanged SN interval. It reads only the synthetic protocol and
invented arrays. It neither reads market outcomes nor runs the closed studies.
Development coverage counts are diagnostic, never PASS certification.

Final development coverage was 46–48 of 48 per cell; positive false positives
were 0–1 of 48, with zero undefined intervals. Exact attribution held to floating
precision. An initial development run incorrectly sampled predictors from the
first 12 weekly positions instead of each 63-session block's entry position; its
coverage was 43–48 and positives 0–5. Both diagnostics are preserved in the
verification file with the correction disclosed. Neither run establishes PASS,
FAIL or the sufficiency of six blocks. No formal run, seed search, interval,
threshold or DGP change was made.

For a future inferential protocol, freeze before any formal simulation: exact
273-session original momentum and frozen state function on synthetic histories;
gross compounded total-return buy-and-hold attribution; exogenous and endogenous
prior-market states; state clustering/imbalance; missing-state and selected-name
mechanisms; all inherited null DGPs; the complete stopping rule and calendar depth;
MDE80 in synthetic units and an owner-set effect target. The engine's independent
predictors/additive sums cannot substitute for these checks. A provisional minimum
grid is state counts (6,6), (6,14), (14,6), two orders per pair, six DGPs, plus
endogenous-state/stopping and missingness scenarios. Formal R=8,000 follows v5's
0.5pp precision rule, not this smoke's observed counts; reserve a new seed,
recompute the complete FAIL Bonferroni family, require all registered metrics
(coverage ≥.95, positive FP ≤.05, undefined ≤.05) via existing one-sided CP rules.
No formal seed/protocol is approved here; no formal run was attempted. Any
FAIL/INCONCLUSIVE leaves inference unavailable. No seed search or threshold rescue.

## Review and smallest next step

Review the exact D1–D8 matrix, especially literal momentum indexing, full Study A
eligibility, stricter D4 missingness and the one-look schedule. Record owner
decisions in a separate approval change; then prepare a separately reviewed
`rp1-b-h1-outcome-v1` spec/code package and merge before the deadline. A merge of
this **draft** alone does not register outcomes. The smallest next step is owner
approval/amendment of D1–D8 with **D6=DESCRIPTIVE_ONLY**, followed by an outcome-free
archive/PIT feasibility check for the first block. Until then the LIVE outcome
status stays `BLOCKED_OUTCOME_CONTRACT_NOT_REGISTERED`.
