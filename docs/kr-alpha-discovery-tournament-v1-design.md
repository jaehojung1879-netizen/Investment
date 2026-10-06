# kr-alpha-discovery-tournament-v1 — a pre-registered, bounded model-selection tournament (KR)

> **PREREGISTRATION + HARNESS + SYNTHETIC TESTS ONLY. NO HISTORICAL OUTCOME OF THIS STUDY HAS BEEN COMPUTED.**
> `scientificStatus: EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY`. Every Korean date through the 2026-09-14 cutoff is outcome-exposed and
> the factor, industry, stock-within-industry and integrated-portfolio studies (and the post-outcome audit) were read before this was designed. Every
> historical number this study can produce is DEVELOPMENT evidence about a model-selection **process**. Only prospective receipts can confirm it.

Machine-readable twin: `research_specs/kr-alpha-discovery-tournament-v1.json` (SHA-256 in the `.sha256` sidecar). Every rule below is a module
constant compared with the spec on every load (`pipeline/kr_alpha_tournament_execution.load_spec`). Outcome-free readiness:
`docs/results/kr-alpha-discovery-tournament-v1-readiness.json`.

## 0. Duplicate-research gate (answered before anything was built)

The brief requires stopping if this is a relabelled redo. It is not, and the one way it is NOT different is stated just as plainly.

| | regional-alpha-model-v1 (closed, `NO_MODEL_EVIDENCE`) | kr-model-overlay-portfolio-v1 (`DEVELOPMENT_REJECT`) | this study |
|---|---|---|---|
| Information representation | 31 percentile features: price/trend/risk, fundamental LEVEL, 4 accelerations, KR cap; **valuation yields excluded**; no industry | 11 sealed KR features + 4 fixed family products | the 11 sealed features **plus** 11 derived price/liquidity/LOO-industry features, **8 v4 industry-state features**, a past-only market state; each as robust z **and** cross-sectional percentile **and** within-industry percentile **and** missingness |
| Target | within-date rank of stock − benchmark | stock − 069500 | **four**: same-data universe magnitude, **LOO-industry residual**, cross-sectional rank, **top-quintile event** |
| Model selection | none (Ridge 10, one HGBR) | none (Ridge 10, one HGB) | **nested purged walk-forward tournament** over 120 configurations with a frozen inner economic rule and a diversity-constrained ensemble |
| Objective | IC classification | fixed top-5 book | **net geometric wealth over a passive core**, uncertainty-shrunk fractional Kelly, dynamic breadth |

What is **not** different: no genuinely new raw information. Investor flow, ownership, short selling and vintage-safe macro are not ready (§3). Every
raw input was already measured by an anatomy or a model study. Therefore an `INFORMATION_LIMITED` verdict closes model search on **this** information
set; it is not an invitation to try another algorithm.

## 1. What exactly are we trying to maximize?

Realistic long-run **net geometric wealth growth** from information this repository can know at each date, after costs, liquidity and estimation error,
long-only and unlevered. The headline quantity is `G` = annualised mean daily **log**-return of the process's book minus that of 100% 069500.KS, net of
every cost, over every session from the first outer anchor (2018-01) to the cutoff. Classification accuracy, IC and hit rate are diagnostics.

## 2. Why is passive capital the default opportunity cost?

Because it is the realistic alternative: holding KODEX 200 costs almost nothing and earns the market. A portfolio here is
`passive core (069500.KS) + long-only active overweights`, gross ≤ 1, no cash target. An active name enters only by **displacing** passive capital:
its shrunk expected incremental return over 069500.KS must pay its covariance penalty **and** the cost of buying it and selling the passive leg. With
nothing worth that, the allocator returns zero active weight and the book stays passive (`PASSIVE_DEFAULT`). Both legs live in one self-financing
ledger (`kr_alpha_tournament_portfolio.execute`), so this is simulated, not assumed.

