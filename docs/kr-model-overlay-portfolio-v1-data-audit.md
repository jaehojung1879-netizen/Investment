# Outcome-blind source and data-gap audit

Starting main: `449508ad18ef6f4a7fce3678c0f593b3237dbab3`. The earlier audit is retained, not reversed. The continuation explicitly allows KRX capitalization and defers sectors. No return/label/performance criterion was used for feature eligibility.

## Source inventory

| Source / grain / history | PIT / units / actions / applicability | v1 status, coverage and limitations |
|---|---|---|
| DART share-count blob `a515ca2c4f237d688566b45b2f4cc5afd3d6f0fb` at `4ea107ed…`; issuer/report records, 2015–2026 | No receipt or public-date provenance; share count, common/preferred selection legacy logic | **REJECTED_AS_PIT_VALUATION_SOURCE**. All 3,721 records lack `availableFrom` and receipt lineage. Counts by FY: 2015 74; 2016 309; 2017 347; 2018 360; 2019 366; 2020 382; 2021 400; 2022 366; 2023 334; 2024 324; 2025 311; 2026 148. Never read by v1 input preparation. |
| Official `KRX:sto/stk_bydd_trd`, security/date; `close, marketCap, listedShares, volume, tradingValue`; historical KOSPI service already used by repository | Signal-close observed KRW price/capitalization/turnover, shares/volume in units. Execution strictly next session or later. Exact query/served-date match; own cap/close/shares reconciliation ≤1%. No total-return Close as monetary denominator. | **PRIMARY_MARKET_VALUE_SOURCE**. New immutable daily cache/collector implemented. New daily complete-value cache has NOT been collected in this task; joined coverage by year is **NOT_MEASURED**, never zero or invented. Existing monthly universe caps are not substituted. Cash dividends/splits can change quotes; direct observed cap avoids mixing a historical share count with a different price basis. |
| KRX monthly ranked top120 membership, per-security/date, 2013–2026; exact v5 universe blobs at `4ea107ed…` | Latest strictly older snapshot. No current-listing union. Monthly transition uncertainty inherited; market cap rank provides membership only. | **REUSED_PINNED_PIT_UNIVERSE**. Hashes pinned in spec; frozen coverage semantics inherited, not relaxed. |
| `kr-repaired-accounting-snapshot-v1`, issuer × FY × report; 2015–2026, 9,351 records, 250/260 tickers, frozen source `fb6e837…` | Strict receipt date `< signalDate`. KRW unscaled. BS assets/liabilities are levels; NI/OCF are YTD/annual flows. DD TTM rollforward; CFS/OFS chain equality required. No earlier visibility invented for amendments. | **REUSED_PINNED_ACCOUNTING**. Four concept families have lineage; 400 records lack a family, two receipt mismatches are rejected by visibility. Canonical-v2 8,826 records and 525 original FY2015 XBRL records; original-XBRL without a single explicit record-level CFS/OFS basis is withheld in this version. The prior 60-fact source validation does not validate all 8,826 canonical records. |
| Repaired assets and liabilities | Same filing/basis; total equity = assets − liabilities; includes NCI for CFS | **ELIGIBLE_PROXY**. Not parent/common equity. Issue market cap is not total consolidated equity capitalization; ratios are explicitly named proxies and flagged. Preferred class economics remain a known limitation; no unverified issuer capitalization aggregation. |
| Repaired NI and OCF | Annual as filed or FYprior − same-stage YTDprior + current YTD; all visible and identical CFS/OFS | **ELIGIBLE_PROXY** for NI/cap, OCF/cap, NI/assets, OCF/assets, (OCF−NI)/assets, same-stage prior-TTM OCF improvement/assets. Negative numerators retained; nonfinite/missing or denominator ≤1 KRW is missing. Cash conversion means differ across business models, especially financial firms. No modern industry map used to conceal this. |
| replay-v16 frozen adjusted price index, security/session; cutoff 2026-09-14; benchmark 069500.KS | Immutable manifest/content-addressed objects, exact regional sessions. Trailing ratios at/through signal-close; next-session close endpoints only behind permit. | **REUSED_TARGET_SEMANTICS**. Includes distributions only where vendor event inputs existed. KRX native bars alone are price-return; unresolved dividends/terminal economics remain unresolved. Not unqualified full shareholder total return. |
| KRX daily trading value/volume + past adjusted-index changes | ADV60 KRW includes all 60 sessions, all quotes present and volume positive; downside126 zero-target semideviation over all126 sessions | **ELIGIBLE_RISK_INPUTS**. No adjusted Close × Volume turnover. New joined liquidity coverage not yet measured. Suspension/zero-volume signal excludes fresh admission; actual executable quotes control later fills. |
| Historical sector/industry classifications | No verified dated classification in pinned input tree; static `sectors.py` has no availability history | **DEFERRED_BY_PIT_SECTOR_HISTORY**. Earlier repo audit plus one bounded check of official KRX listings/industry page and pinned source tree found no reproducible historical classification contract. This does NOT prove no paid/public history exists anywhere. No sector ranks, normalization, caps or financial classification in v1. |
| Benchmark trend/volatility | Observed same-close index; SMA200 and annualized std63. No macro vintage needed | **ELIGIBLE_OVERLAY**. USD/KRW, Korean rates/curve/credit and market breadth are deferred; source publication/vintage/denominator contracts are not independently frozen for this system. |

