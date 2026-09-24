# Alpha data foundation v2 — lineage manifest

> Per-field lineage for every new derived/collected field this PR adds.
> Nothing here is wired into any scoring path.

## Workstream A — `pipeline/accounting_quality.py` (`ACCOUNTING_QUALITY_V1`)

| Field | Region | Raw source | Canonical raw account(s) | `availableFrom` | Transformation | PIT safety |
|---|---|---|---|---|---|---|
| `ocfToNetIncomePct` | KR | DART | `영업활동현금흐름` / `당기순이익` | filing receipt date | TTM(OCF)/TTM(NI) × 100, via `dart_derive.trailing_twelve_months` | Reuses production's own rollforward; no new PIT logic |
| `ocfToNetIncomePct` | US | Finnhub | `NetCashProvidedByUsedInOperatingActivities...` / `NetIncomeLoss...` | SEC accepted-filing date | Same, via `finnhub_derive.trailing_twelve_months` | Same |
| `fcfToNetIncomePct` | KR/US | DART/Finnhub | OCF − |capex| over NI | same as above | Same rollforward, then ratio | Same |
| `assetGrowthPct` | KR | DART | `자산총계` (level) | filing receipt date | (assets − prior-year same-stage assets) / prior × 100 | Level comparison, same-stage-a-year-apart, matching `earningsGrowth`'s own discipline |
| `assetGrowthPct` | US | Finnhub | `Assets` (level) | SEC accepted-filing date | Same | Same |
| `debtGrowthPct` | KR | DART | `부채총계` (level) | filing receipt date | Same construction as assetGrowthPct | Same |
| `debtGrowthPct` | US | Finnhub | `Liabilities` (as-filed or Assets−Equity fallback, via `finnhub_derive.total_liabilities`) | SEC accepted-filing date | Same | Same |
| `capexIntensityPct` | KR/US | DART/Finnhub | capex / TTM revenue × 100 | as above | TTM rollforward then ratio | Same |
| `shareCountChangePct` | KR | DART | share count (`carried_shares`, AS_FILED or CARRIED_FORWARD) | as above | (shares − prior-year same-stage shares) / prior × 100 | Inherits `dart_derive`'s carry-forward discipline (never carries FORWARD from a later filing) |
| `shareCountChangePct` | US | Finnhub | share count (`share_count`/`carried_shares`) | as above | Same | Inherits `finnhub_derive`'s own carry-forward discipline |

Coverage (measured against the real sealed store, `signal-history` branch,
126 KR tickers/3,965 rows 2015-2026, 779 US tickers/30,999 rows 2011-2026):
see `docs/alpha-data-foundation-v2.md`'s Workstream A section for the full
table. `NOT_FEASIBLE_DATA_MISSING`: receivables growth, inventory growth,
any working-capital metric — no raw line item collected in either region.

## Workstream B — `pipeline/liquidity_attention.py` (`LIQUIDITY_ATTENTION_V1`)

| Field group | Raw source | `availableFrom` | Transformation | PIT safety |
|---|---|---|---|---|
| Volume ratios (1/20, 1/60, 5/20, 5/60), log shock, z-score | Existing OHLCV (Close/Volume) | Same trading day (end-of-day, no restatement) | Rolling mean/std over the trailing window, ending at each row | Backward-only rolling windows; no future row read |
| Dollar volume, turnover | Close × Volume; turnover additionally needs a shares-outstanding series | Same trading day | Direct multiplication/ratio | Same; turnover is `NaN` without a share count, never guessed |
| Close-location value, abnormal range, gap, gap×volume, range×volume | Open/High/Low/Close | Same trading day | Direct arithmetic on the day's own OHLC plus a trailing average | `NaN` on a zero-range day, never a fabricated 0.5 |
| Close-near-high/low-after-shock | Derived from the above | Same trading day | Threshold indicator, conditional on a shock day | `NaN` on a non-shock day; not complements of each other |
| Amihud illiquidity proxy | |return| / dollar volume | Same trading day | Rolling mean over 20 days | `NaN` wherever dollar volume is non-positive |

Cross-sectional percentile (`cross_sectional_percentile`) is a caller's own
separate call across a date's universe — this module never bakes a
percentile into a per-ticker field.

## Workstream C — `pipeline/kr_investor_flow.py`

