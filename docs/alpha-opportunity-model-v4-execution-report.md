# alpha-opportunity-model-v4 — KR historical execution report

Execution of the merged, sealed `alpha-opportunity-model-v4` preregistration
(PR #159; `research_specs/alpha-opportunity-model-v4.json`, SHA-256
`4db0a96267a8b0de41c445ac600a8064a760191abdd29d97600153a78cbab8e6`,
unchanged). **No production behaviour changed, nothing is promoted, and no
Alpha, IC, calibration or portfolio result exists from any run below.**

This PR ran the study with three harness contracts. Two had implementation
defects found by review before merge. They must not be read as one result.

| | Run 1 (contract V1) — **DEFECTIVE** | Run 2 (contract V2) — **region-year mismatch** | Run 3 (contract V3) — **contract-correct** |
|---|---|---|---|
| Harness commit | `1ffb8a72` (plus an identical provenance re-run) | `073169e3` | `b8a5dd29` |
| Report | `docs/results/alpha-opportunity-model-v4-execution-run1-defective.json` (bytes unchanged) | `docs/results/alpha-opportunity-model-v4-execution-run2-region-year-mismatch.json` (bytes unchanged) | `docs/results/alpha-opportunity-model-v4-execution-report.json` |
| Order | features → tradability → **forward labels → `label_eligibility`** → coverage gate | identity → features → tradability → **v2 20% region-year eligibility** → coverage + depth gates → (stop) | identity → features → tradability → coverage + depth gates on every tradable KR name-date → (stop) |
| Defect | labels built before the gate (§1) | applied the v2 rule v4's seal replaces (§2) | none known |
| Numerical effect of the defect on the gate | none (gate reads PIT features only) | none (no KR year exceeds 20%; max 0.128%) | — |
| Forward labels built | **Yes, in memory** | 0 | 0 (`targetFromSessionsCalls: 0`) |
| v4 `label_eligibility` called | **Yes** | 0 | 0 (`labelEligibilityCalls: 0`) |
| Models fit / folds evaluated | 0 / 0 | 0 / 0 | 0 / 0 (`predictCellCalls: 0`, `evaluateCellCalls: 0`) |
| Raw input identity enforced | No | Yes | Yes, 28 sealed git blobs at `signal-history` `4ea107ed` |
| Result | `BLOCKED_BY_DATA_INTEGRITY` | `BLOCKED_BY_DATA_INTEGRITY` | `BLOCKED_BY_DATA_INTEGRITY` |

## 1. Correction: the first run's sequencing defect

The V1 harness (`scripts/execute_alpha_opportunity_model_v4.py` at
`1ffb8a72`/`8695e00f`) called `alpha_opportunity_v2_evaluation.
target_from_sessions`, `attach_labels` and `alpha_opportunity_v4_eligibility.
label_eligibility` for every horizon **before** its coverage gate. It then
wrote `stoppedBeforeLabels: true`. That field, and this document's earlier
statements that "zero forward-return labels were ever constructed" and that
"the eligibility policy was never reached", were **false** for run 1.

What run 1 actually did before the gate stopped it:

- `target_from_sessions` read the entry and exit closes for every tradable KR
  name-date and computed `forwardRelativeReturn`; `attach_labels` computed
  `beatBenchmarkNet`. Run 1 had no call counters, so the count is derived
  rather than logged: the corrected run's own pre-label frame has 85,132
  tradable name-dates, and run 1's tradability function was a line-for-line
  copy of v2's, so run 1 made 85,132 x 2 horizons = **170,264** label
  constructions and the same number of `label_eligibility` calls. The
  mechanism was also reproduced directly on the unrepaired code with a
  synthetic frame: 1,248 label and 1,248 eligibility calls before a coverage
  stop that reported none.
- The labels lived only in process memory. The coverage gate raised before
  any walk-forward fold, model fit, prediction, evaluation or diagnostic, and
  the report it wrote contains no label, no return and no outcome-derived
  field. Nothing outcome-derived was persisted, printed or inspected.
- No parameter, threshold, feature, eligibility rule or gate was changed in
  response to any Alpha outcome — none was computed. The run-1 coverage
  numbers are identical to runs 2 and 3 (§5), which could not have happened
  if the premature labels had fed the gate: the gate reads PIT features only.

Run 1 also did not verify the raw KR fundamentals/universe files, which the
replay manifest does not cover. That is fixed from V2 on (§3). Those files
were in fact byte-identical to the sealed identity for run 1 as well: every
one of the 28 files matched at the `signal-history` head used then
(`2132d8d8`), and only unread collector bookkeeping differed.

## 2. Correction: the second run's region-year mismatch

