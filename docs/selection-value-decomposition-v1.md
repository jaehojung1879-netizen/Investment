# Selection-value decomposition v1

## Research question

`benchmark-relative-alpha-v1` closed **BENCHMARK_NOT_BEATEN** and proposed
protecting the calibrated challenger's +0.340pp/yr gross edge from turnover with
a replacement hurdle. That proposal rests on two things nobody had measured:
that the +0.340pp is stock selection, and that the gap to the benchmark belongs
to the ranking rather than to the screen that feeds it.

This is a read-only **diagnostic** on the sealed replay-v16 ledger. It changes
no selector, promotes nothing, and leaves CHAMPION, production selection, Kelly,
macro policy, `paperTrading` and `liveValidated` exactly as they were.

## What a CAGR gap was hiding

A CAGR difference answers *which ended richer*. It does not say whether the book
picked better names or simply lost less to variance. Splitting the published
challenger's gross gap:

| | Arithmetic selection | Compounding (volatility) | Geometric gross edge | Block sd vs benchmark |
|---|---:|---:|---:|---:|
| Combined CHAMPION | -1.589pp | -0.141pp | -1.730pp | 0.96x |
| Calibrated challenger | **+0.040pp** | **+0.300pp** | +0.340pp | 0.83x |

**88% of the only positive number in the benchmark-alpha report is a
low-volatility tilt compounding better, not a name picked better.** The book is
*less* volatile than its matched benchmark — it is scored and weighted per unit
of downside volatility — so it keeps more of its own arithmetic mean. The
arithmetic stock-selection edge is +0.040pp/yr.

## Where the turnover goes

The two components have opposite remedies, so one number for both answers
nothing. Weight retargeting is discretionary — carrying the drifted book costs
zero — while name replacement means holding different names.

| | Avg one-way | From name replacement | From weight retarget | Names carried to next block |
|---|---:|---:|---:|---:|
| Combined CHAMPION | 53.42% | 49.21% (92.1%) | 4.21% | 32.9% |
| Calibrated challenger | 41.07% | 38.22% (93.1%) | 2.85% | 39.8% |

A no-retarget band would remove ~7% of the bill. The ~1.4pp/yr is paid for the
ranking's opinion about *which* names, at ~0.30pp per 1x annual one-way
turnover. That rate sets a hard arithmetic constraint: even a rule that
preserved the whole +0.340pp would have to hold turnover under ~1.1x/yr to be
net positive, against 4.56x today.

## The ladder

Three rungs, one matched benchmark each, the same fixed 21-session blocks, the
same PIT research pool, the same production `selection_and_baseline` and
`baseline_weights`, the same realistic cost schedule. Each rung uses the
calibrated challenger ranking for **one more thing** than the rung below:

| Rung | The ranking is used to… |
|---|---|
| `SCREEN_ONLY_RISK_WEIGHTED_NO_RANKING` | nothing. Hold every eligible pool name, inverse-downside-volatility weighted, conviction tilt off. |
| `SCREEN_PLUS_CONVICTION_TILT_NO_CONCENTRATION` | size positions (0.5x–1.5x by rank). Same held set. |
| `SCREEN_PLUS_CONCENTRATION_PUBLISHED_BOOK` | also exclude names — the published ~5-name book. |

Cadence, retargeting, caps, cash floor, entry-state exclusions and costs are
identical across all three. `benchmark-relative-alpha-v1` moved cadence, a cash
gate and the weighting rule together, and its 1.4pp gross loss could not be
attributed to any of them; this ladder moves one thing at a time so each
difference is readable.

This is not a parameter search. Each rung is a fixed point on *how much of the
ranking do you use*, specified before the result was seen, and tilt-off is the
**absence** of the tilt rather than a fitted value for it.

## Result: the hypothesis was refuted

The hypothesis the ladder was built to test — the ranking is not worth its bill,
so hold what the screen approved and stop paying to choose within it — **failed
its own test**.

