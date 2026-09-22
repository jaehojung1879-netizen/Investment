# Fundamental-acceleration discovery v1

> Read-only research DISCOVERY study on sealed `replay-v16` inputs. No
> factor weight is changed, no portfolio is selected or valued anywhere in
> this study, no threshold is tuned after seeing a result.
> `promotionEligible: false`, production unchanged.

This implements the study `challenger-2-signal-source-feasibility-v1`
selected and `challenger-2-fundamental-acceleration-v1-design.md`
pre-registered: does the RATE OF CHANGE in a company's own profitability,
margins and growth — measured filing-over-filing, strictly point-in-time —
carry information about future benchmark-relative return that the existing
Quality sleeve's LEVEL measurement does not?

## What this study is

1. **Computability**: is the two-consecutive-filing PIT construction
   actually computable on real data, and at what coverage?
2. **Distinctness**: is the resulting composite genuinely different
   information from the existing Quality percentile, or a relabelling of
   it?
3. **Minimal discovery evidence**: is there standalone and incremental Rank
   IC evidence, at the pre-registered 126-trading-day horizon, of a
   forward-return relationship?
4. **Stability**: is that evidence consistent across region and a fixed
   chronological half-split?

## What this study is not

- Not a portfolio backtest. `kelly_portfolio.select_portfolio_by_scores`
  and `replay_valuation` are never called.
- Not a promotion, not a factor-weight change, not a combination search.
- Not a threshold, window, or field tune. The composite formula (sector-
  neutral z of each of `roe`/`operatingMargin`/`profitMargin`/
  `earningsGrowth`'s filing-over-filing delta, minimum 3 of 4 present,
  `debtToEquity` diagnostic-only), the primary horizon (126D), and the two
  failure thresholds (coverage < 0.60, |orthogonality rho| >= 0.70) were
  all fixed in `docs/challenger-2-fundamental-acceleration-v1-design.md`
  before this module was written.
- Not confirmatory validation. Per the design's own split, the confirmatory
  claim is reserved for the prospective sealed window
  (`pipeline/fundamental_acceleration_seal.py`); this discovery study on
  `replay-v16` is explicitly the bridge, per the design's own language,
  never the confirmatory evidence.

## PIT construction, exactly as pre-registered

`pipeline/fundamental_acceleration.py` is the single shared implementation,
used identically by this discovery study and by prospective sealing:

- The **current filing** is the one with the latest REPORT PERIOD among all
  filings visible (`availableFrom <= asOf`) — not simply the latest
  `availableFrom` — because a severely delayed filing could in principle
  arrive out of period order.
- The **previous filing** must be the immediately preceding report period
  in the region's own fixed cadence (US: Q1→Q2→Q3→FY; KR: DART's
  11013→11012→11014→11011), with strict one-step adjacency (same fiscal
  year, or the prior year's final period rolling into the next year's
  first). A skipped period (e.g. a missing half-year filing) is
  `NOT_CONSECUTIVE` and contributes no reading — deliberately conservative,
  never adaptive per-company cadence detection.
- **Amendments/restatements** are resolved by grouping visible filings by
  report period and keeping the max-`availableFrom` record per group before
  chronological ordering. Measured directly against the real sealed ledger:
  zero duplicate `(ticker, reportPeriod)` filings exist in either region (0
  of 4,302 KR keys, 0 of 33,832 US keys), so this logic is exercised only
  by synthetic test fixtures and changes no real number in this study.
- Both legs' PIT visibility is asserted explicitly in code (not merely
  assumed), exactly as `contraction_holds` is asserted for the confidence
  weight in `alpha_reliability.py`.

## Composite construction

