# Investment repository invariants

- Blocked artifacts must contain no actionable output, entry state, positions, weights, or radar tiers.
- Synthetic, seed, and stale artifacts must never pass production validation or deployment.
- Ledger signals are append-only and identified by date, region, ticker, and model version.
- Do not claim point-in-time behavior unless release visibility and vintage limitations are verified and documented.
- `liveValidated` is forbidden until real ledger requirements are met; builds never auto-promote it.
- Keep generated `data/site-data.json` separate from explicit synthetic fixtures.
- After changes run `python -m compileall pipeline`, `pytest -q`, seed generation, and artifact validation.
- Never merge directly to `main`.

## Historical replay invariants (v2.6)

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
- Historical portfolio replay and live construction share the production selection and
  baseline-weighting functions. A copied backtest formula is forbidden.
- A price-sleeve replay without PIT fundamentals is labelled
  `PRICE_SLEEVES_ONLY_AUDIT_PROXY`; it may not claim full four-factor fidelity.
- Challenger calibration admits a label only after `outcomeEndDate <= replayDate`, and no
  historical result may automatically promote a selector or relax the Kelly gate.
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

## Alpha attribution invariants (v2.7)

- A bucket's excess return over the benchmark is `universe carry + alpha spread`. The
  expected return is the LESSER of the level and the spread, and the artifact records which
  side bound. When the universe beat its benchmark the level is inflated by carry the
  ranking did not produce, so the spread binds; when the universe LAGGED its benchmark the
  spread flatters, because a bucket can sit far above a falling universe while earning
  nothing against the index the book is measured on. Crediting either is the same error.
- Ordering admission tests the same conservative quantity that will be published. The top
  bucket's own spread must clear the threshold on its own — a top-minus-bottom spread that
  is significant only because the bottom collapsed is not an edge a long-only book can
  collect — and at least one corroborating reading (top-minus-bottom, or the rank IC) must
  agree.
- The ML acceptance gate obeys the same attribution rule. `netExcessSurvivesCost`,
  `beatsBaselineOutOfSample` and `holdoutHolds` are evaluated on the top bucket's
  attributable excess (the conservative side of level and spread over the per-date
  universe), never on the raw excess over the benchmark. An absolute bar met by a level
  is met by universe carry: on the production ledger a random pick earns +1.1% to +2.4%
  per 126 days and clears a 0.5% bar with no skill.
- An acceptance check that could not be assessed is `None`, not `True`. It stays
  non-blocking, but it is never reported as a pass.
- Passing the gate is not one fact. A significant rank IC is `FULL_RANK`; a significant
  extreme spread with an unproven middle is `EXTREMES_ONLY`, which is usable for a book that
  only holds the top bucket but must never be reported as full-range ordering. A score that
  is sharp at the extreme while its middle runs backwards is real and is admitted on its
  top-bucket spread, not rejected on the IC's sign.
- Shrinkage, standard errors and effective-date counts attach to the SPREAD series, not the
  level. A level made precise by the universe moving together carries no information about
  the ranking.
- Isotonic monotonicity repair runs only where ordering is established. Isotonic regression
  returns a monotone fit for any input, so running it ungated launders noise into a ladder.
- Ordering is established only by a HAC t on the top-minus-bottom spread or on the per-date
  rank IC clearing `minOrderingTStat` with sufficient effective dates. Where it is not
  established, no bucket is usable and no historical prior reaches Kelly.
- HAC bandwidth is measured in observations of the series being estimated, converted from
  the horizon via the replay grid spacing — never fixed at `horizon - 1` trading days. On a
  weekly grid a 126-session overlap spans ~26 observations, and using 125 lags inflates
  every t-statistic and effective sample in the system.
- Thresholds that gate a claim are calibrated against a simulated null of that same gate,
  and the simulated rejection rates are recorded next to the constant.
