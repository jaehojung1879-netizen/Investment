# kr-market-risk-anatomy-v2 — final result (sealed, exploratory)

Scientific status: `EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY`. This is **not** prospective validation. The study is permanently consumed.

This document only summarizes the formal artifact. The numbers below are read from `docs/results/kr-market-risk-anatomy-v2-result.json`, which is byte-for-byte the formal artifact file. Nothing was recomputed, re-ranked, tuned or re-run.

## Identity

| item | value |
|---|---|
| Formal run | GitHub Actions `37244866236`, workflow `KR market risk anatomy v2`, `workflow_dispatch`, conclusion `success` |
| Execution main SHA | `5b73b20d676537c7ed3e613986b61fdade7c9b8d` |
| Artifact | `kr-market-risk-anatomy-v2-results-37244866236`, id `11318254649`, digest `sha256:f7f9f17a3a2aaa9bdb7b4ae488717d5cb1bbfc6228400664d4295557af37450f` |
| Result | `market-risk-anatomy.json`, sha256 `7be4f68f30cf57b01cde88f106b3c0c2ed88fc9942ca2a14007664ffbe4ca769` |
| Marker | `execution-started.json`, sha256 `391b6ff013d5a89d5e0342fdc767c4304bc6d7ad6bc8d63247a45a71794c73bc` (`valuesReadBeforeThisMarker` = 0) |
| Manifest | `manifest.json`, sha256 `d32efef61916ef761a662723a4e18edcbf32ad737a22b9835cd81733204e0067` |
| Frozen spec / design / source audit | `4be62167…06f2` / `3c398b6e…8aaa` / `29e1b54b…9345` |
| Counters | analysis 1, episode 1, forward-target 1, marker 1, value reads 14 |
| Locks | `refs/tags/kr-market-risk-anatomy-v2-execution-lock` and `…-lock-<specSha256>`, both at the execution SHA |

## A. Formal observed result

**Reference and sample.** Primary reference `FDR_KS200` (KOSPI 200 price index, one vendor route, not spliced), analysis end 2026-09-17. The analysis ran over the whole retained series: 9,475 expected sessions from 1990-01-03, 9,465 valid closes, 10 missing sessions and 5 vendor dates off the XKRX calendar (all before 2006; the preregistered quality gate window starts 2006-01-01). Fast-family features run on weekly rows from 1990; slow features on monthly rows (about 360–413 valid rows by horizon).

**Drawdown episodes.** The algorithm found 13, 12 and 9 underwater episodes of depth at least 10%, 15% and 20%.

**FAST market-break variables (horizons H21 / H63 / H126).** Realised and downside volatility show the clearest descriptive relation to subsequent downside. For example `fast_realized_vol_21` has AUROC for a ≤ −15% forward loss of 0.816 / 0.713 / 0.658, and at H21 the ≤ −15% event rate is 17.1% when the state is high against 2.4% when it is not. `fast_downside_vol_63` reads 0.807 / 0.728 / 0.671 and `fast_realized_vol_63` 0.796 / 0.739 / 0.668. Rank correlation with forward max-drawdown severity is 0.38–0.45 for these. Drawdown depth, overlay count and long-horizon return are weaker (AUROC mostly 0.55–0.71 at H21, 0.52–0.66 beyond). `fast_sma200_slope_21` and `fast_vol_acceleration` are near 0.5 at H63/H126.

**SLOW variables (H63 / H126 / H252).** Simple 10y–3m flatness (AUROC about 0.48–0.51) and inversion duration (0.45–0.48) show no usable association; 10y–2y flatness is only slightly above 0.5. The post-inversion re-steepening flag is more notable: AUROC for ≤ −15% of 0.665 / 0.667 / 0.657, event rate 56.2% when on against 23.5% when off at H252, and the largest loss-severity correlation among slow variables at H252 (0.289). The fed-funds level also shows a positive association (0.674 / 0.638 / 0.593); fed-funds change points the other way (AUROC about 0.38–0.42).