Caveat, carried and not repaired: the 069500.KS series has an unexplained accrual against the same-data constituent reference (+4.53%/yr vs +1.85%/yr,
2017-2024; `INTERNAL_CONSTRUCTION_ANOMALY_FOUND`). Holding it as the core inflates the passive leg of **every** path, which biases the comparison
**against** active capital. The passive leg pays 15 bp each way (an assumption, stated as one; no transaction tax on the ETF leg, no impact).

## 3. Which information is actually available? (outcome-blind audit)

| Family | Class | Fields |
|---|---|---|
| Price trend | A ready, PIT | relative126, momentum121, ret21, ret63, dist252High, ma200Distance |
| Price risk | A | negativeDownsideVol126, vol63, beta252, maxDrawdown252 |
| Liquidity / attention | B derived | logAdv60, logVolumeShock5_60 (magnitude kept), logAmihud60, logMarketCap |
| Valuation | B derived | bookToMarketProxy, earningsYieldProxy, ocfYieldProxy (repaired PIT DART × signal-date KRX cap) |
| Quality / accounting | B derived | netIncomeToAssets, ocfToAssets, negativeAccrualsToAssets, ocfImprovementToAssets (receipt-date availability) |
| Industry state | B derived | REL_MOM_63/126, BREADTH_ABOVE_MA_126, CONSTITUENT_DISPERSION_126, TOP1_CAP_SHARE, MEDIAN_LOG_ADV60, DOWNSIDE_VOL_126, stockMinusLooIndustry126 (v4 membership, a reconstruction) |
| Market state (price) | A | marketTrendAdverse, marketVol63 (sealed `kr_market_risk_overlay.state_at` on 069500.KS, past-only) |

All come from the exact preserved raw-input artifact `kr-model-raw-inputs-36844599518` (pinned by name, run, id, archive digest and identity, the
same pin the integrated study used) and committed membership files. Known limits: KR fundamentals dark in 2015 and partial in 2016; the return basis
is an adjusted index with partial distributions; the universe is the PIT top-120 large caps only.

## 4. Which information is excluded and why?

| Family | Class | Reason |
|---|---|---|
| FRED / VIX macro | D revised | current/revised-history contract; 10 of 28 panel columns have no ALFRED vintages |
| KR macro (ECOS) | D | adapter exists, no pinned release-vintage series |
| KR investor flow | E | collector exists; KRX portal answered LOGOUT/400; no historical ledger |
| KR short selling | E | source access unresolved; three regulatory regimes inside the window |
| DART 5% ownership | C | collected receipts span 2024-09-24..2026-09-23 only (BLOCKED_HISTORICAL_DEPTH) |
| Analyst revisions | F | no free PIT history |
| Official PIT sector history | F | none; v4 reconstruction used as context only |
| Total shareholder return / terminal consideration | C | partial distributions; 22 terminated names unresolved |

Code existence is not data readiness: nothing in C/D/E/F enters the tournament.

## 5. Which prior historical questions are already closed?

`regional-alpha-model-v1` (31-feature matrix, KR and US `NO_MODEL_EVIDENCE`, budget spent); `kr-model-overlay-portfolio-v1` (`DEVELOPMENT_REJECT`);
`alpha-opportunity-model-v5` (`INCONCLUSIVE` at H21/H126); `kr-factor-anatomy-v1`, `kr-industry-opportunity-anatomy-v1`,
`kr-stock-within-industry-anatomy-v1` (descriptive maps); `kr-integrated-alpha-portfolio-v1` (consumed; industry layer development-supported in a
regime- and industry-concentrated way; named Samsung / SK Hynix exclusion already studied — **no bespoke rescue test here**). Their result bytes are
pinned in `spec.priors` and none is rerun.

## 6-7. Which model families compete, and why these?

Method review (included / excluded, with reasons, also in `spec.candidates.excluded`):

