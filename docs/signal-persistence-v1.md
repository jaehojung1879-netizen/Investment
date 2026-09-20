# Signal persistence v1

## Research question

`regional-switch-hurdle-v1` was built to save the fees a swap costs. It saved
0.270pp of cost drag — and gained **2.157pp of arithmetic stock selection**,
eight times more, which nothing in the cost argument predicts. Holding a name
longer cannot make the name better. What it can do is stop the book acting on a
ranking that was wrong to move.

So the finding that rule actually produced is about the **signal**, not about
costs. This tests it directly.

Read-only research **CHALLENGER** on the sealed replay-v16 ledger. It promotes
nothing and leaves CHAMPION, production selection, Kelly, macro policy,
`paperTrading` and `liveValidated` unchanged.

## Headline, stated the way the evidence supports

**Every point estimate moves the same way and none of the ladder's own intervals
clears zero.** That is the whole result and the order matters:

- The diagnostic's paired difference is **-1.331% per block** with 95% CI
  **[-3.029%, +0.174%]** — the interval **contains** zero.
- Neither smoothing rung separates from its control: k=3 is +0.745pp
  (CI [-4.042, +5.158]), k=6 is +2.974pp (CI **[-0.348**, +6.906]).
- The **only** interval that clears zero is the two-axis combination, and a
  two-axis result is attributable to neither axis.

What is real is the *consistency*: three angles that could each have come out
flat all point the same direction, and the ladder is monotone in its one
parameter. That is corroboration, not proof.

## Diagnostic: are the ranking's newest picks its worst ones?

Parameter-free. At every rebalance the book's names divide into those it just
**ADDED** and those it **RETAINED**. Both were chosen by the same ranking on the
same date under the same constraints; only incumbency separates them. The paired
figure is the within-rebalance difference, so it carries no market-timing term.

| | Mean 21-session benchmark excess | Name-blocks |
|---|---:|---:|
| ADDED | **-0.357%** | 449 |
| RETAINED | **+0.980%** | 273 |
| **Paired ADDED − RETAINED** | **-1.331%** per block, 95% CI [-3.029%, +0.174%] | 131 rebalances |

| Region | ADDED | RETAINED | Difference |
|---|---:|---:|---:|
| KR | -0.710% | +0.230% | -0.940% |
| US | +0.008% | +2.791% | **-2.784%** |

A gap of -1.331% per 21-session block is roughly -15%/yr between the names the
ranking had just picked and the ones it was already holding. It is large, it is
consistent across both regions, and **its interval still contains zero** — 131
paired rebalances is not many and the block-to-block spread is wide.

## Is there room to smooth?

A name's alpha percentile moves a mean of **1.146 points** between consecutive
blocks it appears in (median 1.000, p90 3.000, 3,276 observations). The
percentile is integer-rounded, so the ranking is *nearly stable* in level.

This measurement exists because a signal that barely moves leaves smoothing
nothing to do — and it says the axis the ladder varies is a narrow one. That a
~1-point input change produces a multi-percentage-point output change is exactly
what this repository's determinism invariant already warns about: *"a tiny input
change is not a tiny output change when selection is greedy."* Top-5 of ~24
names means a one-point reorder can swap who makes the cut. It cuts both ways:
the mechanism is plausible, and the result is sensitive.

## Ladder: rank on the signal averaged over the span it forecasts

One axis. No hurdle, same cadence, same caps, same cash floor, same costs.
`k=6` is the forecast horizon in blocks (126 sessions / 21); `k=3` is the
midpoint to the control. Neither is swept, neither was picked from a result.

| Rung | k | Gross CAGR | Cost drag | Net CAGR | Matched benchmark | Net excess | Sharpe | MDD | Turnover |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Latest percentile (**control**) | 1 | 13.564% | 1.404pp | 12.161% | 12.845% | **-0.684pp** | 0.853 | -25.158% | 4.679x |
| Mean over 3 blocks | 3 | 14.181% | 1.387pp | 12.794% | 12.733% | **+0.061pp** | 0.869 | -24.519% | 4.617x |
| Mean over 6 blocks | 6 | 16.519% | 1.427pp | 15.092% | 12.802% | **+2.289pp** | 1.050 | -24.287% | 4.625x |

Paired against the control:

- k=3: Δ +0.745pp, 95% CI [-4.042, +5.158] — contains zero.
- k=6: Δ +2.974pp, 95% CI [-0.348, +6.906] — contains zero.

### The mechanism is NOT the one the hurdle used

| Rung | Arithmetic selection | Compounding | Geometric gross edge | Turnover |
|---|---:|---:|---:|---:|
| k=1 | +0.315pp | +0.405pp | +0.719pp | 4.679x |
| k=3 | +1.137pp | +0.310pp | +1.448pp | 4.617x |
| k=6 | **+2.994pp** | +0.723pp | +3.717pp | **4.625x** |

**Turnover barely moves** (4.679 → 4.625) while arithmetic stock selection goes
from +0.315pp to +2.994pp. Smoothing does not work by trading less; it works by
picking *different names at the same turnover*. The switch hurdle worked the
other way — it cut turnover from 4.679x to 3.567x and held the same kind of
names longer.

The two levers are therefore **orthogonal**, which is why they stack rather than
overlap.

## Smoothing and the hurdle together, reported separately

This moves **two axes at once**, so its number is attributable to neither. It is
here because the combination is what a production rule would actually be.

| | Net excess | Sharpe | MDD | Turnover |
|---|---:|---:|---:|---:|
| Control (k=1, no hurdle) | -0.684pp | 0.853 | -25.158% | 4.679x |
| Smoothing only (k=6) | +2.289pp | 1.050 | -24.287% | 4.625x |
| Hurdle only (`switch-hurdle-v1`) | +2.072pp | 1.057 | -22.311% | 3.567x |
| **Both** | **+3.560pp** | **1.115** | **-22.560%** | 3.506x |

Against the ladder control: Δ **+4.244pp**, 95% CI **[+0.233, +8.712]** — the
only interval in this study that clears zero, and the one that says least about
*why*.

## What this is not

- **Not a promotion.** `promotionEligible` stays `False`, no prospective
  evidence exists, and the calibrated challenger's own selection null still
  returns `INDISTINGUISHABLE_FROM_RANDOM` at best p=0.065.
- **Not a separated ladder.** `separatedFromControl` is empty. The rungs are
  ordered and monotone; that is a pattern, not a rejection of the null.
- **Not free of multiplicity.** This is the third study in a row on one
  historical sample, with several rungs looked at in each, and no correction is
  applied anywhere.
- **Sensitive by construction.** A greedy top-5 cut turns a one-point percentile
  change into a different book. The same property that lets smoothing help is
  the one that makes the estimate fragile.

## Reproduction

```
python scripts/run_signal_persistence_replay.py <sealed-ledger> \
  --output signal-persistence-report.json --markdown signal-persistence-report.md
```

`.github/workflows/signal-persistence.yml` checks out sealed commit
`b71d8cb5ce21815980d28b606852f9294d43cc53` read-only, runs the tests, verifies
the ledger tree digest is unchanged before and after, and `cmp`s against the
checked-in result. Two runs produce byte-identical reports.
