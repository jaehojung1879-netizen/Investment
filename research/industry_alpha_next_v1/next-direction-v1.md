# Next industry research direction — v1 (design only)

Status: **DESIGN_ONLY**. Nothing here reads an outcome, fits a model, collects data or changes a sealed run, the Atlas
closure, a source-use decision or an outcome authorisation. Every number quoted below is copied from an already
committed artifact, which is named beside it.

**Scope correction.** #300's `industry-ocfyield-conditional-v1` NO_GO is specific to one underpowered conditional OCF-yield
hypothesis on the KR 14-industry Top120 panel. It says nothing about industry research in general, about analyst-style
sector-cycle analysis, or about the US industry lane.

## 1. Source coverage matrix

Status words: `RETAINED_PIT` (values plus a retained known-at timestamp), `RETAINED_RECONSTRUCTED` (retained but timing or
membership partly inferred), `RETAINED_NOT_ELIGIBLE` (retained, fails an existing eligibility gate),
`ACQUIRABLE_NOT_RETAINED`, `BLOCKED_ACCESS` (exists, unreachable from CI), `UNAVAILABLE_FREE` (no free historical PIT
source found).

| Data family | KR | US |
|---|---|---|
| Dated industry classification | `RETAINED_RECONSTRUCTED`: v4 KIND/KSIC crosswalk to 14 groups; 69,756 of 73,200 Top120 name-dates classified, of which 54,173 are "no change" inferences; 22 terminated securities unclassified (`data-eligibility.md`) | Dated third-party labels: 195 commit-dated S&P 500 snapshots, 11 GICS sectors, but the 2023-03-07 snapshot uses 123 sub-industry labels (`sp500-snapshot-sectors.json.gz`). Not provider-certified. Filing-time SIC is `BLOCKED_ACCESS` (SEC unreachable from Actions) |
| Quarterly earnings and balance sheet | `RETAINED_PIT`: DART receipt-dated filings for the Top120 ever-members; annual reports from fiscal 2015, quarterlies from fiscal 2016 (fiscal-2015 quarterlies only via original XBRL, not yet landed); financials rarely state revenue or operating income; amendments sometimes served in place of originals (AGENTS v2.33) | `RETAINED_PIT`: Finnhub 10-Q/10-K store, 779 tickers 2011–2026, SEC accepted date as `availableFrom`. Exact-concept rule costs coverage: the us-capital-allocation audit's four-feature funnel is 45–80% not measured by sector (Real Estate and Utilities worst); OperatingIncomeLoss/Assets coverage by sector is NOT yet measured. Use rights not verified |
| Preliminary or press-release earnings | `ACQUIRABLE_NOT_RETAINED`: DART 잠정실적 공정공시 in `list.json` (only KR22 listings retained) | `BLOCKED_ACCESS`: 8-K earnings releases (SEC) |
| Consensus estimates and revisions | `UNAVAILABLE_FREE`: FnGuide/FnSpace ToS-blocked | `UNAVAILABLE_FREE`: no free historical PIT panel; Finnhub sells historical estimates separately (inventory v2.23) |
| Real-economy cycle by industry | `ACQUIRABLE_NOT_RETAINED`: KOSIS 광공업생산 by KSIC, customs exports by HS chapter; retained ECOS evidence is the base rate, 3-year rates, CPI, all-industry IP and the leading index, all `REVISED_HISTORY` | `ACQUIRABLE_NOT_RETAINED`: Fed G.17 production and capacity by NAICS, Census M3 shipments/orders/inventories, via FRED/ALFRED; per-series vintage coverage unverified (10 of 28 macro panel columns had no ALFRED vintages, AGENTS v2.9) |
| Industry momentum, breadth, concentration | Computed in the sealed KR industry anatomy; outcome-exposed (REL_MOM_126 H126 IC +0.066; TOP1_CAP_SHARE negative in all six cells) | Not computed. The price panel never priced 212 departed identities, so survivor-only industry price states are `RETAINED_NOT_ELIGIBLE` |
| Investable industry returns (sector ETFs) | `ACQUIRABLE_NOT_RETAINED` (KODEX sector ETFs) | `ACQUIRABLE_NOT_RETAINED` (sector SPDRs) |
| Stock shareholder total return | `RETAINED_NOT_ELIGIBLE`: partial distributions; 22 terminated securities have no total-return lineage | `RETAINED_NOT_ELIGIBLE`: survivor-only sample, 0 failed or acquired companies priced (AGENTS v2.27) |
| Segments and supply-chain links | `UNAVAILABLE_FREE` as structured data. Business-section text is retained for the KR22 only | `UNAVAILABLE_FREE` (needs SEC XBRL segments, blocked) |

## 2. Five questions that must not be merged

1. **Historical association** of an industry state with later industry-minus-market return. In KR this is done, sealed and
   outcome-exposed (industry anatomy; Atlas closed Korean history with zero nominations).
2. **Prediction of future industry business performance** (earnings, revenue). This is untested in both regions, and it
   does not need eligible shareholder returns.
