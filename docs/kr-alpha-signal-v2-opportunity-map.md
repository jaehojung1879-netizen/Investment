# kr-alpha-signal-v2 — opportunity map (three hypotheses)

> **SCOPE CORRECTION (same PR, before merge).** This map first named H2 as "the" first direction for Korean research. That framing is
> withdrawn. The governing architecture is now the **KR Alpha Research Completion Program** (`kr-alpha-atlas`):
> `docs/kr-alpha-atlas-methodology.md`, `docs/kr-alpha-atlas-information-map.md`, `docs/kr-alpha-atlas-execution-roadmap.md`. H2 is one
> **`CANDIDATE_SIGNAL_FAMILY`** inside it: Level 3 interaction `X1_valueByBusinessConfirmation`, registry feature `B08_valueBusinessConfirmation`.
> H1 and H3 also live on as registry features (`H01`, `X3`; `G01`-`G07`, `X4`). The analysis below stays as it was written, so the reasoning
> that produced the narrower choice can be read next to the correction.

Status: `DESIGN_ONLY`. No outcome was computed, inspected or re-read to write this. Every number quoted below is copied from a result already
committed in `docs/results/`, and all of it is **development evidence on outcome-exposed Korean history through 2026-09-14**. None of it confirms
anything. The hypothesis was chosen on mechanism, information content, data readiness and testability. It was not chosen on historical headline return.

This is not Alpha Tournament v2. No configuration grid, model competition or machine-learning blend is proposed.

## 1. What the record already says (evidence map)

| Line of work | What it measured | What it found | What it cannot say |
|---|---|---|---|
| `kr-factor-anatomy-v1` | 11 features, market-relative deciles, PIT top-120 | `bookToMarketProxy` H126 D10−D1 +6.5pp, positive in 80% of years (`BROADLY_POSITIVE_HISTORICAL_ASSOCIATION`); quality levels `NO_CLEAR_MONOTONIC_PATTERN`; `relative126` `CONCENTRATED_IN_SPECIFIC_STRATA` | descriptive only; partial-distribution return basis understates high-dividend names |
| `kr-industry-opportunity-anatomy-v1` | 19 industry features vs industry − 069500 | `REL_MOM_126` IC +0.066, tercile +5.4pp, but IC by year −0.18 to +0.29; leaving the largest constituent out collapses the tercile spread to +0.1pp; `MEDIAN_netIncomeImprovementToAssets` IC −0.185 | ~14 coarse reconstructed industries; overlapping signals; no multiplicity correction |
| `kr-stock-within-industry-anatomy-v1` | within-industry rank vs stock − leave-one-out industry | `bookToMarketProxy` +0.086 (mean/se +2.9, 90% of years positive), `earningsYieldProxy` +0.073 (+2.6); both `SURVIVES` the move from market-relative to industry-relative; `ocfImprovementToAssets` +0.044; momentum `ABSORBED_TO_NEAR_ZERO` | descriptive Spearman means; the reason within-industry value is chosen below is partly this outcome-exposed table, which is disclosed |
| `kr-model-overlay-portfolio-v1` | Ridge on VALUE+QUALITY+CATALYST+RISK and 4 interactions, top-5 book | `DEVELOPMENT_REJECT`: all three H126 model statistics negative, net excess −2.61 | a joint 22-term fit; its own post-mortem says it cannot be decomposed into per-factor findings |
| `kr-integrated-alpha-portfolio-v1` | industry layer + stock layer + market overlay | industry layer development-supported, but regime- and industry-concentrated: D trailed A 2017-2024 and led only in 2025-2026; D did not beat passive over the window (+15.0% vs +20.2%/yr) | one realised regime carried the result |
| `kr-alpha-discovery-tournament-v1` | 120-configuration process | `BLOCKED_BY_DATA_INTEGRITY`, no performance gate evaluated (`docs/kr-alpha-discovery-tournament-v1-forensic-closure.md`) | nothing about alpha |
| `kr-market-risk-model-v1` | equity multiplier only | separate layer (D), not a stock-selection signal | — |
| DART 5% ownership (`dart_ownership_events`) | raw receipts | `BLOCKED_HISTORICAL_DEPTH`: `majorstock.json` serves a rolling two years; collected receipts span 2024-09-24..2026-09-23, 1,285 events over the 119-name current list | no history before 2024-09; no classification of `report_resn` |
| KRX investor flow | collector exists | `BLOCKED_SOURCE` (KRX portal `HTTP 400: LOGOUT`) | nothing |

