# alpha-opportunity-model-v5 execution harness (v1) — implemented, NOT authorized, NOT executed

State: **`HARNESS_READY_BUT_NOT_AUTHORIZED`**. This change implements the separately reviewed execution
harness that `research_specs/alpha-opportunity-model-v5.json` (`executionHarness`) deliberately left out of the
sealed closure. It executes nothing. No Alpha-v5 label, prediction, interval or verdict exists, the operator
authorization file does not exist, and no result artifact exists.

The frozen scientific design is `docs/alpha-opportunity-model-v5-preregistration.md` and the sealed spec
(digest `d0f1aaf50d9629ba2f8a0a9802cd4ebd653018028ee97b2746f9e50703741e75`, file SHA-256
`8a0a42a3f9414dbefa3ab8ec47f00ad71f8d7436febb125dff150f3c1e50d54c`). None of it is restated or amended here.
Where the harness could not implement the frozen contract exactly it fails closed instead of reinterpreting.

## Files

| File | Role |
|---|---|
| `pipeline/alpha_opportunity_v5_execution.py` | identity guard, pre-label gates, label permit, walk-forward ladder, orchestration, result artifact |
| `pipeline/alpha_opportunity_v5_evidence.py` | calendar-time attribution of real cohorts, the registered designs, claim state machine, economic tier |
| `scripts/execute_alpha_opportunity_model_v5.py` | CLI: `--print-code-identity`, `--freeze-only`, `--stop-before-labels`, `--execute` |
| `.github/workflows/alpha-opportunity-model-v5-execution.yml` | `verify` / `gates-only` / `execute`, main-only, one-shot |
| `tests/test_alpha_opportunity_v5_execution.py`, `tests/v5_harness_fixtures.py` | synthetic-fixture tests only |

The sealed `pipeline/alpha_opportunity_v5_spec.py` and `scripts/run_alpha_opportunity_model_v5.py` are
byte-identical to the preregistration merge; the sealed runner's `--execute` still refuses with
`NO_V5_EXECUTION_HARNESS_IN_THIS_PR`. The harness files are outside `dependencyHashes` by construction
(a test proves it), so adding them did not rewrite the seal.

## Order of operations (enforced by construction, proved by counters and spies)

1. `IdentityGuard.freeze` records, in one place: the sealed spec digest, the recomputed dependency closure
   with every sealed file hash, the v1–v4 seals and inherited values, the KR accounting snapshot (per-shard git
   blob, candidate identity, content hash, record count), the sealed raw-input blobs at the pinned
   signal-history commit and the replay manifest digest, the calibrated-inference pins, the terminal-action
   execution snapshot (regression check against the v4-cited snapshot, then frozen once), and the harness code.
2. PIT features and the tradability guard.
3. `pre_label_gates`: feature coverage and the calendar-depth upper bound for every cell. A failure raises
   `PreLabelStop` for the whole run: no label, fit, prediction or evaluation has run.
4. `issue_label_permit` exchanges a `GatesPassed` object for a `LabelPermit` and **re-verifies every frozen
   identity immediately before the first label**.
5. `build_labels` refuses without a permit. Labels, `label_eligibility`, folds, B0–B5, statistics and intervals
   exist only past this point.
6. Identity is verified again after evaluation.

`Counters` are incremented at the call sites of `target_from_sessions`, `label_eligibility`, every fit,
every prediction and every evaluation. `ordering.stoppedBeforeLabels` is **derived** from them and is never
asserted independently. That is the direct fix for the v4 defect (a first harness that built ~170k labels
before its coverage gate and reported that it had not). A test replaces every one of those functions with a
spy that raises, and a pre-label failure must finish with all counters at zero and no spy reached.

A same-run input swap fails: a shard, the snapshot, a raw blob, the replay manifest, the terminal-action
snapshot, the calibrated engine or the harness code changing after it was frozen raises `InputIdentityChanged`,
which is reported as `INFRASTRUCTURE_ERROR` (never as a verdict).

## Ladder, statistics and claims (all from the sealed spec)

