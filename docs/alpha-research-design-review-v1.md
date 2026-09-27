# Alpha research design review v1

Review date: 2026-09-28 (Asia/Seoul). Repository base: `2c5b684949af82746dd2ba2ed810c255f4b84c2e`, the actual `main` verified at checkout and again during review. This is a methodological review, **not an executable specification or v5**. Recommendations below are proposals to freeze before a future execution, not edits to prior seals.

## 1. Executive conclusion

**Keep the investable regional benchmark-relative expected-return objective, the small feature set, and the conservative linear-plus-shallow-tree architecture. Repair the identification and decision contract before adding model complexity.** The strongest credible test asks three separately answerable questions: does stock information improve forecasts over simple alternatives; does it identify an economically meaningful net advantage; and can that advantage be implemented at the declared capital scale? Passing one does not establish the others.

The most consequential modifications are: symmetric security/total-return auditing; an explicit conditional estimand when endpoints remain unresolved; matched baseline attribution; a return-evidence gate independent of classifier quality; overlap-aware uncertainty with a frozen sensitivity rule; and distinct statistical, economic and deployability statuses. More gates are not automatically more rigor. More predictors are not automatically more information.

The existing sample has been used by earlier research. A new seal or a repaired input snapshot does not make it an untouched confirmatory sample. Future v5 should be labelled historical discovery/replication evidence and should reserve prospective confirmation. It must not claim production readiness or universal absence of predictability after a negative result.

### Exposure and scope record

The initial required `AGENTS.md` read exposed embedded historical research outcomes. Early keyword/paragraph filtering also allowed qualitative result commentary from mixed documentation through. Those exposures cannot be undone; this review **does not certify complete outcome blindness**. No recommendation is justified by those outcomes, no result values are reproduced here, and no historical labels, model execution, outcome reports, ledger, or workflow logs were intentionally used as review evidence. Raw data were present in the ordinary repository checkout but were not loaded to calculate returns. The operator subsequently authorized continuation with an exposure filter. This is pre-v5-execution methodological evidence with disclosed prior-result exposure, not proof of an independent untouched holdout.

`scripts/review_design_view.py` replaces the inadequate keyword-only approach: mixed prose is metadata-only; only explicit structural JSON declarations are emitted; results/ledger paths are refused. It is an exposure-reduction aid, not a semantic guarantee for arbitrary future files or a retroactive eraser. The source manifest hashes reviewed sources and marks partial/screened reads honestly.

PR #161 was not opened, modified, merged, rebased onto, or cherry-picked. Only its branch ref was checked (`8170a8941c49a3f8213cf743ecd3cc69515a0d53` at the check). Its candidate inputs are not dependencies. This branch uses no unmerged accounting repair. No `signal-history` fetch, write, collection, or Alpha workflow was performed.

## 2. Reconstruction of the actual design

Sources are the v1–v4 preregistration documents and JSON, `alpha_opportunity_model.py`, `alpha_opportunity_features.py`, v2 evaluation, v3 decision, v4 eligibility, and accounting-quality implementation, at the base above. Legacy documents were inspected for design concepts with incomplete filtering; their performance is not supporting evidence.

| Layer | Actual contract and important distinction |
|---|---|
| Regional predecessor | `regional-alpha-model-v1` predicts within-date 126-session relative-return ranks, uses ranked features, Ridge and HGBR, annual expanding folds and a price-only ablation. That rank target cannot identify an absolute positive expected advantage. Its documents close its historical discovery budget. |
| Opportunity v1 | US/KR separate; 21/126 sessions; gross expected-relative-return and probability heads; a cost/uncertainty/edge/concentration gate with unspecified capacity inputs. It is a different question from rank prediction. |
| v2 | Keeps benchmark as outside option; requires expected net advantage, probability above half, and both fitted lower bounds. Moves notional/ADV/slippage budget out of the signal gate. |
| v3 | Correctly separates expected value from probability and fitted uncertainty. Sign of expected net alpha defines the descriptive surface; probability and uncertainty do not veto it. Identity/survivorship problems remain data constraints. |
| v4 | KR only; carries v3's economic contract and model/feature stack; adds explicit label eligibility, missingness disclosures and execution-snapshot rules. Two horizon claims, not four regional claims. The presence of an execution report is observed by filename only; this review did not open it. |
| Predictors | Both horizons: `relative126`, `acceleration21`, `vol63`, `logVolumeShock60`, `shockPersistence5d`, `volumePriceAlignment`. KR 126 adds OCF/net income, asset growth and total-liability growth. Earlier US 126 also admits capex intensity and share-count change. |
| Models | Ridge alpha 10 (lsqr); Logistic C 1 (L2/lbfgs); HGB learning rate .05, 100 iterations, 7 leaves, minimum leaf 50, L2 10, no early stopping, seed 42. Linear is primary; HGB complementary. No search. |
| Timing | Last regional session each week; information end-of-day; next session close entry; H additional sessions to exit. Date-only filings strictly earlier; label end strictly before annual fold cutoff. |
| Preprocessing | Signed-log accounting transformations; training date-weighted median/IQR, median imputation, missing indicators; all-missing training feature inactive until next refit. No full-sample fitting. |
| Weighting | Each date has weight one, shared across available training names. Repeated bootstrap date draws get separate cluster IDs. |
| Uncertainty | 200 training refits for fitted-value intervals; 2,000 evaluation moving-block draws; 26 weekly dates per block; whole-date clusters. At least 104 training dates, six evaluation blocks and five annual folds are inherited requirements. |
| Costs | Signal-date round-trip commission, full spread and dated sell tax. Benchmark charged zero in that comparison. These are an ex-ante friction estimate, not a fill simulation. |
| Universe | Opportunity research uses strictly prior observed S&P constituent snapshots / monthly KRX top-120 ranks. The older KR universe document describes a current-configured-name union; the regional/opportunity contract explicitly rejects that union. Do not conflate production/replay history with the newer research adapter. |
| Missing endpoints | No invented last-price or zero recovery. v4 removes observations whose audited dividend basis or terminal chain is unresolved and defers unaudited non-crossing cases to production. That rule avoids fabrication but does not establish random missingness. |

