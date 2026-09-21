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

- Measured on 143 rebalances; 2 more had every near miss stopped by a sector or region cap, so the cut there was made by the diversification rules and is not read as a ranking boundary.
- Expected-alpha gap between the last name held and the first excluded: mean -0.066pp, median 0.000pp.
- **86.710%** of those cuts are a TIE on expected alpha — the calibration cannot tell the two names apart and the cut is made by downside volatility.
- Alpha percentile gap at the cut: mean 0.301 points.

### At the cut, confidence + hysteresis rung

- Measured on 143 rebalances; 2 more had every near miss stopped by a sector or region cap, so the cut there was made by the diversification rules and is not read as a ranking boundary.
- Expected-alpha gap between the last name held and the first excluded: mean -0.098pp, median 0.000pp.
- **68.530%** of those cuts are a TIE on expected alpha — the calibration cannot tell the two names apart and the cut is made by downside volatility.
- Alpha percentile gap at the cut: mean 0.725 points.

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

## What actually decides the book (observational)

None of this section added a rung, changed a score or moved a constraint.
The `lowvol` sleeve weight, the downside-volatility denominator, the
inverse-downside-volatility sizing, the entry multipliers, the region and
sector caps and `targetNames = 5` are all exactly as the ladder ran them.

### A. Alpha or low volatility?

| Reading | Control | + confidence + hysteresis |
|---|---:|---:|
| Spearman(score, alpha percentile) | -0.035 | 0.063 |
| Spearman(score, calibrated alpha) | 0.758 | 0.290 |
| Spearman(score, downside vol) | 0.075 | 0.044 |
| Downside vol of names held | 24.445 | 25.379 |
| Downside vol of names rejected | 27.172 | 26.880 |
| `lowvol` sleeve percentile, held | 74.374 | 70.505 |
| `lowvol` sleeve percentile, rejected | 63.808 | 65.019 |
| `lowvol` is the name's highest sleeve | 32.690% | 28.530% |
| `lowvol` is in its top two sleeves | 58.860% | 53.880% |
| Held set matching an alpha-only top-N | 30.070% | 30.710% |
| Held below the alpha top-N with below-median risk | 262 | 230 |
| In the alpha top-N but dropped with above-median risk | 102 | 132 |
| Held/not-held pairs the alpha term orders the other way | 37.521% | 40.691% |

### B. The entry state's step function

- States observed: `{'ACCUMULATE_GRADUALLY': 996, 'AVOID': 299, 'EVENT_RISK': 3, 'WAIT_FOR_PULLBACK': 1676, 'WATCH': 746}`.
- 1740 state transitions, **26.320%** of them on a name this rebalance moved in or out.
- 260 transitions into a state that blocks sizing outright; 39 departures had one.
- **114** departures where the multiplier fell while the name's own alpha percentile moved a point or less — the step function, not the signal, deciding.

| Transition | Count | Of those, on a name moved in or out |
|---|---:|---:|
| `WAIT_FOR_PULLBACK -> ACCUMULATE_GRADUALLY` | 312 | 108 |
| `ACCUMULATE_GRADUALLY -> WAIT_FOR_PULLBACK` | 267 | 82 |
| `ACCUMULATE_GRADUALLY -> WATCH` | 235 | 56 |
| `WAIT_FOR_PULLBACK -> WATCH` | 229 | 38 |
| `WATCH -> WAIT_FOR_PULLBACK` | 180 | 35 |
| `WATCH -> ACCUMULATE_GRADUALLY` | 178 | 54 |
| `WATCH -> AVOID` | 98 | 25 |
| `AVOID -> ACCUMULATE_GRADUALLY` | 58 | 22 |

### C. Does the diversification guard override the ranking?

- `maxNamesPerRegion = 3`, `maxNamesPerSector = 2`, on 145 rebalances.
- The region cap stopped a name on **93.100%** of them; the sector cap on 24.140%.
- On **134** rebalances a capped name outscored the lowest-scoring name the book took, by a median decision-alpha gap of 0.856pp.
- Name-dates held by region: `{'KR': 421, 'US': 301}`.
- Same count, caps lifted, by region: `{'KR': 640, 'US': 82}`.
- Most common held shapes: `{'KR:3/US:2': 132, 'KR:2/US:3': 11, 'US:3': 1, 'KR:3/US:1': 1}`.

### D. What a breadth rule would have to work with

`targetNames` stays at five and no breadth rule is implemented or scored.

The near-neutral count is meaningful only where confidence is ON: the
control discards no uncertainty, so its margin is zero by construction
and the count is zero for that reason rather than as a reading.

