# Alpha information inventory v1 — research map

> **Read-only summary of prior research already published in this repository.
> No new correlation, IC, Rank IC, backtest, or return-relationship was
> computed to produce this document.** Every number below is quoted from
> `AGENTS.md`'s own invariants sections or from the checked-in
> `docs/*.md` / `docs/results/*.md` reports, cross-checked against the
> module source for consistency. This document exists so that the next study
> can tell, before writing one line of new code, which hypotheses this
> repository has already tested and settled, which are pre-registered but
> never executed, and which are genuinely still open.

---

## 1. Full study/module table

Legend for **Needs re-research**: `NO` = the repo's own text treats the
question as closed on this axis; `ONLY_IF_NEW_DATA` = the study's own
conclusion says the axis is exhausted on this historical sample and would
need a new/prospective dataset, not a re-tune, to move; `NEW_HYPOTHESIS_ONLY`
= the study's own conclusion explicitly points at a *different* signal or
source, not further variants of the same one; `PENDING_EXECUTION` = designed
and coded, but no result has ever been published.

| Study / module | File | Hypothesis | Data used | Headline result | Verdict | Re-research |
|---|---|---|---|---|---|---|
| Production scoring (baseline) | `longterm.py` | N/A — the ranking every study below tests | Sector-neutral z-blend of momentum/value/quality/lowvol raw inputs | N/A | `liveValidated: false`; CHAMPION, `paperTrading` | — |
| **Regional alpha model** | `regional_alpha_features.py`, `regional_alpha_model.py` | Does a region-specific ML re-ranking (Ridge/HGBR, annual walk-forward) beat the linear 4-factor blend, using only PIT-reconstructible features? | The 31-feature research-only matrix (§1 of the data map) | **No published result exists.** Pre-registration and code are complete; `data/research/regional-alpha-model-v1/` holds only partial input files; no `docs/results/regional-alpha-model-v1-report.{json,md}` is checked in | **NOT YET EXECUTED / NO VERDICT PUBLISHED** | **PENDING_EXECUTION** — consumes each region's *last* one-shot historical-discovery budget regardless of outcome; supersedes the never-run `us-alpha-discovery-v1`/`kr-alpha-discovery-v1` designs |
| Four-factor subfactor attribution | `four_factor_signal_attribution_audit.py` | Which of the 4 sleeves carry standalone/incremental Rank IC vs 126D forward benchmark excess; which are redundant; which sign-unstable? | Sealed `alphaPercentile`/`rawAlpha`/matured excess (399,547 signals) | Pooled 126D IC: momentum −0.0015 (p=.92), value −0.0056 (p=.74), quality −0.0223 (p=.08), lowvol +0.0286 (p=.15); every CI contains zero, Holm p > 0.32; all four `D_UNSTABLE_REGIME_DEPENDENT` | None significant; all region-sign-unstable | **NEW_HYPOTHESIS_ONLY** — AGENTS.md v2.21's own conclusion: "the proposed next step is new information sources... not a same-sample reweighting" |
| PIT fundamental-acceleration resolver | `fundamental_acceleration.py` | N/A — shared filing-pair infrastructure | DART/Finnhub `FundamentalStore` | Zero duplicate `(ticker, reportPeriod)` keys either region | N/A (infra) | NO |
| Fundamental acceleration discovery | `fundamental_acceleration_discovery.py` | Does filing-over-filing ROE/opMargin/profitMargin/earningsGrowth acceleration carry forward-return info beyond Quality's level? | Sealed candidates + PIT filing pairs | Coverage 64.95% pooled (KR 13.76% vs US 81.79%); orthogonality to Quality \|ρ\|=0.118; standalone IC −0.0026, incremental −0.0009, both CI contain zero, both Holm p=1.0; sign disagrees KR/US and half/half | **CASE D — NO_DISCOVERY_EVIDENCE** | **NEW_HYPOTHESIS_ONLY** — "the next step named is a new source, not a re-tune" |
| Fundamental acceleration prospective seal | `fundamental_acceleration_seal.py` | N/A — append-only prospective ledger, written before outcomes are knowable | Live candidates + live PIT fundamentals | Ships `workflow_dispatch`-only; no maturity has occurred yet | N/A (not yet accumulating) | ONLY_IF_NEW_DATA (needs the prospective window to mature) |
| Alpha reliability (persistence/confidence/hysteresis ladder) | `alpha_reliability.py` | Does averaging the percentile over its own history, contracting it by confidence, or a hysteresis rule improve on ranking the latest raw percentile? | Sealed candidates; `ExpandingBucketCalibration` | CONTROL net excess −0.684pp. `PERSISTENCE_CONFIDENCE` separates from `PERSISTENCE` in the **wrong direction**: −3.984pp, 95% CI [−8.144, −0.214] | One rung statistically **worse**; none promotable | **NO** on confidence (harmful, separated) / **ONLY_IF_NEW_DATA** on persistence-alone (contains zero) |
| Signal persistence (smoothing window ladder) | `signal_persistence.py` | Is last month's ranking noisier than the position it displaces? | Same candidates; k∈{1,3,6}, backward-only | Added names −0.357% vs retained +0.980%, paired −1.331%, 95% CI [−3.029%,+0.174%]; every rung's interval spans zero | CONTAINS ZERO for every rung | **ONLY_IF_NEW_DATA** — axis itself narrow (1.146pt mean move, integer-rounded) |
| Lowvol-alpha separation (drop lowvol from alpha) | `lowvol_alpha_separation.py` | Does removing `lowvol` from the 4-factor alpha improve selection? | Same ledger; harness CONTROL fidelity 0.906 rank-corr to published `alphaPercentile` (disclosed gap) | Predicted higher-momentum/vol/tech book built, but on a worse calibrated reading; net excess −1.647pp→−4.556pp, paired −2.909pp, CI contains zero | `DIRECTIONAL_BUT_NOT_STATISTICALLY_SEPARATED` | **NO** — "research attention belongs on persistence, role separation, and calibration resolution... not the alpha's factor composition" |
| Alpha-risk separation (drop risk denominator from score) | `alpha_risk_separation.py` | Does removing downside-vol from the selection score's denominator (keeping it in sizing) help? | `alpha_reliability.CONTROL` + `ALPHA_ONLY` rung | Paired −0.902pp, 95% CI [−5.068,+3.210]; `BENCHMARK_NOT_BEATEN`; no permutation null run | CONTAINS ZERO | ONLY_IF_NEW_DATA |
| Alpha-risk separation diagnostics | `alpha_risk_separation_diagnostics.py` | What did removing the denominator actually buy? (mechanical re-run of the frozen ladder) | Same frozen rungs, set-difference by date | 233 disagreement dates: momentum +0.687, quality +0.626 vs lowvol −9.725, downside vol +5.157pp — "bought the SAME ALPHA MORE RISKILY"; forward excess did not improve (0.587% vs 0.799%) | Diagnostic only, no new verdict | **NO** — exists to be read once |
| Alpha calibration resolution (ordinal rescue) | `alpha_calibration_resolution.py` | Among names the calibration scores identically, does the discarded ordinal `alphaPercentile` info still predict which is better? | Same ledger; within-group reorder only, mechanically no-op-verified on all 155 blocks | Pairwise concordance 49.06% (chance), mean Spearman 0.006; paired vs control −1.181pp, CI contains zero | **CASE B — ordinal rescue does not help** | **NO** — "a finer calibration would not be expected to recover value Stage B shows is not there" |
| Dynamic breadth (3–10 SE-distinguishable count) | `dynamic_breadth.py` | Does a 3–10 name dynamic book (stop when the next name's alpha no longer clears zero by 1 SE) beat a fixed 5? | Same ledger; `SE_MULTIPLE` imported from `switch_hurdle`, not re-derived | 138/155 stopped at the floor (~rank 4); net excess −0.684pp→−1.001pp, paired −0.317pp, CI contains zero; region/sector caps bind before the ceiling | CONTAINS ZERO | ONLY_IF_NEW_DATA |
| Regional switch hurdle | `switch_hurdle.py` | Should a challenger beat an incumbent by more than round-trip cost (±1 SE) before swapping? | Same ledger; region-dated cost schedule | Cost drag saved 0.270pp; arithmetic selection gained 2.157pp (8x more from holding longer than from fees avoided); lower bound clears zero by 0.122pp, one sample, no multiplicity correction. **Note: this study's own no-hurdle CONTROL rung lands at −0.684pp vs. the originally-published challenger path's −1.046pp — a disclosed harness difference (gross vs cost-adjusted excess in calibration), published beside it rather than absorbed silently.** Every later study inherits this −0.684pp baseline. | Thin positive separation, **not a promotion** — stays a CHALLENGER awaiting prospective evidence | **ONLY_IF_NEW_DATA** — needs prospective confirmation |
| Region quota removal | `region_quota_removal.py` | Does removing `maxNamesPerRegion=3` help? | Same ledger; prerequisite (cross-region calibrated-excess comparability) measured first (shrinkage gap −0.002, comparable) | Calibrated alpha LEVEL differs ~16x by region (KR 0.645pp vs US 0.041pp mean); uncapped ranking wants KR640/US82, replayed at KR639/US85; net excess −0.684pp→−2.314pp, paired −1.630pp, CI contains zero; arithmetic selection −1.351pp (quota-opened) — the KR-concentrated book picks worse names, not just lower vol | Point estimate worse, CONTAINS ZERO | **NO** on this axis alone — "quantifies the trade, does not adjudicate it" |
| Entry-selection separation | `entry_selection_separation.py` | Should the WATCH/WAIT_FOR_PULLBACK discount act on post-selection weight (as pre-registered) rather than on the selection score itself (today's production shape)? | Same ledger | Discount changes the held set on 130/155 (83.87%) rebalances; average cash 30.4%→56.0%; arithmetic selection +0.315→+2.017pp; net excess −0.684pp→+1.385pp, paired +2.069pp, 95% CI [−1.881,+6.061] **contains zero** | Large favourable point estimate, CONTAINS ZERO | ONLY_IF_NEW_DATA — this was the fourth and last study `alpha-reliability-v1` pre-registered |
| Selection null (permutation machinery) | `selection_null.py` | What does the same construction produce when the conviction score carries no information? | Real scores permuted within the alpha-filtered pool | Champion `INDISTINGUISHABLE_FROM_RANDOM`; challenger's own (correctly-labelled) null reaches 87th/84th/94th percentile (p=.134/.164/.065) — closer, still not <5% on any statistic | Neither selector clears the null at 5% | **NO** — reusable methodology, not itself a re-research question |
| Selection value decomposition | `selection_value.py` | Is the calibrated challenger's headline mostly picking or mostly a low-vol tilt? | SCREEN_ONLY / SCREEN_PLUS_TILT / SCREEN_PLUS_CONCENTRATION ladder | +0.340pp/yr = +0.040pp arithmetic selection + 0.300pp compounding (88% is tilt, not picking). Own hypothesis ("hold the screen, stop choosing") **REFUTED by its own pre-specified test**: broad-pool book −2.729pp/yr vs concentrated −1.046pp/yr | Hypothesis refuted; refutation reported, module kept | **NO** — settled; "deleting the module afterwards loses the instrument that produced the answer" |
| Benchmark-relative alpha v1 | `benchmark_alpha.py` | After realistic costs, does selection beat holding the benchmark? | 3 axes moved together (cadence + cash gate + weighting) | `BENCHMARK_NOT_BEATEN`; 1.4pp gross loss could not be attributed to any one axis | Superseded methodologically | **NO** (superseded by the single-axis ladder above; motivated it) |

**One item in this table is not a "concluded study" at all**: `regional-alpha-model-v1`
has a frozen spec and runnable code but no published result — it needs to be
run to completion and published before a re-research verdict is even
meaningful. This is flagged in the executive report as the highest-priority
action that requires **zero new data**.

---

## 2. Design/proposal documents (pre-registered, no backtest run)

| Doc | Status |
|---|---|
| `docs/regional-alpha-research-separation-v1.md` | Architecture-only (Case A). Splits US/KR into independent research problems; pre-registers `us-alpha-discovery-v1`/`kr-alpha-discovery-v1`, each a one-shot historical-discovery budget — **both superseded, not run**, by `regional-alpha-model-v1` |
| `docs/us-alpha-research-design-v1.md`, `docs/kr-alpha-research-design-v1.md` | Candidate-gate tables only (economic rationale/PIT/coverage/cost/sealability), no historical return consulted. Superseded pre-execution by `regional-alpha-model-v1`; never independently run |
| `docs/challenger-2-signal-source-feasibility-v1.md` | Feasibility audit that selected fundamental acceleration as `PROPOSED_CHALLENGER_2_SOURCE` — led directly to `fundamental_acceleration_discovery.py`'s CASE D result. Also already rejected Form 4 and options-implied-skew as candidates, citing the same SEC block this inventory reconfirms |
| `docs/challenger-2-fundamental-acceleration-v1-design.md` | Pre-registration implemented essentially as specified |
| `docs/challenger-2-research-prompt.md` | External-AI brainstorming prompt; not itself a study |
| `docs/four-factor-pit-instrumentation-proposal-v1.md` | Proposal (not implemented) to persist a `rawFactorInputs` block on future signals — would close the exact "only percentiles survive" gap this inventory's data map documents in §2 |
| `docs/benchmark-relative-alpha-v1.md` | Design doc backing `benchmark_alpha.py` above |

---

## 3. Challenger registry (`docs/challenger-registry.md`)

| # | Identifier | Description | Status |
|---|---|---|---|
| CHAMPION | `ALPHA_RANK_PER_DOWNSIDE_RISK` | Sector-neutral 4-factor alpha → percentile, gated at 66th pctile, score = rank-edge / downside vol, top-5 concentrated | `paperTrading`; `liveValidated: false` |
| CHALLENGER-1 | `CALIBRATED_EXPECTED_RETURN_PER_DOWNSIDE_RISK` | Calibrated expected-return-per-downside-risk scorer | Verified, statistically indistinguishable from random (best p=0.065); **not promoted** |
| CHALLENGER-2 | *TBD* | "A genuinely different kind of ranking logic" — reserved | **Not started.** `fundamental_acceleration_discovery.py` (the source selected for this slot) returned CASE D at the diagnostic stage and never built/scored a portfolio — per the registry's own rule, a row is added the day a genuinely different ranking method is *scored*, not for a discovery-only diagnostic, so no CHALLENGER-2 row was warranted yet |

Every other single-axis ablation study (`switch-hurdle-v1`, `signal-persistence-v1`,
`alpha-reliability-v1`, `lowvol-alpha-separation-v1`, `alpha-risk-separation-v1`,
`alpha-calibration-resolution-v1`, `dynamic-breadth-v1`,
`region-quota-removal-v1`, `entry-selection-separation-v1`) is explicitly
**not** a new challenger number — each is a rung on the CHAMPION's own
ranking with its own control, none introduced a new `score_fn` run through
`selection_null` as a distinct challenger.

---

## 4. Production scoring detail

**`FACTOR_WEIGHTS`**: momentum .30 / value .25 / quality .25 / lowvol .20
(`longterm.py:50`). Raw inputs: `mom121`/`mom6` (momentum); `earningsYield`/
`fwdEarningsYield`/`bookYield`/`fcfYield` (value); `roe`/`opMargin`/
`profitMargin`/`earningsGrowth`/`−debtToEquity` sector-exempt (quality);
`−vol252` (lowvol). `alpha = rawAlpha × evidenceCoverage`.

**Entry-state multiplier**: `score = decision / (risk×100) × state`, where
`state ∈ {1.0 ACCUMULATE_GRADUALLY, 0.5 WATCH, 0.25 WAIT_FOR_PULLBACK, 0.0
EVENT_RISK/AVOID/non-positive research view}`. Production bakes this
**directly into the selection score**, deciding both whether a name is held
at all and its conviction-tilt rank — the opposite of `alpha-reliability-v1`'s
own pre-registered intent ("alpha decides the held set; entry state decides
only how fast the target weight is approached"). `entry-selection-separation-v1`
tested the pre-registered separation; result above (contains zero).

**Selection-edge / permutation null (BEATS_RANDOM)**: already published, not
recomputed here. The corrected `selection_null` now stamps `selector` on
every return (an earlier version conflated the champion's null with a
challenger-promotion decision — flagged and fixed, per AGENTS.md's
Selection-value invariants). Bottom line already published: **neither
selector clears the pre-registered 5% bar on any statistic**; "beating the
null" and "beating the benchmark" are reported as different bars, never
merged.

---

## 5. The Opportunity change-detection model

**Files**: `pipeline/opportunity.py`, `scripts/train_opportunity.py`,
`pipeline/historical_replay.py` (feature computation, shared with live
scoring), `.github/workflows/replay.yml` (the only trainer). **No
`docs/*.md` design doc and no `docs/results/opportunity*` report file
exist** — unlike every other study in this repository, this model's only
artifact is the raw trained-model JSON committed to the `signal-history`
branch; it has never been written up.

### Q1 — Is "volume shock × momentum acceleration × healthy fundamentals" already covered?

**Substantially, yes — and it already failed.** The Opportunity model's 28
`FEATURE_COLUMNS` (19 level + 9 change features,
`pipeline/opportunity.py:52-65`) already include `volumeSurge`,
`volumeSurgeDelta`, `momentum20Acceleration`, `momentum60Acceleration`,
`valuePercentile`, and `qualityPercentile` — a percentile-blended version of
exactly this information set — fit through 7 model families including
LightGBM and Gradient Boosting, on 260,020 development rows, with a sealed
final holdout. **A new study proposing this same combination would need a
genuinely different construction to not be a redo**: e.g. preserving raw or
log magnitude of the volume shock instead of percentile rank (the data map's
§4 economic argument about losing the 2x-vs-15x distinction), or a
hand-specified conditional/threshold interaction rather than an ML blend.
Any next study in this space must state explicitly which construction
choice makes it different from what was already tried and rejected here —
not merely relabel the same features under a new name.

### Q2 — Did fundamental quality actually go in?

**Yes** — `valuePercentile` and `qualityPercentile` are two of the 19 level
features and are populated directly from `longterm_mod`'s value/quality
sleeve percentiles.

### Q3 — Did macro regime go in?

**No.** `macroRegime`/`macroConfidence` are attached to the signal record
and carried as a plain column in the training dataset, but are **not** in
`FEATURE_COLUMNS` and are never passed to `.fit`/`.predict_proba`. Their only
use is a post-hoc diagnostic (checking the top bucket isn't regime-concentrated)
— the classifier itself never sees macro state.

### Q4 — Did sector context go in?

**Partially/mostly no.** Raw sector identity is stored for grouping
diagnostics only. The one sector-derived *feature* the model sees is
`sectorRotationImproved` — a binary proxy from the sector's own member
median relative-momentum, explicitly disclaimed in the source
(`historical_replay.py:429-433`) as *not* the ETF-based `rotation.py` read.

### Q5 — Did investor flow go in?

**No.** No flow/13F/NPS-derived quantity appears anywhere in
`FEATURE_COLUMNS`, `LEVEL_FEATURES`, `CHANGE_FEATURES`, or the rule-based
fallback scores.

### Q6 — Did it complete historical validation?

**Yes — twice (opportunity + warning radars), committed to
`ledger/opportunity-model.json`/`warning-model.json` on the `signal-history`
branch.** `trainedAt: 2026-09-13`, `replayVersion: replay-v14`,
28 variants × 4 targets tested for opportunity (14×2 for warning), including
4 real executed LightGBM runs with concrete fold-level metrics — **LightGBM
was actually run, not merely wired up**, and did not win selection on any
target. Winner (opportunity): `GRADIENT_BOOSTING_SHALLOW` on
`TARGET_B_STRONG_EXCESS_126D`. Winner (warning): `LOGISTIC_L2_WEAK`. The
sealed final holdout (2023-01-01+) was opened exactly once, per the
`accessLog`.

### Q7 — Was the result accepted?

**No — both radars were rejected (`accepted: false`).** Opportunity model
failed `beatsBaselineOutOfSample` (winner's attributable excess 0.877% <
the plain-logistic baseline's 1.841%) and `decileMonotonicity` (measured
**−0.1152**, negative — the winner's highest-scored decile actually
underperformed its lowest-scored decile in the test period: pooled decile
excess `[+2.83,+0.88,−1.31,−6.35,−1.75,+6.79,+2.31,+2.81,−2.36,−0.87]`).
Warning model failed the same two checks plus `holdoutHolds`. Both correctly
triggered the documented fallback: the ML radar is not published and the
transparent rule-based change score (`opportunity.py:989-1028`) is used
instead.

### Q8 — Is it currently live in production?

**The radar runs on every build; the ML score inside it does not, for two
independent reasons.** First, `opportunity.py` is imported and called by
`build.py` on every build (unless safety-blocked), always producing an
`opportunityRadar`/`warningRadar` section. Second, and separately, the
committed trained model spec is **stranded**: it was trained on
`replayVersion: replay-v14`, while production has since bumped to
`replay-v16` (`provenance.py`). `build.py`'s `_load_generation_spec`
requires an exact match on `replayVersion` + `featureVersion` +
`modelVersion`, so today it returns `{}` and every build falls back to the
rule-based score with `mlStatus: "NOT_TRAINED"` — even setting the
generation mismatch aside, the model would still be inert because it failed
its own acceptance gate (Q7). Both facts are independent causes of the same
observed dormancy, and both are worth knowing separately: fixing the
generation mismatch alone would not resurrect a model that already failed
acceptance.

### Q9 — Overlap with a new Conditional Alpha study

Any new study that scores volume shock, momentum acceleration, and
fundamental quality together — under any construction — is operating on
exactly the information set the Opportunity model already tried and
rejected. A next study must either (a) use a materially different
construction (magnitude-preserving instead of percentile-only, a
hand-specified interaction instead of an ML blend, or a different target
horizon/definition), or (b) explicitly frame itself as a retry of the same
construction against fresh, prospective (not sealed-historical) data — and
say so, rather than presenting the same combination as untested.

---

## 6. Regime interaction research

**Exists, is wired into production output, but is never consumed
downstream.** `pipeline/historical_calibration.py:790-893`,
`regime_interaction()` tests exactly `region × alpha-calibration-bucket ×
macroRegime`: a hierarchically-shrunk mean realized excess per cell,
z-scored against the region×bucket parent, flagged `significant` only at
`|z|≥1.96` and `effectiveDates≥15`. Gated by an `activate` flag that is
`true` only if at least one cell is genuinely significant. Called on every
build, surfaced at `historicalValidation.regimeInteraction`, but **nothing
downstream reads the `activate` flag** — confirmed by grep across
`kelly_portfolio.py`, `validate.py`, `build.py`: it never feeds Kelly sizing
or base calibration. Whether it has found a significant cell on the real
replay-v16 ledger is **UNDETERMINED FROM AVAILABLE EVIDENCE** — no committed
report exists for it, unlike every other study in this line, and running
`build.py` to find out was out of scope for this read-only inventory.

**Confirmed genuinely absent** (named as untested candidates in
`docs/regional-alpha-research-separation-v1.md`, Section 11, and
independently re-confirmed here by grep — no file combines these):

- Momentum under easing liquidity (US)
- Value under reflation (US)
- KR exporters under KRW weakness
- Quality under slowdown (either region)
- Volume shock × Quality × Liquidity regime
- Momentum acceleration × Financial Conditions

A separate, unrelated dead-code finding surfaced while investigating this:
`pipeline/direction.py:190-201` reads a `"stance"` key from
`macro_summary["US"/"KR"]` that `macro.py`'s current `summarize()` never
sets (it was retired when `regime.py` replaced the old threshold system,
but `direction.py` was never updated) — this signal in the direction
"compass" silently always reports "Stable" regardless of the real macro
state. Not an alpha-scoring defect (the compass is a descriptive panel), but
worth fixing before anyone relies on it.

---

## 7. Regime/rotation modules — what is descriptive-only

`pipeline/rotation.py` (RRG sector rotation + factor/style momentum) and
`pipeline/indices.py` (11-symbol market tape) are both wired into
`build.py` but are **descriptive dashboard panels only** — neither is
consumed by `longterm.py`, `kelly_portfolio.py`, or `opportunity.py`.
`pipeline/regional_rotation.py` (US/KR capital-allocation blender across two
already-scored regional replays) is **not imported by `build.py` at all**;
its only consumer is a standalone research script, and its output is a
completed research artifact (`docs/results/regional-rotation-report.*`,
`docs/regional-rotation-validation-v1.md`), not a production component.

---

## 8. Comparison table — information group vs. existing research surfaces

| Information group | Regional Alpha v1 (unexecuted) | Opportunity (executed, rejected) | Regime Engine (production, US/global only) | New-to-any-surface? |
|---|---|---|---|---|
| Price/trend/momentum (level) | Y (21 of 31 features) | Y (19 level features) | N | No |
| Momentum acceleration | N | **Y** | N | No |
| Fundamental level (quality) | Y (5 features) | Y (via percentile) | N | No |
| Fundamental acceleration | Y (4 delta features) | N | N | No (separately tested, CASE D) |
| Volume/liquidity (percentile-only) | Y (`volumeSurge5_60`) | **Y** (`volumeSurge`, `volumeSurgeDelta`) | N | No |
| Volume/liquidity (raw/log magnitude) | N | N | N | **Yes** |
| Macro regime (US/global 6-axis) | N | N (attached but unused by the model) | **Y** | No, but never interacted with stock-level features |
| Macro regime (KR) | N | N | N (does not exist) | **Yes — nothing has this at all** |
| Sector context (ETF-based rotation) | N | N | N | **Yes** (rotation.py exists but feeds nothing) |
| Sector context (member-median proxy) | N | **Y** (`sectorRotationImproved`) | N | No |
| Investor flow (KR) | N | N | N | **Yes — genuinely absent everywhere** |
| Investor flow (US, 13F) | N | N | N | Collected, unused everywhere — see data map §23 |
| Accounting quality (accruals, cash conversion, etc.) | N | N | N | **Yes** |
| Analyst expectations | N | N | N | **Yes, but Grade D/E — likely not buildable free** |
| Corporate events (dividend changes) | N | N | N | **Yes, and cheapest to build (data already collected)** |

The comparison shows plainly: momentum, fundamental level, fundamental
acceleration, and percentile-only volume shock are **not** new information
relative to what has already been assembled (in production, in the
unexecuted regional model, or in the rejected Opportunity model). The
genuinely new axes are: KR investor flow, KR macro/regime entirely, raw
volume/liquidity magnitude, accounting-quality ratios, and (narrowly) US
dividend-change signals.

---

## 9. Files read to build this map (for reference)

`pipeline/longterm.py`, `regional_alpha_features.py`, `regional_alpha_model.py`,
`four_factor_signal_attribution_audit.py`, `fundamental_acceleration.py`,
`fundamental_acceleration_discovery.py`, `fundamental_acceleration_seal.py`,
`alpha_reliability.py`, `signal_persistence.py`, `lowvol_alpha_separation.py`,
`alpha_risk_separation.py`, `alpha_risk_separation_diagnostics.py`,
`alpha_calibration_resolution.py`, `dynamic_breadth.py`, `switch_hurdle.py`,
`region_quota_removal.py`, `entry_selection_separation.py`, `selection_null.py`,
`selection_value.py`, `benchmark_alpha.py`, `opportunity.py`,
`scripts/train_opportunity.py`, `historical_calibration.py`, `rotation.py`,
`regional_rotation.py`, `indices.py`, `direction.py`; all `docs/*.md` and
`docs/results/*.md` named above; `docs/challenger-registry.md`;
`.github/workflows/replay.yml`; `ledger/opportunity-model.json` and
`ledger/warning-model.json` (read from the `signal-history` branch, not
modified). No file was modified, and no script was run, in the production of
this map.
