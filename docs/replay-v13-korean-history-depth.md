# Replay v13: the green run that was quietly missing three and a half years

Run #48 was the first green replay this ledger has produced. `contractValidation`
came back **VALID**, `eligible: true`, no failures, 154 of 154 matured blocks
complete at the headline horizon, and for the first time a continuous NAV path —
so CAGR, MDD, Sharpe and Sortino exist:

| selector | CAGR | annualised excess | MDD | Sharpe | turnover |
|---|---|---|---|---|---|
| `ALPHA_RANK_PER_DOWNSIDE_RISK` | 8.11% | **−5.47%p** | −28.17% | 0.53 | 54.1% |
| `CALIBRATED_EXPECTED_RETURN_PER_DOWNSIDE_RISK` | 8.78% | **−3.31%p** | −37.62% | 0.54 | 49.3% |

The Korean vendor change worked exactly as intended: `KR market-wide gap dates in
the primary vendor: 0`, and the 2025-09-19 hole that blocked v9 through v11 is
gone.

But the run sealed **46,356 fewer Korean rows than v11**, and nothing said so.

## What went wrong

`fetch_fdr_prices` called `fdr.DataReader(code, start, end)`. For a KRX code that
dispatches to `NaverDailyReader`, and Naver's `fchart` endpoint takes **no date
argument at all**:

```python
url = 'https://fchart.stock.naver.com/sise.nhn?timeframe=day&count=6000&requestType=0&symbol='
r = requests.get(url + symbol)
...
return df.loc[start:end]          # start applied AFTER the fetch
```

Naver caps the response at roughly 3,000 items regardless of `count`, so every
name came back with about 3,000 trailing sessions and `start` was applied to a
window that had already been truncated. Measured against the v11 seal:

* 56 of 68 Korean names began **2014-06-23** instead of **2011-01-03**
* Korean rows fell from 236,978 to 190,622
* signals fell from 346,074 to 338,795

None of that failed anything. A short answer is a successful answer, and nothing
downstream can tell "this name listed in 2014" from "this download stopped at
2014" — except the other vendor, which has the earlier sessions. The v12
cross-check did record the symptom (`sessionsOnlyInSecondary: 46,407`) but
nothing acted on it.

A second, smaller defect rode along: Naver returns a derived `Change` column
beside the bar, and it was sealed into every Korean price row — a `pct_change`
computed on the pre-adjustment basis, stored next to a `Close` that no longer
matches it, and absent from the US rows.

## What v13 changes

* **Ask an endpoint that takes the date.** Naver's `siseJson` endpoint accepts
  `startTime`/`endTime` and returns the whole span, so the history goes as deep
  as it is asked to. Same basis as before — split-adjusted,
  dividend-unadjusted — so `price_adjustment.to_total_return` is unchanged.
  FinanceDataReader's default route stays as a fallback, and the truncation
  guard below means it can never quietly become the record again.

  This is the second attempt. The first went to KRX's own `getJsonData`
  (`MDCSTAT01701`, which does take `strtDd`/`endDd` and pages in two-year
  windows) and it answered **every one of 119 Korean tickers with
  `400 Bad Request`** from the CI runner — run #49. Only routes proven to
  answer from CI are used.
* **Seal only the bar.** Open, High, Low, Close, Volume. KRX also serves
  `Change`, `MarCap` and `Shares`; none of them is an input.
* **Stop where the failure is.** Run #49 lost every Korean ticker in the fetch
  and carried on for fifteen more minutes, to die at the benchmark preflight
  with `KR 126D: None% (0/0)` — a message about the benchmark, for a failure in
  the price fetch. The run now refuses to start when the Korean vendor serves
  fewer than 90% of the requested names, and says so with the vendor and the
  count.
* **Refuse to seal a truncated primary.** The cross-check now records each
  name's first session in both vendors. If the primary starts more than a month
  after the cross-check for any name, the run prints what is short and exits
  before committing the generation. A genuinely late listing starts late in both
  vendors, so its difference is zero and it passes.

## About those headline numbers

They are the first real ones this ledger has produced, and they say both
selectors **underperform**: −5.47%p and −3.31%p annualised over thirteen years,
at 49-54% turnover, with drawdowns of 28% and 38%.

Two things must be read alongside them before anyone treats them as final:

1. **The Korean history was three and a half years short.** v13's numbers will
   differ, and the early cross-sections are the ones that change most — before
   about 2015-06 the Korean names had no 273-session trailing history and were
   unrankable, so 2013-2015 was effectively US-only.
2. **The benchmark is not like-for-like.** The US leg is SPY total return; the
   Korean leg is `^KS200`, a **price index** that excludes distributions. The
   blended benchmark is therefore understated, which means the reported excess
   is *flattered* — the true shortfall is worse than the table shows. This
   predates v12 and is now the largest remaining asymmetry in the metric. It
   needs its own decision: source a KOSPI 200 total-return series, or state the
   asymmetry in `metricDefinition`.

Alpha diagnostics from the same generation point the same way: 126-day Rank IC
0.0059 for KR (`FAIL` on monotonicity) and 0.0096 for US (`WEAK`).

## Operator sequence

v13 is a new generation; v12's inputs stay sealed beside it.

1. `full=true`, `frozen_inputs=false`, `retrain=false`. Check that neither the
   `served only ... of ...` nor the `truncated history` error appears, that
   `KR market-wide gap dates in the primary vendor` is 0, and that the Korean
   panel now reaches 2011-01-03. `priceLineage[KR].routes` should read
   `naver-range` for every name; any `fdr-default` there is a name that fell
   back and whose depth the truncation guard then had to vouch for.
2. `full=false`, `frozen_inputs=true` — identical input hash, schedule and
   sealed cross-sections.
3. `full=false`, `frozen_inputs=false` — replay-v11's seal fix under test: it
   must extend the generation rather than raise `INPUT_VERSION_CONFLICT`.
4. Only if all three pass and `contractValidation` is eligible, run **Build
   insight data and deploy Pages**.
