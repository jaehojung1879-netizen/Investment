"""KR alpha discovery tournament v1 — the frozen registries (information, representations, targets, candidates, grid, protocol, verdict).

EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY. Every Korean date through the development cutoff is outcome-exposed and the component
anatomies (factor, industry, stock-within-industry, integrated portfolio and its post-outcome audit) were read before this was designed, so every
historical number this study can produce is DEVELOPMENT evidence about a model-selection PROCESS. Only prospective receipts can confirm it.

The object under test is a PROCESS, not a model: at each outer decision year, using only information that existed then, a bounded, pre-registered
tournament of model families x targets x hyperparameters x recency schemes is fitted and scored on purged inner folds; a frozen rule picks an
ensemble; a common past-only calibration turns the ensemble into an expected incremental return over the passive benchmark; disagreement and
calibration error shrink it; and a robust long-only fractional-Kelly allocator decides how much passive capital (069500.KS) each active name may
displace after costs. The concatenation of those untouched outer decisions is the result.

This module holds ONLY definitions. No I/O, no fit, no outcome. Every number in it is frozen into the spec and compared on every load.
"""
from __future__ import annotations

import itertools
import math

STUDY = "kr-alpha-discovery-tournament-v1"
SCIENTIFIC_STATUS = "EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY"
DEVELOPMENT_STATEMENT = (
    "Every KR date through the development cutoff is outcome-exposed, and the factor, industry, stock-within-industry and integrated-portfolio "
    "studies (and the post-outcome audit) were read before this tournament was designed. Every historical number it produces is DEVELOPMENT "
    "evidence about a pre-registered model-selection PROCESS, never validation; only prospective receipts written before outcomes can confirm it.")
OBJECTIVE = ("Maximize realistic long-run net geometric wealth growth from information this repository can actually know at each date, after "
             "costs, liquidity and estimation error, long-only and unlevered. 069500.KS (KODEX 200) is the passive opportunity cost and the default "
             "destination of capital: an active name must displace passive capital by clearing its cost and its uncertainty, and with no "
             "convincing active opportunity the book stays passive.")
RETURN_BASIS = "BENCHMARK_RELATIVE_ADJUSTED_INDEX_RETURN_PARTIAL_DISTRIBUTIONS"
BENCHMARK = "069500.KS"
PASSIVE = "PASSIVE_069500"
DEVELOPMENT_CUTOFF = "2026-09-14"
FEATURE_START = "2015-01-01"
EVALUATION_START = "2017-01-01"        # inherited anchor-calendar origin rule of the integrated study; the first OUTER decision is in OUTER_FIRST_YEAR
STRIDE_KR_SESSIONS = 21
OUTER_FIRST_YEAR = 2018                # first year with >= 36 months of feature history AND >= 104 matured weekly training dates (calendar rule)
PRIMARY_HORIZON = 126
SECONDARY_HORIZON = 252                # descriptive evaluation of the SAME H126 process predictions; never trained on, never a rescue
INNER_BLOCK_HORIZON = 21               # anchor-to-anchor block used by the inner economic score

# =======================================================================================================================================
# 4. Information audit (outcome-blind). Classes: A READY_PIT_SAFE, B READY_REPRESENTATION_DERIVED, C PARTIAL_HISTORY, D REVISED_HISTORY_NOT_PIT,
#    E CODE_EXISTS_DATA_NOT_READY, F NOT_AVAILABLE. Only A and B enter the tournament.
# =======================================================================================================================================
INFORMATION_CLASSES = {
    "A": "READY_AND_PIT_SAFE", "B": "READY_BUT_REPRESENTATION_MUST_BE_DERIVED", "C": "PARTIAL_HISTORY",
    "D": "REVISED_HISTORY_NOT_PIT_SAFE", "E": "COLLECTION_CODE_EXISTS_HISTORICAL_DATA_NOT_READY", "F": "NOT_AVAILABLE"}