| Reading | Control | + confidence + hysteresis |
|---|---:|---:|
| Eligible candidates per rebalance (mean) | 20.883 | 20.883 |
| Top-ten names whose doubt exceeds their claim (mean) | 0.000 | 4.276 |
| Tied pairs inside the top five (mean) | 3.559 | 2.945 |
| Ranks 6-10 tied with the fifth name (mean) | 2.034 | 2.255 |
| Decision-alpha dispersion, top five (mean) | 0.111 | 0.366 |
| Decision-alpha dispersion, top ten (mean) | 0.368 | 0.371 |

| Gap in decision alpha | Control mean | Control median |
|---|---:|---:|
| rank10MinusRank11 | 0.031pp | 0.000pp |
| rank3MinusRank4 | 0.064pp | 0.000pp |
| rank5MinusRank6 | 0.144pp | 0.000pp |
| rank8MinusRank9 | 0.108pp | 0.000pp |

### Why each departure happened

444 departures on the control path, attributed once each in the order the machinery applies them.

| Cause | Count | Share |
|---|---:|---:|
| LEFT_THE_RESEARCH_POOL | 160 | 36.040% |
| OUTRANKED_AT_THE_CUT | 150 | 33.780% |
| REGION_CAP | 84 | 18.920% |
| ENTRY_OR_RESEARCH_STATE_TURNED_BLOCKING | 40 | 9.010% |
| SECTOR_CAP | 10 | 2.250% |

For the ones the ranking outranked, the departing name's own move since its previous appearance: percentile -0.627, reliable alpha -0.183pp, confidence 0.000 (means, signed).

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

The pool occupies 2 calibration buckets and 83.550% of its name-dates sit in one of them, so 86.710% of the control's top-5 cuts and 29.770% of its swaps are between names the calibration scores IDENTICALLY — ordered by realised downside volatility, not by alpha. Net excess moves from -0.684pp at the control to 2.289pp (PERSISTENT_ALPHA_ONLY), -1.695pp (PERSISTENT_ALPHA_X_SIGNAL_CONFIDENCE), -1.406pp (PERSISTENT_ALPHA_X_CONFIDENCE_PLUS_SIGNAL_HYSTERESIS).

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

### Five questions this study was asked to answer

**1. What explains the final ordering — alpha or downside risk?**

BOTH, at different places, and only one of them is where the decision happens. Across the whole cross-section the score's rank correlation with the calibrated alpha averages 0.758 against 0.075 with downside volatility, so the alpha term orders most PAIRS. But a five-name book is decided at its margin, and there 86.710% of cuts are between two names the calibration scores identically — the alpha term has two levels and both sides of the cut are almost always on the same one. What settles those is the risk-and-entry product in the denominator. The held set matches an alpha-only top-N only 30.070% of the time and 37.521% of held against not-held pairs are ordered the other way by the alpha percentile.

**2. Does low-volatility dominance survive persistence and confidence?**

The tilt is visible in what is HELD rather than in a large rank correlation, and it narrows without going away. Names held carry downside volatility of 24.445% against 27.172% rejected on the control, and 25.379% against 26.880% on the confidence-plus-hysteresis rung; the `lowvol` sleeve percentile of held names goes 74.374 to 70.505 against 65.019 for the rejected. `lowvol` is among a held name's top two sleeves 58.860% of the time, so part of the tilt arrives through the ALPHA itself and would survive removing the denominator — which is why the pre-registered first study moves the denominator alone and leaves the sleeve for the one after it.

**3. What drove the actual replacements?**

Of 444 departures on the control path: LEFT_THE_RESEARCH_POOL 36.040%, OUTRANKED_AT_THE_CUT 33.780%, REGION_CAP 18.920%, ENTRY_OR_RESEARCH_STATE_TURNED_BLOCKING 9.010%, SECTOR_CAP 2.250%. The diversification guard alone — sector and region caps — accounts for 21.170% of every name this book replaced, and the entry-state step for 9.010%; 114 of those had the multiplier fall while the name's own percentile moved a point or less. Where the ranking did outrank a name, its own percentile had moved -0.627 points and its reliable alpha -0.183pp.

**4. Do a fixed five and the region quota override the signal?**

Yes, and the region quota is the larger of the two. It stopped a name on 93.100% of rebalances and on 134 of 145 the capped name outscored one the book took, by a median decision-alpha gap of 0.856pp. Held name-dates split {'KR': 421, 'US': 301}; at the same count with the caps lifted the ordering wanted {'KR': 640, 'US': 82}. On breadth, 3.559 tied pairs sit inside the top five and 2.034 of ranks 6-10 cannot be separated from the fifth name, so a fixed five is cutting an ordering that does not have five distinguishable names in it.

