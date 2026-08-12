# Investment repository invariants

- Blocked artifacts must contain no actionable output, entry state, positions, weights, or radar tiers.
- Synthetic, seed, and stale artifacts must never pass production validation or deployment.
- Ledger signals are append-only and identified by date, region, ticker, and model version.
- Do not claim point-in-time behavior unless release visibility and vintage limitations are verified and documented.
- `liveValidated` is forbidden until real ledger requirements are met; builds never auto-promote it.
- Keep generated `data/site-data.json` separate from explicit synthetic fixtures.
- After changes run `python -m compileall pipeline`, `pytest -q`, seed generation, and artifact validation.
- Never merge directly to `main`.

## Historical replay invariants (v2.4)

- HISTORICAL_OOS and PROSPECTIVE_PAPER evidence live in separate files, carry separate
  `evidenceClass` labels, and are never pooled into one table, one average, or one UI panel.
  They may only meet inside the expected-return posterior, with both weights published.
- A replay must read no data after its as-of date. Historical fundamentals without a
  publication date are WITHHELD, never back-applied from today's snapshot.
- Historical signals are immutable and stamped with `replayVersion`, `featureVersion`,
  `modelVersion` and `dataVersion`. A model change starts a new generation; it never
  rewrites or pools with an old one.
- The historical ledger is stored as gzipped month shards under
  `ledger/historical/<replayVersion>/`, never as one file: a decade of weekly
  cross-sections is ~900 MB and GitHub rejects blobs over 100 MB. Shard writes must stay
  byte-deterministic so an unchanged shard is not re-committed, and `assert_pushable`
  must run before any push. If a shard outgrows the limit, shard finer — do not raise it.
- Path-dependent statistics (drawdown, CVaR, Sharpe) are computed only on non-overlapping
  date samples. Means and hit ratios may use every date.
- The final holdout stays sealed during development and raises on access; it is scored
  once, after the winning model is frozen.
- Model selection happens on validation blocks only. Test blocks are scored, never consulted.
- An ML model that fails any acceptance check is NOT published; the rule-based score stays
  in force and the artifact says which checks failed.
- `VALIDATED_OPPORTUNITY` requires an accepted model. The validator rejects the tier otherwise.
- Drift between historical and prospective evidence may only reduce the Kelly fraction.
- Serving features come from `historical_replay.live_features` so training and inference
  share one feature definition. Do not build a second one in `build.py`.
- `trackingDays` and `maturedObservationDays` are different quantities and are reported
  separately; a ledger with recorded signals must never report zero tracking days.
