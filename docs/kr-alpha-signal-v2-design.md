# kr-alpha-signal-v2 — research design (KR, H126): value with business confirmation, within industry

Status: `DESIGN_DRAFT_NOT_PREREGISTERED`. This document defines a signal, its tests and its prospective record. **It computes nothing on
historical outcomes, authorizes no evaluation and registers no prospective start.** Code in this change is the signal and receipt contract with
synthetic tests (`pipeline/kr_alpha_signal_v2.py`, `pipeline/kr_alpha_signal_v2_receipts.py`, `pipeline/prospective_receipt_core.py`). No
production path imports it. Why this hypothesis: `docs/kr-alpha-signal-v2-opportunity-map.md`.

## 1. The question, and what is kept apart

For stock X on weekly decision date T: is X cheap against its own industry while its business is profitable, cash-backed and not deteriorating?
If so, does that state carry an expected H126 return above 069500.KS large enough to pay for trading it and for being wrong?

| Layer | In this design | Kept separate because |
|---|---|---|
| A. Information discovery | the state rule (§3); the contrasts in §6 | a state is not a forecast |
| B. Prediction / calibration | a later, separately authorized calibration maps state to expected excess return and SE | until it exists, no expected return is published (`NOT_READY`) |
| C. Allocation | 0-5 names, one 20% slot each, unused slots to a declared fallback (§9) | selection and sizing never share a score |
| D. Risk | per-name downside volatility and max drawdown recorded; `kr-market-risk-model-v1` stays its own layer | a market overlay cannot rescue or tune a signal |
| E. Costs | dated KR schedule from `config.json`, passive-leg cost stated as an assumption | reported, never netted invisibly |
| F. Prospective validation | weekly receipts; outcomes as separate records after maturity (§10) | historical development evidence and prospective evidence are never pooled |

## 2. Inputs and PIT contract

One row per PIT top-120 KRX member on T (the same universe as every KR anatomy). A row may carry only the keys in `ROW_FIELDS`; any other key,
including any forward or outcome column, refuses the whole cross-section.

| Field | Source (existing code, reused) | Availability rule | Missing means |
|---|---|---|---|
| `ticker`, `isPreferredShare` | PIT membership, `kr_industry_membership_v4.PREFERRED_SUFFIX` | member on T | unknown preferred status = preferred (excluded) |
| `industry` | v4 economic crosswalk (14 groups) over KIND/KRX labels | label observable on T | `INDUSTRY_UNCLASSIFIED` (ineligible) |
| `priceAsOf`, `positiveVolumeSessions20`, `medianTradedValue60Krw` | replay price panel / KRX daily | session T and earlier | ineligible |
| `bookToMarketProxy`, `earningsYieldProxy` | `kr_value_quality_catalyst.accounting_values` × signal-date KRX cap | filing `availableFrom` (DART receipt date) ≤ T | `MISSING_VALUE_INPUT`, never cheap |
| `netIncomeToAssets`, `ocfToAssets`, `ocfImprovementToAssets` | the same TTM roll-forwards (`dart_derive`) | receipt date ≤ T; no CFS/OFS mix | `CHEAP_CONFIRMATION_UNMEASURED`, never unconfirmed |
| `relative126` | price | ≤ T | control only, never in the signal |
| `downsideVol126`, `maxDrawdown252` | price | ≤ T | recorded risk flags only |

`fundamentalsAvailableFrom` or `priceAsOf` after T refuses the cross-section (`FUNDAMENTALS_AVAILABLE_AFTER_SIGNAL_DATE`, `PRICE_AFTER_SIGNAL_DATE`).
Accounting numbers are whole-entity figures over one issue's market cap (`ISSUE_CAP_ACCOUNTING_PROXY`); preferreds are excluded for that reason.

## 3. What the signal means

Among eligible names in the same industry on T (at least 5, else `INDUSTRY_BELOW_MIN_MEMBERS`; a thin industry is never ranked against the whole
market instead):

