# Replay v11: why every generation died on its second acquisition run

Replay v7, v8, v9 and v10 each lasted one or two runs before the ledger had to
start over. The reason was never the evidence. It was that the input the store
seals cannot be sealed.

## The measurement

`InputStore.commit` compares the published prefix byte for byte:

```python
prefix = [r for r in components.get(key, []) if str(r.get("date") or "") <= prior["through"]]
if digest(prefix) != digest(old.get(key, [])):
    raise InputVersionConflict(f"{key}: published input prefix changed/recovered; ...")
```

Comparing the seals replay-v9 (run #42) and replay-v10 (run #44) committed —
one day apart, same vendors, same pinned lineage — for **January 2011**:

| component | rows | byte-identical? |
|---|---|---|
| `^KS200` via FDR | 21 | **all 21 identical** |
| `SPY` via Yahoo adjusted close | 20 | 18 differ |
| `price/2011-01` (US + KR universe) | 11,392 | 8,321 differ (73%) |

Splitting `price/2011-01` by size of the move separates two causes cleanly:

* **550 of 567 tickers** moved by less than 1e-6 over the whole month — median
  1.25e-07, one float32 step. Round-off in a 15-digit JSON serialisation of a
  float32-precision value.
* **17 tickers** moved by 3 to 86 bps: SWK 86, `003550.KS` 84, AEE 70, CI 55,
  BLK 51, AJG 27, ROST 19, WDC 3. Every one of them went **ex-dividend between
  the two fetches**.

That second group is the fatal one. Yahoo's auto-adjusted close is a
**back-anchored** total-return series: each value is scaled by the dividends
that come *after* it, so a distribution paid today rewrites that ticker's entire
history back to 2011. In a 500-name universe some names go ex-dividend nearly
every session, so the "immutable published prefix" legitimately changes every
day and `commit` must refuse.

`DATA_VERSION` said both `yahoo-adjusted-close-v3` and `immutable-inputs-v1`.
Those two cannot both hold. Run #43 and run #46 conflicted on the identical
component, `benchmark/2011-01`, three generations apart — v10's pinned vendor
lineage was a real fix for a real second cause, and it could not have fixed
this one.

## What v11 seals instead

`pipeline/price_adjustment.py` rebases the same vendor rows so the seal is
append-only:

1. **Undo the splits.** Yahoo's *unadjusted* close is still split-adjusted, so a
   later split divides every earlier close. Multiplying each session by the
   ratio of the splits that come after it cancels that exactly — a new split
   divides the fetched close and multiplies the correction by the same number —
   and what is left is the price that actually printed.
2. **Accumulate the total return forward.** From the first session, with
   Yahoo's own factor `1 / (1 - dividend / previous close)` at each ex-date and
   the split ratio at each split. A dividend paid tomorrow multiplies tomorrow
   onward and touches nothing already published.
3. **Seal the events too.** Dividends and splits are non-zero on a handful of
   sessions, so they go in their own sparse `corporate-events/<YYYY-MM>`
   component rather than widening every price row. The adjustment is then
   auditable row by row from the ledger alone.

Forward anchoring changes the level by **one constant factor per ticker** and
nothing else: the series stays exactly proportional to Yahoo's adjusted close.
Momentum, volatility, drawdown, benchmark excess and NAV growth are all ratios
of it, so **nothing that is measured changes**. This is a provenance fix, not a
new metric. `metricDefinition.priceBasis` states it in every published report.

`tests/test_replay_evaluation.py` pins both halves: the forward index is
proportional to the backward one, a 2:1 split recovers the 100/101/102 that
printed and leaves the index continuous, a dividend landing past the cutoff is
accepted as an append — and, as the control, the same store still refuses the
rescaled adjusted close that v10 was sealing.

## Also in v11: the targeted retry is actually narrow

`recover_systemic_kr_gaps` built one retry window from `min(systemic)` to
`max(systemic)`. On run #44 those were 2017-09-22 and 2025-09-19, so the
"small-window retry" was an eight-year bulk download of every affected name,
twice — the same shape of request that dropped the rows. The run reported
`targetedYahooRetries: 0` and `basisBoundReconstructions: 0`: the designed
first-choice recovery had never once succeeded. Each contiguous run of
market-wide gap dates now gets its own window over only the names missing in
it, and the retry is fetched on the same as-traded basis as the panel it
splices into.

Whether that is enough to close the 2025-09-19 KRX hole — 42 of 68 active
Korean names, the reason both selectors still report
`continuous_nav_has_unknown_intervals` — is not knowable before the run. Run
#44's telemetry disproved v10's explanation for it: every rejected row had
`adjustedBridgeDifferenceBps` and `rawBridgeDifferenceBps` agreeing to four
decimals (`012330.KS` 176.5655 vs 176.5650), so the adjustment basis was never
the disagreement; Yahoo and FDR simply disagree about the 09-18 → 09-22 price
ratio for those names.

## Limits

* SPY's dividend and split events are not sealed. `benchmark_source.resolve`
  returns one close series per benchmark, and the total return is accumulated
  inside the fetcher, so the benchmark's basis is stable and its lineage is
  sealed but the events behind it are not separately auditable from the ledger.
* `^KS200` is a price index with no distributions; it was already bit-stable
  across generations and is unchanged.
* The prospective daily build (`pipeline/build.py`, `scripts/update_ledger.py`)
  still uses Yahoo's auto-adjusted close. That path seals nothing, so the
  instability costs it nothing.

## Operator sequence

v11 is a new generation; v10's inputs cannot be reinterpreted on the new basis
and stay sealed beside it.

1. **Historical point-in-time replay** with `full=true`, `frozen_inputs=false`,
   `retrain=false` — acquires the v11 inputs and runs the full replay.
2. The same workflow with `full=false`, `frozen_inputs=true` — must reproduce
   the identical input hash, schedule and sealed cross-sections.
3. A third run with `frozen_inputs=false` is the one that matters for this
   change: under v10 it was guaranteed to fail with `INPUT_VERSION_CONFLICT`,
   and under v11 it must extend the generation instead.
4. Only if all three pass and `contractValidation` is eligible, run **Build
   insight data and deploy Pages**.
