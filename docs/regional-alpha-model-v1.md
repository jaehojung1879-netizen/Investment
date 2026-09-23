# regional-alpha-model-v1 — frozen research specification

Base: main `6fc26a9be616cba0f259fbb6cbf4aa9b7039a8cd`.
Evidence: **DISCOVERY_ONLY**, promotionEligible=false. Replay-v16 has already
been exposed to repeated research. Annual walk-forward prevents training leakage;
it does not create an untouched sample. Production is unchanged.

## Architecture decision before outcomes

MODEL RULE → MODEL FEATURE. This is a new conditional ordering function, not a
fifth factor or a factor-weight change. US_ALPHA_MODEL_V1 and KR_ALPHA_MODEL_V1
are fitted separately, never pooled. Each region consumes its one remaining
historical discovery budget in this study. The previously proposed standalone
US breadth and KR FX-beta studies are superseded, not run first.
After this study HISTORICAL_ALPHA_DISCOVERY_PHASE=CLOSED regardless of outcome.
No parameter search, third algorithm, follow-up factor discovery, or automatic promotion.

## Stage -1: source audit decisions

The machine-readable manifest enumerates every candidate, canonical field,
formula, transformation, eligibility decision, source, and measured coverage.
Feature eligibility is frozen before any forward outcome is constructed.

- Price: sealed replay-v16 forward total-return Close, supplied by Yahoo for US
  and FDR/KRX routes with Yahoo distributions for KR. Reuse historical_replay
  price functions; features end at the as-of date. Source objects are hashed.
- Universe: the existing membership builder erases intermediate exits on
  re-entry, and KR adds today's configured names. Neither behavior is admitted.
  US uses each dated upstream constituents CSV, pinned to source commit
  `3b2bb60e6269439cd75541eded6281c48e7681d1`; a snapshot becomes usable the next
  calendar day after its commit (conservative daily publication convention).
  KR uses latest strictly prior raw KRX monthly snapshot, top 120 by its dated
  rank, without today's configured names. These are snapshot-observed universes,
  not claims of exact index-effective-date reconstruction. Missing prices are
  reported against the whole source universe. No future membership filtering.
- Sector: current static sectors.py has no dated provenance. Sector metadata
  remains null; sector leadership and legacy sector-neutral percentiles/rawAlpha
  are DATA_LINEAGE_UNRESOLVED and excluded. No approximate four-factor replacement.
- Fundamentals: only FundamentalStore canonical records that can be independently
  reproduced from raw filings visible at that record's availableFrom are admitted.
  Mixed-receipt DART records are withheld. Original canonical fields are retained
  only when matched to the visible-only derivation, never silently replaced.
  All four acceleration deltas use the unchanged resolve_filing_pair and
  compute_deltas, with the same eligibility rules for all four components.
- Valuation yields: sealed Close is a forward total-return index, not the
  as-traded price needed for a filing's per-share numerator. No substitute field
  or invented price reconstruction: earnings/book/FCF yields excluded.
- Forward yield and US market cap: historical source unconfirmed; excluded.
  KR marketCap is the latest prior KRX snapshot's actual MKTCAP, with snapshot
  date retained; no interpolation to an imaginary current-day capitalization.
- FX: replay_recovery.resolve_fx_fixings treats observationDate as publication.
  No release timestamp/vintage in sealed DEXKOUS observations verifies that claim.
  Signed/absolute 26-week FX beta are pre-registered but excluded with
  DATA_LINEAGE_UNRESOLVED. Macro is not an alpha input; ECOS is not a blocker.
- Volume: sealed forward split-normalized Volume; trailing 5/60 ratio only.

## Fixed features and transformations

Price candidates: returns 21/63/126/252 sessions; repository mom6 (125 intervals)
and mom121 (positions -21/-252, minimum 273 observations); arithmetic own-benchmark
relative returns at the same endpoints, 12-1 relative momentum; distance to trailing
252-session high; repository RSI14; 200-session MA distance; vol20/60/252,
downsideVol252, maxDD252, beta252, volumeSurge5_60. US adds fraction of positive
weekly own-benchmark excess returns across 52 completed weeks, requiring all 52.
Fundamentals: roe, operatingMargin, profitMargin, debtToEquity, earningsGrowth and
all four pre-registered deltas. KR adds lagged snapshot marketCap.
All eligible numeric features use within-date/region average percentile ranks.
Explicit missing indicators accompany every feature. No ticker, date, year,
region, sector, label-maturity, or macro value is a predictive input.
A feature entirely absent from a training fold is omitted for that fold only,
recorded, and cannot become active mid-fold; there is no fabricated median zero.

