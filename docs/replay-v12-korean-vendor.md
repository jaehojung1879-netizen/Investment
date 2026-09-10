# Replay v12: Korean sessions from the exchange, not from Yahoo

Replay v11 was the first run whose portfolio audit completed, so it is the first
run whose blocked verdict means anything. It said what the three before it had
been unable to say: `contractValidation` BLOCKED on
`continuous_nav_has_unknown_intervals`, one date, 2025-09-19, six held names,
153 of 154 matured blocks complete at the headline horizon (99.35%).

It also closed the last open question about that date.

## What v11 proved

v11 narrowed the same-vendor retry to one window per gap cluster — v10 had built
a single eight-year window spanning every systemic date, so the "focused retry"
had been a bulk download of the same shape that dropped the rows. With the fix
in place the retry ran correctly against all five market-wide holes and
recovered **nothing**:

```
krPriceSummary: targetedYahooRetries: 0, basisBoundReconstructions: 0
                accepted 284 (all FDR_RETURN_ANCHORED_TO_PREVIOUS_PRIMARY_CLOSE)
                rejected 42 (all RAW_RETURN_BRIDGE_MISMATCH, all 2025-09-19)
```

Yahoo does not have those sessions. It serves 3,782 KOSPI 200 sessions against
FinanceDataReader's 3,855 — 73 KRX sessions, 1.9% of the record — and five of
them are absent for the entire Korean cross-section: 2017-09-22, 2017-12-20,
2022-01-03, 2022-05-09, 2025-09-19, each missing for all 61-68 names active on
the day. A session a vendor does not have cannot be retried into existence.

Two other explanations were ruled out on the v11 telemetry:

* **Not dividends.** All 42 rejected rows report
  `adjustedBridgeDifferenceBps == rawBridgeDifferenceBps` to four decimals. On
  the v11 basis the "adjusted" panel *is* the as-traded forward total return, so
  equality means no distribution fell between the anchors.
* **Not a shifted session label.** If Yahoo's 09-22 bar were really 09-19's, the
  bridge difference would equal each name's own 09-19 → 09-22 return: it would
  scale with that name's daily volatility and be about one day's move. Measured
  across the 42: correlation with daily volatility **-0.074**, and the median
  difference of 55 bps is **0.32x** a typical day's move (median 171 bps). It is
  the price level, not the calendar.

So the bridge check was refusing correct FDR observations because it measured
them against Yahoo anchors that are themselves off by a median 55 bps, maximum
227 bps. The whole Korean recovery apparatus existed to paper over a vendor
choice, and inside that choice it could not succeed.

## What v12 changes

`pipeline/korea_prices.py` acquires the Korean panel from two sources, each for
what it is actually good for:

* **FinanceDataReader** serves every KRX session's bar. Naver quotes
  split-adjusted, dividend-unadjusted closes — the same shape as Yahoo's
  unadjusted close — so `price_adjustment.to_total_return` treats both
  identically and v11's as-traded forward total-return basis carries over
  unchanged.
* **Yahoo** serves the dividends and splits, which FDR does not publish. Both
  vendors quote to the same split basis, so an event transfers across without
  rebasing.
* **Yahoo's closes are kept as a cross-check.** Every session both vendors quote
  is compared and the disagreement — median, p99, worst, and how many sessions
  each vendor has that the other does not — is summarised into
  `diagnostics.priceLineage` and sealed as the static `price/source` component.
  It is evidence about the second vendor, not something to prefer away.

The two panels are never spliced within a ticker: a name is served whole by the
exchange-native vendor or it is reported missing.

`recover_systemic_kr_gaps` is replaced in the replay path by
`detect_systemic_kr_gaps`. The detector still runs, because a market-wide hole
in the PRIMARY source must be visible, but nothing is reconstructed. If FDR ever
loses a session the coverage gate fails loudly instead of bridging from a vendor
that disagrees with it.

## Known limitation, unchanged by this work

The US benchmark (SPY) is a total-return series and the Korean benchmark
(`^KS200` via FDR) is a **price index**. KR excess returns are therefore
measured against a benchmark that excludes distributions, which flatters them by
roughly the KOSPI 200 dividend yield. This predates v12 and is not introduced by
it, but it is now the largest remaining asymmetry in the metric and it should be
decided on its own: either source a KOSPI 200 total-return series or state the
asymmetry in `metricDefinition`.

## Operator sequence

v12 is a new generation; v11's inputs stay sealed beside it.

1. **Historical point-in-time replay** — `full=true`, `frozen_inputs=false`,
   `retrain=false`. Check the log line `KR sessions via
   krx-fdr-sessions-with-yahoo-distributions-v1`, that `KR market-wide gap dates
   in the primary vendor` is **0**, and that the audit writes a **replay-v12**
   report.
2. The same workflow — `full=false`, `frozen_inputs=true`. Must reproduce the
   identical input hash, schedule and sealed cross-sections.
3. `full=false`, `frozen_inputs=false`. This is v11's fix under test: under v10
   it was guaranteed to fail with `INPUT_VERSION_CONFLICT`, and it must now
   extend the generation instead.
4. Only if all three pass and `contractValidation` is eligible, run **Build
   insight data and deploy Pages**.
