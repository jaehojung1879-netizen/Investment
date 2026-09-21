# Alpha calibration resolution v1

> Read-only research CHALLENGER on sealed replay-v16 inputs. The four-factor
> alpha, the calibration table and its bucket edges, the selection score's
> downside-volatility denominator, entry logic, region/sector caps,
> `targetNames = 5`, the cash floor, inverse-vol sizing, transaction costs,
> benchmark construction and the rebalance schedule are unchanged and
> IDENTICAL on both rungs. `promotionEligible: false`, production unchanged.

## The question

Among names the expanding-bucket calibration scores IDENTICALLY (same region,
same `calibrationBucket`, hence the same calibrated expected excess), does the
`alphaPercentile` ordering it discards still carry value — restored WITHOUT
ever letting a name cross a DIFFERENT calibration level?

## The one axis

| Rung | Ranking |
|---|---|
| `LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS` | `alpha_reliability.CONTROL`, called directly |
| `WITHIN_CALIBRATION_ORDINAL_RESCUE` | Same score values at every position; within each (region, calibrationBucket) group only, the IDENTITY occupying a position is reassigned by `alphaPercentile` descending |

## Stage A — information-loss diagnostic (read before the ladder)

- Total eligible candidate name-dates: **3028**
- Distinct (region, calibrationBucket) levels: **3**
- Largest level's share of all eligible name-dates: **53.700%**
- Within-level alphaPercentile range: mean 2.979, sd 1.197

## Stage B — within-calibration information (evaluation only)

- Pairwise concordance (higher percentile realised better): **49.060%** over 9375 pairs
- Mean within-group Spearman (percentile vs forward excess): 0.006
- Median-rank half split, top minus bottom forward excess: 0.075pp

## The ladder

| Rung | Gross CAGR | Cost drag | Net CAGR | Benchmark | Net excess | Vol | Sharpe | MDD | Turnover | Avg cash | Names |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS | 13.564% | 1.404pp | 12.161% | 12.845% | -0.684pp | 11.985% | 0.853 | -25.158% | 4.679x | 30.417% | 4.658 |
| WITHIN_CALIBRATION_ORDINAL_RESCUE | 12.811% | 1.306pp | 11.505% | 13.371% | -1.865pp | 14.026% | 0.706 | -28.419% | 4.361x | 27.944% | 4.658 |

**Paired difference (ordinal rescue minus control): -1.181pp, 95% CI [-6.207pp, 3.955pp] over 155 paired blocks.**

Verdict: **DIRECTIONAL_BUT_NOT_STATISTICALLY_SEPARATED**

### Where the gross gap comes from

| Rung | Arithmetic selection | Compounding | Geometric gross edge | Block sd ratio |
|---|---:|---:|---:|---:|
| LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS | 0.315pp | 0.405pp | 0.719pp | 0.784x |
| WITHIN_CALIBRATION_ORDINAL_RESCUE | -0.402pp | -0.158pp | -0.560pp | 1.033x |

## Factor profile of the names the rungs disagree about

145 rebalances; 291 held name-dates agreed, 431 disagreed.

| Metric | Challenger-only | Control-only |
|---|---:|---:|
| alpha percentile | 99.443 | 97.339 |
| calibrated expected excess | 0.449 | 0.449 |
| downside volatility | 27.590 | 25.428 |

## Cascade attribution

| Category | Name-dates |
|---|---:|
| Total changed | 862 |
| Direct within-calibration reorder | 853 |
| Sector cap cascade | 9 |
| Other | 0 |
| Region cap cascade (rebalances) | 0 |

## Boundary diagnostic

| Reading | Control | Ordinal rescue |
|---|---:|---:|
| Cuts tied on expected alpha | 86.710% | 86.010% |
| Incumbent retention | 38.080% | 49.510% |

## Tied-swap population — linkage to alpha-reliability-v1

Same pairing definition (weakest arrival vs strongest departure by score,
restricted to swaps tied on calibrated expected alpha), measured before
(control) and after (rescue) the ordinal rescue.

| Rung | Swaps measured | Mean realised excess difference |
|---|---:|---:|
| LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS | 39 | -2.601% |
| WITHIN_CALIBRATION_ORDINAL_RESCUE | 57 | 2.558% |

## EXPLORATORY stacks — outside the ladder

Each row below moves MORE THAN ONE axis and is attributable to NONE of
them individually. None is paired into the primary ladder and none is
the ordinal rescue's independent effect.

| Stacked path | Axes moved | Net excess | Arithmetic selection | Sharpe | MDD | Avg cash | vs control |
|---|---:|---:|---:|---:|---:|---:|---:|
| EXPLORATORY_ORDINAL_RESCUE_PLUS_PERSISTENCE_K6 | 2 | -2.995pp | -1.536pp | 0.577 | -38.902% | 28.976% | -2.311pp [-9.344pp, 4.293pp] |
| EXPLORATORY_ORDINAL_RESCUE_PLUS_ENTRY_AT_WEIGHT | 2 | -0.817pp | -0.049pp | 0.557 | -14.198% | 66.099% | -0.133pp [-5.354pp, 4.917pp] |
| EXPLORATORY_ORDINAL_RESCUE_PLUS_PERSISTENCE_K6_PLUS_ENTRY_AT_WEIGHT | 3 | -0.104pp | 0.532pp | 0.691 | -13.590% | 66.343% | 0.580pp [-5.348pp, 6.378pp] |

### Combined interpretation: **CASE B — ordinal rescue does not help**

