# Alpha calibration resolution v1 — design

> Research CHALLENGER. The four-factor alpha, the calibration table and its
> bucket edges, the selection score's downside-volatility denominator, entry
> logic, region/sector caps, `targetNames = 5`, the cash floor, inverse-vol
> sizing, transaction costs, benchmark construction and the rebalance
> schedule are unchanged and IDENTICAL on both rungs. `promotionEligible`
> stays `false` and production is unchanged.

## Where this came from

`alpha-reliability-v1` measured that the research pool's percentiles run
91-100 and the calibration's edges are `(0, 60, 80, 90, 95, 100)`, so 83.55%
of candidate name-dates sit in one of two occupied buckets and 86.71% of the
control's top-5 cuts are between names the calibration scores IDENTICALLY.
Four single-axis interventions downstream of that fact — the selection
score's risk denominator (`alpha-risk-separation-v1`), dynamic breadth
(`dynamic-breadth-v1`), the region quota (`region-quota-removal-v1`), and the
`lowvol` sleeve inside the alpha (`lowvol-alpha-separation-v1`) — were each
removed in turn and none separated from its control.

This study moves the question from the FACTOR COMPOSITION that feeds the
calibration to the CALIBRATION LAYER itself:

> Among candidates the calibration has already collapsed to one calibrated
> expected excess, does the `alphaPercentile` ordering it discards still
> carry value — restored WITHOUT ever letting a name cross a DIFFERENT
> calibration level?

## The one axis

| Rung | Ranking |
|---|---|
| `LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS` | `alpha_reliability.CONTROL`, called directly |
| `WITHIN_CALIBRATION_ORDINAL_RESCUE` | Same score VALUES at every position; within each `(region, calibrationBucket)` group only, the IDENTITY occupying a position is reassigned by `alphaPercentile` descending |

## Why this does not rebuild the selector

`kelly_portfolio.select_portfolio_by_scores` always re-sorts candidates by
`(-score, ticker)` before calling `_select_scored` — reordering candidate
ROWS and handing them to that function in a new order changes nothing,
because the re-sort erases any ordering that is not carried in the SCORE
FIELD itself. `rescue_scores` therefore never permutes rows: for every
within-group swap it keeps the exact SCORE VALUE that occupied a given
Control rank and reassigns which candidate's row carries it. This is why
`select_portfolio_by_scores` and `_select_scored` run completely unmodified —
`verify_reproduces_control` checks this mechanically on small fixtures, and
`assert_noop_blocks_match_control` checks it on every one of the sealed
replay's own 155 blocks: a block with an EMPTY swap list must reproduce
Control's held set exactly, by mathematical construction, at zero extra
computation cost. Both checks passed on the full sealed replay.

Cross-calibration order is never touched: a candidate is only ever
reassignable INSIDE its own group's existing position set, so a name from a
lower calibration level can never be pulled above a name from a higher one.

Grouping is restricted to `eligible=True` rows with a non-`None`
`calibrationBucket`, and every group's members share one REGION by
construction — so a swap can change which SECTOR occupies a position (a
`SECTOR_NAME_LIMIT` cascade is possible and is measured) but a region-cap
cascade is structurally impossible. This is measured, not assumed: of 862
changed name-dates, 0 rebalances with at least one swap showed a changed
regional shape in the held set.

## Harness fidelity — read directly, no reconstruction

Unlike `lowvol-alpha-separation-v1`, which had to rebuild alpha from stored
sleeve percentiles because the sealed ledger has no z-scores, this study
reads `alphaPercentile`, `calibrationBucket` and
`expectedGrossBenchmarkExcessPct` DIRECTLY from `alpha_reliability
.reliability_scores`'s own sealed output. There is no reconstruction step and
no harness-fidelity gap to publish.

## Stage A — information-loss diagnostic (read before the ladder)

Measured on the CONTROL path's own scored candidates, over the full 155-block
replay:

- Total eligible candidate name-dates: **3,028**
- Distinct `(region, calibrationBucket)` levels: **3**
- Largest level's share of all eligible name-dates: **53.70%**
- Within-level `alphaPercentile` range: mean **2.979** points (sd 1.197)

The calibration compresses hard, exactly as `alpha-reliability-v1` found, and
there is real ordinal spread inside a level for it to discard.

## Stage B — within-calibration information (evaluation only)

