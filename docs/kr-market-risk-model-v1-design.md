# kr-market-risk-model-v1 — preregistration and harness (no outcome computed)

Scientific status: `EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY`.

> **The Market Risk Model v1 design is informed by outcome-exposed Market Anatomy v2 and therefore all historical performance from this model
> remains DEVELOPMENT / EXPLORATORY evidence.**

Every KR date through the frozen end (2026-09-17) has already been seen, by the anatomy and by the researchers. A historical run of this study can say
which architecture *appears* most economically useful on development data. It cannot say that a model is validated. Real evidence can only come from
the prospective receipts described in section 9.

This change freezes the protocol, builds the harness and tests it on synthetic data. **No historical outcome was computed, no candidate's return,
drawdown, Sharpe or cost was looked at, no lock exists and no workflow was dispatched.**

## 1. What the anatomy taught, and why this study is about action

`kr-market-risk-anatomy-v2` is sealed (PR #198, formal run 37244866236, result SHA-256 `7be4f68f…a769`). It stays closed: it is not rerun,
re-thresholded or reread as validation. Its descriptive findings, which motivated this architecture and nothing more:

- **Fast** market-break information, volatility above all, is where the link to near-term downside is clearest.
- **Slow**: plain curve inversion is weak; the re-steepening state after an inversion is more notable at longer horizons.
- **Transition**: VIX level carries information; VIX changes and USD/KRW alone are weak; policy easing marks stress rather than calm.
- **The existing SMA200 + Vol63 overlay is a real trade-off.** "Either leg adverse" caught all 12 large drawdowns early but was on 53% of sessions,
  and 80% of its activations saw no 10% drawdown within H63. "Both legs adverse" was on 17% of sessions and cleaner, but missed half the episodes and
  fired late.

So a new signal hunt is not the next step. The open question is an action question: **when risk rises, how much should KR equity exposure be cut,
so that large losses fall meaningfully without paying too much in false alarms, missed rebounds, time spent de-risked, turnover and costs?**

## 2. Role

This model owns one thing: **how much KR equity risk to take**, as `equityRiskMultiplier` in {1.0, 0.7, 0.4}. 1.0 is the normal budget; below 1.0 is
partial de-risking; there is no leverage. It owns no industry or stock ranking, no security selection, no valuation or excess-return signal, no 0–5
name portfolio, no Kelly sizing and no Market × Industry × Stock integration. The model modules import no stock, industry or portfolio-selection
module and take no ticker (tested).

No machine learning: there are too few independent severe KR market episodes to support a high-dimensional classifier. The model is deterministic,
low-dimensional, monotone in risk and reproducible.

## 3. Three layers — every definition inherited, none tuned

| layer | state | definition (from `kr_market_risk_anatomy`) | cadence |
|---|---|---|---|
| SLOW vulnerability | 0 / 1 | `slow_resteepening_flag_10y3m`: 10y−3m > 0 now and < 0 at some point in the last 504 sessions | calendar month-end |
| TRANSITION stress | 0 / 1 | VIX level (FRED VIXCLS, the anatomy's selected VIX role source) at or above the 0.80 past-only expanding percentile of its own weekly history (≥ 156 observations) | calendar week-end |
| FAST market break | 0 / 1 / 2 | the existing overlay's count: close < mean of the last 200 closes, plus annualised vol63 > 25% | every session (read weekly) |

Inputs: the KOSPI 200 reference the anatomy selected (`FDR_KS200`), FRED `DGS10` and `DGS3MO` (10y−3m on dates where both legs exist) and `VIXCLS`.
Availability lags (4 calendar days for FRED, 0 for the KR close), the 14-day staleness rule, 504, 0.80, 156, 200, 63 and 25% are all the anatomy's
frozen constants, imported rather than restated. No SMA length, volatility window, VIX threshold or curve threshold was chosen here.

Deliberately **not** inputs: the policy-easing flag (a stress marker that would add a degree of freedom), HY/IG credit spreads (valid only from
2023-10), USD/KRW and VIX changes (weak in the anatomy), and the market internals (short sample). Why SLOW is re-steepening rather than inversion is
disclosed as anatomy-informed — that is exactly why the evidence class is development.

## 4. The candidate ladder (frozen; a 2 × 2 on one vocabulary)

Two structural switches, each a hypothesis, on the control's own three levels:

- **GATING** — a single FAST warning reduces nothing unless SLOW or TRANSITION confirms it (false-alarm hypothesis).
- **PREEMPTION** — SLOW and TRANSITION both adverse step the budget down one level (floor 0.4), even with no FAST break (lateness hypothesis).

A severe FAST break (both legs) is 0.4 in every candidate and is never diluted by benign slow data.

| | gating off | gating on |
|---|---|---|
| **preemption off** | **C0** existing baseline control | **C1** confirmation-gated |
| **preemption on** | **C2** preemptive hierarchical | **C3** multi-layer consensus |

Complete mapping (S = SLOW, T = TRANSITION, F = FAST):

| S | T | F | C0 | C1 | C2 | C3 |
|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 1.0 | 1.0 | 1.0 | 1.0 |
| 1 | 0 | 0 | 1.0 | 1.0 | 1.0 | 1.0 |
| 0 | 1 | 0 | 1.0 | 1.0 | 1.0 | 1.0 |
| 1 | 1 | 0 | 1.0 | 1.0 | 0.7 | 0.7 |
| 0 | 0 | 1 | 0.7 | 1.0 | 0.7 | 1.0 |
| 1 | 0 | 1 | 0.7 | 0.7 | 0.7 | 0.7 |
| 0 | 1 | 1 | 0.7 | 0.7 | 0.7 | 0.7 |
| 1 | 1 | 1 | 0.7 | 0.7 | 0.4 | 0.4 |
| any | any | 2 | 0.4 | 0.4 | 0.4 | 0.4 |

C3 is exactly the consensus count: a severe FAST break is 0.4; otherwise count adverse families (SLOW, TRANSITION, FAST ≥ 1): 0 or 1 → 1.0, 2 → 0.7,
3 → 0.4 (tested to equal the switch form on all twelve cells). Every rung moves one thing: C1 vs C0 is gating, C2 vs C0 preemption, C3 vs C1
preemption, C3 vs C2 gating. Slow alone never reduces exposure; transition alone never reduces exposure; every candidate is monotone in each layer and
never exceeds 1.0. No intermediate level was introduced: the ladder tests architecture, not percentages. The table is computed from the module, stored in
the spec and compared on every load.

## 5. Missing data, re-entry and timing

- **Missing is neither benign nor adverse.** A candidate's multiplier is defined only when every completion of the missing layers it reads gives the
  same answer (a missing SLOW does not matter to C1 when FAST = 0 or 2). Otherwise the candidate **holds its previous target** — no information, no
  action — and the hold is counted. Undefined on the first decision date refuses the run. Readiness requires every candidate to be determinable on the
  first decision date and on ≥ 99% of decision dates (the anatomy's FAST coverage bar).
- **Re-entry uses the same state machine.** The multiplier is a memoryless function of today's observable states; normal exposure returns on the first
  decision date whose state maps to 1.0. No trough, no rebound threshold, no minimum hold, no hysteresis. The cost of this (the trend leg and the sticky
  re-steepening flag can keep exposure low after a bottom) is *measured* (section 7), not engineered away.
- **End-date invariance.** Weekly and monthly sampling dates come from the exchange calendar (a session whose next session is in a later week or month),
  never from where the data stop; every input is the value known at t; percentiles are expanding and past-only from the frozen 1990 grid start. The state
  at t is identical whether the data end at t or in 2026 (tested).
- **Timing.** Decisions on calendar week-end sessions; the signal is the decision-date close; the trade is at the **next** KR session's close.

## 6. The economic test isolates the market allocation

The only asset is the KOSPI 200 reference the states are computed on, scaled by the multiplier; the rest is cash. No stock or industry enters. The
retained KODEX 200 route is not used: it starts 2007-01-29, is an as-traded close without dividends and never passed the anatomy's source-quality gates.

- Start: NAV 1 at the first execution close, holding the first target (the initial build is not a rebalance and is not charged).
- Trade only when the target changes, exactly to target × post-cost NAV; holdings drift between trades.
- Costs: the repository's KR buy 15bp / sell 45bp, unchanged (conservative for index exposure, which carries no securities transaction tax), at 1×,
  2× and 3× stress; gross = the same decisions at zero cost. Cash earns zero (`ZERO_KRW_NOMINAL`).
- Basis: a price index, so dividends are omitted on every path. Omitted dividends favour de-risking; zero cash yield disfavours it. Both directions
  are stated; neither size is measured.
- Passive reference: 1.0 always — the participation denominator and a dominance reference; never nominated.

**Evaluation window:** the first decision date on or after 2007-01-01 through the anatomy's analysis end, 2026-09-17. The anatomy's session-quality
window starts 2006-01-01 (zero missing sessions after it); 2006 is warm-up for the 200-session FAST window. Earlier history is warm-up only.

## 7. Preregistered evaluation table

For every candidate (net at 1×, and gross; the stress paths report return and cost drag):

- **Return / participation:** cumulative and annualized return, upside and downside participation versus the passive path, average equity weight,
  share of sessions at 1.0 / 0.7 / 0.4.
- **Downside:** maximum drawdown (with its recovery time), worst rolling H63 and H126 return, downside and total volatility, and per algorithmic
  reference episode (`underwater_episodes` at ≥ 10 / 15 / 20%, no named dates) the candidate's peak-to-trough loss, loss-capture ratio, avoided loss and
  sessions to regain its value at the reference peak.
- **False-alarm cost:** activations (target falls from 1.0), false alarms (no −10% reference loss within H63 of the activation; unmatured windows
  PENDING and excluded), and reduced sessions not followed by a −10% loss.
- **Rebound / re-entry cost:** after each episode trough, reference minus candidate return over H63 and H126, sessions until the target is back at 1.0,
  and reference minus candidate return from the trough to the reference recovery.
- **Implementation cost:** multiplier switches, traded notional, one-way turnover (repository convention) and its annual rate, cost drag.
- **Robustness:** chronological halves (split at the middle session, each rebased), episode subsets by depth; calendar-year returns are descriptive and
  cannot redefine a rule.

Overlapping windows are descriptive: no significance test, no multiplicity correction.

## 8. Preregistered decision (Pareto first, symmetric bands, no weighted utility, no forced winner)

> **Pre-outcome revision 1 (made before any outcome access; all counters zero).** The first version of this section required every candidate to
> improve maximum drawdown by at least 10% versus C0 and then broke ties with a simplicity order. Review showed that is incompatible with C1's own
> hypothesis: C1 is never more de-risked than C0 (it differs only in leaving an isolated FAST = 1 warning at 1.0), so it exists to cut false alarms
> and time de-risked at acceptable protection, and a mandatory 10% drawdown gain made it ineligible by construction. A simplicity order would also
> have silently preferred the least-structured hypothesis. Both were replaced below. The revision is recorded in the spec (`preOutcomeRevisions`)
> and changes no candidate, state, threshold, multiplier, cost, window or diagnostic.

Axes, all net of 1× cost over the full window: **net annualized return** (higher), **maximum drawdown** (higher, i.e. shallower), **share of sessions
de-risked** (lower).

1. **Pareto elimination.** Remove any candidate dominated by another candidate or by the passive path (at least as good on every axis, strictly
   better on one).
2. **Non-inferiority versus C0 — both required.** Net annualized return ≥ C0's − 0.50 pp, **and** |max drawdown| ≤ 1.10 × |C0's|.
3. **At least one meaningful improvement versus C0.**
   - *Efficiency route:* net annualized return ≥ C0's + 0.50 pp (drawdown being non-inferior), for fewer costly false alarms and better participation.
   - *Protection route:* |max drawdown| ≤ 0.90 × |C0's| (return being non-inferior), for meaningfully shallower losses.
4. **Outcome.**
   - Exactly one survivor → it is the development nomination.
   - No survivor → `NO_CANDIDATE_NOMINATED_CONTROL_RETAINED`.
   - Several survivors → `NO_UNAMBIGUOUS_NOMINATION_PARETO_TRADEOFF`. Step 1 already removed every dominated candidate, so survivors are mutually
     non-dominated: each beats another on some axis. Ranking them (by return, by simplicity, by anything) would be a preference between hypotheses —
     fewer false alarms, less lateness, both — that this protocol does not own, so **no tie-break exists**. The trade-off is reported, and every
     candidate remains in the prospective receipts.

The 0.50 pp and ±10% bands are round development tolerances fixed here before any candidate outcome, applied symmetrically (the same band is the
non-inferiority margin and the meaningful-improvement margin). No threshold is fitted; no weighted score exists; neither CAGR nor drawdown alone can
decide. A value exactly on a band edge counts as inside it (a 1e-12 float tolerance, frozen). Missing values never pass a band. A nomination is a
**development** result for later integration and prospective receipts — never validation, never production. For prospective receipts the final
architecture is the nominated candidate, otherwise C0.

## 9. Prospective contract (designed; not running)

`pipeline/kr_market_risk_model_receipts.py` and `research_specs/kr-market-risk-model-v1-receipt.schema.json`. On every future decision date, before
the execution close, one immutable receipt records: the signal and execution dates, the SHA-256 of every input read, the layer inputs, the SLOW /
TRANSITION / FAST states, **every** candidate's multiplier (so the prospective record does not depend on the nomination), the final architecture
(the sealed nomination, C0 when none) and its `finalEquityRiskMultiplier`, the model version, the spec hash, the code identity, a timestamp and the
receipt's own digest. Receipts are appended to a JSON Lines ledger; a duplicate key, an out-of-order date, a changed spec or an altered earlier row
refuses the append. A receipt is evaluated only after its horizon (21 / 63 / 126 sessions) has matured. Prospective and historical evidence are
separate classes and are never pooled. No receipt is written and no schedule exists in this change.

## 10. Lifecycle and the automatic Draft seal

```
workflow_dispatch on merged main -> committed spec + sidecar -> pins (predecessor, inputs, closure) -> outcome-free readiness (dates only)
-> no result / marker / manifest -> no lock under the study prefix -> DURABLE LOCK (atomic POST /git/refs, two tags) -> marker
-> first value read -> outcomes -> immutable result artifact
-> seal job: run identity (this workflow, workflow_dispatch, main, the locked commit, execute job succeeded), artifact name = results-<runId>
   (never an attempt artifact), archive SHA-256 = GitHub's digest BEFORE extraction, exactly three files, manifest -> result and marker bytes,
   spec SHA everywhere, marker lock refs on the locked commit with zero values read before it, both lock tags verified by GET
-> exact bytes copied (renamed only) + provenance -> branch research/kr-market-risk-model-v1-result-seal-<runId> -> ONE Draft PR -> a human merges
```

The seal code (`pipeline/kr_market_risk_model_seal.py`) imports only the standard library — it cannot recompute, rerun or reinterpret anything — and
its only pull-request write is a `draft: true` create. It never merges, never marks ready, never seals over an existing file. Any mismatch stops with
no PR. `mode: seal` re-attempts **only** the seal of an earlier successful execute run. A failure before the lock spends nothing; a failure after it
consumes the study for good — **do not retry**; the attempt artifact is kept under `-attempt-<runId>` and the job summary says the study is consumed.

## 11. Freeze

`research_specs/kr-market-risk-model-v1.json` (canonical SHA-256 in the sidecar) freezes candidates, states, multipliers, re-entry, missing-data rules,
metrics, horizons, costs, decision semantics, input identities, the lifecycle and the prospective contract, and hash-pins the import closure, the
sealed anatomy artifacts, the source bytes, the workflow, the scripts, this document and the receipt schema. `load_spec` rebuilds every scientific
section from the modules and refuses any difference. Changing any of it after outcome access requires a **new study identity**.
