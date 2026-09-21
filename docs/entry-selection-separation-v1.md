# Entry selection separation v1 — design

> Research CHALLENGER. Alpha/risk score, `targetNames`, sector/region caps,
> cash floor and every cost assumption byte-for-byte unchanged,
> `promotionEligible` stays `false` and production is unchanged.

## Why this study exists

Study 4 of the four pre-registered by `alpha-reliability-v1`
(`docs/alpha-reliability-v1.md`) — the last one. The pre-registration named
the separation directly: "alpha decides the held set, entry state decides
how fast the target weight is approached — ACCUMULATE to full weight, WATCH
to part, WAIT_FOR_PULLBACK throttles new entry, EVENT_RISK holds new entry."

Production does not implement that separation today. `_state_multiplier`
returns 1.0 for ACCUMULATE, 0.5 for WATCH, 0.25 for WAIT_FOR_PULLBACK, 0.0
for a fully blocking state — and every rung in this line of studies computes
`score = decision / (risk * 100) * state`. The multiplier is baked directly
into the **selection** score: a WATCH name's score is cut in half before it
is ever ranked against an otherwise-identical ACCUMULATE name's, which can
push it out of the top-N cut entirely and can move its rank inside the
0.5x-1.5x conviction tilt for names that do make the cut. Once a name is
selected, nothing in `baseline_weights` applies the multiplier again — a
WATCH name that survives the discounted cut gets a full, untouched weight.
So today's mechanism does the opposite of the pre-registration on both ends:
entry state decides *who*, and does nothing to *how fast*.

## The axis, and only the axis

| Rung | Entry-state role |
|---|---|
| `alpha_reliability.CONTROL` | multiplies the selection score |
| `ENTRY_STATE_THROTTLES_WEIGHT_NOT_SELECTION` | removed from selection/tilt, applied once to the held name's weight |