USABLE_INFORMATION_CLASSES = ("A", "B")
INFORMATION_REGISTRY = {
    "PRICE_TREND": {"class": "A", "source": "replay-v16 Close (adjusted index, partial distributions) in the preserved raw artifact",
                    "fields": ["relative126", "momentum121", "ret21", "ret63", "dist252High", "ma200Distance"],
                    "note": "trailing windows end at the signal close; entry is the NEXT session close"},
    "PRICE_RISK": {"class": "A", "source": "replay-v16 Close", "fields": ["negativeDownsideVol126", "vol63", "beta252", "maxDrawdown252"]},
    "LIQUIDITY_ATTENTION": {"class": "B", "source": "KRX stk_bydd_trd tradingValue / volume / marketCap (preserved raw artifact)",
                            "fields": ["logAdv60", "logVolumeShock5_60", "logAmihud60", "logMarketCap"],
                            "note": "magnitude-preserving log shock, not a percentile only (alpha-information-inventory-v1 data map)"},
    "VALUATION": {"class": "B", "source": "repaired PIT DART accounting snapshot x signal-date KRX market cap",
                  "fields": ["bookToMarketProxy", "earningsYieldProxy", "ocfYieldProxy"],
                  "note": "issue-cap proxies; regional-alpha-model-v1 EXCLUDED every valuation yield, so this family is new to a learned model here"},
    "QUALITY_ACCOUNTING": {"class": "B", "source": "repaired PIT DART accounting snapshot",
                           "fields": ["netIncomeToAssets", "ocfToAssets", "negativeAccrualsToAssets", "ocfImprovementToAssets"],
                           "note": "receipt-date availability; KR fundamentals dark in 2015 and partial in 2016 (published, not imputed away)"},
    "INDUSTRY_STATE": {"class": "B", "source": "kr-industry-membership-foundation-v4 (14 groups, PIT reconstruction) x replay Close",
                       "fields": ["REL_MOM_63", "REL_MOM_126", "BREADTH_ABOVE_MA_126", "CONSTITUENT_DISPERSION_126", "TOP1_CAP_SHARE",
                                  "MEDIAN_LOG_ADV60", "DOWNSIDE_VOL_126", "stockMinusLooIndustry126"],
                       "note": "membership is DATA_FOUNDATION_INSUFFICIENT_V4 (no-change reconstruction; 22 terminal names unclassified); used as context"},
    "MARKET_STATE_PRICE": {"class": "A", "source": "069500.KS replay Close via the sealed kr_market_risk_overlay.state_at (past-only)",
                           "fields": ["marketTrendAdverse", "marketVol63"]},
    "MARKET_STATE_MACRO_FRED_VIX": {"class": "D", "reason": "FRED / VIX series carry a current/revised-history contract; 10 of 28 panel columns have no "
                                                          "ALFRED vintages (macro vintage invariants); a revised value may not masquerade as PIT"},
    "KR_MACRO_ECOS": {"class": "D", "reason": "an ECOS adapter exists (pipeline/ecos_macro.py) but no pinned release-vintage series; revised history only"},
    "KR_INVESTOR_FLOW": {"class": "E", "reason": "collector and probe exist; KRX portal answered LOGOUT/400 (BLOCKED_SOURCE); no historical ledger"},
    "KR_SHORT_SELLING": {"class": "E", "reason": "collector exists; source access unresolved; three regulatory regimes (bans 2020-03..2021-05, 2023-11..2025-03)"},
    "DART_OWNERSHIP_5PCT": {"class": "C", "reason": "BLOCKED_HISTORICAL_DEPTH: collected receipts span 2024-09-24..2026-09-23 only; prospective only"},
    "ANALYST_REVISIONS": {"class": "F", "reason": "no free PIT history in either region; FnGuide ToS-blocked"},
    "PIT_SECTOR_HISTORY_OFFICIAL": {"class": "F", "reason": "no dated official sector history; v4 reconstruction used as context only"},
    "TOTAL_SHAREHOLDER_RETURN": {"class": "C", "reason": "Yahoo distributions only where served; 22 delisted names have none; basis is partial"},
    "TERMINAL_CONSIDERATION": {"class": "C", "reason": "PARTIALLY_REPAIRED foundation; terminal economics unresolved for the 22 audited securities"},
}

# =======================================================================================================================================
# 5. Features and representations (target-agnostic; no hand-weighted blend)
# =======================================================================================================================================
SEALED_STOCK_FEATURES = ("bookToMarketProxy", "earningsYieldProxy", "ocfYieldProxy", "netIncomeToAssets", "ocfToAssets",
                         "negativeAccrualsToAssets", "relative126", "momentum121", "ocfImprovementToAssets", "negativeDownsideVol126", "logAdv60")
DERIVED_STOCK_FEATURES = ("ret21", "ret63", "dist252High", "ma200Distance", "vol63", "beta252", "maxDrawdown252", "logVolumeShock5_60",
                          "logAmihud60", "logMarketCap", "stockMinusLooIndustry126")
STOCK_FEATURES = SEALED_STOCK_FEATURES + DERIVED_STOCK_FEATURES
INDUSTRY_FEATURES = ("REL_MOM_63", "REL_MOM_126", "BREADTH_ABOVE_MA_126", "CONSTITUENT_DISPERSION_126", "TOP1_CAP_SHARE", "MEDIAN_LOG_ADV60",
                     "DOWNSIDE_VOL_126")
MARKET_FEATURES = ("marketTrendAdverse", "marketVol63")
REPRESENTATIONS = {
    "z": "robust cross-sectional z: (x - median) / (1.4826 * MAD) over the same signal date, clipped to [-5, 5]; NaN with < 10 finite values or MAD = 0",
    "p": "cross-sectional average-rank percentile in (0, 1) over the same signal date",
    "w": "within-industry average-rank percentile (same date and industry, >= 5 finite peers; eligible v4 industries only)",
    "m": "missingness indicator (1 when the raw signal-time value is not finite)",
    "i": "industry-state feature as the cross-industry percentile of the stock's industry (>= 5 ranked industries), mapped to members",
    "mkt": "date-level market state (trend-adverse flag, 63-session benchmark volatility); only trees and registered interactions can use it",
}
RAW_MAGNITUDE_RULE = ("raw cross-date levels are NOT a representation: they are non-stationary across a decade; magnitude within a date is "
                      "carried by the robust z, which preserves relative distances that a percentile discards")
