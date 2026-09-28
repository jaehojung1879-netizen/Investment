# Alpha inference calibration v1 — frozen failure record

Status: **SUBSTANTIVE FAIL**. This is a synthetic-methods result, not an Alpha outcome.

## Immutable run identity

- workflow: `Synthetic alpha inference calibration v1`
- run: `36472769120`
- main commit: `1d6098d2553dd8ab6d7465fe18cb05c0a0513172`
- contract: `ALPHA_INFERENCE_CALIBRATION_V1`
- spec SHA-256: `195a365c5224e10671e91fb601353a29fe39e6efa633d6e053fc67360461b433`
- uploaded artifact ZIP SHA-256: `ba41dce994639ce0155168d749557ff0c55d1f6b91bd6b554729898b833a8ffd`
- simulation replicates: 300 per DGP/depth/horizon cell
- bootstrap draws: 10,000 per interval
- result cells: 40
- primary cells: 16
- primary cells failed: **16 / 16**
- undefined-frequency failures: **0**

The prior run `36470839016` is not a substantive calibration attempt: it failed before simulation at a Python import-path error and produced no result artifact.

## What failed

V1 used a non-circular moving-block bootstrap and raw percentile interval. The frozen acceptance floor required at least 95% empirical null coverage, at most 5% positive-direction false positives, at most 5% undefined frequency, and Monte Carlo 95% half-width at most 4 percentage points.

All 16 evaluable primary DGP/depth cells failed at least one registered statistic. Material undercoverage was the dominant failure and was already present in `IID_SHARED`, so the failure cannot be attributed only to persistent serial dependence.

Primary-statistic coverage ranges by horizon/calendar depth were:

| Horizon | Calendar weeks | Primary block | Coverage range across DGP × statistic | Positive-FP range |
|---|---:|---:|---:|---:|
| 21 | 78 | 10 | 88.67%–95.33% | 2.67%–6.00% |
| 21 | 156 | 10 | 90.00%–97.33% | 0.67%–4.67% |
| 126 | 312 | 52 | 86.67%–92.33% | 3.67%–7.67% |
| 126 | 624 | 52 | 91.67%–96.67% | 1.67%–4.67% |

The most acute finite-depth case was H126 / 312 weeks, where the registered 52-week primary block leaves only six floor-effective blocks. Directional false-positive excess also appeared in several serial/shared-shock cells.

## Interpretation and stopping rule

This FAIL closes `ALPHA_INFERENCE_CALIBRATION_V1`. Do not rerun it, lower the acceptance threshold, or promote a sensitivity block because its observed v1 coverage looked better.

The permissible next step is a new, separately frozen methods protocol with a structural rationale independent of historical Alpha outcomes. V2 therefore keeps the v1 block grid, primary block choices, DGPs, statistics, replication budget and acceptance tolerances unchanged and changes only the interval mechanics: circular block resampling plus a centered/basic error interval.

No historical return, label, Alpha score, model result, or `signal-history` outcome was read by the calibration workflow.
