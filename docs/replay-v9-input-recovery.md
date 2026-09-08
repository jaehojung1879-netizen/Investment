# Replay v9: source-backed input recovery and continuous-path gates

Replay v9 is a new experiment generation. It does not alter production scoring.
It changes historical valuation inputs and can change portfolio outcomes, so v8
objects and reports remain under their existing generation and are never relabelled.

## Why v8 remained blocked

The first full v8 run completed the expensive signal and outcome stages, then
correctly failed the portfolio audit. Champion measured 143/154 matured 21-session
blocks (92.857%) and Challenger 144/154 (93.506%). The missing blocks were not a
moving-calendar or determinism failure:

- Yahoo's `KRW=X` panel omitted union-calendar valuation dates, including dates
  on which one market was open. Exact-FX valuation therefore rejected otherwise
  measurable blocks.
- Yahoo omitted several market-wide Korean equity rows while the Korean benchmark
  had an observed session. Those were data-source holes, not exchange holidays.
- ESRX stopped printing quotes after its acquisition. Treating the contractual
  merger consideration as a missing price discarded the whole held portfolio.
- The report called the configured 90% completeness floor `sufficientForPath`,
  but separately failed on any missing block. The stricter outcome was safe, but
  the two concepts and the resulting reason were contradictory.

## v9 input policy

USD/KRW uses the Federal Reserve H.10 `DEXKOUS` series (KRW per USD) for the whole
generation. Every union-calendar valuation date resolves to the latest official
fixing dated on or before that session. This is a past-only publication carry,
not price interpolation; a fixing more than seven calendar days old is rejected.
Raw observations, resolved values, observation-date mapping, age and source policy
are separate content-addressed snapshot components. Yahoo and H.10 are not spliced.

Korean primary-price recovery is intentionally narrow. A date is eligible only
when the benchmark traded and at least 5% (and at least twenty) active Yahoo names
are absent despite having primary observations both before and after the date.
FinanceDataReader then supplies the missing session return. It is scaled from the
preceding Yahoo adjusted close and accepted only when its bridge return to the next
Yahoo observation differs by at most 25 bps. Gaps over three KRX sessions,
individual-name gaps, missing bridges and adjustment mismatches remain missing.
The threshold is grounded in the v8 snapshot: each five observed failure dates
lost 61–68 of 638–686 active names (9.56–10.15%) as one repeatable vendor batch,
while names immediately before and after were present.
Every accepted and rejected attempt is snapshotted. This is observed fallback data,
not linear interpolation and not a suspension/delisting imputation.

The reviewed corporate-action ledger currently covers the Express Scripts merger.
An ESRX share held across 2018-12-20 becomes USD 48.75 cash plus 0.2434 CI shares,
using the terms in the [SEC-filed announcement](https://www.sec.gov/Archives/edgar/data/1532063/000119312518074974/d549178dex991.htm)
and the [issuer's completion notice](https://newsroom.thecignagroup.com/Cigna-Completes-Combination-with-Express-Scripts-Establishing-a-Blueprint-to-Transform-the-Health-Care-System).
The cash remains exposed to USD/KRW until the next scheduled rebalance and earns no
assumed yield inside that block. The CI component becomes the terminal holding for
turnover. The action cannot make ESRX purchasable on or after its effective date.

The manifest policy binds the recovery implementation version and corporate-action
book hash. Components include prices, benchmarks, historical universe, PIT
fundamentals, macro vintages, VIX, raw and resolved FX, dated risk-free coverage,
calendar, recovery audit and corporate actions. A later vendor correction inside a
sealed prefix causes `INPUT_VERSION_CONFLICT`; it never modifies v9 quietly.
PR #85's schedule/cross-section determinism guard remains the final independent gate.

## Completeness and comparability

Two gates are now explicit:

| Gate | Requirement | What it authorizes |
|---|---:|---|
| Block evidence | configured floor (currently 90%) | distributional block diagnostics, with every omission disclosed |
| Continuous headline | 100% of matured fixed blocks | chained NAV, CAGR, MDD, Sharpe and Sortino |

Passing the first never authorizes joining an unknown interval. A missing matured
block reports `continuous_nav_has_unknown_intervals` and still blocks publication.
`HORIZON_NOT_MATURED` stays outside the eligible denominator. `EMPTY_PORTFOLIO`
stays a measured 100% KRW cash decision and its long-interval asymmetry remains in
the report.

The v8 headline is unavailable, and v9 has not been run at PR time. Therefore no
headline metric can be compared yet:

| Generation | Champion 21-session matured coverage | Challenger coverage | Headline comparison |
|---|---:|---:|---|
| v8 observed | 143/154 (92.857%) | 144/154 (93.506%) | unavailable: unknown intervals |
| v9 PR | not run | not run | not directly comparable; FX/action/input definition changed |

## Remaining limits and operator sequence

H.10 is a reference fixing, not an executable FX total-return product. The BOK
policy rate is still a cash proxy. Daily closes do not model simultaneous KR/US
execution, taxes beyond configured costs, intraday drawdowns or corporate-action
cash interest before rebalance. The historical-universe and PIT-fundamental coverage,
especially early years and former US members, remain the dominant evidence limits.
FDR bridge acceptance proves consistency only around the recovered hole; it does
not prove the vendor's entire history. None of this changes `liveValidated` status.

After merge, run these workflows in order:

1. **Historical point-in-time replay** with `full=true`, `frozen_inputs=false`,
   `retrain=false`. This acquires v9 inputs and performs the full replay.
2. **Historical point-in-time replay** with `full=true`, `frozen_inputs=true`,
   `retrain=false`. Confirm identical snapshot hash, fixed schedule and a reproducible
   determinism verdict.
3. If both runs and the portfolio contract pass, run **Build insight data and deploy
   Pages**. Do not deploy a blocked report and do not lower either gate.

The next full replay requires both the new `DATA_VERSION` and `REPLAY_VERSION`
already introduced by this change. A later correction to a date sealed into v9
requires another explicit generation; a frozen reproduction of v9 does not.