- Walk-forward: `V1.folds` (expanding, first weekly signal date each year, exact strict maturity purge, 36
  months of history, ≥104 matured training dates, ≥10 names per date). A fold before the cell's coverage start
  year is not an evaluation fold; from the first READY fold on, every later scheduled fold must be READY or the
  cell is `DATA_INSUFFICIENT`. Transforms are fitted on the training frame alone; every date carries equal
  total weight. US rows are refused.
- B0 training date-weighted mean gross relative return; B1 zero; B2 Ridge(alpha 10) on `relative126`; B3
  Ridge on the six non-accounting features (H126 only; **at H21 B3 and B4 are one predictor, no duplicate
  fit is made and the accounting contrast is reported `NOT_APPLICABLE`**); B4 Ridge on the cell's full frozen
  registry, the sole primary model; B5 the frozen shallow HGB on B4's inputs (descriptive; the harness
  cannot let it change a conjunct — a test swaps B5 and the Logistic head for an oracle and for junk and the
  claim does not move). The Logistic head (C=1) is separate and descriptive.
- Conjuncts: `pairedMseImprovement(B4 vs B0)`, `pairedMseImprovement(B4 vs B2)`, `rankWeightedSpread(B4)`, each
  at the sealed 97.5% calendar-time self-normalised interval. `rankIC` is descriptive only.
- States: `PASS` all lower bounds strictly > 0; `FAIL` some upper bound strictly < 0; `INCONCLUSIVE` all defined,
  none refuted, one contains zero; `DATA_INSUFFICIENT` gate / depth / fold / undefined-interval shortfall;
  `INFRASTRUCTURE_ERROR` no complete valid result. Within a claim the precedence is the sealed
  `precedenceWithinClaim`; overall it is INFRASTRUCTURE_ERROR > FAIL > INCONCLUSIVE > DATA_INSUFFICIENT > PASS
  and PASS needs both claims. Depth floors are read from the spec (H21 78, H126 312 signal weeks), never
  from the data.
- `ECONOMIC_CANDIDATE_FINDING` is evaluated only when the claim is PASS (52 defined selected dates, both
  lower bounds, both chronological halves). It is a conditional candidate-date finding, never portfolio or
  deployability evidence; margin, notional, ADV and slippage stay blocked and are not invented.

### How the calibrated engine is reused, and the one thing that is new

The interval is `alpha_inference_calibration_v4.calendar_time_sn_interval` (an engine file pinned by hash in
the sealed spec), called with the sealed U1 value 66.57 and tolerance 1e-12, and the `rankWeightedSpread`
weights are the engine's `_centred_rank_weights`. What is new is the realisation-time attribution of REAL
cohorts. The calibration simulates additive daily returns shared by all cohorts; the frozen label is a
compounded ratio. Its exact additive decomposition is the per-session increment `(Close[s]-Close[s-1]) /
Close[entry]` for the stock minus the same for the benchmark; these telescope to the label exactly
(asserted per name-date to 1e-9) and are cohort-specific, so the engine's shared-panel `calendar_time_series`
cannot be used directly. `calendar_time_attribution` is the same identity generalised, a test proves it equals
the engine's function on additive data, and the sum of D over calendar weeks is asserted equal to the sum of
the signal-date statistic on every series or the run raises. A session with no print carries a zero increment
and the move appears on the next printed session; entry and exit closes must exist for a label to be matured,
so the level is never a price substitute. Estimator and estimand are unchanged.

## What the artifact carries

`alpha-opportunity-model-v5-result.json` (canonical JSON, no timestamps): protocol identity; the frozen input
identity and every recheck; foundation freeze; pre-label gate results per cell (coverage by feature and year,
start year, depth upper bound); the call counters and the derived ordering proof; sample counts; per-fold
records (training rows and dates, omitted features, predictive residual RMS, fitted-value interval width);
per-cell conjunct intervals and states, ladder contrasts, descriptive instruments (rankIC, slope, absolute
calibration, Logistic Brier/log loss/ECE, annual estimates, cost x2, selection counts by date), the claim and the
conditional economic tier; the overall status; missingness/survivorship diagnostics; code identity (harness
hashes and the full import closure) and library versions; and the attempt identity. Its `substantiveResultSha256`
excludes only the attempt identity, so an identical frozen execution reproduces it byte for byte (tested,
including under shuffled input row order). No portfolio, weight, NAV, Kelly, Sharpe or order field exists.