For each of `roe`, `operatingMargin`, `profitMargin`, `earningsGrowth`:
`accel_f = f(current) - f(previous)`, sector-neutral z-scored within
`(date, region)` via `longterm.sector_neutral_z` at its existing
`winsor=2.5` default (no new normalization). The composite is the mean of
whichever z-scores are present, minimum 3 of 4 required, else
`DATA_INSUFFICIENT`. `debtToEquity` acceleration is computed and reported
as its own diagnostic, sector-exempt exactly as production's own leverage
penalty is (`SECT.LEVERAGE_EXEMPT_SECTORS`), and is never in the composite.

## Results (measured on sealed `replay-v16`, byte-identical across two full runs)

Input snapshot: `f0781292f508a123c234ded6d28aa8e84a0dc3cc29500e14989dc0b68f53b4d2`,
through 2026-09-14. 399,547 signals, 396,358 outcomes, 38,134 PIT filings
across 904 tickers (125 KR, 779 US).

### Table A — Coverage

| Region | Total | Data-sufficient | Ratio |
|---|---:|---:|---:|
| KR | 98,901 | 13,611 | 13.76% |
| US | 300,646 | 245,894 | 81.79% |
| **Overall** | **399,547** | **259,505** | **64.95%** |

Overall coverage **PASSES** the pre-registered 0.60 minimum, but the
regional split is stark: KR's ratio is barely a fifth of US's. KR is 24.7%
of the sample by row count, so the overall ratio is US-dominated — the
pass is real but region-imbalanced, and this imbalance is reported here
rather than averaged away. By time half: first half 58.13%, second half
70.65% — coverage rises over the sample as more consecutive filing pairs
accumulate, consistent with DART serving Korean fundamentals only from
2015 and the replay starting 2013.

By status: OK 336,309, `NO_FILING_VISIBLE` 51,893, `NOT_CONSECUTIVE` 9,725,
`NO_PREVIOUS_FILING` 1,620. Among OK consecutive-filing pairs, per-field
presence: roe 79.46%, profitMargin 79.12%, operatingMargin 75.96%,
earningsGrowth 74.99%, debtToEquity 93.61%.

### Table B — Orthogonality (Stage B)

| Factor | Mean Spearman vs accelerationPercentile |
|---|---:|
| quality | **0.1180** |
| momentum | 0.1772 |
| value | -0.0235 |
| lowvol | -0.0124 |

|rho| vs Quality = 0.1180, well under the 0.70 redundancy threshold —
**PASSES**. The acceleration composite is not a relabelling of the
existing Quality level factor.

### Table C — Discovery evidence (primary, 126D)

| Statistic | Mean | 95% CI | Raw p | Holm p |
|---|---:|---:|---:|---:|
| Standalone Rank IC | -0.0026 | [-0.0257, 0.0204] | 0.8233 | 1.0000 |
| Incremental Rank IC (beyond Quality alone) | -0.0009 | [-0.0205, 0.0187] | 0.9248 | 1.0000 |

Both point estimates are near zero and both CIs contain zero. By region,
standalone Rank IC is KR +0.0361 (95% CI [-0.0502, 0.1224], n=460
dates, 18 effective independent) vs US -0.0056 (95% CI [-0.0295,
0.0183], n=680 dates, 27 effective independent) — opposite signs.

### Table D — Stability

- **Region**: KR POSITIVE, US NEGATIVE — `REGION_SIGN_UNSTABLE`.
- **Time** (fixed chronological half-split): first half mean -0.0222 (95%
  CI [-0.0473, 0.0030]), second half mean +0.0157 (95% CI [-0.0192,
  0.0507]) — `HALF_SIGN_UNSTABLE`.
- **Secondary horizons** (descriptive only, never promoted to primary):
  21D +0.0049, 63D -0.0007, 252D -0.0091.

### Table E — Quintiles (pooled, 126D)

| Q1 | Q2 | Q3 | Q4 | Q5 | Monotonicity | Q5-Q1 |
|---:|---:|---:|---:|---:|---:|---:|
| 0.0023 | -0.0106 | -0.0165 | -0.0131 | 0.0068 | 0.500 | 0.0045 |

