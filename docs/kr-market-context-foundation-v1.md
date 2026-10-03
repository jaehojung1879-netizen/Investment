# KR market context foundation v1

PR #188 continues from reviewed head b0ced85853046488817329220ca3688e7daf6965,
with main/base 9504f970a2895781eedcc3a6a1c94126fd4682f8. This is source
validation and reusable architecture. No historical Alpha labels, fitting,
future industry ranking, threshold search or sealed execution is permitted.

The program is MarketContext → IndustryCycleState → StockWithinIndustry →
Portfolio/RiskBudget. Its eventual economic objective is future benchmark-relative
Alpha after costs and investability. Context itself makes no prediction claim.

## Separate KR axes

| Axis | Measurements | Interpretation and remaining prerequisites |
|---|---|---|
| domesticGrowth | industrial production, exports, leading index | Native units and exact seasonal adjustment/index semantics must be validated; no common favorable score |
| inflation | CPI, CoreCPI | Index levels, backward changes; annualized/YoY transforms can be preregistered later after exact index semantics |
| domesticRates | BOK base rate, Korea 3M, Korea 10Y, matched 10Y−3M spread | OECD 3M is an interbank rate; do not describe it as a Treasury bill yield |
| domesticLiquidityCredit | KR M2, KTB 3Y, rated corporate 3Y yield, matched corporate−government spread | Corporate yield is not itself a spread. AA− versus BBB− is an explicit semantic choice |
| externalFinancialConditions | USD/KRW, broad USD, US real 10Y, Fed funds, US 2Y/10Y, HY spread, VIX | First-class external axis for a small open export economy |
| equityMarketState | KODEX200 trend adverse flag, 63-session realized volatility, future breadth and concentration | Reuses `kr_market_risk_overlay.state_at`; breadth needs measured full universe and PIT membership; concentration needs dated cap/universe. Missing remains null |

`pipeline/kr_market_context.py` produces a date/region/axes record with per-measurement
value, backward change, direction, acceleration, unit, source, coverage, observedThrough,
publishedAt, availableFrom, fetchedAt, knownFrom and vintageStatus. Axis coverage is
observed/expected measurements; no axis scalar, good/bad score, Goldilocks or Stagflation
label is emitted. Adjacent native observations are the default difference window;
callers may preregister another positive window. Index changes remain in index points,
not inflation/growth rates. Mixed units or source definitions block changes. Derived
spreads require aligned observation endpoints and explicit matching units; spread
changes/acceleration remain null until a dated derived series is supplied.

Knowledge records are immutable. The latest visible vintage for each observation is
chosen before past differences. Both observation and availability must be at/before t.
For revised/current snapshots, knownFrom also cannot precede the retained fetch of that
exact value. An approximate historical release date cannot make a current revised
number visible in the past. Date-only input means UTC midnight; adapters must provide
real publication instants, including Korea close timestamps, for intraday work.

The benchmark wrapper requires a snapshot availability instant, calls the existing
past-only 201-session KODEX engine, and emits trend/vol only. Caller price lineage is
explicitly unverified; it is not historical confirmatory evidence. Its existing risk
multiplier remains in the separate risk-budget layer. Inputs after t cannot affect it.

## Existing FRED/global reuse

The inventory is generated from current `config.json`, `datafeed.py`, `regime.py`
and `pit_data.py`; this PR makes no new FRED request or vintage entitlement claim.

| Input | Existing source | Current repository vintage contract |
|---|---|---|
| USD_KRW | FRED DEXKOUS, daily | REVISED_HISTORY unless retained release evidence exists; no new evidence here |
| Korea_10Y | FRED IRLTLT01KRM156N, monthly OECD long-term rate | Same; observation date is not publication date |
| Korea_3M | FRED IR3TIB01KRM156N, monthly OECD interbank rate | Same; not a Treasury proxy silently substituted |
| Broad_Dollar | FRED DTWEXBGS | Existing fetch reused; no PIT upgrade |
| Real_10Y | FRED DFII10 | Existing fetch reused; no PIT upgrade |
| HY_Spread | FRED BAMLH0A0HYM2 | Existing fetch reused; no PIT upgrade |
| FedFunds, Treasury_2Y, Treasury_10Y | FRED DFF, DGS2, DGS10 | Existing fetch reused; no PIT upgrade |
| NFCI, ANFCI, IG_Spread | FRED NFCI, ANFCI, BAMLC0A0CM | Existing financial-condition inputs inventoried; additional context candidates, not added to KR axis by this change |
| VIX | Existing `fetch_vix`, Yahoo ^VIX; economic source CBOE | No retained release-vintage matrix supplied; current/revised source contract |