1. `valuePercentile` = mean of the within-industry mid-rank percentiles of book-to-market and earnings yield. Both are required.
2. **Cheap** = `valuePercentile ≥ 2/3`, the top within-industry tercile.
3. **Confirmed** = net income > 0 **and** operating cash flow > 0 **and** trailing OCF above its level a year earlier (each scaled by assets).

States: `INELIGIBLE`, `MISSING_VALUE_INPUT`, `NOT_CHEAP`, `CHEAP_CONFIRMED`, `CHEAP_UNCONFIRMED`, `CHEAP_CONFIRMATION_UNMEASURED`. Ranks come from T's
cross-section only, so no other date and no outcome can move a rank; the result does not depend on input order (tested).

Two valuation anchors (assets and earnings) rather than one, so that one accounting quirk does not make a name cheap. OCF yield is left out so the
same cash-flow line does not appear in both "cheap" and "confirmed". The confirmation is three signs at zero, so no level is fitted.

## 4. Constants and where they come from

None is fitted to an outcome. Each is inherited from an existing repository rule or is structural:

| Constant | Value | Provenance |
|---|---|---|
| tradability | positive volume on each of the last 20 sessions | `alpha-opportunity-model-v2` PIT traded-at-all guard |
| liquidity floor | median 60-session traded value ≥ KRW 1bn | `expectedTradeNotionalKrw` (10m, `config.json` KR) ÷ 1%-of-daily-value capacity rule |
| industry floor | 5 eligible members | the industry and within-industry anatomies' floor |
| cheap | top tercile | structural: the finest split stable for 5-15 member groups |
| coverage floor | 60% of the denominator | `config.json` `probabilityCalibration.integrity.minPitCoverage` |
| max names per industry | 2 | `config.json` `selection.maxNamesPerSector` |
| uncertainty unit | 1 × SE | `switch_hurdle.SE_MULTIPLE` (also inherited by `dynamic_breadth`) |
| stock costs | buy 11bp, sell 31bp | `config.json` KR: commission 5, half of 12bp spread, 20bp sell tax |
| passive-leg costs | 15bp each way | an assumption, stated as one (tournament v1 design §2) |

`kr_alpha_signal_v2.design_digest()` hashes all of them, and every receipt carries the digest.

## 5. Target, horizon, benchmark

- **Target:** stock return − 069500.KS return from the execution session (the next KR session after T) over 126 KR sessions, on the repository's
  `BENCHMARK_RELATIVE_ADJUSTED_INDEX_RETURN_PARTIAL_DISTRIBUTIONS` basis. That basis is not a total shareholder return: it understates
  high-dividend names, and those are disproportionately the cheap ones, so the bias runs **against** H2.
- **Horizon:** H126 primary. Valuation and quality information resolves over 126-252 sessions (philosophy v2 §7). H126 is the shorter end, spans two
  reporting cycles, and is a horizon the calibrated inference engine covers (`alpha_inference_calibration_v4.calendar_time_sn_interval`, validated
  at H126 in calibration v4/v5). H252 is secondary and descriptive only: its effective sample is half and its interval is not calibrated.
- **Benchmark:** 069500.KS, unchanged. Its unexplained accrual against the same-data constituent reference stays documented and unrepaired. Holding
  it as the comparator also biases against active selection.
- **Split:** every result is reported as (stock − leave-one-out industry) + (leave-one-out industry − 069500.KS), the within-industry anatomy's
  decomposition. H2 claims the first term.

## 6. Tests

All statistics are per signal date first, then averaged with equal date weights. Intervals use the calibrated calendar-time interval at H126.

