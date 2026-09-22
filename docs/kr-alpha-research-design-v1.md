# KR alpha research, defined independently — v1

> **Design and candidate pre-registration only. Not executed in this PR.**
> No backtest, no candidate scoring against historical return, no code.
> This document defines the KR alpha research PROBLEM as independent from
> US's, per `docs/regional-alpha-research-separation-v1.md`. Korean alpha
> research does not assume the same factor that works (or fails) in the US
> must work (or fail) the same way in KR.

## The question

**"What information, cleanly observable in the Korean market — including
Korea's own economic, flow, and currency structure — distinguishes future
KR benchmark-relative return?"** Answered independently of
`docs/us-alpha-research-design-v1.md`.

## Universe and benchmark (confirmed against current code)

- Universe: `config.json universe.KR` — KOSPI market-cap-based, resolved
  via `pipeline/universe.py`'s `_kr_kospi()` (FinanceDataReader listing
  sorted by market cap, truncated to `cfg.universe_size`).
- Benchmark: **069500.KS** (KODEX 200, a KOSPI 200 tracking ETF), as-traded
  forward total-return basis via `korea_prices.py`'s
  `_krx_total_return_close` route — deliberately **not** `^KS200` (a price
  index that excludes dividends; see `config.json`'s own
  `benchmarkSources._notes`). Confirmed to match the actual code.
- Fundamentals: DART, via `dart_fundamentals.py`/`dart_derive.py`
  (PIT-exact, `availableFrom` = DART 접수일자 receipt date). DART serves
  from 2015; the replay starts 2013, so KR value/quality are dark for the
  first two years regardless of collection completeness — an accepted,
  documented gap (`AGENTS.md` PIT-fundamentals invariants), not something
  this design works around.
- Prices: FinanceDataReader + KRX Open API (`korea_prices.py:acquire`),
  as-traded forward total-return, split-adjusted.

KR factor results are evaluated only against KR outcomes. A KR hypothesis
is never scored against US realised returns.

## Existing KR evidence (read-only summary, not re-scored here)

| Signal | KR standalone 126D pooled IC | 95% CI | Coverage note |
|---|---:|---|---|
| Momentum | region-sign-unstable component | — | none material |
| Value | region-sign-unstable component | — | **KR value missing-rate 55.45%** — over half the sample |
| Quality | region-sign-unstable component | — | **KR quality missing-rate 53.99%** |
| Lowvol | +0.0511 alone (95% CI [+0.0047, +0.0974], clears zero standalone) but does not survive pooling against US (-0.0225) | — | none material — this is a real KR-only reading, carried forward as a *prior*, never as a conclusion (per that study's own Section 8 rule) |
| Fundamental Acceleration | +0.0361 | [-0.0502, +0.1224] | **13.76% coverage — a sixth of US's.** Per `docs/regional-alpha-research-separation-v1.md` Section 15, the positive point estimate here cannot be separated from noise created by the thin, coverage-limited sample; it is neither confirmed nor discarded |

Two consequences for candidate selection below: (1) Korean PIT
*fundamental*-based candidates inherit the same DART-coverage ceiling that
already constrains Value/Quality/Fundamental-Acceleration, so a
fundamentals-heavy candidate should be weighed against that known
limitation before being proposed; (2) KR Lowvol's standalone-significant
reading and Fundamental Acceleration's inconclusive-but-positive reading
are both carried forward as priors worth keeping in view for
`kr-alpha-discovery-v1`'s own design, without being treated as settled.

## Candidate gates (Section 18)

Same five gates as the US design doc, with PIT availability given
explicit priority over academic appeal (Section 18's own instruction:
"실제로 PIT historical data를 확보할 수 없는 것은 명확히 제외한다" — what
cannot be cleanly measured with real historical PIT data is excluded
outright, not scored down).

## Candidates considered

| Candidate | Gate 1 (new info) | Gate 2 (PIT data) | Gate 3 (coverage) | Gate 4 (cost) | Gate 5 (sealable) | Verdict |
|---|---|---|---|---|---|---|
| **Foreign / institutional investor net-flow** (외국인·기관 수급) | Pass — famously influential in KOSPI, genuinely distinct from any existing sleeve | **Fails** — no per-stock investor-type trading-value field exists anywhere in this pipeline today (confirmed by exhaustive grep); the KRX Open API endpoints currently integrated (`korea_prices.py`) are price/session endpoints only, and per `AGENTS.md`'s vendor-refusal invariants, KRX access is granted *per service* — a new endpoint would need its own separate subscription approval, unconfirmed | Unknown pending Gate 2 | **Unconfirmed** — depends on an unapproved endpoint | Pass in principle | **Excluded — `DATA_LINEAGE_UNRESOLVED`, not a candidate this round** |
| **Short interest / 공매도 관련 정보** | Pass — distinct information | **Fails** — no field, no integrated source; Korean short-sale disclosure data is not currently collected anywhere in this pipeline | Unknown | Unconfirmed | Pass in principle | **Excluded — `DATA_LINEAGE_UNRESOLVED`** |
| **Earnings revision (analyst consensus)** | Pass — expectations-revision information | **Fails, confirmed (not merely unconfirmed)** — `challenger-2-signal-source-feasibility-v1` already established that the official Korean analyst-consensus provider's terms of service explicitly forbid building a user's own database, categorically incompatible with PIT ledger storage | n/a | **Fails** — categorical, not a cost question | n/a | **Excluded — confirmed fail, carried over from prior study, not re-probed** |
| **National Pension Service allocation as a flow proxy** | Fails — aggregate fund-level asset-class allocation (국내주식/국내채권/...), not a per-name holding; cannot feed a stock-selection score by construction | n/a | n/a | n/a | n/a | **Excluded — wrong granularity, not a data-access problem** |
| **거래대금 / liquidity** (trading value as a factor) | **Marginal** — plausible size/liquidity effect, but conceptually close to existing Lowvol/size-adjacent information; orthogonality is an open question, not assumed | Pass — already-collected price/volume data | Pass | Pass | Pass | **Not selected this round** — Gate 1 orthogonality unresolved, kept as a second-ranked candidate |
| **USD/KRW sensitivity (FX beta)** — each name's rolling sensitivity of return to USD/KRW change | **Pass, cleanly** — a stock's currency exposure (export-oriented vs domestic-demand-oriented) is conceptually distinct from momentum/value/quality/lowvol, and is a structurally KR-specific claim (a small, open, export-heavy economy) that has no US analog in this repository's factor set | **Pass** — both inputs (`USD_KRW` via FRED `DEXKOUS`, already fetched; stock/benchmark returns, already collected) exist today with confirmed PIT semantics (daily observation, no restatement) | **Pass** — computable for the full KR universe, no vendor gap | **Pass** — zero incremental cost, no new vendor | **Pass** — computable identically in a live/prospective context from data already in the pipeline | **Selected — see design below** |

**USD/KRW sensitivity (FX beta) is the pre-registered next KR hypothesis.**
It is the only candidate that clears every gate without any new vendor
dependency, is genuinely Korea-specific in its economic rationale (not a
copy of a US-motivated candidate), and does not lean on the DART
fundamentals coverage ceiling that already constrains Value/Quality/
Fundamental-Acceleration.

## FX beta: design (pre-registered, not executed)

**Hypothesis.** Korean equities are not uniformly exposed to KRW moves.
Export-heavy names (semiconductors, autos, shipbuilding) plausibly benefit
from KRW weakness (foreign-currency revenue, domestic-currency costs);
domestic-demand names plausibly do not. A rolling, name-level measurement
of this sensitivity — rather than a sector label — is a continuous,
PIT-clean signal already implied by data this pipeline collects but never
turns into a factor.

**Exact construction.**
1. Over a trailing `N`-week lookback (`N` fixed before any result —
   proposed `N = 26`, roughly two quarters, short enough that a name's FX
   exposure profile has not structurally changed, long enough for a stable
   regression), regress each name's weekly LOCAL-CURRENCY return (not its
   KRW-benchmark-relative return — the FX beta claim is about the stock's
   own price response to FX, not fund performance) against the
   contemporaneous weekly USD/KRW percentage change.