Two things follow. Price-based leadership has been used heavily (overlay, integrated, tournament) and its support is regime-concentrated. Valuation
within an industry is the most stable association the record holds, and the record also contains a rejected model that used the same accounting
fields. A new study has to say exactly how it differs from that rejection.

## 2. The three hypotheses

### H1 — Industry leadership persistence

- **Mechanism.** Industries whose leadership reflects sustained demand or earnings momentum keep leading over months, because investors under-react
  to slow-moving industry fundamentals. Noise-driven leadership mean-reverts.
- **Inputs.** Industry relative momentum (`REL_MOM_126`), breadth (`BREADTH_ABOVE_MA_126`), and to separate persistence from noise an industry earnings
  trend (median `netIncomeImprovementToAssets` / `ocfImprovementToAssets`). These need v4 industry membership plus DART fundamentals.
- **PIT.** Prices `A`; membership is a reconstruction historically (`DATA_FOUNDATION_INSUFFICIENT_V4`, 22 terminated names unclassified) and observable
  live prospectively; industry earnings medians are sparse (216-334 valid IC dates of 404).
- **Horizon / benchmark.** H63-H126; industry (cap-weighted) − 069500.KS. Stock selection is not credited.
- **Controls.** Market momentum (069500 trend), industry momentum without the earnings condition, and leave-largest-constituent-out.
- **Confounders.** Mega-cap concentration (one constituent carries the tercile spread), the 2025-2026 regime, coarse taxonomy.
- **Falsified if** earnings-confirmed leadership does not beat unconfirmed leadership, or the effect disappears when the largest constituent is removed.
- **Testable now?** Partly. Its refinement (earnings-backed versus price-noise leadership) depends on the thinnest fundamental medians, and the only
  outcome-exposed reading of that refinement is negative (IC −0.185). It also overlaps most with the work that has already been spent: integrated D,
  the tournament's industry-state block. **Information distinctness: low.**

### H2 — Value with business confirmation, within industry

- **Mechanism.** A stock can be cheap against its industry peers for two reasons: the market over-discounts a sound business (mispricing that closes as
  results arrive), or the business is deteriorating and the price is right (the value trap). Requiring that the cheap business is profitable,
  cash-backed and not deteriorating should separate the first from the second. Comparing within an industry removes industry-wide valuation
  differences (banks against software), which are not mispricing.
- **Inputs.** `bookToMarketProxy`, `earningsYieldProxy` (value); `netIncomeToAssets > 0`, `ocfToAssets > 0`, `ocfImprovementToAssets > 0` (confirmation).
  All come from the repaired PIT DART store (receipt-date availability) and the signal-date KRX market cap, plus v4 industry membership.
- **PIT.** Grade `B` (derived, receipt-dated). KR fundamentals are dark in 2015 and partial in 2016; DART coverage is limited to the ever-top-120 issuers.
  Pooled raw coverage among eligible name-dates runs from 75% (book-to-market) down to 51% (OCF improvement), so the per-date readiness gate (§design 4)
  can bind and is measured outcome-free before any evaluation.
- **Horizon / benchmark.** H126 primary, H252 secondary (descriptive), stock − 069500.KS, with an industry/within-industry split.
- **Primary comparison.** Cheap-and-confirmed against cheap-and-unconfirmed (is confirmation information?), and cheap-and-confirmed against 069500.KS
  after costs (is it investable?).
- **Negative controls.** The same confirmation contrast among expensive names (if it is as large there, the effect is generic quality, not value
  confirmation), and a within-date permutation of confirmation among cheap names.
- **Confounders.** Partial distributions understate exactly the high-dividend cheap names (banks, holding companies), which biases against H2. The
  whole-entity book over one issue's cap distorts preferreds and holding companies (preferreds excluded). Cheap names are more likely to delist,
  and terminal economics are unresolved for 22 historical names.
- **Falsified if** confirmation adds nothing within cheap names, the confirmed basket does not beat 069500.KS after costs, the expensive-name control
  is as large, or the whole effect is industry tilt.
- **Testable now?** Yes for the data path and for prospective receipts; the historical development evaluation needs its own authorization.
  **Information distinctness: low as raw information, distinct as construction** (§3).

### H3 — Investor ownership / flow confirmation

