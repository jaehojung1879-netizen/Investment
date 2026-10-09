# kr-alpha-atlas Phase B — point-in-time feature matrix and data readiness

Phase A (PR #211) designed a bounded Korean-equity alpha investigation: 106 registered features in ten information families, six Level 3 interactions, five Level 2
baselines. Phase B answers one question and nothing else: **is there enough point-in-time data to attempt the registered comparisons?** It computes no relationship to a return.
It reads no label, no forward price and no outcome; it fits no model and values no portfolio. `READY` below is a statement about cells, never about alpha.

## What it produces

| File | What it is |
|---|---|
| `docs/results/kr-alpha-atlas-phase-b-readiness.json` | per registered feature: source, PIT verdict, coverage with its denominator, coverage by year / industry / liquidity tier, usable range, missingness reasons, horizon usability, next action; joint coverage; the six interactions; the five baselines; the input audits |
| `docs/results/kr-alpha-atlas-phase-b-phase-c-manifest.json` | the outcome-blind inputs a Phase C registration may pin: eligible features, controls, context, construction/eligibility features, exclusions with reasons, baselines, interactions, identities, terminal-event risks, benchmark status, prerequisites |
| `docs/results/kr-alpha-atlas-phase-b-source-feasibility.json` | blocked-source register (with the repository's own latest evidence quoted) and the broader-universe feasibility measurement |
| `docs/results/kr-alpha-atlas-phase-b-weekly-dry-run-example.json` | one replay of the weekly process, `NOT_READY` or `BLOCKED` only |
| `docs/kr-alpha-atlas-phase-b-readiness-ko.md` | the Korean summary, rendered from the JSON above (`--check` fails if they disagree) |

The matrix itself (85,680 member-dates x 76 columns) is not committed. It is fully reproducible from pinned inputs and is identified by a canonical digest.

## The grain and the inputs

One row per `(signal_date, ticker)`: every PIT Top120 member on each weekly decision session from 2013-01-04 to 2026-09-11. Membership is the monthly KRX snapshot
**strictly older than the signal date** (`MembershipSnapshots.on`). The inputs are the ones `kr-model-overlay-portfolio-v1` pinned and verified (accounting blobs, universe blobs, the
replay-v16 manifest and price objects, all checked by git blob or content hash by the sealed `kr_model_raw_snapshot` code), plus two stores that study did not pin and whose git blob SHA-1
is recorded in the report: the KRX bar ledger (`ledger/prices/kr`, as-traded OHLCV + listed shares) and the DART share counts. All are read from the one `signal-history` commit the sealed
studies pinned (`4ea107ed`), never from a moving branch. `pipeline/kr_alpha_atlas_inputs.py` loads them; `load_inputs(commit, root)` run against the preserved raw-input artifact also
finds the official KRX market values (`market/`) and uses them.

## One definition per feature

`pipeline/kr_alpha_atlas_catalogue.py` lists every computed feature, the existing function that produces it, any arithmetic this change adds, and any place the implemented definition is
narrower than the registry's wording. Nothing is a second implementation of an economic feature:

* volume, traded value and liquidity: `liquidity_attention` (and `krx_prices` for the split basis), through `kr_alpha_atlas_bars`;
* accounting quality: `accounting_quality.derive_kr_fields` and `dart_derive` on the filings visible **before** the signal date (never a whole-history derive followed by a filter), with a
  consolidated/separate basis check on every key a figure needs;
* price, industry and the sealed controls: `kr_alpha_tournament_features`, `kr_industry_anatomy`, `kr_stock_within_industry_anatomy`, `kr_value_quality_catalyst`, `kr_market_risk_overlay`;
* the H2 value-with-business-confirmation state: `kr_alpha_signal_v2.cross_section`, fed the same fields the weekly dry run feeds it.

The historical matrix and `kr_alpha_atlas_dry_run` call the same `build_matrix`, so the weekly process cannot drift from the study.

## Basis rules (each is a test)

* **Volume, traded value and turnover are three quantities.** Traded value is as-traded close x as-traded volume (KRW; a split cannot move it); turnover is volume over listed shares on one split basis;
  an adjusted close is never multiplied by an unadjusted volume.
* **A split is only adjusted once it was knowable.** A split is a clean par-value ratio that moves the price at least 42.5% and is corroborated by the listed-share count, which can lag the ex-date by
  weeks (064960.KS: 33 days). A feature window containing a price move shaped like a split that is not yet confirmed at the signal date is **missing**
  (`UNCONFIRMED_CORPORATE_ACTION_IN_WINDOW`), never adjusted with later knowledge. A turnover window touching the stale-share interval is missing (`STALE_SHARE_COUNT_IN_WINDOW`).
  The replay-v16 price panel itself was adjusted with the later confirmation; windows it feeds are masked by the same rule, and the residual limitation is stated.
* **A suspension is not a session.** Zero-volume rows are NaN; a window containing one is missing (`GAP_OR_SUSPENSION_IN_WINDOW`). Nothing is filled.
* **A move above the daily limit that no ratio explains** (capital reduction, re-listing) masks the windows it touches (`UNEXPLAINED_PRICE_MOVE_IN_WINDOW`).
* **A ratio on an undefined denominator is missing**, not an ordinary number: cash conversion needs positive net income, ROE needs positive equity, growth needs a positive prior level, capex
  intensity needs positive revenue.
* **Every missing cell carries a reason from a closed vocabulary**; `reason_checks` fails the build on any cell that does not.
* **Cost, capacity, eligibility and risk-construction columns are never alpha candidates**; the OHLCV accumulation proxy (D11) stays in the volume family and is never investor flow.

## Thresholds (declared before any measurement)

A feature is `MEASURED_READY` when it is measured on at least 60% of the rows inside its own usable range (`kellyPortfolio.probabilityCalibration.integrity.minPitCoverage`) on at least 52 weekly
dates that each have at least 30 measured names (methodology section 4). A Level 3 interaction needs the same joint coverage, at least 52 evaluable dates, and at least 3 names in each corner cell of
its 2x2 contrast on each date. 52 dates and 3 names are introduced here and stated as such. A pass that clears a floor by under 5 points is reported **thin** beside the number.

## Reproduce

```
git fetch origin signal-history
python scripts/build_kr_alpha_atlas_phase_b.py --scratch <empty directory>     # about 30 minutes, network-free after the fetch
python scripts/build_kr_alpha_atlas_phase_b.py --check                         # the summary and canonical form match the committed JSON
```

## Four status axes (revision: status reconciliation)

Every feature carries four separate facts, read from the readiness report and repeated unchanged in the manifest (`featureStatusLedger`) and the source register (`rows`):
the registry's **design-time status** (`registryReadinessStatus`, never edited), the **implementation status** (did this build write it), the **measured coverage verdict**
(`measuredStatus`), and a **genuine source blocker** (`genuineSourceBlocker`, non-null only for a feature that was NOT computed). A feature computed on the real matrix is never a
source blocker, whatever the registry expected: B04 (`MEASURED_READY`, thin, 62.29%), C06 (56.63%) and C15 (52.90%) were `DATA_BUILD_REQUIRED` by design and are published under
`coverageVerdicts`; the registry's own note on them is kept verbatim as `registryBlockingNote` with `registryNoteStatus: SUPERSEDED_BY_MEASUREMENT`. C16 is the one feature of that
registry group that was not computed (no gross-profit account), and it stays a blocker. `reconcile_sources` refuses a computed feature inside a source group and a non-computed
feature that has no source verdict; tests compare the report, manifest, source register and Korean summary feature by feature. No measurement, gate or source identity moved.

## What this does not do

It does not evaluate any feature, fit any model, build any label, select a winner or authorise anything. The registry (`readinessStatus`) is not edited: the report's `measuredStatus` is the
measured overlay, and Phase C pins the registry by hash. Investor flow stays `SOURCE_BLOCKED`. The broader universe stays a feasibility measurement. The official `ACC_TRDVAL` was not read.
