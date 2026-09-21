# Alpha reliability v1 — design

> Research CHALLENGER. No factor is added, no factor weight moves, no selector
> is promoted, `promotionEligible` stays `false` and production is unchanged.

## Why this study exists

Four measurements on the same sealed ledger keep pointing at one place, and
none of them has looked at it directly.

| Study | What it found | What it left open |
|---|---|---|
| `selection-value-decomposition-v1` | The calibrated challenger's +0.340pp/yr headline is +0.040pp of arithmetic stock selection and +0.300pp of compounding. 92-93% of turnover is names REPLACED, not weights retargeted. | The bill is paid for the ranking's opinion about WHICH names. Is that opinion worth it? |
| `selection_null` (challenger-specific) | 87th / 84th / 94th percentile of its own permutation null; p = 0.134 / 0.164 / 0.065. | Does not clear the pre-registered 5% bar on any statistic — and does not establish that the ranking is worthless either. |
| `regional-switch-hurdle-v1` | Saved 0.270pp of cost drag and gained **2.157pp** of arithmetic stock selection. | Eight times more of the gain than the cost argument predicts. Holding a name longer cannot make the name better. |
| `signal-persistence-v1` | ADDED names realised -0.357%/block against +0.980% for RETAINED; paired -1.331%, 95% CI [-3.029, +0.174], which CONTAINS zero. Smoothing the percentile over k=6 blocks moved net excess -0.684pp → +2.289pp, every interval spanning zero. | Corroboration across angles, not a rejection of any null. |

They are all the same claim wearing different coats: **the conversion from a
continuous signal into a discrete five-name book is losing more than the signal
is worth.** This study measures that conversion and then tries to spend the
SAME signal more carefully. It is an extraction-efficiency study, not a feature
study.

## The axis, measured before the ladder was specified

`AGENTS.md` requires the axis to be measured before the ladder is read.
`alpha_reliability.axis_diagnostics` does that on the sealed pool, and two of
its readings **refuted rungs this module was going to have**.

1. **The pool lives in two calibration buckets.** Its alpha percentiles run
   91-100 (mean 97.4, sd 2.33). The calibration's bucket edges are
   `(0, 60, 80, 90, 95, 100)`, so only `90-95` and `95-100` are ever occupied
   and about five name-dates in six fall in the second. Names inside one bucket
   are handed the **same** expected excess, so for most of the pool the
   ranking's alpha term is a constant and the ordering is decided by realised
   downside volatility alone.

   The premise that "alphaPercentile 74 versus 73 flips a holding" is not what
   this system does. What it does is worse and more specific: 97 versus 98 is
   not a difference the calibration can represent at all, and the book swaps on
   it anyway.

2. **Shrinking the PERCENTILE toward a neutral percentile cannot be the
   channel.** Shrink toward the pool mean (~97) and a weak name at 93 moves
   *up* into the top bucket — confidence would be raising an alpha claim, the
   one thing it must never do. Shrink toward 50 and every name lands in `60-80`
   together, which deletes the signal instead of refining it. So confidence is
   applied in **alpha space**, where the neutral point is a genuine neutral:
   zero benchmark excess.

3. **Evidence coverage is already inside the level.** `longterm` computes
   `alpha = rawAlpha × evidenceCoverage` *before* the percentile is taken.
   `evidenceCoverage` and `factorCoverage` have therefore already shrunk the
   number this module is handed, and reusing either as a confidence weight
   would charge the same doubt twice while looking like a new instrument. Both
   are excluded, with the reason recorded in `CONFIDENCE_EXCLUSIONS` and the
   diagnostic published beside the ladder.

## The three layers

### A. Level — unchanged

The production `alphaPercentile`, built from the production
0.30 / 0.25 / 0.25 / 0.20 momentum / value / quality / low-vol sleeve weights,
mapped to an expected benchmark excess by the production expanding bucket
calibration. Nothing here is re-weighted, re-fitted or re-bucketed.

### B. Persistence — inherited, not re-searched

`signal_persistence.PercentileSmoother` at `k = 6`, imported rather than
re-implemented. `k = 6` is the forecast horizon in blocks (126 sessions / 21)
and was fixed a priori by that study; **no new window is introduced and no grid
is swept.** The smoother looks backward only, over a name's own prior pool
appearances, and a name seen for the first time carries its raw percentile.

This module adds one accessor to that class — `dispersion(ticker)`, the sample
sd of the same backward window the mean is taken over — so the confidence layer
reads the name's own noise from the one place the window is defined instead of
building a second history beside it. One observation has no dispersion and
returns `None`, never `0.0`.

### C. Confidence — the new work

Two factors, each in (0, 1], each fixed before any path was run, each built
from information the level does **not** already contain:

```
r_history   = n·τ² / (n·τ² + σ²)
r_agreement = 1 − sd(factor percentiles) / 50

confidence     = r_history × r_agreement
reliable_alpha = confidence × alpha
```