The foundation document's statement that some cash-flow items are structurally absent is not proof that omitted source concepts cannot be recovered. Coverage is an empirical input-only question for the independent repair, not a conclusion this review adopts from old prose.

## 3. Literature: findings, disputes, implementation and transfer limits

Published primary citations are in section 20. Each row yields a design decision; no paper's historical return magnitude is a target or parameter here.

| Primary work | Evidence class and lesson | Repository implication | What does not transfer |
|---|---|---|---|
| Fama–French 1993, 2015 [L1,L2] | Broad empirical evidence: size/value and profitability/investment help characterize average-return variation; factor explanations are model-dependent. | KEEP economic family grouping; add a secondary exposure diagnostic; audit missing value/profitability definitions. | Factor-model fit is not proof of stock-specific mispricing, implementable long-only alpha, or a validated KR cash-conversion proxy. |
| Jegadeesh–Titman 1993 [L3] | Broad evidence for intermediate-horizon momentum in their setting. | KEEP leadership and require a momentum-only baseline. | Does not validate this exact 126-day definition, acceleration signal, forecast horizon, or trading cost. |
| Harvey–Liu–Zhu 2016 [L4] | Multiple discovery opportunities inflate false positives. | MODIFY to a complete claim ledger and prospective confirmation; correct across primary cells. | Their significance discussion is not a universal magic t-statistic and does not reset the repository's prior research history. |
| McLean–Pontiff 2016 [L5] | Post-sample and post-publication decay; mechanisms include selection and informed trading. | KEEP pessimistic transfer assumptions and freeze prospective follow-up. | Do not multiply repository predictions by their estimated average decay or infer why any particular signal decays. |
| Hou–Xue–Zhang 2020 [L6] | Replication is sensitive to construction, microcap treatment and standards of evidence. | KEEP large/liquid initial universe; report weighting and membership definitions. | Their rejection rates do not prove this repository's features fail. |
| Chen–Zimmermann 2022 [L7] | Reproducible definitions/code can reproduce many published predictors. | MODIFY source-to-formula registry and semantic tests, especially liabilities and cash conversion. | Reproducing a published portfolio is not new out-of-sample economic evidence. |
| Jensen–Kelly–Pedersen 2023 [L8] | Global, economic-theme and Bayesian evidence gives a more favorable replication interpretation than some anomaly critiques. | KEEP family-level priors and separate regional feasibility; do not assume all anomalies false. | Their global evidence does not certify KR top-120 data or justify pooling US/KR. |
| Gu–Kelly–Xiu 2020 [L9] | Regularization and nonlinear interactions can aid prediction in their large US panel. | KEEP Ridge plus shallow HGB as a complementary functional form. | Their much longer, broader panel, features and portfolio results do not establish a need for deep nets here. |
| Feng–Giglio–Xiu 2020 [L10] | New-factor contribution must be assessed conditional on existing factors. | MODIFY to matched incremental baseline comparisons; EXCLUDE redundant family proliferation. | A stock-characteristic prediction ladder is not their formal factor-pricing test. |
| Novy-Marx–Velikov 2016 [L11] | Frictions, turnover and buy/hold rules materially change anomaly implementability. | KEEP dated costs; separate signal research from a later frozen turnover/holding policy. | Neither published capacity nor a generic cost rate identifies this user's order impact. |
| Lee–Swaminathan 2000 [L12] | Volume and momentum can have joint information. | KEEP a small attention family as hypotheses, not established local alpha. | Raw volume shocks are not direct investor attention or guaranteed liquidity. |
| Novy-Marx 2013 [L13] | Profitability definition matters; gross profitability is an economically motivated characteristic. | ADD_LATER a conventional profitability measure after source proof. | OCF/net income is not gross profits/assets and cannot borrow its empirical validation. |

**Contested:** the scale of the factor-zoo replication problem, the economic source of premiums (risk versus mispricing), persistence after publication, and the portability of ML gains. HXZ and Chen–Zimmermann/JKP answer different replication questions with different designs. Choosing the most optimistic paper would be another degree of freedom. The practical common ground is exact definitions, modest family count, valid timing, friction-aware interpretation and genuinely new confirmation.

## 4. Design-versus-literature decision matrix

Every recommendation has a problem, evidence, action, benefit, new risk and freeze requirement. `BLOCKED` means a missing source/contract prevents the associated claim, not that it disproves a hypothesis.