| ID | Comparison | Role |
|---|---|---|
| **P1** | mean(CHEAP_CONFIRMED) − mean(CHEAP_UNCONFIRMED), same date | **primary**: is confirmation information inside cheap names? |
| **P2** | equal-weight CHEAP_CONFIRMED − 069500.KS, net of one round trip | **primary**: is the confirmed-cheap state investable? |
| A1 | P2 split into within-industry and industry terms | attribution: stock selection vs industry tilt |
| B0 | 100% 069500.KS | passive default |
| B1 | equal-weight eligible universe | universe carry |
| B2 | all cheap names, no confirmation (value only) | the simple value baseline; P2 − B2 is the incremental test |
| B3 | top within-industry tercile of `relative126` (momentum only) | the simple momentum baseline |
| B4 | top tercile of the mean of value and momentum percentiles | value + momentum baseline; H2 must not be worse |
| N1 | the P1 contrast among EXPENSIVE names (bottom value tercile) | negative control: generic quality vs value-specific confirmation (H2 needs P1 > N1) |
| N2 | P1 under within-date permutation of confirmation among cheap names (+1-corrected p) | negative control: is the ordering better than chance? |

A date enters P1 only with at least 3 confirmed and 3 unconfirmed cheap names. Otherwise it is `NOT_EVALUABLE` and counted, never imputed.

## 7. Falsification and verdicts (decided before any number exists)

| Verdict | Condition |
|---|---|
| `REJECTED` | P1 point estimate ≤ 0, **or** P2 net ≤ 0, **or** N1 ≥ P1, **or** A1's within-industry term ≤ 0 while P2 > 0 (industry tilt, not stock selection) |
| `INCONCLUSIVE` | none of the above, but the P1 or P2 interval contains zero, or P2 − B2 ≤ 0 (no increment over plain value) |
| `SUPPORTED_DEVELOPMENT` | P1 and P2 intervals clear zero, P2 > B2 and P2 ≥ B4 at point estimates, N1 < P1, N2 permutation p < 0.05 |
| `BLOCKED` | per-date readiness fails on more than 20% of scheduled dates, or the evaluation needs a terminal outcome that is unresolved (§9) |

`SUPPORTED_DEVELOPMENT` permits only the next step (a calibration and prospective receipts). It is never confirmation and never promotion.

## 8. Evidence classes

- `DEVELOPMENT_HISTORICAL_OUTCOME_EXPOSED`: anything computed on KR dates through 2026-09-14. The within-industry anatomy was read before this
  design, so no historical number here can confirm it.
- `PROSPECTIVE_PAPER`: receipts written under a registered authorization after the frozen design merges. `PROSPECTIVE_OUTCOME`: separate records.
- The classes are never pooled into one table, average or headline.

## 9. Costs, investability, portfolio policy, terminal events

- **Entry:** a CHEAP_CONFIRMED name with an authorized forecast enters only if `mu − round trip − 1 × SE > 0`. The round trip is 42bp of stock cost
  plus 30bp of passive leg when the fallback is the benchmark.
- **Hold:** an incumbent that is still CHEAP_CONFIRMED stays while `mu − 1 × SE > 0`, because its entry cost is already paid. This lowers turnover
  without a new parameter. It exits when it is no longer CHEAP_CONFIRMED.
- **Book:** at most 5 names, at most 2 per industry, one 20% slot each, at most 1% of median daily traded value per order. Zero names is a valid
  answer (`NO_ELIGIBLE_OPPORTUNITY`). Slots are never redistributed to fill the book.
- **Fallback:** `PASSIVE_BENCHMARK` (069500.KS) is the primary policy and `CASH` is a separate one. Every receipt names which one is in force, and
  the comparison with passive is always made on the same capital base.
- **Risk:** per-name downside volatility and 252-day max drawdown are recorded on every candidate. They do not size anything in this version.
- **Weekly at most:** receipts exist only on the last KR session of an ISO week, decided from the exchange calendar.
- **Terminal events, conservatively:** a held name that stops trading is never marked at its last price, dropped or assumed to receive anything.
  Its outcome is `TERMINAL_ECONOMICS_UNRESOLVED` until a cited consideration exists, and the portfolio outcome is then `None`
  (`prospective_receipt_core.portfolio_outcome`). A historical development evaluation applies the same rule. If one of the 22 unresolved
  terminations is held, that path is `BLOCKED`, as in tournament v1. It is not excluded after the fact.

