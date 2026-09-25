# Alpha opportunity model v3: sealed preregistration

**Status: `BLOCKED_BY_DATA_INTEGRITY`.** Spec
`research_specs/alpha-opportunity-model-v3.json`, seal in the adjacent
`.sha256`. No historical label, return, IC, calibration table, model fit or
portfolio path was computed for this study. There is deliberately **no v3
workflow**: `scripts/run_alpha_opportunity_model_v3.py --execute` refuses on
the sealed status before any input is read. The repair route is
`docs/alpha-opportunity-v3-data-repair-plan.md`.

## Lineage

| Version | What it is | Status |
|---|---|---|
| `alpha-opportunity-model-v1` (`e3c699b1…6dd6e`) | first opportunity preregistration | `BLOCKED_PREREGISTRATION`, never executed |
| `alpha-opportunity-model-v2` (`97c3727b…0e19`) | benchmark-as-outside-option redesign | sealed `READY`, never historically executed |
| `alpha-opportunity-model-v3` | separates expected value from probability and confidence; audits identity and survivorship in both regions; seals only the computed execution closure | `BLOCKED_BY_DATA_INTEGRITY` |
| data-foundation repair | separate work (repair plan) | — |
| `alpha-opportunity-model-v4` | new immutable preregistration over repaired, sealed, re-audited inputs | the **only** version that may become `READY_FOR_HISTORICAL_EXECUTION` |

v1 and v2 are unchanged. v3 checks both by their own spec digests and sidecars
on every load, never through their dependency lists. v3 is never unblocked in
place, and no alpha outcome is read before v4 is sealed.

## 1. Expected value is the alpha question

v2 counted a name as `ACTIVE_OPPORTUNITY` only if four conditions held together:

- expected net alpha > 0
- P(net alpha > 0) > 0.5
- the lower bound of each head's bootstrap interval above that same outside-option value

The last three are not the outside-option comparison. They are hidden hurdles on
whether expected value exists at all. A payoff of 40% × +30% and 60% × −8% has
positive expectation and a probability of beating the benchmark below one half,
and a positive fitted mean can have an estimation interval that spans zero.

v3's alpha layer (`pipeline/alpha_opportunity_v3_decision.py`) has one rule:

```
expectedNetAlpha = E[R_i − R_benchmark(i)] − roundTripCost_i      (benchmark: 0, cost 0)
expectedNetAlpha > 0   → POSITIVE_EXPECTED_ALPHA
expectedNetAlpha ≤ 0   → BENCHMARK_EXPECTED_VALUE_PREFERRED
(+ NOT_TRADABLE / UNMEASURED for the PIT tradability guard and invalid predictions)
```

Two readings are published beside that class. Neither can change it.

- **Outperformance probability.** `probabilityNetOutperform` = P(R_i − R_b −
  cost > 0) comes from the Logistic head, which is fitted **separately** from
  the Ridge expected-return head. The two are not one coherent predictive
  distribution, so the probability is **not** a median or any other quantile
  of the Ridge prediction. The four states say only what is known:
  - `EXPECTATION_POSITIVE_OUTPERFORM_PROBABILITY_ABOVE_HALF`
  - `EXPECTATION_POSITIVE_OUTPERFORM_PROBABILITY_NOT_ABOVE_HALF`
  - `EXPECTATION_NOT_POSITIVE_OUTPERFORM_PROBABILITY_ABOVE_HALF`
  - `EXPECTATION_NOT_POSITIVE_OUTPERFORM_PROBABILITY_NOT_ABOVE_HALF`
- **Uncertainty.** These are two different objects, checked in code:
  - `expectedNetAlphaLower/Upper` and `probabilityLower/Upper` come from
    `prediction_uncertainty`: 5th/95th percentiles over 200 training-only
    moving-block refits. That is **fitted-value sampling uncertainty**, not a
    return interval.
  - `predictiveResidualRms` comes from `matured_residual_scale`: realised minus
    predicted RMS over past matured out-of-fold predictions. That is
    **predictive outcome dispersion**.

The opportunity surface is every `POSITIVE_EXPECTED_ALPHA` name, ordered by
`expectedNetAlpha` for analysis only. An empty surface is
`NO_POSITIVE_EXPECTED_ALPHA`.

