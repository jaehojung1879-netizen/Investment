# Alpha inference calibration v3 — closed substantive failure

Status: `FAIL`. Synthetic-methods result, not an Alpha outcome. Closed; not rerun.

## Immutable run identity

- workflow: `Synthetic alpha inference calibration v3`
- run: `36483954346` (`workflow_dispatch`, run attempt 1)
- main commit: `faff543fd0516e734d14d680cecf0f12b8850fd6`
- contract: `ALPHA_INFERENCE_CALIBRATION_V3`
- spec SHA-256: `e8340ac3541e8981983996b8a66b54030757c2cd0419aab2140f8e3fe41d1d59`
- artifact: `alpha-inference-calibration-v3`, id `10998470853`, 3,736 bytes,
  zip SHA-256 `c9ee787aaa34d0102e0cef13505195b1b40d19b5bbfb74f1998e27c6fb2abe14`
- cells: 16; failing cells: 3; failing statistic-cells: 5

The job completed the simulation, printed `primaryStatus: FAIL`, and exited 2 by
design; the artifact upload succeeded. It was not an infrastructure failure.

## Per-cell values

The artifact blob host is unreachable from the environment that wrote this
record, so the table below is the output of re-running the unmodified, fully
seeded v3 runner at `faff543` with the pinned `requirements.txt`. The
reproduction printed the same status, cell count and spec hash as the run log.

Coverage (nominal 0.975, floor 0.95) of the failing H126 / 312-week cells:

| DGP | dateMean | selectedMean | pairedMseImprovement | rankIC | selectedMinusUniverse |
|---|---:|---:|---:|---:|---:|
| IID_SHARED | 0.9500 | **0.9467** | 0.9800 | 0.9800 | 0.9767 |
| WEAK_SERIAL | **0.9367** | **0.9400** | 0.9800 | 0.9900 | 0.9867 |
| PERSISTENT_SERIAL (pass) | 0.9600 | 0.9667 | 0.9700 | 0.9833 | 0.9667 |
| PERSISTENT_SHARED_HEAVY | **0.9433** | **0.9433** | 0.9833 | 0.9533 | 0.9733 |

Every H21 cell and every H126 / 624-week cell passed. No directional false-positive,
undefined-frequency or Monte Carlo precision failure occurred.

## Diagnosis

See `docs/alpha-inference-calibration-v4-methodology.md` §3. In short: v3's SN
interval was applied to an overlapping signal-date series whose mechanical
dependence spans 26 of 312 dates; its exact Gaussian `dateMean` coverage there is
0.957–0.958 against nominal 0.975, and the observed failures are that
distortion read through 300-replicate Monte Carlo noise against the 0.95 floor.
The other three statistics were martingale-difference sequences under the v1–v3
null and could not fail for this reason.

## Stopping rule

This FAIL closes `ALPHA_INFERENCE_CALIBRATION_V3`. Do not rerun it, change its
critical value, seed, depths, DGPs or tolerances, or argue from the analytic
coverage that it "really passed". The successor is the separately frozen
`ALPHA_INFERENCE_CALIBRATION_V4`. No historical return, label, Alpha score, model
result or `signal-history` outcome was read.