The accounting manifest contains FY counts and family coverage (full per-shard measurements are in the pinned `research_specs/kr-repaired-accounting-snapshot-v1.json`). Do not pretend its filing-level coverage equals tradable security/signal coverage. The executable gate computes the latter by year including missing members, using the exact fixed registry below. The warmup 2015–2016 is disclosed; gates start 2017. Data validity determines eligibility; no feature is dropped if a gate fails later. A failed registered feature gate blocks the system instead of silently substituting a price-only model.

## Fixed registry

| Family | Exact raw feature names | Definition |
|---|---|---|
| VALUE | `bookToMarketProxy`, `earningsYieldProxy`, `ocfYieldProxy` | Total book equity / direct KRX cap; TTM total NI / cap; TTM OCF / cap |
| QUALITY | `netIncomeToAssets`, `ocfToAssets`, `negativeAccrualsToAssets` | NI/assets; OCF/assets; (OCF−NI)/assets; all signed |
| CATALYST | `relative126`, `momentum121`, `ocfImprovementToAssets` | 126-session index return minus benchmark; 252-to-21-session skip-month momentum; same-stage prior-year TTM OCF change / current assets |
| RISK | `negativeDownsideVol126`, `logAdv60` | Negative annual downside semideviation; log(1+ADV60 KRW) |

Registry eligibility is structural, subject to the predeclared joined coverage gates. Real KRX-cache and joined coverage are pending, so this is **machine frozen / raw-data readiness pending**, not verified operational readiness.

## Deferred candidates and reasons

* Gross/operating profitability, EBITDA, interest coverage, cash/net debt, ROIC, sales/EV: concept identity/statement/basis or cross-sector applicability not validated in the repaired four-family contract (**DEFERRED_SOURCE_OR_SEMANTICS**).
* FCF yield, investment intensity: capex coverage/semantics are insufficient in prior outcome-free audit; do not turn absent capex into zero. Asset growth can be valid but is deferred to keep a small quality/catalyst model, not because of returns.
* Parent-attributable/common book equity and NI, common/preferred aggregate issuer capitalization: not separately validated; raw total-entity proxies disclosed instead of silently calling them common equity.
* Dividend yield/increase and distribution return attribution: ordinary continuing-security payment/ex-date lineage not fully validated; terminal dividend audits alone are not a market-wide feed.
* Share-count reduction, buyback announcements/completions/cancellations: no independently sealed sufficient event history; legacy share records rejected. Ownership disclosures do not establish buyback execution.
* Sector-relative valuation, own-history valuation z-score: sector history unresolved; own-history point-in-time monetary denominator series needs the new cache and adds a second correlated value construction. Deferred, no performance screening.
* OCF/NI: sign-sensitive loss denominator contract avoided. Negative accruals/assets provides a non-sign-flipping alternative.
* Attention shock features: economically distinct from six-to-twelve-month valuation convergence and not essential to the small architecture; excluded before outcomes, regardless of v5 estimates.
* Analyst revisions/consensus: no permitted PIT source. No fabricated estimates.

No external economic-series histories were collected. The only added source infrastructure is the official KRX date-specific market-value cache. It is first-write immutable, complete-day identity checked, source hashes recorded, and invalid data refuse rather than masquerade as observed zeros.

## Core family observability and model eligibility repair

Before imputation, valueObserved, qualityObserved and catalystObserved each mean at least one finite raw constituent in that family. PRIMARY stock eligibility requires their conjunction, coreFamilyObserved; RISK/price variables cannot substitute for absent VALUE or QUALITY. Individual constituent missing indicators remain. Execution gates report all four presence rates by year over all PIT member name-dates, alongside existing per-feature coverage. Freeze coreFamilyObserved >=20%, using the existing accounting-family floor; a real failure yields DATA_INSUFFICIENT with no post-outcome relaxation. Joined coverage remains NOT_MEASURED.

MODEL training/evaluation uses only MATURED + ELIGIBLE finite-return rows, with ten eligible names/date and registered depth rules. Ineligible/unresolved terminal rows are explicitly excluded, never return-imputed, and status/core-family/raw missingness diagnostics retain the full annual denominator. These exclusions do not invalidate sufficient remaining model evidence. They are not an ex-ante terminal selection filter. ACTUAL PORTFOLIO held unresolved terminal economics still block/withhold the continuous path.