| ID / decision | Problem and evidence | Proposed change / benefit | New risk | Required before v5 outcomes? |
|---|---|---|---|---|
| R01 KEEP target | Rank-only success cannot establish advantage over the passive option (§2; L1,L3). | Gross total-return difference primary economic quantity; dated costs explicit. Preserves investor meaning. | Benchmark/style carry can look like skill. | Yes: exact endpoint and benchmark contract. |
| R02 MODIFY claims | v4 joins mean, rank and classification gates although v3 calls probability descriptive. | Separate expected-return, incremental-prediction, probability and deployability conclusions. Avoid irrelevant vetoes. | Easier cherry-picking unless all statuses reported. | Yes, complete conjunctions and multiplicity. |
| R03 MODIFY baselines | Training mean alone cannot isolate information beyond momentum (L9,L10). | Freeze matched ladder in §13. Identifies incremental information. | Extra comparisons can become a tournament. | Yes; one primary model, no replacement. |
| R04 MODIFY survivorship | Code invariance to a termination flag does not remove outcome-correlated audit selection. | Symmetric auditing and unconditional denominator; narrow claims if unresolved (§9). | Strict repair can reduce feasible scope. | Yes, before broad-universe claims. |
| R05 MODIFY accounting semantics | Total liabilities ≠ interest-bearing debt; OCF/NI changes interpretation around losses. Actual code (§8). | Rename in future registry; predefine denominator policy and sector comparability. | New definitions break historical comparability. | Yes; preserve old seals. |
| R06 KEEP small models | Current feature count and date depth do not justify an architecture tournament (L9). | Retain exact Logistic/Ridge/HGB defaults; no third class. | True signal may fall outside these forms. | Yes; conclusions restricted to tested forms. |
| R07 MODIFY overlap inference | A 26-week block is close to 126-session overlap; dependence may extend beyond it. | Horizon-aware 10/52-week primary blocks and 5/26/104-week fixed sensitivities (§11). | Fewer effective blocks; unstable long-block inference. | Yes; synthetic calibration and depth gate. |
| R08 KEEP chronological PIT | Current raw-before-derive, endpoint maturity and train-only transforms address concrete leakage routes. | Retain and test prefix invariance. | Expanding windows adapt slowly to breaks. | Yes; no rolling-window rescue. |
| R09 MODIFY regularization contract | Date weights sum to number of dates; fixed penalty has changing strength as history grows. | Document sum-loss objective explicitly; retain current scaling instead of silently renormalizing. | Shrinkage weakens with growing sample. | Yes; synthetic mechanics check only. |
| R10 MODIFY uncertainty labels | Bootstrap fitted values do not include all model/source risk or individual payoff dispersion. | Report conditional uncertainty, residual dispersion, numerical failures separately. | Users may still over-read intervals. | Yes. |
| R11 MODIFY stability | Joint annual positivity and classification gates mix questions and can waste power. | Fixed return-relevant stability disclosure/restriction (§11); classification standalone. | Less stringent than inherited omnibus gate. | Yes; explicitly a methodological change, no retrospective upgrade. |
| R12 BLOCKED costs/capacity | Positive volume is not a cash participation estimate (L11). | Input-only notional/ADV/slippage contract (§12); separate conditional signal evidence. | Assumed costs can still understate stress fills. | Yes for investability, not gross predictive evidence. |
| R13 MODIFY secondary factor diagnostic | Benchmark outperformance may be factor exposure (L1,L2,L10). | Freeze local factor set, historical-beta residual diagnostic (§14). | Factor misspecification and source revisions. | Protocol yes; unavailable regional factors BLOCKED. |
| R14 EXCLUDE expansion/search | Microcap evidence and ML papers do not justify universe/model shopping. | Keep universe; new study only with independent feasibility rationale. | Some real opportunities excluded. | Yes. |
| R15 MODIFY stopping | New version names can conceal repeated use of exposed history (L4,L5). | Full attempt ledger; one v5 run; prospective confirmation (§15). | Slower learning after genuine failures. | Yes. |
| R16 BLOCKED source families | Value, capex, shares, macro/flows have specific price, availability or coverage gaps. | KEEP exclusions where unproven; ADD_LATER only after independent source audit. | Omitted-variable risk. | Yes; freeze exact registry. |
| R17 KEEP layer separation | Candidate-date evidence is not a funded, overlapping-position strategy. | No portfolio/production conclusions; future construction study separately sealed. | Deployability remains unanswered. | Yes. |
| R18 MODIFY dates/snapshot | KR accounting source starts later than generic 2013 warmup; mutable repair cannot define a run midstream. | Input-only coverage selects start under a frozen rule; hash exact repaired snapshot before labels. | Shorter sample may lack power. | Yes; no automatic v5 now. |

## 5. Strengths worth retaining

Raw filing availability is checked before fiscal indexing/TTM construction; date-only releases use strict earlier dates. Explicit regional calendars and next-close entry avoid same-close trading on closing information. Date-balanced fitting prevents large cross-sections dominating. Entirely absent training features cannot activate inside a fold. Labels are purged by their endpoints. Bootstrap repetitions retain date cluster identity. Separate probability and return heads are acknowledged as distinct models. Prior versions are sealed, production is isolated, and failures need not produce a portfolio. These are useful controls with specific failure modes, not evidence that a profitable model exists.

## 6. Weaknesses and pseudo-rigor to remove

The current program risks mistaking procedural detail for identification: a hash proves bytes, not public availability; a preregistration proves commitment after its timestamp, not ignorance of earlier research; a deterministic exclusion is not a representative sample; five folds are not five independent experiments; and a positive fitted mean is a model statement, not established alpha.

The wording “alpha existence” should become “positive model-implied expected relative return” in a future interface/spec. A failure of the tested mapping cannot prove no signal exists. Likewise a model can beat a weak intercept forecast because the chosen universe differs from the benchmark, without distinguishing stocks within a date. Separate within-date information, absolute calibration and economic advantage.

## 7. Target and benchmark review

KEEP `Y(i,t,H) = TR(i; entry,exit) - TR(b_region; entry,exit)` in local currency, with identical scheduled endpoints, next-session-close entry and 21/126-session holding intervals. Ridge learns the gross conditional mean; the forecast cost estimate is subtracted transparently. Logistic may predict a separately defined cost-adjusted positive-outcome event; it does not reconstruct the Ridge payoff distribution.

Keep SPY for US and 069500.KS for KR as the predeclared investable passive comparators. KR top-120 and KOSPI200 ETF membership differ: disclose universe carry and maintain same-date universe contrasts. No better-looking replacement benchmark. ETF total returns already include internal fund drag; specify distribution reinvestment, withholding convention, FX exclusion, transaction fees and tax treatment consistently for stock and benchmark. No claim about this household's after-tax wealth without its tax/account contract.

Subtracting the same benchmark from all stocks on a date does not change their return rank. Thus rank IC cannot validate the choice or level of the benchmark. Positive relative means can reflect beta, style or sector exposure. The factor diagnostic answers a different question and must not replace the investable benchmark target.

KEEP two horizons, with 126 as the long-horizon economic question and 21 as the short-horizon question; both stay in the multiple-claim family. No extra 63-day window, no post-result promotion of whichever horizon works. A negative finding at these horizons says nothing definitive about untested horizons, but does not authorize testing them on the same sample as a rescue.

## 8. Feature-family review

`KEEP` below means retain a hypothesis in the small frozen candidate design, not that local predictive value has been established. `BLOCKED_BY_DATA` maps to the decision artifact's `BLOCKED`. No new family is activated by this review.