None of the following exists, and the loader refuses a spec that gives any of
them a value:
- a Top-N or US/KR quota
- an invested fraction
- a +X% hurdle, a probability hurdle or a lower-bound hurdle
- any sizing field

Risk preference, confidence weighting, Kelly, volatility targeting and dependence
belong to a later portfolio layer.

**Carried unchanged from v2:** the model family (Ridge and Logistic heads, plus
a fixed shallow HGB complement), features, 21- and 126-session horizons,
transforms, dated costs, the tradability guard and the inference scheme. No
feature was found PIT-unsafe.

**Pre-registered evaluation, for v4:**

| | What it tests | Requirement |
|---|---|---|
| **A** | Absolute calibration: `realised = a + b·predicted`, date-balanced, pooled | b lower bound > 0; MSE improvement |
| **B** | Ordering | rank IC and within-date slope |
| **C** | Probability head | Brier, log-loss and pooled ECE |
| **D** | The outside-option test, on names with predicted `expectedNetAlpha > 0` | realised net alpha lower bound > 0, and its same-date spread over non-positive names > 0 |
| **E** | Stability | as in v2 |

For D, the positive-region slope and prediction terciles are disclosed, and the
`…OUTPERFORM_PROBABILITY_NOT_ABOVE_HALF` and interval-spanning-zero subsets are
disclosed separately, none of them gated. No threshold other than 0 is
evaluated.

## 2. Identity comes first

`pipeline/alpha_opportunity_v3_identity.py` classifies every membership symbol
before any survivorship statistic is computed. Its evidence is
`research_specs/alpha-opportunity-model-v3-us-identity-evidence.json.gz`:
Symbol, name and CIK read from **exactly** the upstream
`datasets/s-and-p-500-companies` commits the pinned membership cites. Their
Symbol columns reproduce every pinned member list, and the build is
byte-identical when re-run. The upstream file carries CIK only from 2023-04-13.

Symbols are joined only with explicit evidence, and each join records which of
three bases it used:

- **`SAME_CIK`:** same CIK, the two symbols are never co-listed (share classes
  such as GOOG/GOOGL are), and the successor is present at the exit snapshot.
- **`PREVIOUSLY_ANNOTATION`:** the successor's own upstream row says
  "(Previously X)".
- **`IDENTICAL_NAME`:** the same security name at the exact exit snapshot, never
  co-listed.

An acquired or delisted company is never priced from its acquirer. A panel that
starts after a member left is never read as that member's history. Anything
else stays unresolved.

**The two malformed identifiers** are upstream data errors in the Symbol
column, traced to their source rows:

- **`American Airlines Group`:** commit `9217bee` (2021-03-11), CSV row
  `American Airlines Group,reports,Airlines`. AAL is missing only from that
  snapshot.
- **`RVTY (Previously PKI)`:** commit `a9ae84a` (2023-12-31). RVTY is missing
  only from that snapshot.

Both resolve by rule: the real symbol is absent where the key sits, present in
both neighbouring snapshots, and named by the key. No other malformed identifier
exists in either region.

**US identity classes** (827 identities after resolution):

| Class | Count |
|---|---|
| current member, own panel | 496 |
| current member, panel starts after membership began (earlier issuer or later listing, e.g. FOXA) | 7 |
| departed, removed from index but still trading (own history) | 97 |
| departed, panel partial own history | 2 |
| verified rename (13 priced through successor; CDAY→DAY successor has no panel) | 14 |
| departed, symbol's only panel belongs to a **later security** (reuse: FB, LB, STI, APC, NFX, …) | 29 |
| acquired (sealed corporate-action book: ESRX) | 1 |
| **departed, no usable panel, exit not established by sealed evidence** | **181** |

Pre-2023 renames that also changed the company name (for example FB→META,
ANTM→ELV, PCLN→BKNG) carry no CIK in the evidence, so they stay among the 181.
They are not guessed.

**Reconciliation, computed by the audit rather than narrated:**
- **829 vs 828:** v2 took the union over *all* snapshots. v3 uses only snapshots
  that some weekly date actually reaches, and `RVTY (Previously PKI)` sits only
  in a snapshot no date reaches.
- **194 vs 195:** v2's list set the malformed keys aside. v3's first seal
  counted `American Airlines Group` as a departed security with no panel.