`MacroVintageView` counts actual nonempty release frames, not opt-in names, and
`vintage_column` drops later releases before reconstruction. Derived US Yield_Curve
reuses `pit_data.derive_macro_columns` and is exact only if both legs are exact.
AGENTS records 10/28 panel columns with no ALFRED history; moving a lag or start date
cannot open that aggregate gate. No previous probe/study is rerun here. Existing US
regime aggregation/transformations, macro-context definitions and display behavior
remain unchanged. Their lag filtering is availability approximation, not vintage proof.

## Manual ECOS source validation

The existing registered `probes.yml` gains `probe=ecos-market-context`, usable on
this PR branch without merging a new workflow onto main. A separate job requires
`workflow_dispatch`; other probe jobs exclude this option. Only that step receives
`ECOS_API_KEY: ${{ secrets.ECOS }}`. PR metadata audit receives no credentials.
The runtime refuses any other event, uses fixed read-only metadata/search APIs,
never logs a credential-bearing URL or arbitrary exception/message, rejects any
credential echo in serialized output, and uploads only source-readiness JSON.

`StatisticSearch` now has the actual positional row-range/table/cycle/start/end
contract. Each series has its own native cycle; there is no caller default D.
Unverified item/cycle/source identity blocks collection, including unique tables.
Daily, monthly, quarterly and annual periods are formatted independently;
pagination limits fail closed and partially fetched series are discarded.
Blank, nonnumeric and nonfinite observations are absent, never zero.

The probe reads full paginated table/item metadata. It reports configured table
existence, candidate tables/items, each item's native cycle, group/code/name/unit,
START_TIME/END_TIME/DATA_CNT, source status and a latest-period smoke status.
A unique exact semantic primary item with unambiguous additional groups can resolve
a candidate. Multiple corporate ratings, core-index definitions, seasonal adjustment
choices or other group alternatives remain AMBIGUOUS_SOURCE or DATA_LINEAGE_UNRESOLVED.
No fuzzy first-row match or guessed item code is written into config.

For ambiguous cases, dispatch `args` is JSON containing exact selections by friendly
name. Each selection must supply seriesId, cycle, itemCode (and itemCode2/3/4 where
needed), semanticName, expectedTableName, expectedItemNames and expectedUnit. These
must match fresh metadata and the allowed semantic family before a read-only latest
observation smoke. Args is parsed as data, never shell. The output's validatedConfig
contains only resolved codes/cycles and REVISED_HISTORY, suitable for reviewed application
to config. Wrong existing placeholder tables remain visible alongside alternatives.

LIVE_VALIDATED_SOURCE describes endpoint/identity/smoke validation. Independently,
ECOS history is REVISED_HISTORY. Metadata observation coverage is not release-date
coverage; publishedAt/availableFrom remain null when ECOS provides no evidence.
No ALFRED-equivalent endpoint or first-vintage history is invented. The fixed metadata
services expose no retained revision matrix in the adapter contract; live output
records the services actually inspected and absence of vintage evidence.