- Pairwise concordance (higher percentile realised better): **49.06%** over
  9,375 within-group pairs
- Mean within-group Spearman (percentile vs forward excess): **0.006**
- Median-rank half split, top minus bottom forward excess: **+0.075pp**

All three readings sit at essentially CHANCE. Before the ladder is even run,
the discarded percentile does not appear to order forward outcomes within a
group the calibration already says are tied.

## The ladder

| Rung | Gross CAGR | Cost drag | Net CAGR | Benchmark | Net excess | Vol | Sharpe | MDD | Turnover | Avg cash |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Control | 13.564% | 1.404pp | 12.161% | 12.845% | -0.684pp | 11.985% | 0.853 | -25.158% | 4.679x | 30.417% |
| Ordinal rescue | 12.811% | 1.306pp | 11.505% | 13.371% | -1.865pp | 14.026% | 0.706 | -28.419% | 4.361x | 27.944% |

**Paired difference (ordinal rescue minus control): -1.181pp, 95% CI
[-6.207pp, +3.955pp] over 155 blocks.**

Verdict: **DIRECTIONAL_BUT_NOT_STATISTICALLY_SEPARATED** — the point estimate
is unfavourable and the interval contains zero.

### Where the gross gap comes from

| Rung | Arithmetic selection | Compounding | Block sd ratio |
|---|---:|---:|---:|
| Control | +0.315pp | +0.405pp | 0.784x |
| Ordinal rescue | -0.402pp | -0.158pp | 1.033x |

Both terms move unfavourably, and the block sd ratio rises above 1 — the
rescue rung is not merely a volatility trade, it lost on selection.

## Cascade attribution

| Category | Name-dates |
|---|---:|
| Total changed | 862 |
| Direct within-calibration reorder | 853 (99.0%) |
| Sector cap cascade | 9 (1.0%) |
| Other | 0 |
| Region cap cascade (rebalances with any swap) | 0 of the swap-bearing rebalances |

The result is overwhelmingly attributable to the axis itself, not to a
downstream cap interaction — the region cap's structural inability to
cascade from this axis was predicted and is confirmed at zero.

## Tied-swap population — linkage to `alpha-reliability-v1`

Same pairing definition (weakest arrival vs strongest departure by score,
restricted to swaps tied on calibrated expected alpha):

| Rung | Swaps measured | Mean realised excess difference |
|---|---:|---:|
| Control | 39 | -2.601% |
| Ordinal rescue | 57 | +2.558% |

`alpha-reliability-v1` published -2.601% on n=39 as its own reference point
for this population. The rescue rung's tied-swap population GREW (57 vs 39,
because incumbent retention rose and turnover fell, changing which pairs
qualify) and its mean flipped sign — descriptive, not the primary claim, and
consistent with a small, noisy sub-population rather than a stable effect.

## Boundary diagnostic

| Reading | Control | Ordinal rescue |
|---|---:|---:|
| Cuts tied on expected alpha | 86.71% | 86.01% |
| Incumbent retention | 38.08% | 49.51% |
| One-way turnover | 4.679x | 4.361x |

The tie rate barely moves, as expected — it is a property of the
calibration's bucket edges, which this axis never touches. Incumbent
retention rises and turnover falls: the rescue rung holds names longer,
consistent with `signal-persistence-v1`'s and `switch-hurdle-v1`'s finding
that hysteresis-like effects reduce turnover mechanically, independent of
whether the underlying ranking is better.

## Exploratory stacks — outside the ladder

Each row moves MORE THAN ONE axis and is attributable to NONE of them
individually. None is paired into the primary ladder.

| Stacked path | Axes moved | Net excess | Arithmetic selection | vs control |
|---|---:|---:|---:|---:|
| + persistence k=6 | 2 | -2.995pp | -1.536pp | -2.311pp [-9.344, +4.293] |
| + entry-at-weight | 2 | -0.817pp | -0.049pp | -0.133pp [-5.354, +4.917] |
| + both | 3 | -0.104pp | +0.532pp | +0.580pp [-5.348, +6.378] |

All three stacked paths also contain zero, and none is read as the axis's
independent effect.

## Combined interpretation: CASE B — ordinal rescue does not help