| Family / actual fields | Literature theme / economic rationale | Recommendation and PIT condition |
|---|---|---|
| Relative momentum / `relative126` | Momentum, gradual information diffusion [L3]. | KEEP. Ratios use only past total-return endpoints. Benchmark subtraction does not remove beta. Include a fitted momentum-only baseline. |
| `acceleration21` | Change in recent price leadership; possible momentum/reversal context. | KEEP as an explicitly weaker hypothesis, not a separate proven anomaly. Actual formula compares adjacent 21-session returns; no overlapping-window subtraction. No additional acceleration windows. |
| `vol63` | Volatility/risk and heterogeneity of expected payoffs [L9]. | KEEP as a context variable; do not interpret it as pure selection alpha. No inverse-volatility rescaling of the target or selection score. |
| `logVolumeShock60` | Attention/activity [L12]. | KEEP magnitude, backward-only denominator and split-consistent volume. Trading intensity can reflect supply shocks or noise as well as information. |
| `shockPersistence5d` | Duration of activity, not persistence of predictive success. | KEEP the existing five-day shock statistic; do not import legacy smoothed model rankings as a new predictor. |
| `volumePriceAlignment` | Joint price/volume behavior [L12]. | KEEP one interaction proxy. It is partly redundant with shock and price direction; no additional hand-built crosses. |
| `ocfToNetIncomePct` | Cash conversion/earnings composition, imperfect quality proxy. | KEEP family, MODIFY definition before v5: ratio only when NI > 0; nonpositive NI is missing plus existing missing indicator, with exclusions logged. Signed log does not solve denominator semantics. Keep lost coverage explicit. Do not call it gross profitability [L13]. |
| `assetGrowthPct` | Investment/asset expansion [L2]. | KEEP year-over-year same-stage comparison, positive prior assets, units and consolidation scope checked. Acquisitions can drive growth; no causal efficiency claim. |
| `debtGrowthPct` | Financing/balance-sheet expansion. | KEEP information but MODIFY name to `totalLiabilitiesGrowthPct` in future registry: KR reads 부채총계, not interest-bearing debt. No assertion of canonical debt issuance exposure. Retain old file unchanged. |
| `capexIntensityPct` | Investment intensity [L2]. | US KEEP only after sign/unit and denominator proof; KR BLOCKED_BY_DATA pending repaired coverage. Acquisition cash outflows must have a consistent positive magnitude; revenue <= 0 is missing. Do not automatically admit it because #161 later improves coverage. |
| `shareCountChangePct` | Issuance/dilution. | US KEEP subject to share-class and split consistency; KR BLOCKED_BY_DATA until independent public availability is proven. A split is not economic issuance. |
| Value: book/earnings/cash-flow yields | Valuation [L1,L2]. | ADD_LATER; activation BLOCKED_BY_DATA by dated as-traded price, per-share basis and identity alignment. Forward accumulated total-return Close is not a valuation denominator. |
| Conventional profitability, e.g. operating profitability/assets | Profitability [L2,L13]. | ADD_LATER as one family after an exact raw-account/PIT definition and coverage audit. Do not add multiple synonymous quality ratios to v5. |
| Liquidity/Amihud/cash turnover | Trading frictions and liquidity [L9,L11]. | BLOCKED_BY_DATA as a predictor/capacity input until actual cash traded value and dated share/price bases are sealed. Positive share volume does not resolve it. |
| FCF/net income beside OCF, capex | Algebraic overlap. | EXCLUDE from this design: substantial redundant construction, weak denominator semantics. |
| Macro, investor flow, shorting, ownership, analyst revisions | Potentially distinct information with different release/depth requirements. | BLOCKED_BY_DATA where depth/vintage/source proof absent; EXCLUDE from v5 core. No fresh collection in this PR. |
| Legacy calibrated score, persistence/confidence multiplier, dynamic breadth | Output/portfolio overlays, not new raw information. | EXCLUDE as new v5 features. KEEP their methodological separation of selection, costs and sizing. |

Additional accounting checks before activation: consolidated versus standalone basis; amendments with their own release timestamps; fiscal-stage consistency; currency/unit changes; stale filing age; financial-sector comparability. Without dated sector lineage, do not create a current-sector neutralized predictor or retroactive financial-sector exclusion. State that balance-sheet meanings are heterogeneous. The proposed NI/capex policies are economic-definition changes, not repairs to old results; their final registry must be frozen and newly named before v5.

## 9. Universe, survivorship and terminal economics

KEEP the dated large-cap universes for the first credible test. Personal capital can relax institutional capacity constraints, but it does not remove spreads, halts, limit moves or the need to sell. Monthly KRX observations provide a lagged top-120 investable rule, not daily exact historical index membership. Retain membership gaps, intermediate exits/re-entry and each security's identity interval. Missing prices remain in the scheduled denominator.

The pivotal distinction is between **signal-time eligibility** (known membership, tradability and feature availability) and **ex-post label measurement** (whether the economic payoff can be reconstructed). Future termination information may be needed to measure a label; it may not alter the original candidate set. If late reconstruction reveals that a dividend series was incomplete, it can invalidate a target; it cannot be presented as an exclusion that an investor knew at the signal date.

The v4 function has a defensible local property: changing an eventual-termination flag while holding economic evidence fixed should not change pre-termination eligibility. It does not establish the global missing-at-random assumption, because the audit cohort was selected around terminated securities. A convenience sample of persistent continuing names does not close that gap.

**Required v5 policy:** audit dividend basis/identity with the same criteria across the entire scheduled universe (including departed-but-trading names). Freeze the audit method and input snapshot before outcomes. Account for delisting cash, shares, multiple components, successor chains, fractions, payment dates, trading halts and distributions. Document whether cash held after settlement earns zero or a declared risk-free rate until the common horizon endpoint; whether successor shares are held through that endpoint; and how an unpaid/contested claim is valued. A final traded quote is not shareholder recovery. Unknown does not equal zero, benchmark return or last close.

When payoff reconstruction remains incomplete, publish a conditional **observable-label** analysis only if explicitly preregistered, with no full-universe/investability verdict. Keep every missing name-date and reason in the denominator. Predeclare sensitivity identification bounds only where externally justified payoff bounds exist; a blanket −100% to zero-return substitution is not a two-sided bound because upside is not finitely bounded by that rule. No complete-case renormalization dressed up as complete coverage. If valid bounds are unavailable, the broad claim is BLOCKED. A tiny missing fraction is not automatically harmless when selection can concentrate on those names.