**Actual manual Actions status: completed successfully.** Run
[37080934658](https://github.com/jaehojung1879-netizen/Investment/actions/runs/37080934658)
ran on head `6ebe13922e899b88e938f4f7aec7b8575ec47f34`. This revision downloaded
only artifact `11258377162`, named
`ecos-market-context-source-metadata-37080934658`, and applied its facts offline.
No ECOS request or probe rerun was made to apply this evidence.

Verified ZIP SHA-256:
`6a0f59e13737b55102cfd3bbdf31f812c19ce71e104a0fde9727d86dcbffb1b3`.
Verified sanitized JSON byte SHA-256:
`8cfb15cdcbf88796831b2b2c7eb25d44ca411a8acf44a53512906dd7f32e6b07`.
The metadata was checked at `2026-10-03T00:15:46.789703+00:00`.
`research_specs/kr-market-context-ecos-evidence-37080934658.json` retains an
explicitly scoped metadata extract, original selection hashes, unresolved
semantic/group alternatives and exact artifact provenance. It is not a copy of
the complete discovery catalog; the full source JSON is identified by the hash above.

| Name | Configured table exists | Applied item / native cycle | Exact semantic name / unit | Observation coverage | Source status |
|---|---|---|---|---|---|
| BaseRate | 722Y001: yes | null / null | unresolved | null | AMBIGUOUS_SOURCE |
| KTB_3Y | 817Y002: yes | 010200000 / D | 국고채(3년) / 연% | 19981113–20261002; 6,910 observations | LIVE_VALIDATED_SOURCE |
| CorpBond_3Y | 817Y002: yes | null / null | rating unresolved | null | AMBIGUOUS_SOURCE |
| CPI | 901Y009: yes | null / null | native cycle unresolved | null | AMBIGUOUS_SOURCE |
| CoreCPI | 901Y010: yes | null / null | definition unresolved | null | DATA_LINEAGE_UNRESOLVED |
| IndustrialProduction | 901Y033: yes | null / null | production/adjustment selectors unresolved | null | DATA_LINEAGE_UNRESOLVED |
| LeadingIndex | 901Y067: yes | I16E / M | 선행지수순환변동치 / 2020=100 | 197001–202608; 680 observations | LIVE_VALIDATED_SOURCE |
| Exports | 901Y011: no | null / null | table unresolved | null | NOT_AVAILABLE |
| M2 | 101Y004: yes | null / null | monetary definition unresolved | null | DATA_LINEAGE_UNRESOLVED |

Only the artifact's two `validatedConfig` entries are promoted. BaseRate's
`0101000` occurs in A/D/M/Q and CPI's total index `0` in A/M/Q; no cycle is
chosen from the table header alone. Corporate AA− and BBB− remain alternatives.
Core CPI exposes both exclusion definitions; production exposes original and
seasonally adjusted groups. M2's configured table advertises historical
average-balance, original-series components, not a uniquely validated current M2
definition. Export alternatives in the catalog do not resolve the absent
configured table. None of these metadata candidates become executable selectors.

LeadingIndex specifically means the cyclical component, not the leading index
level. Its unit is retained exactly as ECOS advertised (`2020=100`); no economic
reinterpretation or normalization is applied. Coverage is metadata observation
coverage, not release/vintage coverage. Both latest-period smoke checks succeeded
and retained no values. All nine entries remain `REVISED_HISTORY`, with
`publishedAt`/`availableFrom` null and historical confirmatory eligibility false.

## Future industry connection and readiness

MarketContext_t and IndustryCycleState_s,t are separate objects. A future study
can condition an industry-market future gap on both, then study the stock-industry
future gap separately. Future returns are labels, never a contemporaneous state
ingredient. Common industry candidates: trailing relative momentum, breadth,
dispersion, earnings/accounting changes, credit and liquidity. Industry-specific
candidates: export mix for exporters; rates/curve for banks; commodity/input costs
for producers; inventory/order cycle for cyclicals. This is a candidate map, not
an implemented/selected feature set or fitted interaction.

Ready: six-axis primitive, immutable visibility mechanics, per-series ECOS fetch,
manual metadata/smoke runner, source schema/status matrix and synthetic verification.
Still needed: exact semantic/native-cycle selections for seven blocked series, historical release
vintages where genuinely available, PIT breadth/concentration and historical industry
taxonomy/membership. Industry outcomes/models remain deliberately outside this PR.

NO HISTORICAL ALPHA OUTCOME WAS COMPUTED

NO MARKET OR INDUSTRY STATE WAS DEFINED USING FUTURE RETURNS

NO REVISED ECOS HISTORY WAS MISREPRESENTED AS PIT_EXACT

NO SEALED STUDY WAS RERUN

KR MARKET CONTEXT IS NOW A REUSABLE FOUNDATION LAYER, NOT A CLAIM OF PREDICTIVE ALPHA
