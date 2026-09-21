# Lowvol alpha separation v1 — design

> Research CHALLENGER. The selection score's downside-volatility denominator,
> inverse-volatility sizing, the entry multiplier, the research pool, every cap
> and `evidenceCoverage` itself are unchanged and IDENTICAL on both rungs.
> `promotionEligible` stays `false` and production is unchanged.

## The question

Production's alpha is `0.30 momentum + 0.25 value + 0.25 quality + 0.20 lowvol`.
The question is not whether low volatility is a good property. It is narrower:

> Does spending 20% of the ALPHA on a RISK characteristic weaken the
> benchmark-relative selection signal, when the risk denominator and
> inverse-volatility sizing are both left exactly as they are?

`alpha-risk-separation-v1` removed downside volatility from the selection
score's *denominator* and found nothing (-0.902pp, 95% CI [-5.068, +3.210]).
Its diagnostic extension then measured why: on the name-dates the two rungs
disagreed about, momentum separated them by +0.687 and quality by +0.626 —
under a percentile point — while `lowvol` moved -9.725. The denominator was
not suppressing high-momentum names. That localised the surviving defensive
tilt in the one risk channel neither study touched: the `lowvol` sleeve
**inside** the alpha. This study removes that sleeve, and nothing else.

## The one axis

| Rung | Alpha |
|---|---|
| `CONTROL_FOUR_FACTOR_ALPHA` | 0.30 momentum + 0.25 value + 0.25 quality + 0.20 lowvol |
| `NO_LOWVOL_IN_ALPHA` | 0.375 momentum + 0.3125 value + 0.3125 quality |

The challenger's weights are **derived, not fitted**: `THREE_FACTOR` is
computed from `longterm.FACTOR_WEIGHTS` at import by dropping `lowvol` and
renormalizing, so production's 30:25:25 ratio is preserved exactly (the
momentum/value ratio is 1.2 on both rungs) and the weights cannot drift from
production's if it ever changes them. **No weight sweep was performed**, and
the design forbids one.

## Three things established from the sealed ledger before anything was built

### 1. The harness difference, measured and published rather than hidden

Production blends sleeve **z-scores**. The sealed replay-v16 ledger does not
store them — it stores each sleeve's **percentile** (`factorPercentiles`),
the blended `rawAlpha` as a single scalar, and `evidenceCoverage`. Integer
percentiles cannot be inverted back to z-scores, so **production's exact alpha
arithmetic is unreachable from sealed inputs**. This was verified against the
ledger, not assumed.

Both rungs therefore blend percentiles. That keeps the axis between them
exactly one thing, but it means this harness's control is **not** the
published path. Per `switch-hurdle-v1` — a ladder carries its own control, and
the control's own gap to the published path is published beside it —
`harness_fidelity` measures that gap on every cross-section. Measured over
1,430 cross-sections: **rank correlation ≈ 0.906** to the published
`alphaPercentile`.

This bounds what the study can claim. The paired comparison between the two
rungs is internally valid; the absolute level of either rung is not
production's.

### 2. Coverage is applied to a CENTRED blend, chosen on fidelity not on result

Production computes `alpha = rawAlpha × evidenceCoverage`, where `rawAlpha` is
a **signed** z-blend centred near zero — so coverage shrinks a name toward
neutral, pushing a negative alpha further down and a positive one further up.
A percentile blend is strictly positive, so multiplying it raw would push every
weakly-covered name **down regardless of sign**: a different operation wearing
the same name.

`_rung_alpha` therefore centres the blend at 50 before applying coverage.
Measured rank correlation to the published `alphaPercentile`:

| Construction | Correlation |
|---|---:|
| blend only, no coverage | 0.9198 |
| blend × coverage (uncentred) | 0.7461 |
| **(blend − 50) × coverage (centred)** | **0.9294** |

The choice was made against the CONTROL's fidelity to the published path,
**before any rung was valued** — not by which gave the challenger a better
number.

### 3. The section-5 trap is real, and is avoided by not recomputing coverage

`longterm` computes `factorCoverage = sleevesPresent / len(FACTOR_WEIGHTS)`
and averages `SLEEVE_SOURCE_QUALITY` over the sleeves a name has (momentum and
`lowvol` are 1.0; value and quality 0.6). Naively deleting `lowvol` would drop
factor coverage from 4/4 to 3/4 and shift source quality from 0.80 to 0.733,
costing roughly **14 points of `evidenceCoverage`** — a mechanical penalty with
nothing to do with the hypothesis, which would make the challenger look worse
for entirely the wrong reason.

This study **never recomputes coverage**. `evidenceCoverage` is read from the
sealed row and is identical on both rungs, so the penalty cannot arise.
`dataInsufficient`, `longTermResearchView`, `valueTrap`, the risk block,
`entryState`, sector, region and the research **pool** are likewise
production's own, unchanged and shared. Only which sleeves enter the blend
moves.

Measured: **zero of 399,547 name-dates** have no three-factor sleeve at all, so
the challenger can rank every name the control can and **no eligibility
diverges between the rungs**.

## What stayed fixed

Momentum/value/quality sleeve definitions and their 30:25:25 ratio;
`evidenceCoverage`, `dataInsufficient`, `longTermResearchView`, `valueTrap`;
the research pool and its membership; the expanding-bucket calibration; **the
selection score's downside-volatility denominator**; entry-state logic and the
entry multiplier; `targetNames = 5`, sector and region caps, the cash floor;
inverse-downside-volatility sizing and the conviction tilt; transaction costs,
rebalance schedule, benchmark construction; and no persistence, no confidence
contraction, no hysteresis, no cost hurdle on either rung.

## Exploratory stacks — outside the ladder

Three stacked paths are reported **outside** the primary ladder, each carrying
an explicit `axesMoved` count: `+ persistence k=6` (2 axes), `+ entry-at-weight`
(2 axes), and both (3 axes). They **compose the existing studies' own
functions** — `AR.confidence_rows(persistence=True)` and
`entry_selection_separation.entry_weighted_scores` — rather than
reimplementing them. Each moves more than one axis and is attributable to
**none of them individually**; none is paired into the primary ladder and none
is the lowvol sleeve's independent effect.

## What this study does NOT establish

- Not a promotion. `promotionEligible` is false, and no permutation null was
  run, so no rung here may be described as beating random.
- The harness blends percentiles, not z-scores. The ladder is internally
  consistent; it is not the production path.
- Forward-return and sector readings are descriptive, fitted to nothing, with
  no multiplicity correction.
- Every stacked path moves more than one axis and settles none of them.
- One historical sample, after nine studies on this ledger.

## Reproducing

```
python scripts/run_lowvol_alpha_separation_replay.py <sealed-ledger> \
  --output lowvol-alpha-separation-report.json \
  --markdown lowvol-alpha-separation-report.md
```

`--skip-exploratory` runs the primary ladder alone. The runner refuses to
write inside the sealed ledger, digests the ledger tree before and after the
run and raises on any change, and the workflow compares its output
byte-for-byte against the checked-in artifacts in `docs/results/`.
