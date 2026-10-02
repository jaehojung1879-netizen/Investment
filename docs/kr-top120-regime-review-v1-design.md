# kr-top120-regime-review-v1 — design and protocol (exploratory post-outcome regime diagnostic)

> **EXPLORATORY PROTOCOL ONLY — NO NEW HISTORICAL REGIME-REVIEW OUTCOME COMPUTED.**
> `scientificStatus: EXPLORATORY_POST_OUTCOME_REGIME_DIAGNOSTIC`.
> This document, the frozen spec (`research_specs/kr-top120-regime-review-v1.json`), the harness and the workflow were
> written and tested on synthetic data only.

## 1. What this study is, and what it cannot be

It is designed **after** the `kr-factor-anatomy-v1` outcomes were seen. The only legitimate question is whether those
already-known relationships are concentrated in particular outcome periods, signal-time market states or mega-cap names.

It **cannot** confirm a factor, validate a strategy, rescue `kr-model-overlay-portfolio-v1`, produce production weights,
choose a best factor, tune a threshold from a favourable slice or claim independent replication. Known predecessor
observations (book-to-market H126 positive, `relative126` large positive D10-D1, `logAdv60` weak within strata, weak quality,
extreme 2025-26 winners, Samsung Electronics / SK Hynix prominence) are **not** confirmatory evidence here.

## 2. Predecessor and inputs

The sealed predecessor is pinned by hash (result, report, manifest, provenance, archive digest, spec SHA, raw input identity)
and re-verified on every load. The exact frozen raw lineage is reused; there is no recollection and no Top300 broadening. The
universe is `PIT_TOP120_LARGE_CAP_ANALYSIS_UNIVERSE`, the 11 anatomy factors in frozen order, H126 / H252, the anatomy return
basis `BENCHMARK_RELATIVE_ADJUSTED_INDEX_RETURN_PARTIAL_DISTRIBUTIONS` (not total shareholder return) and the v1 terminal
discipline. Anatomy helpers are reused, not copied; the sealed anatomy files are never edited or rerun.

Same-date D10-D1 is a cross-sectional stock-return spread because the benchmark cancels; benchmark-relative levels, the
beat-benchmark fraction and KODEX200-relative fundamentals success remain benchmark dependent.

## 3. Questions (frozen)

Q1 recent-regime window removal for book-to-market and price strength; Q2 Samsung / Hynix / dynamic-top-2 dependence of
momentum and liquidity; Q3 extreme winners versus median and rank-correlation views; Q4 improving fundamentals: negative
absolute return or merely lagging KODEX200; Q5 signal-time trend / volatility states.

## 4. Chronology — by outcome window

Slices are decided by each observation's `entryDate` / `exitDate`, never by signal year alone (a late-2024 signal maturing in
2025 is a 2025 observation). A slice removes outcomes only; same-date ranks are unchanged. Registered slices:
`FULL_SAMPLE`; `PRE_2025_COMPLETE_WINDOW` (exit < 2025-01-01); `TOUCHES_2025_OR_LATER` (exit >= 2025-01-01);
`PRE_2026_COMPLETE_WINDOW` (exit < 2026-01-01); `TOUCHES_2026` (entry <= 2026-09-14 and exit >= 2026-01-01);
`EXCLUDE_WINDOWS_TOUCHING_2025`, `_2026`, `_2025_OR_2026` (closed-interval intersection with the calendar year).
Signal-year tables are context only. A slice with too few dates is `DATA_INSUFFICIENT`; no breakpoint is added afterwards.

## 5. Signal-time market states

Read from `pipeline.kr_market_risk_overlay.state_at()` on the signal date (past-only): `trendAdverse` (close < SMA200),
`volAdverse` (63-session annualised vol > 25%), `riskMultiplier` 1.0 / 0.7 / 0.4. Tables: TREND_OK / TREND_BAD, VOL_OK /
VOL_HIGH, the four joint cells and the three risk multipliers. No outcome-defined regime, no best regime.

## 6. Mega-cap / semiconductor concentration

Exactly five universes: `FULL_TOP120`, `EXCLUDE_SAMSUNG_ELECTRONICS` (005930.KS), `EXCLUDE_SK_HYNIX` (000660.KS),
`EXCLUDE_BOTH`, `EXCLUDE_DYNAMIC_TOP2_MARKET_CAP` (two largest signal-date market caps, ties by ticker). Names are removed
**before** ranking and same-date ranks and deciles are recomputed in the reduced cross-section. No third company can enter.
Per-date Samsung / Hynix / combined / largest / top-2 shares are context only.