ROBUST_Z_CLIP = 5.0
ROBUST_Z_MIN_FINITE = 10
WITHIN_INDUSTRY_MIN_PEERS = 5
INDUSTRY_MIN_RANKED = 5
INTERACTIONS = (                                     # linear families only; context interactions; never mined from outcomes
    ("z_relative126", "mkt_marketTrendAdverse"),
    ("z_negativeDownsideVol126", "mkt_marketTrendAdverse"),
    ("z_bookToMarketProxy", "ic_REL_MOM_126"),
    ("z_relative126", "ic_REL_MOM_126"),
)
LINEAR_IMPUTATION = "centred representations (z, p-0.5, w-0.5, i-0.5) are 0 where missing, beside an explicit missingness indicator; labels are never imputed"
TREE_IMPUTATION = "NaN passed through to the native missing-value branch of HistGradientBoosting"

# =======================================================================================================================================
# 6. Targets (model-learning targets; the ECONOMIC benchmark stays 069500.KS)
# =======================================================================================================================================
TARGETS = {
    "A_MAGNITUDE_VS_SAME_DATA_UNIVERSE": {
        "definition": "H126 stock return minus the signal-date-cap-weighted H126 return of the OTHER label-eligible PIT Top120 members",
        "minimumOtherNames": 50, "loss": "squared",
        "why": "the 069500.KS series carries an unexplained accrual (BENCHMARK_EXTERNAL_RECONCILIATION_UNRESOLVED); a same-data reference is used "
               "for LEARNING only and the benchmark is never repaired"},
    "B_RESIDUAL_VS_LOO_INDUSTRY": {
        "definition": "H126 stock return minus the cap-weighted leave-one-out industry return (sealed kr_stock_within_industry_anatomy.stock_targets, "
                      "CAP_WEIGHTED lens, STOCK_MINUS_LOO_INDUSTRY; every peer must be matured)", "loss": "squared"},
    "C_CROSS_SECTIONAL_RANK": {"definition": "within-date average-rank percentile of the H126 stock return among label-eligible members, minus 0.5",
                               "loss": "squared"},
    "D_TOP_QUINTILE_EVENT": {"definition": "1 when the within-date percentile of the H126 stock return exceeds 0.8, else 0", "loss": "squared",
                             "note": "a linear-probability / regression-tree fit of the event; the common calibration converts it to a return scale"},
}
TARGET_ORDER = tuple(TARGETS)
ECONOMIC_LABEL = "H126 stock return minus H126 069500.KS return over the SAME endpoints (target_from_sessions semantics); calibration and evaluation only"
MIN_NAMES_PER_LABEL_DATE = 20