- **Mechanism.** An identified large holder crossing or adding to a 5% stake, or sustained foreign and institutional net buying, reveals capital
  committed on information that prices and accounting do not yet show.
- **Inputs.** DART `majorstock.json` receipts (`stkrt`, `stkrt_irds`, `report_resn`, reporter), already collected by `dart_ownership_events` and
  `dart_ownership_universe` (not rebuilt here); KRX per-stock investor-type net buying.
- **PIT.** Ownership: receipt-date PIT, grade `C` — history starts 2024-09-24 because the endpoint serves a rolling two years, and the older filings
  need an official document parser that does not exist. A 5% disclosure is not a daily foreign or institutional flow: it reports only holders at or
  above the 5% line and their reportable changes, and its `report_resn` is raw text with no confirmed classification. Flow: `BLOCKED_SOURCE`.
- **Horizon / benchmark.** H21-H63, stock − 069500.KS.
- **Controls.** Disclosures by passive or index holders (pension, index funds) against active holders; decreases as the mirror image.
- **Confounders.** Event sparsity (1,285 events in two years over 119 names, many of them routine institutional refilings); reporter type is not
  classified; the 2024-2026 window is a single extreme regime.
- **Falsified if** accumulation events do not beat matched non-event names after costs over H21-H63.
- **Testable now?** No historical evaluation is possible: about 18 months of matured events, all in one regime. Prospective collection is possible
  but `dart-ownership-events.yml` is manual-dispatch only. **Information distinctness: high.**

## 3. Duplicate-research gate for H2

| | `kr-model-overlay-portfolio-v1` (`DEVELOPMENT_REJECT`) | `kr-alpha-discovery-tournament-v1` (`BLOCKED`) | kr-alpha-signal-v2 H2 |
|---|---|---|---|
| Raw information | value, quality, catalyst, risk accounting/price fields | the same plus industry state | **the same accounting fields — no new raw information** |
| Construction | Ridge fit of 22 terms incl. four family products | 120 fitted configurations | **no fitted parameter**: within-industry percentiles, a tercile, three sign conditions at zero |
| Comparison frame | market-wide | market-wide, within-industry, residual | **within industry only**, with an industry-versus-stock split of every result |
| Question | does the joint forecast earn alpha? | which process wins? | **does confirmation separate cheap-and-right from cheap-and-wrong?** A conditional contrast with a falsifying control |
| Portfolio | top-5 by prediction | Kelly allocator | 0-5 names only on an authorized calibrated forecast net of cost and 1 SE |

H2 is therefore a different construction of already-measured information, not new information. A negative result closes this construction on
this information set. It is not an invitation to re-weight the same fields, and it does not settle H3.

## 4. Ranking on the brief's six criteria

| Criterion (brief order) | H1 | H2 | H3 |
|---|---|---|---|
| 1. Distinct information | low | low (raw) / distinct (construction) | **high** |
| 2. Economic plausibility | moderate | **high** (value-trap separation is a specific, falsifiable mechanism) | high |
| 3. Data availability / PIT | prices A, membership reconstructed, earnings medians thin | **B, receipt-dated, measurable now** | C (two years), flow E |
| 4. Interpretability | high | **high** (every name has a state and two percentiles) | moderate (raw reason text) |
| 5. Implementation complexity | low-moderate | **low** (existing feature code) | moderate-high (classification, depth) |
| 6. Prospective testability | yes | **yes, from the next PR** | yes, once collection is scheduled; slow to accumulate |

## 5. Selected first direction: H2 (superseded as the program direction; retained as a CANDIDATE_SIGNAL_FAMILY)

H3 wins on the first criterion and loses on every one that decides whether a study can run. It cannot produce development evidence, most names
carry no event in most weeks, and the depth problem is a property of the source. H1 is the least distinct and repeats the regime-concentrated
leadership already spent in three studies. H2 is the one hypothesis whose data path exists end to end. It answers question 4 of the mission
(incremental to simple value and momentum) by its own primary comparison, it can be falsified by a control registered in advance, and it can start
writing honest weekly receipts (`NOT_READY` until a calibration is authorized) as soon as the signal pipeline exists.

H3 is not dropped. It is the next **information** bet, and its first step costs no model: schedule the existing ownership collector so depth
accumulates from now on, and leave the signal design until two or more years of prospective receipts exist. That is a separate, later change.
H1 is parked. Its industry-versus-stock split is kept as an attribution diagnostic inside H2 (§design 6).