v4's sealed `carriedFromV3.walkForward.survivorshipEligibility` states that
v4's per-observation `label_eligibility` policy **replaces** the 20%
region-year gap tolerance v2 and v3 inherited. Contract V2 fixed run 1's
ordering by calling `scripts/run_alpha_opportunity_model_v2.py`'s own
`tradability_frame`, `eligibility` and `pre_label_gates`, and in doing so
re-imported the replaced rule:

- `V2.eligibility` marked each KR region-year eligible only if its unvouched
  share was at most 20%, and `V2.pre_label_gates` measured coverage only on
  tradable name-dates in eligible years. A year above 20% would have been
  dropped wholesale from the coverage denominator, and the same flag
  filtered which rows would later receive labels.
- The V2 report published a `regionYearEligibility` table and a
  `tradableInEligibleRegionYears` count, and the earlier version of this
  document listed `REGION_YEAR_SURVIVORSHIP_ELIGIBILITY` as a step of v4.
  It is not one.

**No numerical effect on run 2.** The KR unvouched share runs from 0.000% to
0.128% (2014), so every one of the 14 KR years stayed eligible, all 85,132
tradable name-dates stayed in the denominator, and run 2's coverage failures
are identical to run 3's.

Contract V3 removes the rule semantically, not by marking every year
eligible: `pipeline.alpha_opportunity_v4_execution.pre_label_gates` applies
v2's sealed `coverageGate` thresholds and `calendar_depth` check to every
tradable KR name-date, and v2's `eligibility` and `pre_label_gates` are no
longer called. The report carries no region-year table. Unvouched shares are
still computed per date after the gates, because the sealed
`WORST_PLAUSIBLE` endpoint stress in `evaluate_cell` reads them; that is a
stress input, not an eligibility gate.

## 3. Implementation facts (harness contract V3)

- New code outside the preregistration's sealed closure:
  `pipeline/alpha_opportunity_v4_execution.py` and
  `scripts/execute_alpha_opportunity_model_v4.py`. The preregistration's own
  files (`research_specs/alpha-opportunity-model-v4.json`/`.sha256`,
  `pipeline/alpha_opportunity_v4_eligibility.py`,
  `pipeline/alpha_opportunity_v4_spec.py`,
  `scripts/run_alpha_opportunity_model_v4.py`) are byte-identical to PR #159.
  `load_sealed()` checks them at every start.
- **Order, enforced by control flow.**
  1. sealed spec identities (v4; v2 and v3, whose sealed JSON supplies runtime
     constants and the raw-input identity)
  2. `SEALED_INPUT_IDENTITY`: signal-history commit, git blob of every raw
     file read, replay-manifest digest; KR terminal-action foundation checked
     for regression and frozen
  3. PIT features
  4. tradability (v2's own `tradability_frame`, the sealed traded-at-all
     guard)
  5. `FEATURE_COVERAGE` and `CALENDAR_SAMPLE_DEPTH` on every tradable KR
     name-date, with v2's sealed thresholds (`firstEvaluationYear` 2016,
     price 0.8, accounting 0.2)
  6. only after every gate passes: input identity and frozen foundation
     re-verified, then labels, v4 observation eligibility, fits, evaluation.
  `--stop-before-labels` ends a run after step 5 whatever the gates say.
  There is no region-year step (§2).
- Regression tests. Every function that reads a forward price, builds or
  consumes a label, or calls the eligibility policy is replaced by a spy
  that raises on touch. The tests prove a coverage failure touches none of
  them and that labels come strictly after the gates and the identity
  recheck. They also cover input mutation, the moving-branch guard and seal
  immutability (each would have failed on V1). Three V3 tests spy on
  `V2.eligibility`/`V2.pre_label_gates` and raise if either is called, keep
  a synthetic year with 10 of 12 names unpriced (far above 20% unvouched) in
  the coverage denominator, and show that year's missing accounting data now
  fails the gate. All three fail on V2.
- Every feature, cost, transform, model, hyperparameter, threshold, gate and
  decision rule is read from the sealed v2/v4 JSON. No number was changed.

## 4. Frozen execution provenance (run 3)

