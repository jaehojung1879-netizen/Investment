# alpha-opportunity-model-v4 — KR historical execution report

> **CORRECTION IN PROGRESS — the claims below about the FIRST execution are
> wrong.** That run's harness (contract V1) called `target_from_sessions`,
> `attach_labels` and `label_eligibility` for every horizon BEFORE the
> coverage gate, so forward labels WERE constructed in memory and the v4
> eligibility policy WAS invoked, even though its report says
> `stoppedBeforeLabels: true`. No model was fit, no fold evaluated, and no
> Alpha/IC/calibration/portfolio result was produced or persisted. The raw
> report is preserved unchanged as
> `docs/results/alpha-opportunity-model-v4-execution-run1-defective.json`.
> The repaired harness (commit `073169e3`) restores v2's sealed pre-label
> order; a corrected, gate-only run is in progress and this document will be
> rewritten with its result.

This is the HISTORICAL EXECUTION of the already-merged, sealed
`alpha-opportunity-model-v4` preregistration (PR #159,
`research_specs/alpha-opportunity-model-v4.json`, SHA-256
`4db0a96267a8b0de41c445ac600a8064a760191abdd29d97600153a78cbab8e6`). It
was run exactly once, from a frozen execution snapshot, against the real,
hash-verified sealed `replay-v16` KR ledger. **No production behaviour
changed and nothing here is a promotion.**

## 1. Implementation facts

- New, non-sealed code: `pipeline/alpha_opportunity_v4_execution.py` (KR-only
  label engine, eligibility wiring, ten `F_missingnessIntegrity`
  diagnostics) and `scripts/execute_alpha_opportunity_model_v4.py` (the real
  execution entry point). Neither is part of the preregistration's own
  sealed dependency closure — `research_specs/alpha-opportunity-model-v4
  .json`/`.sha256`, `pipeline/alpha_opportunity_v4_eligibility.py`,
  `pipeline/alpha_opportunity_v4_spec.py` and `scripts/run_alpha_opportunity_
  model_v4.py` are byte-identical to what PR #159 merged (verified by
  `S4.load_sealed()` at the start of every run — a read-only check, not an
  edit).
- Every feature, cost, transform, walk-forward rule, model family,
  hyperparameter, alpha decision rule and evaluation gate is read from the
  already-sealed `research_specs/alpha-opportunity-model-v2.json` (v4's own
  `sealedDataInputs`) and `research_specs/alpha-opportunity-model-v4.json`'s
  own `carriedFromV3` block, assembled by `build_runtime_spec` — v4's own
  value always wins where both specify one. No number was invented; none was
  changed in response to this run's result.
- `pipeline.alpha_opportunity_v2_evaluation`, `alpha_opportunity_v2_model`,
  `alpha_opportunity_v2_decision`, `alpha_opportunity_v3_decision` and
  `alpha_opportunity_features`'s per-name feature functions
  (`price_attention_at`, `accounting_at`) are called completely unmodified.
  Only the KR-only orchestration loop (membership/raw-fundamentals loading,
  matrix assembly, tradability) is new, and it mirrors the region-scoped
  slice of the already-sealed v1–v3 orchestration exactly.
- 21 new unit tests (`tests/test_alpha_opportunity_v4_execution.py`), all
  against synthetic fixtures, written and passing BEFORE this execution ran.
  Full suite: 2,404 passed / 1 skipped before this PR's own additions; no
  regression after them.

## 2. Frozen execution provenance

Recorded once, before any label was constructed, and verified unchanged at
the end of the run (`assert_snapshot_matches_frozen_hash`):

