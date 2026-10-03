# KR industry membership foundation v2 — PIT classification state (outcome-free)

Status: **`DATA_FOUNDATION_INSUFFICIENT_V2`** (structural / data-based reasons only).

No historical industry return, factor or Alpha outcome, model, portfolio or sealed prior study was read or run.
No current industry classification was backfilled into history, and no taxonomy or granularity was chosen from
future returns. The object is a *last-known-public issuer classification state*; unknown names stay in every
denominator.

## What was frozen before acquisition (unchanged by this continuation)

`research_specs/kr-industry-membership-foundation-v2/`: `criteria.json` (coverage >= 0.90 per signal date and year,
terminal coverage >= 0.90, minimum group size 5, at least 3 sufficient groups holding >= 0.90 of classified names),
`issuer-year-inventory.json` (254 issuers / 3,302 issuer-years), `acquisition-plan.json`, `public-seed-checkpoint.json`
and `classification-chapters.json` (68 supplemental chapter requests, frozen at `75f5b8b` before any was fetched).
The extraction template (`explicit_labels`) is the one committed with the builder before this run; it was not edited
after reading results.

## Retained evidence

| Object | Count | Provenance |
|---|---:|---|
| v1 retained public DART receipts | 413 | completed run 37096833360 (not redone) |
| v2 annual originals | 2,533 receipts in 26 batches | run 37119776441, frozen per-batch request lists; bytes re-verified by SHA-256 and committed under `data/.../v2/acquired-dart/annual/` |
| classification-chapter supplements | 68 of 68 frozen (HTTP 200, 68 calls, no retry) | run 37163093324; `.../acquired-dart/chapters/` |
| receipts read by the builder | 2,946 | |
| retained terminal documents | 92 | v1 |

Listing: 253 issuers answered `000`, 1 answered `013`; 2,859 original annual receipts were listed; 443 issuer-years
have no listed original annual report; 3,302 issuer-years were planned.

## Result (610 signal dates x 120 = 73,200 name-dates)

* Admitted observations: 79 (53 with a reported code, 26 label-only), 6 securities, 5 distinct literal labels,
  `known_from` 2014-03-31 .. 2026-03-20. 42 annual receipts and 19 chapter supplements produced a label; 2,884
  receipts matched no safe issuer template; 20 had unproven source/identity.
* Classified name-dates 2,876 (3.93%); UNKNOWN 70,324. Signal-date coverage min / median / max 2.50% / 3.33% / 5.00%;
  annual coverage 3.13% (2015) .. 5.00% (2024-2025).
* Conflicted name-dates: 0 (nothing was resolved by choosing between disagreeing sources).
* Groups: sizes 1-2, so **0** dates have even one sufficient group (>= 5 names). Minimum / median group size 1 / 1.
* Terminal securities: 0 of 2,345 terminal name-dates classified.
* Classification age (days since release): min 1, median 212, max 3,084.
* Taxonomy: `standardizedTaxonomyReady = false`. The three KSIC codebook/transition sources fetched in v1 returned 502 gateway
  pages, no edition is verified, and `taxonomy-sources/manifest.json` restates that retained fact. Labels are literal
  issuer labels (`group_id=LITERAL:*`); no KSIC grouping or granularity is claimed or chosen.

Every frozen gate fails (signal coverage, annual coverage, terminal coverage, group sufficiency, standardization).

## Why the supplement did not close the gap

The 68 frozen chapters lifted observations from the short business overviews by 29 admitted rows, still 6 securities.
Of the 16 issuers named as positive in the frozen chapter plan, 10 produce no admitted observation under the frozen
strict issuer-only template. That template is the binding limit, and loosening it after seeing this result would be a
re-specification; any broader rule belongs to a new preregistered version, not this one.

## Reproduction

`python scripts/build_kr_industry_membership_v2.py --output data/kr-industry-membership-foundation-v2/state --verify`
rebuilds the state offline from retained bytes and compares it to `state/observations.json.gz` and `state/audit.json.gz`.