# =======================================================================================================================================
# 10-11. Candidate registry and bounded hyperparameter grid (closed before execution)
# =======================================================================================================================================
POINTWISE_TARGETS = TARGET_ORDER
RANKER_TARGETS = ("C_CROSS_SECTIONAL_RANK", "B_RESIDUAL_VS_LOO_INDUSTRY")   # A induces the same within-date ORDER as C; D a coarsening of it
MODEL_FAMILIES = {
    "SHRUNK_LINEAR": {"estimator": "weighted ridge (closed form, training-only standardisation), date-balanced pooled cross-sectional regression",
                      "grid": {"alphaPerUnitWeight": [0.01, 0.1, 1.0]}, "targets": list(POINTWISE_TARGETS), "design": "linear"},
    "SPARSE_LINEAR": {"estimator": "sklearn ElasticNet(l1_ratio=0.5, selection='cyclic', max_iter=5000, tol=1e-4) on a training-standardised target",
                      "grid": {"alpha": [0.005, 0.02]}, "targets": list(POINTWISE_TARGETS), "design": "linear"},
    "SHALLOW_TREE": {"estimator": "sklearn HistGradientBoostingRegressor(learning_rate=0.05, max_iter=150, min_samples_leaf=200, l2_regularization=10, "
                                  "early_stopping=False, random_state=0), one thread",
                     "grid": {"max_depth": [2, 3]}, "targets": list(POINTWISE_TARGETS), "design": "tree"},
    "LEARNING_TO_RANK": {"estimator": "pairwise logistic ranker (RankNet-style, linear): within-date pairs from the top and bottom halves of the target, "
                                      "both orientations, sklearn LogisticRegression(fit_intercept=False, lbfgs, max_iter=1000)",
                         "grid": {"C": [0.1, 1.0]}, "targets": list(RANKER_TARGETS), "design": "linear",
                         "pairsPerDate": 50},
    "LATENT_FACTOR": {"estimator": "weighted PLS1 (NIPALS, deterministic) on the linear design: characteristic-conditioned latent directions",
                      "grid": {"n_components": [2, 4]}, "targets": list(POINTWISE_TARGETS), "design": "linear"},
    "ENSEMBLE": {"estimator": "equal-weight average of the calibrated expected incremental returns of the top-K validated candidates, at most one per "
                              "family", "grid": {}, "targets": [], "design": "none", "K": 3},
}
FAMILY_ORDER = tuple(MODEL_FAMILIES)
FITTED_FAMILIES = tuple(f for f in FAMILY_ORDER if f != "ENSEMBLE")
RECENCY_SCHEMES = {"NO_DECAY": None, "HALF_LIFE_5Y": 5.0, "HALF_LIFE_2Y": 2.0}
RECENCY_ORDER = tuple(RECENCY_SCHEMES)
EXCLUDED_METHODS = {
    "FAMA_MACBETH_PER_DATE_AVERAGING": "equivalent in spirit to the date-balanced pooled ridge (each date carries equal total weight); a second linear family "
                                       "would spend trials on a near-duplicate",
    "ROBUST_HUBER_REGRESSION": "robust z clipping already bounds feature leverage; outcome outliers are handled by rank / event targets C and D",
    "LIGHTGBM_XGBOOST": "lightgbm is pinned but its thread-dependent histogram build adds a determinism risk HistGradientBoosting (one thread) avoids "
                        "for no new idea",
    "SHALLOW_NEURAL_NETWORK": "about 120 names x ~600 weekly dates of heavily overlapping H126 labels is ~600 x 120 / 26 effective cross-sections; too "
                              "little effective sample for a network to earn its variance",
    "DEEP_NETWORK": "no effective sample; complexity for its own sake is excluded",
    "IPCA": "needs a balanced characteristic panel and alternating least squares with many latent dimensions; PLS1 on the same characteristics is the "
            "deterministic, auditable latent-factor challenger",
    "LISTWISE_RANKING": "pairwise covers relative-order learning with far fewer moving parts",
    "QUANTILE_REGRESSION": "uncertainty comes from calibration error and model disagreement, both past-only; a quantile head would be another "
                           "set of hyperparameters with no economic role in the allocator",
    "VALIDATION_WEIGHTED_CONVEX_ENSEMBLE": "weights fitted on two or three inner folds are noise; equal weights over a diverse top-K are the frozen rule",
    "DYNAMIC_MODEL_AVERAGING": "the annual outer re-selection already lets the process change family through history using past evidence only",
    "UNCONSTRAINED_MEAN_VARIANCE": "raw noisy forecasts into an unconstrained optimizer manufacture weights; the allocator shrinks, caps and costs",
}

# =======================================================================================================================================
# 8-9. Nested walk-forward
# =======================================================================================================================================
WALK_FORWARD = {
    "signalGrid": "last KR session of each completed calendar week (regional_alpha_features.weekly_grid) from FEATURE_START",
    "outer": {"refit": "annual: one outer fold per calendar year from OUTER_FIRST_YEAR; its information cutoff C_Y is the signal date of the year's first "
                       "anchor; every anchor of year Y uses the fold-Y process", "firstYear": OUTER_FIRST_YEAR,
              "trainingRule": "a row trains only if its H126 label exit date is STRICTLY before C_Y; labels of later exits do not exist for that fold",
              "untouchable": "nothing with an exit date >= C_Y enters fitting, inner selection, hyperparameters, recency choice, calibration or "
                             "uncertainty for fold Y"},
    "inner": {"blocks": 3, "validationShare": 0.5,
              "rule": "the most recent half of the fold's training signal dates is split into 3 contiguous equal validation blocks V1 < V2 < V3; for "
                      "Vj the inner training set is every row whose label exit is strictly before the FIRST entry date of Vj (purge) and whose "
                      "signal date is at least EMBARGO_SESSIONS sessions before the first signal of Vj (embargo); validation rows must themselves "
                      "exit before C_Y",
              "minimumTrainingDates": 52, "minimumValidationDates": 13, "minimumValidFolds": 2,
              "economicScoreFolds": "V2 and V3 (calibration for Vj is fitted on the candidate's OUT-OF-FOLD predictions of V1..Vj-1 only)"},
    "embargoSessions": 21,
    "noRandomSplit": True, "noShuffle": True,
    "standardisation": "fitted on the training rows of the fold only; representations are per-date cross-sectional transforms (no cross-date fit)",
}
EMBARGO_SESSIONS = WALK_FORWARD["embargoSessions"]
INNER_BLOCKS = WALK_FORWARD["inner"]["blocks"]
MIN_TRAIN_DATES = WALK_FORWARD["inner"]["minimumTrainingDates"]
MIN_VALID_DATES = WALK_FORWARD["inner"]["minimumValidationDates"]
MIN_VALID_FOLDS = WALK_FORWARD["inner"]["minimumValidFolds"]

