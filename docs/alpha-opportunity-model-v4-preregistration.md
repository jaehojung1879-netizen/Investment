# Alpha opportunity model v4: sealed preregistration (KR-only)

**Status: `READY_FOR_HISTORICAL_EXECUTION` at the study-DESIGN level.** Spec
`research_specs/alpha-opportunity-model-v4.json`, seal in the adjacent
`.sha256`. **The KR terminal-action source foundation this study depends on
remains `PARTIALLY_REPAIRED`** (`docs/results/kr-terminal-action-
reconstruction-v2.json`, unchanged, unedited by this PR) — see §1 for why
these are two different facts, not a contradiction. No historical label,
return, IC, calibration table, model fit or portfolio path was computed for
this study. There is deliberately no v4 execution harness:
`scripts/run_alpha_opportunity_model_v4.py --execute` refuses
unconditionally, regardless of readiness, because this PR builds no label
engine, training loop or evaluation code — only the preregistration and the
machine-checked policy a future execution PR must follow exactly.

## Lineage

| Version | What it is | Status |
|---|---|---|
| `alpha-opportunity-model-v1` | first opportunity preregistration | `BLOCKED_PREREGISTRATION`, never executed |
| `alpha-opportunity-model-v2` | benchmark-as-outside-option redesign | sealed `READY`, never historically executed |
| `alpha-opportunity-model-v3` | separates expected value from probability/confidence; audits identity and survivorship in both regions | `BLOCKED_BY_DATA_INTEGRITY` in both regions, never executed |
| `kr-terminated-security-total-return-foundation-v1` | data-foundation build (no live DART access in that environment) | `BLOCKED_BY_SOURCE_ACCESS` |
| `kr-terminal-action-reconstruction-v2` (PR #158, merged) | real DART evidence collected and reconstructed | `PARTIALLY_REPAIRED`; every evidence-recovery route in this environment confirmed exhausted |
| **`alpha-opportunity-model-v4`** | **this preregistration**: KR-only, carries v3's economic contract forward unchanged, adds a predeclared eligibility policy | `READY_FOR_HISTORICAL_EXECUTION` (design), source foundation `PARTIALLY_REPAIRED` |

v1, v2 and v3 are unchanged. v4 checks all three by their own spec digests
and sidecars, never through their dependency lists (`pipeline
.alpha_opportunity_v4_spec.verify_prior_versions`). v4 is never unblocked by
editing v3, and no alpha outcome is read here.

## 1. Three layers, never conflated

This is the central design decision of v4, and it directly resolves a real
conflict in this repository's own prior documents (§2 below).

| Layer | What it answers | Where it lives | Current value |
|---|---|---|---|
| **Source foundation** | Has the underlying DART/dividend/terminal-action evidence actually been collected and resolved? | `docs/results/kr-terminal-action-reconstruction-v2.json`'s own `foundationStatus`, computed by `pipeline.kr_termination_inventory.foundation_status` | `PARTIALLY_REPAIRED` — unchanged, never edited by this PR |
| **Study design** | Does a study exist that predeclares, for every possible gap in that foundation, exactly what a future execution may and may not do — with zero discretionary choices left for later? | `research_specs/alpha-opportunity-model-v4.json`'s `preregistrationStatus`, computed by `pipeline.alpha_opportunity_v4_spec.preregistration_status` | `READY_FOR_HISTORICAL_EXECUTION` |
| **Execution** | Has a label been built, a model fit, a return read? | This PR | Not started. No harness exists. `--execute` always raises. |

A study can be `READY_FOR_HISTORICAL_EXECUTION` while its source foundation
is `PARTIALLY_REPAIRED` precisely because "ready" here means "the treatment
of every known gap is decided, deterministic, and machine-checked" — not
"the gap is gone." `pipeline.alpha_opportunity_v4_eligibility` is that
treatment: a pure function of the sealed completeness matrix that answers,
for any (security, date, horizon), ELIGIBLE or INELIGIBLE-with-a-stable-
reason-code, never a hardcoded list of names.

## 2. A real conflict with two prior documents, stated rather than hidden

`docs/kr-terminated-security-total-return-foundation-v1.md`'s "Exact next
step" (§5) and `docs/kr-terminal-action-reconstruction-v2.md`'s (PR #158)
final determination both state, in their own words, that a v4
preregistration should be drafted **only once every applicable
completeness-matrix field reads READY**, "never before, and never by
loosening this matrix's own rules," and that the one remaining operator
action was a workflow retry, not a v4 draft.

That retry has now been run and is confirmed exhausted (§3). There is no
further repair action available in this environment: every evidence-
recovery route (direct HTTPS, `WebFetch`, `workflow_dispatch` with a real
token) was already exhausted by PR #158 itself, and this PR's own retry
reproduced the identical 38-of-38 failure with the identical error. This
PR's governing task requires a v4 preregistration now, built on a new
study-level eligibility-policy concept the prior documents did not
contemplate. The conflict is resolved, not silently overridden, by:

1. **Never editing** `kr-terminal-action-reconstruction-v2.json`'s
   `foundationStatus` — it stays `PARTIALLY_REPAIRED`, exactly as PR #158
   left it, and v4's own loader (`verify_source_foundation`) raises if that
   file's hash or its quoted status ever disagrees with what v4 cites.
2. Introducing the three-layer distinction in §1, which the prior documents'
   binary "wait for READY" framing did not have room for.
3. An eligibility policy that **excludes** affected observations by a
   computed rule — it does not repair, bound, or paper over the underlying
   gap, and it does not loosen a single field in the completeness matrix.

Both prior documents' instruction to wait for full repair was correct given
what they knew; this document does not claim they were wrong, only that the
retry they named as the remaining step has since been run and the picture
has changed from "one more thing to try" to "nothing more to try in this
environment."

## 3. The final retry, verified directly

GitHub Actions run
[`36264244053`](https://github.com/jaehojung1879-netizen/Investment/actions/runs/36264244053)
("Collect KR terminated-security corporate actions", `workflow_dispatch`,
`mode: collect`, triggered 2026-09-26T18:55Z on `main` at PR #158's merge
commit `68c950d9f2fbd05fcb76b36bd714b236e2b33850`) was read directly from
its own job logs, not assumed from a prior summary:

- **`collect` job** (disclosure index): logged `no new disclosures` — already
  complete at 22/22 securities, 451 rows.
- **`collect-dividends` job**: logged `no new dividend rows` — already
  complete at 47/47 tickers, 6,150 rows.
- **`collect-documents` job**: retried exactly the 38 previously-failed
  receipts against live DART with the real `DART_API_KEY` secret —
  ```json
  {"callBudget": 200, "calls": 38, "datasetComplete": true,
   "fullWorkListExhausted": true, "outcome": "EMPTY_BUT_VALID",
   "receiptsFailed": 38, "receiptsRemaining": 0, "receiptsRequested": 130,
   "receiptsSucceeded": 92, "stopReason": "WORK_LIST_EXHAUSTED", "written": 0}
  ```
  All 38 failed again with the same retained error (`document.xml did not
  return a ZIP (147 bytes)`). Signal-history commit
  `2132d8d83589ddc8ee6c0e640016211c8ebc65f0` (1 file changed, 38 insertions,
  38 deletions) refreshes retry/failure bookkeeping only — no new document
  was recovered, and this is not read as 38 new documents.

This closes the repeated-DART-retry loop. `docs/results/kr-terminal-action-
reconstruction-v2.json` is unchanged by this run (its own content hash is
identical to PR #158's committed value,
`b1d2dcb0a8064139e601c4efab51a44e1323f93910ae70228054338a90629017`) and
stays `PARTIALLY_REPAIRED`.

## 4. Scope: KR-only, and why

The US leg has a **structurally different** survivorship defect:
`NO_TERMINATED_SECURITY_IN_SAMPLE` — the sealed price panel never priced
212 of 324 departed S&P 500 identities **at all** (0% coverage), so
termination is entirely invisible, not merely basis-inconsistent. There is
no source available to this repository (per `docs/alpha-opportunity-v3-
data-repair-plan.md`'s own vendor survey: FMP and Polygon paid-plan-only,
stooq bot-walled, finnhub unusable with the current key) that would fix
this without a human paid-vendor decision. This PR does not wait for that,
does not repair it, and does not silently touch it:
`alpha-research-philosophy-v2` §1 already states that treating US and KR as
"one model, or as two models forever" is not required, and
`regional-alpha-research-separation-v1` split the two regions before this
PR existed.

KR's own remaining gap is narrower and of a different kind: KR's price
panel prices **all 260** historical members, including all 22 that
terminate — the gap is a total-return **basis** problem (missing dividend
ex-dates for those 22), not a missing-security problem. That is exactly
what §5's eligibility policy is built to bound.

**Benchmark, verified from the actual repository, not assumed:**
`config.json`'s `benchmarks.KR` is `069500.KS` (KODEX 200), a KOSPI 200
tracking ETF explicitly chosen over the `^KS200` price index because the
index excludes constituent dividends
(`config.json`'s own `_notes` field, `pipeline/rotation.py:32`,
`pipeline/regional_alpha_features.py:29`). It is priced through the
identical `pipeline.korea_prices` total-return pipeline every KR stock
uses — "an ETF is quoted like any listed name," per that same note — so the
benchmark side of this study carries no basis inconsistency of its own.

**KR universe**: the same strictly-earlier KRX top-120-by-market-cap PIT
universe v1-v3 already used (`tradabilityGuard.universeFloor`), read from
the sealed monthly snapshots under `ledger/universe/kr/`, never today's
membership backfilled onto the past.

## 5. The eligibility policy (the core of this preregistration)

`pipeline/alpha_opportunity_v4_eligibility.py`. Reads no price, return or
label — only the already-sealed completeness metadata in `docs/results/kr-
terminal-action-reconstruction-v2.json`.

### Why a security-level gate, not only a terminal-window gate

Production's KR price panel (`pipeline/korea_prices.py`) takes
distributions from Yahoo "if Yahoo happens to carry the name" — and Yahoo
serves **zero** of the 22 terminated securities' distributions (`alpha-
opportunity-model-v3`'s sealed survivorship audit: 0 of 22 terminated names
have any dividend event, against 215 of 238 continuing names). That is not
only a problem for the forward window that crosses termination: it means
**every session** of these 22 securities' trading life — not only the
final one — is on a price-return basis, while the matched benchmark and
every continuing name are total-return. A window entirely before
termination is not automatically clean.

The predeclared rule therefore gates the whole security first:

1. **`exDateSemanticsResolved` must read `READY`** in the sealed
   completeness matrix before *any* observation on that security is
   eligible — pre- or post-termination. Measured directly: this field is
   `BLOCKED` for **all 22 of 22** securities today (verified by re-reading
   `docs/results/kr-terminal-action-reconstruction-v2.json` in this PR).
   `exDateSemanticsResolved` reads `READY` only when a security's dividend
   evidence states `exDateSource: "DIRECT"` — an ex-date DART's own
   disclosure stated outright. No sealed, dated Korean settlement-cycle
   rule exists anywhere in this repository to derive one from a record
   date, and none is invented here.
2. Even if resolved, an actual total-return series must have been
   **reconstructed and spliced** into the price panel used to build labels
   — a separate, not-yet-built engineering step this preregistration does
   not perform (`TOTAL_RETURN_SERIES_NOT_YET_BUILT`).
3. **Only if both hold**, a window entirely before the security's last
   traded session is eligible.
4. A window whose exit session is **after** the last traded session
   additionally requires `terminationTypeResolved`,
   `terminalConsiderationResolved`, `successorResolvedWhereRequired`
   (where the resolved type requires a successor) and
   `terminalActionChainResolved` all `READY`, and — where a successor is
   required — that successor's own price panel. Measured: `terminal
   ActionChainResolved` is also `BLOCKED` for all 22 today, so this
   condition is never reached in practice; it exists so a future partial
   repair (e.g. one security's ex-date lineage resolved without its
   terminal consideration also being finalised) is still handled correctly
   without a new preregistration.

### This is computed, not hardcoded

Every function takes the completeness row as an argument. Running
`scripts/audit_alpha_opportunity_v4_kr_eligibility.py` against the real,
already-sealed evidence (input-only: two JSON reads, one JSON write, no
price, no return) produces `docs/results/alpha-opportunity-model-v4-
eligibility-policy.json`, committed alongside this spec:

```json
{"securitiesEvaluated": 22, "eligibleTodaySecurityLevel": 0,
 "ineligibleTodaySecurityLevel": 22,
 "reasonCounts": {"KR_TERMINATED_SECURITY_DIVIDEND_EXDATE_LINEAGE_UNRESOLVED": 22}}
```

All 22 known-terminated securities are excluded from v4's labeled sample
today, for exactly one reason, computed rather than asserted. If a future,
separate data-foundation PR resolves a specific security's ex-date lineage
(never inferred, never derived from a record date) and splices a real
total-return series for it, the **same function, unmodified**, would admit
that security's pre-termination observations without a new preregistration
— the policy is reusable across the repair, not a one-time filter tuned to
today's gap.

### What this policy never does

- Treats an unresolved exchange ratio or successor as final.
- Carries the last traded price forward through a termination.
- Invents an ex-date from a record date or any other computed rule.
- Assumes zero recovery for an unresolved termination.
- Excludes or includes an observation based on its own realised return
  magnitude.
- Uses today's KR universe membership as a historical one.
- Invents a new exclusion rule after an outcome is seen — every reason code
  in `pipeline.alpha_opportunity_v4_eligibility.REASON_CODES` is frozen by
  this seal.

### A known, disclosed, bounded consequence — not the same defect as US

Excluding all 22 securities' labels entirely raises a fair question: does
this recreate the same "the sample never observes termination" defect v3
found unrepairable in the US leg? **No, and the difference is measured, not
asserted.** In the US case, the panel never priced 212 of 324 departed
identities *at all* — termination was structurally invisible, 0% observed.
In KR, all 22 securities *are* priced right up to their last session, *are*
members of the PIT universe on their live dates, and *do* still enter
feature computation and cross-sectional ranking context — only their own
forward-return **label** is withheld. The affected share is disclosed and
bounded: `alpha-opportunity-model-v3`'s sealed audit measured 3.7366% of
tradable KR member-dates, front-loaded at 7.93% in 2013 and declining to
0.76% by 2025 (never zero, so no cutoff here would be structural — this is
exactly why it is handled by an eligibility rule rather than a coverage
tolerance).

This is still a real, disclosed limitation: v4's labeled sample never
observes the realised forward outcome of a name that is about to be
delisted or merged out, which understates tail risk relative to the true
investable universe. The future execution's evaluation report **must**
publish `exclusionsClusterAroundTerminalEventsCheck` (§7) quantitatively,
and any headline result must be read alongside this caveat, never as an
unconditional statement about KR delisting risk.

## 6. Economic contract — carried forward from v3, KR-only

Nothing below is a new design decision; each item is v3's own KR leg,
narrowed to one region, with no feature, hyperparameter or horizon change,
and re-verified that no feature is PIT-unsafe.

- **`expectedNetAlpha = E[R_i - R_benchmark] - roundTripCost_i`.**
  `POSITIVE_EXPECTED_ALPHA` iff `expectedNetAlpha > 0` against the KR
  benchmark's own outside-option value of exactly 0, cost exactly 0.
  `BENCHMARK_EXPECTED_VALUE_PREFERRED` / `NOT_TRADABLE` / `UNMEASURED`
  otherwise. No probability hurdle, no lower-bound hurdle — both stay
  descriptive-only, per v3's own correction of v2's hidden hurdles.
- **No Top-N, no quota, no invested fraction, no sizing field.** The spec
  loader (`pipeline.alpha_opportunity_v4_spec.load_sealed`) refuses a spec
  that reintroduces any of v3's `FORBIDDEN_DECISION_PARAMETERS`, reused
  unchanged rather than re-declared.
- **Horizons 21 and 126 sessions**, kept separate, never averaged.
- **Targets**: entry = next KR regional session close after the
  information date; exit = `horizon` further sessions; exact endpoints
  only. `MISSING_FORWARD_PRICE_OR_DELISTING` for an ordinary gap; a
  *different* reason code (`DATA_UNAVAILABLE_UNDER_PREDECLARED_POLICY`, via
  §5's policy) for one of the 22 terminated securities, because the failure
  mode is a basis gap, not a missing row, and collapsing the two would hide
  which one happened.
- **Model family**: linear primary (Ridge for expected return, Logistic for
  P(net outperform)), plus a fixed shallow HistGradientBoosting complement
  that is never a decision, never a rescue — exactly v3's config, reused
  byte-for-byte (`carriedFromV3.models` in the spec).
- **Features (KR, carried from v3 unchanged)**: 21D —
  `relative126`, `acceleration21`, `vol63`, `logVolumeShock60`,
  `shockPersistence5d`, `volumePriceAlignment` (price/momentum and
  magnitude-preserving liquidity/attention, per `alpha-data-foundation-v2`
  workstream B). 126D adds `ocfToNetIncomePct`, `assetGrowthPct`,
  `debtGrowthPct` (workstream A, KR coverage 52-97%). Deliberately excludes
  `capexIntensityPct` (7.74% KR coverage) and `fcfToNetIncomePct` (4.31%) —
  not promoted merely because they exist, per this study's own philosophy
  and workstream A's own finding.
- **Transforms**: `signedLog1p` on the three accounting fields;
  date-weighted training median/IQR scaling; training-median imputation
  with missingness indicators; **no blanket cross-sectional percentile
  transform** — magnitude is preserved on the price/liquidity features by
  construction (`logVolumeShock60` is explicitly a log-magnitude field, not
  a percentile, per workstream B's own "2x vs 15x" argument).
- **Zero new interactions** (§7 — `newInteractions.count: 0`, with
  rationale).
- **Transaction costs**: KR's existing dated schedule
  (`benchmark_alpha.REALISTIC_COSTS` via `portfolio_validation
  ._dated_cost_policy`) — commission 1.5bp, spread 8bp, and the sell-tax
  schedule already in force (30bp in 2013 down to 15bp in 2025, 20bp from
  2026), unchanged and un-invented.
- **Tradability guard**: PIT KR top-120 member, positive finite close and
  volume on every one of 20 preceding sessions — v1's sealed window,
  volume as traded/not-traded evidence only, never a cash ADV.
- **Uncertainty**: 200 training-only moving-block bootstrap refits (fitted-
  value sampling uncertainty) plus past matured out-of-fold RMS
  (predictive outcome dispersion) — two different objects, kept apart, per
  v2/v3's own discipline.

## 7. Evaluation — predeclared now, executed later

Claims A-E are v3's own KR-leg design (absolute calibration, ordering,
probability calibration, the outside-option test on positive-predicted
names, and stability across chronological halves), unchanged. **F is new**:

**F — missingness/survivorship integrity.** Before any of A-E may be
*interpreted*, the execution report must publish every one of:

- `pitUniverseObservationsByYear`
- `eligibleLabelsByYearAndHorizon` (21D and 126D separately)
- `unavailableLabelsByReasonCode` (using `pipeline.alpha_opportunity_v4_eligibility.REASON_CODES` plus `MISSING_FORWARD_PRICE_OR_DELISTING`)
- `terminatedVsContinuingLabelAvailability`
- `memberDatesRemovedPctByReasonAndYear`
- `temporalConcentrationOfMissingness`
- `securityConcentrationOfMissingness`
- `exclusionsClusterAroundTerminalEventsCheck`
- `benchmarkCoveragePct`
- `totalReturnComparabilityCoveragePct`

A report missing any one of these is not a partial result — it is
`DATA_INSUFFICIENT` for every downstream claim. No post-hoc tolerance may
be chosen after seeing these numbers; they are diagnostics, not knobs.

**Multiplicity**: Bonferroni across the two horizon claims (21D, 126D):
two-sided tail 0.0125, 97.5% two-sided intervals — half of v3's four-claim
correction, since KR-only halves the claim count.

**Verdict vocabulary** (v3's own, reused because it already covers
failure): `PIT_INVALID`, `MODEL_UNSTABLE`, `DATA_INSUFFICIENT`,
`POSITIVE_EXPECTED_ALPHA_EVIDENCE`, `PREDICTIVE_EVIDENCE_BENCHMARK_
PREFERRED`, `NO_MODEL_EVIDENCE`. None guarantees success; `promotionEligible`
is hardcoded `false` in every evaluation artifact this design permits.

## 8. Excluded information families, verified rather than assumed

| Family | Status |
|---|---|
| KR investor-type flow | `pipeline/kr_investor_flow.py` exists; access unproven from a real network (Grade B REPAIRABLE); excluded |
| KR short-selling | `pipeline/kr_short_selling.py` exists; same status; excluded |
| KR ownership events (5%-rule) | `pipeline/dart_ownership_events.py` exists; `BLOCKED_HISTORICAL_DEPTH` — `majorstock.json` serves only a rolling ~2-year window, unusable for a 2013-2026 study |
| KR macro context | No KR axis in `regime.py` (every `INDICATORS` entry is FRED/CBOE); `pipeline/ecos_macro.py` is an unwired fetch layer, vintage status `REVISED_HISTORY` not `PIT_EXACT` even if wired; excluded |
| Guru/13F | Separate track; never an alpha feature |
| Analyst estimate revisions | No stable 2013-2026 PIT panel established in either region |

## 9. Zero new interactions, and why

Section 11 of this study's own governing task requires any interaction to
be selected on economic mechanism, PIT availability, coverage and
manageable multiplicity — never on outcome data. The one candidate that
needs investor-flow confirmation is excluded above as access-unproven. The
remaining candidates (fundamental state/change × liquidity shock; price
leadership × liquidity persistence; weak fundamentals × liquidity shock;
attention × price-leadership divergence) all combine the same small,
already-carried-forward KR feature set that v1-v3 never found PIT-unsafe
but also never tested in combination. Rather than add an untested
interaction term to a preregistration whose purpose is closing a
data-integrity gap, v4 carries v3's model family unchanged — the shallow
HGB complement can already surface such an interaction as complementary
evidence (never a decision) without this spec committing to one by name. A
dedicated interaction study, if warranted, is a separate preregistration.

## 10. Time / PIT design — carried from v3

Expanding-history annual refit, first KR weekly signal date each calendar
year; prediction on the last KR session each week; maturity requires
`outcomeEndDate` strictly before the fold cutoff (a label that has started
but not matured is unavailable to training, never partially credited);
exact-endpoint purge, no extra embargo; KR accounting features dark
2013-2014 (DART serves from 2015, per the PIT-fundamentals invariants),
evaluation gate applies from 2016; frozen seed 42 throughout, identical to
v1-v3.

## 11. Dependency closure

Computed on every load (`pipeline.alpha_opportunity_v4_spec.load_sealed`),
never hand-listed: the top-level-and-lazy pipeline-import closure of three
entry points (`scripts/run_alpha_opportunity_model_v4.py`,
`scripts/audit_alpha_opportunity_v4_kr_eligibility.py`,
`pipeline/alpha_opportunity_v4_eligibility.py`) plus declared data inputs
(v1/v2/v3 specs and sidecars, the v3 survivorship audit, the KR terminal-
action reconstruction and inventory artifacts, the terminal-actions book,
`requirements.txt`). `kelly_portfolio`, `longterm`, `replay_valuation`,
`selection_null` and `portfolio_validation` are not in the closure —
editing them changes nothing here, exactly v3's own discipline.

`verify_source_foundation` additionally checks that every cited
source-foundation artifact's hash AND its quoted status still match the
file on disk — a source foundation that improves *or* regresses after this
seal both raise, because either would mean this spec's own quoted fact is
stale.

## 12. Self-audit (see also the PR description)

- No future return, label, IC, quintile spread, CAGR, Sharpe, Sortino or
  hit rate was computed anywhere in this PR (checked by
  `tests/test_alpha_opportunity_v4.py`'s forbidden-token tests, mirroring
  `test_kr_data_foundation_guardrails.py`'s existing discipline).
- No model was fit; no coefficient was inspected; no portfolio was
  backtested.
- `alpha-opportunity-model-v1/v2/v3` reload byte-identical
  (`test_v1_v2_v3_seals_unchanged`).
- `kr-terminal-action-reconstruction-v2.json`'s `foundationStatus` was read,
  never edited, and stays `PARTIALLY_REPAIRED`
  (`test_source_foundation_is_pinned_and_still_partially_repaired`).
- The 38 failed DART receipts were not silently treated as successful —
  `written: 0`, `receiptsFailed: 38`, quoted verbatim in `citations`.
- No zero terminal recovery was inferred; no ex-date was invented; no
  survivor-only universe was introduced (§5's "known, disclosed, bounded
  consequence" section states precisely why this differs from the US
  defect); no outcome-dependent threshold was introduced anywhere in this
  design.
- `ruff check .`, `python -m compileall pipeline scripts`, full `pytest -q`
  (2,365 passed, 1 skipped — 45 more than PR #158's 2,320, all new v4
  tests), `python scripts/make_seed.py` +
  `python -m pipeline.validate data/site-data.json --allow-seed` all pass.

## 13. What the next execution PR is allowed to do

Build the label engine (calling `pipeline.alpha_opportunity_v4_eligibility
.label_eligibility` for every KR observation before constructing a label,
never re-implementing its logic), the training loop (respecting §10's PIT
folds exactly), and the evaluation harness (producing every §7 diagnostic
before interpreting any gate) — strictly within this sealed spec. It may
**not**: add a feature, interaction, hyperparameter, horizon, or model not
named here; loosen or reinterpret any `eligibilityPolicy` reason code;
treat an `INELIGIBLE` observation as zero, as the benchmark's return, or as
missing-at-random; edit `kr-terminal-action-reconstruction-v2.json` or its
`foundationStatus`; or promote any result to production. It may re-run
`scripts/audit_alpha_opportunity_v4_kr_eligibility.py` against a *later*
source-foundation snapshot and get a *different* (more permissive) result
without a new preregistration — that is the one designed degree of freedom
this document grants in advance.
