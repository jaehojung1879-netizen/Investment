# Replay v14: the benchmark the KR leg was actually measured against

Run #52 was the first replay to complete end to end: `contractValidation` VALID,
`eligible: true`, no failures, 154 of 154 matured blocks, and the first
`historical/replay-v13/` seal this ledger has ever held. With the Korean history
restored to 2011-01-03 it also produced very different headline numbers:

| selector | CAGR | benchmark | annualised excess | Sharpe | MDD |
|---|---|---|---|---|---|
| `ALPHA_RANK_PER_DOWNSIDE_RISK` | 8.71% | 11.79% | −3.09%p | 0.61 | −29.46% |
| `CALIBRATED_EXPECTED_RETURN_PER_DOWNSIDE_RISK` | 15.26% | 10.63% | **+4.62%p** | 1.13 | −25.32% |

Under v12's truncated Korean panel the same two selectors came out at −5.47%p
and −3.31%p. The challenger moved **7.9 percentage points** on the restored
data alone.

That number is the reason this generation exists, because it is measured against
a benchmark that was never comparable to the US one.

## The defect

`config.json` paired two different kinds of instrument:

* **US — `SPY`.** An ETF. Its history carries the dividends its holdings pay, so
  it is a total-return series.
* **KR — `^KS200`.** A **price index**. It carries none of them.

So every KR excess return this ledger has published was measured against a
benchmark short by roughly the KOSPI 200 dividend yield, and was **flattered by
that much**. The KR leg's excess was overstated, the US leg's was not, and the
blended headline sat somewhere between the two with nothing recording the
difference. v12 and v13 both wrote the asymmetry down as a known limitation and
neither closed it.

This is not a rounding detail. It is the largest single bias left in the metric,
and it runs in the direction that makes the strategy look better.

## Why not a KOSPI 200 total-return index

Because there is not one to read. Measured directly against the cache
`FinanceDataReader` actually serves `^KS200` from:

```
ks200    → HTTP 200   Date,Close,UpDown,Comp,Change,Open,High,Low,Volume,Amount,MarCap
ks200tr  → HTTP 404
ks200_tr → HTTP 404
KS200TR  → HTTP 404
ks200tri → HTTP 404
```

The cache holds `ks11`, `kq11` and `ks200` — three price indices. FDR's own
source shows the authenticated `KrxIndexReader` route commented out, and KRX's
`getJsonData` endpoint answered **every one of 119 Korean tickers with `400 Bad
Request`** from the CI runner in run #49. An unreachable series is not an option,
and shipping an unproven endpoint is how run #49 happened.

## What v14 changes

The KR benchmark becomes **`069500.KS` (KODEX 200)**, a KOSPI 200 tracking ETF.

An ETF is quoted like any other listed name, so
`price_adjustment.to_total_return` gives it the *identical* as-traded forward
total-return basis SPY already gets. Both legs are now ETF total return on one
basis, and the two sides of the portfolio finally measure the same thing.

The cost is the ETF wrapper: roughly 0.15%/yr of fees and tracking error in the
KR benchmark against SPY's 0.09%. That residual asymmetry is an order of
magnitude smaller than the dividend yield it removes, and — unlike the yield —
it makes the benchmark *harder* to beat rather than easier, so it cannot flatter
the result.

### It is acquired through `korea_prices`, not from Yahoo

This is the part that matters more than the ticker. Yahoo serves 3,782 KOSPI 200
sessions against FinanceDataReader's 3,855, and five of the missing ones are
absent for the **entire** Korean cross-section — that is the defect v12 was built
to fix. Taking the benchmark from Yahoo just because the new ticker happens to be
quoted there would have walked it straight back in through the benchmark.

So the new `krx-total-return` route runs the same chain the Korean universe
runs: exchange-native sessions from FDR, distributions from Yahoo, one basis.
Yahoo stays configured as the second vendor, quoting the same instrument, so the
redundancy survives if the primary breaks.

### The fallback rule was clarified, not broken

`benchmark_source`'s contract says redundancy is across vendors, never across
instruments — and it explicitly named "a tracking ETF" as a forbidden
substitution. That rule governs **fallback**: a series that means one thing
before a vendor outage and another after it. Choosing a different instrument
deliberately, for the whole history at once, under a new `REPLAY_VERSION`, with
the old generation sealed beside it, is the opposite of that failure mode. The
docstring now says so rather than appearing to forbid the fix.

## Tests