| Field | Value |
|---|---|
| v4 spec SHA-256 | `4db0a96267a8b0de41c445ac600a8064a760191abdd29d97600153a78cbab8e6` |
| Harness contract / commit | `ALPHA_OPPORTUNITY_V4_KR_EXECUTION_HARNESS_V3` / `b8a5dd294d5038c4f603e48d62d2dd77491681e8` (clean) |
| `signal-history` commit (checked out and verified) | `4ea107ed0cde289f0a049a65ff13d2441a786710`, the commit v3's sealed `futureExecutionInputs` and v2's sealed `snapshots` both name |
| Replay manifest SHA-256 | `f0781292f508a123c234ded6d28aa8e84a0dc3cc29500e14989dc0b68f53b4d2` |
| Raw input identity | 28 git blobs: `ledger/fundamentals/kr/dart-2015…2026.jsonl.gz`, `shares.jsonl.gz`, `ledger/universe/kr/krx-universe-2013…2026.jsonl.gz`, `ledger/historical/replay-v16/inputs.json` — exactly v3's sealed list, listed in the JSON report |
| Input identity SHA-256 | `674a8b976707012438d2613fc54f238ffefe1179e5959461ce5a6d380f0a8f26` |
| KR terminal-action foundation | unchanged since seal; frozen snapshot hash `a844d39e159130ac04eddd895d8dd2b3f14b0bfc3ef3c30050afbc6b7c181b66` |
| Data cutoff / seeds | `2026-09-14` / inference 42, uncertainty 42 |

**Why this identity contract, and not the current branch head.** The replay
manifest content-addresses price, benchmark and corporate-event objects, but
not the raw `ledger/fundamentals/kr` and `ledger/universe/kr` shards the
feature path reads. The only sealed statement of those shards' identity in
this lineage is v3's `futureExecutionInputs.gitBlobSha1`, the same files and
hashes as v2's sealed `inputFiles`. v3's JSON is one of v4's own hash-pinned
`sealedDataInputs`. v4's own spec pins no raw-shard identity and names no
newer one. So the sealed identity governs, rather than whichever
`signal-history` head a run happens to check out. Collector bookkeeping that
v3 names as unread (`fundamentals/kr/manifest.json`, `absent.json`,
`krx-universe-done.json`) is outside the identity, as v3's `excludedAdjacent`
states.

## 5. Preregistered gate decisions (run 3)

**`BLOCKED_BY_DATA_INTEGRITY`, `stoppedBeforeLabels: true`.** All four call
counters are zero. 85,132 of 85,680 KR member-dates are tradable, and all
85,132 are in the coverage denominator.

Coverage failures (every tradable KR name-date, `firstEvaluationYear =
2016`, accounting floor `0.2`, inherited from v2 unmodified):

| Year | Feature | Coverage | Observed / rows |
|---|---|---|---|
| 2016 | `ocfToNetIncomePct` | 3.99% | 248 / 6,212 |
| 2016 | `assetGrowthPct` | 0.00% | 0 / 6,212 |
| 2016 | `debtGrowthPct` | 0.00% | 0 / 6,212 |
| 2025 | `ocfToNetIncomePct` | 17.42% | 1,083 / 6,218 |

Every price and attention feature, and every other year, clears the gate.
The calendar-depth gate was not reached because coverage stops first.

## 6. Descriptive diagnostics — why the gate fires (input data, not outcomes)

These findings come from run 1's investigation and are unaffected by its
defect. They read only filing metadata and account presence, never a return.
Runs 2 and 3 reproduce the same four failures exactly.

- **2016, exact zeros.** The raw DART collection's earliest fiscal year, 2015,
  has only the annual report (`11011`: 81 tickers, 0 quarterly rows).
  `assetGrowthPct` and `debtGrowthPct` need a same-report-code prior-year
  filing. During calendar 2016 the current filing is always a fiscal-2016
  quarterly, because the FY2016 annual is not filed until about March 2017.
  None of those quarterlies has a fiscal-2015 counterpart, so both features
  are structurally zero for every 2016 signal date. That extends this
  repository's "dark for the first two years" PIT-fundamentals finding to a
  third year for these two features.
- **2025, 17.42%.** Fiscal 2024 and 2025 have all four report codes for all
  126 DART tickers, so the 2016 mechanism does not apply. The cause is
  account completeness per filing. For example, `000080.KS`'s
  `(2024, '11014')` filing lacks `당기순이익` and `부채총계` although its
  neighbouring filings carry them. A TTM rollforward needs three filings, so
  these gaps compound.
- Only 126 of the 260 KR securities ever in the top-120 universe have any DART
  fundamentals (48.5%). This lowers every accounting feature's ceiling in
  every year.

None of this was addressed by loosening the floor, imputing, or excluding
2016 or 2025.

## 7. Limitations

- **The v4 eligibility policy has produced no evidence on real data.** Runs 2
  and 3 never call it. Run 1 called it, but on labels the harness should not yet
  have built, and nothing downstream used the result. Whether the policy
  behaves as intended on labelled data is untested.
- The `0.2` accounting floor comes from a joint US+KR design and is inherited
  unmodified; this report does not judge whether it suits KR-only.
- One sealed snapshot. A foundation or DART collection change could change the
  gate outcome without any code or policy change.
- No promotion (`promotionEligible: false`) and no production change.