Later universe expansion requires, before outcomes: dated listing/membership and share-class coverage, actual cash ADV/spread evidence, an explicit trade notional and participation cap, feasible terminal-payoff recovery, adequate calendar depth, a mechanism specific to the new universe, and a new claim budget plus fresh confirmation data. Strong microcap results in a paper alone do not satisfy this standard.

## 10. Models and training

The current stack is **appropriately conservative**, though no single fixed stack is guaranteed sufficient. Ridge supplies a low-variance additive conditional mean; Logistic supplies a separate event probability; shallow HGB can represent nonlinear thresholds and interactions. No clearly necessary third model class is missing for this small feature set. EXCLUDE neural nets, random forests, elastic-net grids and ensembles from v5; this is scope control, not a claim that they never work.

Retain annual expanding refits, weekly predictions and the published numerical settings. Do not weaken HGB capacity or increase it based on historical outcomes. No outcome-selected early stopping or hyperparameter calibration. The main comparison is full Ridge against matched simple baselines. HGB evidence is complementary and cannot rescue a failed primary claim.

The precise weight scale is part of a model: current weights sum to the number of dates, not rows or one. Under a sum-loss Ridge objective, the relative penalty diminishes as dates accumulate. KEEP that convention for continuity, record the objective and effective sample weight, and never normalize weights differently across library wrappers. That is a design choice, not automatically a bug. Fixed defaults are conservative commitments, not literature-derived optima.

MODIFY implementation in a future version so classifier one-class/convergence failure does not automatically suppress a valid Ridge forecast and vice versa. Existing `folds` and `fit_heads` require two classes and fit both heads together. Failure statuses must follow the separate claims in §11, not conceal numerical problems.

## 11. Validation, leakage and uncertainty

### Timing and leakage checklist

| Route | Required invariant / review finding |
|---|---|
| Overlapping labels | Training ends strictly before annual cutoff; entry/exit use exchange sessions. Nearby validation outcomes are dependent even though training is clean. Purging alone does not fix standard errors. |
| Extra embargo | KEEP exact maturity purge for past-only expanding training; no arbitrary additional 126-day gap. If future-side training were introduced, additional purging would be necessary; v5 does not introduce it. |
| Filings/restatements | Raw visibility filter before fiscal index and TTM; amendments never backdated; same-day date-only releases unavailable. Feature values are prefix-invariant when later filings are appended. |
| Membership | Strictly earlier observed snapshot; no current-member union, future deletion, or row set inferred from priced survivors. Observation timestamp is not automatically the actual publication timestamp. |
| Price adjustments | Splits/distributions after t cannot alter t's features. Verify price and volume normalization together; keep as-traded price distinct from a total-return index. |
| Benchmarks | Identical entry and exit sessions/basis; no nearest-date substitutions or independent quote-count horizons. Benchmark coverage failure invalidates the paired label. |
| Preprocessing | Fit every scaler/imputer/active-column decision on each training fold or bootstrap replicate. Validation missingness cannot activate a column. Missing indicators are not a repair of MNAR source coverage. |
| Fold schedule | Schedule determined by exchange calendar and input-only availability rule; no moving starts to the first convenient labelled date. Later failed folds remain visible. |
| Candidate evaluation | Select on predictions before seeing measurement availability; do not fill an unavailable selected name with a survivor. Zero-selection and all-selected dates have explicit denominators. |

### Proposed v5 evidence contract

All following are recommendations, never evaluations performed here. Keep the two KR horizon claims if KR is the only ready region. US joins only under a separately reviewed repaired data contract before freeze; the region count cannot change after results. Reserve familywise alpha 0.05 divided by the number of region×horizon **primary expected-return claims**. Use two-sided simultaneous intervals (KR-only: 97.5% each). HGB and probability results are descriptive unless separately allocated error budget before execution.

For a cell, test one fixed full Ridge rule. A **credible incremental expected-return finding** requires positive lower bounds for paired date-average squared-error improvement versus the training intercept and versus momentum-only, and positive lower bound for mean within-date rank correlation. They are conjunctive requirements for this one composite claim, not three opportunities to declare success. Report absolute calibration intercept/slope, within-date slope and tail errors; do not add independent significance gates for every correlated diagnostic. A positive slope is not calibration: intercept near zero and slope near one must be shown with intervals, without inventing an arbitrary acceptance band.

An **economic candidate finding** additionally requires the predeclared positive-net-forecast set to have a date-balanced net advantage lower bound above externally specified meaningful edge and a matched same-date selected-minus-whole-universe lower bound above zero. Use whole universe, not “nonpositive names” as the comparator, so all-selected dates remain defined (spread is zero). This measures conditional candidate-date opportunity, not a financed portfolio. With zero candidates, conditional advantage is undefined and opportunity evidence is absent; the calendar still contributes selection counts. Report the number/fraction of selected dates, name counts and all-selected dates. Require at least 52 selected weekly dates as a retained operational floor, not as proof of sufficient power; undefined bootstrap statistics must cause `DATA_INSUFFICIENT`, never silently discarded draws.

Probability quality (Brier, log loss, calibration bins and bias) is a **separate descriptive conclusion**. A flawed probability forecast cannot refute a correctly estimated expected return; success in classification cannot compensate for a failed economic mean. Mean/probability disagreement is natural for skewed payoffs. Fixed ten-bin ECE is sample- and bin-dependent; the inherited .05 cutoff is not a universal validity criterion and must not gate mean-return evidence.

Keep five annual folds as a minimum descriptive time-span floor. MODIFY stability to report every annual return-relevant estimate and the fraction positive; require economic candidate point estimates positive in both predeclared chronological halves for an economic claim. Define the split by the midpoint of the scheduled evaluation-date list before observing labels. Remove the omnibus “70% of years jointly positive on IC/Brier/MSE” veto. Annual folds overlap in training and outcomes, so they are not independent replications. If the primary interval clears but the half check fails, label the finding `PERIOD_CONCENTRATED`, not robust economic evidence. This deliberate power/robustness trade-off must be adopted before outcomes; it cannot rehabilitate v4.

### Dependence and intervals