## Fixed fitting

Target: within-date/region percentile rank of stock 126D total return minus
SPY (US) / 069500.KS KODEX200 (KR), minus 0.5. Existing outcome machinery
counts observed stock quotes; admit a label only when its endpoint equals
as-of plus exactly 126 benchmark sessions. Missing/halted paths with a longer
observed-quote horizon are unmeasurable, not silently relabeled. Date weights sum to exactly 1.
Annual expanding fits only. At least 36 months of feature history and 104
matured training dates with >=10 names each. Training labels must satisfy
outcomeEndDate < validationStartDate. ValidationStartDate is the first scheduled
regional evaluation date in the year, not the first date with a measurable label.
The weekly date is each region's last session of the completed calendar week.
No random splitting; no post-validation embargo needed with past-only training.

Ridge: alpha=10.0, training-fold median imputation, explicit missing indicators,
training-only StandardScaler, sample_weight=1/n_date. HGBR primary:
learning_rate=.05, max_iter=100, max_leaf_nodes=7, min_samples_leaf=50,
l2_regularization=10, early_stopping=false, random_state=42. One thread.
Only ablation: HGBR_PRICE_ONLY, excludes all fundamental and size features.
No fitted parameter/window changes after outcomes; no AutoML/deep learning.

## Fixed measurement and classification

Date-level Spearman IC; reuse kelly_portfolio._newey_west_stats with 126D
horizon and observation-spacing-aware bandwidth. Report SE, normal two-sided p,
95% CI, dates, HAC effective dates and bandwidth limitation. Never pool regions.
Quintiles use average predicted-score ranks (ties never broken by outcomes);
monotonicity is share of four adjacent strict increasing steps; 'reasonably
monotone' is fixed at >=.75. All five means must exist. Constant-score dates have
no measurable IC/quintile spread. Top10 uses equal weights and ticker solely as
a deterministic tie break. Selection precedes outcome availability; any missing
Top10 label makes that date's Top10 unmeasurable (never replace with survivors).
No fees or construction overlay: Top10 is a gross signal diagnostic, not a book.
Also report Top10 minus equal-weight universe to distinguish carry from selection.

A: IC>0, lower CI>0, spread>0, monotonicity>=.75, positiveFoldFraction>=.70:
STRONG_DISCOVERY_ONLY. B: IC>0, spread>0, >.5 folds positive, CI includes zero:
PROMISING_BUT_UNCERTAIN_DISCOVERY. All other measurable cases C:
NO_MODEL_EVIDENCE (including positive but insufficiently stable patterns not
covered by A/B). Missing measurement is NOT_EVALUABLE, never C or numeric zero.
Baselines on identical validation dates/universe: mom6, mom121, relative126,
US breadth; four-factor/FX unavailable when lineage fails. KR marketCap Top10
only where prior dated KRX MKTCAP exists; US PIT_MARKET_CAP_BASELINE_UNAVAILABLE.
Annual folds including negative years are published. Paired date-level IC gaps
with HAC intervals compare nonlinear vs linear, full vs price-only and baselines.
Coefficients/importance are diagnostic only and never select new features.

## Operational separation and dependencies

No changes to production config, FACTOR_WEIGHTS, CHAMPION, selector, Kelly,
entry, live/paper trading, rotation, or macro budgets. No sealed ledger writes.
ECOS fetch/IDs and KR live Yahoo price asymmetry remain promotion dependencies.
A/B warrants a future prospective append-only seal; C does not schedule one.
Prospective schema: generatedAt, asOfDate, region, ticker, modelVersion,
featureVersion, modelDigest, featureDigest, predictionScore, rankPercentile,
trainingCutoff, gitSHA. Evaluate only after 126D maturity; never rewrite signals.

## Reproduction

The runner has separate feature audit/freeze and fit/evaluate stages, and writes
only outside its sealed input tree. Two independent full executions must yield
byte-identical manifest, feature matrix, predictions, metrics and report. No
wall-clock timestamps in historical artifacts. Pin requirements and thread count.
See the results report for actual execution status, not assumptions of completion.