| Family | Status | Why |
|---|---|---|
| A. Ridge (date-balanced pooled cross-sectional regression ≈ regularised Fama-MacBeth) | **SHRUNK_LINEAR** | the honest linear baseline; closed form; deterministic |
| A. Elastic Net | **SPARSE_LINEAR** | ~108 correlated linear columns; sparsity is a different hypothesis from shrinkage |
| A. Robust (Huber) | excluded | robust-z clipping bounds leverage; rank / event targets handle outcome outliers |
| B. Shallow HistGradientBoosting | **SHALLOW_TREE** | learns interactions and nonlinearity without hand-mined products; one thread |
| B. LightGBM / XGBoost | excluded | same idea, extra thread-determinism risk |
| B. Shallow / deep neural net | excluded | ~600 weekly dates × ~120 names with 126-session overlap is only ~25 effective cross-sections a year |
| C. Pairwise learning-to-rank | **LEARNING_TO_RANK** | relative order as the objective, distinct from point prediction |
| C. Listwise / ordinal | excluded | pairwise covers relative order with fewer moving parts |
| D. PLS (weighted NIPALS) | **LATENT_FACTOR** | characteristic-conditioned latent directions; deterministic |
| D. IPCA | excluded | needs a balanced panel and ALS with many latent dims; PLS is the auditable challenger |
| E. Ensemble | **ENSEMBLE** (a rule) | equal weight over a diverse top-K; validation-weighted or dynamic averaging excluded as noise-fitting on 2-3 folds |
| F. Uncertainty | in the pipeline | calibration error + model disagreement (past-only); quantile heads excluded |
| G. Decision-focused learning | **one quarantined challenger** | Brandt-style parametric portfolio policy; cannot change the verdict |

Five fitted families plus the ensemble rule: six, at the brief's ≤ 6 target.

## 8. What are the exact targets?

| Target | Definition (H126; entry = next session close, exit 126 sessions later) |
|---|---|
| A_MAGNITUDE_VS_SAME_DATA_UNIVERSE | stock return − signal-date-cap-weighted return of the OTHER label-eligible PIT Top120 members (≥ 50) |
| B_RESIDUAL_VS_LOO_INDUSTRY | stock − cap-weighted leave-one-out industry return (sealed `stock_targets`, every peer matured) |
| C_CROSS_SECTIONAL_RANK | within-date percentile of the stock return − 0.5 |
| D_TOP_QUINTILE_EVENT | 1 if that percentile > 0.8 else 0 |

