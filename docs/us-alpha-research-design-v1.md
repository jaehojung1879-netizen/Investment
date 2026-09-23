# US alpha research, defined independently — v1

> **Design and candidate pre-registration only. Not executed in this PR.**
> No backtest, no candidate scoring against historical return, no code.
> This document defines the US alpha research PROBLEM (universe, benchmark,
> existing evidence, next candidate) as independent from KR's, per
> `docs/regional-alpha-research-separation-v1.md`.

## The question

Not "which factor works in both KR and US" — **"what information, cleanly
observable in the US market, distinguishes future US benchmark-relative
return?"** KR's answer is a separate question
(`docs/kr-alpha-research-design-v1.md`), asked and answered independently.

## Universe and benchmark (confirmed against current code)

- Universe: `config.json universe.US` — S&P 500-derived, resolved via
  `pipeline/universe.py`'s `_us_sp500()` (FinanceDataReader listing +
  constituent-CSV fallback, fails closed under 450 names — never a partial
  fallback).
- Benchmark: **SPY**, as-traded forward total-return basis
  (`config.json benchmark`/`benchmarks.US`, `benchmark_source.py`).
  Confirmed to match the actual code, not assumed.
- Fundamentals: Finnhub, via `finnhub_fundamentals.py`/`finnhub_derive.py`
  (PIT-exact, `availableFrom` = SEC accepted-filing date).
- Prices: Yahoo (`datafeed.py:fetch_prices`), as-traded forward
  total-return.

US factor results are evaluated only against US outcomes. A US hypothesis
is never scored against KR realised returns.

## Existing US evidence (read-only summary, not re-scored here)

From `four-factor-signal-attribution-audit-v1` and
`fundamental-acceleration-discovery-v1`, US-only readings:

| Signal | US standalone 126D pooled IC | 95% CI | Coverage note |
|---|---:|---|---|
| Momentum | region-sign-unstable component | — | none |
| Value | region-sign-unstable component | — | US value missing-rate 20.11% (materially better than KR's 55.45%) |
| Quality | region-sign-unstable component | — | US quality missing-rate 0.96% (materially better than KR's 53.99%) |
| Lowvol | negative pooled component | — | none |
| Fundamental Acceleration | -0.0056 | [-0.0295, +0.0183] | 81.79% coverage — a *clean* read, not a coverage-confounded one (unlike KR's) |

US fundamental data coverage is good enough that "no evidence" readings here
are relatively trustworthy reads of the signal itself, not reads of missing
data. This is why Fundamental Acceleration is **not** re-proposed as the
next US candidate below — it already has a clean, coverage-unconfounded US
answer from a completed study, so re-testing it would not be a new
hypothesis.

## Candidate gates (Section 17)

Every candidate below is evaluated against five gates, in this fixed order,
**before** any historical return is looked at (Section 19):

- **Gate 1** — Genuinely new economic information versus the existing
  4-factor (momentum/value/quality/lowvol)?
- **Gate 2** — Sufficient PIT historical data, confirmed or plausibly
  confirmable, not assumed from a vendor's marketing page?
- **Gate 3** — Sufficient US universe coverage (not a handful of
  mega-caps only)?
- **Gate 4** — Collectible at reasonable, sustainable cost (free or
  low-cost tier, compatible with a personal-project budget)?
- **Gate 5** — Compatible with future prospective sealing (computable from
  a PIT-safe input at the time, with no look-ahead)?

## Candidates considered

| Candidate | Gate 1 (new info) | Gate 2 (PIT data) | Gate 3 (coverage) | Gate 4 (cost) | Gate 5 (sealable) | Verdict |
|---|---|---|---|---|---|---|
| **A. Analyst EPS revision** (consensus estimate change over a trailing window) | Pass — expectations-revision information, distinct from trailing factor levels | **Uncertain** — Finnhub's estimate-revision endpoints are widely understood to sit behind a paid tier; this was already flagged in `challenger-2-signal-source-feasibility-v1` and not re-probed in this PR | Unknown pending Gate 2 | **Likely fails** without a confirmed free/low-cost source | Pass in principle | **Not selected — Gate 2/4 unresolved, not re-verified here** |
| **B. Estimate dispersion** (std dev of analyst estimates) | Pass — genuinely different from a point-estimate factor | Same Gate 2 concern as A (same vendor family) | Unknown pending Gate 2 | Same Gate 4 concern as A | Pass in principle | **Not selected — same unresolved dependency as A** |
| **C. Earnings surprise with consensus** (actual EPS vs analyst consensus at announcement) | Pass — an expectations-violation signal, not a level or trend | Depends on the SAME consensus-estimate data as A/B for the "expected" side | Unknown pending Gate 2 | Same Gate 4 concern | Pass in principle | **Not selected — collapses into the same unresolved consensus-data dependency** |
| **D. Relative-strength breadth / persistence** (fraction of trailing rolling sub-windows in which the name outperformed its own region benchmark, i.e. consistency of edge rather than its size) | **Pass, but requires care** — sourced from the same underlying price series Momentum already uses; the claim is deliberately reframed as a *steadiness* measure (how often, not how much), distinct in kind from a magnitude-based momentum sleeve | **Pass** — zero new data; entirely derivable from price history already collected for Momentum/Lowvol | **Pass** — full US universe, no vendor gap | **Pass** — zero incremental cost | **Pass** — computable identically in a live/prospective context | **Selected — see design below** |
| **E. Valuation change / re-rating** (change in a valuation multiple over a trailing window) | **Marginal** — economically close to a first derivative of the existing Value sleeve (a re-rating is definitionally a multiple change), so orthogonality from Value is the open question, not assumed clear | Pass — derivable from already-collected Finnhub fundamentals + price | Pass | Pass | Pass | **Not selected this round** — Gate 1 orthogonality is a real open question a dedicated study should answer explicitly, not wave through; kept as the second-ranked candidate for a future round |

**D — Relative-strength breadth/persistence — is the pre-registered next US
hypothesis.** It is the only candidate that clears Gate 2/3/4/5 without any
unverified vendor dependency, and its Gate 1 concern is addressed by
construction (steadiness, not magnitude) rather than assumed away.

## D: design (pre-registered, not executed)

**Hypothesis.** A name whose forward return has been *consistently*
positive relative to its own region's benchmark across many trailing
sub-windows carries different information than one whose average edge is
identical but concentrated in a few large moves. Momentum's 12-1M/6M
inputs measure magnitude over one or two windows; this candidate measures
the SHAPE of the trailing return path.

**Exact construction.**
1. Over a trailing `N`-week lookback (`N` fixed before any result is
   computed — proposed `N = 52`, one trading year, matching Momentum's own
   annual scope), compute the stock's own weekly excess return over its
   region benchmark for each of the `N` weeks.
2. `breadth = (count of weeks with positive excess return) / N`.
3. Sector-neutral z-score of `breadth` within `(date, US)`, using the
   existing `longterm.sector_neutral_z` at its production `winsor=2.5`
   default — no new normalization invented.
4. This is a single-field sleeve (unlike Momentum's two-input blend);
   `factorCoverage` accounting follows the same evidence-coverage
   convention every existing sleeve uses.

**PIT semantics.** Every week's excess return in the trailing window uses
only price data with a timestamp `<= asOfDate` — identical PIT contract to
the existing price-based sleeves (Momentum, Lowvol). No fundamental data,
so no filing-timing question arises.

**Primary horizon and statistic.** 126 trading days, pooled-within-region
(US-only here) Rank IC via `pool_region_summaries`/`_nw_summary`, reusing
`four_factor_signal_attribution_audit.py`'s machinery exactly as
`fundamental-acceleration-discovery-v1` did — no new statistical method.

**Orthogonality check (Stage B, before any return is read).** Pooled
Spearman(breadth-percentile, momentum-percentile) within `(date, US)`
cross-sections. A pre-registered failure threshold of `|rho| >= 0.70`
(matching `fundamental-acceleration-discovery-v1`'s own threshold) applies
— if breadth turns out to be a relabelling of momentum, the candidate is
abandoned, not re-defined.

**Coverage floor.** `>= 0.60` data-sufficient ratio (same threshold as the
fundamental-acceleration study), computed as (weeks with a valid price
observation) / N per name-date.

**Failure criterion (fixed before any result).** The candidate is
abandoned, not re-tuned, if any of:
- Orthogonality vs Momentum fails the 0.70 threshold above.
- Coverage falls below 0.60.
- The prospective validation's paired interval does not separate from
  zero and the point estimate is unfavourable (same
  `DIRECTIONAL_BUT_NOT_STATISTICALLY_SEPARATED` vs `CONTAINS ZERO`
  discipline every prior study in this line applies).

## What happens after this design is approved

Nothing, in this PR. Implementation (`pipeline/us_relative_strength
_breadth_discovery.py`, its own tests, a runner, execution against sealed
`replay-v16`, and eventually `US_SIGNAL_SEAL` prospective sealing) is a
separate, future PR — per `US_ALPHA_DISCOVERY_BUDGET = 1`
(`docs/regional-alpha-research-separation-v1.md` Section 16), this is the
ONE US-only historical discovery study this research line will run before
either finding meaningful evidence (proceed to prospective validation) or
declaring `HISTORICAL_ALPHA_DISCOVERY_PHASE = CLOSED` for US.


## Pre-result supersession: regional-alpha-model-v1

The architecture decision in [regional-alpha-model-v1](regional-alpha-model-v1.md)
supersedes the standalone US breadth / KR FX-beta historical discovery plans.
Those candidates enter the regional model lineage gate as features; neither
standalone winner-search runs first. The model study consumes the one remaining
historical discovery budget in each region. After that run,
`HISTORICAL_ALPHA_DISCOVERY_PHASE=CLOSED`, irrespective of results.
All historical evidence is `DISCOVERY_ONLY`; `promotionEligible=false`.
This is a pre-result research decision and changes no production setting.
