# Phase 2: actual #354 source intersection and disclosure-clock risk (2026-11-25 KST)

Scope: source-only audit. No prices, outcomes, return labels, strategy changes, or historical reruns. All frozen #354/#375 prior files are unchanged. #376 integration, #372 guidance and #377 raw DART remain independently owned.

## Actual preserved catalog

At #354 head a45f12760a3d27ad09fcfdfb1266308ae59b9e1d, input research/kr_us_earnings_expectations_v1/inputs/us-8k-item202.csv.gz, Git blob e755d3529b39c0b5dfce5e98932e9225dd978a45. Retrieved base64 bytes via connector; decoded gzip and scanned all 57,892 lines of data, checked inflated length 5,584,722 bytes against gzip trailer. No private financials or outcome files were read.

- 57,892 rows, 56,255 unique (CIK, accession), 757 distinct CIKs; 1,637 repeated keys, zero conflicting metadata and zero rows outside 8-K/8-K/A with exact Item 2.02.
- Exact Item 4.02 intersection: 79 raw rows, 78 unique (CIK, accession), 66 issuers. 78 raw 8-K and 1 raw 8-K/A. 21 unique intersection records from 2014 onward.
- Unique counts by year: 2004:5, 2005:20, 2006:15, 2007:5, 2008:3, 2009:2, 2010:3, 2011:1, 2012:2, 2013:1, 2015:3, 2016:2, 2017:2, 2018:2, 2019:2, 2020:2, 2021:3, 2022:2, 2023:2, 2025:1.
- Not a full 4.02 universe or 78 independent events. No contemporaneous PIT security mapping is claimed; the item-filtered #354 source misses standalone 4.02 filings.

## Concrete semantic counterexample to Item 2.02 = quarter release

ADT's frozen catalog contains exactly these two July 1–August 8, 2023 records for CIK 1703056:
- July 10, 20:42:16Z, accession 0001703056-23-000140 (2.02,4.02,7.01): [body](https://www.sec.gov/Archives/edgar/data/1703056/000170305623000140/adt-20230703.htm). Item 2.02 refers to prior-period restatement and possible further goodwill impairment/control disclosures for Q2. Not the normal full Q2 earnings announcement.
- August 8, 11:02:41Z, accession 0001703056-23-000155: [body](https://www.sec.gov/Archives/edgar/data/1703056/000170305623000155/adt-20230808.htm), [earnings release](https://www.sec.gov/Archives/edgar/data/1703056/000170305623000155/adtq22023earningsrelease-e.htm), confirms release of actual Q2 results. Q2 periodic filing is August 8, accession 0001703056-23-000157.
- The #354 events.attach_us_announcements function takes earliest 2.02 within period-end through periodic filing day. For an ADT June 30–August 8 window, it would select July 10 rather than August 8 (29 calendar days earlier). This establishes a semantic counterexample to the rule, not proof that the corresponding private event was admitted or affected a result. Do not blanket-exclude all 4.02 combinations: AXON 2025-05-07, SMCI 2018-11-15 (preliminary results), MAT 2019-10-29 do carry actual current-period earnings information along with restatement material. Require actual period and release-type evidence, not item codes alone.

## Acceptance timestamp risk

The external curated SEC submissions release reports mixed UTC/Eastern clock values with a Z suffix, see https://iangow.github.io/sec_submissions/timestamps/ and https://iangow.github.io/sec_submissions/data/. #354 parses its 2026-11-21 snapshot as UTC throughout. This risk is conditional, not a finding of a corrupted #354 timestamp.

Actual nonrandom spot sample: first four and last three rows of catalog, plus four dual-item records AXON/SMCI/ADT/MAT. Index acceptance clocks are manually transcribed in index_sample.csv (not retained HTML bytes). 8 accessible SEC index pages agree with original UTC after Eastern conversion; 3 could not be retrieved. No error observed in 8; not an error-rate estimate. Effective calendar day in code is the existing 16:00 convention, not an executable exchange session (early-close issue is separate).

Full source option: GitHub public release iangow/sec_submissions_data tag 2026-09-30, filings.parquet 1,235,685,023 bytes, SHA256 f2e3c041cb8eb2cb4b251e11eae25f61b5e18fab0bef34544b912611c0fd219e. Release metadata retrieved directly. Publisher reports 27,272,863 rows, 25,584,390 supported, 1,688,473 unresolved. CC BY 4.0 for curated output, not underlying documents. Independently check provenance, retain unresolved separately, and do not assume Sept 30 snapshot covers Nov 21 source or first public dissemination. Binary release not downloaded (local DNS unavailable; connector can read repository blob base64 but not the large release asset). #354 previous run successfully obtained issuer submissions histories, whereas earlier SEC Actions probes were denied; use an authorized networked environment and respect SEC declared user-agent / pacing. No new workflow.

## Reproduce

In a full local checkout containing the #354 Git object:
```sh
git show a45f12760a3d27ad09fcfdfb1266308ae59b9e1d:research/kr_us_earnings_expectations_v1/inputs/us-8k-item202.csv.gz > /tmp/us-8k-item202.csv.gz
python -m research.us_nonreliance_source_pilot_v1.catalog_audit /tmp/us-8k-item202.csv.gz
python -m pytest -q tests/test_us_nonreliance_catalog_audit.py
```
Five isolated local tests passed (test import adapted to repo namespace); exact repo CI pending. Full catalog counts were obtained from the actual connector bytes, independently of the Python CLI, which has not been run on the full blob in this local container. No reexecution of #354 returns. Next: complete 4.02 metadata via date-bounded SEC issuer submissions or pinned curated release, map actual source periods and prior notices, and measure exact private event joins only with explicit owner scope; do not amend sealed results.