Target A uses a **same-data** reference for learning only, because the 069500.KS series is not reconciled; the benchmark is never repaired. The
**economic** label (stock − 069500.KS over the same endpoints, `target_from_sessions` semantics, cross-checked row by row against the sealed v1
function) is used only for calibration and evaluation. Rankers use C and B (A induces C's order; D coarsens it). H252 is a descriptive secondary
evaluation of the same H126 predictions, never a training target and never a rescue.

## 9. How does nested walk-forward prevent model-selection leakage?

* **Outer** (the historical investor): one fold per year 2018..2026; its cutoff `C_Y` is the signal date of the year's first anchor. A row trains only
  if its label exit is **strictly before** `C_Y`. Fitting, inner selection, hyperparameters, recency, calibration and uncertainty for year Y never
  index a label that exits on or after `C_Y` (a test perturbs exactly those labels and requires identical fold-Y forecasts). Every anchor of year Y
  uses that fold's process; outer forecasts are written once.
* **Inner** (inside the past): the most recent half of the fold's training dates is split into 3 contiguous validation blocks. For block Vj, inner
  training rows must exit strictly before Vj's **first entry** date (**purge**) and have signal dates at least 21 sessions before Vj's first signal
  (**embargo**; implied by the purge at H126, enforced explicitly). No random or shuffled split. A block needs ≥ 52 training and ≥ 13 validation
  dates; a fold needs ≥ 2 valid blocks. Calendar-only readiness: 2018 has 2 valid blocks, every later year 3.
* Representations are per-date transforms; the only fitted transform (standardisation) is fitted on training rows.

## 10. How are hyperparameters chosen?

Inside the inner loop only, from a closed grid: Ridge α/unit-weight {0.01, 0.1, 1}; ElasticNet α {0.005, 0.02} (l1 0.5); HGB depth {2, 3}; ranker C
{0.1, 1}; PLS components {2, 4}; recency {no decay, 5-year half-life, 2-year half-life}. **Trial ledger:** 6 families (5 fitted), 11
hyperparameter configurations, 4 targets, 3 recency schemes = **120 fitted configurations**, + ensemble rule + decision-focused challenger + baseline-1
translator = **123 effective trials**; 9 outer folds × (3 inner + 1 refit) = 4,320 fitted models. These counts are what DSR is paid with.

## 13. The frozen inner selection rule

1. **Stability**: IC > 0 on ≥ ⌈2/3 × valid folds⌉ inner folds; pooled HAC calibration slope > 0; ≥ 90% prediction coverage; finite economic score.
2. **Economics**: survivors ranked by mean inner score = annualised net log growth of the common translator minus 100% passive on non-overlapping
   21-session blocks of V2/V3 (calibration for Vj fitted on the candidate's out-of-fold predictions of earlier blocks only).
3. **Ensemble**: best candidate per family until K = 3, equal weights; 1-2 survivors → those; 0 → `PASSIVE_DEFAULT` for that outer year.

The process may change family through history; the selection algorithm is the object under test.

## 11-12. Disagreement → uncertainty; calibration

**Calibration** (per member, past-only, on inner out-of-fold predictions): s = within-date rank of the native score; per-date slope of the economic
label on (s − 0.5); pooled slope b with a Newey-West SE (lag 26 weekly overlaps); positive-part James-Stein shrinkage b* = b·max(0, 1 − SE²/b²);
universe carry is never credited (intercept = min(0, mean carry)). μ(s) = min(0, a) + b*·(s − 0.5). Continuous in rank — no coarse buckets — and it
cannot create alpha the ranking did not show.

**Uncertainty**: σ² = variance of calibrated μ across ensemble members (disagreement) + mean of (SE·|s − 0.5|)² (calibration). Contraction
κ = μ²/(μ² + σ²) ∈ [0, 1]; μ_post = κ·μ, asserted |μ_post| ≤ |μ| with sign preserved. κ is a signal-to-noise contraction, never a probability.

## 13-14. The capital allocator; why breadth is dynamic

Maximise `w'(μ_post − c_eb) − (1/(2·0.5)) w'Σ_e w − TC(w; w0)` over active weights, where Σ_e is the Ledoit-Wolf covariance of 252 trailing daily
active returns (stock − 069500.KS) scaled to 126 sessions and c_eb their covariance with the benchmark (half Kelly). Constraints: w ≥ 0, w ≤ min(30%,
1% × ADV60 / NAV), per-trade participation ≤ 1% of ADV60, Σw ≤ 1, passive = 1 − Σw. Solved exactly by FISTA with the closed-form prox of the asymmetric
cost and box and a bisected budget multiplier. There is **no Top-N and no fixed five**: the number of names is whatever clears its cost and its
uncertainty, from zero (passive) upward. Realised breadth is reported. Baselines: **0** = 100% passive; **1** = equal weight over the names whose μ_post
exceeds their round-trip cost (the primary's own admission arithmetic), passive residual. The decision-focused challenger uses the same inputs, costs,
constraints and outer folds and is quarantined.

## 15. Transaction costs and liquidity

Inherited unchanged: stock buy 15 bp, sell 45 bp, square-root impact 5 bp at 1% participation on actual KRW notional (KRW 100m reference account,
growing with NAV), ADV60 ≥ KRW 3bn, holding cap min(30%, 1% ADV), execution only on an observed positive-volume quote (otherwise deferred), and a held
name without an observable mark blocks the path (`BLOCKED_BY_DATA_INTEGRITY`). Passive leg 15 bp each way (assumption). Stresses: ×2 cost, half ADV
capacity, one-session execution delay; slices 2017-2020 (outer decisions exist from 2018), 2021-2024, 2025, 2026 to cutoff; leave-largest-contributor-out.

## 16. How is multiple testing paid for?

Trial ledger (above); **Deflated Sharpe** of the primary's non-overlapping 21-session active log-return blocks with N = 123 and the trial-Sharpe
variance taken from every configuration's outer cheap-translator blocks; **PBO** by CSCV (16 contiguous groups, 12,870 splits) over the configuration
universe; **Hansen SPA** (consistent p, stationary bootstrap, mean block 6 = 126/21, B = 2,000) for the primary vs passive and for the whole universe;
**moving-block bootstrap** (126-session blocks, B = 2,000) CI of G. Assumptions are stated in the spec; overlapping daily series never get naive
p-values. The cheap translator (equal-weight top quintile, 21 sessions) exists only to give these diagnostics a universe; it never selects.

## 17-18. What constitutes success; what triggers INFORMATION_LIMITED

Checked in this order, frozen in `kr_alpha_tournament_evaluation.verdict`:

* **E BLOCKED_BY_DATA_INTEGRITY** — a path is incomplete, the input identity moved during the run, or < 80% of outer anchors had a valid cross-section.
* **A ROBUST_ACTIVE_VALUE_FOUND** — ALL of: G ≥ 1.0 pp/yr; bootstrap lower 95% > 0; G under ×2 cost > 0; G > 0 in ≥ 3 of 4 periods; G after removing
  the largest contributor > 0; DSR ≥ 0.95; primary SPA p ≤ 0.05; PBO ≤ 0.5; outer ensemble rank-IC HAC lower 95% > 0.
* **B WEAK_OR_REGIME_DEPENDENT_VALUE** — G > 0 and not A.
* **C PREDICTIVE_SIGNAL_WITHOUT_ECONOMIC_VALUE** — G ≤ 0 and rank-IC lower 95% > 0.
* **D INFORMATION_LIMITED** — G ≤ 0 and no predictive evidence. **Stop**: historical model search on this information set closes permanently — no
  Expected Alpha v2 on the same data, no further algorithms, no weight moves, no H126 change, no rescue; the next step is new information whose PIT
  history is genuinely ready (KR investor flow, DART ownership, short selling, vintage-safe KR macro).

Missing evidence never passes a check. For every verdict: no v1.1, no re-seed, no grid widening.

## 19. What happens prospectively?

The frozen process issues immutable receipts (`pipeline/kr_alpha_tournament_receipts.py`, schema `research_specs/kr-alpha-discovery-tournament-v1-receipt.schema.json`):
as-of timestamp, code SHA, spec SHA, data snapshot identity, training cutoff, candidate-registry digest, selected models and ensemble weights, per
eligible security the member scores, rank, calibrated expected incremental return, uncertainty, contraction and shrunk forecast, the active portfolio
and the derived passive weight, costs, and a SHA-256 seal; append-only, one per decision date, never rewritten. Designed, not running: no receipt is
written and nothing is scheduled by this change.

## Lifecycle (one shot)

`workflow_dispatch` on merged `main` → committed spec + every pin → exact raw artifact (unexpired; name, run, id, digest) and its identity →
signal-time features and every label-free gate (a failure spends nothing) → **durable exclusive lock** (`refs/tags/kr-alpha-discovery-tournament-v1-execution-lock`
and `-<specSha256>`, atomic POST, any existing ref refuses) → marker (zero values read) → first label → tournament, paths, verdict → one results
artifact → exact-byte **Draft** seal PR. A failure after the lock consumes the study. The integrated study's seal job failed because its seal script
had no `main()` guard (every subcommand was a silent no-op); this study's seal script is run as a real subprocess by a test and the commit step refuses
an empty seal. The raw-input artifact was created 2026-10-01 and expires with its retention; the execute guard refuses an expired artifact.

## Limitations

One outcome-exposed sample reused by many studies; PIT top-120 large caps only; adjusted-index return basis with partial distributions; v4 industry
membership is a reconstruction; 069500.KS accrual unresolved; the inner economic score is an approximation (21-session buy-and-hold blocks, linear
costs, label-eligible names) while the outer path is valued daily; DSR/PBO/SPA assumptions are stated, not verified. Nothing here is validation.