3. **Analyst earnings revisions.** These cannot be studied with current data in either region; only a surprise measured
   against a firm's own history is possible.
4. **Prediction of future industry-minus-market return.** KR history is exposed and closed. US return data are ineligible.
5. **Incremental benefit to stock selection.** The integrated KR D audit shows D beat A only after 2024, concentrated in
   one industry (ELECTRONICS_ELECTRICAL 59.5% of gross). That is development evidence, not a test.

Question 2 is the cheapest open question with high information. It is also the prerequisite for 5: if industry peers carry
no information about a firm's own business results, an industry layer has little to add to stock selection beyond price.

## 3. Minimum timestamped evidence per signal family

| Family | Minimum record | Known-at rule | KR | US |
|---|---|---|---|---|
| Earnings expectation change or surprise | security, fiscal period, value, first-publication timestamp of the ORIGINAL filing | value usable after its own receipt/acceptance date; amendments are separate records, never overwrites | receipt dates retained; preliminary releases acquirable | accepted dates retained; 8-K blocked |
| Real-economy order/production/inventory/capacity cycle | series, reference period, value, release date, vintage, plus a dated crosswalk to the securities taxonomy | the vintage published by t only | not retained; vintage history unknown | acquirable with ALFRED vintages; coverage unverified |
| Relative price momentum, breadth, concentration | dated membership, PIT prices, share counts | strictly past sessions | retained, classification reconstructed | dated membership; prices survivor-only |

## 4. Dated, versioned taxonomy (two layers, never pooled)

- **L1, market taxonomy.**
  - **KR:** `KRX_KIND_INDUSTRY`, the v4 crosswalk, edition-pinned.
  - **US:** `GICS_SECTOR_AS_PUBLISHED` from the dated snapshots. The commit timestamp bounds when a label was known. Use
    sector level only, and respect the edition boundaries: Real Estate was split out in 2016-09 and Communication Services
    re-formed in 2018-09. Labels are never remapped backwards. The 2023-03-07 sub-industry snapshot is a different level;
    it is ineligible at sector level and is never mapped.
- **L2, economic supply-chain taxonomy.** These are the statistical classifications that real-economy sources use: NAICS-3
  for G.17 and M3, KSIC-2 for 광공업생산, and HS chapter for exports.
  - **Linking to securities:** only through dated, filing-time statements. For KR, that is the KSIC code stated in the DART
    annual report's 회사의 개요. For US, that is the SIC code at filing, once accessible.
  - **Crosswalk:** kept in a versioned table with fields `(taxonomy_id, version, from_code, to_code, weight, valid_from,
    valid_to, published_at, source, sha256)`.
- **Themes** (AI, batteries, semiconductors supply chain) are not taxonomy nodes. A theme may exist only as a dated,
  documented set of L2 links with its own `published_at`. Today's theme membership or today's company membership is never
  projected backwards.
- **Row contract:** the row contract in `data-eligibility.md` applies unchanged.

## 5. Selected first hypothesis — `us-intra-industry-earnings-transfer-v1`

**Question.** Do same-sector peers' already-filed results for a fiscal quarter predict a firm's own not-yet-filed result for
that quarter, beyond the firm's own history and beyond the market-wide early-filer signal?

**Why this one.**
- The target is a business outcome, so it does not depend on the ineligible shareholder-return data.
- The cross-section is about 500 firms in 11 sectors.
- Targets do not overlap from quarter to quarter.
- Timestamps come from SEC acceptance dates.
- It measures directly whether industry carries firm-relevant fundamental information.

### Design

| Element | Fixed choice |
|---|---|
| Universe at t | S&P 500 members in the latest dated snapshot strictly before t |
| Sector | The snapshot's 11-sector label. Snapshot dates using another level are ineligible, not remapped |
| Quarters | Fiscal Q1–Q3 (10-Q) only, so no Q4 is derived from a 10-K; 2013Q1–2026Q2 |
| Evaluation date | t(q) = fiscal quarter-end + 30 calendar days. Fixed, not tuned |
| Early peers | Same-sector members whose ORIGINAL 10-Q for q was accepted strictly before t |
| Late firms | Members with no accepted q filing at t (absence is known at t) |
| Predictor X | Leave-one-out sector median, over early peers, of (OI_q − OI_{q−4}) / TotalAssets_{q−4}, from first-filed values only. Needs ≥ 3 early peers |
| Target Y | The same quantity for the late firm, from its own original q filing |
| Baseline B | The late firm's latest filed value of the same quantity (q−1), its q−4 value, and the early-filer median over all OTHER sectors |
| Statistic | Per quarter, Spearman partial correlation of Y with X given B, across late firms; mean over quarters; one-sided |
| Inference | Quarters do not overlap. A dependence-robust interval on the quarter series, calibrated on synthetic data before any outcome is read. One primary slot, so no multiplicity |
| Effect of interest | A partial rank correlation of 0.05, fixed now |

### Negative controls