**5. What should the next study separate first?**

Two structural problems are now measured and they are not the same one. The BIGGEST override is the region quota, which binds on almost every rebalance and turns an ordering that wants one region into a near-fixed 3:2 — but it cannot be lifted yet, because alpha percentiles are computed WITHIN a region and there is no common scale to compare them across one. The problem that can be worked NOW is the double use of downside risk: it sets part of the alpha through the 0.20 lowvol sleeve, divides that alpha to make the score, and then sizes the position. `alpha-risk-separation-v1` removes only the middle use and is the pre-registered first study; the cross-region scale is the prerequisite the quota study has to build before it can run.

### Pre-registered next studies

Specified here, before any of them is run, and in this order. None is
implemented, scored or parameterised by this PR.

**Study 1 — `alpha-risk-separation-v1`**

- Question: Is downside risk being spent twice — once deciding a name's expected alpha and again deciding its capital?
- First axis: Remove ONLY the downside-volatility denominator from the selection ranking. The lowvol sleeve keeps its 0.20 weight inside the four-factor alpha, and inverse-downside-volatility sizing and every portfolio constraint stay exactly as they are, so risk is still managed — it just stops deciding WHICH name.
- Deliberately NOT in the first ladder: Moving the lowvol sleeve out of the alpha layer. If a defensive tilt survives the denominator's removal, that is the NEXT study's axis, not this one's — two risk channels moved together would be attributable to neither.

**Study 2 — `dynamic-breadth-v1`**

- Question: Does a fixed count of five cut an ordering that does not have five distinguishable names in it?
- First axis: Breadth follows signal strength between a floor of 3 and a ceiling of 10, with no fixed target: hold the names whose edge is distinguishable and hold cash when it is not.
- Deliberately NOT in the first ladder: Choosing whichever of 3/5/7/10 scored best on this sample. The hypothesis is that a strength-dependent breadth loses less information and churns less at the boundary than ANY fixed count, and a fitted count would answer a different question.

**Study 3 — `region-quota-removal-v1`**

- Question: Should regional diversification be a name quota at all, or a risk budget?
- First axis: Replace `maxNamesPerRegion` with a portfolio-level risk / covariance / concentration budget, so US 8 / KR 0 or KR 7 / US 1 becomes expressible when that is what the ordering says.
- Prerequisite: Alpha percentiles are computed WITHIN a region, so a Korean 90th and an American 90th are not the same claim. A common cross-region scale has to exist before the quota comes off, or the quota is simply replaced by an artefact of the percentile's construction.

**Study 4 — `entry-selection-separation-v1`**

- Question: Should the entry state decide WHAT is owned, or only how fast a target weight is approached?
- First axis: Separate the roles: alpha decides the held set, entry state decides the path to the target weight — ACCUMULATE to full weight, WATCH to part of it, WAIT_FOR_PULLBACK throttles new entry, EVENT_RISK holds new entry.
- Deliberately NOT in the first ladder: Whether an INCUMBENT should be sold on a technical overheat trigger at all. That is a separate claim about exits and gets its own test.

### Frozen candidate for prospective validation

**NONE — see below**

NOTHING IS FROZEN. The freeze rule is that a candidate is carried into prospective validation only if no axis it contains was refuted by its own paired test. PERSISTENT_ALPHA_X_SIGNAL_CONFIDENCE: the axis this rung adds made the path WORSE than the rung below it by -3.984pp of annualized net excess, 95% CI [-8.144pp, -0.214pp], which EXCLUDES zero. The hypothesis behind it is refuted by its own pre-specified test and the rule is kept, not deleted, so the instrument that produced the answer survives. That condition was NOT in the original design, which named the last rung unconditionally; it was added after the first full run returned this refutation, and the record says so rather than pretending otherwise. What makes it a tightening rather than a re-specification: no rung, parameter, window or scoring rule changed, every number here is what that run produced, and the condition can only ever REMOVE a candidate — it cannot promote one and it cannot make a refuted axis look better. So this study freezes no new candidate, the `signal-persistence-v1` k=6 rung stands as the one already frozen, and the refuted rule is kept rather than deleted. What the boundary diagnostic established is independent of the ladder and stands whatever the rungs did.

A rung ending higher than another is a point estimate on sealed history,
after several rungs across four studies, with no multiplicity correction.
It is not evidence to promote a selector.
