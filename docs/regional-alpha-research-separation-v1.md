# Regional alpha research separation v1

> **Architecture / research redesign. Production behavior is unchanged.**
> No factor weight, CHAMPION, selector, region cap, live/paper ranking,
> Kelly parameter, macro multiplier, or regional-allocation rule is changed
> in this PR. `promotionEligible: false`. No backtest is run or scored here.

## 0. What changes and what does not

This study replaces one research question with two. Through eleven prior
studies on this ledger, the working hypothesis was "which factor works in
both KR and US" — and every factor tested (momentum, value, quality,
lowvol, fundamental acceleration) showed KR/US sign disagreement at the
126-trading-day horizon (Table 1). This PR does not fix that by tuning a
weight. It changes the question: **US alpha research and KR alpha research
become two independent research problems**, each with its own factor
definitions, its own macro regime, its own next hypothesis, and its own
one-shot historical discovery budget. Nothing about *how* a stock is
ranked, weighted, or selected changes today — this PR only changes how
*future* research is structured, and pre-registers exactly two follow-up
studies (`us-alpha-discovery-v1`, `kr-alpha-discovery-v1`).

## 1. Background — the evidence that motivates this split

Every factor this repository has measured at the primary 126-trading-day
horizon disagrees in sign between KR and US (`four-factor-signal
-attribution-audit-v1`, `fundamental-acceleration-discovery-v1`):

| Signal | KR sign | US sign | Source |
|---|---|---|---|
| Momentum | region-sign-unstable | region-sign-unstable | `four-factor-signal-attribution-audit-v1` (`classify_sleeve` = `D_UNSTABLE_REGIME_DEPENDENT` on all four sleeves) |
| Value | region-sign-unstable | region-sign-unstable | same |
| Quality | region-sign-unstable | region-sign-unstable | same |
| Lowvol | KR standalone clears zero alone (+0.0511, 95% CI [+0.0047,+0.0974]) but does not survive pooling against US (-0.0225) | negative pooled component | same; Section 8 of that study forbids substituting the regional reading for the pooled one |
| Fundamental Acceleration | +0.0361 (95% CI [-0.0502, +0.1224], 460 dates) | -0.0056 (95% CI [-0.0295, +0.0183], 680 dates) | `fundamental-acceleration-discovery-v1` |

No pooled reading is significant after Holm correction in either study. The
repeated pattern — not one anomalous factor, but every factor tested —
is the evidence this study acts on: a single common-scale ranking applied
identically to both regions is not a proven construction, and the
regionally-disaggregated evidence is more informative than the pooled
average that discards it.

## 2. Core principle

```
                    CAPITAL ALLOCATION
                           |
             +-------------+-------------+
             |                           |
        US RESEARCH                 KR RESEARCH
             |                           |
      US alpha engine              KR alpha engine
      US macro regime              KR macro regime
      US benchmark                 KR benchmark
      US data sources              KR data sources
      US validation                KR validation
             |                           |
             +-------------+-------------+
                           |
                  portfolio allocation
```

Regional allocation is a separate layer above stock selection. US and KR
stock-ranking scores are never mixed on one common raw scale.

## 3. Required reading (completed)

`AGENTS.md`, `README.md`, `config.json`, `docs/investment-philosophy.md`,
`docs/challenger-registry.md`; `four-factor-signal-attribution-audit-v1`,
`fundamental-acceleration-discovery-v1`, `regional-rotation-validation-v1`,
`region-quota-removal-v1`, `signal-persistence-v1`,
`selection-value-decomposition-v1`; `pipeline/longterm.py`, `regime.py`,
`macro.py`, `datafeed.py`, `regional_rotation.py`, `regional_validation.py`,
`historical_replay.py`, `historical_outcomes.py`, `portfolio_validation.py`,
`pit_data.py`, `replay_rates.py`, `benchmark_source.py`,
`korea_prices.py`, `entry.py`, `kelly_portfolio.py`, `dart_derive.py`,
`finnhub_derive.py`, `config.py`.

## 4. Component audit — what is already regionalized, what is not

Measured against the actual code on `main`, not assumed.

