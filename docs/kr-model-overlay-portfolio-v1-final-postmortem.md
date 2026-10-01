# kr-model-overlay-portfolio-v1 — final post-mortem (formal DEVELOPMENT result)

**Seal only. No rerun, no new historical computation, no parameter change.** Every number below is copied from the
sealed artifact `docs/results/kr-model-overlay-portfolio-v1-result.json` or from the descriptive diagnostic
summary archived beside it. Fractions are stored as fractions (0.1026 = 10.26%).

## 0. Identity

| Item | Value |
|---|---|
| Formal run | Actions run `36926769546` (`workflow_dispatch`, `main`), conclusion `success` |
| Execution commit | `89decab393a09381b11cbd16db99e73cc32b2a64` |
| Frozen spec SHA | `563b64ee6f4709a263719669f795ad55e7828e340f082358af1599453253b6fd` |
| Input identity | `233df37ed205cc6b48828121e711417ccf961301dc58aa252430b343db9666a7` |
| Permanent lock | `refs/tags/kr-model-overlay-portfolio-v1-execution-lock-563b64ee…b6fd` → `89decab3…` |
| Primary artifact | `kr-model-overlay-portfolio-v1-primary-36926769546`, id 11194647226, archive `sha256:dcf27477…1c48` |
| Audit artifact | `kr-model-overlay-portfolio-v1-audit-36926769546`, id 11194283481, archive `sha256:03827ed6…98af2` |
| Result file SHA-256 | `2c16e4e121abdd771c103eadce8707484b4092eb501188823aa1ac0726ec272a` |
| Canonical `state` | **`DEVELOPMENT_REJECT`** |
| `scientificStatus` | `DEVELOPMENT_ON_OUTCOME_EXPOSED_HISTORY` (`prospectiveEvidence: false`) |

The two ZIPs reached this change as operator-supplied files because the authoring sandbox cannot reach the Actions
artifact blob host. Both archive digests were recomputed and equal GitHub's; the primary files in both archives are
byte-identical. Provenance is in `docs/results/kr-model-overlay-portfolio-v1-seal-provenance.json`.

---

## A. FORMAL PRIMARY RESULT

### A1. What v1 tested

v1 did **not** test each Korean-market factor independently. It tested one combined, frozen system end to end:

VALUE + QUALITY + CATALYST + RISK/liquidity features → frozen Ridge model (alpha 10, separate fit per horizon,
plus the four pre-specified family interactions) → benchmark-relative H126 / H252 predictions → a 0–5 stock
portfolio (top five eligible names whose H126 prediction is strictly above the fixed round-trip cost, inverse
downside-volatility sizing, 30% single-name cap) → frozen execution, cost (15bp buy / 45bp sell, √-impact, ADV
limits) and benchmark trend/volatility risk-overlay rules, against `069500.KS`.

The question it answered: *does this complete frozen system produce useful benchmark-relative alpha?* A negative
answer is about the system as a whole; it cannot be decomposed into per-factor findings from this result.

### A2. Formal model result (Ridge, walk-forward, expanding annual refits)

| | H126 (primary) | H252 |
|---|---|---|
| evaluation dates | 323 | 243 |
| MSE improvement vs unconditional mean | -0.004479834430418719 | -0.01747129189653065 |
| MSE improvement vs momentum | -0.005242626122747795 | -0.016120378793725458 |
| rank-weighted spread | -0.01449483436548273 | -0.052363254790527204 |

H126: 29,975 eligible matured rows evaluated (33,050 prediction rows; 3,075 ineligible; 49 missing forward
price/delisting; 3,026 pending). H252: 22,400 eligible, 6,117 ineligible of 28,517. Fits: 13 annual folds
(H126 cutoffs 2020-01-03 … 2026-01-02, 7 folds; H252 cutoffs 2021-01-08 … 2026-01-02, 6 folds), 39 fit and 39
prediction calls in total, 146,400 label/target calls.

