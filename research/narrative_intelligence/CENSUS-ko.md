# Third batch: fixed release census, longer stock forecast path, raw acquisition

2026-11-28 · EXPLORATORY / AUTHOR_VALIDATION_ONLY. No new trading outcome or real AI forecast.

## Fixed 2025 FOMC calendar

All 8 regularly scheduled meetings, no cherry-picked meeting dates; official calendar
https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm. August notation vote
excluded, not a regular meeting. Topic selected after prior pilot, not preregistered.
Manual paraphrases of participant outlook sections, not comprehensive document
annotation. Each item preserves scope, modality and public release date separately
from meeting date. Counts measure documents with selected tags, not people,
population shares, intensity, all mentions, or evidence of absence. Same source
lineage can contain competing mechanisms. No policy causal effect identified.

Jan: anticipated pass-through; March: heterogeneous persistence and cost absorption;
May: pass-through plans and input/supply-chain persistence risks; June: inventory
delay plus one-time/persistent views; July: observed goods inflation, delayed
contracts, margin and supplier adjustments; Sept: muted relative to expectations,
expected effects through end-2026; Oct: further pass-through, possible productivity
offset; Dec: waning expectation with other cost pressure. All eight source pages
were opened/read through web, no original byte receipt. Raw FOMC Jan 2025 HTML
download attempted in container, failed DNS (Errno -3). Do not infer PIT certificate.

## Historical market belief extension

Two official Livingston PDFs added (Dec 15 2023 and Jun 14 2024). June 2024
cover visually confirmed; other screenshots failed; stock table extracted text.
Use calendar month end as period label, not a trading timestamp. Along with
prior three tables, same end-Dec 2025 target reads 5088.2, 5824.6, 6489.9,
5801.7, 6830.0 across five successive reports. Price index forecasts, no realized
return, not matched people; differing horizons and proximity to target. June 2026
stock table remains absent. Not forecast error, not trading signal.

## Counter-evidence from business decision-makers

Atlanta Fed working paper abstract (Mar 24 2026; nearly 6000 executives in four
countries) reports over 80% of firms perceived no AI impact on employment or
productivity in the past three years, alongside anticipated productivity gains.
This is self-report, not measured output and not US-only. It is not directly
comparable to SPF macro survey, but supplies an alternative to immediate AI-driven
growth/jobs decoupling. Source indexed abstract; no full document or raw bytes.

## Code and next gate

python -m research.narrative_intelligence.census
python -m pytest -q tests/test_narrative_census.py
python -m research.narrative_intelligence.census --acquire /tmp/narrative-raw-v1

Fixed URL raw retrieval is bounded (10 requests maximum, timeout 20 seconds each,
stop that host on access refusal/rate limit, no redirects, max 16MiB, external new
directory only). Exact bytes and hashes are transport evidence, not publication
timestamp certification or redistribution permission. No production writer or
automated job introduced. Date-only matched A/B input packets require prior-day
evidence; B adds mechanisms to identical numerical facts. Does not certify PIT or
prevent historical LLM knowledge contamination. Real forecast registration remains
separate; no investment outcomes, no sealed data or prior pilot modifications.
Next: acquire raw sources in permitted runner, independently annotate a contiguous
holdout including other topics and quiet periods, define target and baseline,
then run prospective A/B with identical model version and information clock.