* **`r_history`** is the reliability ratio of a group mean under one-way
  partial pooling. `σ` is the name's own backward percentile dispersion over
  the same `k = 6` window, `n` its depth, and `τ` the cross-sectional
  dispersion of the smoothed percentiles among **that region's** pool names on
  that date — the percentile is a within-region rank, so pooling regions would
  compare a Korean name's position against an American cross-section. It asks
  whether this name's position is bigger than its own wobble. Nothing is
  fitted; every term is observable at the rebalance.

* **`r_agreement`** uses the spread the level throws away. The four sleeves are
  the same four the level blends, but averaging discards how far apart they
  were: a name at the 97th percentile built from 99/98/95/96 and one built from
  99/40/99/40 make the same claim on very different evidence. **50 is the
  arithmetic maximum sd of values bounded in [0, 100]** (half at each end), not
  a fitted scale — the observed maximum on this pool is 49.5, which is the
  bound being real rather than chosen.

**This is a contraction, never an amplifier.** `|reliable_alpha| ≤ |alpha|` and
the sign is preserved, so confidence can only ever *reduce* what a name is
credited with. It is not a fifth factor, it cannot earn a name a place it had
not already earned on the level, and `contraction_holds` is asserted on every
row of every block — a violation raises rather than being reported.

**Absence is abstention, not an extreme value.** A name with fewer than two
sleeves has no agreement to measure; a name too new for its own dispersion
borrows the *pooled* median dispersion observed in earlier blocks (the standard
partial-pooling degradation, and backward-only — the pool is banked only after
the block has been scored). A name for which **neither** component can be
measured is excluded with `SIGNAL_CONFIDENCE_UNMEASURABLE` rather than being
handed `confidence = 1.0`.

### D. Hysteresis — and why it is not the switch hurdle

`regional-switch-hurdle-v1` credits an incumbent the **friction** its staying
avoids. That is a claim about the tax code. This credits an incumbent the part
of its own alpha that confidence discarded, which is a claim about the
**signal**:

```
incumbent  decision alpha = reliable_alpha + (1 − confidence)·|alpha|
challenger decision alpha = reliable_alpha − (1 − confidence)·|alpha|
```

For a positive alpha that is exactly: *judge the name you hold on the most
favourable reading of its own signal and the name you would buy on the least
favourable reading of its own* — a swap happens only when the two readings do
not overlap. The margin and the shrinkage are **one quantity read twice**, not
two separately chosen numbers, so no parameter is introduced. Two names in the
same calibration bucket carry the same alpha, so under this rule they can never
displace one another; under the control they do, on nothing but a
downside-volatility ordering.

**No transaction cost enters any rung of the ladder.** The two hypotheses —
*staying is cheaper* and *the signal cannot tell these two apart* — are tested
separately, and their combination is reported outside the ladder.

## The ladder

One axis per rung. Everything else is held fixed: the 21-session cadence, the
PIT research pool, the sleeve weights, the bucket calibration, the entry-state
and research-view exclusions, the name/sector/region caps, `maxPositionWeight`,
the cash floor, the conviction-tilted inverse-downside-volatility weights, and
the realistic dated cost schedule charged to the realised path.

| Rung | Axis it adds |
|---|---|
| `LATEST_ALPHA_NO_CONFIDENCE_NO_HYSTERESIS` | none — the control |
| `PERSISTENT_ALPHA_ONLY` | the backward-only k=6 window |
| `PERSISTENT_ALPHA_X_SIGNAL_CONFIDENCE` | the confidence contraction |
| `PERSISTENT_ALPHA_X_CONFIDENCE_PLUS_SIGNAL_HYSTERESIS` | the incumbent/challenger uncertainty comparison |

Reported **outside** the ladder:
`PERSISTENT_ALPHA_X_CONFIDENCE_PLUS_SIGNAL_HYSTERESIS_PLUS_COST_HURDLE`, which
adds the transaction-cost credit and therefore moves two axes at once. Its
number is attributable to neither and is not promotion evidence.

### The control, and its distance from the published path

The control is the same loop `signal_persistence` runs as
`RANK_ON_LATEST_ALPHA_PERCENTILE` and `switch_hurdle` runs as
`NO_HURDLE_CONTROL_SAME_LOOP`. Its published gap to the sealed challenger path
is **-0.684pp against -1.046pp** of annualized net excess. That 0.362pp is a
research-harness difference, not a rung: every comparison in this study is
paired against this control, never against the sealed path, and the gap is
published beside the ladder rather than absorbed into a result.

## What is measured

Per rung: gross and net CAGR, matched benchmark, gross and net excess; the
`arithmetic selection / compounding` split and the block-sd ratio; realised
volatility, Sharpe, Sortino, CVaR95, maximum drawdown; one-way turnover split
into **names replaced** and **weights retargeted**, with US and KR retention
reported separately; average names held, retained and added, incumbent
retention and replacement rates; and each region's contribution to gross excess
with its interval.