### A3. Formal portfolio result (full path, net of costs, zero-rate cash)

| Metric | Value |
|---|---|
| sessions | 1633 |
| net return | 0.9147460427669039 |
| gross return | 1.015567002842177 |
| benchmark (069500.KS) return | 3.5283951784999132 |
| **net excess** | **-2.6136491357330094** |
| CAGR | 0.10260595742780243 |
| annual volatility | 0.2727442145185811 |
| Sharpe (zero cash rate) | 0.5038064089892271 |
| Sortino (zero cash rate) | 0.7285147848642821 |
| max drawdown | -0.3905257917380852 |
| turnover | 15.867331598432608 |
| cost drag | 0.10082096007527319 |
| average cash | 0.1758581729075142 |
| average holdings | 4.88426209430496 |
| chronological-half excess | -0.5174549341325615, -1.0153036890570903 |

Also stored: daily hit rate 0.4696876913655848, downside volatility 0.18861701388090907, max single-security
weight 0.3715389371441382.

### A4. Why `DEVELOPMENT_REJECT` (frozen decision semantics only)

`kr_model_portfolio_execution.development_state` (spec `developmentState`):

* `CANDIDATE` needs **all** of: H126 MSE-vs-mean > 0, MSE-vs-momentum > 0, rank-weighted spread > 0, full net
  excess > 0, and both chronological halves > 0.
* `REJECT` if **all three** H126 model signs are non-positive **or** full net excess is non-positive.
* Otherwise `INCONCLUSIVE`.

Both REJECT triggers fired independently: all three H126 model statistics are negative (-0.00448, -0.00524,
-0.01449), and full net excess is -2.6136. Both chronological halves are also negative, so even the condition
that distinguishes CANDIDATE from INCONCLUSIVE failed. No secondary reading can rescue the state
(`secondaryCannotRescue: true`), the result is a development point-estimate screen with no significance claim,
and a substantive result closes the preregistration.

### A5. What this result does not prove

* It does not prove Korean equities are uninvestable, or that benchmark-relative alpha cannot exist there.
* It does not prove all value factors, or all quality factors, fail. The three VALUE and three QUALITY inputs
  here are specific accounting proxies (`ISSUE_CAP_ACCOUNTING_PROXY`) with documented coverage limits, entered
  in one linear model with 22 other terms.
* It does not prove liquidity (`logAdv60`) is alpha, or is not. It was one RISK-family input in a joint fit.
* It says nothing about a US version: v1 is KR-only.
* It does not authorize changing any parameter, feature, threshold or horizon and rerunning v1. The study is
  closed; any further work is a new, separately preregistered study.
* It is outcome-exposed history, not prospective evidence, and the portfolio carries acknowledged limitations
  (no PIT sector history or sector cap, zero cash yield, partial-distribution handling in the inherited index).

---

## B. PRESPECIFIED DESCRIPTIVE DIAGNOSTICS (reported, not used)

Source: `docs/results/kr-model-overlay-portfolio-v1-diagnostic-summary.json.gz` (gzip of the artifact's
`diagnostics/summary.json`, uncompressed SHA-256 `db9f2b7a…0be4`, 58,463,505 bytes) and the primary file's
`folds`. Its own header: `status: DESCRIPTIVE_ONLY`, `affectsPrimary: false`, `canRescuePrimary: false`,
`canAuthorizeRerun: false`. None of it can alter the state, and no new outcome analysis was run for this
document.

**Contents.** Annual Ridge coefficients, intercept, training dates/rows, training missingness and transform
snapshots for each of the 13 folds (in the primary file); concordance; cost stress at 2× and 3×; equal-weight
and momentum portfolio baselines; per-stock/date prediction records (realized-label-free: mean, momentum,
Ridge and challenger predictions, rank, VALUE / QUALITY / CATALYST / RISK family scores, the four interaction
contributions, investability and missingness/source-quality flags); and 29,975 valuation-convergence rows.

