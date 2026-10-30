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

Keep three separate statements. The earlier `IMPROVED`/`NOT_IMPROVED` labels
are replaced by **`DESCRIPTIVE_SIGN_ONLY`**. Separate `numericalRelation` and
signed differences retain direction, equality and comparator disagreement;
`economicVerdict` is null. `1e-10` is floating equality only. No complete
synthetic readout can emit an economic-success label or adopt a hurdle:

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

## One bounded next experiment — executable design, historical execution NO-GO

`market_research_c1c_contract.contract()['economicExperimentProposal']` is the
machine-checked **unregistered proposal**, not an execution packet. Its minimal
primary question is KR C0 structural `REENTRY - BASE`, H126; H252 is secondary.
Keep every other arm, the eight same-arm C1-minus-C0 contrasts and the separate
post-outcome breakout family as descriptive comparisons. The proposed fixed
window is the retained 2012-01-02 to 2026-09-14 date intersection, not a newly
untouched sample. All of it remains outcome-exposed development.

Use fixed XKRX weekly decision ends, finality at the later of close+1h and
18:00 KST, next-session **close** execution, and maturity at execution-position+H.
Carry causal pre-window policy memory; do not initialize from future outcomes.
Signals retain KS200 and the original spread/VIX rules; the economic valuation
uses069500 ETF returns. Both readings must use the same signal-price/state
targets, rather than regenerate a favorable signal from an adjusted ETF series.
ETF, candidate and matched-exposure paths share funded entry, terminal
liquidation and 5.5bp buy/5.5bp sell at 1x/2x/3x costs. Report net ETF-relative
returns, CAGR pp (convert each log-growth with `expm1` first), negative-level
funded MDD and nonnegative daily CVaR95 loss separately. Mean-exposure matching
is an ex-post diagnostic, not beta equality or tradable timing evidence.
Asset/cash/action gaps block a fixed cohort; never drop it after outcomes or
fill it with zero. State gaps keep the existing domain-completion/hold rule.

Retained inputs below were **byte-hash checked only** in this continuation;
no historical states, target weights or returns were computed:

| Retained evidence | SHA256 | What it does not establish |
|---|---|---|
| `data/kr-market-risk-anatomy-v1/sources/FDR_KS200/normalized.csv` | `729a94b81dd45d1c5d1ab2ff692ec249bd5c9c4f24598d648d7f88010f193478` | Price-index bytes are not ETF distributions, vendor rights or actual publication proof. |
| `.../FRED_DGS10/normalized.csv` | `db7dc41d9d40ad5608e0ead00086ec15f5969cf785aa378f05cda576a160bc92` | Observation dates and inherited four-day lag/14-day staleness are not release/vintage authentication. |
| `.../FRED_DGS3MO/normalized.csv` | `7ce2bdbe2547e4fc16c18a36295871d16099d60f51f10edfc2cd8d42218dc06c` | Treasury yield observations are not a tradable KRW cash-return path. |
| `.../FRED_VIXCLS/normalized.csv` | `dd0ccfe0a13f5e72a842dc27d53733748f24fb380808a7b2fb9babb40caa00ef` | Source rights and actual prior-known timestamps still need scoped evidence. |
| `docs/audits/kr-alpha-atlas-phase-c-integrity/benchmark-reconciliation-corrected.json` | `58580c4370ec2c5afa124f849afbc4fa7b5c879012e75ebbd48ee7c7a0e659a9` | Corrected retained069500 cash-distribution chain is not new C1c rights/action/timestamp admission; original sealed benchmark/results remain unchanged. |

US SPY/DTB3 evidence is separately listed in the existing
[`rp1-c1-us-source-freeze-39080239146.json`](research-program/sources/rp1-c1-us-source-freeze-39080239146.json).
Its identity/hash manifest and prior-known ACT/360 discount-yield approximation
are not a new source licence, independently issuer-certified actions, current
raw-byte possession or authorization to rerun C1. US is not silently pooled into
the primary KR experiment. No admitted actual KR cash-return source is supplied;
zero cash remains only an opportunity-cost sensitivity scenario.

**Dependencies before execution:** scoped use/retention rights; actual
release/vintage and state-input known-at proof; complete ETF distributions,
splits and return-basis reconciliation; actual cash convention/source or an
explicitly registered scenario-only interpretation; immutable code/input
closure; economic margins and zero/MDD boundary policy; a calibrated
dependence/multiplicity/first-look design. These fields remain null, not zero,
and power is unestimated. The existing52-week/eight-block proposal does not
resolve them. Only then can a new exact-hash owner authorization be requested.
Until then **historical execution NO-GO**; the next valid command is the existing
`python scripts/check_market_research.py verify` plus synthetic tests. No new
historical runner, locks, permits or live receipts are created here.