Paired differences are published **twice**: against the rung immediately below
(the one-axis test) and against the ladder control (cumulative). Both carry a
point estimate, a 95% bootstrap interval and the paired block count.

## The boundary diagnostic

This is the part of the study that stands whatever the ladder does.

* the expected-alpha gap, percentile gap and confidence gap between the **last
  name held** and the **first name excluded**;
* `tiedOnExpectedAlphaPct` — the share of those cuts where the calibration
  scores the two names **identically**, so the cut was made by downside
  volatility alone;
* the same three gaps at every **swap**, paired at its margin (the weakest
  arrival against the strongest departure, which is the pair the decision
  turned on);
* how many held names whose raw percentile moved **one point or less** were
  replaced anyway;
* the **replacement success rate**: the arriving name's realised forward
  21-session benchmark excess minus the departing one's, split by whether the
  two were tied or separated on expected alpha.

The realised figures read what the path already did against the priced
cross-section the book was valued on — the same instrument
`signal_persistence.incumbency_outcomes` uses. Nothing measured here feeds back
into any rung.

## Point-in-time discipline

Every input to persistence and confidence is observable at the rebalance date.
The smoother looks backward only. The pooled dispersion prior is banked after
the block it was measured on, so a new name borrows only from earlier blocks.
No realised return enters any confidence weight: calibrating confidence against
what actually happened would be exactly the look-ahead this repository's
replay invariants exist to prevent. The study does not improve the
repository's existing PIT limitations and does not worsen them.

## What this study does NOT claim

* **No permutation null was run here.** No rung may be described as beating
  random, and `permutationNullRun` is `false` in the freeze manifest.
* A rung ending higher than another is a **point estimate** on one historical
  sample, after several rungs across four studies, with no multiplicity
  correction.
* An interval that contains zero is **not a finding**. Consistency across
  angles is corroboration and is reported as corroboration.
* The functional form guarantees confidence cannot amplify an alpha claim. It
  does **not** guarantee that `r_agreement` carries no return information of
  its own — cross-sleeve agreement could be a weak factor rather than a
  reliability weight, and one historical sample cannot separate those. What the
  form enforces is claimed; what it does not is left unclaimed.
* Nothing here changes `CHAMPION`, the production selector, production weights,
  Kelly, macro policy, regional rotation, `paperTrading` or `liveValidated`.

## Separation is read in BOTH directions

An interval that excludes zero from **below** is as much a separation as one
that excludes it from above, and it is the more informative of the two: it
means a pre-specified axis made the path measurably worse. Reading separation
as "the lower bound cleared zero" would make that invisible, which is how a
ladder ends up reporting "nothing separated" while one of its own rungs has
been refuted. `separatedFromRungBelow` and `separatedFromControl` therefore
carry a `direction` rather than a bare list of names.

## The freeze rule, and where it came from

**A candidate is frozen for prospective validation only if no axis it contains
was refuted by its own paired test** — that is, only if no rung at or below it
separated from the rung beneath it in the `WORSE` direction.

That condition was **not** in the original design, and the record says so
rather than pretending otherwise. The design named
`PERSISTENT_ALPHA_X_CONFIDENCE_PLUS_SIGNAL_HYSTERESIS` as the candidate
unconditionally. The first full run returned the confidence axis separated from
the rung below it in the wrong direction, and freezing a candidate whose own
pre-specified test had just refuted it would have made the test decorative. So
the freeze was made conditional afterwards.

What makes that a tightening rather than a re-specification: **no rung,
parameter, window or scoring rule changed**, the ladder and every measured
number are exactly what the first run produced, and the condition can only ever
*remove* a candidate. It cannot promote one, it cannot make a refuted axis look
better, and it cannot turn a contained interval into a separated one.
Re-specifying a ladder until the hypothesis survives is the failure this
repository's discipline exists to prevent; this moves in the opposite
direction.

A refuted rung is **kept, not deleted**. The ladder that refutes a hypothesis
is the same instrument that would have confirmed it, and the reasoning that
produced the hypothesis is left standing next to the refutation.

If a candidate is frozen, what prospective paper trading must check is:
benchmark excess, turnover, retained-versus-added realised excess, the
replacement success rate, ranking stability, and whether the confidence weight
is **calibrated** — that names it scores low-confidence really do realise
noisier outcomes. That last one is the only check that can falsify the
mechanism rather than the result.

## Reproducing

```
python scripts/run_alpha_reliability_replay.py <sealed-ledger> \
  --output alpha-reliability-report.json \
  --markdown alpha-reliability-report.md
```

The runner refuses to write inside the sealed ledger, digests the ledger tree
before and after the run and raises on any change, and the workflow compares
its output byte-for-byte against the checked-in artifacts in `docs/results/`.
