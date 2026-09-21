# Alpha reliability v1

> Read-only research CHALLENGER on sealed replay-v16 inputs. No factor is
> added, no factor weight moves, no selector is promoted and production is
> unchanged.

## The question

`selection_value` found 92-93% of turnover is names being REPLACED.
`regional-switch-hurdle-v1` saved 0.270pp of cost drag and gained 2.157pp of
arithmetic stock selection, which no cost argument predicts.
`signal-persistence-v1` found ADDED names realise less than RETAINED ones on a
paired interval that contains zero. All three point at the same place: the
conversion from a continuous signal into a discrete five-name book. This
measures that conversion and then tries to spend the SAME signal more
carefully — level, then persistence, then confidence.

## The axis, measured before the ladder was read

The pool's alpha percentiles run 91.000 to 100.000 (mean 97.353, sd 2.330) over 3720 pool name-dates. The calibration's bucket edges are
`[0, 60, 80, 90, 95, 100]`, so only **2 buckets** are ever occupied and **83.550%** of name-dates fall in the
largest one. Names inside a bucket are handed the SAME expected excess, so for
most of the pool the ranking's alpha term is a constant and the ordering is
decided by realised downside volatility alone.

| Bucket | Name-dates |
|---|---:|
| 90-95 | 612 |
| 95-100 | 3108 |

| Input | mean | sd | p10 | median | p90 |
|---|---:|---:|---:|---:|---:|
| own percentile sd over k=6 | 1.242 | 0.843 | 0.408 | 1.000 | 2.483 |
| cross-section percentile sd | 1.779 | 0.864 | 0.793 | 1.735 | 2.701 |
| sleeve agreement | 0.526 | 0.222 | 0.250 | 0.499 | 0.850 |
| evidence coverage (already in the level) | 0.760 | 0.179 | 0.450 | 0.827 | 0.927 |

`evidenceCoverage` is listed because `longterm` computes
`alpha = rawAlpha x evidenceCoverage` BEFORE the percentile is taken. It has
already shrunk the level, so it is not available as a confidence weight —
using it again would charge the same doubt twice.

## How unstable is the top-5 boundary?

### At the cut, control

- Measured on 91 rebalances; 54 more had every near miss stopped by a sector or region cap, so the cut there was made by the diversification rules and is not read as a ranking boundary.
- Expected-alpha gap between the last name held and the first excluded: mean -0.106pp, median 0.000pp.
- **81.320%** of those cuts are a TIE on expected alpha — the calibration cannot tell the two names apart and the cut is made by downside volatility.
- Alpha percentile gap at the cut: mean 0.440 points.

### At the cut, confidence + hysteresis rung

- Measured on 118 rebalances; 27 more had every near miss stopped by a sector or region cap, so the cut there was made by the diversification rules and is not read as a ranking boundary.
- Expected-alpha gap between the last name held and the first excluded: mean -0.125pp, median 0.000pp.
- **66.100%** of those cuts are a TIE on expected alpha — the calibration cannot tell the two names apart and the cut is made by downside volatility.
- Alpha percentile gap at the cut: mean 0.927 points.

### At the swap, control

- 131 rebalances replaced at least one name.
- Expected-alpha gap between the arriving and the departing name: mean -0.476pp, median -0.577pp.
- **29.770%** of swaps are between two names the calibration scores IDENTICALLY.
- Of 412 held names whose raw percentile moved one point or less since the previous block, **47.820%** were replaced anyway.

| Swap population | Arriving minus departing, next block | Win rate | 95% CI | n |
|---|---:|---:|---:|---:|
| all swaps | 0.521% | 50.380% | [-1.756%, 2.924%] | 131 |
| tied on expected alpha | -2.601% | 38.460% | [-5.510%, 0.024%] | 39 |
| separated on expected alpha | 1.845% | 55.430% | [-1.075%, 5.005%] | 92 |

## The ladder

One axis per rung. No transaction-cost hurdle anywhere in the ladder.

