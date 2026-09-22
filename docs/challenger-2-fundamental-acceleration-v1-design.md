# CHALLENGER-2 design proposal: fundamental-acceleration-v1

> **Design only. Not executed in this PR.** No backtest, no code, no
> production change. This document pre-registers the next study so that,
> once a human reviews and approves it, implementation can proceed without
> re-litigating the axis, the horizon, or the validation plan after seeing
> a result.

## The question

Does the RATE OF CHANGE in a company's own profitability, margins and
growth — measured filing-over-filing, strictly point-in-time — carry
information about future benchmark-relative return that the current
Quality sleeve's LEVEL measurement does not?

## Exact raw fields

Read directly from `FundamentalStore`'s existing `PIT_FUNDAMENTALS_V1`
rows (KR via `dart_derive.derive_fields`/`pit_record`, US via
`finnhub_derive.derive_fields`/`pit_record` — same field names, same
shape, already production-proven):

| Field | Source function | Definition |
|---|---|---|
| `roe` | `_ratio(net_income, equity)` | TTM net income / equity level |
| `operatingMargin` | `_ratio(operating, revenue)` | TTM operating income / TTM revenue |
| `profitMargin` | `_ratio(net_income, revenue)` | TTM net income / TTM revenue |
| `earningsGrowth` | YoY TTM net income change | `(net_income_t - net_income_{t-4q}) / abs(net_income_{t-4q})` |
| `debtToEquity` | `_ratio(debt, equity)` | Level, sector-exempt per `SECT.LEVERAGE_EXEMPT_SECTORS` |

Every filing row also carries `reportPeriod`, `reportDate` (period end) and
`availableFrom` (receipt/filing date — the only field licensed for PIT
use).

## Source

- KR: DART, via the existing `dart_fundamentals.py` collector and
  `dart_derive.py` derivation. No new collection.
- US: Finnhub, via the existing `finnhub_fundamentals.py` collector and
  `finnhub_derive.py` derivation. No new collection.

## Timestamp / PIT semantics

For a candidate acceleration reading at replay date `T` for ticker `X`:

1. Find the most recent filing `F_t` for `X` with `availableFrom <= T`
   (this is exactly what production's `FundamentalStore.snapshot` already
   does for the level factors).
2. Find the immediately PRECEDING filing `F_{t-1}` for the same ticker
   (one report period earlier in the append-only, ticker×fiscalYear×
   reportCode-keyed store).
3. **Both legs must independently satisfy `availableFrom <= T`.** `F_{t-1}`
   was, by construction, filed before `F_t`, so this is automatically true
   once `F_t` itself clears the PIT gate — but the check is asserted
   explicitly in code, not assumed, exactly as `contraction_holds` is
   asserted for the confidence weight in `alpha_reliability.py`.
4. If either filing is missing, or the two filings are not consecutive
   report periods (a gap — e.g. `F_{t-1}` is stale because a quarter was
   never filed), the acceleration reading is `None` for that name-date.
   **A missing prior filing is never treated as zero.**
5. Acceleration for a field `f` is `f(F_t) - f(F_{t-1})`, in the field's
   own units (a percentage-point change for `roe`/`operatingMargin`/
   `profitMargin`; a change in a growth rate, not a second derivative, for
   `earningsGrowth`).

## Transformation

For each of `roe`, `operatingMargin`, `profitMargin`, `earningsGrowth`:
`accel_f = f(F_t) - f(F_{t-1})`. A composite "fundamental acceleration
score" is the sector-neutral z-score of each `accel_f`, averaged across
the fields present (evidence-weighted exactly as the existing sleeves
are — no new blending rule invented). `debtToEquity`'s acceleration is
computed and reported but is **not** included in the composite by default
(a shrinking or growing balance sheet is a different economic claim from
profitability/growth inflection); this is a design choice stated here,
before any result, and is itself a candidate ablation rung for the
CHALLENGER-2 study's own ladder, never a post-hoc tune.

## Cross-sectional normalization

Sector-neutral z-score within `(date, region)`, identical in form to the
existing `sector_neutral_z` production already uses for the level factors
— no new normalization scheme is introduced.

## Expected direction

Positive: names whose profitability/margins/growth are accelerating are
expected to realise higher benchmark-relative forward return than names
that are decelerating, at the same LEVEL of Quality. This is the
"fundamental momentum" / earnings-acceleration hypothesis (adjacent to,
but distinct from, price momentum and from static profitability).

## Primary horizon and primary statistic

Following `four-factor-signal-attribution-audit-v1`'s own precedent: fixed
at **126 trading days**, primary statistic **pooled-within-region Rank
IC** via the same fixed-effect inverse-variance combination
(`pool_region_summaries`), computed BEFORE any ladder or backtest, exactly
reusing `historical_outcomes.horizon_frame` and
`portfolio_validation._nw_summary`. No new statistical machinery.

## What this study will NOT do (carried over from every prior study's discipline)

- No portfolio backtest in its discovery stage.
- No factor-weight optimisation.
- No threshold or window sweep.
- No promotion, no `CHAMPION`/`config` change.
- No claim of "beating" the existing sleeves on `replay-v16` — the
  primary claim is standalone/incremental Rank IC evidence, read with the
  same Holm correction discipline `four-factor-signal-attribution-audit-v1`
  established.

## Independent validation split

Per the feasibility audit's finding that no unused historical period or
independent external dataset exists:

1. **Primary: prospective.** Starting from a date fixed BEFORE any
   acceleration value is computed or seen, the signal is generated
   going forward on live PIT filings and sealed. It is scored only once
   its 126-day horizon matures (a ~6-month minimum wait before any
   result exists) and the CHALLENGER-2 study's own confirmatory claim
   rests on this window, never on `replay-v16`.
2. **Bridge: `replay-v16`, discovery-only.** While the prospective window
   matures, the same Rank IC / Holm / redundancy / incremental-IC
   machinery `four_factor_signal_attribution_audit.py` already built is
   reused (not reimplemented) to read the acceleration signal's basic
   properties on the sealed ledger — coverage, cross-sectional
   distribution, and correlation with the existing level-Quality factor
   (the direct test of this design's own Gate-2 prediction). This is
   explicitly labelled `DISCOVERY_ONLY` in every artifact it produces and
   is never cited as confirmatory evidence for promotion.

## Failure criterion

The candidate is abandoned (not re-specified, not re-tuned) if any of:

- The two-consecutive-filing requirement collapses coverage far below the
  existing level-Quality factor's coverage (measured, not assumed, as the
  first diagnostic the discovery stage runs).
- The acceleration composite's cross-sectional correlation with the
  existing level-Quality factor is high enough that it reads as a
  relabelling rather than new information (a threshold specified before
  the correlation is computed, not after).
- The prospective validation's paired interval does not separate from
  zero and the point estimate is unfavourable (the same
  `DIRECTIONAL_BUT_NOT_STATISTICALLY_SEPARATED` vs `CONTAINS ZERO`
  discipline every prior study in this line already applies).
- A PIT leakage path is found in implementation that cannot be closed
  without look-ahead.

## What happens after this design is approved

Nothing, in this PR. Implementation (a new
`pipeline/fundamental_acceleration_discovery.py` module, its own tests, a
runner, and eventually the prospective sealing mechanism) is a SEPARATE,
FUTURE PR, started only after a human reviews this design — per the
pre-registration's explicit instruction not to auto-start the next study.