| Rung | Net excess | Arithmetic selection edge | Annual turnover | Names |
|---|---:|---:|---:|---:|
| Screen only, no ranking | **-2.729pp** | -1.771pp | 3.68x | 21.1 |
| Screen + conviction tilt | **-2.476pp** | -1.501pp | 3.80x | 21.1 |
| Screen + concentration (published) | **-1.046pp** | **+0.040pp** | 4.56x | 4.7 |

Holding the pool broadly is worse, not better, and the arithmetic selection edge
rises **monotonically** with how much of the ranking is used. Breadth halves
name churn and still loses, because what it gives up in ordering exceeds what it
saves in friction. Read the ordering against the paired intervals before taking
it further: `SCREEN_PLUS_CONCENTRATION` minus `SCREEN_PLUS_TILT` is +1.430pp with
95% CI [-3.762, +6.354], which contains zero.

## The null the promotion gate actually needs

`portfolio_validation.selection_null` permutes **one** ranking, so its verdict is
about that ranking and no other. The sealed report publishes a single null built
from `KP.conviction_scores` — the **champion's** score — and it carried no
selector label at all, so the promotion gate in `pipeline.validate` was reading
the champion's verdict whatever selector a promotion concerned. A promotion moves
the **challenger** into production, and the two do not rank alike.

Running the null the gate actually needs, on the same 155 blocks:

| Selector | Annualized excess | Information ratio | Sharpe | Verdict |
|---|---|---|---|---|
| Champion (sealed) | pct 61, p=0.393 | pct 54, p=0.463 | pct 91.5, p=0.090 | INDISTINGUISHABLE_FROM_RANDOM |
| **Challenger (this run)** | pct 87, p=0.134 | pct 84, p=0.164 | **pct 94, p=0.065** | INDISTINGUISHABLE_FROM_RANDOM |

The challenger's ranking sits far above the champion's on all three statistics
and **still does not clear the pre-registered 5% bar on any of them**. It also
trades markedly less than its own null (40.71% against a null median of 66.20%),
so it is not a null that merely churns.

**Two bars are being confused if that is read as the whole answer.** Beating the
permutation null and beating the benchmark are different questions: choosing is
worth roughly +2.9pp/yr against a permuted ranking here (-1.378pp actual against
a -4.324pp null mean), and the book still trails its matched benchmark. The
remaining deficit is implementation, not ordering.

### Gate change

`selection_null` now stamps `selector` and `scoreSource` on every return
including the unavailable ones, `portfolioReplay.promotionEvidence` names the
`promotedSelector`, and `pipeline.validate` refuses a promotion whose null
describes a different selector — or no selector at all. `promotionEligible` is
still hardcoded `False`, so nothing changes today; the hole closes before it can
matter.

## Where this leaves "beat the benchmark"

1. The screen alone loses by 2.7pp/yr. Breadth is **ruled out** as the remedy.
2. The ranking is the only component with any measured signal, it is the
   challenger's rather than the champion's, and it is not yet significant.
3. What remains is implementation: 4.56x/yr turnover at ~0.30pp per 1x, against
   an arithmetic selection edge of +0.040pp.

That leaves the hurdle/hysteresis proposal `benchmark-relative-alpha-v1` already
named — now supported by a measurement instead of by an unsplit CAGR gap, and
now known to be the *only* remaining lever rather than one of several. It must
still be frozen before prospective observations arrive and judged forward.

Nothing here is evidence to promote a selector, and a rung ending higher than
another is not a promotion trigger.

## Reproduction

```
python scripts/run_selection_value_replay.py <sealed-ledger> \
  --output selection-value-report.json --markdown selection-value-report.md
```

`.github/workflows/selection-value.yml` checks out sealed commit
`b71d8cb5ce21815980d28b606852f9294d43cc53` read-only, runs the tests, verifies
the ledger tree digest is unchanged before and after, and uploads the result.
The runner refuses to write inside the ledger and refuses to overwrite an
existing artifact.