# =======================================================================================================================================
# 13-14. Inner selection, ensemble, uncertainty, calibration
# =======================================================================================================================================
SELECTION = {
    "step1Stability": {"directionalIcFoldShare": "mean within-date Spearman IC (score vs realised H126 return rank) > 0 on at least ceil(2/3 x valid "
                                                 "folds) inner folds",
                       "calibration": "pooled HAC calibration slope of the candidate's out-of-fold predictions > 0 (no catastrophic calibration failure)",
                       "coverage": "predictions for at least 90% of label-eligible validation name-dates",
                       "economics": "finite inner economic score on every economic fold"},
    "step2Rank": "survivors ranked by mean inner economic score: annualised net log growth of (common translator portfolio) minus (100% passive) on "
                 "anchor-spaced 21-session blocks of V2 and V3; ties by candidate id",
    "step3Ensemble": "walk the ranked survivors and keep the best candidate of each family until K = 3 (diversity); equal weights on calibrated "
                     "expected incremental returns; 1 or 2 survivors -> an ensemble of those; 0 survivors -> PASSIVE_DEFAULT for that outer year",
    "K": 3, "minIcFoldShare": [2, 3], "minCoverage": 0.9, "minNamesPerIcDate": 20,
}
CALIBRATION = {
    "input": "s = within-date average-rank percentile of the candidate's raw prediction among scored names (native scales differ; a rank is common)",
    "perDate": "OLS slope b_t and intercept a_t of the ECONOMIC label (stock minus 069500.KS, H126) on (s - 0.5); dates with >= 20 names",
    "pooled": "b = mean b_t; SE(b) = Bartlett/Newey-West over the date series with lag ceil(126/5) = 26 weekly overlaps",
    "shrinkage": "b* = b x max(0, 1 - SE(b)^2 / b^2) when b > 0 else 0 (positive-part James-Stein toward zero)",
    "carry": "credited intercept = min(0, mean a_t): universe carry over the benchmark is never credited to the ranking; a lagging universe is charged",
    "mapping": "mu(s) = min(0, a) + b* x (s - 0.5); slope uncertainty sd(s) = SE(b) x |s - 0.5|",
    "noBuckets": "continuous in rank: no coarse bucket map recreates the alpha-reliability-v1 resolution problem",
    "cannotCreateAlpha": "|mu| is bounded by |min(0,a)| + b*/2 and b* <= b; a candidate with b <= 0 has no positive ordering credit",
}
CALIBRATION_HAC_LAG = math.ceil(PRIMARY_HORIZON / 5)
MIN_NAMES_PER_CALIBRATION_DATE = 20
UNCERTAINTY = {
    "disagreement": "population variance across ensemble members of their calibrated mu for the same name (0 with one member)",
    "calibration": "mean across members of sd(s)^2",
    "total": "sigma^2 = disagreement + calibration",
    "contraction": "kappa = mu^2 / (mu^2 + sigma^2) in [0, 1]; mu_post = kappa x mu; |mu_post| <= |mu|, sign preserved (asserted on every row)",
    "notCertainty": "kappa is a signal-to-noise contraction, never a probability of being right",
}

