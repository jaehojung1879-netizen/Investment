# EXP-C-RECOVERY-01 — C protects partially, but misses recoveries

Status: **SEALED_EVIDENCE_REVIEW + UNREGISTERED_DESIGN; NEW OUTCOME EVALUATION BLOCKED**. As of 2026-11-01 UTC.
Repository evidence pinned to main `37f8cbf6b1c066f6b3c65235953648d17ebf2f69`; PR #289 inspected separately at `92d78cd5ca4f74225a2c9456d4f296c082280098`.
This is a separate exploratory project, not C1c, a replacement for Track C, or permission to reopen a closed study.

## Finding and recommendation

**Retain current C unchanged as a research/risk-budget control; retain passive 100% as the allocation default.** The existing evidence supports delayed participation after troughs, alongside partial downside protection. It does **not** establish that an observable recovery signal can improve timing, or that re-entry explains most of the whole-period shortfall. Stop new historical execution here: the existing closure rule and source/registration blockers below remain binding. A separate re-entry comparison is a falsifiable contingency, not a recommended allocation change.

- KR C0/C1 missed **9.70/10.13 percentage points** of H63 rebound on average over seven measurable troughs; median return to full target was **83/83 sessions**, measured for only five of eight episodes. US C0/C1 missed **13.73/13.12 points**, with **73/73 sessions** median delay over seven episodes.
- KR annual cost drag is **0.482/0.373 points**; the remaining passive-minus-gross CAGR gaps are **2.514/2.217 points**. US costs are **0.105/0.094 points**, with **0.940/0.740 points** remaining. Those residuals cannot be assigned uniquely to re-entry.
- Volatility has the strongest documented short-horizon downside association. No sealed test establishes its incremental information about recovery, conditional on C's stressed state. An Oracle's feasible superiority would demonstrate hindsight opportunity, not predictability.

## 1. What the sealed evidence actually identifies

Source: [KR sealed result](../../docs/results/kr-market-risk-model-v1-result.json), [design §§3–7](../../docs/kr-market-risk-model-v1-design.md), and [US formal archive](../../docs/research-program/results/rp1-c1-us-exposure-formal-20261024/README.md). [evidence.json](evidence.json) copies the relevant fields, all ≥15% episodes, denominators and nulls; [review.py](review.py) verifies source hashes and extracts them without reading market prices or rebuilding paths.

| Region / rule | Net CAGR | MDD | Reduced sessions | False alarms / matured activations | Missing-state holds |
|---|---:|---:|---:|---:|---:|
| KR passive | 9.728% | −52.918% | 0% | — | — |
| KR C0 | 6.732% | −40.874% | 50.15% | 36/42 (85.71%) | 0 |
| KR C1 | 7.138% | −36.822% | 28.21% | 26/31 (83.87%) | 0 |
| US passive | 8.817% | −56.775% | 0% | — | — |
| US C0 | 7.772% | −42.332% | 27.14% | 39/49 (79.59%) | 0 |
| US C1 | 7.983% | −43.426% | 21.16% | 32/41 (78.05%) | 0 |