The pre-registration named three cases: favourable-and-separated (A),
doesn't-help (B), and directionally-good-but-uncertain (C). This result's
point estimate is UNFAVOURABLE (-1.181pp) though not statistically
separated, which the pre-registration did not name as a fourth case — routing
it to "directionally good" (C) would misrepresent a negative point estimate,
so it is reported as B on point-estimate sign. Stage B's near-chance
pairwise concordance (49.06%) corroborates this reading independently: the
discarded percentile does not appear to order forward outcomes even within a
tied group.

## Answering the pre-registered questions (Q1-Q10)

1. **Compression**: 3,028 eligible name-dates fall into 3 distinct levels;
   the largest holds 53.70%. Real ordinal spread exists within a level
   (mean range 2.979 points) for the rescue to use.
2. **Within-group predictive value**: No. Pairwise concordance 49.06%,
   Spearman 0.006, top-minus-bottom +0.075pp — all near chance.
3. **Did it improve net excess?**: No — point estimate -1.181pp, CI contains
   zero. `DIRECTIONAL_BUT_NOT_STATISTICALLY_SEPARATED`.
4. **Selection or volatility/compounding?**: Both terms moved unfavourably
   (arithmetic +0.315pp -> -0.402pp; compounding +0.405pp -> -0.158pp) — not
   a volatility-drag story, a selection loss.
5. **What characterises the disagreement?**: Challenger-only names carry a
   higher raw percentile (99.443 vs 97.339) at the SAME calibrated alpha
   (0.449pp both sides) and higher downside volatility (27.59% vs 25.43%).
6. **Direct vs cascade?**: 99.0% direct, 1.0% sector cascade, 0% region
   cascade (structurally impossible, confirmed).
7. **Did the historically-losing tied-swap population shrink?**: It grew
   (39 -> 57 swaps) as turnover fell, and its mean flipped sign
   (-2.601% -> +2.558%) — descriptive, not the primary claim.
8. **Turnover / retention**: Incumbent retention 38.08% -> 49.51%; one-way
   turnover 4.679x -> 4.361x; tie rate essentially unchanged (86.71% ->
   86.01%), as predicted since this axis never touches the bucket edges.
9. **Does this justify `continuous-alpha-calibration-v1`?**: No. This study
   carries none of `lowvol-alpha-separation-v1`'s harness-fidelity gap
   (fields read directly, no reconstruction), and the combined reading is
   CASE B.
10. **Resolution or discrimination?**: Stage B's 49.06% concordance — near
    chance — points at DISCRIMINATION, not resolution. The percentile does
    not order forward outcomes even where the calibration agrees, so a finer
    calibration would not be expected to recover value that is not there.

## What this study does NOT establish

- Not a promotion. `promotionEligible` is `false` and no permutation null was
  run, so no rung here may be described as beating random.
- Forward-return and Stage B readings are evaluation-only, fitted to
  nothing, with no multiplicity correction.
- Every stacked path moves more than one axis and settles none of them.
- One historical sample, after ten studies on this ledger.
- No bucket-count sweep, no percentile-coefficient optimisation, no isotonic
  or spline fit, no threshold search — one binary mechanistic test,
  specified before the result.

## Next research (proposed, NOT run here)

Given Case B: research attention belongs on alpha signal discrimination,
persistence and entry structure rather than on calibration resolution or a
finer/continuous calibration. `alpha-reliability-v1`'s own diagnostic
bottleneck — the two-occupied-bucket resolution — is confirmed NOT to be
hiding usable ordinal information on this sample; the deeper problem is that
the percentile itself does not discriminate forward outcomes within a tied
group.

Sealed ledgers should ideally store more production-computed intermediate
fields (sleeve z-scores, `rawAlpha`, evidence-adjusted alpha) for future
studies — proposed, not executed here; no historical ledger was regenerated
and no production code changed.

## Reproducing

```
python scripts/run_alpha_calibration_resolution_replay.py <sealed-ledger> \
  --output alpha-calibration-resolution-report.json \
  --markdown alpha-calibration-resolution-report.md
```

`--skip-exploratory` runs the primary ladder alone. The runner refuses to
write inside the sealed ledger, digests the ledger tree before and after the
run and raises on any change, and the workflow compares its output
byte-for-byte against the checked-in artifacts in `docs/results/`. Two
independent full sealed replays from the same commit produced byte-identical
JSON and Markdown output.