Not monotone (0.500 of 4 possible steps agree in direction); the Q5-Q1
spread is near zero.

### Quality-level-conditional (descriptive only, never a score/rule)

Within each Quality-percentile quintile, a median-split on acceleration:

| Quality quintile | High-accel mean excess | Low-accel mean excess | Diff | n |
|---|---:|---:|---:|---:|
| Q1 | 0.0144 | 0.0093 | +0.0051 | 1,348 |
| Q2 | -0.0076 | -0.0100 | +0.0025 | 1,348 |
| Q3 | -0.0219 | -0.0177 | -0.0042 | 1,348 |
| Q4 | -0.0117 | -0.0160 | +0.0044 | 1,348 |
| Q5 | 0.0058 | -0.0077 | +0.0135 | 1,348 |

No consistent direction across Quality levels — descriptive only, entered
no score, ranking or rule.

### Debt-to-equity acceleration (diagnostic only, never scored)

297,790 non-exempt observations, 17,617 exempt-sector observations masked
(Financials, Holding, Real Estate, Utilities). Mean delta among non-exempt
names: +0.0284. Never included in the composite.

## Classification

**CASE D — `D_NO_DISCOVERY_EVIDENCE`.**

Coverage passes (Case C ruled out). Orthogonality passes — the composite
is genuinely distinct from Quality (Case B ruled out). But the standalone
and incremental pooled Rank IC point estimates are not both positive, the
region signs disagree, and the time-half signs disagree. This does not
match Case A (favourable and separated) or Case E (favourable point
estimate, CI contains zero) — the point estimate itself is unfavourable
(standalone -0.0026, incremental -0.0009), so per this study's own
pre-registered routing (a negative point estimate is never stretched into
"directionally promising"), it is Case D.

## What this study recommends next

Per the design's own case-routing, Case D calls for evaluating a new
information source as a separate CHALLENGER rather than re-tuning this
composite — no field was dropped, no weight was added, no window was
searched after seeing this result, and none will be in response to it.
The regional and time-half instability (KR positive vs US negative;
first-half negative vs second-half positive) is itself worth naming
plainly: on this sample, whatever this composite is capturing does not
generalize across region or across time, which is a stronger and more
specific finding than "no effect" alone.

## Prospective sealing (primary validation split)

Per the design's own primary/bridge split, `pipeline/fundamental_
acceleration_seal.py` provides the append-only, digest-verified prospective
recording mechanism — `scripts/seal_fundamental_acceleration_signal.py` for
one day's sealing run, `scripts/extract_acceleration_candidates.py` to pull
the live candidate universe from `data/site-data.json`'s own
`longTerm.regions.*.researchTable`, and the `Seal fundamental acceleration
signal` GitHub Actions workflow (`workflow_dispatch` only in this PR — see
that workflow file for why it is not yet on a schedule). The first live
invocation, which fixes `PROSPECTIVE_START_DATE`, happens after this PR
merges; none of `DART_API_KEY`/`FINNHUB_API_KEY` is configured in this
development sandbox. Given this study's own CASE D reading, a genuinely
useful next step for the prospective window is an open question left to
the PR reviewer, not decided here.

## Verification

- 76 new unit tests across `tests/test_fundamental_acceleration.py` (24),
  `tests/test_fundamental_acceleration_discovery.py` (21),
  `tests/test_fundamental_acceleration_seal.py` (9),
  `tests/test_extract_acceleration_candidates.py` (3) — plus the existing
  suite, 1,707 total, all passing.
- `ruff check .`, `python -m compileall pipeline scripts` clean.
- The historical discovery runner was run twice end to end against the
  real sealed `replay-v16` ledger; the two JSON and Markdown reports are
  byte-identical, and the sealed ledger's own content digest is unchanged
  before and after each run (`sealedInvariant.unchanged: true`, enforced by
  the runner itself, which raises `SEALED_LEDGER_CHANGED` otherwise).