* **Omitted features:** none in any of the 13 folds. **Challenger errors:** none (`challengerError: null` in all
  folds). Training eligibility status in every fold: `MATURED_AND_ELIGIBLE_AND_CORE_OBSERVED`.
* **Challenger concordance** (correlation of the Ridge prediction with the frozen gradient-boosting
  challenger's prediction): H126 0.4167695189082535; H252 0.3877691076647435. Only the correlation is
  archived; no challenger verdict was computed and none is claimed.
* **Cost stress** (same path, costs ×2 / ×3): net excess -2.7893627770644565 / -2.949120992616537; net return
  0.7390324014354568 / 0.5792741858833763; CAGR 0.086762010508457 / 0.071128440410692; max drawdown
  -0.40059182549698136 / -0.4161919622435394; cost drag 0.19086262125763565 / 0.2712215631812105. Chronological
  halves stay negative in both (-0.5525, -1.1360 and -0.5859, -1.2511).
* **Equal-weight baseline** (same selected names): net excess -2.8007890698950364, net return
  0.7276061086048766, CAGR 0.08568529399773661, max drawdown -0.4008699072192605.
* **Momentum baseline** (same cost/risk rules): net excess -3.3046552932854887, net return
  0.22373988521442456, CAGR 0.030826530099567817, average cash
  0.904182261667636, average holdings 0.5407225964482547 (the book was mostly cash).
* **Valuation convergence:** 29,975 descriptive rows (entry/exit cheapness, log book growth, log multiple
  expansion, fundamental-improved and multiple-expanded flags). Each is flagged `priceMechanical: true` and
  `notACompleteShareholderReturnDecomposition: true`. They were archived, not aggregated, here.
* **Eligibility / missingness:** per-year eligibility and missing-raw-feature counts are in the primary file's
  `model.*.fullEligibilityByYear`; family scores and interaction contributions are per prediction record.
* **Portfolio path diagnostics:** the primary `portfolio` block above plus the baselines and cost stress.

Reading rule: B is context for A. A diagnostic that looks favourable or unfavourable changes nothing.

---

## C. POST-HOC / EXPLORATORY QUESTIONS FOR FUTURE WORK

### Next exploratory research: KR Factor Anatomy

This is motivation only; nothing here is implemented or evaluated by this change.

v1 answered *"does this complete frozen system generate useful benchmark-relative alpha?"* (no, on this
development history). It did **not** answer *"which individual characteristics have historically been associated
with benchmark-relative returns in the Korean equity market, in which regimes and subgroups?"*

Korean history through 2026-09-14 is already outcome-exposed. Everything below must therefore remain
**EXPLORATORY / DEVELOPMENT / HYPOTHESIS-GENERATING**; anything that looks promising needs a new preregistration
and prospective or otherwise independent confirmation, with the multiplicity cost counted.

Candidate questions (listed, not answered):

* standalone decile/quantile behaviour of each raw feature
* VALUE / QUALITY / CATALYST family-level behaviour
* annual and regime stability
* large vs smaller capitalization and liquidity strata
* whether liquidity is independent alpha or a large-cap proxy
* earnings/fundamental improvement vs subsequent market re-rating
* "fundamentals up, price down" cases
* cheap + high profitability vs cheap + low profitability
* cheap + improving fundamentals vs cheap + deteriorating fundamentals
* sector heterogeneity
* bank/financial-sector behaviour, if PIT sector history can be made valid
* concrete case studies (e.g. Samsung Electronics, SK Hynix) using exact historical frozen observations,
  predictions, benchmark returns and realized relative returns

## Closure

The committed result file is the repository's one-shot guard: the runner (`SUBSTANTIVE_RESULT_ALREADY_CLOSED_V1`)
and the workflow (`V1_ALREADY_CLOSED`) refuse any further execution while it exists, and the permanent lock tag
is never updated or deleted. The frozen specification, harness, workflow, authorization and pinned test file are
byte-unchanged by this change.