| Rung | Gross CAGR | Cost drag | Net CAGR | Matched benchmark | Net excess | Vol | Sharpe | MDD | Turnover |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS | 13.564% | 1.404pp | 12.161% | 12.845% | -0.684pp | 11.985% | 0.853 | -25.158% | 4.679x |
| PERSISTENT_ALPHA_ONLY | 16.519% | 1.427pp | 15.092% | 12.802% | 2.289pp | 12.222% | 1.050 | -24.287% | 4.625x |
| PERSISTENT_ALPHA_X_SIGNAL_CONFIDENCE | 12.421% | 1.330pp | 11.091% | 12.786% | -1.695pp | 12.681% | 0.737 | -28.024% | 4.535x |
| PERSISTENT_ALPHA_X_CONFIDENCE_PLUS_SIGNAL_HYSTERESIS | 13.174% | 0.847pp | 12.328% | 13.734% | -1.406pp | 12.333% | 0.844 | -28.432% | 2.955x |

### Where the gross gap comes from

| Rung | Arithmetic selection | Compounding | Geometric gross edge | Block sd ratio |
|---|---:|---:|---:|---:|
| LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS | 0.315pp | 0.405pp | 0.719pp | 0.784x |
| PERSISTENT_ALPHA_ONLY | 2.994pp | 0.723pp | 3.717pp | 0.820x |
| PERSISTENT_ALPHA_X_SIGNAL_CONFIDENCE | -0.454pp | 0.090pp | -0.364pp | 0.908x |
| PERSISTENT_ALPHA_X_CONFIDENCE_PLUS_SIGNAL_HYSTERESIS | -0.361pp | -0.199pp | -0.560pp | 1.059x |

### Turnover: names replaced against weights retargeted

| Rung | One-way turnover | From name replacement | From weight retarget | Name share | US retention | KR retention |
|---|---:|---:|---:|---:|---:|---:|
| LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS | 42.170% | 39.417% | 2.752% | 93.470% | 41.240% | 53.170% |
| PERSISTENT_ALPHA_ONLY | 41.592% | 38.846% | 2.747% | 93.400% | 40.200% | 57.180% |
| PERSISTENT_ALPHA_X_SIGNAL_CONFIDENCE | 40.938% | 38.314% | 2.624% | 93.590% | 37.840% | 59.550% |
| PERSISTENT_ALPHA_X_CONFIDENCE_PLUS_SIGNAL_HYSTERESIS | 25.896% | 20.035% | 5.861% | 77.370% | 89.900% | 86.470% |

### Selection behaviour

| Rung | Names held | Retained | Added | Incumbent retention | Replacement rate |
|---|---:|---:|---:|---:|---:|
| LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS | 4.658 | 1.761 | 2.897 | 38.080% | 61.920% |
| PERSISTENT_ALPHA_ONLY | 4.658 | 1.800 | 2.858 | 38.910% | 61.090% |
| PERSISTENT_ALPHA_X_SIGNAL_CONFIDENCE | 4.658 | 1.819 | 2.839 | 39.330% | 60.670% |
| PERSISTENT_ALPHA_X_CONFIDENCE_PLUS_SIGNAL_HYSTERESIS | 4.658 | 3.103 | 1.555 | 67.090% | 32.910% |

### Regional contribution to gross excess

| Rung | US contribution | US 95% CI | KR contribution | KR 95% CI |
|---|---:|---:|---:|---:|
| LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS | 0.781pp | [-1.178pp, 2.922pp] | -0.467pp | [-7.272pp, 5.743pp] |
| PERSISTENT_ALPHA_ONLY | 1.188pp | [-0.759pp, 3.296pp] | 1.806pp | [-5.188pp, 8.314pp] |
| PERSISTENT_ALPHA_X_SIGNAL_CONFIDENCE | 0.305pp | [-1.948pp, 2.605pp] | -0.759pp | [-8.575pp, 6.230pp] |
| PERSISTENT_ALPHA_X_CONFIDENCE_PLUS_SIGNAL_HYSTERESIS | 2.429pp | [-0.442pp, 5.414pp] | -2.790pp | [-9.458pp, 3.296pp] |

### Paired differences, one axis at a time

Each rung against the rung BELOW it, which differs from it in exactly one
thing. The cumulative column is the same rung against the ladder control.

| Rung | Δ vs rung below | 95% CI | Δ vs control | 95% CI | Blocks |
|---|---:|---:|---:|---:|---:|
| PERSISTENT_ALPHA_ONLY | 2.974pp | [-0.348pp, 6.906pp] | 2.974pp | [-0.348pp, 6.906pp] | 155 |
| PERSISTENT_ALPHA_X_SIGNAL_CONFIDENCE | -3.984pp | [-8.144pp, -0.214pp] | -1.010pp | [-5.701pp, 3.047pp] | 155 |
| PERSISTENT_ALPHA_X_CONFIDENCE_PLUS_SIGNAL_HYSTERESIS | 0.288pp | [-4.430pp, 5.416pp] | -0.722pp | [-7.195pp, 5.570pp] | 155 |

