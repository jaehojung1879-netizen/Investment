# C1c B1: economic criteria for independent review

Status: **PROPOSED_NOT_REGISTERED_NOT_AUTHORIZED**. This note changes no rule,
threshold, hypothesis, cost, execution authorization or production behavior.
The implemented B2 repair is separate: it reconstructs invented policy paths;
it does not establish the economic value of those paths.

## What is already fixed, and where it applies

The [sealed KR model decision](../research_specs/kr-market-risk-model-v1.json)
(`decision`) and [implementation](../pipeline/kr_market_risk_model.py)
(`annualized`, `development_nomination`) define a development nomination against C0:

1. Pareto elimination on net annualized return, MDD and reduced-session share.
2. Both non-inferiority conditions: annual return at least C0 minus **0.005**,
   and absolute MDD no greater than **1.10** times C0's.
3. At least one improvement: annual return at least C0 plus **0.005**, or
   absolute MDD no greater than **0.90** times C0's.
4. No forced winner or tie-break; multiple survivors remain a trade-off.

[The original design, section 8](kr-market-risk-model-v1-design.md), calls these
round pre-outcome **development tolerances**, not validated effect sizes or
significance levels. They remain binding for that sealed study. The
[US primary replication](../pipeline/rp1_c1_us_exposure_spec.py) inherits that
decision; its separate economic reading cannot change it.

These numbers are provenance for review, **not defaults adopted by C1c**:

| Quantity | Existing rule | C1c difference requiring a decision |
|---|---|---|
| Annual return | CAGR; 0.005 means 0.50 percentage points/year | C1c reports annual log growth `g`; CAGR is `expm1(g)`. Applying 0.005 directly to `g` changes the unit. |
| MDD | Relative 110% non-inferiority / 90% improvement | C1c uses funded entry and final liquidation. Zero or tiny control MDD needs an explicit boundary policy; equality at zero is not protection improvement. |
| Tail risk | No economic CVaR hurdle in that decision | C1c daily CVaR95 loss differs from the US descriptive monthly statistic. No inherited 10% CVaR band exists. |
| Comparisons | Original C0, full window, 1x costs | C1c has two distinct families, C0 BASE and an ex-post mean-exposure-matched static diagnostic; source/ETF/cash conventions differ. |

## Proposed separation of conclusions

Keep three separate statements. The existing `IMPROVED` is **numerical
dominance under a proposed descriptive policy**; `1e-10` is floating equality
only. Neither that label nor a green CI establishes either remaining statement:

- **Economic materiality: unregistered.** Before any supported economic verdict,
  fix the metric units, return and downside non-inferiority margins, at least one
  required material gain, tail-risk treatment, and zero/missing-value rules.
  A possible review option is the original efficiency/protection structure with
  CAGR reconstructed from log growth. Its margins are **unset**, including any
  decision to reuse 0.005 or the MDD ratios. Do not select margins by viewing
  C1c historical performance or sweeping tolerances.
- **Inferential support: unregistered.** Economic tolerances are not confidence
  intervals. Fix a paired dependence-aware uncertainty/calibration method, the
  tested family and multiplicity treatment, decision error rate, minimum
  detectable effect and power assessment before supported claims. No alpha
  level or new significance test is adopted here.

Preserve C0 as the primary control and C1 as auxiliary. Keep the pre-result
one-rung structural reentry and post-result 20-session breakout under separate
hypothesis IDs. Retain both fixed one-axis contrasts (`REENTRY - BASE` and
`COMBINED - HARD_EXIT`) within each family; do not select a favorable family,
control, horizon, country, basis or cost after results. The exact primary family,
horizon and multiplicity family still require explicit registration.

Record the paired regional passive ETF and the candidate's mean-exposure-matched
static path on the same dates, funded entry/liquidation and costs. The static
mix uses the full path and is an **ex-post diagnostic**, not an executable
forecast or proof of beta matching. Improvement versus C0 alone is not alpha
versus 069500.KS/SPY. Mixed growth/downside outcomes remain explicit trade-offs
unless a risk preference was fixed before results; no weighted score is added.

## Readiness before a new authorized interpretation

The [current contract](../pipeline/market_research_c1c_contract.py) proposes 52
matured weekly decisions and eight non-overlapping blocks. These are support
floors, not a power guarantee: H126/H252 overlap, and disjoint holdings can still
share market regimes. The maturity calendar does not establish independence.
Use the [common research contract](research-program/04-common-research-contract-ko.md)
as constraints, not as automatic calibration of this new growth/MDD/CVaR family.

KR zero cash remains an opportunity-cost scenario. Any investable interpretation
needs approved ETF total-return/corporate-action data, actual prior-known cash
convention and rights, plus implementation cost and missingness treatment.
US cash/ETF admission is separate. Diagnostic/economic or country disagreement
must not authorize promotion. Keep incomplete comparisons and terminal gaps
visible rather than select only measurable winners.

Owner registration must therefore identify the exact new protocol/code/input
closure, controls/contrasts, units and unset economic margins, source/cash/cost
basis, evaluation window and first look, missingness/maturity rules and calibrated
uncertainty/multiplicity/power design. Until then: **economic verdict unresolved,
execution unauthorized, promotion forbidden**. Already-exposed history remains
developmental; it cannot become retrospective OOS. Do not rerun the spent C1
experiment, alter its seal or infer a new authorization from this proposal.

Review provenance: only specification/source semantics inform this proposal.
Initial broad discovery searches incidentally returned existing result snippets;
they were not used to choose a margin or recommendation. This rule review is
not represented as outcome-blind confirmation. No historical performance was
executed or recalculated.
