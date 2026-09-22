# KR macro regime design — v1

> **Design only. No threshold or weight is fitted or optimized in this
> document, and no production code changes.** This proposes the AXIS
> structure a future KR-specific regime engine would use, built from an
> audit of what data genuinely exists today versus what is configured but
> unfetched versus what is not available anywhere in this pipeline.

## Why this is not a copy of `regime.py`'s six axes

`regime.py`'s current six axes (growth, inflation, liquidity, financial
conditions, risk appetite, earnings/credit) were built for a
large-economy, reserve-currency, domestically-driven macro reading. Korea
is a small, open, export-heavy economy where external financial
conditions and the currency are not a secondary adjustment — they are
often the dominant channel. This design does not force Korea into the same
six-axis shape; it proposes a structure suited to Korea's own economy,
while explicitly keeping the genuinely global inputs Korea is exposed to
identically to how the US is (Section 8 of
`docs/us-alpha-research-design-v1.md`'s sibling document,
`docs/regional-alpha-research-separation-v1.md` Section 8-9).

## Proposed axes

| Axis | Candidate inputs | Domestic / Global | PIT source | History depth | Current availability |
|---|---|---|---|---|---|
| **domesticRates** | BOK base rate; Korea 3M; Korea 10Y; KR 10Y-3M curve | Domestic | BOK ECOS (base rate); FRED via OECD (`Korea_10Y`=`IRLTLT01KRM156N`, `Korea_3M`=`IR3TIB01KRM156N`) | FRED series available back to well before 2013 (OECD long-run series) | **Korea_10Y/Korea_3M: already collected, currently display-only** (`macro.py:_kr_indicators`). BOK base rate itself: `ECOS BaseRate=722Y001`, **configured, never fetched** (see Data Gap table below) |
| **growth** | Industrial production; exports; leading index | Domestic | BOK ECOS | Monthly, ECOS history typically extends well before 2013 where the series exists | **`DATA_LINEAGE_UNRESOLVED`** — `IndustrialProduction=901Y033`, `Exports=901Y011`, `LeadingIndex=901Y067` are configured, none fetched |
| **inflation** | CPI; core CPI | Domestic | BOK ECOS | Monthly, long history | **`DATA_LINEAGE_UNRESOLVED`** — `CPI=901Y009`, `CoreCPI=901Y010` configured, never fetched |
| **domesticLiquidity** | M2; corporate bond spread | Domestic | BOK ECOS | Monthly | **`DATA_LINEAGE_UNRESOLVED`**, and see the caveat below — `M2=101Y004` configured, never fetched; `KTB_3Y` and `CorpBond_3Y` are BOTH configured to the identical ECOS series id `817Y002`, which cannot be correct for two economically distinct series (a 3-year Treasury yield and a corporate bond spread), and is itself evidence the ECOS block is an unverified placeholder set exactly as `config.json`'s own trailing note says |
| **externalFinancialConditions** | USD/KRW level and change; Broad Dollar; US real 10Y; Fed Funds; US 2Y/10Y; VIX; HY spread | **Global, but a first-class KR axis, not an afterthought** | USD/KRW via FRED (`DEXKOUS`); the rest already collected as US `regime.py` inputs | Daily/long history, all already flowing today | **USD/KRW: already collected, currently display-only.** The US-side inputs (Broad_Dollar, Real_10Y, VIX, HY_Spread) are already collected AND already used — by `regime.py`'s US classification — so reusing them here is zero incremental cost, not a new dependency |
| **riskAppetite** | VIX; KR-specific breadth or volatility measure if one is built | Global (VIX) with a domestic option open | VIX already collected; no KR-specific volatility index currently collected | n/a for a KR-specific addition | VIX: already collected, already used in the US engine, reusable here directly |

`FLOOR`/`CEILING`-style parameters, axis weights, and regime-label
thresholds are **not** proposed with specific numeric values in this
document — inventing untested numbers here would violate Section 24's own
instruction not to optimize thresholds/weights in this study.

## Data gap table (measured, not assumed)

