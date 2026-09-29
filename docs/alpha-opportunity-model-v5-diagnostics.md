# alpha-opportunity-model-v5 supplemental diagnostics (v1) — descriptive, pre-outcome, primary-isolated

State: implemented and **frozen before any Alpha-v5 outcome**; not executed. The formal v5 execution has not happened, no
authorization file exists and no result artifact exists.

The protocol is `research_specs/alpha-opportunity-model-v5-diagnostics-v1.json` (SHA-256
`15a855faae2b7a1ae34aea703a8e0b996b363fd8359210bb43ab308945048f9a`, sidecar
`research_specs/alpha-opportunity-model-v5-diagnostics-v1.sha256`). It is **not a v5.1 primary preregistration**: it
changes nothing the frozen v5 spec (`d0f1aaf5…`) fixed — features, horizons, targets, models, hyperparameters,
inference, thresholds, costs, universe, PIT rules, claim states or execution count. It exists to extract more
descriptive information from the ONE authorized execution and to preserve enough of it that later research does not
need to rerun Alpha v5.

## Isolation guarantee

1. The complete registered primary result is built, canonicalised and hashed (`primaryResultSha256`, the existing
   `substantiveResultSha256` formula, unchanged) **before** any diagnostic runs.
2. Diagnostics receive deep copies of the primary intermediates and use their own counters; the primary counters never
   see a diagnostic fit.
3. The result file is the unchanged primary payload plus its original hash plus, only if diagnostics ran, a
   `diagnosticReferences` block (status, spec digest, artifact SHA-256/bytes/schema/row count). That block is excluded
   from the primary digest, so the primary digest is identical with diagnostics on or off (tested, including against a
   re-run), and with diagnostics disabled the bytes are exactly the previous harness's.
4. Any diagnostic exception, malformed return or firewall violation becomes a separate `DIAGNOSTIC_ERROR` reference. It
   never changes a claim, an overall status, a payload or a hash, never fails the job and **never authorises a
   substantive retry**.
5. `firewall.*` flags in the spec (`affectsPrimaryClaim`, `promotionEligible`, `modelSelectionAllowed`,
   `featureSelectionAllowed`, `resultCanRescuePrimary`, `resultCanRefutePrimary`, `resultCanGatePrimary`,
   `resultCanTriggerRerun`, …) are all `false`, are re-checked on every load, and a flipped-and-resealed spec is refused.
6. The authorization (created later, by the operator) pins the diagnostic-spec digest beside the harness file hashes.

## Methods (all descriptive, none a claim)

- **Feature groups** (attribution only; the registry, B2, B3 and B4 are untouched): TREND_MOMENTUM (`relative126`,
  `acceleration21`), RISK_VOLATILITY (`vol63`), ATTENTION_LIQUIDITY (`logVolumeShock60`, `shockPersistence5d`,
  `volumePriceAlignment`), ACCOUNTING (H126 only: `assetGrowthPct`, `debtGrowthPct`; `NOT_APPLICABLE` at H21). Each
  active feature belongs to exactly one family, enforced on load.
- **Ridge coefficient stability**: per annual refit, per feature, the standardized value coefficient, the missing-indicator
  coefficient, intercept, active/omitted and sign; median, median absolute, IQR, fraction positive/negative, sign-flip
  count, year-to-year drift and L2 coefficient-vector drift. Model coefficients under training-only robust scaling, never
  causal effects, no significance label.
- **Exact prediction decomposition**: `intercept + Σ_j (valueCoef_j·transformed_j + missingCoef_j·indicator_j)` equals the
  B4 prediction to 1e-9 on every evaluated row or the diagnostic run is a `DIAGNOSTIC_ERROR`. Each diagnostic refit must
  also reproduce the primary B4 (and B5) prediction exactly. Family signed contribution is the sum of member
  contributions; family absolute contribution is the sum of member absolute contributions; the share is the family's
  mean absolute contribution over the sum across families. The Logistic head is decomposed on the LOG-ODDS scale only.
  This is model attribution, not "true importance".
- **Leave-one-feature-out and leave-one-family-out** Ridge refits on exactly B4's folds, purge, weights, transforms,
  missingness semantics, alpha=10, universe and evaluation rows. Deltas are `metric(ablation) − metric(B4)` for pooled
  MSE, equal-date MSE, rankWeightedSpread and prediction cross-sectional variance, overall and per fold. Individual
  LOFO is unique information conditional on the remaining correlated features (a near-zero value does not mean the
  feature is uninformative when substitutes exist); family LOFO is reliance on the family and is the preferred
  headline reading. There is no search, no selection and no PASS/FAIL.
- **Redundancy map**: training-fold-only date-weighted Pearson and Spearman among active transformed features
  (pairwise complete, before imputation), median/IQR across folds, reported beside individual and family LOFO with no
  verdict label.