| # | Component | US-specific | KR-specific | Shared | Should be separated? | Reason |
|---|---|---|---|---|---|---|
| 1 | Factor **definitions** (formula) | — | — | `longterm.score_cross_section` — one formula, `longterm.py:265`, called once per region inside `build_region()` from a `for region, tickers in universe.items()` loop (`longterm.py:354-367,653-656`); the module's own docstring states "KR and US are ranked in SEPARATELY z-scored universes and never compared directly" (`longterm.py:12-13`) | **YES** (research axis) | Momentum/Value/Quality/Lowvol use the identical formula in both regions today, even though cross-sections are never pooled. This is this study's primary research target — not changed here, pre-registered to `us-alpha-discovery-v1`/`kr-alpha-discovery-v1`. |
| 2 | Factor **weights** | — | — | `FACTOR_WEIGHTS = {momentum:.30, value:.25, quality:.25, lowvol:.20}`, `longterm.py:50` | **YES** (research axis) | Same weights applied to both regions; never tuned per region. Not changed in this PR (section 13 forbids it here). |
| 3 | Cross-sectional **normalization** (sector-neutral z) | — | — | Mechanism shared, but `score_cross_section` is already called once per region's own cross-section (`rows: dict[str, dict]` = one region, `longterm.py:265-266`) | Already correctly separated | No raw factor value ever crosses a region boundary at normalization time. |
| 4 | **Universe** | `config.json universe.US` (69 names + SPY family) | `config.json universe.KR` (43 names) | — | Already separated | N/A |
| 5 | **Benchmark** | SPY | 069500.KS (KODEX 200, total-return ETF basis) | Resolution *code* shared (`benchmark_source.py`), series never merged | Already separated | `benchmark_source.py:443-497` (`resolve`) resolves and snapshots each region's ticker independently; an accepted candidate is "used alone, never merged with the snapshot" (module docstring). |
| 6 | **Transaction costs** | `config.json transactionCosts.US` (sellTaxBps 3) | `transactionCosts.KR` (sellTaxBps 20, 1.6-2.5x US) | — | Already separated, confirmed at the code level | `estimate_transaction_cost()` reads `regional = (cfg.get("transactionCosts") or {}).get(region) or {}` (`kelly_portfolio.py:387`) — and even its Python-level fallback default is region-conditional: `sell_tax = float(regional.get("sellTaxBps", 20.0 if region == "KR" else 3.0))` (`kelly_portfolio.py:390`). `measured_turnover_by_region()` (`kelly_portfolio.py:301-345`) further replaces the assumed rate with each region's own measured churn. |
| 7 | Trading / evaluation **calendar** | — | — | `replay_calendar.sessions(..., region=...)` supports per-exchange (`"KR"`->XKRX, `"US"`->XNYS) and combined modes, but `schedule()` — which drives the rebalance/anchor grid both the replay and `regional_rotation.py` use — defaults to `region="COMMON"`, which **intersects** the two exchange calendars (`replay_calendar.py:20-34,50-56`; `metadata()` records `"sessionRule": "XKRX_INTERSECTION_XNYS"`, confirming this is deliberate) | **Worth naming explicitly, not silently kept** | A US-only holiday (Thanksgiving, Juneteenth) removes that date from the KR schedule too, and a Korean holiday (Lunar New Year) removes it from the US schedule — today's rebalance/anchor dates are not independently chosen per region even for research that claims to evaluate one region alone. This does not need to change for `us-alpha-discovery-v1`/`kr-alpha-discovery-v1` (both can still sample their own region's per-exchange calendar directly via `sessions(region=...)`), but any research reusing `schedule()`'s existing anchor grid inherits the intersection. |
| 8 | **Fundamental data source** | Finnhub (`finnhub_fundamentals.py` / `finnhub_derive.py`) | DART (`dart_fundamentals.py` / `dart_derive.py`) | Storage/access layer (`pit_data.FundamentalStore`) is ticker-keyed with no `region` field, loaded from one merged `PIT_FUNDAMENTALS_V1` JSONL | Ingestion already separated; storage layer is shared infrastructure, not a leak point | `pit_data.FundamentalStore.merge`'s own docstring: "the filings come from different vendors under different account names and they fail separately." Downstream consumers (`longterm.build_region()`) already slice by region before querying the store, so the shared store never blends a KR reading into a US one. |
| 9 | **Price data source** — replay/backtest path | Yahoo (`datafeed.py:fetch_prices`) | FinanceDataReader + KRX Open API (`korea_prices.py:acquire`), used by `benchmark_source.py` and `scripts/run_replay.py` | — | Already separated for backtest evaluation | `korea_prices.py`'s own header documents why: Yahoo serves only 3,782 of FinanceDataReader's 3,855 KOSPI 200 sessions, with 5 gaps absent for the whole KR cross-section. |
| 9a | **Price data source — LIVE production path** | — | — | `pipeline/build.py`'s live daily generation calls `fetch_prices()` (Yahoo-only, `datafeed.py`) for **both regions' tickers together** (`build.py:724-725`), never routing KR through `korea_prices.acquire()` | **A genuine, previously-undocumented asymmetry — flagged, not fixed here** | The rigor `korea_prices.py` exists specifically to add for KR (its own header calls Yahoo's KR gaps a known defect) is applied in backtest but **not** in the live signals a user actually sees today. This is a real production data-quality gap for KR, independent of the alpha-research-separation question this PR addresses; recorded here because it surfaced during the audit, not investigated or fixed (Section 26: no production behavior changes in this PR). |
| 10 | Macro regime **classification** | 100% of `regime.py`'s `INDICATORS` (21 series: FRED macro + VIX) | **none** — zero KR series enter the classification | The regime *engine* (code) is region-agnostic and reusable, but its entire input set today is US/global | **YES — the single largest gap this study found** | `regime.py:38-68`; every one of the 21 indicators is a FRED or CBOE series. KR's `USD_KRW`/`Korea_10Y`/`Korea_3M` are fetched (via FRED — see row 11) but are DISPLAY-ONLY in `macro.py:_kr_indicators` (`macro.py:76-85`) and never appear in `regime.py`'s `INDICATORS` dict or `build()`. |
| 11 | KR **domestic** macro data collection (BOK/ECOS) | — | `config.json`'s `ecos.KR` block (BaseRate, KTB_3Y, CorpBond_3Y, CPI, CoreCPI, IndustrialProduction, LeadingIndex, Exports, M2) is *defined* | — | **`DATA_LINEAGE_UNRESOLVED`** | Exhaustive grep across `pipeline/*.py` found zero ECOS HTTP fetch implementation. `cfg.ecos_regions`/`cfg.has_ecos` are loaded (`config.py:52,69,120,146`) but the only consumer anywhere is a boolean diagnostic flag, `build.py:1145: "ecosEnabled": cfg.has_ecos`. `config.json`'s own trailing note calls the series IDs "placeholders to be verified against BOK ECOS before a live KR macro build" — this has never happened. |
| 12 | Entry-state **ranking** (overheat percentile) | — | — | `entry.overheat_score()`/`classify()` take no region argument, but `build._attach_entry_states()` computes "universe-relative overheat percentiles per region" (`build.py:586-600`), ranking each name only within its own region's cross-section before `classify()` sees it | Already correctly separated in ranking | Overheat is relative to each region's own cross-section, not an absolute level. |
| 13 | Entry-state **thresholds** (fixed constants: overheat >= 85p, RSI >= 78, >=25% above 200dma, vol-spike >= 1.6x, 30% sector-cap default) | — | — | Identical hard-coded levels for every name regardless of region (`entry.py:112,125,128-132`) | **YES** (research axis) | No evidence these levels were ever validated separately against KR's different liquidity/volatility regime. Not changed in this PR. |
| 14 | Selection **score formula** | — | — | `score = edge / max(risk_unit, 0.05) * evidence * state_multiplier` (`kelly_portfolio.py:945`), applied to and sorted across **both regions' candidates together** before region caps apply (`_select_scored`, `kelly_portfolio.py:969`) | **Partially — the region cap is currently the only thing preventing this shared scale from freely mixing regions** | `region-quota-removal-v1` measured what happens with the cap lifted: the book goes to ~KR 639/US 85 of ~720 held name-dates, because calibrated alpha *level* differs ~16x by region (KR mean +0.645pp vs US +0.041pp, `region-quota-removal-v1`). The shared score scale is not economically comparable across regions today; the region cap (`maxNamesPerRegion=3`) absorbs that gap rather than a validated cross-region scale doing so. |
| 15 | Selection **gate threshold** (`minAlphaPercentile=66`) | — | — | One shared value, `config.json kellyPortfolio.selection.minAlphaPercentile` | **YES** (research axis) | Same 66th-percentile bar applied to both regions' own percentile distributions, regardless of shape differences. Not changed in this PR. |
| 16 | **Calibration** mechanism (`ExpandingBucketCalibration`, bucket edges `[0,60,80,90,95,100]`) | — | — | Bucket edges are one shared numeric scheme, but the calibration is grouped, stored and queried by `(region, bucket)` from the start — `__init__` groups by `["outcomeEndDate","date","region","bucket"]` (`portfolio_validation.py:425`), stores in `self.values[(region, bucket)]` (`portfolio_validation.py:432,445`), and `expected(region, alpha_percentile)` (`portfolio_validation.py:449-451`) can structurally never read another region's observations | Already correctly separated — no work needed | `portfolio_validation.alpha_diagnostics()` states the policy explicitly: `"poolingPolicy": "DATE_X_REGION_ONLY; KR_US_NEVER_POOLED"` (`portfolio_validation.py:401`). The measured ~16x KR/US level gap (`region-quota-removal-v1`: KR mean 0.645pp vs US 0.041pp) is a genuine OUTPUT of two independently-fit calibrations, not an artefact of a shared one. |
| 17 | `regional_rotation.py` / `regional_validation.py` (capital allocation) | — | — | A layer strictly *above* two independently-computed regional portfolios (softmax on trailing regional benchmark excess, 252-calendar-day lookback) | Already correctly separated — this **is** the capital-allocation layer Section 23 describes | Module docstring: "a capital-allocation question sitting a level above stock selection, not a third way of picking stocks" (`regional_rotation.py:1-9`); `apply_schedule()` (`regional_rotation.py:189-285`) only ever blends each region's *already-computed* return path, never re-ranks or re-selects a stock. `docs/regional-rotation-validation-v1.md`; CHALLENGER status, not wired to production. |
| 18 | Kelly **covariance** estimation | — | — | `estimate_active_covariance(..., region=region, benchmark=benchmark)` (`kelly_portfolio.py:691-717`) is called inside a `for region in sorted({...})` loop over the portfolio-assembly function, producing `covariance_matrices[region]` and running `optimize_fractional_kelly` separately per region against `regionCaps[region]` (`kelly_portfolio.py:1423-1471`, esp. 1431, 1440, 1464-1465) | Already separated for the primary path — confirmed at the call-site loop, not just the estimator | A secondary `ABSOLUTE_LOCAL_CURRENCY` fallback path (`kelly_portfolio.py:683-688`) pools **all** tickers' raw local-currency returns into one panel regardless of region if the regional-active path is unavailable. Flagged as a caveat, not fixed in this PR (production behavior unchanged). |

**Summary**: universe, benchmark, transaction costs (code-level, not just
config), fundamental data ingestion, backtest-path price data, Kelly's
covariance estimation, and the alpha calibration are already properly
regionalized — several more rigorously than the request assumed (e.g. the
calibration's `KR_US_NEVER_POOLED` policy string). Factor formulas, factor
weights, entry-state thresholds, the selection gate/score formula, and —
most materially — the macro regime are still one shared US/global
construction applied identically to both regions. Korean domestic macro
data (rates, inflation, growth) is not merely under-weighted; it is **not
collected at all** (ECOS is configured, never fetched). Two additional
couplings surfaced during the audit that are neither alpha-formula nor
macro-regime issues, but affect how independent the two research problems
can be even after those are split: the rebalance/anchor calendar both
regions currently share is an *intersection* of XKRX and XNYS sessions
(row 7), and the live production price fetch — unlike the backtest path —
does not route KR through the more rigorous FinanceDataReader/KRX path
(row 9a).

## 5. Data lineage gate

No column mapping is guessed. A field with no confirmed source is
recorded as absent, never inferred from a similar name.

### 5a. US alpha inputs

| Input | Source | Raw / canonical field | PIT timestamp | Used by |
|---|---|---|---|---|
| ROE | Finnhub (`finnhub_fundamentals.py`) | `roe` (`finnhub_derive.py:290`) | `availableFrom` = SEC accepted-filing date, carried through untouched (`finnhub_derive.py:325,333`) | Quality |
| Operating margin | Finnhub | `operatingMargin` (`finnhub_derive.py:291`) | same | Quality |
| Profit margin, earnings growth, debt/equity | Finnhub | `profitMargin`, `earningsGrowth`, `debtToEquity` | same | Quality |
| Trailing/forward earnings yield, book yield, FCF yield | Finnhub (per-share numerators) + `datafeed.py` close | derived via `pit_data.derive_price_relative` | filing `availableFrom` for the numerator; replay-date close for the divisor | Value |
| Price / momentum / lowvol inputs | Yahoo (`datafeed.py:fetch_prices`) | as-traded forward total-return close | daily, no lag (price is observed same-day) | Momentum, Lowvol |
| Momentum/value/quality raw subfactor inputs (`mom121`, `mom6`, four value ratios, five quality ratios) | computed internally by `historical_replay.py`, never persisted | **absent from the sealed signal ledger** — `four-factor-signal-attribution-audit-v1` Stage 0 | n/a | not independently auditable today (`docs/four-factor-pit-instrumentation-proposal-v1.md` proposes closing this, not implemented) |
| Macro (growth/inflation/liquidity/financial-conditions/risk-appetite/earnings-credit) | FRED (`datafeed.py:fetch_macro`) | `CFNAI`, `Payrolls`, `Unemployment`, `Initial_Claims`, `Headline_CPI`, `Core_CPI`, `Core_PCE`, `Headline_PPI`, `Core_PPI`, `Breakeven_10Y`, `WTI`, `Fed_Assets`, `RRP`, `TGA`, `M2`, `NFCI`, `ANFCI`, `HY_Spread`, `IG_Spread`, `Real_10Y`, `Broad_Dollar`, `VIX` (CBOE) | conservative fixed publication lag per series (`regime.py:38-68`, 0-30 business days) | `regime.py` regime classification |
| Benchmark | Yahoo (`_yahoo_close`), snapshot fallback | SPY as-traded forward total-return close | daily | US matched-benchmark excess return |

### 5b. KR alpha inputs

| Input | Source | Raw / canonical field | PIT timestamp | Used by |
|---|---|---|---|---|
| ROE, operating margin, profit margin, earnings growth, debt/equity | DART (`dart_fundamentals.py`) | `roe`, `operatingMargin`, `profitMargin`, `earningsGrowth`, `debtToEquity` (`dart_derive.py:227-228`) | `availableFrom` = DART 접수일자 (receipt date), carried through untouched (`dart_derive.py:262,273`) | Quality |
| Trailing/forward earnings yield, book yield, FCF yield | DART per-share numerators (2nd collection pass, net of treasury stock) + `korea_prices.py` close | derived via `pit_data.derive_price_relative` | filing `availableFrom`; replay-date close | Value |
| Price / momentum / lowvol inputs | FinanceDataReader + KRX Open API (`korea_prices.py:acquire`) | split-adjusted, as-traded forward total-return | daily | Momentum, Lowvol |
| USD/KRW | FRED (`DEXKOUS`, `config.json fred.KR`) | `USD_KRW` | daily, fetched via same `fetch_macro` path as US series | **display only** (`macro.py:_kr_indicators`) — not in `regime.py` |
| Korea 10Y / 3M rates | FRED (`IRLTLT01KRM156N` / `IR3TIB01KRM156N`, OECD-sourced series hosted on FRED) | `Korea_10Y`, `Korea_3M` | daily/monthly per FRED vintage, no explicit release-lag model applied (unlike the US `regime.py` indicators) | **display only** — not in `regime.py` |
| BOK policy rate | BOK official page scrape, `replay_rates.py` | `annualRatePct`, event-dated | effective the day *after* the announced decision (`replay_rates.py:5,32`) | Portfolio-level KRW cash/risk-free proxy (currency-consistent; base currency is KRW) — **not** a macro-regime input |
| ECOS: BaseRate, KTB_3Y, CorpBond_3Y, CPI, CoreCPI, IndustrialProduction, LeadingIndex, Exports, M2 | *configured in `config.json`, never fetched* | — | — | **`DATA_LINEAGE_UNRESOLVED`** — no consumer anywhere in `pipeline/` |
| Benchmark | `korea_prices.py` via `_krx_total_return_close`, Yahoo fallback | 069500.KS (KODEX 200) as-traded forward total-return close | daily | KR matched-benchmark excess return |
| Foreign/institutional investor flow, short interest | — | no field anywhere in the pipeline | — | not collected; see `docs/kr-alpha-research-design-v1.md` §candidate gates |
| National Pension Service allocation | official NPS homepage scrape, `national_pension.py` | fund-level asset-class allocation percentages (국내주식/국내채권/해외주식/...) | monthly, as-of the disclosed "기금 포트폴리오 ... 기준" date | **display panel only** — this is a *fund-level aggregate*, not a per-name holding, so it cannot feed a stock-selection score; noted and excluded as a candidate for that reason, not because it is unavailable |

**No fallback field was invented for anything in either table.** Where a
config key exists with no fetch implementation (ECOS), it is recorded as
`DATA_LINEAGE_UNRESOLVED`, not silently treated as available.

## 6-7. US and KR alpha research, defined independently

See `docs/us-alpha-research-design-v1.md` and
`docs/kr-alpha-research-design-v1.md` for the full candidate gates,
economic rationale, and pre-registered next hypothesis for each market.
Neither document backtests a candidate; both are pre-registration only,
per Section 19/33 of the request.

## 8-9. Macro regime audit

**US_GLOBAL_REGIME (current `regime.py`) is accurately named as such, not
as a "US regime."** Of its 21 indicators: `CFNAI`, `Payrolls`,
`Unemployment`, `Initial_Claims`, the five inflation series, `M2`, and
`Fed_Assets`/`RRP`/`TGA` are genuinely US-domestic. `NFCI`/`ANFCI` are
Chicago Fed indices, US-domestic by construction. `HY_Spread`/`IG_Spread`,
`Real_10Y`, `Breakeven_10Y`, `Broad_Dollar`, and `VIX` are US-market-priced
but globally *relevant* (a Korean exporter is exposed to the US high-yield
credit cycle and the dollar just as a US importer is). None is KR-domestic.
A rename to `US_GLOBAL_REGIME` (or similar) is a reasonable follow-up but
is **not** made in this PR — production code is unchanged (Section 25's own
instruction).

Every one of `regime.py`'s 21 `INDICATORS` (`regime.py:38-68`), classified:

| Class | Indicators |
|---|---|
| Genuinely US-domestic (little KR-equivalent use as a KR regime signal) | `CFNAI`, `Payrolls`, `Initial_Claims`, `NFCI`, `ANFCI`, `TGA`, `RRP`, `Fed_Assets`, `Yield_Curve` (US 10Y-2Y specifically) |
| Genuinely global / plausibly kept as a shared overlay | `WTI` (oil), `VIX` (global risk-sentiment proxy, though a US options index), `Broad_Dollar` (affects KRW and imported inflation directly), `HY_Spread`/`IG_Spread` (US credit, but correlates globally risk-off) |
| Has a direct KR analog **already collected but unused** in `regime.py` | `Headline_CPI`/`Core_CPI` <-> ECOS `CPI`/`CoreCPI` (901Y009/901Y010); `M2` <-> ECOS `M2` (101Y004); `Real_10Y`/`Breakeven_10Y` <-> `Korea_10Y` (partial analog, no KR TIPS-equivalent collected); `Fed_Assets`/liquidity axis <-> BOK `BaseRate` (722Y001) is a direct policy-rate analog to `FedFunds` |

One correction to Section 6 (US inputs table): `FedFunds`/`DFF` is
collected (`config.json fred.US.FedFunds`) but, like the KR series, sits
**unused** in `regime.py`'s `INDICATORS` — it appears only in `macro.py`'s
US display panel (`macro.py:68`). The US regime engine is not reading
every US series it collects either; this is noted for completeness, not
acted on in this PR.

See `docs/kr-macro-regime-design-v1.md` for the KR regime design (Section
24 of the request).

## 10. Macro is separate from alpha — reaffirmed, not changed

`regime.py`'s own docstring already states this: "The regime does NOT add
to any single-stock alpha. It drives a SEPARATE risk-budget layer." This
study does not touch that architecture. It is reaffirmed for both the US
and the future KR engine: `stock alpha + macro score = final alpha` is
never built. The architecture stays:

- **Alpha layer** — what to buy (region-specific factor engine).
- **Macro / regime layer** — how much equity risk to carry, and what
  region/style risk budget to grant (region-specific regime engine).

## 11. Macro x Alpha interaction — candidate hypotheses only, not tested

Recorded for future research, none tested or backtested here:

- Momentum under easing liquidity (US)
- Value under reflation (US)
- KR exporters under KRW weakness (KR domestic x external-financial-conditions interaction)
- Quality under slowdown (either region)

## 12-13. Factor definitions and weights need not match across regions

Nothing in this PR assumes `US Momentum == KR Momentum` in formula,
weight, horizon, retention, or candidate count. Nothing in this PR *changes*
any of those either — Section 13's prohibition list is honored in full:
no US/KR weight change, no factor removal, no macro threshold optimization,
no return-driven factor selection. This section exists to remove the
*assumption* that they must match, not to act on that removal yet.

## 14. Existing research, resorted by region

Built from what prior studies actually measured — no new backtest, and this
table is not used to set a new weight.

| Signal | US evidence | KR evidence | Pooled evidence | Data quality issue | Interpretation |
|---|---|---|---|---|---|
| Momentum | region-sign-unstable (`four-factor-signal-attribution-audit-v1`) | region-sign-unstable | pooled 126D IC -0.0015, p=0.9155 | none material | No pooled or single-region confirmatory evidence either sleeve works as currently defined. |
| Value | region-sign-unstable | region-sign-unstable, and separately KR value missing-rate 55.45% vs US 20.11% | pooled -0.0056, p=0.7373 | **KR PIT value coverage is materially worse** — DART serves from 2015, replay starts 2013 | KR value reading is `NO EVIDENCE DUE TO COVERAGE`-adjacent, not `EVIDENCE OF NO EFFECT` (per that study's own explicit rule) |
| Quality | region-sign-unstable, KR quality missing-rate 53.99% vs US 0.96% | region-sign-unstable | pooled -0.0223, p=0.0805 (closest to raw significance of the four, still fails) | **KR quality PIT coverage gap even larger than value's** | Same coverage caveat as Value, more severe |
| Lowvol | pooled component negative | standalone clears zero alone (+0.0511, CI excludes zero) | pooled +0.0286, p=0.1464 | none material | KR-only reading is real evidence but is explicitly **not** the primary claim (Section 8 of that study forbids substituting a regional reading for pooled); still worth carrying into KR-only research as a prior, not a conclusion |
| Fundamental Acceleration | -0.0056 (n=680 dates), coverage 81.79% | +0.0361 (n=460 dates), coverage **13.76%** | standalone -0.0026 (Holm p=1.0), incremental -0.0009 (Holm p=1.0) | **KR coverage is a sixth of US's** — see Section 15 | See Section 15 — the two regions' negative pooled result is not read the same way |

This table is not new evidence. It exists to demonstrate, from data this
repository already has, why continuing to force one pooled answer onto two
economically different markets is the wrong next move — not to select a
winner.

## 15. Fundamental Acceleration, read correctly by region

`fundamental-acceleration-discovery-v1` measured KR data-sufficient
coverage at 13.76% against US's 81.79% (a sixth as complete), because KR
requires two CONSECUTIVE DART filings and DART itself only serves from
2015 against a 2013 replay start. This asymmetry means the pooled CASE D
(`NO_DISCOVERY_EVIDENCE`) verdict that study reached is not equally
informative about both regions:

- **US**: 81.79% coverage lets the study evaluate the signal's own
  predictive power fairly directly — the negative US standalone reading
  (-0.0056) is close to a clean read of "this signal does not work in the
  US as currently constructed."
- **KR**: 13.76% coverage means data insufficiency and genuine signal
  weakness are **not separable** in the KR-only reading. The KR standalone
  point estimate is *positive* (+0.0361) despite its wide interval —
  consistent with either a real (if uncertain) KR effect, or noise from a
  thin, coverage-limited sample. Neither explanation is ruled out.

**The pooled result is not used to discard the KR signal.** This is
recorded as a live, uncertain candidate for `kr-alpha-discovery-v1`'s
consideration (see `docs/kr-alpha-research-design-v1.md`), contingent on
whether KR's fundamental PIT coverage improves enough by the time that
study runs to separate the two explanations.

## 16, 30. Alpha discovery budget — fixed, not open-ended

```
US_ALPHA_DISCOVERY_BUDGET = 1
KR_ALPHA_DISCOVERY_BUDGET = 1
```

Exactly one US-only independent alpha hypothesis (`us-alpha-discovery-v1`)
and exactly one KR-only independent alpha hypothesis
(`kr-alpha-discovery-v1`) will be run as historical discovery on this
ledger. Neither is executed in this PR — both are pre-registered only.
Default stop rule: if neither shows meaningful discovery-stage evidence,
`HISTORICAL_ALPHA_DISCOVERY_PHASE = CLOSED` is declared and the programme
moves to prospective validation or to instrumenting new data sources,
never to a third or fourth signal search on the same historical sample.

## 17-18. Candidate selection gates

See the two design docs. Candidates are gated (economic rationale,
orthogonality, PIT quality, historical depth, coverage, implementation
integrity, sustainable data access), never selected by running them
through historical return first (Section 19).

## 19. No return-driven candidate selection in this PR

No candidate signal in either design doc was scored against historical
return before being written down. Both design docs' candidate tables are
built from data-lineage and economic-rationale reasoning only.

## 20. Prospective validation stays region-independent

`US_SIGNAL_SEAL` and `KR_SIGNAL_SEAL` are conceptually separate append-only
prospective stores (mirroring the pattern `fundamental_acceleration_seal.py`
already established for the pooled case). A US signal is scored only
against US benchmark-relative outcomes; a KR signal only against KR's. No
code implementing this is added in this PR (Section 33) — it is a stated
design constraint for whichever of the two pre-registered discovery studies
proceeds to a prospective phase.

## 21. Benchmark discipline — reaffirmed

SPY (US) and 069500.KS/KODEX 200 (KR) are each already on a total-return
-compatible basis (`benchmark_source.py`, `config.json`'s own
`benchmarkSources._notes`). They are never combined into one excess-return
series; they meet only at the regional capital-allocation layer above
stock selection (`regional_rotation.py`/`regional_validation.py`).

## 22. Currency issue

Base currency is KRW (`config.json kellyPortfolio.currency.baseCurrency`),
with `fxReturnsIncluded: false` and `fxHedged: false` explicitly stated.
US stock selection is evaluated as `US stock return - SPY return` — a pure
USD-basis comparison — so USD/KRW movement cannot make US stock-picking
alpha look better or worse than it is. Kelly's `REGIONAL_ACTIVE` covariance
basis (`kelly_portfolio.py:712-717`) is built from each region's own
active-return series (stock minus own regional benchmark) precisely to
keep this separation, and `investment-philosophy.md` states the limitation
explicitly (`currencyPolicy` disclosed in the artifact). The one caveat
flagged in Section 4, row 18 — the `ABSOLUTE_LOCAL_CURRENCY` covariance
fallback pooling raw local-currency returns across regions if the regional
path fails — is a pre-existing production behavior, noted here, not
changed in this PR.

## 23. Regional allocation stays separate from alpha selection — reaffirmed

```
US stock selection        KR stock selection
        |                         |
independent regional portfolios
        |
regional capital allocation
        |
   final portfolio
```

`regional_rotation.py`/`regional_validation.py` already implement exactly
this layering (`docs/regional-rotation-validation-v1.md`) and remain
CHALLENGER, unwired to production. This PR does not change that status.

## 24-25. See the two macro documents

`docs/kr-macro-regime-design-v1.md` (new KR axis design) and Section 8-9
above (US/global audit) cover these in full.

## 26. Production impact

None. No factor weight, CHAMPION, selector, region cap, live/paper
ranking, Kelly parameter, macro multiplier, or regional-allocation rule
changes in this PR. `promotionEligible: false`.

## 27. Final architecture

```
                    FINAL PORTFOLIO
                          |
                 Capital Allocation
                          |
          +---------------+---------------+
          |                               |
       US BOOK                         KR BOOK
          |                               |
   US risk budget                   KR risk budget
          |                               |
   US macro regime                  KR macro regime
   (regime.py, audited              (design proposed,
    Section 8-9 — already            docs/kr-macro-regime-
    exists, US/global inputs)        design-v1.md — not
                                      implemented here)
          |                               |
   US Alpha Engine                  KR Alpha Engine
   (score_cross_section,            (score_cross_section,
    shared formula today)            shared formula today —
                                      research target, not
                                      changed here)
          |                               |
  US-only signals                  KR-only signals
  (next: us-alpha-                 (next: kr-alpha-
   discovery-v1,                    discovery-v1,
   pre-registered)                  pre-registered)
          |                               |
   SPY benchmark                 KODEX 200 benchmark
```

Macro is never added into single-stock alpha in either book, in either the
current architecture or the proposed KR regime.

## 28. Answers

**Q1. Which parts are already separated in real code?**
Universe, benchmark resolution, transaction costs, fundamental data
sources (DART vs Finnhub), price data sources (KRX/FDR vs Yahoo), the
per-region call boundary in `score_cross_section`, entry-state ranking
(percentile within region), Kelly's primary `REGIONAL_ACTIVE` covariance
path, and the entire regional-rotation capital-allocation layer. See
Section 4 rows 3-9, 12, 17, 18.

**Q2. Which parts still use one common model?**
Factor formulas, factor weights, entry-state thresholds, the selection
score formula and its 66th-percentile gate (applied to both regions'
candidates on one shared scale before region caps intervene), and —
critically — the entire macro regime, which is 100% US/global with zero
KR domestic inputs. See Section 4 rows 1, 2, 10, 13, 14, 15.

**Q3. Does existing factor evidence actually show regional sign
instability?** Yes, measured, not assumed: every one of five signals
tested (momentum, value, quality, lowvol, fundamental acceleration) shows
either outright sign disagreement or a KR-only significant reading that
does not survive pooling. See Section 1 and Section 14.

**Q4. Is treating US/KR as separate alpha research problems justified by
the data?** Yes. Five-for-five sign instability across independently
motivated factors, plus a measured ~16x difference in calibrated alpha
*level* between regions (`region-quota-removal-v1`), is a stronger
statement than "no common factor was found" — it is evidence the
economically appropriate ranking construction likely differs by region,
not merely its calibration.

**Q5. How US-centric is the current macro regime?** Entirely. All 21
`regime.py` indicators are FRED or CBOE series; the fetched KR series
(`USD_KRW`, `Korea_10Y`, `Korea_3M`) are display-only and never enter the
regime classification. See Section 8-9.

**Q6. What KR-relevant macro data already exists?** `USD_KRW`, `Korea_10Y`,
`Korea_3M` (via FRED, currently display-only) and the BOK policy rate
history (`replay_rates.py`, currently used only as a KRW cash/risk-free
proxy, not a regime input).

**Q7. What additional KR domestic macro data is needed?** BOK ECOS series
already *named* in `config.json` (BaseRate, KTB_3Y, CPI, CoreCPI,
IndustrialProduction, LeadingIndex, Exports, M2) but never fetched — see
`docs/kr-macro-regime-design-v1.md` for which of these are prioritized and
why, and which remain unverified.

**Q8. Which global variables should a KR model keep?** US real 10Y, Fed
Funds, US 2Y/10Y, Broad Dollar, VIX, HY spread — external financial
conditions a small open economy is genuinely exposed to. See
`docs/kr-macro-regime-design-v1.md` Axis B.

**Q9. US next single alpha hypothesis candidate?** See
`docs/us-alpha-research-design-v1.md`.

**Q10. KR next single alpha hypothesis candidate?** See
`docs/kr-alpha-research-design-v1.md`.

**Q11. Are both candidates testable cleanly on historical PIT data?**
Addressed per-candidate in each design doc's own gate table; neither
candidate is selected without a PIT-availability answer first, per Section
19's rule against return-driven selection.

**Q12. How does independent prospective validation start for each?**
Via the `US_SIGNAL_SEAL`/`KR_SIGNAL_SEAL` split (Section 20) once each
discovery study's design is approved and (if warranted) implemented — not
in this PR.

## 29. Classification

**CASE A — `READY_FOR_REGIONAL_RESEARCH`.**

The data architecture already supports independent US and KR alpha
research: separate universes, benchmarks, transaction costs, fundamental
and price data sources, and (for US) a fully-populated macro regime. KR
alpha research can proceed on the existing four factors plus fundamental
acceleration immediately. KR *macro* research has a real, named,
`DATA_LINEAGE_UNRESOLVED` gap (ECOS never wired) that
`docs/kr-macro-regime-design-v1.md` documents but does not block
KR-only *stock-selection* research, which does not depend on the macro
regime being region-specific yet (macro remains a separate risk-budget
layer per Section 10, and today's US/global regime can continue to gate
overall equity risk while KR-specific stock selection research proceeds
independently).

`us-alpha-discovery-v1` and `kr-alpha-discovery-v1` can both be
pre-registered now (see the two design docs). Implementing a KR-specific
regime (closing the ECOS gap) is a parallel, separate workstream — not a
precondition for KR alpha discovery, per this classification's own
reasoning above, but it is a precondition for a KR-specific risk-budget
layer to ever exist.

## 31. Data snooping discipline

`replay-v16` has been used by twelve prior studies, including this one's
own evidence-gathering in Section 1 and 14. Any future US-only or KR-only
historical result on this ledger is `DISCOVERY_ONLY`. Final evidence comes
from the prospective sealed window (Section 20). A good historical
reading from either of the two pre-registered discovery studies does not
fast-track production promotion; a bad one does not get rescued by tuning.

## 32. Document outputs

1. `docs/regional-alpha-research-separation-v1.md` — this document.
2. `docs/us-alpha-research-design-v1.md`
3. `docs/kr-alpha-research-design-v1.md`
4. `docs/kr-macro-regime-design-v1.md`

## 33. Code change scope

No production code is changed in this PR. No historical artifact is
modified or rewritten. This is documentation only.

## 34. Verification

No code changed → `ruff check .`, `python -m compileall pipeline`,
`pytest -q` are run as a baseline-unchanged check (Section 34's own
instruction), not because any module changed.

## 35-36. Git discipline and GitHub Actions

New branch from latest `main`; Draft PR only; no auto-merge. See the PR
description for the exact required workflow statement.
