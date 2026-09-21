# Region quota removal v1 — design

> Research CHALLENGER. Score formula, `targetNames`, `maxNamesPerSector`, cash
> floor and position sizing byte-for-byte unchanged, `promotionEligible` stays
> `false` and production is unchanged.

## Why this study exists

Study 3 of the four pre-registered by `alpha-reliability-v1`
(`docs/alpha-reliability-v1.md`). That study's structural diagnostics found
the region cap is a bigger source of turnover than the ranking's own opinion:
`maxNamesPerRegion = 3` stopped a name on **93.10%** of control rebalances,
and on **134 of 145** the stopped name outscored one the book took (median
decision-alpha gap **0.856pp**). Held name-dates split KR 421 / US 301 under
the cap where the same count with the caps lifted wanted KR 640 / US 82.
`dynamic-breadth-v1` then measured the same cap binding **17.42%** of its
rebalances even in a study that was not asking about regions at all. This
study removes it directly, and only it.

## The prerequisite, answered by measurement before the ladder is read

`alpha-reliability-v1`'s own pre-registration named a prerequisite: alpha
percentiles are a **within-region** rank, so a Korean 90th and an American
90th are not the same claim, and removing the quota needs a common scale
first or the result is just an artefact of the percentile's construction.

That scale already exists and this study does not invent a second one.
`ExpandingBucketCalibration.expected(region, percentile)` converts a
within-region percentile into a region-specific calibrated expected
**benchmark excess**, in percentage points, against that region's own
matched benchmark — the same quantity every rung in this line of studies
already ranks on. `calibration_comparability` reads that quantity from the
control path's own candidates, split by region, before the ladder is read:

| Region | Alpha mean | Alpha sd | Shrink mean | Effective dates mean | n |
|---|---:|---:|---:|---:|---:|
| KR | 0.645pp | 0.532pp | 0.299 | 14.076 | 1728 |
| US | 0.041pp | 0.147pp | 0.297 | 13.986 | 1740 |

The shrinkage means and effective-date counts are nearly identical between
regions (US-minus-KR shrinkage gap **-0.002**) — the comparability artefact
the prerequisite warned about, thinner history in one region pulling its
calibrated alpha harder toward zero, is **not present** on this sample. What
the table shows instead is a real, measured difference in the **level**: the
calibrated alpha the pool assigns Korean names averages **0.645pp**, against
**0.041pp** for American names — roughly 16x. Whatever the ladder below
finds, it is not being confounded by a shrinkage asymmetry; it is a
consequence of what the calibration already believes about each region's
opportunity.

## The axis, and only the axis

| Rung | Region cap |
|---|---|
| `alpha_reliability.CONTROL` | `maxNamesPerRegion = 3` |
| `NO_REGION_QUOTA_SAME_SCORE` | opened to `targetNames` (5) — never itself binding |

`local_cfg` copies production's config and moves **only**
`selection.maxNamesPerRegion`, opened to `targetNames` rather than to
infinity — the same "cap set equal to the count it cannot usefully exceed"
pattern `selection_value.broad_config` already established for a different
cap. `maxNamesPerSector` (2), `targetNames` (5), the cash floor, and every
cost assumption are untouched. Breadth stays fixed at the production
`targetNames = 5` on both rungs — stacking this with `dynamic-breadth-v1`'s
adaptive count would move two axes at once and is left for a stacked
reference path, never the ladder itself.

## What this is not

Not a promotion, not a production change, and not the "portfolio-level
risk/covariance/concentration budget" the pre-registration named as the
eventual destination — building a covariance-based concentration budget is
substantially more machinery than a single-axis ablation should introduce at
once, and every study in this line moves exactly one thing. This rung
answers the narrower, prior question: does the ranking, left alone, want a
different regional mix than the quota allows, and does letting it have one
help.

## Result (two byte-identical sealed replays)

| | 3-cap (control) | Quota opened |
|---|---:|---:|
| Net excess | -0.684pp | **-2.314pp** |
| Gross CAGR | 13.564% | 10.178% |
| Sharpe | 0.853 | 0.615 |
| MDD | -25.158% | -26.209% |
| One-way turnover | 4.679x | 3.673x |
| Held name-dates | KR 421 / US 301 | **KR 639 / US 85** |

Opening the cap moves the book almost entirely into Korea — KR 639 / US 85,
against KR 421 / US 301 under the cap, and matching `alpha-reliability-v1`'s
earlier caps-lifted measurement (KR 640 / US 82) almost exactly. That
agreement is itself a finding: two independently built measurements of "what
the ranking wants without the region cap" land on the same regional split,
which is what the prerequisite check above explains — the calibration
assigns Korean names roughly 16x the expected excess it assigns American
ones, so an unconstrained ranking piles in.

**The paired difference against the control is -1.630pp, 95% CI
[-4.462pp, +0.961pp] over 155 blocks — CONTAINS ZERO.** Nothing here is
refuted by its own pre-specified test: the interval does not clear zero in
either direction. The point estimate is worse, consistent with
`alpha-risk-separation-v1`'s and `dynamic-breadth-v1`'s point estimates, but
none of the three separates from its control on this sample.

### Where the gross gap comes from

| Rung | Arithmetic selection | Compounding | Geometric gross edge |
|---|---:|---:|---:|
| Control | 0.315pp | 0.405pp | 0.719pp |
| Quota opened | -1.351pp | 0.260pp | -1.091pp |

The entire gross gap is arithmetic stock selection, not a volatility-tilt
effect: the KR-heavy book is not just concentrated, it is choosing names that
underperformed their own region's benchmark by more than the diversified
book's names did.

## What is measured

The same instrumentation the earlier studies built, plus two additions
specific to this study's axis:

- `selection_value.summarize`, `switch_hurdle.regional_attribution`,
  `regional_validation.paired_bootstrap` — reused unchanged;
- `calibration_comparability` (new) — the pre-ladder scale check above, read
  from the control path's own candidate stream;
- `region_mix` (new) — held name-dates by region and the rebalance-level
  region "shape" (e.g. `KR:3/US:2`), so the regional swing is a measured
  count, not an inference from the summary contribution table.

## What this study does NOT claim

- Not a promotion, not a production change.
- Not a claim that Korea is a better market than the US in general — the
  calibrated alpha level is a property of this research pool's expanding
  bucket calibration on this replay sample, not an independent macro view.
- Not a claim that the region cap is *wrong* to exist — the opposite reading
  is at least as consistent with the result: the cap may be providing real
  diversification the single-region concentration this rung produces gives
  up, at a cost (in what the ranking itself would have picked) that this
  study quantifies but does not adjudicate.
- No permutation null was run here.
- The paired interval is a point estimate on one historical sample, after
  several rungs across seven studies now, with no multiplicity correction.
- Nothing here changes `CHAMPION`, the production selector, production
  weights, Kelly, macro policy, regional rotation, `paperTrading` or
  `liveValidated`.

## Reproducing

```
python scripts/run_region_quota_removal_replay.py <sealed-ledger> \
  --output region-quota-removal-report.json \
  --markdown region-quota-removal-report.md
```

The runner refuses to write inside the sealed ledger, digests the ledger tree
before and after the run and raises on any change, and the workflow compares
its output byte-for-byte against the checked-in artifacts in `docs/results/`.