KR: 4,856 sessions, 1,027 weekly decisions, first execution 2007-01-08. US: 8,459 sessions, 1,754 decisions, first execution 1993-02-08. Both original result windows end **2026-09-17**; **2026-09-14 is the last execution**, not the valuation end (the US archive overview's shorthand is ambiguous). KR is outcome-exposed development; the original US execution is frozen-rule replication on publicly known history. Every historical comparison proposed here is outcome-exposed exploratory development, even with chronological splits. Both sealed decisions retained C0, with no candidate nominated.

### Opportunity-loss accounting: only the cost bridge is complete

All entries below are CAGR percentage points/year: `passive − net = (gross − net) + (passive − gross)`. This difference-of-CAGRs bridge is exact arithmetic, not a decomposition of compounded wealth or causal mechanisms.

| Region / rule | Total passive − net | Trading costs: gross − net | Unattributed non-cost residual |
|---|---:|---:|---:|
| KR C0 | 2.996 | 0.482 | 2.514 |
| KR C1 | 2.590 | 0.373 | 2.217 |
| US C0 | 1.045 | 0.105 | 0.940 |
| US C1 | 0.834 | 0.094 | 0.740 |

| Requested cause | Identifiable quantity | Limit of attribution |
|---|---|---|
| Delayed exit | Anatomy baseline B3 (either trend/vol adverse) had already taken median 19.6% of final episode damage when triggered; B4 (both) 65.2%, missing 6/12 ≥15% episodes. Model episode loss-capture is retained. | These are trigger/damage diagnostics, **not** C0/C1 CAGR loss from delayed exit. No sealed first-exit counterfactual allocation is retained. Amount unresolved. |
| False-alarm de-risking | Counts above; reduced sessions without a subsequent −10% H63 loss: KR 1,789/869, US 1,612/1,185 for C0/C1. | A non-event is not necessarily a profitable missed rally. No per-alarm NAV opportunity-cost ledger; amount unresolved. |
| Delayed re-entry | Trough-aligned return gaps and sessions to first full target below. | Net gaps include costs, later de-risking and all intervening returns. They overlap false alarms and each other; not additive to CAGR. Amount attributable solely to re-entry unresolved. |
| Transaction costs | Exact gross-minus-net bridge above, same decisions and regional cost basis. | Sum of costs/NAV is a different quantity: KR 8.679/6.701%, US 3.280/2.905%; not annual drag. |
| Residual | Passive-minus-gross gaps above remain unresolved in full. | Includes beneficial protection, lost participation, beta reduction, timing, drift and compounding. Do not subtract episode averages from it. |

US's sealed arithmetic diagnostics show up-market cost/down-market saving of 18.81/17.13 points/year for C0 and 16.79/15.35 for C1. These signed daily-return sums are not a CAGR attribution. A matched-average-exposure static result is **not** present in these sealed results; timing alpha cannot be inferred from drawdown reduction alone.

### Why the map can remain stressed through a rebound

The [actual state map](../../pipeline/kr_market_risk_model.py) is memoryless, apart from hold-on-missing. C0 uses only FAST: zero warnings → 1.0, one → 0.7, two → 0.4. C1 changes only **FAST=1 and SLOW=TRANSITION=0** to full exposure. Both remain 0.4 at FAST=2. Both return to full at FAST=0 regardless of SLOW/VIX. Thus SLOW/VIX **cannot delay C0** and cannot independently prevent C1 recovery once FAST clears.

The trend leg compares price with a trailing 200-close average; vol63 retains recent crash returns until they roll out. These are lagging stress measurements, not recovery forecasts. Monthly SLOW retains post-inversion history for 504 sessions; weekly VIX percentile can remain elevated. They can keep C1's single-FAST-warning state confirmed. Weekly decisions and next-session-close execution add calendar delay, without any built-in minimum hold. Missing-state holds were zero, ruling out that mechanism in these sealed samples. **Daily leg/state/execution paths are not included in the retained result JSONs**: per-episode shares of delay caused by trend, vol, VIX, SLOW or scheduling cannot be measured from these summaries. Structural plausibility is not empirical variable attribution.

### Requested episode inspection (no new event selection or return calculation)

Entries are **C0 / C1**. Full = sessions from hindsight trough to first executed full target; H63 = passive-minus-candidate net return in percentage points. These are copied from the original ≥15% underwater episodes, not newly imposed named-event windows.

| Episode / market | Sealed trough | Full sessions | H63 missed, pp | H126 missed, pp |
|---|---|---:|---:|---:|
| 2008 / KR | 2008-10-24 | 174 / 174 | 15.44 / 15.44 | 26.49 / 26.49 |
| GFC / US | 2009-03-09 | 97 / 97 | 28.29 / 28.29 | 32.22 / 32.22 |
| 2011 / KR | 2011-09-26 | 96 / 83 | 8.49 / 8.49 | 13.61 / 12.88 |
| 2020 / KR | 2020-03-19 | 83 / 83 | 25.47 / 25.47 | 30.17 / 30.17 |
| 2020 / US | 2020-03-23 | 82 / 82 | 23.68 / 23.68 | 27.96 / 27.96 |
| 2022 / KR | 2022-09-30 | 81 / 29 | 1.15 / 3.72 | 5.84 / 4.68 |
| 2022 / US | 2022-10-12 | 65 / 37 | 3.38 / 2.49 | 4.68 / 2.86 |
| 2026 / KR | 2026-03-31 | null / null | 15.90 / 15.90 | null / null |
| 2026 / KR | 2026-06-08 | null / null | −1.18 / −1.18 | null / null |
| 2026 / KR | 2026-07-30 | null / null | null / null | null / null |

US 2011 is inside the unrecovered 2007–2013 underwater episode, not a separate sealed trough. US has no 2026 episode even at the original ≥10% cut. Neither absence is zero loss or evidence of no stress; a new local-event definition would be a new evaluation. KR July 2026 recovery is censored; March/June reference recovery completed but full exposure did not return within the retained sample. Null is never zero delay. H126 is immature for those 2026 troughs. The negative June H63 gap is important: more exposure after that trough would not automatically help. KR 2022 C1 returned earlier yet missed more H63 return than C0; faster first re-entry is not a sufficient economic objective.

All ≥15% episodes, including 2007 KR and 1998/2002/2018/2025 US, remain in evidence.json. KR mean H63 uses 7/8 episodes, H126 5/8 and full-target delay 5/8; US uses 7/7. The KR full-delay median omits three still-unresolved recoveries and includes a zero in 2007. These are tiny dependent event samples, not effective independent sample sizes or uncertainty estimates. KR recovery-opportunity-cost mean includes a censored window ending at the sample end; do not call it a completed-recovery mean.

## 2. Inputs: documented relevance and actual availability

[Sealed anatomy](../../docs/kr-market-risk-anatomy-v2-final-result.md) counts are valid feature dates, before forward-label maturity, over the retained 1990–2026 series. They are neither full-period coverage percentages nor independent events. AUROC refers to future worst loss ≤−15% from the signal close, in the feature's risk orientation; not incremental information or a recovery test.

| Observable input (exact anatomy ID in evidence.json) | First valid / valid dates | Cadence | H21 / H63 downside AUROC | Role / limitation |
|---|---|---|---|---|
| Price/SMA200 distance | 1990-09-08 / 1,634 | weekly | .598 / .539 | Trend leg exists in C; weak standalone downside ranking. |
| Negative SMA200 slope over 21 sessions | 1990-09-29 / 1,615 | weekly | .528 / .480 | Not a C input; no recovery evidence. |
| Realised vol21 | 1990-02-03 / 1,871 | weekly | .816 / .713 | Strongest short-horizon descriptive downside relation. |
| Realised vol63 | 1990-03-24 / 1,806 | weekly | .796 / .739 | C threshold is annualised 25%; persists after shocks. |
| Downside vol63 | 1990-03-24 / 1,806 | weekly | .807 / .728 | Root mean squared negative daily returns ×√252. |
| Vol acceleration: vol21/vol63−1 | 1990-03-24 / 1,806 | weekly | .623 / .504 | Weak beyond H21; a testable normalisation signal, not established recovery predictor. |
| VIX level | 1990-01-06 / 1,914 | weekly | — / .651 | C uses expanding midrank percentile ≥.80, ≥156 finite weekly observations, including current known observation; no future ranks. Separate percentile coverage not published in anatomy. |
| SLOW re-steepening | 1991-09-30 / 421 | monthly | — / .665 | Positive 10y−3m after negative within trailing 504 sessions; H252 .657. Stress marker, not bullish easing signal. |
| Negative trailing-252 drawdown | 1990-11-10 / 1,587 | weekly | .706 / .638 | Observable rolling high; not a future-defined trough. |
| Negative trailing returns 63 / 126 | 1990-03-24 / 1,898; 1990-06-09 / 1,886 | weekly | .604/.521; .557/.548 | Past market-recovery proxies only; no from-future-trough feature. |

KR breadth-above-SMA200: **95** valid dates, 2015-10-16..2023-10-27; breadth deterioration63: **50**, 2016-11-04..2023-10-27. Concentration has 588 dates but is not breadth. These are sparse PIT Top120 internals, not market-wide coverage. No 2008/2011 breadth, no 2026 breadth, no full valid contemporaneous panel or independently effective event count. Exclude from the small candidate comparison; do not backfill present constituents. US historical breadth coverage is **unestablished** in C1 and must not be borrowed from KR.

US freeze metadata reports ^GSPC **9,245 rows**, 1990-01-02..2026-09-17; SPY **8,466**, 1993-01-29..2026-09-17; DTB3 **9,184**, 1990-01-02..2026-09-17. It establishes determinability for all 1,754 C decisions, not individual coverage for every proposed continuous feature. **New US feature-cell coverage has not been computed.** KR's source-quality window has 5,108/5,108 sessions from 2006 onward; the broader anatomy has 10 missing sessions and five off-calendar vendor dates before 2006. Do not transplant its sampling implementation into a new weekly decision calendar.

### Observation time is not historical availability

The source [readiness record](../../docs/kr-market-risk-anatomy-v2-source-readiness.md) identifies KS200 retrieval at **2026-10-04T16:38:34.032270+00:00**, with retained observations ending **2026-09-17**. That acquisition timestamp is not publication at each historical close. The sealed mapping uses **observation date + four calendar days** for FRED VIX/Treasury legs, rejects age >14 calendar days, and zero date lag for local price. SLOW samples calendar month-end and carries; VIX samples week-end on its own regional calendar. For example, a 2026-09-14 FRED observation is date-eligible no earlier than 2026-09-18, outside this retained valuation window. This is a rule illustration, not proof that a particular release occurred then.

The retained sources are **MARKET_OBSERVED_UNREVISED_APPROXIMATE_AVAILABILITY**, not PIT_EXACT. Exact per-observation release timestamps and historical vintage proofs are missing. No honest timestamp table can manufacture them. A future admitted row must preserve `observedAt`, `publishedAt`, `availableAt`, source/version/hash and decision instant, using the later of documented release and the inherited conservative lag. KR finality is at least 18:00 KST (09:00 UTC); US actual XNYS close +60 minutes, accounting for early closes/DST. Decision follows finality, execution is the next regional session close. These finality requirements are for a new contract; the old date-indexed simulation is not retroactively upgraded. No revised ECOS/macro history or all-history percentile is admitted.

## 3. Oracle definition and label boundary (proposal, no solver executed)

**Comparable OR-C:** optimise terminal net NAV retrospectively over targets {1.0, 0.7, 0.4}, no leverage/shorts, one target per regional calendar week-end, executed only at next-session close. Start at the comparator's actual first allocation/NAV with the same uncharged initial build. Trade only on target change, to target × post-cost NAV; let equity/cash drift between trades. No initial clairvoyant pre-positioning, same final valuation, no forced terminal liquidation absent in C. Use the existing engine's self-financing post-fee buy/sell equations, not target-difference fees.

Separate KR KS200 price-index/zero-KRW-cash and US ^GSPC price-index/zero-USD-cash readings. KR buy/sell **15/45 bp**, US **8/8.3 bp**; report 1×, 2×, 3× with no cost-based model selection. These are the original conservative index conventions, not ETF investability. A future economic Oracle must be separate: KR admitted 069500 total return + named KRW cash; US admitted SPY corporate-action total return + prior-known DTB3 accrual. Do not substitute the separate US economic series for the primary, pool currencies, or silently replace KR's sealed price series with the corrected ETF series. The original vendor-adjusted US economic reading remains hash-blocked; the archived cash-reinvestment reading is distinct.

**Turnover comparison:** original C has no hard turnover ceiling; its restriction is weekly target-change trading with drift. Define OR-C separately against C0 and C1, adding both `switches ≤ comparator switches` and `Σ|executed notional|/(2×pre-trade NAV) ≤ comparator one-way turnover`, evaluated under the same cost multiplier. At 1× these exact budgets are KR C0 **96 / 14.341268**, C1 **69 / 11.057276**; US C0 **135 / 20.119310**, C1 **107 / 17.821419**. These whole-sample budgets are retrospective constraints, not observable trading inputs. Baseline paths are feasible witnesses, so the exact optimum cannot underperform their terminal NAV. At 2×/3× derive the corresponding budgets under authorization, not by reusing 1× realized notional. Freeze tie-breaking as least turnover, then least switches, then lexicographic target sequence; do not search utilities, drawdown penalties or budget grids after results. Drift makes target alone an insufficient optimisation state; any later solver needs a feasibility replay and certified optimality gap. An uncertified feasible solver output is a lower bound on the optimum, not the upper bound itself.

**Unconstrained OR-U:** a frictionless daily-retargeting clairvoyant relaxation, same initial NAV and asset/cash, no switch/notional budget; choose the best daily weight in [0,1]. Its product of daily maximal asset/cash wealth factors is an upper bound on OR-C with nonnegative costs. It may use zero exposure and daily foresight; **only OR-C** obeys the original vocabulary/cadence/fees/turnover. Neither is an implementable strategy. No realised OR-U/OR-C value or superiority magnitude is available; claiming a number would require prohibited new outcome optimisation.

**Strict label contract:**

| Namespace | Permitted contents | Access rule |
|---|---|---|
| Ex-ante features | Only the listed past price/volatility, dated VIX/curve and C states; source availability metadata | Features frozen as of decision instant; unknown/stale stays missing. No Oracle targets, future trough/recovery dates, future returns or full-sample ranks. |
| Downside A labels | H21/H63 worst loss `min(P[t+1:t+H])/P[t]−1`, event ≤−15%, continuous severity; execution-anchored loss separately | Label table only; signal-anchored definition preserves anatomy comparability. Actual policy economics start at next close. Never mix the two origins. |
| Recovery B labels | Conditional H21/H63 asset-minus-cash return distribution given C0 target <1; C1-stressed cohort auxiliary | Cohort fixed from ex-ante states, not successful future rebounds. No trough-selected training. |
| Opportunity labels | Paired wealth difference of full versus the frozen C continuation, both entering at next close with identical funded/cost conventions through H | Can be negative. Future C decisions are outcomes, never current features. Full strategy and C continuation are distinct from holding a constant lower weight. |
| Oracle-only labels | OR-C decisions/regret, episode troughs and recovery endpoints | Isolated retrospective diagnostic table. Whole-path Oracle target depends on the entire optimisation window; unavailable for training until that window's terminal finality. Not the primary A/B training target. |

Training must wait until **all** label dependencies have finalised strictly before the training cutoff. Future trough dates and OR-C target are never deployable inputs, including joins, missingness flags and sample filters. A/B are separate tasks; **do not enforce A+B=1**. A volatile rally can carry both high subsequent loss risk and positive recovery opportunity. The small timestamp/namespace audit helpers in review.py check this boundary on invented rows; they do not authenticate historical publication evidence or constitute a deployable model.

## 4. Small falsifiable comparison, conditional on new authorization

No new model fit, label generation, path reconstruction, Oracle optimisation or historical threshold search occurred. The following is a **proposal to register**, not a completed preregistration:

| Alternative | One question it could falsify | Prior evidence / cost |
|---|---|---|
| Keep C0/C1 | Is partial protection worth participation lost under an explicitly chosen risk budget? | Measured above. No alpha claim, no new configuration. |
| Original one-rung structural re-entry | Can changing only re-entry reduce net opportunity loss without unacceptable loss of protection? | Listed before US C1 outcomes; reuse #289's separate ORIGINAL_STRUCTURAL definition if ever admitted, no reinterpretation or implementation here. |
| One augmented forecast comparison | Do past-only ret63 and vol21/vol63 add recovery information beyond existing states? | Unmeasured. Economic plausibility and weak standalone downside evidence do not establish incremental recovery signal. |

For a separately registered forecast study, propose **M0** expanding constant event rate/return distribution; **M1** additive FAST (categorical), SLOW and TRANSITION forecasts; **M2** M1 plus signed trailing ret63 and vol acceleration. Separate A logistic and B conditional-return fits; identical predeclared settings in both regions with independent coefficients. No feature ranking step, interactions, threshold/lookback sweep or deep ML. A single fixed regularisation/standardisation/distribution-estimation protocol must be registered and synthetic-calibrated before fitting; it remains unset here. Do not sneak a forecast-to-exposure decision rule into a scoring study.

Use H63 primary and H21 descriptive **as a proposal only**; both must be reported. Primary incremental tests would be paired Brier loss M2−M1 for A and paired proper-distribution score M2−M1 for B in the pre-fixed C0-stressed cohort. Show M0, calibration, event rates, severity errors and conditional-return quantiles. No predictive claim from AUROC ranking alone. Common-contract calibration currently does not establish valid inference for these nonlinear probability/distribution scores; a new synthetic dependence-aware calibration is a prerequisite, not permission to borrow a return-mean interval. Economic materiality, score choice, multiplicity/error rate, power/MDE and minimum support remain **unregistered**. Existing C's 0.50pp/1.10×/0.90× nomination tolerances are provenance, not automatically adopted new hurdles.

If authorized, use yearly **strictly expanding** training, train-only transforms, label-finality before fold start, purge every intersecting H-window and embargo H63 sessions at internal boundaries. Freeze estimation start, first holdout, missingness policy, support floors and first prospective look before outcomes. No previously exposed year becomes independent OOS. Report weekly observations **and** non-overlapping horizon blocks, distinct stress episodes, event/non-event counts, dependence-adjusted effective size and calibrated uncertainty; seven US/eight KR ≥15% episodes do not become thousands of independent trials. If MDE exceeds the registered useful effect or support fails, skip inferential historical claims and stop; do not add predictors.

Economics must compare regional passive, sealed C0/C1, any single frozen challenger and **matched-average-realised-exposure static paths** with the same dates, fees, drift, cash and execution convention. State static retarget cadence in advance. Full-sample matching is an ex-post diagnostic, not a feasible forecast or exact beta match. Report gross/net protection, participation, costs, beta and volatility/compounding separately from excess over the matched static control. Check first/second halves, fixed regimes, country disagreement and coefficient instability; never select a favourable period or currency. Recovery timing includes wrong early entries, whipsaws and remaining underexposure, not merely days to the first full target. Prospective immutable pre-execution receipts for all frozen arms and matured outcomes are required before any allocation proposal; none are created here.

## 5. Exact blockers and completed work

1. **Closure:** [03 §C.7](../../docs/research-program/03-studies-abc-ko.md) says KR C0-retained + US C0-retained ends further H/I/J exposure search; [stop list](../../docs/research-program/05-priority-first-experiment-stop-list-ko.md) forbids rerunning sealed studies and same-information KR searches. The [atlas roadmap](../../docs/kr-alpha-atlas-execution-roadmap.md) also restricts renewed broad KR historical search. Changing the objective to Oracle/recovery does not create a new information axis. Independent review must explicitly resolve the closure conflict before any new study admission. This report does not override it.
2. **Registration/authorization:** no independently reviewed EXP-C-RECOVERY-01 registration, approved economic/inferential thresholds, immutable code/input closure, owner exact-hash execution authorization, lock/first-look plan or prospective support contract exists. This request expressly reserves new outcome-dependent optimization for those gates. A draft PR or synthetic test pass does not grant execution.
3. **Attribution data:** sealed JSONs retain episode/aggregate diagnostics, not daily NAV, orders, target and FAST-leg/SLOW/VIX provenance paths. Exact mutually exclusive temporal attribution requires separately admitted retained paths, or a specifically authorized new diagnostic. A new counterfactual return calculation is not a read-only extraction. No new original-C execution or lock is permitted.
4. **Timestamp/source admission:** exact historical release/finality/vintage proofs are missing; the inherited four-day lag is approximate. [US freeze](../../docs/research-program/sources/rp1-c1-us-source-freeze-39080239146.json) has metadata/hashes, not a new licence or proof of local raw-byte possession. No new US continuous-feature coverage or valid historical breadth panel is available here.
5. **Economic data and #289:** the [independent audit](../../docs/research-program/audits/pr289-market-c1c-independent-audit-ko.md) identified control selection, FAST=2 trigger blind spots, structural versus post-result breakout hypotheses, missing decision criteria, cash basis, beta matching and reused history. Later [independent source review](https://github.com/jaehojung1879-netizen/Investment/pull/289#issuecomment-6550483429) and [author repair/handoff](https://github.com/jaehojung1879-netizen/Investment/pull/289#issuecomment-6550576753) leave **13 source blockers, zero newly verified distributions**: 26/46 payment-date/tax-base records unresolved (24 only rule-bounded, two record-rule-only). The repaired code claims at most SHAPE_VALID_UNVERIFIED, not official admission. No investable KRW cash series or historical investor tax treatment is established. Conditional first-order payment bounds are not funded total return. Current handoff flags unresolved KODEX/KRX/Cboe/FRED use/retention/publication terms and a possible direct-Board H.15 route; these are reported source-admission findings, not an independently verified legal ruling by this project. They block new raw-data use; no files or work on #289 were changed.

**Completed:** sealed-result extraction with three SHA checks, all five US archived payloads verified by the existing read-only verifier (160 archived independent checks; no new independent audit claimed), quantified cost/residual bridge, episode/feature coverage review, Oracle/label design and seven focused stdlib tests. **Not completed/authorized:** Oracle performance, incremental recovery forecasts, matched-static backtests, complete causal attribution or prospective evidence. The honest answer to “can observable signals approximate hindsight?” is **not established by the available studies**.

### Reproduction and verification

From a complete repository checkout, these commands only inspect sealed outputs or invented fixtures:

```sh
python research/exp_c_recovery_oracle_v1/review.py > /tmp/exp-c-recovery-evidence.json
cmp research/exp_c_recovery_oracle_v1/evidence.json /tmp/exp-c-recovery-evidence.json
python -m unittest discover -s research/exp_c_recovery_oracle_v1 -p 'test_*.py' -v
python docs/research-program/results/rp1-c1-us-exposure-formal-20261024/verify.py
```

This environment could not clone through its configured shell proxy. Files were read at pinned refs through the GitHub connector and tested against an isolated exact-byte evidence snapshot. Seven tests passed; extraction reproduced evidence.json exactly; the five-payload archive verifier passed. Repository-wide ruff/pytest, pipeline compilation, seed generation and production-artifact validation required by AGENTS.md could **not** run in this partial snapshot (ruff/pytest also absent). Run the normal repository CI before review; no workflow was modified or manually dispatched. These limitations do not authorize editing protected files or claiming full CI success. Only four new files under this directory belong to this draft.
