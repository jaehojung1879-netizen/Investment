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
- Survivorship has two gaps and they are counted separately: names the membership
  file describes but the vendor cannot price (`constituentCoveragePct`), and names
  the file does not describe at all (`membershipCoveragePct`). A gate that reads one
  of them turns green when the other is wide open — a US-only membership file prices
  everything it knows about and answers the first with 100.0 while an entire region
  is undescribed. `portfolio_validation.universe_ready` is the single predicate for
  both; the published `affectedObservationsPct` is their UNION, never one of them and
  never their sum. Measured-on-one-side is `None`, not a pass.
- Coverage is reported by region and by year, and the risk band is the WORST region's,
  not the pooled average's. The gap is concentrated: one region can be entirely
  unresolved while the pooled figure reads as a nick, and the need is front-loaded in
  time — the 2013 S&P 500 is missing 219 of 500 names before any vendor is asked
  against 34 in 2025. A decade-averaged coverage figure describes no cross-section
  inside it.
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

## PIT fundamentals invariants (v2.9)

- A filing's `availableFrom` comes from its receipt date and from nothing else. The
  period it describes ended long before it was submitted — on the 2023 samples the
  quarterlies landed 45 days after period end and the annual report 71 — so reading
  it from the period end is a look-ahead of exactly that gap. A filing whose receipt
  date is missing is REFUSED, never stored with a substitute: a row that cannot say
  when it became visible looks like coverage and is not.
- Filings are stored RAW — the accounts as DART states them, under DART's own amount
  column names. Deriving TTM figures, per-share numerators and ratios is a separate
  step, because a derivation found wrong must be fixable without re-fetching a
  backfill that took fourteen hours.
- Both amount columns are kept. `thstrm_amount` is the period and `thstrm_add_amount`
  the year-to-date running total; an income figure in a Q3 report is nine months
  cumulative, not three, and a TTM built from the wrong column is wrong all the way
  down to the position size.
- Consolidated and separate statements are different definitions of the same company.
  Consolidated is preferred, the separate one is the only statement some filers have,
  and which answered is RECORDED on the record — a book that mixes them without
  saying so ranks companies against each other on two different bases.
- Account labels are matched EXACTLY against a filer-alias list. A substring rule
  folds `영업이익률` into `영업이익` and ranks a percentage against a currency amount
  without erroring.
- A blank line item is `None`, never `0.0`. Zero is a number a filer stated; blank is
  a line they did not, and a fabricated zero propagates into every ratio built on it.
- Collection is append-only and identified by ticker x fiscal year x report code. A
  restatement arrives as its own filing with its own receipt date rather than
  overwriting the number that was actually visible at the time.
- DART serves from 2015 and the replay starts 2013, so Korean value and quality are
  dark for the first two years however complete the collection is. That gap is
  reported per year, not averaged away, and it is not a reason to move the replay
  start: it would trade two years of price-sleeve evidence for uniformity.

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

## Selection-edge invariants (v2.8)

- A concentrated book's edge is a claim about CHOOSING, and it is tested against the
  distribution the same construction produces when the conviction scores are permuted
  across names. Dates, research pool, name/sector/region caps, entry-state and evidence
  exclusions, cash floor, weighting function and transaction costs are all held fixed;
  only which name carries which score changes. A benchmark comparison cannot make this
  claim, because it bundles universe carry and the construction rules in with the
  ranking.
- The null permutes REAL scores rather than drawing noise, so the null book carries the
  same conviction-tilt and concentration profile as the real one. Drawing fresh scores
  would change the shape of the book and confound tilt with ordering.
- The alpha selection floor is dropped inside the null, because it is itself a score
  decision — a null bound by it could only ever pick names the score already approved.
  Every other exclusion is a fact about the name, and the null stays subject to it.
- `BEATS_RANDOM` requires clearing the null on a RISK-ADJUSTED statistic. Beating it on
  raw excess while sitting inside it on information ratio means the extra return was
  bought with extra risk, which is not what a 3-5 name book is for.
- The null tests the ranking and concentration step WITHIN an already alpha-filtered
  research pool. It does not test the research screen, and no artifact may describe it
  as if it did.
- Selectors are compared on ONE shared block schedule, over dates where every selector
  is measurable, using the later maturity date so the blocks do not overlap for either.
  Comparing two selectors over two different periods and two different benchmark blends
  is not a comparison; the 2026-08-22 report ranked a champion from 2013-01 against a
  challenger from 2013-11 that way.
- A selector difference is decided by a paired difference with a published interval, not
  by a bare inequality between two point estimates. On ~130 blocks the sampling error is
  wider than any gap either selector has shown.
- A path is published only when nearly every portfolio in it was measurable
  (`minPortfolioCompletenessPct`). A dropped portfolio is not a random omission: a name
  without a matured benchmark is disproportionately a halted or delisted one, so a path
  built from the survivors is a different strategy. Refuse the headline; never
  renormalize the covered weight and present it as the book.
- A permutation p-value carries the +1 correction in both terms, so it is never zero and
  never claims more evidence than the draw count supports.

- Rank IC is not the instrument for a concentrated book. It scores whether the whole
  cross-section is ordered correctly on average; the production book holds five names,
  and the two disagree in practice — on the validation period the composition with the
  best US rank IC had a WORSE Sharpe than production, and the one with the worst IC had
  the smallest drawdown. A sleeve may be there to hold down risk rather than to predict
  return, and IC cannot tell the difference. Judge selection by the null-tested portfolio
  path.
- A factor attribution measured over the full ledger includes the sealed holdout. Any
  number used to MOTIVATE a model change must be recomputed on the validation period
  first: the KR rank IC that justified a region-specific rule was +0.019 over
  2013-2026 and -0.001 over the validation period alone.

## Transaction-cost invariants (v2.9)

- The turnover in a cost estimate is a share of the SLEEVE, not of the book.
  `estimate_transaction_cost` multiplies it by one candidate's position, so the
  quantity is "of the weight held in this region, what fraction is traded per
  rebalance". The portfolio-level figure divides by the whole book including
  cash, so with a cash floor it is always the smaller number: on the replay
  ledger it reads 58.1% while the sleeves measure 85.3% (US) and 63.1% (KR).
  One number applied to both understated BOTH, most on the sleeve that churns
  hardest. The sleeves differing is established by a paired difference with an
  interval, not by the inequality between two point estimates: US-KR is
  +22.20pp over the 50 shared rebalances, 95% bootstrap CI [+9.83, +34.09]pp.
  A regional split whose interval spans zero is a split nobody measured, and
  the portfolio figure stands.
- A region held at neither end of a rebalance is absent from the measurement,
  never a 0% observation. Counting it as one drags a region's hurdle down in
  exactly the periods the strategy was avoiding that region.
- Regional rates do not sum to the portfolio rate and are not expected to; cash
  carries no region. Reconciling them by attributing cash to a region would
  invent an allocation the book never made.
- A 3-5 name book holds 2-3 names a side, so one name replaced moves a regional
  rate 33-50 points. A regional rate is admitted only over
  `MIN_REGIONAL_TURNOVER_REBALANCES`; below it the portfolio rate stands in and
  `turnoverNote` says the region is wearing another sleeve's number. Silence
  would read as its own measurement.
- The initial build is not a rebalance. It is paid once and the rate it feeds is
  multiplied by every cycle in the horizon, so it is excluded from both the
  portfolio and the regional averages.

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
