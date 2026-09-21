# Region quota removal v1

> Read-only research CHALLENGER on sealed replay-v16 inputs. Score formula,
> targetNames, maxNamesPerSector, cash floor and position sizing are
> unchanged, no selector is promoted and production is unchanged.

## The question

`alpha-reliability-v1` measured the region cap stopping a name on 93.10% of
rebalances, 134 of 145 times against one that outscored what the book took.
This removes ONLY that cap — `maxNamesPerRegion` opened to `targetNames` — and
asks what the ranking wants when it is left to decide the regional mix itself.

## The prerequisite: is the existing scale comparable across regions?

Alpha percentiles are a within-region rank, so this is answered by the
CALIBRATED score every rung already ranks on — a region-specific expected
benchmark excess in percentage points, read from the CONTROL path's own
candidates, never re-derived.

| Region | Alpha mean | Alpha sd | Shrink mean | Effective dates mean | n |
|---|---:|---:|---:|---:|---:|
| KR | 0.645pp | 0.532pp | 0.299 | 14.076 | 1728 |
| US | 0.041pp | 0.147pp | 0.297 | 13.986 | 1740 |

## The axis

| Rung | Region cap |
|---|---|
| `LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS` | `maxNamesPerRegion = 3` |
| `NO_REGION_QUOTA_SAME_SCORE` | opened to `targetNames` (never itself binding) |

## The ladder

| Rung | Gross CAGR | Cost drag | Net CAGR | Matched benchmark | Net excess | Vol | Sharpe | MDD | Turnover |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS | 13.564% | 1.404pp | 12.161% | 12.845% | -0.684pp | 11.985% | 0.853 | -25.158% | 4.679x |
| NO_REGION_QUOTA_SAME_SCORE | 10.178% | 1.223pp | 8.955% | 11.269% | -2.314pp | 11.879% | 0.615 | -26.209% | 3.673x |

### Where the gross gap comes from

| Rung | Arithmetic selection | Compounding | Geometric gross edge | Block sd ratio |
|---|---:|---:|---:|---:|
| LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS | 0.315pp | 0.405pp | 0.719pp | 0.784x |
| NO_REGION_QUOTA_SAME_SCORE | -1.351pp | 0.260pp | -1.091pp | 0.769x |

### Turnover and selection behaviour

| Rung | One-way turnover | Name share | Names held (mean) | Incumbent retention |
|---|---:|---:|---:|---:|
| LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS | 42.170% | 93.470% | 4.658 | 38.080% |
| NO_REGION_QUOTA_SAME_SCORE | 32.984% | 86.070% | 4.671 | 49.370% |

### Regional mix: what the ranking held once the cap could not stop it

| Rung | Held name-dates by region | Most common shapes |
|---|---|---|
| LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS | `{'KR': 421, 'US': 301}` | `{'KR:3/US:2': 132, 'KR:2/US:3': 11, '': 10, 'US:3': 1}` |
| NO_REGION_QUOTA_SAME_SCORE | `{'KR': 639, 'US': 85}` | `{'KR:5': 102, 'KR:4/US:1': 25, '': 10, 'US:5': 5}` |

### Regional contribution to gross excess

| Rung | US contribution | US 95% CI | KR contribution | KR 95% CI |
|---|---:|---:|---:|---:|
| LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS | 0.781pp | [-1.178pp, 2.922pp] | -0.467pp | [-7.272pp, 5.743pp] |
| NO_REGION_QUOTA_SAME_SCORE | -0.128pp | [-1.076pp, 0.748pp] | -1.223pp | [-8.348pp, 5.188pp] |

### Paired difference against the control

Δ annualized net excess: **-1.630pp**, 95% CI [-4.462pp, 0.961pp], over 155 paired blocks.

This interval CONTAINS zero.

## Reading

**BENCHMARK_NOT_BEATEN**

Net excess moves from -0.684pp (3-cap) to -2.314pp (quota opened). Paired difference -1.630pp, 95% CI [-4.462pp, 0.961pp], which CONTAINS zero. Held name-dates move from {'KR': 421, 'US': 301} under the cap to {'KR': 639, 'US': 85} once it is opened. The US-minus-KR shrinkage gap on the control's own candidates is -0.002 — the two regions' calibrations are not systematically different in shrinkage on this sample.

### Refuted

- Nothing was refuted by its own pre-specified test.

### Next direction

This rung tested only whether the COUNT quota binds; it did not build the portfolio-level risk or covariance budget the pre-registration named as the eventual replacement, and does not claim to. `entry-selection-separation-v1` remains pre-registered and untouched by this result.

A rung ending higher than another is a point estimate on sealed history,
after several rungs across seven studies, with no multiplicity correction.
It is not evidence to promote a selector.