## Stacked with the transaction-cost hurdle, reported separately

This adds the `regional-switch-hurdle-v1` cost credit on top of the last
ladder rung, so it moves TWO axes and its number is attributable to
neither. It is here because a production rule would carry both, not
because it is evidence for either.

- Net excess **-0.184pp**, Sharpe 0.879, MDD -29.085%, turnover 2.818x.
- Against the last ladder rung: Δ 1.223pp, 95% CI [-0.735pp, 3.223pp].

## Reading

**BENCHMARK_BEATEN** — The verdict reads the best rung's POINT ESTIMATE against its matched benchmark and says nothing about whether that rung is distinguishable from the control. It is not: its paired interval against the control contains zero.

The pool occupies 2 calibration buckets and 83.550% of its name-dates sit in one of them, so 81.320% of the control's top-5 cuts and 29.770% of its swaps are between names the calibration scores IDENTICALLY — ordered by realised downside volatility, not by alpha. Net excess moves from -0.684pp at the control to 2.289pp (PERSISTENT_ALPHA_ONLY), -1.695pp (PERSISTENT_ALPHA_X_SIGNAL_CONFIDENCE), -1.406pp (PERSISTENT_ALPHA_X_CONFIDENCE_PLUS_SIGNAL_HYSTERESIS).

### What separated, and in which direction

An interval that excludes zero from BELOW is as much a separation as one
that excludes it from above, and it is the more informative of the two:
it means a pre-specified axis made the path measurably worse.

- PERSISTENT_ALPHA_X_SIGNAL_CONFIDENCE separated against the rung below, **WORSE**: -3.984pp, 95% CI [-8.144pp, -0.214pp].
- Nothing separated against the ladder control.

### Refuted

- PERSISTENT_ALPHA_X_SIGNAL_CONFIDENCE: the axis this rung adds made the path WORSE than the rung below it by -3.984pp of annualized net excess, 95% CI [-8.144pp, -0.214pp], which EXCLUDES zero. The hypothesis behind it is refuted by its own pre-specified test and the rule is kept, not deleted, so the instrument that produced the answer survives.
- Shrinking the alpha PERCENTILE toward a neutral percentile: the pool sits at 91-100, so shrinking toward the pool mean moves weak names UP into the top bucket and shrinking toward 50 collapses every name into one bucket. The confidence weight is applied in alpha space instead.
- Evidence coverage and factor coverage as confidence weights: `longterm` already computes alpha = rawAlpha x evidenceCoverage before the percentile is taken, so both are inside the level and reusing them charges the same doubt twice.
- 'A one-point percentile change flips a holding' as the mechanism: the percentile only reaches the decision through a five-edge bucket map, so most one-point moves change nothing and most swaps happen between names with no alpha difference at all.

### Frozen candidate for prospective validation

**NONE — see below**

NOTHING IS FROZEN. The freeze rule is that a candidate is carried into prospective validation only if no axis it contains was refuted by its own paired test. PERSISTENT_ALPHA_X_SIGNAL_CONFIDENCE: the axis this rung adds made the path WORSE than the rung below it by -3.984pp of annualized net excess, 95% CI [-8.144pp, -0.214pp], which EXCLUDES zero. The hypothesis behind it is refuted by its own pre-specified test and the rule is kept, not deleted, so the instrument that produced the answer survives. That condition was NOT in the original design, which named the last rung unconditionally; it was added after the first full run returned this refutation, and the record says so rather than pretending otherwise. What makes it a tightening rather than a re-specification: no rung, parameter, window or scoring rule changed, every number here is what that run produced, and the condition can only ever REMOVE a candidate — it cannot promote one and it cannot make a refuted axis look better. So this study freezes no new candidate, the `signal-persistence-v1` k=6 rung stands as the one already frozen, and the refuted rule is kept rather than deleted. What the boundary diagnostic established is independent of the ladder and stands whatever the rungs did.

A rung ending higher than another is a point estimate on sealed history,
after several rungs across four studies, with no multiplicity correction.
It is not evidence to promote a selector.
