# Alpha inference calibration v2

Status: **FROZEN METHODS PROTOCOL — DO NOT EXECUTE BEFORE MERGE**.

This protocol follows the substantive FAIL of `ALPHA_INFERENCE_CALIBRATION_V1` recorded in `docs/results/alpha-inference-calibration-v1-report.md`. It remains synthetic-only and must not read historical returns, labels, model results, or `signal-history` outcomes.

## Why v2 exists

V1 completed its registered synthetic experiment and failed all 16 primary DGP/depth cells. Material undercoverage was present even under the IID synthetic DGP, while undefined statistics were not the problem. That result closes v1; it is not rerun or rescued by selecting a favorable sensitivity block.

The v1 implementation used a non-circular moving-block bootstrap. In a finite series, non-circular block starts make edge dates eligible for fewer block positions than interior dates. With long blocks and only six to fifteen effective blocks in the primary cells, that inclusion asymmetry is an avoidable finite-sample distortion. V1 also used percentile endpoints from the bootstrap mean distribution directly rather than explicitly forming the sampling error distribution around the observed estimate.

V2 therefore changes exactly two coupled mechanics:

1. **Circular moving blocks.** Every weekly date is an admissible start. A block wrapping past the end continues at the first date. Concatenated blocks are truncated to exactly `n` dates. This removes endpoint start-probability asymmetry without changing block length.
2. **Basic centered-error interval.** For estimate `theta_hat`, each bootstrap draw gives `e*=theta*−theta_hat`; the interval is `[theta_hat−q_(1−tail)(e*), theta_hat−q_tail(e*)]`.

This is a finite-sample mechanics repair, not a bandwidth search.

## What is deliberately unchanged from v1

- H21 candidate blocks `{5,10}`; primary `10`
- H126 candidate blocks `{26,52,104}`; primary `52`
- calendars H21 `{78,156}` weeks and H126 `{312,624}` weeks
- four DGPs and all their persistence/variance parameters
- five known-zero statistics
- 60 names per date, weekly five-session signal step
- 300 Monte Carlo datasets per DGP/depth/horizon cell
- 10,000 bootstrap draws per interval
- 97.5% claim-level interval (`tail=0.0125`)
- minimum six floor-effective blocks
- coverage floor 95%
- positive-direction false-positive ceiling 5%
- undefined-frequency ceiling 5%
- Monte Carlo 95% half-width ceiling 4 percentage points

The v1 sensitivity results are not used to promote 5 or 26 weeks, expand the grid, lower a tolerance, or choose a new DGP.

## Frozen identity

The source of truth is `research_specs/alpha-inference-calibration-v2.json`. Its seed is `20260929`. The spec is committed before implementation/execution results are available. The runner records the exact spec SHA-256 in the artifact.

## Acceptance and stopping rule

Only the predeclared primary blocks determine `PASS`/`FAIL`. Every evaluable primary DGP/depth/statistic must satisfy all frozen tolerances. Registered sensitivity blocks remain disclosure-only and cannot rescue a failed primary.

A complete `FAIL` is substantive and closes v2. Do not rerun with another seed, change blocks, relax thresholds, or choose the best-looking sensitivity. A retry is permitted only for a transport/runtime defect that prevents a complete artifact from being produced.

A `PASS` validates only these synthetic null interval mechanics. It is not historical Alpha evidence and does not create v5 automatically. The next steps after PASS remain: original-XBRL fixed-sample value validation, repaired KR snapshot freeze/hash, final accounting semantic contract, then v5 preregistration before any authorized historical execution.
