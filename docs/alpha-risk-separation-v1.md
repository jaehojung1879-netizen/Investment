# Alpha risk separation v1 — design

> Research CHALLENGER. No factor is added, the `lowvol` sleeve's 0.20 weight
> and inverse-volatility position sizing are unchanged, `promotionEligible`
> stays `false` and production is unchanged.

## Why this study exists

Study 1 of the four pre-registered by `alpha-reliability-v1`
(`docs/alpha-reliability-v1.md`). That study measured, on the production
scoring shape, that:

- across the whole research cross-section the score's rank correlation with
  the calibrated alpha is **0.758** against **0.075** with downside
  volatility — the alpha term orders most *pairs*;
- but a five-name book is decided at its **margin**, and **86.71%** of top-5
  cuts are between names the calibration scores *identically* — there, what
  remains ordering the cut is the risk-and-entry product in the score's
  denominator;
- the resulting tilt is visible in what is *held*: downside volatility
  **24.45%** held against **27.17%** rejected, `lowvol` sleeve percentile
  **74.37** against **63.81**, `lowvol` among a held name's top two sleeves
  **58.86%** of the time.

Downside risk enters this system through three separate channels:

1. it is **0.20** of the four-factor alpha (the `lowvol` sleeve);
2. it is the **denominator** of the selection score
   (`expected excess / downside volatility`);
3. it is the **base of the position size**
   (`1 / downside volatility`, inverse-vol weighting).

The pre-registration named channel 2 as the first axis to remove, and named
channel 1 as **explicitly out of scope** — "moving the sleeve out of the alpha
layer is explicitly the *next* study: two risk channels moved together would
be attributable to neither." Channel 3 is untouched by design in every study
in this line; capital sizing is a separate question from which names are
chosen.

## The axis, and only the axis

| Rung | Score |
|---|---|
| Control (`alpha_reliability.CONTROL`) | `calibrated alpha / (downside vol × 100) × entry multiplier` |
| `RANK_ON_CALIBRATED_ALPHA_ONLY_NO_RISK_DENOMINATOR` | `calibrated alpha × entry multiplier` |

**The control is not reproduced — it is called.** `pipeline.alpha_risk_separation.CONTROL` is literally `pipeline.alpha_reliability.CONTROL`, and the control path is produced by calling `alpha_reliability.run_rung(alpha_reliability.CONTROL, ...)` directly. This is the same discipline every ladder in this line has followed since `switch-hurdle-v1`: a control that is a second implementation of an existing path is a way for the two to quietly drift, so the existing, already-tested function is called rather than copied.

**`DOWNSIDE_RISK_UNAVAILABLE` still excludes a name on both rungs.** A name with no downside-volatility unit cannot be *sized* — inverse-volatility weighting needs it regardless of what the ranking does — so removing the denominator from the score is not the same thing as pretending the risk does not exist. This mirrors the precedent in `selection_value.SCREEN_ONLY`: an eligibility fact about the name is kept even when a rung stops using it for ordering.

## What the score's double duty means for sizing

`kelly_portfolio.selection_and_baseline` hands one `scored` list to two
consumers:

- `select_portfolio_by_scores` — decides *which five names*;
- `baseline_weights` — decides the *conviction tilt* (0.5×–1.5×) among those
  five, ranked by the same score, applied on top of the inverse-volatility
  base weight.

Removing the denominator therefore changes the tilt's rank order along with
the selection. This is correct and in scope: both are downstream of the same
"selection ranking" the pre-registration named. What does **not** change is
the tilt's base — `1 / max(risk_unit, 0.05)` — computed identically on both
rungs. Inverse-volatility sizing is exactly as it was; only the ranking that
decides who receives it, and how much extra tilt on top of it, no longer
divides by risk.

## What is measured

The same instrumentation the earlier studies built, reused rather than
re-derived:

- `selection_value.summarize` — path metrics, the arithmetic-selection /
  compounding split, and the name-replacement / weight-retarget turnover
  split, on both rungs;
- `switch_hurdle.regional_attribution` — each region's contribution to gross
  excess, with intervals;
- `regional_validation.paired_bootstrap` — the paired difference against the
  control, with a 95% interval, read in **both** directions (an interval that
  excludes zero from *below* is as informative as one that excludes it from
  above — the lesson `alpha-reliability-v1`'s confidence rung taught this
  line of studies).

**The central diagnostic is `alpha_reliability.risk_dominance`, run
unchanged on each rung's own decisions.** Nothing here re-derives that
instrument; it is called twice, once per rung, and the two readings are
compared directly by `tilt_survival`. This answers the question the previous
study posed without answering: does the score's rank correlation with
downside volatility fall toward zero, and does the gap in downside volatility
and `lowvol` sleeve percentile between held and rejected names narrow, once
the denominator is gone?

## Reading the result

Two outcomes were possible before the replay ran, and the report says which
happened rather than assuming one:

- **The tilt does not survive** the denominator's removal (the vol/lowvol gap
  between held and rejected collapses toward the score's remaining
  correlation with downside volatility going to zero). That would mean the
  ranking denominator was the channel, and the `lowvol` sleeve question is
  less urgent — the alpha layer was not where the defensive bias was coming
  from.
- **The tilt survives.** That would mean part of the defensive bias arrives
  through the alpha term itself (the `lowvol` sleeve), which this study does
  not touch. That is explicitly the *next* study's axis — moving the sleeve
  out of the alpha layer — and is not a reason to widen this ladder.

Either reading is reported plainly; neither is grounds for promotion.

## What this study does NOT claim

- Not a promotion, not a production change, and not a claim that either rung
  beats the benchmark going forward.
- No permutation null was run here, so no rung may be described as beating
  random.
- The paired interval, whichever direction it falls, is a point estimate on
  one historical sample, after several rungs across five studies now, with no
  multiplicity correction.
- Nothing here changes `CHAMPION`, the production selector, production
  weights, Kelly, macro policy, regional rotation, `paperTrading` or
  `liveValidated`.

## Reproducing

```
python scripts/run_alpha_risk_separation_replay.py <sealed-ledger> \
  --output alpha-risk-separation-report.json \
  --markdown alpha-risk-separation-report.md
```

The runner refuses to write inside the sealed ledger, digests the ledger tree
before and after the run and raises on any change, and the workflow compares
its output byte-for-byte against the checked-in artifacts in `docs/results/`.
