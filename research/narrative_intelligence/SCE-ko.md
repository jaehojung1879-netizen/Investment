# Fifth batch — monthly household beliefs, not a one-dimensional sentiment score

2026-11-28 · DESCRIPTIVE / AUTHOR_VALIDATION_ONLY. No new trading outcome or registered forecast.

## Original release census

NY Fed Survey of Consumer Expectations, Jan 2025–Oct 2026 (latest publicly
released observation as of this cutoff), all 22 months. Two observed aggregate
means: subjective probability US stock prices rise over 12 months; subjective
probability unemployment rate rises in one year. The sample is a rotating panel
of approximately 1,200–1,300 household heads; not an investor-only survey.
Store survey month separately from the actual dated press release. 44 manually
transcribed numeric facts, source URL and section anchors per row. Official
indexed text or HTML, not raw bytes or precise historical clock certification.
Workbook URL confirmed on NY Fed site; web XLSX response unsupported, direct
container download failed. No invented hash or claim of microdata access.
Methodology: https://www.newyorkfed.org/microeconomics/sce

## Actual result

22 level pairs: Pearson r = -0.06412754. Adjacent monthly changes (21): r =
-0.61481299; both rise 6, both fall 5, stocks rise/unemployment falls 4,
stocks fall/unemployment rises 6. Same direction 11/21 despite negative
change correlation; magnitude matters. No missing/tied changes. These are
descriptive correlations in a selected short window, not tests of causal
direction or market predictability.

| Period | Months | Mean stock-up probability | Mean unemployment-up probability | Level correlation |
|---|---:|---:|---:|---:|
| 2025 Jan-Dec | 12 | 37.575% | 40.50% | -0.59645 |
| 2026 Jan-Oct | 10 | 39.31% | 43.05% | +0.18046 |

Both period means increased. This is not a demonstrated regime break: unequal
short periods, overlapping expectations, serial dependence, sampling
composition and release-rounding. The same-direction aggregate means do not
identify the joint belief distribution of an individual. Do not infer
perceived probabilities of joint events from two marginal means. No
significance tests or alpha estimates. Current Oct reading stock 40.0%,
unemployment 45.3%; not an estimate of actual risk, expected return or
investment recommendation.

## Decision for the next research gate

KEEP multidimensional belief measurement and release census; STOP treating
one positive/negative score as sufficient or the 22-month panel as a trading
training set. SOURCE_BLOCKED original workbook/microdata and release-time PIT.
Exact full SCE chart data path and public microdata catalog are documented.
SCE started in 2013: roughly 13 calendar-year blocks at most for 12-month
non-overlapping targets, not the number of monthly respondents. Longer monthly
history alone cannot remove the horizon overlap. Within-person associations
require weights, panel IDs, entry/exit, missingness and contemporaneous
questionnaire definitions, not aggregate means.

Next economically useful gate: acquire original SCE workbook and questionnaire
in permitted runner, fix release clocks and rights, verify against this 22-row
sample, count actual independent blocks; then compare beliefs to **already
observed** trailing market moves and macro releases in a predeclared design.
A test against subsequent investment returns is a separate preregistered
experiment, with authorized exact price/total-return source and overlapping
horizon inference; do not use FRED SP500 full price series for redistribution
without permission. Survey probability, index-level forecast, implied
risk-neutral probability, and investment total return are different objects.
No existing study replay, no new forecast registration, production NONE.
Recompute: python -m research.narrative_intelligence.sce_diagnostics