- **Permuted sectors:** sector labels permuted within each quarter, keeping group sizes. The incremental effect should be
  about zero.
- **Stale information:** peers' q−4 values used in place of their q values must not reproduce the effect beyond the baseline.
- **Leakage canary:** a synthetic future-filing leak must be detected by the harness.

### Missingness and coverage

- Late firms that never file q (acquired or delisted) are counted.
- A worst-plausible bound, which assigns them the bottom of the quarter's Y distribution, must keep the sign.
- Sectors where the required fields cover less than 60% of members are excluded by a rule fixed before any outcome is read.

### Stop conditions

1. **Before outcomes:** support is below the floor, i.e. fewer than 30 quarters each having ≥ 6 sectors with ≥ 3 early and
   ≥ 3 late eligible firms, or calibrated power at 0.05 is below 80%. Then the result is NO_GO with no outcome read.
2. **After authorised execution:** the interval contains zero, or the point estimate is below 0.05. Then the hypothesis is
   closed, with no switch to revenue, another t, Q4, another taxonomy or a KR rescue.

### What a result would and would not mean

- **Positive:** peers carry incremental fundamental information about a firm's own results. This justifies building an
  industry-information feature for stock selection.
- **Not a return claim.** 8-K releases may already have made the firm's result public before t, so a separate return test
  is still needed.

### Prerequisites outside engineering

- Owner clearance of Finnhub use and retention.
- The license of the snapshot dataset.
- An exact-hash execution authorisation.
- A KR replication (DART receipt dates, v4 reconstructed taxonomy, smaller cross-section) only as a separately registered
  study, after this one.

## 6. Later, separately authorised test of incremental net alpha (M+I+S vs M+S)

- **Sample:** identical eligible samples, i.e. the intersection mask of both arms on the same dates, names, calendar,
  execution engine and costs. Industry is the only switch. The market layer and the stock model are identical objects in
  both arms, which a spy proves from the call arguments.
- **Target:** net-of-cost path difference at 1×, 2× and 3× costs, H126 primary and H252 secondary. The interval is
  calibrated on the paired path, and the two horizons are corrected with Holm.
- **Turnover:** turnover is attributed separately to names replaced and to weights retargeted.
- **Market beta:** daily-path beta of each arm is reported. The difference is also read against a beta-matched passive
  path, which is an ex-post diagnostic, not a control.
- **Concentration:**
  - KR: Samsung Electronics and SK Hynix excluded from the investable set before selection.
  - US: the five largest caps excluded before selection.
  - Top-1 industry weight and the industry HHI are reported.
  - Industry ON vs OFF is never read off a book that is more than 60% one industry without that being stated.
- **Data:** shareholder-return eligibility (KR terminal economics, US survivorship) must pass first. History is
  outcome-exposed in KR, so confirmation is prospective.

## 7. Known, unknown, structurally impossible today

- **Known:**
  - KR: small positive descriptive industry-price associations, outcome-exposed.
  - KR: within-industry value ranks lean positive, outcome-exposed.
  - KR: integrated D is concentrated in one industry and only post-2024.
  - US: receipt-timestamped filings and dated 11-sector labels exist.
- **Unknown:**
  - Whether industry carries fundamental information about firms' results in either region.
  - US vintage coverage of industry-level real-economy series.
  - Finnhub and snapshot use rights.
- **Structurally impossible with current data:**
  - Analyst revision signals in either region.
  - Segment-weighted or supply-chain exposure.
  - Pre-2023 US SIC history from the CI environment.
  - Eligible shareholder-return tests in either region before terminal-economics and survivorship repair.

## 8. ONE Codex engineering task

**`us-intra-industry-earnings-transfer-v1` outcome-free readiness.** New directory only. No target value is read.

- **`protocol.json`:** freezes every choice in §5, including t = quarter-end + 30 days, Q1–Q3, the ≥ 3 peer floor, the 60%
  coverage rule, the support floor and the 0.05 effect of interest. All execution thresholds that the owner has not approved
  stay null.
- **Readiness builder:** reads the pinned Finnhub PIT store (`signal-history` commit pinned by hash) and
  `sp500-snapshot-sectors.json.gz`. Per fiscal quarter and sector it reports:
  - members at t;
  - early and late counts at t;
  - late firms with ≥ 3 early peers;
  - coverage of OperatingIncomeLoss and Assets in ORIGINAL 10-Qs filed before t, for q−1, q−4 and the early peers;
  - snapshot age and level per date;
  - identity-join failures.

  It writes `readiness.json` with the support-floor verdict. Only predictor-side fields known at t are read; the late firms'
  own q filings are never opened.
- **Tests:**
  - A spy that raises if any late firm's q-filing value is accessed.
  - Rejection of a mixed-level snapshot.
  - Original-vs-amendment selection.
  - Leave-one-out exclusion of the evaluated firm.
  - A deterministic double run producing identical bytes.
- **Acceptance:** `ruff`, `compileall` and the new tests pass, and exact-head CI is green. The output is GO or NO_GO for
  support only. It is not authorisation to read targets.
