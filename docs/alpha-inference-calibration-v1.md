# Alpha inference calibration v1

Status: **FROZEN BEFORE SYNTHETIC RESULTS**  
Scope: synthetic-only methods validation. This is not v5 and does not authorize any historical Alpha execution.

## 1. Why this exists

`alpha-research-design-review-v1` retained moving-block bootstrap inference but explicitly refused to treat 10 weeks (21-session horizon) or 52 weeks (126-session horizon) as validated bandwidths without a synthetic null calibration. This record freezes that calibration before any result is observed.

The calibration asks only whether the proposed interval mechanics behave tolerably under invented null data with label overlap, serial shocks and shared cross-sectional shocks. It cannot establish that Alpha exists, that a model is correctly specified, or that a strategy is investable.

## 2. Frozen protocol

Machine-readable source of truth: `research_specs/alpha-inference-calibration-v1.json`.

- root seed: `20260928`
- Monte Carlo datasets per DGP/depth/horizon cell: **300**
- moving-block bootstrap draws per interval: **10,000**
- synthetic names per weekly date: **60**
- signal spacing: **5 invented sessions**
- claim-level interval: **97.5% two-sided** (`tail=0.0125`), matching two KR horizon primary expected-return claims under familywise alpha 0.05
- 21-session candidate blocks: **5, 10 weeks**; primary remains **10**
- 126-session candidate blocks: **26, 52, 104 weeks**; primary remains **52**
- minimum operational depth: **6 non-overlapping block lengths**

Calendar-depth cells are intentionally short and longer:

- H21: 78 and 156 weekly dates
- H126: 312 and 624 weekly dates

The 104-week sensitivity is intentionally depth-ineligible at 312 weeks and evaluable at 624 weeks. That is a planned depth diagnostic, not a failure to be repaired after the run.

## 3. Synthetic null DGPs

Four fixed Gaussian processes are used:

1. `IID_SHARED`: no serial persistence; moderate shared shock.
2. `WEAK_SERIAL`: weak shared and idiosyncratic persistence.
3. `PERSISTENT_SERIAL`: strong shared persistence plus moderate idiosyncratic persistence.
4. `PERSISTENT_SHARED_HEAVY`: highly persistent shared shock and lower idiosyncratic scale.

For every DGP, daily synthetic stock innovation is `shared + idiosyncratic`. Forward targets are exact sums over 21 or 126 invented sessions, sampled every five sessions. The overlap is therefore generated mechanically rather than approximated by an AR process on weekly labels.

Outcome innovations and all predictors are generated from separately spawned RNG streams. No predictor receives the serial shock or any future target innovation. The population predictive null is therefore exact by construction.

## 4. Null statistics

Every statistic has known null value zero:

- `dateMean`: cross-sectional mean forward synthetic target.
- `pairedMseImprovement`: MSE difference between two exchangeable independent synthetic forecast streams; expectation is zero by symmetry.
- `rankIC`: within-date Spearman correlation between an independent synthetic score and target.
- `selectedMean`: mean target of the top 20% by an independent selection score.
- `selectedMinusUniverse`: selected mean minus full-universe mean on the same synthetic date.

The bootstrap resamples complete weekly dates in consecutive non-circular moving blocks and preserves within-block order. It uses the same truncation semantics as `pipeline.alpha_opportunity_model.block_sample_indices`; a unit test proves the optimized block-sum implementation is numerically identical.

## 5. Frozen acceptance tolerances

Only the predeclared primary block determines protocol PASS/FAIL. Sensitivities are always disclosed and never replace a failed primary.

For every evaluable primary DGP/depth/statistic cell:

- empirical interval coverage must be **>= 95%** against nominal 97.5%; lower is `MATERIAL_UNDERCOVERAGE`;
- positive-direction false-positive frequency (`lower > 0` under the exact null) must be **<= 5%**;
- undefined interval frequency must be **<= 5%**;
- 95% Monte Carlo half-width for coverage and positive false-positive estimates must be **<= 4 percentage points**.

These are finite-simulation materiality tolerances, not claims that 95% coverage is ideal. The nominal target remains 97.5%.

If a primary block fails any frozen tolerance in any evaluable cell, the overall calibration is **FAIL**. Do not choose the sensitivity that happened to look best, expand the block grid, change the seed, or repeat simulations until PASS. Any revised method requires a separately documented and pre-frozen protocol before another synthetic run.

## 6. Execution and stopping rule

This PR freezes and implements the method only. It deliberately does **not** contain a calibration result.

After this protocol is reviewed and merged to `main`, run GitHub Actions workflow:

`Synthetic alpha inference calibration v1`

exactly once for the substantive calibration.

A rerun is allowed only for an infrastructure/runtime failure that produced no complete calibration result. A substantive PASS or FAIL is an observed methods result and closes this protocol's run budget.

The workflow:

- reads only the frozen JSON protocol and code;
- has no secrets and no market-data input;
- writes no `signal-history` data;
- uploads `alpha-inference-calibration-v1.json` as an artifact even on substantive FAIL;
- exits nonzero on primary FAIL so the result cannot be mistaken for a passing methods gate.

## 7. What comes after

If calibration PASSes, the next outcome-independent work is:

1. fixed-sample original-XBRL value validation for the 2015 recovered accounts;
2. exact repaired KR snapshot identification and freeze/hash;
3. final accounting semantic contract, including cash-conversion loss/denominator state treatment;
4. v5 preregistration and review;
5. only then, one explicitly authorized historical v5 execution.

If calibration FAILs, stop before v5. Diagnose the inferential method using only the synthetic evidence and create a new frozen methods protocol. Historical Alpha outcomes remain untouched.
