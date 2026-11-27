# N1–N3 second batch · market forecasts and semantic mechanism extraction

2026-11-28. EXPLORATORY / AUTHOR_VALIDATION_ONLY. No new outcome test or prospective registration.

## First finding: exact same-date stock-price expectation revisions

Livingston Survey (Philadelphia Fed) covers professional economists, not a
representative investor population. Published medians, variable-specific
respondent counts. Select four consecutive June/December reports from Dec 2024
to June 2026; the last HTML summary lacks stock table, preserved as missing.
June 2025 PDF page 1 and 6 checked visually; Dec 2024 and Dec 2025 text extracted
but screenshot unavailable. No raw bytes or source hash claimed.

| Release | S&P500 end-Dec 2025 | S&P500 end-Dec 2026 | 2026 CPI annual avg | Stock N |
|---|---:|---:|---:|---:|
| 2024-12-20 | 6489.9 | 6920.9 | 2.3 | 15 |
| 2025-06-24 | 5801.7 | 6210.3 | 3.0 | 13 |
| 2025-12-19 | 6830.0 | 6990.0 | 2.8 | 14 |
| 2026-06-24 | past | unavailable | unavailable | unavailable |

End-2026 target revision -710.6 then +779.7 index points, about -10.27% and +12.55%.
GDP H2 2025 annualized 1.9→0.9→2.0; unemployment Dec 2025 4.3→4.6→4.5%;
2026 CPI 2.3→3.0→2.8%. One coherent swing of *published expectations*, not proof
of what caused their revision. Survey submission dates precede public release,
and medians for different metrics may have different respondents. No within-person
or causal inference. Stock forecasts are price index targets, not total returns
or actual investment positions. No market outcome queried for this batch.

## Second finding: AI can preserve meaning beyond the numbers

FOMC June 2025 minutes (public July 9): a few participants regarded tariffs as
a one-time price-level effect; most noted persistence risk. December 2025
minutes (public Dec 30): many expected tariff effects on goods inflation to
wane, with some uncertainty about timing/pass-through. These statements
are competing/conditional mechanisms, not comparable binary votes or
individual revisions. The same person could believe both.
October 2026 minutes (public Nov 18): Fed staff highlighted conditional AI
debt/lease/circular-financing amplification and forced deleveraging/redemption
in severe scenarios. Staff scenario is not committee consensus or crash forecast.
Separate source, speaker, scope, modality, mechanism, potential empirical test
and alternative. Dates refer to public release, never meeting time.

Seven claim cards, two contrasts, two candidate test cards. Source excerpts
manually extracted in chat; no independent annotation or recall denominator.
We do not claim semantic predictive skill. Next evaluation must compare
numeric-only inputs against numeric + text, including negative/uncertain claims,
with independent human labels and unknown future resolutions. Do not treat
absence of a theme in selected extracts as absence of concern.

## Source-access and scaling

- SPF microdata official workbook link: web XLSX unsupported, direct container
  download failed. Individual ID caveats (early reuse, firm vs person) verified
  in official documentation text; screenshot failed. No participant panel.
- Livingston historical median/mean/individual/dispersion catalog accessible,
  no workbook acquisition; discontinued 1952–90 stock index not maintained.
- Yale confidence index now raw monthly rather than 6-month average; permission
  required for redistribution. No raw data stored.
- AAII historical page 403; methodology verified. Voluntary weekly member
  survey, not probability that stock market rises.
- GDELT not attempted in this batch. Prefer metadata and original source links
  instead of bulk storing restricted content.

## Prospective process (DESIGN ONLY)

A fixed release census is cheaper and more interpretable than an open news
crawl: Livingston semiannual, SPF quarterly, FOMC minutes on release, BOK
quarterly outlook, permitted investor surveys weekly/monthly. Build official
calendar and log all missing/blocked releases; preserve corrections with new
receipt rather than overwriting. Start manual chat analysis per release; no
paid API or unattended LLM introduced. Require source byte identity and access
rights before automated import; index/HTML snippets remain weak evidence.

Every forecast should specify actor/model version, as-of time, evidence IDs,
one measurable target and unit, precise horizon, baseline prediction, point or
probability prediction (not made-up confidence), resolution source/vintage,
failure/missing policy and immutable receipt. Evaluation: baseline error and
AI error on same target; Brier/log scores only for genuine probabilities.
Evidence review by nonauthor, no historical LLM performance claimed.
Economic forecasts are not trading signals. S1–S5 cross-over only after
independent data admission and owner approval; S2 forced-sales overlap explicitly
tagged. No actual AI forecast registration in this PR; no deployment.

Run: python -m research.narrative_intelligence.mechanisms
Tests: python -m pytest -q tests/test_narrative_mechanisms.py
