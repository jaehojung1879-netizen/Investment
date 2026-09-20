# Regional switch hurdle v1

> Read-only research CHALLENGER on sealed replay-v16 inputs. No selector is
> promoted and production is unchanged.

## What this isolates

One thing: the replacement decision. Cadence stays at every 21-session block,
caps and the cash floor stay production, and there is no positive-alpha cash
gate. An incumbent is credited the sell cost of its own region and a challenger
charged the buy cost of its own region, so Korean positions become stickier
than American ones without anyone choosing that ratio — the sell tax does it.

## Cost of a swap, by region and year

| Year | US round trip | KR round trip | KR / US |
|---|---:|---:|---:|
| 2013 | 0.163% | 0.410% | 2.515x |
| 2019 | 0.163% | 0.360% | 2.209x |
| 2021 | 0.163% | 0.340% | 2.086x |
| 2023 | 0.163% | 0.310% | 1.902x |
| 2025 | 0.163% | 0.260% | 1.595x |
| 2026 | 0.163% | 0.310% | 1.902x |

## Ladder

| Path | Gross CAGR | Cost drag | Net CAGR | Matched benchmark | Net excess | Sharpe | MDD | Annual turnover | Avg cash |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PUBLISHED_CHALLENGER_NO_HURDLE | 12.979% | 1.386pp | 11.593% | 12.639% | -1.046pp | 0.757 | -24.563% | 4.564x | 30.515% |
| NO_HURDLE_CONTROL_SAME_LOOP | 13.564% | 1.404pp | 12.161% | 12.845% | -0.684pp | 0.853 | -25.158% | 4.679x | 30.417% |
| SWITCH_HURDLE_ROUND_TRIP_COST | 15.963% | 1.133pp | 14.830% | 12.757% | 2.072pp | 1.057 | -22.311% | 3.567x | 30.793% |
| SWITCH_HURDLE_ROUND_TRIP_COST_PLUS_ONE_STANDARD_ERROR | 14.867% | 0.814pp | 14.053% | 13.553% | 0.500pp | 0.848 | -35.036% | 2.814x | 29.391% |

## Did the hurdle bite harder where it costs more?

| Path | US retention | KR retention |
|---|---:|---:|
| NO_HURDLE_CONTROL_SAME_LOOP | 41.240% | 53.170% |
| SWITCH_HURDLE_ROUND_TRIP_COST | 88.020% | 62.900% |
| SWITCH_HURDLE_ROUND_TRIP_COST_PLUS_ONE_STANDARD_ERROR | 96.120% | 89.490% |

## Where the gain came from

The rule was designed to save the fees a swap costs. Against the control:

| Path | Cost drag saved | Arithmetic selection gained |
|---|---:|---:|
| SWITCH_HURDLE_ROUND_TRIP_COST | 0.270pp | 2.157pp |
| SWITCH_HURDLE_ROUND_TRIP_COST_PLUS_ONE_STANDARD_ERROR | 0.590pp | 1.441pp |

## Where the gross gap comes from

| Path | Arithmetic selection | Compounding | Geometric gross edge |
|---|---:|---:|---:|
| PUBLISHED_CHALLENGER_NO_HURDLE | 0.040pp | 0.300pp | 0.340pp |
| NO_HURDLE_CONTROL_SAME_LOOP | 0.315pp | 0.405pp | 0.719pp |
| SWITCH_HURDLE_ROUND_TRIP_COST | 2.471pp | 0.734pp | 3.206pp |
| SWITCH_HURDLE_ROUND_TRIP_COST_PLUS_ONE_STANDARD_ERROR | 1.755pp | -0.441pp | 1.314pp |

## Regional attribution

`excessByRegion` sums to `grossExcessReturn`, so the contributions rebuild
the headline. Sleeve figures are weight-normalised. Both carry wide
intervals on 155 blocks split two ways — they locate the question.

| Path | Region | Avg weight | Contribution | 95% CI | Sleeve excess | 95% CI |
|---|---|---:|---:|---|---:|---|
| PUBLISHED_CHALLENGER_NO_HURDLE | KR | 50.954% | -1.457pp | [-8.575pp, 5.165pp] | -0.579pp | [-12.460pp, 10.986pp] |
| PUBLISHED_CHALLENGER_NO_HURDLE | US | 18.531% | 1.496pp | [-0.634pp, 3.761pp] | 10.488pp | [-2.543pp, 24.615pp] |
| NO_HURDLE_CONTROL_SAME_LOOP | KR | 49.790% | -0.467pp | [-7.272pp, 5.743pp] | 1.935pp | [-9.218pp, 12.933pp] |
| NO_HURDLE_CONTROL_SAME_LOOP | US | 19.793% | 0.781pp | [-1.178pp, 2.922pp] | 8.364pp | [-4.758pp, 22.496pp] |
| SWITCH_HURDLE_ROUND_TRIP_COST | KR | 50.668% | 0.335pp | [-6.071pp, 6.309pp] | 1.651pp | [-9.229pp, 12.154pp] |
| SWITCH_HURDLE_ROUND_TRIP_COST | US | 18.538% | 2.136pp | [-0.261pp, 4.599pp] | 14.057pp | [0.731pp, 27.762pp] |
| SWITCH_HURDLE_ROUND_TRIP_COST_PLUS_ONE_STANDARD_ERROR | KR | 47.155% | -1.377pp | [-8.552pp, 5.312pp] | -1.630pp | [-14.448pp, 11.334pp] |
| SWITCH_HURDLE_ROUND_TRIP_COST_PLUS_ONE_STANDARD_ERROR | US | 23.453% | 3.132pp | [-0.442pp, 7.295pp] | 13.833pp | [-0.371pp, 28.970pp] |

## Control fidelity

The no-hurdle control through this loop lands at -0.684pp against the published challenger's -1.046pp. It is NOT expected to match:

`portfolio_replay` builds its ExpandingBucketCalibration on cost-adjusted excess returns (the constructor default); this runner follows `benchmark_alpha` and builds it on GROSS excess returns, because a rule that subtracts costs itself must not be handed an alpha that already has them removed. The two therefore rank on different quantities and the control is NOT expected to reproduce the published path byte for byte. It is the baseline for the hurdle regardless, and the gap below is what a reader must not attribute to the hurdle.

The hurdle is therefore measured against the control, never against the
published path.

## Paired differences against the no-hurdle control

- SWITCH_HURDLE_ROUND_TRIP_COST minus NO_HURDLE_CONTROL_SAME_LOOP: Δ annualized excess 2.757pp, 95% CI [0.122pp, 5.732pp].
- SWITCH_HURDLE_ROUND_TRIP_COST_PLUS_ONE_STANDARD_ERROR minus NO_HURDLE_CONTROL_SAME_LOOP: Δ annualized excess 1.185pp, 95% CI [-6.814pp, 10.263pp].

## Reading

**BENCHMARK_BEATEN**

Against its own no-hurdle control, which shares every other part of this loop, hurdling the replacement decision moves net excess from -0.684pp to 2.072pp (SWITCH_HURDLE_ROUND_TRIP_COST), 0.500pp (SWITCH_HURDLE_ROUND_TRIP_COST_PLUS_ONE_STANDARD_ERROR), with annual one-way turnover going from 4.679x to 3.567x, 2.814x. The published challenger sits at -1.046pp, but it is not the baseline for this comparison: see controlFidelity.

A path with positive net excess on sealed history is a hypothesis for prospective shadow collection, not a promotion. Freeze it and judge forward.

A rung ending higher than another is a point estimate on sealed history.
It is not evidence to promote a selector.