- **Corrected no-usable-panel count:** 195 − 1 (malformed key resolved) − 11
  (renames priced through successor: BK, CBG, FI, HCN, JEC, MMC, PEAK, PKI, RE,
  SATS, WLTW) + 29 (reused-symbol panels, which the first seal counted as
  priced) = **212**.

The correction is stricter, not looser.

## 3. Survivorship after identity

`docs/results/alpha-opportunity-model-v3-survivorship-audit.json` is input-only
and byte-identical on repeated runs. Its sources are the signal-history commit
`4ea107e`, replay-v16 manifest `f0781292…` (through 2026-09-14), the pinned
membership and the identity evidence.

### US: still blocked

| | Value |
|---|---|
| identities / current / departed | 827 / 503 / 324 |
| no usable history: departed / current | **212 (65.4%) / 0 (0%)** |
| departed priced by own history / via verified rename | 99 / 13 |
| **securities in the panel that ever stop trading** | **0** |
| missing forward endpoints among tradable member-dates | **0** of 301,714 (21-day) / 290,710 (126-day) |
| departed-only no-usable-panel share of member-dates | 30.32% (2013), 22.48% (2016), 17.03% (2019), 9.12% (2021), 4.13% (2023), 1.79% (2025), 0.54% (2026) |

After identity cleanup, the earlier US blockers are reassessed as follows:

- **`US_DELISTED_MEMBER_HISTORY_ABSENT`:** still applies. The panel holds no
  terminated company.
- **`US_PANEL_SYMBOL_IDENTITY_UNVERIFIED`:** still applies, narrowed. Malformed
  keys are resolved, renames verified and reuse detected, but the panels are
  keyed by bare ticker and pre-2023 upstream rows have no CIK.
- **`US_NO_STRUCTURAL_RESTRICTED_WINDOW`:** still applies. The departed-only share
  is nonzero in every year, so any cutoff would be a tolerance.
- **`US_EXIT_IDENTITY_UNRESOLVED`:** new, covering the 181 unresolved exits.

Endpoint stress cannot help. The US has zero missing endpoints, because the
absent companies never entered the sample.

### KR: coverage complete, lineage and terminal values missing

| | Value |
|---|---|
| members / current / departed | 260 / 120 / 140, all priced by their own KRX codes; no malformed codes, no renames or reuse needed |
| terminated securities observed to their last session | 22 |
| terminated names with any dividend event | **0 of 22** (vs 215 of 238 continuing) |
| affected tradable member-dates | 3.74% (7.93% in 2013 → 0.76% in 2025) |
| missing forward endpoints (all on terminated names) | 22 (21-day) / 300 (126-day) |
| termination type | `TERMINATION_TYPE_UNRESOLVED` for all 22 (the `krTerminations` audit table lists KRX names and last sessions) |

**KR blockers:**
- `KR_TERMINATED_NAME_DIVIDEND_LINEAGE_ABSENT`: Yahoo distributions do not
  serve delisted KR tickers.
- `KR_TERMINAL_CONSIDERATION_UNRESOLVED`: dividends alone do not value a
  merger, share exchange, tender or delisting.

## 4. Dependency closure

The sealed set is recomputed on every load. It is the top-level and lazy import
closure of four entry points, plus declared data inputs:

- **Entry points:** the runner, the audit script, the identity-evidence builder,
  and the decision module.
- **Data inputs:** the audit, the identity evidence, the v1 and v2 specs with
  their sidecars, the v1 registry and US membership, the v2 input audit, and
  `requirements.txt`.

Behaviour is enforced by tests:
- a new unsealed import raises `DEPENDENCY_CLOSURE_CHANGED`
- an edited sealed file raises `SEALED_DEPENDENCY_CHANGED`
- `kelly_portfolio`, `longterm`, `replay_valuation`, `selection_null` and
  `portfolio_validation` are **not** in the closure, and editing them changes
  nothing

The DART ownership shards, `pit-*.jsonl` and collector bookkeeping are
documented adjacent datasets, not inputs.

## 5. Scope

v3 is a conservative baseline model. It does not test fundamental state ×
change × liquidity shock × price leadership × investor flow × event context,
and its blockage says nothing about those hypotheses.

`Alpha opportunity model v2` must not be run: its US leg would train and
evaluate on the survivor-only sample measured here.