| Field | Value |
|---|---|
| Sealed v4 spec SHA-256 | `4db0a96267a8b0de41c445ac600a8064a760191abdd29d97600153a78cbab8e6` |
| Preregistration `immutableVersion` | `4.0.0` |
| Execution code commit | `1ffb8a7272603f053fa48d577ff08344f5e8ecd7` (checkout clean) |
| Execution checkout dirty | `false` |
| Replay ledger version | `replay-v16` |
| Replay manifest SHA-256 | `f0781292f508a123c234ded6d28aa8e84a0dc3cc29500e14989dc0b68f53b4d2` (matches the sealed audit's own citation exactly) |
| Data cutoff | `2026-09-14` |
| KR terminal-action foundation snapshot | `docs/results/kr-terminal-action-reconstruction-v2.json`, unchanged since the v4 seal (current file hash == cited seal-time hash: `b1d2dcb0a8064139e601c4efab51a44e1323f93910ae70228054338a90629017`) — `assert_foundation_not_regressed` trivially holds |
| Frozen execution-snapshot hash | `a844d39e159130ac04eddd895d8dd2b3f14b0bfc3ef3c30050afbc6b7c181b66` |
| Deterministic seeds | `inference.seed=42`, `uncertainty.seed=42` (both carried unchanged from v3) |
| KR ledger inputs read | `ledger/replay-inputs` (price/benchmark panels), `ledger/historical/replay-v16/inputs.json`, `ledger/fundamentals/kr` (126 tickers, DART raw shards), `ledger/universe/kr` (weekly top-120 snapshots, 2013–2026) |

The run was executed twice against this identical frozen snapshot — once
before, once after the harness code itself was committed — to both correctly
stamp `executionCodeCommitSha` and verify determinism. The two runs are
byte-identical in every field except that one commit-SHA string.

## 3. OOS results

**None were computed.** The run stopped at the pre-label coverage gate
(`pre_label_gates`, inherited unmodified from `alpha-opportunity-model-v2`'s
own `coverageGate`: `firstEvaluationYear=2016`, `accounting` floor `0.2`) —
**zero forward-return labels were ever constructed**, zero models were
fitted, zero folds were evaluated. `results: []`, `folds: []`,
`numericalFailures: []`.

## 4. Preregistered gate decisions

**Status: `BLOCKED_BY_DATA_INTEGRITY`** (one of the four statuses
`alpha_opportunity_v4_spec.STATUSES` names; `stoppedBeforeLabels: true`).

Coverage failures (KR accounting features, tradable name-dates in the built
feature matrix, `firstEvaluationYear=2016` onward):

| Year | Feature | Coverage | Observed / Universe rows |
|---|---|---|---|
| 2016 | `ocfToNetIncomePct` | 3.99% | 248 / 6,212 |
| 2016 | `assetGrowthPct` | **0.00%** | 0 / 6,212 |
| 2016 | `debtGrowthPct` | **0.00%** | 0 / 6,212 |
| 2025 | `ocfToNetIncomePct` | 17.42% | 1,083 / 6,218 |

All against the inherited (v2/v3, unmodified) `0.2` accounting-coverage
floor. Every other year (2017–2024, 2026) and every price/attention feature
clears the gate.

This gate is exactly the one `alpha-opportunity-model-v2`'s own script
already enforced, carried forward unmodified — it is not new to this
execution, and passing or failing it says nothing about the eligibility
policy that is v4's own design change (see §6): **the eligibility policy was
never reached in this run.**

## 5. Descriptive diagnostics — WHY the gate fired, investigated (not tuned around)

Two independent, root-caused, disclosable data facts, verified directly
against the real fetched KR ledger before this report was written — neither
is a bug in this harness or in the sealed preregistration:

**(a) 2016 growth features (0% both).** The raw DART collection's earliest
fiscal year is 2015, and for 2015 **only the annual report (code `11011`) was
collected — no quarterly filings exist for fiscal year 2015 at all**
(measured: 81 tickers each carry exactly one `(2015, '11011')` filing, zero
`(2015, '11012'/'11013'/'11014')` rows). `assetGrowthPct`/`debtGrowthPct`
require a same-report-code prior-year filing
(`accounting_quality.derive_kr_fields` → `_growth_pct(current, prior)`). During
calendar year 2016 itself, the filing `alpha_opportunity_features.accounting_at`
picks as "current" is always one of fiscal-year-2016's own report codes
(11011/12/13/14, whichever has most recently become PIT-visible) — the
fiscal-year-2016 ANNUAL report is not filed until ~March 2017, so it can
never be "current" during 2016. Every fiscal-year-2016 QUARTERLY filing that
IS current during 2016 needs a fiscal-year-2015 SAME-quarter filing that this
collection never has. The result is a **structural, deterministic** zero for
every signal date in calendar year 2016 — a sharper, newly-measured version
of this repository's own PIT-fundamentals invariant ("DART serves from 2015
... Korean value and quality are dark for the first two years"): the
`ocfToNetIncomePct`/`assetGrowthPct`/`debtGrowthPct` darkness measured here
extends into a **third** year (2016) for the two growth-rate features
specifically, because 2015's own collection is annual-only.

**(b) 2025 `ocfToNetIncomePct` (17.4%).** Not explained by (a): fiscal years
2024 and 2025 both have full four-report-code coverage across all 126
DART-tracked tickers. Root cause instead: `dart_derive.trailing_twelve_months`'s
rollforward needs `당기순이익` (net income) present in BOTH the current AND the
prior-year same-quarter filing's own `accounts` dict, and DART's own reported
account set varies filing-by-filing — measured directly on one real example
(`000080.KS`, `(2024, '11014')`): that filing's `accounts` carry `매출액`,
`영업이익`, `영업활동현금흐름`, `유형자산의취득`, `자본총계`, `자산총계` but
**not** `당기순이익` or `부채총계`, even though the SAME ticker's other
quarters and its annual filings do carry it. This is a per-filing DART
reporting-completeness gap this repository's own PIT-fundamentals invariants
already anticipate ("a blank line item is `None`, never `0.0`") — never
fabricated here, and compounding across the three filings a TTM rollforward
needs is what drags aggregate coverage down for this specific flow account
in this specific year. 126 of 260 ever-top-120 KR tickers (48.5%) have DART
fundamentals collected at all (matching `alpha-research-foundation-v2`'s own
126-ticker citation exactly), which lowers every accounting feature's ceiling
further but does not by itself explain a 17% (rather than ~50%) reading —
the per-filing account-completeness gap above is the dominant mechanism.

Neither fact was known to require this specific gate to fire before this
run; both were investigated with real, re-executable evidence after the run
stopped, exactly as the two-phase discipline requires (`STOP and document
it`, never `silently repair and rerun`). No threshold, feature, or gate was
changed in response.

## 6. Limitations

- **The eligibility policy — v4's entire design contribution — was never
  exercised.** No observation ever reached `label_eligibility`; the 22
  audited KR terminated securities' known-blocked completeness evidence
  never entered a single label decision in this run. This report cannot say
  anything about whether that policy behaves as intended on real labelled
  data; it can only report (§1–2) that it is wired correctly against
  synthetic fixtures.
- **The `0.2` accounting coverage floor is inherited from v2, unmodified.**
  It was designed for a joint US+KR study; whether it is the right bar for a
  KR-only study is a legitimate question this report does not answer — and
  is explicitly NOT one this run may answer by loosening it.
- **This is one execution, from one frozen ledger snapshot** (`replay-v16`
  through `2026-09-14`). A later KR fundamentals collection run that adds
  quarterly 2015 filings, or improves per-filing DART account completeness,
  could change this specific gate's outcome without any code or policy
  change — exactly what `assert_foundation_not_regressed`/`freeze_execution_
  snapshot` exist to make auditable rather than silent.
- **No promotion, no production change, regardless of this result.**
  `promotionEligible: false` is asserted in the report schema itself.
- The full, byte-identical result is committed at
  `docs/results/alpha-opportunity-model-v4-execution-report.json`.
