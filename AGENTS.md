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

## Benchmark acquisition invariants (v2.8)

- A benchmark panel materially shorter than the span it was requested for is a FAILED
  download, not a market with no sessions. It is rejected at the source. Outcomes are
  recomputed from a fresh panel every run, so one truncated response silently rewrites
  the whole evidence base — this happened on 2026-08-20, 08-23 and 08-24, and moved the
  published headline from +1.96%/yr to -2.18%/yr on an unchanged ledger.
- The last panel that passed that check is committed under `ledger/benchmarks/`. When no
  vendor passes, the replay runs on that snapshot and the region is labelled
  `SNAPSHOT_FALLBACK`. That is not a substitute value: it is the same vendor's own
  observations, versioned in git and named in the artifact. An outage then costs the
  newest grid dates — not yet matured at 126 days — instead of a decade.
- A snapshot fallback never rewrites the snapshot. A run that could not reach the vendor
  must not be able to shorten the record for the next one.
- Benchmark redundancy is across VENDORS for the SAME instrument. Substituting a
  different index, or a tracking ETF, when one is unavailable redefines what excess
  return means halfway through the history — a quieter error than the outage. A second
  vendor is only admissible when both quote the same series: `^KS200` qualifies because
  a price index carries no dividend adjustment; `SPY` does not, because `auto_adjust`
  returns total return and most alternative routes return raw close.
- An accepted panel is used alone and never stitched to the snapshot. Adjusted closes are
  rescaled retroactively on every dividend, so a series spliced from two fetch vintages
  carries two adjustment factors and its returns across the join are wrong.
- Regional benchmark coverage is appended to `ledger/benchmark-coverage-history.jsonl`
  every run. A collapse must be visible as a one-line diff, not something that can only
  be found by rewinding the branch and recounting shards.
- Lowering `minBenchmarkCoveragePct`, or dropping a region from `benchmarks`, is never
  the fix for a coverage failure. Both restore the pre-gate state where a run is green
  and the evidence is silently gone.

## Version generation policy (v2.8)

- `dataVersion` covers acquisition: sources, batching, date normalization. `modelVersion`
  covers scoring only. A download-shape change is not a scoring change, and bumping
  `modelVersion` for one resets the prospective paper ledger to zero days.
- A generation bump is a deletion. It strands every existing record behind a version
  filter, and two bumps in two days stranded 853,076 historical signals and 13,518
  prospective ones while the underlying defect was still unfixed. A PR that bumps any
  generation version states, in its description: what changed that makes old records
  incomparable, how many records are stranded, and when the replacement generation will
  exist. Verify the fix works on real data BEFORE bumping.
- A generation the code requires but no run has ever produced is a PIPELINE FAULT, not an
  absence of evidence. `historicalValidation.pipelineHealth` must say which, and the
  validator rejects an artifact that reports the fault as plain unavailability.

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
- A skill threshold is never negative. `minBrierSkill` gates the probability distribution
  that sizes a Kelly weight, and it is the only reliability check a zero-information
  predictor cannot clear: a constant at the base rate has Brier <= 0.25 by construction,
  near-zero ECE and log-loss ~0.69, so `maxBrier`, `maxEce` and `maxLogLoss` pass every
  time. The floor is not a noise allowance — the simulated null has sd ~0.001.
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
