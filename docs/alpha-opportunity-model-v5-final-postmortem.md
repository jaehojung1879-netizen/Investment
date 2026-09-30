# alpha-opportunity-model-v5 — final post-mortem and result seal

This document archives and interprets the ONE authorized formal execution of `alpha-opportunity-model-v5`. It is
not a new experiment, not v6, and not a rerun. Every number below is copied from the archived artifacts in
`docs/results/`; nothing was recomputed, cut or searched after reading the result.

## 0. Identity of the sealed execution

| Item | Value |
| --- | --- |
| GitHub Actions run | `36660521285` ("Alpha opportunity model v5 execution", run number 2, `workflow_dispatch`, `main`, conclusion `success`) |
| Execution commit | `47df596c42975902b4e4983e068fb852f97c467f` (merge of PR #176) |
| Frozen spec digest | `d0f1aaf50d9629ba2f8a0a9802cd4ebd653018028ee97b2746f9e50703741e75` |
| Diagnostic spec digest | `15a855faae2b7a1ae34aea703a8e0b996b363fd8359210bb43ab308945048f9a` |
| Primary artifact | `alpha-opportunity-model-v5-result`, artifact ID `11074672605`, archive digest `sha256:ca9bd57fb1093979438461783a9fd748f1acdec4ac989744b8c9905f67164eca` |
| Diagnostics artifact | `alpha-opportunity-model-v5-diagnostics`, artifact ID `11074762247`, archive digest `sha256:4c07b3c83fee8f9f3f27c842eff11391ad27ed34a621cf53177d55c5c001fbec` |
| Primary result file SHA-256 | `e06aa3fe17fb5986dd7e6a36272cc1bda59f78f97bfa4e6efaa68d1359d020d4` |
| Internal substantive-result SHA-256 | `9f5f84f4632847a74d21e29d22b46de9695490c2e4ad55ca1b75a0673e90c135` (recomputed by `substantive_digest` on the archived bytes: equal) |
| Diagnostic models / summary / references | `b43d7d42…db98` / `37c6d899…304d` / `cf580b0c…7d2e` (full values in the table in section 9) |

The diagnostic references state `status = DIAGNOSTICS_COMPLETE`, `changesPrimary = false`, `authorizesRetry = false`
and cite the primary file and substantive digests above. The result records `identity.unchangedThroughout = true`,
sealed signal-history commit `4ea107ed0cde289f0a049a65ff13d2441a786710`, KR accounting source commit
`fb6e83743fd8cdba647d1522a4645b662a9d5647`, foundation status `PARTIALLY_REPAIRED`, sample status
`HISTORICAL_DISCOVERY_ON_AN_EXPOSED_SAMPLE`, 714 scheduled signal dates and 85,132 tradable name-dates. The
archive transfer bytes were verified against `SHA256SUMS.txt` before anything was committed.

## A. Formal confirmatory result

**The preregistered overall result is `INCONCLUSIVE`.** It is not PASS, not FAIL, not evidence that true Alpha is
zero, and not evidence of a profitable portfolio. `substantiveResult = true`, `closesPreregistration = true`,
`promotionEligible = false`. KR H21 = `INCONCLUSIVE`, KR H126 = `INCONCLUSIVE`, US = `BLOCKED_BY_DATA_INTEGRITY`
(no US model was fitted). The economic tier is `NOT_EVALUATED` at both horizons (`PRIMARY_CLAIM_NOT_PASS`).

Confirmatory conjuncts (estimate, 95% interval as recorded, registered state). Positive MSE improvement means B4 beats the
comparator.

### H21 — 552 signal weeks (78 required), 63,851 evaluation rows

| Conjunct | Estimate | Interval | State |
| --- | --- | --- | --- |
| B4 vs B0 paired MSE improvement | -2.3239352942602633e-05 | [-4.8264454537311934e-05, 1.7857486521066715e-06] | CONTAINS_ZERO |
| B4 vs B2 paired MSE improvement | -2.334130036637733e-05 | [-7.1977384668034e-05, 2.529478393527934e-05] | CONTAINS_ZERO |
| B4 rank-weighted spread | -0.00028708131802944426 | [-0.006533229015858956, 0.005959066379800067] | CONTAINS_ZERO |

All three point estimates are negative. The B4-vs-B0 upper bound is close to zero (1.79e-06) but the registered state is
`CONTAINS_ZERO`. Descriptive Rank IC (role `DESCRIPTIVE_ONLY_NEVER_A_GATE`): -0.02666954670654461, interval
[-0.05315064136208081, -0.00018845205100840798] over 552 dates. That descriptive interval does not contain zero, on the
negative side. It is reported exactly as recorded, cannot gate or change the primary status, and is not a FAIL: the
frozen primary verdict is `INCONCLUSIVE`.

Conservative reading: the registered evidence did not establish reliable H21 cross-sectional predictive value for this
frozen information set.

### H126 — 530 signal weeks (312 required), 61,223 evaluation rows

| Conjunct | Estimate | Interval | State |
| --- | --- | --- | --- |
| B4 vs B0 paired MSE improvement | 0.0005524326788934506 | [-0.007401682263479424, 0.008506547621266325] | CONTAINS_ZERO |
| B4 vs B2 paired MSE improvement | 0.0005339386075866514 | [-0.005627125175705776, 0.0066950023908790785] | CONTAINS_ZERO |
| B4 rank-weighted spread | 0.012213196127168391 | [-0.04750118371499561, 0.07192757596933239] | CONTAINS_ZERO |

Descriptive Rank IC: 0.05548959123876622, interval [-0.1029807249015166, 0.21395990737904902] over 530 dates.

Reading: all three H126 confirmatory point estimates are directionally favourable and all three registered intervals
contain zero. Robust confirmatory Alpha evidence was therefore NOT established. This does NOT establish that true Alpha
equals zero: the intervals are wide (widths 0.0159, 0.0123 and 0.1194) and cannot exclude a sizeable effect of either sign.

## B. What v5 was, and what it did not test

v5 was a **cross-sectional forward benchmark-relative return predictability test** on a frozen KR feature set
(H21 and H126 horizons, walk-forward Ridge ladder B0–B4 with descriptive B1/B3/B5 and a Logistic head). It was not a
completed portfolio-strategy backtest and must not be described as a complete investing system. No portfolio fields
exist in the result (`noPortfolioFields`).

v5 did NOT establish or refute, and its result implies nothing about:

- **Valuation / value convergence:** PBR, book-to-market, earnings yield, FCF yield, OCF yield, EV/EBITDA, intrinsic-value
  gap, valuation convergence, rerating, quality-adjusted cheapness, catalyst-driven rerating.
- **Macro / economic regimes:** policy-rate, yield-curve, KRW/USD, credit-spread, aggregate-liquidity, export/business-cycle
  and earnings-revision regimes. The frozen descriptive market regime (section C) is only a limited market-state diagnostic.
- **Portfolio implementation:** top-3 or top-5 portfolios, concentration rules, weights, inverse downside-volatility sizing,
  Kelly sizing, risk budgeting, NAV, CAGR, Sharpe, Sortino, turnover optimisation, implementable portfolio economics.

The failure of any of these must not be inferred from the v5 primary result.

## C. Prespecified descriptive diagnostics — DESCRIPTIVE / HYPOTHESIS-GENERATING ONLY

These diagnostics were frozen (diagnostic spec `15a855fa…8f9a`) before any outcome was read. They cannot rescue,
overturn, upgrade or gate the primary `INCONCLUSIVE` result, choose a best feature, group or regime, or authorize a rerun.
Every figure below is read from `alpha-opportunity-model-v5-diagnostic-summary.json` or `...-diagnostic-models.json`.
Ablation deltas are `metric(ablation) − metric(B4)`; a positive pooled-MSE delta means removing the member made
the fit worse. Ridge coefficients are model attribution under training-only robust scaling, not causal effects.

**H126 ablations (pooled MSE delta; rank-weighted-spread delta; 530 signal weeks).**

| Removed | Pooled MSE delta | Rank-weighted spread delta |
| --- | --- | --- |
| TREND_MOMENTUM group (`relative126`, `acceleration21`) | +0.0004325893379107937 | -0.021307770941682895 |
| `relative126` alone | +0.0004467753045290096 | -0.020709504198796337 |
| RISK_VOLATILITY group (`vol63`) | +0.0001405797341619136 | +0.012053717895907947 |
| ACCOUNTING group (`assetGrowthPct`, `debtGrowthPct`) | +7.082278615250237e-05 | +0.004446621047374567 |
| ATTENTION_LIQUIDITY group (3 features) | +9.22660169692946e-06 | -0.00030170247967203044 |

Descriptively, the trend/momentum family and `relative126` carry the largest fit and rank-spread signal among the H126
model's members; removing the risk/volatility feature worsens fit but raises the rank-weighted spread. Individually
removing `assetGrowthPct` (-0.0001080898782331724) or `debtGrowthPct` (-0.00009472108100548604) lowers pooled MSE.

**Family attribution (H126, share of absolute contribution).** ACCOUNTING 0.5042786558869252, TREND_MOMENTUM
0.24669283367540387, RISK_VOLATILITY 0.17354658953228203, ATTENTION_LIQUIDITY 0.07548192090538884. This is model
attribution, not importance: the accounting family has the largest attributed magnitude while its group removal changes
pooled MSE by only +7.08e-05.

**Ridge coefficient stability (H126, 11 annual refits).** `relative126` value coefficient: median 0.01012202694870178,
positive in 11 of 11 refits, 0 sign flips. `vol63`: median -0.008547762390413962, negative in 10 of 11, 1 flip.
`acceleration21`: median -0.003088166320905918, negative in 11 of 11. Median L2 coefficient-vector drift 0.016338577195917112
(H21: 0.002398646567761731; H21 `relative126` median 0.0005344197472659715, 2 sign flips).

**Feature redundancy (training-only association, median over folds).** `assetGrowthPct`/`debtGrowthPct`: Spearman
0.8195221876919211, Pearson 0.7890098531509846 over 10 folds — the two accounting features are strongly redundant.
Other listed pairs are far weaker (for example `logVolumeShock60`/`shockPersistence5d` Spearman 0.29299712893774615;
`relative126`/`vol63` 0.1628975976796802).

**B4 versus B5 (H126).** B5-vs-B4 paired MSE improvement -0.0003944353864635493, interval
[-0.0018157894599280684, 0.0010269186870009697]. `b5CannotRescueB4 = true`; B5-minus-B4 pooled MSE +0.000391254391933743;
equal-date Spearman of the two predictors' means 0.5752307964312346; sign disagreement rate 0.14176044950427127.
(H21: B5-vs-B4 +2.4339557710320592e-05, [-8.727739136795769e-05, 0.0001359565067885989].) Ridge/Logistic head
concordance over 61,223 rows: mean equal-date Pearson 0.9222702304185274, Spearman 0.9118280409204468.

**Prespecified market-state regimes (H126, point estimates only, no intervals, `notAClaim = true`).**

| Regime (trend / volatility) | Signal weeks | B4 vs B0 MSE improvement | Rank-weighted spread |
| --- | --- | --- | --- |
| NON_POSITIVE / HIGH | 182 | -0.0015845287695337024 | -0.010449129274821318 |
| POSITIVE / HIGH | 243 | 0.002210719423370866 | 0.013225449193709353 |
| POSITIVE / LOW | 96 | 0.0009974533747280842 | 0.05087503500186799 |
| NON_POSITIVE / LOW | 9 | `DESCRIPTIVE_DATA_SPARSE` | — |

Point estimates are more favourable in the positive-trend cells than in the non-positive-trend cell. **This is a
candidate hypothesis for future research only.** It is not a finding, a validated regime filter or a trading rule, and
nothing here states that the model works in any market. Calendar-year cuts in the artifact vary in sign (for example
B4-vs-B0 H126 `fractionPositive` 0.4545 across 11 years), and 2026 is data-sparse.

## D. Research boundary after outcome exposure

The KR historical sample through the frozen cutoff **2026-09-14** is now outcome-exposed for future development. Any
future change informed by the v5 result and tested again over this same period — feature selection or removal,
valuation measures, regime definitions, portfolio rules, concentration, model changes, sizing, thresholds,
hyperparameters — is **EXPLORATORY / DEVELOPMENT EVIDENCE**, not independent confirmatory evidence. Good performance of a
revised model on the same 2016–2026 KR history must not be represented as untouched validation. The history remains
usable for development; it cannot certify what it helped shape.

Potential clean evidence sources, none of which is automatically comparable or pre-approved:

1. prospective KR observations strictly after the frozen v5 cutoff;
2. a properly repaired US sample, only if its protocol is frozen before US outcomes are inspected;
3. another genuinely untouched sample defined before inspection.

Each needs its own separately frozen protocol.

## E. Candidate research questions — questions, not decisions

No v6 specification is chosen or preregistered here.

1. Does point-in-time valuation information improve H126 cross-sectional predictability?
2. Can cheapness combined with quality and catalyst variables identify subsequent rerating candidates?
3. Is H126 signal efficacy conditional on an ex-ante market or macro regime?
4. Can a prediction model be converted into a realistic concentrated 3–5 security portfolio after transaction costs and risk constraints?
5. Can a future frozen H126 strategy replicate in truly untouched prospective KR data?
6. Can it replicate in repaired US data under a protocol frozen before US outcome inspection?

## F. Interpretation firewall

- **Confirmatory:** only the frozen primary claim and its registered verdict — `INCONCLUSIVE` (section A).
- **Prespecified descriptive:** the frozen diagnostic extension (section C). Useful for forming hypotheses; cannot rescue,
  overturn or upgrade the primary result.
- **New exploratory:** anything learned after reading the result. This PR adds no new cut, sub-period, sector,
  threshold, regime, feature or portfolio rule, computes no statistic that is not already in the artifacts, and does not
  search for where the model worked.

## G. Closure and rerun authority

The committed `docs/results/alpha-opportunity-model-v5-result.json` is the path the harness checks
(`COMMITTED_RESULT`). While it exists any formal execution attempt refuses with
`A_COMMITTED_V5_RESULT_ALREADY_EXISTS`; `tests/test_alpha_opportunity_v5_sealed_result.py` verifies this against
the real authorization file. The result is a substantive result, so it closes the preregistration; the authorization
was for exactly one execution and no rerun authority remains. A gap in the record is a gap: what is not in the archived
artifacts is not asserted here.

## H. Diagnostic ledger — metadata only (not committed)

| Field | Value |
| --- | --- |
| Filename | `alpha-opportunity-model-v5-diagnostic-ledger.jsonl.gz` |
| Original artifact | `alpha-opportunity-model-v5-diagnostics` (ID `11074762247`), run `36660521285` |
| Artifact archive digest | `sha256:4c07b3c83fee8f9f3f27c842eff11391ad27ed34a621cf53177d55c5c001fbec` |
| Row count (after gzip decompression) | 125,074 |
| Byte count (compressed) | 40,563,496 |
| SHA-256 | `863827c0ad8de265e7d1f170265ece8927e649c6494f384eaef19f7957d61e6c` |

Row count, byte count and SHA-256 are recorded in the committed diagnostic references file. The ledger itself was not
supplied to or committed by this seal; its size and row count were taken from those references and from the transfer
metadata supplied with the archive, and it was not opened here.

## I. Archived files

| File | SHA-256 |
| --- | --- |
| `docs/results/alpha-opportunity-model-v5-result.json` | `e06aa3fe17fb5986dd7e6a36272cc1bda59f78f97bfa4e6efaa68d1359d020d4` |
| `docs/results/alpha-opportunity-model-v5-result.sha256` | file SHA above |
| `docs/results/alpha-opportunity-model-v5-diagnostic-summary.json` | `37c6d8996f5a2696c7bd34863f96a9f74fc4a4a50bf694b5a772b1a4cafc304d` |
| `docs/results/alpha-opportunity-model-v5-diagnostic-models.json` | `b43d7d42e95375619c0cd0c1fa2ee28e95273ad485a54fb9d46803ae3831db98` |
| `docs/results/alpha-opportunity-model-v5-diagnostic-references.json` | `cf580b0c47b4023dfda707b4f9906796e8aabe88f4aa347b62ac8e23d3d67d2e` |

All are byte-for-byte copies of the formal artifacts.
