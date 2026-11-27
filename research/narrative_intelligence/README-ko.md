# Narrative Intelligence — Belief & Reality research pilot v1

**EXPLORATORY / AUTHOR_VALIDATION_ONLY.** Separate research axis, not S6 or a new trading signal.
The owner wants to reconstruct what people believed at the time, then evaluate
how beliefs, economic reality and market prices changed. This first pilot
establishes comparable forecast revisions and source-grounded mechanisms.
Existing S1–S5, protected issuer corpora, and sealed outcome tests untouched.

## Scope and evidence

For a small contiguous sample select calendar years 2022–24, IMF WEO January
and July updates for the same US annual-average real GDP growth target. This is
an author-chosen recent window (not randomized, not outcome-blind, not a
claim about all eras). Match the next January BEA first annual estimate.
No post-January revisions used to change historical actuals. Sources are
indexed official text/table extracts manually transcribed in chat; no raw
file bytes or cryptographic source receipts available, exact historical
availability clock not certified. IMF 2023 January publication date is the
Singapore calendar date. Some eLibrary pages returned 403 on full open,
BOK November full open failed, and SPF PDF screenshot failed; indexed
primary excerpts are available, but do not claim full document review.
Preserve locator, URL, original publication date, paraphrase and access status.
Historical context may already be known to the LLM.

| Year | Jan forecast | July forecast | First BEA estimate | Jan error (actual−forecast) | July error |
|---|---:|---:|---:|---:|---:|
| 2022 | 4.0 | 2.3 | 2.1 | −1.9 | −0.2 |
| 2023 | 1.4 | 1.8 | 2.5 | +1.1 | +0.7 |
| 2024 | 2.1 | 2.6 | 2.8 | +0.7 | +0.2 |

Jan MAE 1.2333 pp; July MAE .3667 pp. Three annual blocks only, overlapping
institution and changing forecast lead; midyear forecast includes observed
economic activity. Not evidence of incremental model skill or profitable timing.
2024 revision from Jan to July +.5 pp coexists with April to July −.1 pp.
Do not conflate revision since January with the immediate latest revision.
Market context: S&P DJI reported calendar-year TR −18.11%, +26.29%, +25.02%
for these three years. Context only, not return following forecast timestamps;
no return-join, trading rule, statistical test or causation claim.

## Current belief snapshot (2026-11-27 KST)

Philadelphia Fed SPF Q4 (Nov 16, 32 forecasters): 2027 annual GDP median
2.2→2.3%, monthly payroll gains (annual-average level change) 75.4→62.8k.
2027 Q2 quarterly GDP annualized 2.1→2.2%, payroll 80.4→49.3k/month.
2026 Q4 CPI annualized 2.5→4.0%. Q1 2027 negative quarterly real GDP
mean probability 17.4% (not annual recession probability).
Previous values are quoted in the Nov report, not independently recovered
August original; old vintage date and verified available date are distinct.
Aggregate survey change is not necessarily within-person revision or dispersion.

BOK Aug 27→Nov 26: 2027 GDP 2.9→4.1%, CPI 2.3→2.4%. August release names
semiconductor expansion; November governor discusses higher IT weight in
chain-weighted growth. Rate increase 25bp reported at same press conference.
These are institutional forecasts, not private beliefs or traded expectations.
Same actor report + press conference counts as one evidence lineage.

Two competing-explanation cards in pilot.json are hypotheses, not probabilities:
US growth/jobs decoupling (productivity, industry mix, labor weakness, survey
composition), KR growth/inflation (semiconductors and discount rates).
No AI prospective forecast claimed. 2027 annual target resolves beyond
6–12 months from Nov 27; near-horizon GDP/payroll and risk event are candidate
targets, not automatic registrations. Need independently specified outcomes.

## Engineering

```sh
python -m research.narrative_intelligence.ledger
python -m pytest -q tests/test_narrative_intelligence.py
```

Source/claim IDs, actor/metric/target/unit match, vintage and evidence
availability dates, source class, no future source, mechanism provenance,
separate actual resolution, no duplicate comparison, no nonfinite numbers.
No corpus collector, embeddings, AI API or scheduled workflow here.
Production effect NONE. The diagnostics explicitly do not join market outcomes.
Raw source hash is null, not an invented hash of a summary.

## Next bounded gate (design, not authorized activation)

1. N1 source expansion: select monthly/quarterly contiguous historical windows
   and fixed source strata before outcome access: policy, professional survey,
   investor survey, corporate public commentary, press. Admit original
   artifacts/rights and published clocks. GDELT news metadata only, SPF
   individual forecasts (panel composition and missingness), AAII survey,
   BOK consumer/business surveys and permitted original comments. Verify
   duplicate syndication separately from narrative propagation. Include quiet
   periods and dissent. No protected S3 issuer universe.
2. N2 claim schema expansion: event/publication/retrieval time, proposition,
   target/unit/horizon, attribution, direct evidence, quoted source lineage,
   causal assumptions, confidence only if speaker gives it, revisions vs
   retractions, falsifier and resolution source. Human label review and
   source-only extraction baseline; separate text retrieval from AI inference.
3. N3 compare content against numeric-only baseline: blinded independent
   annotators and entity/time evidence checks; assess whether semantic
   mechanism extracts recover genuinely new observations rather than post-hoc
   causal stories. Current LLM historical analysis is contaminated by knowledge
   of future events; not a predictive holdout.
4. N4 prospective record: fixed source census, append-only claim and AI
   forecast receipt with model version, explicit probability (if calibrated),
   timestamp and immutable resolution rule; separate owner approval.
   Start with a few measurable 6–12m or intermediate outcomes; no market
   decision until forecast calibration and economic relevance demonstrated.
5. N5 bridge to Quant: after independent review and approved preregistration,
   compare incremental prediction versus price/financial/macro baseline with
   correct lag, benchmark total return, cost, exposure/risk and sample power.
   Stop if the narrative is only a restatement of published numbers, already
   priced, or unverifiable. No historic sealed tests replayed.

The main question is not whether forecasters are right, but whether the
*change in what they believe and why* contributes information beyond the
already-observable macro/price series. This pilot establishes feasibility only.
