# Phase 3 — metadata acquisition handoff and metric-specific evidence

2026-11-25 KST. No historical outcomes, pricing, or production changes. No other PR files edited; #376 integration and #377/#379 DART fixes remain separately owned.

## Source evidence and concrete distinctions

Manually reviewed five SEC bodies; these are known dual-item cases from the #354 catalog, purposive examples, not a frequency estimate.

| CIK / accession | Item 2.02 semantic content | Specific measurement consequence |
|---|---|---|
| [LNC 59558 / 0001193125-23-080586](https://www.sec.gov/Archives/edgar/data/59558/000119312523080586/d421416d8k.htm) | Preliminary estimates of prior-period reinsurance restatement, not a normal current-quarter release | Preliminary FY21 net income 1,405→1,897 USD million (+492); FY22 loss −2,227→−2,252 (−25); FY22 equity 4,101→4,568 (+467). Issuer says distributable earnings and free cash flow unaffected. |
| [SWK 93556 / 0001193125-22-018393](https://www.sec.gov/Archives/edgar/data/93556/000119312522018393/d303104d8k.htm) | Item 2.02 incorporates 4.02; correction of prior periods | FY2020 diluted GAAP EPS reduced 0.31 to 7.46 (previous 7.77); historical net earnings unchanged. |
| [ANF 1018840 / 0001018840-21-000014](https://www.sec.gov/Archives/edgar/data/1018840/000101884021000014/anf-20210301.htm) | March 2 release for Q4/FY ended Jan 30, filed March 3; not first dissemination time | 50 million USD moved from operating to investing cash flow, prior FCF affected, statements of operations/balance sheets unaffected. No separate 10-Q/A planned: later annual filing contains corrections. |
| [XRAY 818479 / 0001140361-22-039283](https://www.sec.gov/Archives/edgar/data/818479/000114036122039283/brhc10043485_8k.htm) | Investigation completion plus preliminary Q3 2022 results, potentially changing | Prior Q3 2021 and FY2021 misstatements, customer incentives/revenue and reserves. Current impairment estimate is distinct from prior restatement. |
| [AXON 1069183 / 0001069183-25-000074](https://www.sec.gov/Archives/edgar/data/1069183/000106918325000074/axon-20250501.htm) | Actual Q1 2025 results plus prior-period balance-sheet classification | 690 million USD principal convertible notes; classification current vs long-term; not a 690 million P&L loss, and issuer says total liabilities, assets, equity, statements of operations and cash flows unchanged. |

A Form 8-K 4.02 event is not a universal financial-factor error. Separate exact metric dependencies, scope, release type, original availability and correction availability. Never remove a historically visible observation retroactively. Never infer no error simply from no 4.02 or no amended 10-Q. Cross-filer example: [Lincoln National Life](https://www.sec.gov/Archives/edgar/data/726865/000119312523080609/d463711d8k.htm) disclosed related reinsurance issue separately from parent LNC; do not map subsidiary CIK to parent by name or count as a separate economic event without analysis.

## Implemented offline extractor

SEC official documentation: https://www.sec.gov/search-filings/edgar-application-programming-interfaces ; public bulk https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip. Reuse frozen #354 catalog Git blob for 757 distinct issuer CIKs; this is a catalog-derived cohort, not a complete historical S&P 500 universe. No ticker alias multiplication. Read each issuer's recent block and every declared overlapping historical page (8-K and 8-K/A, exact 4.02, including those without 2.02); keep unknown item codes/missing pages explicit and preserve raw acceptance clocks as unverified. Archive hash and each read JSON page hash are output. Complete declared pages scanned is not proof of complete SEC history or first dissemination. Dates filter filingDate, not economic event date. No new network workflow.

Run in authorized networked environment with a full repository checkout containing #354 objects:
```sh
git show a45f12760a3d27ad09fcfdfb1266308ae59b9e1d:research/kr_us_earnings_expectations_v1/inputs/us-8k-item202.csv.gz > /tmp/us-8k-item202.csv.gz
# Acquire SEC submissions.zip using a compliant declared user agent; preserve archive and retrieval metadata outside public git.
python -m research.us_nonreliance_source_pilot_v1.bulk_402 /tmp/us-8k-item202.csv.gz /path/to/submissions.zip --through 2026-11-21 > /tmp/402-cohort-metadata.json
python -m pytest -q tests/test_us_nonreliance_bulk_402.py
```

Local exact module tested on six isolated synthetic ZIP cases (test import adjusted for local standalone execution); no real SEC archive run, cohort counts beyond prior 78 intersection NOT MEASURED. Local DNS checks for github.com/data.sec.gov/www.sec.gov failed; prior #354 successful submissions collection and existing SEC Actions probes already inspected; this does not imply global SEC source block. Web access served cited body examples but API JSON inaccessible. The independent curated Sept 30 release in phase 2 remains an alternative for clock audit; neither binary downloaded. To avoid repeating source scaffolds, stop further code until a networked execution supplies actual metadata counts, missing pages, raw archive hash, and 4.02-only overlap. Then collect original bodies and link affected metric-period-accession before measuring actual contamination. No new historical outcome run or merge approved.