| Field | Source | `availableFrom` | Coverage/status |
|---|---|---|---|
| Foreign/institution/individual net buy (`MDCSTAT02302`) | KRX public statistics portal | Trading date (end-of-day settlement, no restatement) | **UNPROVEN** — probe not yet run with real network access |
| Institution sub-breakdown (금융투자/보험/투신/사모/은행/기타금융/연기금/기타법인, `MDCSTAT02303`) | Same | Same | Same |

## Workstream D — `pipeline/dart_ownership_events.py`

| Field | Source | `availableFrom` | Coverage/status |
|---|---|---|---|
| `rcept_no`, `rcept_dt`, `corp_code`, `corp_name`, `report_tp`, `repror`, `stkqy`, `stkqy_irds`, `stkrt`, `stkrt_irds` | DART `majorstock.json` (API group DS004) | `dart_fundamentals.receipt_date(rcept_no)` — same mechanism as financial statements | **UNPROVEN** — field set corroborated from third-party libraries, not a live response; probe not yet run |
| `reportType` (`NEW_5PCT_HOLDER`/`OWNERSHIP_CHANGE`/`reportTypeRaw` passthrough) | Derived from `report_tp` | Same | Only two DART label values are mapped; anything else passes through unchanged |
| Derived INCREASE/DECREASE/EXIT_BELOW_THRESHOLD | Derived from the sign of `stkrt_irds` and whether `stkrt` crosses below 5% | Same | Never reads an unconfirmed "before" field; no subtraction performed on unverified fields |

## Workstream E — `pipeline/kr_short_selling.py`

| Field | Source | `availableFrom` | Coverage/status |
|---|---|---|---|
| Daily short-sale trading volume/value (`MDCSTAT301`) | KRX public statistics portal | Intraday (same-day after 15:40 KST regular market, full day after 18:10 KST) | **UNPROVEN** — screen id/lag researched via WebSearch of KRX's own page description, not a direct read |
| Net short position balance (`MDCSTAT305`) | Same portal, investor-reported | T+2 from a 0.01%-of-shares or KRW 1bn threshold crossing — a DIFFERENT, LONGER lag than the trading screen | Same |
| `regimeLabel` (`NORMAL`/`BANNED_COVID`/`BANNED_STRUCTURAL`) | Derived from published Korean short-selling ban date ranges | N/A (a classification, not a fetched value) | Carried on every row so a factor built on this data cannot silently pool across a ban period |

## Workstream F — `pipeline/macro_context.py` (US), `pipeline/ecos_macro.py` (KR fetch layer)

| Field | Source | `availableFrom` / vintage | Coverage/status |
|---|---|---|---|
| Axis level/change/acceleration, all 6 axes | `regime.INDICATORS` (FRED/CBOE), via `regime.indicator_read`/`_axis_summary` | Each indicator's own `release_lag_business_days`, exactly as `regime.py` already enforces | **Built and tested on synthetic data.** Live coverage depends on the same FRED/CBOE access `regime.py` already has in production. |
| ECOS series (BaseRate, KTB_3Y, CorpBond_3Y, CPI, CoreCPI, IndustrialProduction, LeadingIndex, Exports, M2) | Bank of Korea ECOS `StatisticSearch` | Vintage status: `REVISED_HISTORY`, not `PIT_EXACT` (current-value API, no ALFRED-style release history found) | **UNPROVEN** — no `ECOS_API_KEY` available in this session; `KTB_3Y`/`CorpBond_3Y` additionally blocked on an unresolved `itemCode` (schema now supports it; value is `null`, not guessed) |

## Workstream G — `pipeline/dividend_events.py`

| Field | Source | `availableFrom` | Coverage/status |
|---|---|---|---|
| `dividendPerShareTtm`, `priorDividendPerShareTtm`, `changePct`, `event` | Finnhub `CommonStockDividendsPerShareDeclared` (`PER_SHARE` class) | SEC accepted-filing date | **Measured**: 3,806 classifiable events, 220/779 tickers (28.2%). Known precision ceiling: raw values observed as bare integers only (sub-dollar precision loss upstream, not introduced by this module). |

## Guru track — `pipeline/guru_13f_store.py`, `pipeline/security_identity.py`

See `docs/guru-decision-atlas-data-v1.md` in full for schema, action
threshold, identity-resolution tiers, and access status.