## 10. Prospective receipt

Contract: `pipeline/kr_alpha_signal_v2_receipts.py` and `research_specs/kr-alpha-signal-v2-receipt.schema.json`, on the storage format of
`pipeline/prospective_receipt_core.py`. That format is byte-compatible with the three existing study receipts (tested).

- **Identity:** spec SHA-256, design digest, commit SHA plus per-file SHA-256, PIT feature / universe / industry snapshot SHA-256, forecast model
  SHA-256 and training cutoff. A receipt without any of them is refused.
- **Timing:** created after T's 15:30 KST close and before the execution session's 09:00 KST open, not in the future of the writer's clock. The
  public proof is the commit or artifact time of the ledger row.
- **Eligibility:** only for T on or after the first KR session strictly after the KST date of the authorizing merge, so same-day observations are
  excluded. `REGISTERED_AUTHORIZATION` is `None`, so no live receipt can be written yet.
- **States:** `BLOCKED` (identities and counts only), `NOT_READY` (research-only signal, no weights), `NO_ELIGIBLE_OPPORTUNITY`, `CANDIDATE_PORTFOLIO`.
  A blocked or not-ready receipt edited to carry weights fails validation.
- **No leakage:** any outcome-named key at any depth is refused; a forecast trained on a target that had not matured by T is refused.
- **Append-only:** a duplicate `(studyId, signalDate)`, an earlier date, a changed spec or an altered earlier row refuses the append. Bytes are
  never rewritten.
- **Outcomes:** a separate `PROSPECTIVE_OUTCOME` record keyed by `receiptSha256`, built only after 126 KR sessions have closed. The receipt is never
  modified.

## 11. Roadmap and gates

| Step | Scope | Depends on | Gate to pass |
|---|---|---|---|
| **This PR** | tournament closure; opportunity map; this design; receipt core and signal/receipt contract with synthetic tests | — | CI green; sealed files byte-identical |
| **Next PR** | build the PIT feature adapter from existing code (`kr_value_quality_catalyst`, `dart_derive`, v4 crosswalk, price panel) into `ROW_FIELDS`; an outcome-free readiness report (per-date coverage, state counts, P1-evaluable dates) over the committed raw-input artifact; a weekly dry-run writer that can only emit `NOT_READY`/`BLOCKED` | this PR | no label built (call counters and spy tests, as in v5); readiness published before any evaluation is designed further |
| **Following PR** | freeze this design as a spec (hash, sidecar, lock-ref one-shot) and, if readiness allows, authorize ONE constrained development evaluation of §6-7, kept separate from prospective evidence | next PR's readiness | ≥ 80% of scheduled dates READY; tests and verdicts frozen as written here |
| **Then** | register the authorization; schedule the weekly writer; publish `NOT_READY` receipts until a calibration is authorized, then forecast-bearing receipts | the freeze merge | first receipt strictly after the merge's KST date |
| **Later** | evaluate matured H126 receipts (and H252 descriptively) against B0-B4 and after costs, under a separately frozen prospective evaluation plan | enough matured receipts | none promised: a 126-session horizon needs about six months per receipt to mature, and the evidence length needed is decided by that plan, not here |

## 12. Blocked or unvalidated today

- No real signal has been computed. The feature adapter does not exist yet, so the cross-section has run only on synthetic rows.
- Per-date readiness is unknown. Pooled raw coverage (51-75% across the five fields) says the 60% floor can bind, especially in 2015-2016.
- Prospective industry snapshots need the live KIND/KRX label captured on T. That capture is not built.
- No calibration exists, so no expected return, SE or contribution is published, and every receipt would be `NOT_READY`.
- No authorization is registered and no workflow is scheduled.
- Terminal economics for the 22 historical KR terminations stay unresolved. A historical path that holds one is `BLOCKED`.
- H3 ownership collection is manual-dispatch only. Scheduling it is a separate, later change.