## 7. Robust-outlier views and the three returns

Per factor, horizon and view: equal-date mean D10-D1, equal-date mean of (D10 median − D1 median) stock return, mean
within-date Spearman, year-by-year D10-D1 and leave-best-year-out. No winsorisation or trimming; the three headline views are
separate outputs. Outcomes: `ABSOLUTE_STOCK_RETURN`, `KODEX200_RELATIVE_RETURN` and the **new, post-outcome exploratory**
`TOP120_LEAVE_ONE_OUT_EQUAL_WEIGHT_RELATIVE_RETURN` (stock minus the mean of all OTHER valid PIT Top120 names on that
date / horizon / terminal treatment; subject excluded; at least 50 other valid names else the observation is
`DATA_INSUFFICIENT`; a missing peer is never a zero).

## 8. Fundamentals improved

`ocfImprovementToAssets > 0` and `netIncomeImprovementToAssets > 0`. Three separate rates: `ABSOLUTE_UP`, `BEATS_KODEX200`,
`BEATS_TOP120_EQUAL_WEIGHT`, each over its own valid population, date-equal, never collapsed. This separates "improved but fell"
from "improved and rose but lagged a semiconductor-heavy index". Korean Value-up is neither an exclusion regime nor a factor.

## 9. Descriptive labels (deterministic, sign-based, first match wins)

`DATA_INSUFFICIENT` → `NO_CLEAR_PATTERN` (zero direction) → `OUTLIER_SENSITIVE` (mean sign not supported by median spread nor
Spearman) → `MEGA_CAP_SENSITIVE` (EX_BOTH or EX_DYNAMIC_TOP2 changes sign or falls below 0.5 of the full magnitude) →
`RECENT_REGIME_CONCENTRATED` / `PRE_RECENT_ONLY` (pre-recent views versus `TOUCHES_2025_OR_LATER`) → `REGIME_DEPENDENT` (opposite
trend or volatility states) → `PERSISTENT_ACROSS_PRE_RECENT_AND_RECENT` → `NO_CLEAR_PATTERN`. Constants are reused from the
anatomy (104 dates, 0.5) or frozen simply now (26 dates per slice, the anatomy's H126 block length). No "validated",
"proven", "pass", "fail", "best" or "production-ready" label exists.

## 10. Lifecycle (decided now) — a durable lock, not an artifact

Protocol PR merges → a human dispatches `execute` once → identities and readiness gates pass → **a durable, exclusive lock is
created on GitHub** → only then may any outcome be read → result artifact → seal commits the exact bytes without rerunning →
later attempts fail closed.

**The lock** is the git tag `refs/tags/kr-top120-regime-review-v1-execution-lock-<specSha256>`, created from Actions by an
atomic `POST /git/refs` pointing at the dispatched main commit (verified by a `GET` afterwards). It is the repository's
already-proven mechanism from `kr-model-overlay-portfolio-v1`. An existing ref answers 422 and execution refuses; only POST and
GET are ever issued, so the tag is never updated, moved, deleted or recreated. `attach_outcomes` refuses without the lock
object, so no outcome can be read before it exists. An unverifiable lock state (no token, any non-200/404 answer) refuses.

* A failure **before** the lock (identity, predecessor, input identity, any readiness gate) writes `gates-failed.json`, creates
  no lock and spends nothing.
* A failure **after** the lock permanently consumes v1, whether or not any artifact was emitted, kept, expired or deleted. A
  retry would be a new, separately preregistered version.
* Actions artifacts and their retention, local files, a later-committed result and the committed `execution-started.json`
  are **not** the enforcement; the last is provenance only. The workflow's results-artifact check is an additional convenience.

Workflow permissions: `contents: write` on the `execute` job only, solely to create the lock ref; the verify job and PRs stay
read-only. A verdict, including `DATA_INSUFFICIENT`, is a successful process. Authorization and lock tests build their own
synthetic repositories and a fake GitHub API, so none depends on the real repository's state.

## 11. Outputs

Regime executive map, mega-cap sensitivity table, market-regime table, fundamentals-improved table, concentration context,
JSON + CSV and a Markdown report that states the limitation and carries no promotional interpretation.