# =======================================================================================================================================
# 15-19. Common translator and allocator (passive core + long-only active overweights, no leverage)
# =======================================================================================================================================
PORTFOLIO = {  # stock execution values inherited unchanged from kr-model-overlay-portfolio-v1 / kr-integrated-alpha-portfolio-v1
    "singleNameCap": 0.3, "minimumAdvKrw": 3000000000.0, "maximumAdvFraction": 0.01, "referenceNavKrw": 100000000.0,
    "buyFixedCost": 0.0015, "sellFixedCost": 0.0045, "impactAtOnePercent": 0.0005, "advLookback": 60, "minimumDownsideVol": 0.01,
}
PASSIVE_LEG = {
    "instrument": BENCHMARK, "mark": "replay Close of 069500.KS (the repository's accepted return basis)",
    "costEachWay": 0.0015,
    "costAssumption": "ASSUMPTION_NOT_MEASURED: the ETF leg pays the inherited stock BUY-side fixed cost (15 bp) on buys AND sells as a stand-in for "
                      "commission and half-spread; no securities-transaction tax is applied to the ETF leg; no impact (KRW 100m reference NAV)",
    "benchmarkCaveat": "the 069500.KS series carries an unexplained accrual vs the same-data constituent reference (+4.53%/yr vs +1.85%/yr over "
                       "2017-2024, INTERNAL_CONSTRUCTION_ANOMALY_FOUND); holding it as the passive core inflates the passive leg for EVERY path and "
                       "therefore biases the active-vs-passive comparison AGAINST active capital; it is not repaired",
}
ALLOCATOR = {
    "objective": "maximise w'(mu_post - c_eb) - (1 / (2 lambda)) w' Sigma_e w - TC(w; w0) over active weights w >= 0",
    "kellyFraction": 0.5,
    "covariance": "Ledoit-Wolf shrinkage (sklearn.covariance.LedoitWolf) of 252 trailing daily ACTIVE returns (stock - 069500.KS) ending at the signal "
                  "date, scaled by 126; c_eb = sample covariance of each active return with the benchmark daily return, scaled by 126",
    "transactionCosts": "linear: buying stock i from the passive leg costs buy + passive sell; selling it back costs sell + passive buy; the ledger "
                        "additionally charges the inherited square-root impact",
    "constraints": ["w_i >= 0 (long-only)", "w_i <= min(singleNameCap, maximumAdvFraction x ADV60 / referenceNav)", "sum w <= 1 (passive = 1 - sum w)",
                    "no leverage, no short, no cash target"],
    "eligibility": "finite mu_post, tradable at the execution close (positive volume), ADV60 >= minimumAdvKrw, 252 finite trailing daily returns",
    "solver": "FISTA proximal gradient, step 1 / L with L = largest eigenvalue of Sigma_e / lambda, exact prox of the asymmetric cost + box with a "
              "bisected budget multiplier; 2000 iterations max, tolerance 1e-10; deterministic",
    "heldIneligible": "a held name without a current eligible forecast is targeted to 0 (sold) when executable; a non-executable order is deferred",
    "breadth": "the number of active names is whatever the objective chooses: no Top-N, no minimum, no fixed five",
}
ALLOCATOR_MAX_ITER = 2000
ALLOCATOR_TOL = 1e-10
COVARIANCE_LOOKBACK = 252
PORTFOLIO_TRANSLATORS = {
    "BASELINE_0_PASSIVE": "100% 069500.KS from the first outer anchor, never traded",
    "BASELINE_1_EQUAL_WEIGHT_SLEEVE": "the names whose mu_post exceeds their round-trip active cost (the primary's own admission rule, no new "
                                      "threshold), each at min(1/n, its cap), passive residual",
    "PRIMARY_ROBUST_KELLY": "the allocator above",
}
DECISION_FOCUSED_CHALLENGER = {
    "status": "QUARANTINED_CHALLENGER_CANNOT_CHANGE_THE_VERDICT",
    "policy": "parametric portfolio policy (Brandt / Santa-Clara / Valkanov style), long-only: active weight w_i = sigmoid(theta0 + z_i' theta) / N_t "
              "(so sum w <= 1), capped at the name cap; passive residual",
    "training": "maximise mean over training rows' dates of log(1 + sum_i w_i (e_i - roundTripCost)) - gamma ||theta||^2 on the H126 economic label of "
                "the OUTER training set only (same exit-before-cutoff rule), L-BFGS from theta = 0, theta0 = -2",
    "gamma": 0.001, "theta0Start": -2.0,
    "sameAs": "same inputs (linear design), costs, constraints, outer walk-forward and evaluation as the primary",
    "concentrationDiagnostic": "max active weight, active HHI and HHI x n per anchor are reported; the construction bounds any weight by 1/N_t",
}
DFL_GAMMA = DECISION_FOCUSED_CHALLENGER["gamma"]
DFL_THETA0 = DECISION_FOCUSED_CHALLENGER["theta0Start"]

# =======================================================================================================================================
# 12, 21-24. Evaluation, stresses, multiplicity and the frozen verdict
# =======================================================================================================================================
PERIODS = {"2017_2020": ("2017-01-01", "2020-12-31"), "2021_2024": ("2021-01-01", "2024-12-31"), "2025": ("2025-01-01", "2025-12-31"),
           "2026_TO_CUTOFF": ("2026-01-01", DEVELOPMENT_CUTOFF)}
PERIOD_NOTE = "outer decisions start in 2018, so the 2017_2020 slice holds 2018-2020 sessions only (registered before outcomes)"
STRESSES = {"BASE": {"costMultiplier": 1.0, "advFractionMultiplier": 1.0, "executionDelaySessions": 0},
            "COST_X2": {"costMultiplier": 2.0, "advFractionMultiplier": 1.0, "executionDelaySessions": 0},
            "LIQUIDITY_HAIRCUT_HALF_ADV": {"costMultiplier": 1.0, "advFractionMultiplier": 0.5, "executionDelaySessions": 0},
            "EXECUTION_DELAY_ONE_SESSION": {"costMultiplier": 1.0, "advFractionMultiplier": 1.0, "executionDelaySessions": 1}}
DESCRIPTIVE_DIAGNOSTICS = ("LEAVE_LARGEST_CONTRIBUTOR_OUT", "PERIOD_SLICES", "SECONDARY_H252_PREDICTION", "OPTIMIZER_VALUE_VS_BASELINE_1",
                           "DECISION_FOCUSED_CHALLENGER", "CLASSIFICATION_ACCURACY_DIAGNOSTIC_ONLY")