Use complete weekly date clusters, never iid stock rows. Weekly 21-session labels overlap roughly five dates; 126-session labels roughly 26, with holidays handled by actual interval intersections. Proposed primary blocks: **10 weekly dates for 21-session claims and 52 for 126-session claims**, at least twice the approximate overlap. Fixed sensitivities: 5 and 26 respectively (overlap scale), and 104 for the long horizon if calendar depth permits. No choosing the interval that clears zero. Primary conclusion uses primary length; a sign reversal in a predeclared feasible sensitivity qualifies the claim as dependence-sensitive. If fewer than six primary blocks or five annual folds are available, report insufficient inference depth rather than shortening blocks to unlock a verdict.

These block choices are design recommendations, not a theorem or empirically optimal bandwidth. Dependence from shared shocks/annual model fits can last longer than mechanical label overlap. Before sealing v5, synthetic nulls must check false-positive behavior under cross-sectional shocks, serial dependence and overlapping aggregation; if inadequate, revise the method **before real outcomes**, not after. Use 10,000 evaluation draws, fixed seed, to reduce Monte Carlo noise in multiplicity-adjusted tails; this adds precision, not independent evidence. Keep the 200 training refits as an approximate fitted-value diagnostic and disclose their tail granularity. No bootstrap is a remedy for structural nonstationarity or bad inputs.

Forecast bootstrap intervals are conditional on the chosen model, features and observed history, and Ridge shrinkage introduces bias. They are not confidence guarantees for each security's true mean and not simultaneous across every candidate. Residual RMS is payoff dispersion, not uncertainty about the estimated mean. Evaluation block intervals from frozen OOF scores are conditional performance uncertainty; they do not fully propagate all possible model/research selection. Label these limits. Prospective locked predictions are the appropriate next confirmation.

## 12. Transaction costs, liquidity and personal capacity

KEEP the dated regional schedule as an auditable base assumption, but distinguish legal rates, broker commissions, assumed spread and modeled impact. This review verifies the repository formula, not legal correctness of every historical tax rate. Before a deployable claim, attach dated primary fee/tax sources, instrument/account scope and announcement/effective dates. A future tax change known only after signal cannot enter the ex-ante hurdle. Ex-post cash accounting, in a later portfolio study, uses actual dated costs and separately identifies forecast error.

The base formula `(2*commission + spread + signal-date sell tax)/10000` is a small-cost approximation for an isolated stock round trip, with zero benchmark transaction cost. It is conservative only in that comparator-cost dimension; it does **not** guarantee conservative total costs when spread or impact is understated. A doubled-cost disclosure cannot substitute for an impact model.

| Quantity | Outcome-independent resolution | Current review status / consequence |
|---|---|---|
| Trade notional Q | Operator capital mandate and maximum position size, in local currency; explicitly a scenario if not the actual mandate. Do not infer it from personal net worth. | BLOCKED: no approved order scenario for this review. |
| Cash ADV | Mean actual cash traded value over 20 completed local sessions, with units, timestamps and security identity. | BLOCKED until a sealed daily source exists. KRX snapshots listing a traded-value field do not prove a complete daily panel. |
| Participation fraction rho | Broker/exchange execution research, allowable execution duration and a conservative order policy; freeze independent of alpha. | BLOCKED pending evidence/policy; Q/ADV <= rho is not yet measurable. |
| Liquidity floor | At least Q/rho, plus independently justified minimum activity/spread/price limits. Fixed personal-capital ceiling, not “institutional scale.” | BLOCKED; positive daily volume is only a basic tradability proxy. |
| Spread/slippage | Dated quotes or an independently calibrated execution-cost source, no strategy-return fit; specify whether half-spread is already included. | BLOCKED for a measured investability claim. Avoid double-counting spread in slippage. |
| Meaningful edge delta_H | Operator's minimum compensation for effort/implementation/model risk over H, or a predeclared independently evidenced friction-error buffer; never chosen to get selected names. | BLOCKED for “economically meaningful” verdict until frozen. Zero still defines a positive predicted mean. |
| Concentration penalty | Portfolio utility/risk budget, e.g. a declared risk-aversion coefficient applied to incremental active variance at proposed weights. | BLOCKED without mandate/covariance contract; not a feature or veto on alpha existence. |

Thus v5 may report valid **gross predictive** evidence if price/fundamental integrity passes while implementability remains blocked. It may report net evidence conditional on explicit assumed friction, labelled accordingly. It may not call that an economically meaningful, investable opportunity until delta, Q, cash ADV and slippage are resolved. This avoids both v1's account-budget veto on statistical learning and v2's suggestion that small capital obviates measurement.

Candidate churn is not turnover; overlapping 126-session candidates cannot each receive the whole capital weekly. Later construction must freeze staggered holdings, exits, funding, concentration, correlation, limits and taxes. KEEP those outside this review. A buy/hold spread [L11] is a legitimate later construction hypothesis, not permission to reuse whichever prior hurdle looked best.

## 13. Baseline hierarchy for future registration

Fit and evaluate all rungs on the same regional dates, scheduled universe, maturity rule and source snapshot; freeze missingness handling. A restricted model may not obtain a more favorable sample. This is an attribution ladder, never a competition that selects the best historical model.

| ID | Fixed predictor | Purpose and claim status |
|---|---|---|
| B0 | Expanding training-date-balanced mean gross relative return; net-event prevalence separately. | Unconditional historical prediction. Primary full-model comparator. |
| B1 | Gross relative-return prediction identically zero (stock tracks the passive benchmark); show net prediction minus stated stock friction. | Simple benchmark-relative/no-information comparator; distinct from a financed benchmark position. Descriptive. |
| B2 | Ridge alpha 10 on `relative126` only, same transform/weight convention; optional corresponding Logistic purely descriptive. | Momentum-only conditional predictor. Primary incremental comparator. |
| B3 | Ridge alpha 10 on `relative126`, `vol63`, plus `assetGrowthPct` at 126 sessions only. | Compact economic-feature baseline using already allowed inputs. At 21 it has momentum/risk only. Descriptive attribution. |
| B4 | Ridge alpha 10 on the frozen full regional/horizon registry. | Sole primary expected-return model; B4−B0 and B4−B2 are required paired improvements. |
| B5 | Existing fixed shallow HGB on exactly B4's inputs. | Complementary nonlinear diagnostic; B5−B4 descriptive. Cannot substitute for B4. |

