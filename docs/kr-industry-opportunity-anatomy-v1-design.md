# kr-industry-opportunity-anatomy-v1 — design and protocol (exploratory industry map)

> **PROTOCOL + HARNESS + SYNTHETIC TESTS ONLY. NO HISTORICAL INDUSTRY OUTCOME HAS BEEN COMPUTED.**
> `scientificStatus: EXPLORATORY_DEVELOPMENT_ON_PARTIALLY_RECONSTRUCTED_KR_HISTORY`. The frozen spec
> (`research_specs/kr-industry-opportunity-anatomy-v1.json`), the harness and the workflow were written and tested on synthetic data
> only. No industry return, relative return, feature association, tercile spread or market-state split has been computed or inspected.

## 1. Question and boundary

> Do observable industry states at signal date t show a stable historical association with the subsequent benchmark-relative
> return of that industry?   `IndustryState(s, t)  ->  R_industry(s, t:t+h) - R_market(t:t+h)`

This is an industry **anatomy**: not an Alpha model, not stock selection, not a portfolio, not a recommendation and not evidence of
prospective predictability. Every Korean date through the 2026-09-14 development cutoff is outcome-exposed and the industry history is a
reconstruction, so every result is permanently exploratory. It cannot validate, rescue or promote anything, and there is no PASS/FAIL.

The merged membership foundation ended `DATA_FOUNDATION_INSUFFICIENT_V4` under its own frozen gates (terminal coverage 0 / 2,345; too few
names in groups of five). That result is **not relabelled**. This study is a separate exploratory use of the reconstructed membership with
its own explicit eligibility rules, frozen before any industry outcome exists.

## 2. Pinned inputs (reused, never recollected)
* Membership: `data/kr-industry-membership-foundation-v4/state/{intervals,audit}.json.gz`, the frozen 14-group crosswalk and protocol,
  all by SHA-256 in the spec. v4 facts re-checked on every load: 260 securities, 610 dates, 73,200 name-dates, 69,756 classified,
  78 raw labels, 14 groups, 0 conflicts, terminal coverage 0 / 2,345.
* Prices, market caps, PIT accounting, benchmark state: the preserved raw artifact `kr-model-raw-inputs-36844599518` (artifact 11157875265,
  archive digest `42eeb18b…cce7`, input identity `233df37e…66a7`), through the sealed v1 loaders. DART, KIND and KRX are never contacted.
* Benchmark `069500.KS` and return basis `BENCHMARK_RELATIVE_ADJUSTED_INDEX_RETURN_PARTIAL_DISTRIBUTIONS`, both checked equal to the
  accepted anatomy spec. The return is **not** total shareholder return and is never called that.

## 3. Industry-date eligibility (frozen)
An industry is eligible at t only if: it is one of the 14 frozen v4 groups; each constituent's industry is known at t under the
reconstruction (statuses `CURRENT_KRX_KIND_ANCHOR`, `VERIFIED_KRX_KIND_CHANGE_EVENT`, `RECONSTRUCTED_STABLE_NO_CHANGE_EVENT`,
`PREFERRED_SHARE_OF_ANCHORED_COMMON`); at least **5** classified PIT Top120 members are present; the cohort is the membership at t and
is not revisited; and the measurement's inputs exist. UNKNOWN names never fill a cohort, terminal names are never replaced by
survivors or successors, and an ineligible industry-date stays INELIGIBLE with a reason, never zero.
The reconstruction is not point-in-time exact: most classified name-dates rest on a no-change inference. Membership coverage and the
share by reconstruction status are reported beside every result.

## 4. Targets
Entry = next KR session after t; exit = H sessions later (repository calendar); H126 primary, H63 and H252 descriptive. Cohort and weights
fixed at t for the whole window. **Primary:** cap-weighted industry return (weights = signal-date market caps) minus the same-window
benchmark return. **Robustness:** equal-weight. Roles are frozen; neither is chosen after execution. An industry-date is MATURED only when
**every** cohort member has a matured return under the accepted terminal discipline; otherwise it is UNRESOLVED (no renormalisation over
survivors). A missing cap for any member makes the primary lens INELIGIBLE (fail closed); the equal-weight lens does not need caps.

## 5. Signal-time features (past-only)
A relative momentum 63 / 126 (cap-weighted trailing return minus benchmark); B breadth: positive trailing-126 fraction, above 126-session
moving average fraction, positive relative-momentum fraction; C risk: downside volatility of the fixed-weight industry series (126 sessions),
constituent dispersion; D concentration / liquidity: top-1 and top-2 cap share, constituent count, median log ADV60; E fundamentals:
median (with at least 3 finite members and 60% coverage) of the eight PIT accounting ratios already in the accepted overlay; missing is
missing. F market state (`riskMultiplier`) is identical across industries on a date, so it is only a descriptive conditioning variable,
never a cross-sectional feature. **No ECOS/FRED or other revised macro history enters. No industry-specific cycle data is invented.**

## 6. Anatomy statistics (descriptive)
Primary: per-date Spearman between each feature and the H126 market-relative target across eligible industries (valid only with at least
**8** industries holding both values), reported as mean, median, sign fraction, valid dates and a year table. Top-minus-bottom **tercile** spread
needs at least **9** industries (k = floor(n/3) in each outer tercile, middle absorbs the remainder), ordering by (feature, industry id), and a
tie straddling a tercile boundary makes the date invalid. Secondary: H63/H252, cap vs equal weight, outcome-window slices (pre-2025,
2025-or-later, touches-2026), and a date-aware HAC standard error labelled descriptive. The weekly signals overlap, so effective
independent dates are about dates / (H/5).

## 7. Concentration sensitivity (diagnostics, not routes)
FULL; leave the largest constituent out of every cohort (cohort must still hold 5); exclude Samsung Electronics and SK Hynix (fixed rule,
preregistered here); and two concentration strata by top-1 cap share at the fixed 0.35 cutoff. None is promoted over another.

## 8. Execution is separate and one-shot
Pull requests run synthetic tests, `verify` and `readiness` only. `execute` exists as a manual dispatch on merged `main`: committed spec,
exact artifact identity, pinned membership, no committed result, and a durable exclusive git-tag lock created after identities and gates
pass and **before** the first outcome is read; any existing lock for the study refuses. Not dispatched in this change.

## 9. Outcome-free readiness decision

`python scripts/run_kr_industry_anatomy_v1.py --mode readiness` decides between `READY_FOR_INDUSTRY_ANATOMY_EXECUTION` and
`DATA_BLOCKED_BEFORE_INDUSTRY_ANATOMY` from structure only: frozen spec and import closure, membership / taxonomy / benchmark pins,
the raw artifact pin with its archive digest, price inputs pinned by the replay manifest, market caps pinned by the KRX cache digest,
PIT accounting pinned by content digest, a synthetic determinism self-check, zero outcome-access counters and the presence of the
synthetic tests. It never reads a price, cap, return or outcome. Result: `docs/results/kr-industry-opportunity-anatomy-v1-readiness.json`.

What the decision does not say: the real-data path (`prepare`, the label-free gates, `forward_table`) is exercised on synthetic data only;
the first real run may still fail a label-free gate, which writes `gates-failed.json` and spends nothing. The preserved raw artifact was
observed unexpired through GitHub Actions metadata (expires 2026-12-30) and the execution must occur before then. The 22 terminal
securities and the reconstruction's no-change inference remain stated limitations, not repaired ones.