`_alpha_only_score` divides `entryStateMultiplier` back out of the score
`AR.reliability_scores` already computed — for an eligible row the
multiplier is always > 0, so the division is exact:
`score / state == decision / (risk * 100)`, the alpha/risk quantity with no
state term. Selection (`select_portfolio_by_scores`) and the conviction tilt
(`baseline_weights`'s `ranking_rows`) then run on that alpha-only score,
unmodified from production. After `baseline_weights` returns each held
name's risk-parity, tilt-adjusted target weight, that **same name's own**
`entryStateMultiplier` — the exact value production already computed, never
re-derived — shrinks it once. Capital the throttle withholds is left in
cash, **never redistributed** to other names: an under-approached position
is not fully funded yet, not a signal to fund something else more.

## What this axis does not touch

A multiplier of 0.0 (EVENT_RISK, AVOID, a non-POSITIVE research view,
insufficient data) remains a full eligibility exclusion — `ENTRY_OR_
RESEARCH_STATE_BLOCKS_SIZING` — on **both** rungs, for incumbents and new
entries alike, exactly as production computes it today. Whether an
incumbent should be forced out on a blocking state at all is explicitly the
pre-registration's own next claim about *exits*: "whether an incumbent
should be sold on a technical overheat trigger at all is a separate claim
about exits and gets its own test." This study changes only the continuous
throttle's role. `targetNames`, `maxNamesPerSector`, `maxNamesPerRegion`,
the cash floor and every cost assumption are unchanged from
`alpha_reliability.CONTROL`, called directly rather than reimplemented.

## Before the ladder: does this axis have any bite?

`entry_state_incidence` reads the control path's own scored candidates and
its own recorded held set (`retained`/`added` on the decision — **not** a
`selected` flag on the scored rows, which `select_portfolio_by_scores`
never sets on the caller's own row objects; see "A bug caught before
publishing" below). It recomputes the selected set with production's own
`select_portfolio_by_scores` on the alpha-only score and reports how often
the two disagree, before any performance number is read:

- Eligible names by state: `{'ACCUMULATE_GRADUALLY': 845, 'WAIT_FOR_PULLBACK': 1518, 'WATCH': 665}`
- Held names by state: `{'ACCUMULATE_GRADUALLY': 365, 'WAIT_FOR_PULLBACK': 197, 'WATCH': 160}`
- Rebalances where alpha-only selection would choose a different set:
  **130 of 155 (83.87%)**
- Names the discount kept out that alpha-only would hold: **258**
- Names the discount let in that alpha-only would drop: **258** (necessarily
  equal — both rungs hold the same COUNT per block under the same caps, so
  the two set differences are always the same size)

This axis clearly has bite: the discount changes the held set on the large
majority of rebalances.

## A bug caught before publishing

The first sealed run of `entry_state_incidence` reported `heldByState: {}`
and `namesTheDiscountLetIntoTheBook: 0` on every block — both mechanically
impossible if the diagnostic were reading real data. The cause:
`select_portfolio_by_scores` builds and mutates its **own** internal row
copies (`normalized = [dict(row) for row in scored]`), never the `scored`
list a caller hands it — so the rows stored in a decision's `scored` field
never carry a reliable `selected` flag, and the diagnostic's first version
was comparing the alpha-only selected set against an always-empty "original
selected" set. The fix reads the actual held set from `retained`/`added` on
the decision instead — the same fields `region_mix` (Study 3) and
`selection_behaviour` (every study) already use for exactly this reason.
This is recorded here rather than silently fixed, per this repository's own
discipline: a defect the code caught and corrected is a fact about the
measurement, not something to erase from the record.

## Result (two byte-identical sealed replays)

| | Control (state discounts selection) | Entry-at-weight |
|---|---:|---:|
| Net excess | -0.684pp | **1.385pp** |
| Gross CAGR | 13.564% | 8.976% |
| Matched benchmark | 12.845% | 6.671% |
| Sharpe | 0.853 | 0.813 |
| MDD | -25.158% | **-11.466%** |
| One-way turnover | 4.679x | 3.620x |
| Average cash held | 30.417% | **56.002%** |

**Average cash nearly doubled (30.4% → 56.0%).** This is the dominant
mechanism, not a side effect: alpha-only selection holds far more of the
WATCH/WAIT_FOR_PULLBACK names the discount used to exclude, and most of
those are exactly the names the new post-selection throttle then shrinks —
68.7% of held name-dates on the new rung carried a throttled weight,
withholding a mean of 66.7% of target when throttled. A materially smaller
invested fraction mechanically shrinks realized volatility (11.985% →
7.446%) and drawdown, and also moves the **matched benchmark** itself
(region-weighted to the book's own actual exposure), which is why the
benchmark row differs between rungs — the same pattern every prior study's
ladder shows.

**The gross gap is not merely that volatility effect.** The
arithmetic-selection / compounding split:

| Rung | Arithmetic selection | Compounding |
|---|---:|---:|
| Control | 0.315pp | 0.405pp |
| Entry-at-weight | **2.017pp** | 0.289pp |

The improvement is overwhelmingly arithmetic stock selection, not
compounding from lower volatility. On this sample, the names the discount
used to exclude realised **better** excess returns over their own region's
benchmark than the names it favoured — a claim about this historical
sample's realised outcomes, not a mechanism this study tested or a
prediction about future samples.

**The paired difference against the control is 2.069pp, 95% CI
[-1.881pp, +6.061pp] over 155 blocks — CONTAINS ZERO.** The point estimate
is large and in the favourable direction, but the interval does not clear
zero, and no permutation null was run. Nothing here is a promotion signal.

## What this study does NOT claim

- Not a promotion, not a production change.
- Not a claim that the state-discount mechanism is wrong in general — the
  large cash increase this rung produces is a specific consequence of
  applying the *existing* 0.25/0.5 multipliers as a *weight* throttle on
  *this* pool's actual WATCH/WAIT_FOR_PULLBACK incidence, not a general
  property of "separating alpha from entry state."
- Not a claim about *why* the excluded names outperformed on this sample —
  that would be a claim about the entry-state signal itself, untested here.
- No permutation null was run here.
- The paired interval is a point estimate on one historical sample, after
  several rungs across eight studies now, with no multiplicity correction.
- Nothing here changes `CHAMPION`, the production selector, production
  weights, Kelly, macro policy, regional rotation, `paperTrading` or
  `liveValidated`.
- Whether an incumbent should be force-exited on a blocking entry state is
  explicitly out of scope, per the pre-registration's own boundary.

## Reproducing

```
python scripts/run_entry_selection_separation_replay.py <sealed-ledger> \
  --output entry-selection-separation-report.json \
  --markdown entry-selection-separation-report.md
```

The runner refuses to write inside the sealed ledger, digests the ledger tree
before and after the run and raises on any change, and the workflow compares
its output byte-for-byte against the checked-in artifacts in `docs/results/`.