NO_BESPOKE_RESCUE = "no named-security exclusion (the Samsung / SK Hynix exclusion was already studied in the post-outcome audit)"
MULTIPLICITY = {
    "trialLedger": "every family x hyperparameter x target x recency configuration (fitted in every outer fold), plus the ensemble rule, the "
                   "decision-focused challenger and the two non-passive translators",
    "deflatedSharpe": "Bailey & Lopez de Prado DSR of the primary's non-overlapping 21-session active log-return blocks; N = total effective trials; "
                      "variance of trial Sharpes from every configuration's outer cheap-translator blocks",
    "pbo": "CSCV probability of backtest overfitting over the configuration universe's outer cheap-translator block returns, S = 16 contiguous groups",
    "spa": "Hansen SPA (consistent p-value) that no strategy in {primary, baseline 1, challenger, every configuration} beats passive; stationary "
           "bootstrap, mean block 6 blocks (126 / 21), B = 2000, fixed seed",
    "bootstrap": "moving-block bootstrap (block 126 sessions, B = 2000, fixed seed) of the daily log-growth difference primary minus passive",
    "cheapTranslator": "per configuration and outer anchor: equal-weight top-quintile of its predictions held 21 sessions, minus passive; gross; used "
                       "ONLY to give PBO / DSR / SPA a configuration universe, never to select",
    "assumptions": "DSR treats the block series as i.i.d. with skew/kurtosis; PBO assumes exchangeable groups; SPA uses a stationary bootstrap for the "
                   "126-session overlap. Overlapping daily series are never given naive p-values",
}
BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_BLOCK_SESSIONS = 126
SPA_MEAN_BLOCK = 6
PBO_GROUPS = 16
RANDOM_SEED = 20261006
VERDICTS = {
    "A": "ROBUST_ACTIVE_VALUE_FOUND", "B": "WEAK_OR_REGIME_DEPENDENT_VALUE", "C": "PREDICTIVE_SIGNAL_WITHOUT_ECONOMIC_VALUE",
    "D": "INFORMATION_LIMITED", "E": "BLOCKED_BY_DATA_INTEGRITY"}
VERDICT_RULES = {
    "G": "net annualised log-growth difference, primary minus 100% passive, over every session from the first outer anchor to the cutoff (pp/yr)",
    "E": "the primary or passive path is incomplete (unresolved held mark), the frozen identity moved during the run, or fewer than 80% of outer "
         "anchors had a valid signal-time cross-section",
    "A": ["G >= 1.0 pp/yr", "block-bootstrap 95% lower bound of G > 0", "G under COST_X2 > 0", "G > 0 in at least 3 of the 4 registered periods",
          "G with the largest single contributor removed > 0", "DSR >= 0.95", "SPA p-value of the primary vs passive <= 0.05", "PBO <= 0.5",
          "outer ensemble rank IC HAC 95% lower bound > 0"],
    "B": "G > 0 and not A",
    "C": "G <= 0 and the outer ensemble rank IC HAC 95% lower bound > 0 (forecast information that costs, risk or transfer destroy)",
    "D": "G <= 0 and no predictive evidence (outer rank IC lower bound <= 0) -> INFORMATION_LIMITED",
    "order": "E is checked first; then A, B, C, D exactly as written; nothing is decided after the numbers exist",
}
MEANINGFUL_G_PP = 1.0
DSR_MIN = 0.95
SPA_MAX_P = 0.05
PBO_MAX = 0.5
MIN_PERIODS_POSITIVE = 3
MIN_SIGNAL_COVERAGE_PERCENT = 80
OUTER_IC_HAC_LAG = math.ceil(PRIMARY_HORIZON / STRIDE_KR_SESSIONS)
STOP_RULES = {
    "INFORMATION_LIMITED": "historical model search on THIS information set closes permanently: no Expected Alpha v2 on the same data, no further "
                           "algorithms, no weight moves, no horizon change, no rescue. The next step is NEW information whose PIT history is "
                           "genuinely ready (KR investor flow, DART 5% ownership, short selling, a vintage-safe KR macro context)",
    "ANY_VERDICT": "no v1.1, no re-seed, no grid widening, no target or horizon added; the frozen process issues prospective receipts; development "
                   "evidence is never promotion",
}


# =======================================================================================================================================
# The trial ledger
# =======================================================================================================================================
def candidate_id(family, target, recency, params):
    body = ",".join(f"{k}={params[k]}" for k in sorted(params))
    return f"{family}|{target}|{recency}|{body}"


def candidate_registry():
    """Every fitted configuration, in a fixed order. Each entry: {id, family, target, recency, params}."""
    out = []
    for family in FITTED_FAMILIES:
        spec = MODEL_FAMILIES[family]
        keys = sorted(spec["grid"])
        for target in spec["targets"]:
            for recency in RECENCY_ORDER:
                for values in itertools.product(*(spec["grid"][k] for k in keys)):
                    params = dict(zip(keys, values))
                    out.append({"id": candidate_id(family, target, recency, params), "family": family, "target": target, "recency": recency,
                                "params": params})
    ids = [c["id"] for c in out]
    if len(set(ids)) != len(ids):
        raise ValueError("DUPLICATE_CANDIDATE_ID")
    return out


