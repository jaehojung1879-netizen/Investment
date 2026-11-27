# SEC Item 4.02 — source-only non-reliance scope pilot

Status SOURCE_ONLY / purposive examples, not a representative sample or strategy. Independent of #371/#373 ownership and industrial information, #372 guidance, #374 continuity and #370 13F. PR title/body search did not surface prior Item 4.02-specific research; full historical code inventory was not proven exhaustive. No prices, outcomes, returns, candidate recommendations or production mutation.

## Evidence (five manually transcribed SEC filings, three issuers)

- 0001837240-24-000213: [filing](https://www.sec.gov/Archives/edgar/data/1837240/000183724024000213/sym-20241118.htm), [acceptance/index](https://www.sec.gov/Archives/edgar/data/1837240/000183724024000213/0001837240-24-000213-index.htm)
- 0001193125-24-266541: [filing](https://www.sec.gov/Archives/edgar/data/1837240/000119312524266541/d868548d8ka.htm), [acceptance/index](https://www.sec.gov/Archives/edgar/data/1837240/000119312524266541/0001193125-24-266541-index.htm)
- 0001193125-26-039396: [filing](https://www.sec.gov/Archives/edgar/data/940942/000119312526039396/d77454d8k.htm), [acceptance/index](https://www.sec.gov/Archives/edgar/data/940942/000119312526039396/0001193125-26-039396-index.htm)
- 0001193125-26-218141: [filing](https://www.sec.gov/Archives/edgar/data/940942/000119312526218141/d146211d8k.htm), [acceptance/index](https://www.sec.gov/Archives/edgar/data/940942/000119312526218141/0001193125-26-218141-index.htm)
- 0001493152-26-041986: [filing](https://www.sec.gov/Archives/edgar/data/1331421/000149315226041986/form8-k.htm), [acceptance/index](https://www.sec.gov/Archives/edgar/data/1331421/000149315226041986/0001493152-26-041986-index.htm)

SEC [Financial Reporting Manual topic 4](https://www.sec.gov/about/divisions-offices/division-corporation-finance/financial-reporting-manual/frm-topic-4) distinguishes issuer and auditor non-reliance notices. A filing may describe one or both; an amendment can expand a prior disclosure. Acceptance time is from the filing index, expressed in US Eastern time with the applicable offset. It is a conservative observation boundary for this *filing* and not necessarily first public notice or executable trade time.

- Symbotic: November 18, 2024 initially identified Q1–Q3 FY2024 reports; November 27 amendment repeated those three scopes, disclosed another error and extended non-reliance to Q4/full-year preliminary results. Dropping 8-K/A loses information; treating all five scope labels as independent events is wrong.
- Hub Group: February 5, 2026 confirmed Q1–Q3 2025 errors; 2023 and 2024 were only under review. May 12 filing confirms those two annual statements. Do not backdate the confirmation to February or to the May 11 internal conclusion.
- SDR Drone: September 9, 2026 filing explicitly acknowledges the four-business-day deadline was missed following April 27 and May 27 determinations; earlier 10-K and 10-K/A already reported corrections. The 4.02 filing is therefore not proof of the first warning. The 2025 interim scope concerns 2024 comparative information only, not all 2025 quarterly values.

Totals: five filings; three issuers; fifteen unique issuer/scope labels and three repeated labels; two prior-review labels later confirmed. Counts are descriptive, not independent event N. The scope history records newly observed scope, not new errors on already observed scope, resolution, an active exclusion flag or fraud. In particular Symbotic has additional errors inside already-observed periods. No inference that a later restatement itself is adverse or that each period is a separate event.

## Next admission gate

1. Reuse the SEC submissions bulk/issuer history route documented at https://www.sec.gov/search-filings/edgar-application-programming-interfaces and the historical issuer cohort from #354 if available. #354's 57,892 Item 2.02 records are not a complete 4.02 population. Check existing Actions probe evidence before treating network restrictions as permanent.
2. Retrieve 8-K and 8-K/A item metadata and complete versioned originals; verify timestamps and bytes; record missing submissions, issuer-to-security mappings and earlier public notices.
3. Code affected original statement accession, exact line item/period, confirmed vs under review, issuer vs auditor, explicit supersession and resolution. Assess coverage and independent issuer-time clusters before any return experiment. Never replace original historical financial inputs with a later corrected value as if already known.
4. Separate financial-data reliability audit from risk-exclusion hypothesis. No automatic exclusion, trading decision, historical outcome execution, or production integration.

The original HTML bytes were not retained or hashed. Examples were chosen to expose ambiguity, not to estimate frequency. The prototype only compares manually coded scope labels and accepts no automated claims of complete coverage/PIT qualification.

Run: `python -m research.us_nonreliance_source_pilot_v1.scope` and `python -m pytest -q tests/test_us_nonreliance_source_pilot_v1.py`. Five equivalent isolated tests ran locally against the manually coded sample; repo-wide CI and exact-head tests remain pending.