A verdict (PASS / FAIL / INCONCLUSIVE / DATA_INSUFFICIENT) is a successful process (exit 0) and, from the
formal run, a **substantive result that closes the preregistration** (including a registered pre-label gate
stop). Only INFRASTRUCTURE_ERROR exits non-zero, and its artifact is kept under an attempt name so it never
trips the one-shot guard.

## Modes

- `verify` — outcome-free identity check (unchanged from the preregistration change).
- `gates-only` — `--stop-before-labels`: PIT features, tradability, coverage and depth on the sealed inputs,
  then stop. Reads no label or outcome (counters in the artifact prove it), is never a substantive result, needs
  no authorization. It exists because a formal run that stops at a coverage or depth gate is a closing result;
  learning that fact from an outcome-free run costs the one-shot budget nothing.
- `execute` — the single authorized run.

## Operator steps after review and merge (not performed here)

1. Optionally dispatch `mode: gates-only` from merged `main` and read the gate result.
2. Compute the harness hashes and read the diagnostic-spec digest: `python scripts/execute_alpha_opportunity_model_v5.py --print-code-identity`. The supplemental diagnostics (`docs/alpha-opportunity-model-v5-diagnostics.md`) are part of the formal run and their spec digest is pinned by the authorization.
3. Commit `research_specs/alpha-opportunity-model-v5-execution-authorization.json`:

   ```json
   {"studyId": "alpha-opportunity-model-v5", "specSha256": "<the sealed digest>",
    "authorizedExecutions": 1, "authorizedBy": "<operator>",
    "diagnosticSpecSha256": "15a855faae2b7a1ae34aea703a8e0b996b363fd8359210bb43ab308945048f9a",
    "harnessFiles": {"pipeline/alpha_opportunity_v5_diagnostics.py": "<sha256>",
                     "pipeline/alpha_opportunity_v5_evidence.py": "<sha256>",
                     "pipeline/alpha_opportunity_v5_execution.py": "<sha256>",
                     "scripts/execute_alpha_opportunity_model_v5.py": "<sha256>"}}
   ```

   The harness refuses unless the digest and every harness file hash match, so an authorization cannot be
   spent on a different version of the code than the one that was reviewed.
4. Dispatch `mode: execute` from `main` exactly once. On a substantive result, commit the artifact as
   `docs/results/alpha-opportunity-model-v5-result.json`; its existence makes any rerun a refusal that does not
   depend on artifact retention.

## Disclosed limits

- Only the harness files are pinned by the authorization. The rest of the import closure (eligibility, features,
  v2 evaluation/model, calibration engine) is recorded in the artifact for audit, not pinned, because pinning
  files like `portfolio_validation.py` would let unrelated production edits invalidate an authorization; the
  calibration engine is separately pinned by the sealed spec.
- Price objects under `ledger/replay-inputs` are covered by the replay manifest digest and re-hashed by
  `InputStore` when read, not re-hashed a second time after the gates.
- A fold whose PRIMARY Ridge fit fails numerically is an `INFRASTRUCTURE_ERROR` (retryable only after an
  outcome-independent repair); a failure of a descriptive head (Logistic, HGB, fitted-value interval) is
  recorded and changes nothing.
- The spec has no worst-plausible / unresolved-endpoint treatment (v4's belonged to its replaced omnibus gates),
  and none is invented: unresolved and ineligible endpoints are excluded and counted by reason.
- All harness tests use synthetic fixtures. The harness has never run on real prices; a first real run can stop
  at a gate or on an input the fixtures did not anticipate, and that is a reported outcome, not a reason to
  alter the protocol.