**TRANSITION variables (H63 / H126).** VIX level is associated with downside (AUROC 0.651 / 0.637; ≤ −15% rate 19.0% vs 12.3% at H63), while VIX changes are close to 0.5. USD/KRW 63-day change is near 0.5 and USD/KRW 21-day realised volatility points the unexpected way (AUROC 0.455 / 0.410). The easing flag marks higher downside (≤ −15% rate 29.1% when on vs 11.0% when off at H63; AUROC 0.613 / 0.600), and easing-after-inversion is similar (0.628 / 0.591). Credit-spread (HY/IG OAS) features have valid rows only from late 2023 (114–140 rows), and the benign-easing and HY post-vulnerability flags had no valid rows, so none of these can be read.

**Existing SMA200 + Vol63 overlay baseline (12 episodes of depth ≥ 15%).**

| trigger | in adverse state | episodes triggered | median share of the drawdown already taken at trigger | triggered before 20% of drawdown | activations that saw no −10% within H63 |
|---|---:|---:|---:|---:|---:|
| B3 either condition adverse | 53.0% of sessions | 12 of 12 | 19.6% | 50.0% | 79.8% |
| B4 both conditions adverse | 17.2% of sessions | 6 of 12 (6 missed) | 65.2% | 0.0% | 32.4% |
| B1 trend only | 38.6% | 8 of 12 | 30.5% | 8.3% | 68.5% |
| B2 volatility only | 31.6% | 10 of 12 | 32.5% | 41.7% | 60.0% |
| D10 trailing drawdown | 40.3% | 12 of 12 | 33.4% | 16.7% | 66.1% |

**Market internals (EXTENDED tier).** Most internals have only 95 valid dates (2015-10-16 to 2023-10-27); breadth deterioration has 50; only top-5 concentration has 588 (2015-01-02 to 2026-09-11). At H21 several have as few as 1–3 loss events, so most AUROCs are undefined or rest on 17–22 events.

## B. Interpretation / development implication

- Fast market-break information, volatility above all, is where the descriptive signal about near-term downside is clearest. High recent realised or downside volatility goes with materially larger short-horizon downside risk.
- Plain curve inversion is not the strongest slow-risk reading in this sample; the re-steepening state after inversion is more notable at longer horizons.
- VIX level carries transition-layer information; VIX change and USD/KRW alone are comparatively weak.
- Simple policy easing behaves more like a stress-state marker than a clean bullish signal in this historical sample.
- The SMA200 + Vol63 baseline shows a real trade-off. Reacting when either condition is adverse catches every large drawdown and early (median 19.6% of the drawdown taken) but is on 53% of sessions and most activations see no 10% drawdown within H63. Requiring both is on 17% of sessions and cleaner, but misses half the episodes and, when it fires, is late (median 65.2% taken).
- Market internals look interesting in places but rest on a much shorter sample and few events; they should not be promoted from this anatomy.
- Any hypothesis these observations suggest belongs to a new preregistration. This seal does not create one.

## C. What is not claimed

- Not prospective validation: every date through 2026-09-17 is outcome-exposed.
- No feature or trigger is validated, predictive, best, or recommended; no threshold, window, multiplier or horizon is chosen or changed (SMA200, Vol63, the 25% volatility threshold, 1.0 / 0.7 / 0.4 multipliers, H21 / H63 / H126 / H252 and the loss thresholds are exactly as frozen).
- No composite score, no Market Risk Model and no portfolio or performance result exists here.
- Descriptive statistics on overlapping, serially dependent windows carry no multiplicity correction and are not significance tests.
- The reference is a price index (`MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY`), not total return, and the selected source is not live-ready (17 days stale against the 10-day live limit).
- Revised-history macro series were excluded, not treated as point-in-time.
- The analysis used history before the 2006 quality window; its 10 missing sessions and 5 off-calendar vendor dates are reported above, not repaired.
