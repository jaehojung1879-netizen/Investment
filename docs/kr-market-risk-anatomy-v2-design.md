# kr-market-risk-anatomy-v2 — corrected source-admissibility preregistration (outcome-free)

Scientific label: `EXPLORATORY_DEVELOPMENT_ON_OUTCOME_EXPOSED_KR_HISTORY`. The broad historical Korean market is already familiar, so
preregistration here is **not** prospective confirmation.

## What v2 is, and is not

`kr-market-risk-anatomy-v1` (PR #196) is a **permanently valid blocked study**: `DATA_BLOCKED_BEFORE_MARKET_RISK_ANATOMY`, blocker
`PRIMARY_REFERENCE_NOT_SELECTED`. v2 does not unblock it in place and does not edit, reinterpret or re-run it. v2 is a new study identity that
repairs only the **source-admissibility rules** that stopped v1. It is not a new macro model and it adds no feature.

Unchanged from v1 and imported (never re-declared): the feature registry and orientations, the slow / transition / fast / internals structure,
past-only expanding percentiles, exact future-path targets, underwater-episode algorithm, the SMA200 / Vol63 overlay comparison, the time-series
statistics, every v1 coverage / continuity / identity threshold, and the exclusion of revised-history series (ECOS, FRED NFCI/ANFCI, OECD) from
`PIT_EXACT` use. The v1 module files are byte-pinned by v2's import closure.

## The two source-QA defects (neither is an investment result)

1. **Live freshness was used as historical admissibility.** v1 rejected `FDR_KS200` only because its last date (2026-09-17) was 17 days before the
   acquisition day against a 10-day limit. A historical anatomy over a fixed window needs identity, calendar coverage and continuity over that window;
   it does not need a series that is current today. v2 separates the two concepts. Live operational freshness is recorded as an informational field and
   is **never** a gate; the v2 result is never described as live-ready or production-ready.
2. **The invalid-row gate divided by raw vendor rows.** Weekends, exchange holidays, vendor placeholders and duplicated calendar rows were in the
   denominator (and, when unparseable, the numerator). v2 measures quality against **expected XKRX trading sessions** in the frozen window.

This is methodological versioning from source metadata and source-quality observations. No historical market outcome was read to write it. It is
*not* blind to source metadata: v1's committed readiness record showed these diagnostics, and that is the disclosed reason v2 exists.

## Frozen v2 rules

- **Historical reference admissibility** = identity + documented-blocker + duplicate-date + first-date (<= 2005-12-31) + 2007-2009 and 2019H2-2020
  session coverage (>= 0.99) + full-range session coverage from 2006-01-01 (>= 0.98) + longest missing run (<= 5 sessions) + session-based bad-share
  limit. **No wall-clock freshness test.**
- **Session-based quality.** Denominator: expected XKRX sessions in [2006-01-01, analysis end]. A *bad session* is an expected session with no valid
  (finite, positive) row; it is split into MISSING (no vendor row) and INVALID (vendor rows exist, none valid). Limit 0.005 (the v1 number; only its
  denominator changes). Rows on weekends, holidays and placeholder dates, and surplus duplicate raw rows, are reported separately and count neither
  for nor against a source. A genuine expected-session hole counts and fails closed. A duplicate date in the *used* (valid) series fails closed.
- **Priority (outcome-blind).** (1) official `KRX_OPENAPI_KOSPI200` if retained and sufficient (documented blocker: service history starts 2010-01-04
  and the portal answered LOGOUT/400); (2) retained `FDR_KS200` if it passes; (3) `YAHOO_KS200` (evaluated; retained one row); (4) the KOSPI
  composite `YAHOO_KS11` only if no KOSPI 200 route passes, as a distinct fallback instrument. One vendor route supplies the whole series. **No splice**
  of KOSPI 200 with the composite, of FDR with Yahoo, no interpolation, no forward fill, no reconstruction, no outcome-dependent deletion.
- **Analysis end.** The latest valid date of the selected reference that is an expected, completed XKRX session. Sessions after the retained source ends
  are neither synthesized nor counted missing, and a reference is not rejected for ending before the wall clock. The coverage windows still force the
  source to span 2019H2-2020, so a source that simply stopped early cannot pass.
- **Reuse.** The exact immutable bytes retained by v1 are the only source input; nothing is re-acquired. No DART / KIND contact.

## Lifecycle (built, not dispatched)

committed authorization (workflow_dispatch on merged main, committed exact spec) -> frozen spec -> immutable source identities (v2 spec pins, v1
sealed artifacts, v1 retained bytes) -> label-free / data-quality gates -> no prior result -> no prior marker -> no existing lock under the study's tag
prefix -> **durable exclusive lock** (atomic `POST /git/refs`, tags `kr-market-risk-anatomy-v2-execution-lock` and `...-<specSha256>`) -> marker ->
**first** source-value read and outcome computation. A failure before the lock spends nothing; once the lock exists the study is never silently rerun.

## Boundary

No historical market-risk outcome is computed in this change. No drawdown, trigger performance, false alarm, recovery cost or anatomy result is
inspected. v2 produces no recommendation, no best feature or trigger, and no promotion. Execution is a separate, later, explicitly authorized step.
