# Dynamic breadth v1 — design

> Research CHALLENGER. Score formula, region/sector caps, cash floor and
> position sizing byte-for-byte unchanged, `promotionEligible` stays `false`
> and production is unchanged.

## Why this study exists

Study 2 of the four pre-registered by `alpha-reliability-v1`
(`docs/alpha-reliability-v1.md`). That study's `breadth_readiness` diagnostic,
measured on the production score before any ladder was read, found that a
fixed count of five is cutting an ordering that does not have five
distinguishable names in it:

- a mean of **3.56** tied pairs sit inside the top five;
- a mean of **2.03** names in ranks 6-10 cannot be told apart from the fifth;
- the decision-alpha gaps at 3-vs-4, 5-vs-6, 8-vs-9 and 10-vs-11 all cluster
  at a median of **0.000pp**.

`alpha-risk-separation-v1` then showed what happens to that same boundary
when the score's one continuously-varying term is removed: cuts tied on
expected alpha rise from 86.71% to 94.41%. Neither study changed how many
names the book actually holds — both left `targetNames = 5` fixed. This one
changes exactly that, and nothing else.

## The axis, fixed before the result

Breadth is bounded in `[FLOOR, CEILING] = [3, 10]` — the exact numbers
`alpha-reliability-v1` pre-registered for this study, not re-derived here.
`FLOOR = 3` is also production's existing `selection.minNames`; it is not a
new number.

Beyond the floor, one more name is admitted for each consecutive rank (by the
unchanged score) whose **own calibrated alpha estimate** clears zero by at
least `SE_MULTIPLE = 1.0` standard errors — the same multiple and the same
`raw_se × shrinkageFactor` scaling `switch_hurdle.hurdle_scores` already uses
for its own margin, **imported from `switch_hurdle.SE_MULTIPLE` rather than
re-declared**. The walk is monotonic: it examines ranks in score order and
stops at the **first** rank that fails the bar. A later name clearing the bar
after an earlier one failed it is not "distinguishable breadth" — it is the
tail of a ranking whose head already said stop.

No new parameter exists anywhere in this module. `FLOOR`, `CEILING` and
`SE_MULTIPLE` are all inherited from prior, already-committed work.

## Why the test is on the alpha, not the score

The selection **score** is `calibrated alpha ÷ downside volatility ×
entry multiplier` — three different questions blended into one number. The
breadth question is specifically about the **alpha claim's own precision**,
so distinguishability is tested on `expectedExcessReturnPct` and
`standardErrorPct` directly, read from the same
`ExpandingBucketCalibration.expected()` result every rung in this line of
studies already computes. Nothing here fits a new statistic to produce them,
and the SCORE used to rank names is completely unchanged from
`alpha_reliability.CONTROL`.

## What changes, and what does not

`local_cfg` copies production's config and moves **only**
`selection.targetNames`, following the exact discipline
`selection_value.broad_config` already established for a different count.
`maxNamesPerSector` (2), `maxNamesPerRegion` (3), `maxPositionWeight`, the
cash floor, and every cost assumption are untouched.

**This creates a measured, reported interaction.** With two regions and
`maxNamesPerRegion = 3` unchanged, the hard ceiling this book can actually
hold is `2 × 3 = 6` — the pre-registered ceiling of 10 can structurally never
bind in this universe. `breadth_distribution` reports the gap between what
the SE-distinguishability walk *computed* before any cap, and what the book
*actually held* after the region/sector caps trimmed it, plus how often that
trim occurred. Widening those caps is explicitly `region-quota-removal-v1`'s
axis, not this one's, and this study does not touch them.

## What is measured

The same instrumentation the earlier studies built:

- `selection_value.summarize` — path metrics, the arithmetic-selection /
  compounding split, name-replacement / weight-retarget turnover;
- `switch_hurdle.regional_attribution` — each region's contribution to gross
  excess, with intervals;
- `regional_validation.paired_bootstrap` — the paired difference against the
  fixed-five control, read in both directions;
- `breadth_distribution` (new, specific to this study) — the distribution of
  names actually held, the computed-vs-held gap from the region/sector cap
  interaction, and the stop-reason breakdown (floor-bound on thin eligibility,
  alpha not distinguishable, or reached the ceiling).

## What this study does NOT claim

- Not a promotion, not a production change, and not a claim that the dynamic
  rung beats the benchmark going forward.
- Not a search over 3/5/7/10 for whichever scored best on this sample — that
  comparison is exactly what the pre-registration forbade. Only ONE dynamic
  rule is run, specified before the result.
- No permutation null was run here.
- The paired interval, whichever direction it falls, is a point estimate on
  one historical sample, after several rungs across six studies now, with no
  multiplicity correction.
- Nothing here changes `CHAMPION`, the production selector, production
  weights, Kelly, macro policy, regional rotation, `paperTrading` or
  `liveValidated`.

## Reproducing

```
python scripts/run_dynamic_breadth_replay.py <sealed-ledger> \
  --output dynamic-breadth-report.json \
  --markdown dynamic-breadth-report.md
```

The runner refuses to write inside the sealed ledger, digests the ledger tree
before and after the run and raises on any change, and the workflow compares
its output byte-for-byte against the checked-in artifacts in `docs/results/`.