Report B3−B2 and B4−B3 descriptively: they separate a compact economic extension from remaining price/attention/accounting information. B3 is not claimed to replicate a published factor model. No separate tests for every feature, permutation ranking, subgroup or alternative missingness rule. If future authors want inferential claims for additional contrasts, include them in the error budget before freezing, never after reading the ladder.

## 14. Secondary factor-adjusted diagnostic

Recommend a predeclared explanatory diagnostic, **not a new training target**. For each stock and its benchmark, estimate daily excess-return exposures on the same trailing 756 regional sessions ending at signal t, requiring at least 504 paired observations. Use an intercept and local market, size, value, profitability, investment and momentum factors; unpenalized OLS with full-rank requirement. No factor deletion to resolve a singular fit: mark unavailable. Window/minimum are round trading-year conventions selected here without performance comparison, not optimized values.

At the future evaluation step only, residual daily active return is `(r_i-r_b) - (beta_i(t)-beta_b(t))' f_s`. Sum over the exact entry/exit interval for an **additive factor-residual diagnostic**, labelled as such; it is not exactly the simple compounded benchmark-relative target. Do not subtract the estimated intercept: that would remove the abnormal-return component being examined. Re-estimate neither beta nor factor choice using the forward window. Use date-cluster dependence treatment and match B4's candidate set; no secondary selection.

This indicates whether observed active payoffs align with the selected systematic exposures. It does not establish causal skill, arbitrage, equilibrium risk adjustment under the true model, or a tradeable factor hedge. Factor returns used only to evaluate future residuals are allowed ex-post, but factors used to estimate t's beta must use information available then. Current revised factor histories are not automatically historical-vintage safe. Require independently documented regional factor construction, local currency/risk-free rate, corporate-action basis, vintages and full timestamps. **KR full-factor diagnostic BLOCKED until that source contract exists.** Do not substitute US factors or quietly switch to CAPM and keep the same label. The diagnostic is non-gating and can remain unavailable without replacing the main objective.

## 15. Stopping rules after a future v5 result

1. Seal the review decisions, exact code/environment, feature registry, source hashes, data cutoff, horizons, claims, missingness policy and output schema before the first outcome query. Record all prior study IDs and exposure, including this review; a new ID is not a reset.
2. One authorized historical execution per frozen design. An identical retry is permitted for transport/runtime interruption; all attempts and artifacts remain. No automatic search or promotion.
3. Invalid provenance, numerical failure and insufficient data are distinct from a substantive negative result. A data repair needs an outcome-independent bug description and old/new input manifest. Never choose among repairs based on alpha.
4. A correction after outcomes is a disclosed amended exploratory analysis on an exposed sample. Preserve the defective run; do not rewrite it as untouched confirmatory evidence. A deterministic reproduction is not a new discovery chance.
5. On valid failure, close the registered hypothesis. Do not switch horizons, add/remove predictors, retune hyperparameters, lower edge/stability criteria, choose HGB instead, change benchmark, or shop universes. Publish all registered cells even if one succeeds.
6. On success, freeze the candidate mapping for prospective observation. Define the prospective horizon, data sufficiency and error-spending rule before collection; do not inspect repeatedly and stop at the first favorable result. No automatic production or concentrated-capital deployment.
7. Legitimate new research must state a new mechanism or independently documented new information source, why it was not simply selected from failure diagnostics, its complete researcher-choice ledger, and a new unexposed/prospective evaluation. The old sample may inform discovery, never be rebranded confirmation.

## 16. Decision summary

- **KEEP:** regional total-return difference, two horizons, next-close timing, separate regions where ready, small frozen model stack, date weighting, training-only transforms, exact maturity purge, immutable prior versions and signal/portfolio separation.
- **MODIFY:** semantic feature registry; baseline attribution; return versus probability conclusions; symmetric audit and conditional estimand; dependence/stability contract; uncertainty labels; source/period freeze; complete attempt ledger.
- **EXCLUDE:** third model class, feature zoo, post-failure rescue, retrospective universe expansion, contemporary sector labels, portfolio sizing in the signal test, point estimates called proven alpha.
- **BLOCKED:** unreconstructed total-return/terminal payoff coverage; US identity/price survivorship gaps absent a verified repair; as-traded cash ADV and slippage; approved edge/notional/risk mandate; local factor history; unsupported feature sources. These are review-time contract gaps, not fresh data measurements.

## 17. Exact recommendations for future v5

After this review is accepted and the KR foundation work finalized: identify a repaired input snapshot and perform input-only feasibility/coverage and semantic checks. Freeze the final registry (including NI policy and liabilities naming), source dates, start rule, class-specific failure behavior, B0–B5 ladder, primary conjunctions, block lengths/sensitivity/depth gates, dates/halves, multiplicity, and cost/edge assumptions. Test synthetic mechanics before touching real outcomes.

KR accounting should not be represented as observed in 2013–2014. Use a deterministic start rule: the first annual refit with the retained minimum history/matured-date requirements **and** all registered input-only coverage gates satisfied; document which families are actually active in every training fold. Require the same evaluation dates for baselines and full model. The source-availability audit, not alpha, determines whether the planned sample is long enough. A price-only earlier period is a separately labelled analysis, not a silent fallback for a blocked accounting study.

Create v5 only after (1) review acceptance, (2) KR foundation finalization, (3) exact repaired snapshot identification and (4) all outcome-independent choices frozen. No v5 file, seal or workflow is created by this PR. A foundation repair alone does not authorize execution. After v5 is separately reviewed/sealed, the operator may explicitly authorize its one execution. There is **no Alpha Action to run for this review**.

## 18. Intentionally unchanged

No production Alpha weights, selectors, entry state, Kelly, macro, benchmark instruments, v1–v4 sealed artifacts, old research verdicts or closed-study budgets are altered. No #161 implementation is copied. No return labels, scores, model fits, Alpha experiments, portfolio returns or historical outcome metrics are generated. No `signal-history` changes. The optional synthetic work here validates the reading filter, not a new alpha method.

## 19. Questions requiring new data, not stronger rhetoric