- **Linear vs nonlinear**: B4 vs B5 MSE difference, Pearson and equal-date Spearman prediction correlation, top/bottom
  quintile overlap by date, sign-disagreement rate and dispersion of B5−B4, overall and by fold. B5 can never rescue B4.
- **1-D ALE of B5** (10 equal-count bins whose edges come from the fold's TRAINING values only; evaluated on the fold's
  out-of-fold rows; centered; support recorded per bin; bins under 50 rows are `UNSUPPORTED` and never extrapolated,
  interpolated or bridged; nothing accumulates across a gap). Not PDP, not SHAP.
- **Regimes** from information known at the signal date: TREND (KR benchmark trailing 126-session return > 0) and
  VOLATILITY (trailing 63-session realized volatility vs the median of the same statistic over the strictly earlier
  signal dates, expanding, at least 26 prior dates). Four mechanical regimes; no named event; no full-sample threshold. A
  cell under 26 signal weeks is `DESCRIPTIVE_DATA_SPARSE` (counts only). The same metrics are reported by calendar
  evaluation year, with no winner/loser label.
- **Ridge/Logistic concordance**: equal-date head correlation, expected-return deciles vs realized beat rate and mean
  realized relative return, probability deciles, a 10-bin calibration table and disagreement counts.

## Multiple-testing firewall

Diagnostics report effect sizes, coefficients, fold distributions, curves, out-of-fold losses and correlations. Every
output is scanned and a key containing `significan`, `pvalue`, `winner`, `bestfeature/model/regime/group`,
`promotedpredictor`, `tstat`, `holm` or `bonferroni` makes the run a `DIAGNOSTIC_ERROR`. No best feature, group, regime
or interaction is chosen, no threshold is optimized from outcomes, and any hypothesis these diagnostics suggest is input to
a NEW preregistration, not a change to v5.

## Artifacts (schema version 1)

Uploaded as their own workflow artifact `alpha-opportunity-model-v5-diagnostics` (never named like the one-shot result):

| Artifact | Content |
|---|---|
| `alpha-opportunity-model-v5-diagnostic-ledger.jsonl.gz` | one canonical-JSON line per out-of-fold evaluated name-date, sorted by (horizon, date, ticker), gzip mtime 0: feature values, transformed values, missing indicators, B0–B5, Logistic probability, B4 feature and family contributions, realized return, benchmark-beat label, round-trip cost, selected flag, eligibility status, regime |
| `alpha-opportunity-model-v5-diagnostic-models.json` | per fold: transforms/scalers, active/omitted features, B4 and Logistic coefficients, coefficient stability, ablation summaries, redundancy, ALE |
| `alpha-opportunity-model-v5-diagnostic-summary.json` | contribution summaries, linear-vs-nonlinear, head concordance, regime and calendar-year tables |

Every artifact carries its schema version, row count, `primaryResultSha256`, `diagnosticSpecSha256` and the harness file
hashes, and the primary result's `diagnosticReferences` records each artifact's SHA-256 and size. Serialization is
deterministic and the ledger is row-order invariant (tested).

## Scientific references (motivation only)

None of these validates any Alpha-v5 result; they motivate the method and the caution.

- Gu, Kelly & Xiu (2020), *Empirical Asset Pricing via Machine Learning*: nonlinearity and interactions matter in
  return prediction and the same families — momentum, liquidity, volatility — recur among the most influential
  predictors. This motivates the family grouping and the linear-vs-nonlinear comparison.
- Harvey, Liu & Zhu (2016), *…and the Cross-Section of Expected Returns*, and Harvey, Sancetta & Zhao (2026) on the
  factor zoo and selection bias: the reason the diagnostics carry no p-values or significance labels and choose no best
  feature, group or regime.
- Fisher, Rudin & Dominici (2019), model reliance: importance depends on the model class and the reference set; hence
  `model attribution` and `predictive reliance` are named as such and not as true importance.
- Verdinelli & Wasserman (2024), *Decorrelated Variable Importance*: with correlated features leave-one-covariate-out
  understates a feature that has substitutes; hence group ablation is the headline and the redundancy map is reported
  beside individual ablation.
- Apley & Zhu (2020), *Visualizing the effects of predictor variables in black box supervised learning models*:
  accumulated local effects avoid the off-manifold extrapolation partial-dependence plots suffer with correlated
  predictors; hence ALE, with training-derived bins and explicit unsupported bins.

## Disclosed limits

Everything is tested on synthetic fixtures; the diagnostics have never touched a real price or outcome. The diagnostic
Ridge refits repeat the primary fits, so runtime roughly doubles. The ledger is a large artifact (tens of MB expected on
the real sample). The retention of `alpha-opportunity-model-v5-diagnostics` is 90 days: commit what is needed.
