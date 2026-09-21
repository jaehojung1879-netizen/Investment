# Dynamic breadth v1

> Read-only research CHALLENGER on sealed replay-v16 inputs. Score formula,
> region/sector caps, cash floor and position sizing are unchanged, no
> selector is promoted and production is unchanged.

## The question

`alpha-reliability-v1` measured that a fixed count of five cuts an ordering
that does not have five distinguishable names in it. This asks whether
breadth that follows the ranking's own precision — bounded between a floor
of 3 and a ceiling of 10, both pre-registered — loses less information than
the fixed count.

## The axis

| Rung | Breadth rule |
|---|---|
| `LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS` | fixed `targetNames = 5` |
| `DYNAMIC_BREADTH_3_TO_10_SE_DISTINGUISHABLE` | floor 3, ceiling 10, one more name admitted per rank whose own calibrated alpha clears zero by 1.0x its standard error (`switch_hurdle.SE_MULTIPLE`, imported) |

The score is unchanged from `alpha_reliability.CONTROL` on both rungs —
calibrated alpha / downside volatility x entry multiplier. Only the COUNT
of names taken from that same ranking differs.

## The ladder

| Rung | Gross CAGR | Cost drag | Net CAGR | Matched benchmark | Net excess | Vol | Sharpe | MDD | Turnover |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS | 13.564% | 1.404pp | 12.161% | 12.845% | -0.684pp | 11.985% | 0.853 | -25.158% | 4.679x |
| DYNAMIC_BREADTH_3_TO_10_SE_DISTINGUISHABLE | 11.728% | 1.333pp | 10.395% | 11.396% | -1.001pp | 12.025% | 0.719 | -21.336% | 4.416x |

### Where the gross gap comes from

| Rung | Arithmetic selection | Compounding | Geometric gross edge | Block sd ratio |
|---|---:|---:|---:|---:|
| LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS | 0.315pp | 0.405pp | 0.719pp | 0.784x |
| DYNAMIC_BREADTH_3_TO_10_SE_DISTINGUISHABLE | -0.009pp | 0.341pp | 0.332pp | 0.770x |

### Turnover and selection behaviour

| Rung | One-way turnover | Name share | Names held (mean) | Incumbent retention |
|---|---:|---:|---:|---:|
| LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS | 42.170% | 93.470% | 4.658 | 38.080% |
| DYNAMIC_BREADTH_3_TO_10_SE_DISTINGUISHABLE | 38.552% | 91.600% | 3.910 | 38.310% |

### Regional contribution to gross excess

| Rung | US contribution | US 95% CI | KR contribution | KR 95% CI |
|---|---:|---:|---:|---:|
| LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS | 0.781pp | [-1.178pp, 2.922pp] | -0.467pp | [-7.272pp, 5.743pp] |
| DYNAMIC_BREADTH_3_TO_10_SE_DISTINGUISHABLE | -0.053pp | [-1.416pp, 1.314pp] | 0.043pp | [-6.626pp, 6.241pp] |

### Paired difference against the control

Δ annualized net excess: **-0.317pp**, 95% CI [-2.133pp, 1.425pp], over 155 paired blocks.

This interval CONTAINS zero.

## How wide did the dynamic-breadth book actually run?

- Names held: mean **3.91**, median 3.0, range [0, 6].
- The SE-distinguishability walk itself computed a target averaging **4.290** before any cap was applied.
- **17.420%** of rebalances held FEWER names than the walk defended, because the region or sector cap trimmed the book below its computed target — those caps are
unchanged and out of scope for this study.
- The walk reached the ceiling of 10 on **4.520%** of rebalances.

| Stop reason | Rebalances |
|---|---:|
| `ALPHA_NOT_DISTINGUISHABLE_FROM_ZERO` | 138 |
| `FEWER_THAN_FLOOR_ELIGIBLE` | 10 |
| `REACHED_CEILING` | 7 |

## Reading

**BENCHMARK_NOT_BEATEN**

Net excess moves from -0.684pp (fixed five) to -1.001pp (dynamic 3-10). Paired difference -0.317pp, 95% CI [-2.133pp, 1.425pp], which CONTAINS zero. The book held a mean of 3.91 names (range [0, 6]) against the control's fixed five, and 17.420% of rebalances were trimmed below their computed target by the unchanged region/sector caps — the ceiling of 10 was rarely if ever the binding constraint in a two-region universe.

### Refuted

- Nothing was refuted by its own pre-specified test.

### Next direction

The region-cap interaction measured here is itself evidence for `region-quota-removal-v1`: a breadth rule that wants more names than two regions at a cap of three each can hold is being trimmed by a constraint neither this study nor `alpha-risk-separation-v1` touches. `region-quota-removal-v1` and `entry-selection-separation-v1` remain pre-registered and untouched by this result.

A rung ending higher than another is a point estimate on sealed history,
after several rungs across six studies, with no multiplicity correction.
It is not evidence to promote a selector.
