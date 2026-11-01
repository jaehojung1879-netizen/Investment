# M3 backlog → shipments v1: REJECTED (exploratory)

Owner-authorized one-shot business-outcome evaluation. Contract/parser/statistical settings were committed as `0ef5636b` BEFORE future source values were parsed. No stock returns, investment recommendation, sealed-study replay, or live change. Original source-feasibility packet SHA256: `22b2df36c1a06900c8e35e933c761fbf47465aa068661260f2391e4a5cefed22`.

## Fixed comparison and source admission

Six fixed M3 publication groups; 68 quarter-calendar cutoffs in 2009–2025. Forecast next three COMPLETE calendar months, with latest originally published FULL M3 available at the cutoff. Target is mean of three as-first-full-reported within-vintage monthly SA shipment log changes (nominal dollars, not physical output). Persistence baseline is the last three known first-full shipment changes. Candidate adds one common expanding past-only OLS coefficient times same-vintage backlog log change, with no intercept/tuning/clipping and at least 60 completely published past monthly training origins. Baseline has no fitted parameters. All six industries enter the common mask.

283 original hashes pinned, no raw PDFs committed. Numeric parsing passed all 273 post-Jul-2003 published releases: **0 failed cells/rows**. Nine pre-Jul-2003 references and the Aug-2013 shutdown nonrelease retain their original source exclusions. A real legacy parser defect (single space after row leaders) was fixed before outcomes; 24 original known-prefix SA cells were manually checked against the Nov-2008 report, released Jan 6 2009. Current/prior same-vintage values, million-dollar units, and SA columns are tested.

Evaluated **66/68 blocks, 396 paired industry-cutoff rows**; time units are 66, never 396 independent observations. Excluded: Jan-2009 only 58 completed past training origins; Jul-2013 lacks Aug-2013 first-full target. Model training at the first evaluated Apr-2009 cutoff has 60 actually numeric-complete past origins. Source age is preserved, including delayed government-shutdown releases.

## Actual results

MAE/RMSE below are **percentage points of mean monthly log growth** (JSON stores natural-log units). Skill is relative MSE reduction, not an investment return.

| Scope | Baseline MAE | Candidate MAE | Baseline RMSE | Candidate RMSE | Skill |
|---|---:|---:|---:|---:|---:|
| All | 1.017633 | 1.027826 | 2.424120 | 2.433091 | -0.741581% |
| 2009–2017 (34 blocks) | 0.903552 | 0.918799 | 1.353062 | 1.362192 | -1.354198% |
| 2018–2025 (32 blocks) | 1.138845 | 1.143667 | 3.189794 | 3.199738 | -0.624462% |
| primary_metals (descriptive) | 1.250960 | 1.256476 | 1.989412 | 1.985662 | +0.376613% |
| fabricated_metals (descriptive) | 0.564897 | 0.574905 | 0.970750 | 0.974002 | -0.671147% |
| machinery (descriptive) | 0.683880 | 0.706115 | 0.971942 | 0.982747 | -2.235758% |
| computers_electronics (descriptive) | 0.612146 | 0.618106 | 0.867710 | 0.875292 | -1.755245% |
| electrical_equipment (descriptive) | 0.592846 | 0.598238 | 0.834491 | 0.837016 | -0.606008% |
| transportation_equipment (descriptive) | 2.401071 | 2.413119 | 5.288105 | 5.309948 | -0.827821% |

Paired MSE loss difference (baseline − candidate, same rows): **-4.35779552537e-06 log²**. Fixed calendar-quarter circular moving-block bootstrap: block length 4, 9,999 draws, seed 20261101, missing calendar slots preserved and all six industries resampled together. Percentile 95% loss-difference interval: `[-9.826608055647134e-06, -9.614338560166989e-08]`; skill interval **[-2.103096%, -0.048090%]**. These exploratory intervals are conditional on the realized walk-forward forecast path, with about 16 year-length spans, not a distribution-free or prospective confirmation guarantee. No block-length or model selection after outcomes. The interval upper bound is close to zero; do not generalize the rejection to all backlog relationships.

## Dated example

Apr-30-2009 cutoff uses Feb-2009 reference report printed **Apr-2-2009**. Primary metals backlog log change: -0.078948686; beta trained only on already fully published past outcomes: 0.025945320. Baseline prediction **-6.298673 log-pp/month**, candidate **-6.503508**, realized May/Jun/Jul first-full shipment growth mean **0.836068**. Last outcome source published **Sep-2-2009**, unavailable at the decision cutoff. Full source/date/forecast/training counts for every cutoff are in `result.json`.

## Conclusion and one next decision

**Close this fixed M3 hypothesis as REJECTED.** The pooled linear backlog increment failed to improve persistence for these six originally published nominal-shipment series; both chronological halves worsened. One descriptive industry gain does not license selecting a favorable sector. This does not disprove every possible industry-leading economic mechanism. Do not substitute G.17 or run another arm. No observed forecast skill justifies advancing this candidate into Portfolio D.

A future separately authorized equity test would still need dated industry-to-security identity, lawful shareholder total returns including terminal actions, common eligible securities/dates/execution/costs/ETF benchmark and concentration controls for Market+Stock vs Market+Industry+Stock. This run uses none of the invalid survivor-only US return panel.

## Reproduction and safeguards

Use Python with numpy/scipy and system `pdftotext`. Offline tests: `python -m pytest -q tests/test_m3_business_forecast.py`. Read/check the saved result and source hashes for reproduction. The execution CLI is `python -m research.m3_backlog_v1.run --sources <original-pdf-directory> --execute-once`; it **refuses existing results and existing execution locks**. Do not delete the lock or rerun to optimize. New exact-byte recovery or a separately authorized replication requires a separate reviewed action, not a silent retry. All originals are reacquirable via the exact URLs/SHA in `source-manifest.json.gz`; HTTP timestamps do not prove past byte immutability. Census original FULL archives may already revise advance durable-goods prints; no modern revised series was used.

Source use: official Census Public-Use Statement with attribution; no third-party rights implied. Original industry definitions, the 2003 semiconductor reinclusion, and 2010 separate-row cessation remain documented in the preserved feasibility packet. Backlog omits semiconductor demand although the computer shipment parent includes it. Published estimates are nominal, revised and from a voluntary nonprobability survey; predictive intervals are not Census survey-error guarantees.

Result SHA256: `fa213493993f9e10d53b272cd245b6bb106cc64afef8b26c298bca4f747b0d1c`.