`pytest tests/` — **826 passed** (`test_pack_roundtrip_preserves_inputs_and_bounds_asof`
fails in this sandbox on a pandas `datetime64[us]`/`[ns]` index dtype; identical
on `main`, green on CI for #90–#95).

Four new tests run the real chain with only the vendor calls stubbed:

* a flat-price benchmark paying one 2% dividend must end **above** where it
  started, step exactly once, and land on `1/(1 − d/prev)` — it returns the flat
  10,000.0 if the total-return rebase is removed
* sessions come from the exchange vendor, so three sessions missing from the
  distributions vendor cost the benchmark nothing — fails under Yahoo-only sourcing
* an empty exchange vendor yields `None`, so `evaluate_candidate` rejects it and
  the committed snapshot holds — fails under Yahoo-only sourcing
* the configured primary route exists in `FETCHERS` and is ordered first, or
  every run silently falls through to Yahoo

## What this does NOT fix

Two things still stand between these numbers and any conclusion, and v14 touches
neither:

1. **Neither selector is separated from its benchmark.** On the 154-block paired
   test the challenger's mean cost-adjusted excess is +0.33% with a 95% interval
   of **[−0.239, 0.854]**, and the champion's is −0.237% with **[−0.85, 0.311]**.
   Both intervals contain zero. 154 blocks is 27 effective independent dates.
2. **Survivorship reverses the comparison.** `REVERSES_UNDER_MEASURED_GAP`, with
   `gapByRegion: KR 100.0%` — no Korean historical constituent is vouched — and
   a breakdown scale of **0.053**: assuming just 5.3% of the measured gap flips
   which selector wins. `promotionEligible: False`; the integrity gate fails on
   `historicalUniverse` and `vintageMacro`.

Expect v14's excess numbers to come in **below** v13's, because the benchmark
now includes the dividends it was missing. A drop is the change working, not a
regression.

## Operator sequence

v14 is a new generation; v13's inputs stay sealed beside it. Benchmark returns
enter every outcome, so nothing from v13 can be reinterpreted on this basis.

1. `full=true`, `frozen_inputs=false`, `retrain=false`. Check that
   `benchmark source KR 069500.KS` reads `VENDOR via krx-total-return` — not
   `via yahoo`, and not `SNAPSHOT_FALLBACK`, which a new generation refuses
   anyway — that KR 126D benchmark coverage stays at 100%, and that
   `metricDefinition.benchmarkBasis` reports `BOTH_LEGS_TOTAL_RETURN`.
2. `full=false`, `frozen_inputs=true` — identical input hash and sealed
   cross-sections.
3. `full=false`, `frozen_inputs=false` — must extend the generation rather than
   raise `INPUT_VERSION_CONFLICT`.
4. Only if all three pass and `contractValidation` is eligible, run **Build
   insight data and deploy Pages**.

---

# Run #53: what the honest benchmark cost

v14's first production run went green — `contractValidation` VALID, `eligible:
true`, no failures, 154 matured blocks, and `benchmark source KR 069500.KS:
VENDOR via krx-total-return (3859 sessions through 2026-09-11)`, the primary
route with no fallback. KR and US 126D benchmark coverage both 100.0%.

The excess numbers fell, as predicted:

| selector | CAGR | benchmark CAGR | annualised excess | Sharpe | MDD |
|---|---|---|---|---|---|
| `ALPHA_RANK_PER_DOWNSIDE_RISK` | 8.31% | 13.19% | −4.87%p (was −3.09) | 0.58 | −29.46% |
| `CALIBRATED_EXPECTED_RETURN_PER_DOWNSIDE_RISK` | 14.22% | 13.14% | **+1.08%p (was +4.62)** | 1.06 | −25.42% |

The benchmark CAGR rose **+1.39%p** for the champion's weights and **+2.51%p**
for the challenger's — the challenger carries more KR, so it lost more of its
apparent edge. The challenger's headline excess fell by **3.55 percentage
points**, which is what a price-index benchmark had been worth.

Portfolio CAGR moved too (15.26% → 14.22%), so the drop is not purely the
benchmark: the run also refreshed point-in-time index membership and recorded
324 more signals (375,084 → 375,408), which changes cross-sections and therefore
selections. The benchmark effect is the benchmark CAGR column; the rest is the
universe.

## The consequence that matters

On the paired block test — the comparison `decisiveComparison` has always named
— the two selectors stopped being distinguishable:

```
v13:  champion − challenger  -0.567%   CI95 [-1.132, -0.101]   separated: True    CHALLENGER_BETTER
v14:  champion − challenger  -0.427%   CI95 [-1.006, +0.042]   separated: False   INDISTINGUISHABLE
```

Each selector against its own benchmark is the same story: the challenger is
+0.048% per block with CI **[−0.495, 0.551]**, the champion −0.379% with
**[−0.995, 0.179]**. Both contain zero, on 27 effective independent dates.

`survivorshipBound` consequently reports `NOTHING_TO_BOUND` — there is no longer
a sign for the gap to reverse. That is not an improvement in the evidence; it is
the evidence admitting it was never there.

## A verdict bug this exposed

With the paired test unseparated for the first time, `historicalComparison` kept
reporting **CHALLENGER_BETTER** — in `comparison` *and* in `promotionEvidence` —
because those fields were computed from three point-estimate inequalities
(excess, Sharpe, MDD) with no interval around them, while `decisiveComparison`
pointed at the paired test beside them. Until v14 the paired test happened to
separate every time, so the two had never disagreed and nothing caught it.

`promotionEligible` is hardcoded `False`, so nothing was promoted on it. But the
integrity gate is the next piece of work, and the moment it opens a promotion
record would have named a winner its own decisive test cannot tell apart.

`comparison_verdict()` now derives the verdict from the paired test whenever it
ran, publishes `historicalComparisonBasis` so a reader knows which comparison
answered, and keeps the point estimate under `pointEstimateComparison` rather
than letting it wear the verdict's name. Report version
`portfolio-validation-v4`. No `REPLAY_VERSION` bump: this changes how a verdict
is labelled, not any input or any computed outcome, so v14's seal stands and no
reacquisition is needed.