def trial_ledger(outer_folds=None):
    """Counts that every multiplicity diagnostic is paid with. `outer_folds` (optional) multiplies the fitted-configuration count by the number of
    outer refits, which is the number of distinct fitted models the process produces."""
    registry = candidate_registry()
    per_family = {f: sum(1 for c in registry if c["family"] == f) for f in FITTED_FAMILIES}
    hp = {f: int(math.prod(len(v) for v in MODEL_FAMILIES[f]["grid"].values())) for f in FITTED_FAMILIES}
    targets_used = sorted({c["target"] for c in registry})
    configurations = len(registry)
    extra = {"ensembleRule": 1, "decisionFocusedChallenger": 1, "baseline1Translator": 1}
    out = {"modelFamilies": len(FAMILY_ORDER), "fittedModelFamilies": len(FITTED_FAMILIES), "hyperparameterConfigurationsPerFamily": hp,
           "hyperparameterConfigurations": sum(hp.values()), "targetArchitectures": len(targets_used), "recencySchemes": len(RECENCY_ORDER),
           "configurationsPerFamily": per_family, "fittedConfigurations": configurations, "otherTrials": extra,
           "totalEffectiveTrials": configurations + sum(extra.values())}
    if outer_folds is not None:
        out["outerFolds"] = int(outer_folds)
        out["fittedModelsAcrossOuterFolds"] = configurations * int(outer_folds) * (1 + INNER_BLOCKS)
    return out


def duplicate_research_audit():
    """The gate the brief requires BEFORE any implementation: does this study differ MATERIALLY from what is already closed?"""
    return {
        "closedPredecessors": {
            "regional-alpha-model-v1": {"status": "EXECUTED / NO_MODEL_EVIDENCE (KR and US) / HISTORICAL_DISCOVERY_CLOSED_ON_EXISTING_FEATURE_SET",
                                        "matrix": "31 features: price/trend/risk percentiles + fundamental LEVEL (roe, margins, D/E, growth) + four "
                                                  "fundamental-acceleration deltas + KR market cap; valuation yields EXCLUDED; no sector/industry",
                                        "target": "within-date percentile rank of 126D return minus benchmark", "models": "Ridge alpha=10, one HGBR",
                                        "selection": "none (two fixed models)", "decision": "IC / quintile classification; no portfolio"},
            "kr-model-overlay-portfolio-v1": {"status": "DEVELOPMENT_REJECT",
                                              "matrix": "11 sealed KR features (value/quality/catalyst/risk) + 4 fixed family interactions",
                                              "target": "stock minus 069500 at H126/H252", "models": "Ridge 10 + one HGB, no search",
                                              "decision": "top-5 inverse-downside-vol book, fixed overlay"},
            "alpha-opportunity-model-v5": {"status": "INCONCLUSIVE (KR H21, H126)", "decision": "no portfolio fields"},
            "kr-integrated-alpha-portfolio-v1": {"status": "CONSUMED; INDUSTRY_LAYER_DEVELOPMENT_SUPPORTED; NO_UNAMBIGUOUS_FINAL_ARCHITECTURE",
                                                 "decision": "hand-weighted 50/50 scores, fixed top-5"},
        },
        "materialDifferences": {
            "informationRepresentation": "industry-state context (8 v4-membership features incl. leave-one-out industry momentum), within-industry "
                                         "percentiles, robust z beside percentiles (magnitude kept), magnitude-preserving liquidity shock, a past-only "
                                         "market state, and VALUATION YIELDS that regional-alpha-model-v1 excluded outright",
            "targets": "four frozen target architectures including the leave-one-out industry residual (B) and the tail event (D); "
                       "regional-alpha-model-v1 had one rank target",
            "modelSelectionArchitecture": "a nested, purged walk-forward tournament over 5 fitted families x 4 targets x 3 recency schemes with an "
                                          "inner economic selection rule and a diversity-constrained ensemble; no predecessor selected anything",
            "objective": "net geometric wealth over a passive core via an uncertainty-shrunk fractional-Kelly allocator with dynamic breadth; "
                         "predecessors used IC or a fixed top-5 book",
        },
        "notDifferent": "NO genuinely new raw information source: investor flow, ownership, short selling and vintage-safe macro are not ready. Every "
                        "raw input here was already measured by an anatomy or a model study. An INFORMATION_LIMITED verdict therefore closes model "
                        "search on THIS information set rather than suggesting another algorithm.",
        "conclusion": "MATERIALLY_DIFFERENT_IN_REPRESENTATION_TARGET_SELECTION_AND_OBJECTIVE_NOT_IN_RAW_INFORMATION",
    }