| Series | Config key | Status | Evidence |
|---|---|---|---|
| Korea 10Y | `fred.KR.Korea_10Y` = `IRLTLT01KRM156N` | **Collected, display-only** | `datafeed.py:fetch_macro` fetches all of `cfg.fred_series` (both regions flattened, `config.py:56-62`); `macro.py:_kr_indicators` (`macro.py:76-85`) is the only reader |
| Korea 3M | `fred.KR.Korea_3M` = `IR3TIB01KRM156N` | **Collected, display-only** | same |
| USD/KRW | `fred.KR.USD_KRW` = `DEXKOUS` | **Collected, display-only** | same |
| BOK base rate | `ecos.KR.BaseRate` = `722Y001` | **`DATA_LINEAGE_UNRESOLVED`** | No ECOS fetch function exists anywhere in `pipeline/*.py` (exhaustive grep); `cfg.ecos_regions`/`cfg.has_ecos` load the config but the only consumer is a boolean diagnostic flag (`build.py:1145`) |
| KTB 3Y | `ecos.KR.KTB_3Y` = `817Y002` | **`DATA_LINEAGE_UNRESOLVED`, and duplicate-ID caveat** | Same as above; also shares its series id with `CorpBond_3Y` below |
| Corporate bond spread | `ecos.KR.CorpBond_3Y` = `817Y002` | **`DATA_LINEAGE_UNRESOLVED`, and duplicate-ID caveat** | Identical series id to `KTB_3Y` — cannot both be correct as stated; `config.json`'s own note already calls these "placeholders to be verified against BOK ECOS before a live KR macro build" |
| CPI / Core CPI | `ecos.KR.CPI`/`CoreCPI` = `901Y009`/`901Y010` | **`DATA_LINEAGE_UNRESOLVED`** | Not fetched |
| Industrial production | `ecos.KR.IndustrialProduction` = `901Y033` | **`DATA_LINEAGE_UNRESOLVED`** | Not fetched |
| Leading index | `ecos.KR.LeadingIndex` = `901Y067` | **`DATA_LINEAGE_UNRESOLVED`** | Not fetched |
| Exports | `ecos.KR.Exports` = `901Y011` | **`DATA_LINEAGE_UNRESOLVED`** | Not fetched |
| M2 | `ecos.KR.M2` = `101Y004` | **`DATA_LINEAGE_UNRESOLVED`** | Not fetched |
| Semiconductor exports specifically | — | **Not available anywhere** | No series id configured at all; would need a new source (e.g. KITA trade statistics), not merely wiring an existing key |
| Manufacturing PMI-equivalent | — | **Not available anywhere** | Not configured |
| Employment | — | **Not available anywhere** | Not configured for KR |
| Consumption | — | **Not available anywhere** | Not configured for KR |
| GDP-related high-frequency indicators | — | **Not available anywhere** | Not configured for KR |
| PPI | — | **Not available anywhere** | Not configured for KR (US has `Headline_PPI`/`Core_PPI`; no KR equivalent series id exists in `config.json`) |
| Credit growth, CD/CP spread | — | **Not available anywhere** | Not configured for KR |

No fallback field is invented for any `DATA_LINEAGE_UNRESOLVED` or
not-available row. A future KR regime implementation either (a) wires the
ECOS fetch path and verifies each series id against BOK's own
documentation before trusting it — the `KTB_3Y`/`CorpBond_3Y` duplicate
must be resolved first, not worked around — or (b) sources an alternative
vendor for a given series, or (c) runs the KR regime with fewer axes
populated, degrading confidence honestly (exactly as `regime.py`'s own
`build()` already does for missing US series: "Missing series lower
coverage/confidence rather than defaulting to neutral or bullish").

## What this design explicitly does not do

- Does not implement an ECOS fetch function.
- Does not resolve the `KTB_3Y`/`CorpBond_3Y` duplicate series id (flagged
  for a human or a future PR to verify against BOK's own documentation).
- Does not assign axis weights, regime-label thresholds, or a risk-budget
  table — `regime.py`'s existing `_REGIME_BUDGET` structure is a template
  for the SHAPE such a table would take, not a value to copy.
- Does not change `regime.py`, `macro.py`, or any production code.
- Does not backtest any KR regime construction against historical KR
  portfolio returns.

## Relationship to KR alpha research

Per `docs/regional-alpha-research-separation-v1.md` Section 10, macro never
adds to single-stock alpha in either region. A future KR regime engine
would drive a KR-specific risk-budget/equity-exposure layer, structurally
identical in ROLE to `regime.py`'s existing budget layer, but built from
Korea's own domestic and externally-relevant inputs rather than reusing
the US regime label for KR capital. This is independent of, and not a
precondition for, `kr-alpha-discovery-v1`
(`docs/kr-alpha-research-design-v1.md`), which is stock-selection research
and does not require a KR-specific macro regime to proceed — see
`docs/regional-alpha-research-separation-v1.md` Section 29's CASE A
classification.