Point estimate -1.181pp, not statistically separated from control (the interval contains zero). Stage B's pairwise concordance of 49.060% is near chance, corroborating this reading: the discarded percentile does not appear to order forward outcomes even within a tied group. Finer bucketing is unlikely to be the answer either, since the ordinal information finer bucketing would expose is exactly what was restored here and tested directly. Research attention moves to alpha signal discrimination, persistence and entry structure rather than calibration resolution.

## Q1–Q10

**Q1. Calibration이 production의 alpha ordering을 얼마나 압축하는가?**

3028 eligible candidate name-dates fall into 3 distinct (region, bucket) levels; the largest single level holds 53.700% of them. Within a level, alphaPercentile still ranges 2.979 points (sd 1.197) on average — real ordinal spread the calibration throws away.

**Q2. Tied group 내에서 더 높은 alphaPercentile이 실제 forward excess를 예측하는가?**

Pairwise concordance (higher percentile realised better) 49.060% over 9375 within-group pairs; mean within-group Spearman 0.006; top-half minus bottom-half (median rank split) forward excess 0.075pp. Concordance near 50% and a near-zero Spearman would mean the discarded percentile is NOT informative even within a tied group, before the ladder is read at all.

**Q3. Ordinal rescue가 net benchmark excess를 개선했는가?**

-0.684pp -> -1.865pp. Paired difference -1.181pp, 95% CI [-6.207pp, 3.955pp] over 155 blocks. Verdict: **DIRECTIONAL_BUT_NOT_STATISTICALLY_SEPARATED**.

**Q4. 그 변화는 arithmetic stock selection 개선인가, volatility/compounding effect인가?**

Arithmetic stock selection 0.315pp -> -0.402pp; compounding 0.405pp -> -0.158pp; block sd ratio 0.784x -> 1.033x. This is the primary mechanism metric in this line of studies.

**Q5. Control/Challenger가 서로 다르게 선택한 종목들의 특징은 무엇인가?**

On the 431 disagreed name-dates — challenger-only vs control-only: alpha percentile 99.443 vs 97.339, calibrated expected excess 0.449pp vs 0.449pp (should be the SAME level unless cascade explains the gap — see Q6), downside volatility 27.590% vs 25.428%.

**Q6. 이 결과 중 direct within-calibration reorder와 downstream cascade의 비중은 어떻게 되는가?**

Of 862 changed name-dates: 853 (99.0%) are the DIRECT within-calibration reorder itself, 9 (1.0%) are a downstream SECTOR-cap cascade the reorder triggered, and 0 are unattributed. The region cap is structurally unable to cascade from this axis (a swap only ever exchanges two eligible names from the SAME region) and this is measured directly: the held set's regional shape differed on 0 of the rebalances that had at least one swap.

**Q7. alpha-reliability-v1이 측정한, calibration에서 tied된 채 손실을 낸 swap population이 줄어들었는가?**

Same pairing definition, before vs after the rescue: 39 tied swaps at -2.601% mean arriving-minus-departing excess (control) vs 57 tied swaps at 2.558% (rescue rung). `alpha-reliability-v1` published -2.601% on n=39 tied swaps as its own reference point for this population.

**Q8. Turnover와 incumbent retention은 어떻게 변했는가?**

Incumbent retention 38.080% -> 49.510%; one-way turnover 4.679x -> 4.361x; cuts tied on expected alpha 86.710% -> 86.010% (this rate is a property of the calibration's bucket edges, which this axis never touches, so it would be surprising for it to move much).

**Q9. 이 결과가 continuous-alpha-calibration-v1을 정당화하는가?**

Read directly from production/sealed fields (alphaPercentile, calibrationBucket, expectedGrossBenchmarkExcessPct) with no reconstruction, so this study carries none of lowvol-alpha-separation-v1's harness-fidelity gap. Combined interpretation: **CASE B — ordinal rescue does not help**.

**Q10. 현재 bottleneck은 calibration RESOLUTION인가, Alpha DISCRIMINATION 자체인가?**

Stage B answers this before the ladder does: pairwise concordance (higher percentile realised better) is 49.060%, which is near chance. That points at ALPHA DISCRIMINATION rather than calibration resolution: the percentile itself does not order forward outcomes even where the calibration already agrees they are equal, so no amount of finer bucketing would recover value that is not there.

## What this study does NOT establish

- Not a promotion. `promotionEligible` is false and no permutation null
  was run, so no rung here may be described as beating random.
- Forward-return and Stage B readings are evaluation-only, fitted to
  nothing, with no multiplicity correction.
- Every stacked path moves more than one axis and settles none of them.
- One historical sample, after ten studies on this ledger.
- No bucket-count sweep, no percentile-coefficient optimisation, no
  isotonic or spline fit, no threshold search — one binary mechanistic
  test, specified before the result.

## Next research (proposed, NOT run here)

1. If Case A: `continuous-alpha-calibration-v1` — a monotonic calibration
   replacing the discrete bucket edges, on an INDEPENDENT sample.
2. If Case B: redirect toward alpha signal discrimination, persistence
   and entry structure rather than calibration resolution.
3. If Case C: a prospective or independent-sample validation of this same
   axis before any finer calibration is attempted.
4. Sealed ledgers should ideally store more production-computed
   intermediate fields (sleeve z-scores, rawAlpha, evidence-adjusted
   alpha) — proposed, not executed here; no historical ledger was
   regenerated and no production code changed.