- Can all scheduled securities' dividends and terminal consideration be reconstructed consistently, including successors and payment timing? An accounting repair alone does not answer this.
- Which KR accounting fields remain available after strict receipt-time/identity and denominator checks, on the actual name-date universe rather than filing rows?
- Does daily as-traded cash value with validated price/volume units exist over every proposed date? A monthly schema does not establish daily coverage.
- Are historical US departed identities and their price endpoints resolved in the proposed new snapshot? This review did not fetch one.
- What notional, minimum meaningful compensation and execution constraints does the operator actually intend? No assumption from wealth or current share prices substitutes for this.
- Can a KR local factor panel meet the diagnostic's public-date and construction contract?
- Is enough calendar depth left for long-horizon inference after source-start, maturity and symmetric coverage restrictions? Synthetic mechanics cannot create missing independent history.

## 20. Exact primary references

Sources checked 2026-09-28. Publisher records/abstracts, author papers and official working-paper pages were used; unavailable full text was not represented as read in full. No literature result magnitudes are imported into thresholds. The design recommendations are this review's methodological judgments.

- **L1:** Fama, Eugene F., and Kenneth R. French (1993). “Common risk factors in the returns on stocks and bonds.” *Journal of Financial Economics* 33(1), 3–56. [doi:10.1016/0304-405X(93)90023-5](https://doi.org/10.1016/0304-405X%2893%2990023-5).
- **L2:** Fama, Eugene F., and Kenneth R. French (2015). “A five-factor asset pricing model.” *Journal of Financial Economics* 116(1), 1–22. [doi:10.1016/j.jfineco.2014.10.010](https://doi.org/10.1016/j.jfineco.2014.10.010).
- **L3:** Jegadeesh, Narasimhan, and Sheridan Titman (1993). “Returns to Buying Winners and Selling Losers: Implications for Stock Market Efficiency.” *Journal of Finance* 48(1), 65–91. [doi:10.1111/j.1540-6261.1993.tb04702.x](https://doi.org/10.1111/j.1540-6261.1993.tb04702.x); [paper](https://www.bauer.uh.edu/rsusmel/phd/jegadeesh-titman93.pdf).
- **L4:** Harvey, Campbell R., Yan Liu, and Heqing Zhu (2016). “… and the Cross-Section of Expected Returns.” *Review of Financial Studies* 29(1), 5–68. [doi:10.1093/rfs/hhv059](https://doi.org/10.1093/rfs/hhv059); [NBER version](https://www.nber.org/papers/w20592).
- **L5:** McLean, R. David, and Jeffrey Pontiff (2016). “Does Academic Research Destroy Stock Return Predictability?” *Journal of Finance* 71(1), 5–32. [doi:10.1111/jofi.12365](https://doi.org/10.1111/jofi.12365).
- **L6:** Hou, Kewei, Chen Xue, and Lu Zhang (2020). “Replicating Anomalies.” *Review of Financial Studies* 33(5), 2019–2133. [doi:10.1093/rfs/hhy131](https://doi.org/10.1093/rfs/hhy131); [NBER version](https://www.nber.org/papers/w23394).
- **L7:** Chen, Andrew Y., and Tom Zimmermann (2022). “Open Source Cross-Sectional Asset Pricing.” *Critical Finance Review* 11(2), 207–264. [doi:10.1561/104.00000112](https://doi.org/10.1561/104.00000112); [Federal Reserve working-paper page](https://www.federalreserve.gov/econres/feds/open-source-cross-sectional-asset-pricing.htm).
- **L8:** Jensen, Theis Ingerslev, Bryan Kelly, and Lasse Heje Pedersen (2023). “Is There a Replication Crisis in Finance?” *Journal of Finance* 78(5), 2465–2518. [doi:10.1111/jofi.13249](https://doi.org/10.1111/jofi.13249); [authors' project](https://www.jkpfactors.com/).
- **L9:** Gu, Shihao, Bryan Kelly, and Dacheng Xiu (2020). “Empirical Asset Pricing via Machine Learning.” *Review of Financial Studies* 33(5), 2223–2273. [doi:10.1093/rfs/hhaa009](https://doi.org/10.1093/rfs/hhaa009); [publisher full text](https://academic.oup.com/rfs/article/33/5/2223/5758276).
- **L10:** Feng, Guanhao, Stefano Giglio, and Dacheng Xiu (2020). “Taming the Factor Zoo: A Test of New Factors.” *Journal of Finance* 75(3), 1327–1370. [doi:10.1111/jofi.12883](https://doi.org/10.1111/jofi.12883); [author-hosted paper](https://dachxiu.chicagobooth.edu/download/ZOO.pdf).
- **L11:** Novy-Marx, Robert, and Mihail Velikov (2016). “A Taxonomy of Anomalies and Their Trading Costs.” *Review of Financial Studies* 29(1), 104–147. [doi:10.1093/rfs/hhv063](https://doi.org/10.1093/rfs/hhv063); [NBER version](https://www.nber.org/papers/w20721).
- **L12:** Lee, Charles M. C., and Bhaskaran Swaminathan (2000). “Price Momentum and Trading Volume.” *Journal of Finance* 55(5), 2017–2069. [doi:10.1111/0022-1082.00280](https://doi.org/10.1111/0022-1082.00280).
- **L13:** Novy-Marx, Robert (2013). “The other side of value: The gross profitability premium.” *Journal of Financial Economics* 108(1), 1–28. [doi:10.1016/j.jfineco.2013.01.003](https://doi.org/10.1016/j.jfineco.2013.01.003).

## 21. Validation and review boundaries

This is a source/code review, not a certification of every execution path. Filenames and selected code/spec sections were inspected; the manifest distinguishes screened document inspection from implementation inspection. Full `pytest` is not an appropriate blind-review gate here because existing tests include reads of checked-in real research reports. The user's synthetic-only constraint takes precedence over the blanket AGENTS test instruction. Do not run the historical suites or seed pipeline merely to attach an impressive test count.

The new filter's self-test uses only invented strings and temporary files and checks unknown-field suppression, prose suppression, deterministic output, results-path refusal and root confinement. JSON/schema consistency, source hashes, diff scope and Python compilation are checked without models or outcomes. Lint and environment limitations are recorded in the PR, not mistaken for substantive empirical validation. Existing sealed file bytes are compared against base via the changed-file list; no resealing occurs.