2. `fxBeta` = the regression slope. Sign convention: positive `fxBeta`
   means the stock tends to rise when KRW weakens (USD/KRW rises) —
   consistent with an exporter profile.
3. The RAW hypothesis is about the absolute magnitude of exposure
   (`|fxBeta|`, "how currency-sensitive is this name"), not its sign — a
   large importer's negative exposure is informationally as significant as
   a large exporter's positive one is. Whether the DIRECTIONAL sign (not
   just magnitude) also carries information is a secondary, descriptive
   question the discovery study can examine without it being the primary
   claim.
4. Sector-neutral z-score of `|fxBeta|` within `(date, KR)` using
   `longterm.sector_neutral_z` at its existing `winsor=2.5` default — no
   new normalization invented.

**PIT semantics.** `USD_KRW` is a daily FRED series with no revision
history concern (an FX fixing is not restated); both legs of the weekly
regression use only observations with a timestamp `<= asOfDate`. No
fundamental-filing timing question arises, so this candidate is
unaffected by DART's 2015 PIT-coverage floor — a genuine advantage over a
fundamentals-heavy KR candidate.

**Primary horizon and statistic.** 126 trading days, KR-only pooled Rank
IC via the same `four_factor_signal_attribution_audit.py` machinery every
prior study in this line reuses.

**Orthogonality check (Stage B, before any return is read).** Pooled
Spearman(`|fxBeta|`-percentile, X-percentile) for X in
{momentum, value, quality, lowvol}. Same `|rho| >= 0.70` pre-registered
failure threshold as the US design doc and
`fundamental-acceleration-discovery-v1`.

**Coverage floor.** `>= 0.60` data-sufficient ratio — expected to be high
and not DART-constrained, since both inputs are price/FX series with
long, complete histories; this expectation is stated here for the record
and will be measured, not assumed, when the study runs.

**Failure criterion (fixed before any result).** Abandoned, not re-tuned,
if orthogonality fails, coverage falls below 0.60, or the prospective
validation's paired interval does not separate from zero with an
unfavourable point estimate — identical discipline to the US design doc
and every prior study in this line.

## What happens after this design is approved

Nothing, in this PR. Implementation
(`pipeline/kr_fx_sensitivity_discovery.py`, its own tests, a runner,
execution against sealed `replay-v16`, and eventually `KR_SIGNAL_SEAL`
prospective sealing) is a separate, future PR — per
`KR_ALPHA_DISCOVERY_BUDGET = 1`
(`docs/regional-alpha-research-separation-v1.md` Section 16), this is the
ONE KR-only historical discovery study this research line will run before
either finding meaningful evidence (proceed to prospective validation) or
declaring `HISTORICAL_ALPHA_DISCOVERY_PHASE = CLOSED` for KR.
