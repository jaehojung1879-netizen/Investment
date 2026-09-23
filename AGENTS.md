# Investment repository invariants

- Blocked artifacts must contain no actionable output, entry state, positions, weights, or radar tiers.
- Synthetic, seed, and stale artifacts must never pass production validation or deployment.
- Ledger signals are append-only and identified by date, region, ticker, and model version.
- Do not claim point-in-time behavior unless release visibility and vintage limitations are verified and documented.
- `liveValidated` is forbidden until real ledger requirements are met; builds never auto-promote it.
- Keep generated `data/site-data.json` separate from explicit synthetic fixtures.
- After changes run `ruff check .`, `python -m compileall pipeline`, `pytest -q`, seed
  generation, and artifact validation.
- Never merge directly to `main`.

## Measurement-absence invariants (v2.11)

- A statistic with nothing measurable behind it is `None`, never its most extreme
  value. Excluding unmeasurable names from a ratio and then returning `0.0` when the
  measurable set is EMPTY is the same defect the exclusion exists to prevent, wearing
  the strongest reading the scale allows: `sentiment` published 0% 200-day breadth for
  a cross-section that stated nothing, and that component carries 0.4 of the fear/greed
  index, so a silent universe read as 극도의 공포. An unmeasured component abstains
  from the score; a component that is measured but wrong is a different bug with a
  different fix, and collapsing them costs the ability to tell which one happened.
- A share is published with what it was measured ON. 100% breadth over two names and
  over five hundred are not the same reading and an artifact carrying only the ratio
  cannot tell them apart. The denominator and the universe size travel with it.
- A classification that has a verdict for the unresolvable case is not a missing
  measurement. `risk.diagnose` answers "Transition" for a name whose 200-day mean does
  not exist yet, so `bull_pct` has no absence to handle — only the statistics that
  return `None` get an abstention branch, and inventing one for the others would hide
  a real reading.

## Selection-value invariants (v2.11)

- A CAGR gap is not a selection edge until it has been SPLIT. Geometric =
  arithmetic + compounding, and a book less volatile than its matched benchmark
  earns the second term without picking a single better name. The calibrated
  challenger's headline +0.340pp/yr is +0.040pp of arithmetic stock selection
  and +0.300pp of compounding at 0.83x the benchmark's block volatility — 88% of
  the only positive number in the benchmark-alpha report is a low-volatility
  tilt. `selection_value.decompose_edge` reports both terms or neither.
- Turnover is reported as names REPLACED and weights RETARGETED separately,
  because the remedies are opposite: carrying a drifted book removes the second
  at zero change in what is held, while the first means holding different names.
  Both published books are 92-93% name replacement, so a no-retarget band was
  never going to be the lever.
- A permutation null belongs to ONE selector and says which. It permutes one
  ranking, so BEATS_RANDOM is a statement about that ranking and no other. The
  report published a single unlabelled null built from the champion's conviction
  score while a promotion would move the CHALLENGER — whose arithmetic selection
  edge is +0.040pp/yr against the champion's -1.589pp. `selection_null` stamps
  `selector` on every return including the unavailable ones, `promotionEvidence`
  names `promotedSelector`, and the validator refuses a mismatch or a blank.
- Beating the null and beating the benchmark are DIFFERENT BARS and are never
  reported as one. Choosing is worth about +2.9pp/yr against a permuted ranking
  on replay-v16 and the book still trails its matched benchmark by 1.378pp: the
  null says the ordering carries information, the benchmark says the
  construction does not yet pay for itself.
- An ablation ladder is specified BEFORE its result and each rung moves exactly
  one thing. `benchmark-relative-alpha-v1` moved cadence, a cash gate and the
  weighting rule together, and its 1.4pp gross loss could not be attributed to
  any of them. A rung is a fixed point on a design axis, never a tuned variant,
  and the neutral setting is the ABSENCE of a component rather than a fitted
  value for it.
- A hypothesis refuted by its own pre-specified test is REPORTED and the
  reasoning that produced it is left standing next to the refutation. "The
  ranking is not worth its bill, so hold what the screen approved" lost to the
  concentrated book by 1.683pp/yr and the arithmetic edge rose monotonically
  with how much of the ranking was used. Re-specifying the ladder until the
  hypothesis survives is the failure this repository's discipline exists to
  prevent; deleting the module afterwards loses the instrument that produced
  the answer.

## Switch-hurdle invariants (v2.12)

- A LADDER CARRIES ITS OWN CONTROL, and the control is the baseline. A research
  loop is not `portfolio_replay` however carefully it is written: this one
  builds its calibration on gross rather than cost-adjusted excess, and its
  no-hurdle rung lands at -0.684pp against the published challenger's -1.046pp.
  Paired against the published path the hurdle would have been credited +3.119pp,
  0.362pp of which is a scoring difference it did not make. Every rung is paired
  against the rung that differs from it in ONE thing, and the control's own gap
  to the published path is published beside it as a harness difference.
- Turnover costs are regional because the tax is. A buy pays commission plus
  half the spread; a sell pays that plus the statutory transaction tax, which
  in Korea has run 30bp down to 15bp and makes a Korean round trip cost 1.6x to
  2.5x an American one. A pooled rate under-protects the expensive market and
  over-protects the cheap one, and the hurdle a decision clears is priced from
  the same dated schedule `_turnover_cost` charges the realised path.
- A HURDLE IS SPENT AGAINST THE GAP BETWEEN COMPETING NAMES, not against zero,
  so the size of a credit does not predict how often it binds. Korea's credit is
  three times America's and American retention still rose four times as much
  (41.2% -> 88.0% against 53.2% -> 62.9%): what decides it is the dispersion of
  expected alpha inside the region, plus how many of its pool names the region
  cap lets the book hold. Predicting where a rule will bite is not measuring it.
- WHERE THE GAIN CAME FROM IS PART OF THE RESULT. The cost hurdle saves 0.270pp
  of cost drag and gains 2.157pp of arithmetic stock selection, so eight times
  more of it is the book holding names longer than the fees it avoids. A rule
  that works for a reason its author did not predict is weaker evidence than one
  that works for the stated reason, and the report says so rather than banking
  the headline. Here it points at a different hypothesis — that last month's
  ranking is noisier than the position it displaces — which is a claim about the
  signal and has not been tested.
- More hysteresis is not monotonically better and the ladder must be able to
  show it. The one-standard-error rung trades least (2.814x) and gives back most
  of the gain at a -35.0% drawdown, deeper than every other path measured.
- A first interval that clears zero is reported with what makes it thin. The
  cost rung's lower bound clears by 0.122pp, on one historical sample, after
  several rungs across two studies, with no multiplicity correction — all of
  which is published with the number, and none of which makes it a promotion.

## Signal-persistence invariants (v2.12)

- WHEN A RULE WORKS FOR THE WRONG REASON, THE REASON IS THE NEXT STUDY. The
  switch hurdle saved 0.270pp of cost drag and gained 2.157pp of arithmetic
  stock selection; holding a name longer cannot make the name better, so the
  finding was about the signal. Banking the headline and moving on would have
  left the actual mechanism unmeasured.
- A SMOOTHER LOOKS BACKWARD ONLY, over a name's OWN prior appearances, and never
  invents the history it lacks. A name seen for the first time carries its raw
  percentile, so every window agrees on it. Reaching forward would hand the
  ranking information it did not have and would do it invisibly — the path would
  simply look better.
- Scoring and selection are handed the SAME number. Ranking on a smoothed
  percentile while capping on the raw one ranks names by one quantity and
  constrains them by another, and nothing in the output shows the disagreement.
- An ADDED-versus-RETAINED comparison is paired WITHIN a rebalance. Both groups
  were chosen by the same ranking on the same date under the same constraints,
  so the within-date difference carries no market-timing term; pooled across
  dates it would measure which months were kind. Measured: -1.331% per block,
  95% CI [-3.029%, +0.174%], which CONTAINS zero on 131 paired rebalances.
- THE AXIS IS MEASURED BEFORE THE LADDER IS READ. A name's alpha percentile
  moves a mean of 1.146 points between consecutive blocks and is integer
  rounded, so the axis being varied is narrow. That a one-point input change
  produces a multi-point output change is the greedy-selection property the
  determinism invariants already name — it makes the mechanism plausible AND
  the estimate fragile, and both halves are published.
- Two levers that move DIFFERENT quantities are reported as different findings.
  Smoothing raises arithmetic stock selection from +0.315pp to +2.994pp at
  essentially unchanged turnover (4.679x to 4.625x); the hurdle cut turnover to
  3.567x holding the same kind of names longer. They stack because they are
  orthogonal, and the stacked path moves TWO axes and is attributable to
  neither, so it is reported outside the ladder.
- A LADDER THAT DOES NOT SEPARATE SAYS SO IN ITS OWN VERDICT.
  `separatedFromControl` is empty here: every point estimate moves one way, the
  rungs are monotone in k, and no interval clears zero. Consistency across
  angles is corroboration and is reported as corroboration — never as a
  rejection of the null, and never as grounds to promote.

## Alpha-reliability invariants (v2.13)

- A RANKING CANNOT BE SPENT BETTER THAN IT CAN BE REPRESENTED, and how much it
  can represent is measured before anything is built on it. The research pool is
  already alpha-filtered: its percentiles run 91-100 (mean 97.4, sd 2.33) and
  the calibration's edges are (0, 60, 80, 90, 95, 100), so exactly TWO buckets
  are ever occupied and 83.55% of 3,720 pool name-dates sit in one of them.
  Names inside a bucket are handed the SAME expected excess, so for most of the
  pool the alpha term is a constant and the ordering falls to realised downside
  volatility. Every study that proposed to refine the percentile was proposing
  to refine something the decision layer cannot see.
- THE BOOK SWAPS NAMES IT HAS NO ALPHA REASON TO SWAP, and this is measured, not
  inferred. 86.71% of the control's top-5 cuts and 29.77% of its swaps are
  between names the calibration scores IDENTICALLY. Of 412 held names whose raw
  percentile moved one point or less since their previous appearance, 47.82%
  were replaced anyway. The relative score gap at the cut has a median of 0.086
  and a p10 of 0.010 — the boundary is decided by a rounding of the risk
  estimate far more often than by the signal.
- THE SWAPS THE CALIBRATION CANNOT JUSTIFY ARE THE ONES THAT LOSE. Arriving
  minus departing realised 21-session excess is -2.601% per block on the 39
  swaps tied on expected alpha (38.5% win rate, 95% CI [-5.510%, +0.024%]) and
  +1.845% on the 92 that were separated (55.4%, [-1.075%, +5.005%]). Pooled the
  two read +0.521% and say nothing. This is the strongest statement this
  programme has about WHICH replacements are worth making, and both intervals
  still contain zero.
- A NAME EXCLUDED BY A CAP IS NOT THE RANKING'S MARGINAL REJECT. `_select_scored`
  stamps `BELOW_TARGET_COUNT_CUTOFF` on what the book was too full to reach and
  a cap code on what it refused earlier, and those are different facts:
  comparing the last held name against the first non-held one would measure the
  diversification rules instead of the ranking. Cap-bound rebalances are
  counted, never silently folded into the boundary statistic — on the control
  path 2 of 145.
- A DIAGNOSTIC BUILT ON AN AUDIT WINDOW MEASURES THE WINDOW. `selection.ranking`
  publishes the selected names plus EIGHT near misses, so every name below that
  carries no cut reason at all — and the first boundary statistic read a missing
  reason as "not excluded by rank" and dropped the rebalance. It reported 91 of
  145 measured and 54 cap-bound; re-running production's own `_select_scored`
  over the whole cross-section gives 143 and 2. The conclusion did not move
  (81.32% -> 86.71% tied) but a third of the sample had been silently
  unobservable, and a truncated audit view is not a measurement of the thing it
  is a view of.
- PRODUCTION MUTATES THE ROWS A CALLER HANDS IT, and a research module that
  keeps them has to know. `select_portfolio_by_scores` shallow copies each row,
  so `item["exclusionCodes"]` IS the caller's list and `_select_scored` appends
  `BELOW_TARGET_COUNT_CUTOFF` and the cap codes straight into it. Departure
  attribution read those back as facts about the name and called 244 of 444
  departures "ineligible on its own facts"; against an immutable
  `eligibilityCodes` captured at build time the real split is 160 pool exits,
  150 outranked, 84 region cap, 40 entry state and 10 sector cap, and none
  ineligible. The two lists answer different questions and are kept apart.
- A CONFIDENCE WEIGHT IS A CONTRACTION OR IT IS A FACTOR. `reliable_alpha =
  confidence x alpha` keeps |reliable| <= |alpha| with the sign preserved, so it
  can only ever reduce what a name is credited with; `contraction_holds` is
  asserted on every row of every block and raises. The alternative shapes were
  refused for cause, not for taste: shrinking the PERCENTILE toward the pool
  mean moves a weak name at 93 UP into the top bucket, shrinking it toward 50
  collapses the whole pool into one bucket, and `evidenceCoverage` is
  unavailable entirely because `longterm` already computes
  `alpha = rawAlpha x evidenceCoverage` before the percentile is taken.
- SEPARATION IS READ IN BOTH DIRECTIONS, and the downside one is the more
  informative. Reading it as "the lower bound cleared zero" is how a ladder
  reports `separatedFromControl: []` while one of its own rungs has been
  refuted. The confidence axis is the first interval in four studies on this
  ledger to exclude zero against its own control — at -3.984pp, 95% CI
  [-8.144, -0.214], in the WRONG direction. `separatedFromRungBelow` carries a
  `direction`, never a bare list of names.
- A CANDIDATE ITS OWN PRE-SPECIFIED TEST REFUTED IS NOT FROZEN, and the
  provenance of that rule is published with it. The design named the last rung
  unconditionally; the condition was added after the first full run produced the
  refutation above. What makes that a tightening and not a re-specification: no
  rung, parameter, window or scoring rule changed, every number is what that run
  produced, and the condition can only ever REMOVE a candidate. A rule that can
  only subtract cannot launder a result.
- A RULE CAN DO EXACTLY WHAT IT WAS DESIGNED TO DO AND STILL NOT PAY. Signal
  hysteresis moved incumbent retention 39.3% -> 67.1%, one-way turnover 4.535x
  -> 2.955x and cost drag 1.330pp -> 0.847pp, and it removed the losing tied
  swaps it was aimed at — the tied population's realised difference goes -2.601%
  (n=39) to +1.149% (n=24). Its paired difference against the rung below is
  +0.288pp, 95% CI [-4.430, +5.416]. Behaviour changing as predicted is
  mechanism evidence and is reported as mechanism evidence; it is not a result.
- WHERE THE ALPHA TERM ORDERS AND WHERE IT DOES NOT ARE DIFFERENT PLACES, and
  only one of them decides anything. Across the whole cross-section the score's
  rank correlation with the calibrated alpha is 0.758 against 0.075 with
  downside volatility, so the alpha term orders most PAIRS — but a five-name
  book is decided at its margin, and 86.71% of cuts have both sides in the same
  bucket. The held set matches an alpha-only top-N 30.07% of the time and 37.52%
  of held-against-not-held pairs are ordered the other way by the alpha
  percentile. Quoting either number alone describes a different system.
- THE DEFENSIVE TILT IS IN WHAT IS HELD, NOT IN A RANK CORRELATION. Held names
  carry 24.45% downside volatility against 27.17% for rejected ones and a
  `lowvol` sleeve percentile of 74.37 against 63.81, and `lowvol` is among a
  held name's top two sleeves 58.86% of the time. So part of the tilt arrives
  through the ALPHA itself and would survive deleting the score's
  downside-volatility denominator — which is why `alpha-risk-separation-v1`
  moves the denominator alone and leaves the 0.20 sleeve weight to the study
  after it. Two risk channels moved together are attributable to neither.
- THE DIVERSIFICATION GUARD IS A LARGER SOURCE OF TURNOVER THAN THE RANKING'S
  OPINION IS. The region cap stopped a name on 93.10% of control rebalances and
  on 134 of 145 the capped name outscored one the book took, median decision
  alpha gap 0.856pp; held name-dates split KR 421 / US 301 where the same count
  with the caps lifted wanted KR 640 / US 82, and the book is KR:3/US:2 on 132
  of 145. Caps account for 21.17% of every replacement and the entry-state step
  for a further 9.01%, against 33.78% the ranking actually outranked. A rule
  that produces a fifth of the turnover is not a side constraint.
- A DIAGNOSTIC ADDED AFTER A LADDER IS SCORED MAY ONLY READ IT. The structural
  diagnostics landed after this study's rungs were final; they changed no score,
  added no rung, moved no constraint, and the ladder, its paired intervals and
  the stacked path are byte-identical with and without them. A within-block
  reading with a constraint notionally lifted — "the top-N on alpha alone", "the
  top-N with the caps off" — is a count of how often two rules disagree, never
  an estimate of what disagreeing would have earned: nothing is valued, carried
  forward or compounded, and no realised return enters one.
- THE BOTTLENECK NAMED BY THIS STUDY IS RESOLUTION, NOT INFORMATION. Before any
  new factor is collected, the open question is whether a finer or pool-relative
  calibration of the SAME percentile recovers orderings the current five-edge
  bucket map discards. Adding a factor to a decision layer that can express two
  states would add it to the same two states.

## Alpha-risk-separation invariants (v2.14)

- A CONTROL THAT IS CALLED IS SAFER THAN A CONTROL THAT IS REPRODUCED.
  `alpha_risk_separation.CONTROL` is literally `alpha_reliability.CONTROL`,
  and the control path is produced by calling
  `alpha_reliability.run_rung(alpha_reliability.CONTROL, ...)` directly rather
  than re-implementing its candidate assembly and scoring. A second
  implementation is a second place for a control to drift from the path it is
  supposed to be.
- REMOVING A DENOMINATOR IS NOT REMOVING AN ELIGIBILITY FACT.
  `DOWNSIDE_RISK_UNAVAILABLE` excludes a name on BOTH rungs, because
  inverse-downside-volatility position SIZING still needs a risk unit
  whatever the selection SCORE divides by. Relaxing the exclusion along with
  the score change would let the study claim a benefit that actually came
  from sizing names the control could not size at all.
- THE SAME SCORE SERVES SELECTION AND THE CONVICTION TILT, so removing its
  denominator changes both. `selection_and_baseline` hands one `scored` list
  to `select_portfolio_by_scores` (which five names) and to `baseline_weights`
  (the 0.5x-1.5x tilt among them, by the same rank). What the axis leaves
  UNTOUCHED is the tilt's BASE, `1 / max(risk_unit, 0.05)`, computed
  identically on both rungs — inverse-volatility sizing is exactly as it was;
  only the ranking that decides who receives it no longer divides by risk.
- REMOVING THE SCORE'S ONE CONTINUOUSLY-VARYING TERM CAN ONLY MAKE TIES AT
  THE MARGIN MORE COMMON. Measured: cuts tied on expected alpha rise from
  86.71% to 94.41%, the median relative score gap at the cut collapses from
  0.086 to 0.000, and one-way turnover rises from 4.679x to 5.744x. This is
  reported as the MECHANISM behind the turnover change, not left as an
  unexplained side effect — `boundary_instability` and `replacement_anatomy`
  (`alpha_reliability`) are run unmodified on the new rung's own decisions,
  exactly as `risk_dominance` is, rather than re-derived.
- A DEFENSIVE TILT CAN SURVIVE THE CHANNEL THAT WAS MEASURED FIRST. Removing
  the denominator moves downside volatility held by +1.664pp and `lowvol`
  being a held name's highest sleeve by -7.76pp (32.69% -> 24.93%) — present
  but reduced, not collapsed. The tilt LARGELY SURVIVES, which means part of
  it arrives through the alpha term itself (the `lowvol` sleeve, 0.20 weight)
  and not through the ranking denominator this rung removed. That is why the
  sleeve move is its OWN study and was never widened into this one.
- THE PAIRED INTERVAL CONTAINS ZERO AND THE POINT ESTIMATE IS WORSE. Net
  excess moves from -0.684pp (control) to -1.586pp (alpha only), paired
  difference -0.902pp, 95% CI [-5.068, +3.210] over 155 blocks. Sharpe falls
  0.853 -> 0.747 and MDD deepens -25.158% -> -28.958%. Removing the
  denominator is not shown to help, and the interval does not clear zero in
  either direction — reported as CONTAINS ZERO, not folded into "no result".
- NO PERMUTATION NULL WAS RUN. No rung in this ladder may be described as
  beating random, and the freeze manifest says so explicitly.

## Dynamic-breadth invariants (v2.15)

- A FLOOR, A CEILING AND A MULTIPLE ARE ALL INHERITED, NONE INVENTED HERE.
  `[FLOOR, CEILING] = [3, 10]` are the exact numbers `alpha-reliability-v1`
  pre-registered for this study; `FLOOR` also equals production's existing
  `selection.minNames`. `SE_MULTIPLE = 1.0` is `switch_hurdle.SE_MULTIPLE`,
  imported rather than re-declared, so the two studies that use it cannot
  silently diverge on the unit.
- DISTINGUISHABILITY IS TESTED ON THE ALPHA CLAIM, NOT THE RISK-ADJUSTED
  SCORE. The selection score blends three questions (alpha, risk, entry
  state); breadth is specifically about the alpha estimate's own precision,
  so the walk reads `expectedExcessReturnPct` and `standardErrorPct x
  shrinkageFactor` directly from the calibration — the same scaling
  `switch_hurdle.hurdle_scores` already uses for its own margin. The SCORE
  used to RANK names never moves from `alpha_reliability.CONTROL`'s.
- THE WALK IS MONOTONIC AND STOPS AT THE FIRST FAILURE. A later name clearing
  the bar after an earlier one failed it is not additional distinguishable
  breadth, it is the tail of a ranking whose head already said stop. Below
  the floor no test is applied — the floor is unconditional, matching
  production's own `minNames`.
- A CAP OUT OF SCOPE FOR THIS STUDY STILL BINDS, AND THAT IS MEASURED RATHER
  THAN ABSORBED. `maxNamesPerRegion = 3` is unchanged and this is a
  two-region universe, so the hard ceiling this book can ever actually hold
  is 6, not the pre-registered 10. Measured: the SE-distinguishability walk
  computed a target averaging 4.290 names before any cap; 17.42% of
  rebalances were trimmed below that computed target by the region or sector
  cap; the walk reached the ceiling of 10 on only 4.52% of rebalances.
  Widening those caps is `region-quota-removal-v1`'s axis, not this one's.
- ON THIS SAMPLE THE WALK MOSTLY STOPS RIGHT AT THE FLOOR. 138 of 155
  rebalances stopped on `ALPHA_NOT_DISTINGUISHABLE_FROM_ZERO`, most of them
  at or near rank 4 — consistent with `alpha-reliability-v1`'s finding that
  the pool occupies two calibration buckets and consecutive-rank alpha gaps
  cluster near zero. Mean names held fell from the fixed 4.658 to 3.910.
- THE PAIRED INTERVAL CONTAINS ZERO. Net excess moves from -0.684pp (fixed
  five) to -1.001pp (dynamic 3-10), paired difference -0.317pp, 95% CI
  [-2.133, +1.425] over 155 blocks. Turnover fell 4.679x -> 4.416x and MDD
  shallowed -25.158% -> -21.336%, but the excess comparison does not
  separate in either direction — reported as CONTAINS ZERO, not as a result.
- NO PERMUTATION NULL WAS RUN, and no search over 3/5/7/10 was performed.
  Exactly one dynamic rule, specified before the result, is compared against
  the fixed-five control.

## Region-quota-removal invariants (v2.16)

- THE PREREQUISITE IS MEASURED, NOT ASSUMED AWAY. `alpha-reliability-v1`
  named a prerequisite for removing the region cap: within-region alpha
  percentiles need a common cross-region scale first. That scale already
  exists — `ExpandingBucketCalibration.expected()` returns a region-specific
  calibrated expected benchmark excess in pp, the same quantity every rung
  already ranks on — so `calibration_comparability` measures whether it is
  comparable IN PRACTICE rather than inventing a second normalization. On
  this sample the US-minus-KR shrinkage gap is -0.002: the comparability
  artefact the prerequisite warned about (thinner history pulling one
  region's alpha harder toward zero) is not present.
- A COMPARABLE SCALE CAN STILL DISAGREE ON THE LEVEL, AND THAT IS A
  DIFFERENT FINDING. Shrinkage and effective-date counts are nearly
  identical between regions, but the calibrated alpha LEVEL is not: the pool
  assigns Korean names a mean of 0.645pp against 0.041pp for American names,
  roughly 16x. An unconstrained ranking is not exploiting a scale artefact
  when it piles into the higher-level region — it is reading the
  calibration's own belief about opportunity, correctly.
- OPENING THE CAP REPRODUCES THE EARLIER CAP-LIFTED MEASUREMENT
  INDEPENDENTLY. `alpha-reliability-v1`'s own diagnostic measured KR 640 /
  US 82 held name-dates with the caps notionally lifted, from a
  within-block reading that valued nothing. This study's actual replayed,
  valued path lands at KR 639 / US 85 — two independently built
  measurements of "what the ranking wants without the region cap" agree to
  within one name-date, and only the second one is a realised return.
- REMOVING THE CAP MADE THE POINT ESTIMATE WORSE, AND THE INTERVAL DOES NOT
  SEPARATE. Net excess moves from -0.684pp (3-cap control) to -2.314pp
  (quota opened), paired difference -1.630pp, 95% CI [-4.462pp, +0.961pp]
  over 155 blocks. CONTAINS ZERO — reported as such, not folded into "no
  result" and not read as a refutation either, since the interval does not
  clear zero in the other direction.
- THE GROSS GAP IS ARITHMETIC SELECTION, NOT A VOLATILITY TILT. Control:
  +0.315pp arithmetic / +0.405pp compounding. Quota opened: -1.351pp
  arithmetic / +0.260pp compounding. The KR-concentrated book is choosing
  names that underperform their own region's benchmark by more than the
  diversified book's names do — the loss is in WHICH names, not in a
  changed risk profile.
- THIS STUDY QUANTIFIES THE TRADE, IT DOES NOT ADJUDICATE IT. The region cap
  costing turnover (`alpha-reliability-v1`) and the region cap providing
  diversification value the ranking's own opinion would forgo (this study)
  are BOTH true on this sample and are not in tension: a constraint can be a
  large source of turnover and still pay for itself. Neither this result nor
  any prior one in this line makes a claim about which effect dominates
  going forward.
- NO PERMUTATION NULL WAS RUN. Only `maxNamesPerRegion` moved; `targetNames`,
  `maxNamesPerSector`, breadth and every cost assumption are unchanged from
  `alpha_reliability.CONTROL`, called directly rather than reimplemented.

## Entry-selection-separation invariants (v2.17)

- ENTRY STATE DECIDES WHO TODAY, NOT HOW FAST. `score = decision / (risk *
  100) * state` bakes the entry-state multiplier straight into the
  SELECTION score, so a WATCH name's score is halved before it is ever
  ranked against an ACCUMULATE name's. Nothing in `baseline_weights`
  applies the multiplier again once a name is selected. Production
  therefore does the opposite of the pre-registration's separation
  ("alpha decides the held set, entry state decides how fast the target
  weight is approached") on both ends.
- THE AXIS IS THE CONTINUOUS THROTTLE ONLY. A multiplier of 0.0 (EVENT_RISK,
  AVOID, a non-POSITIVE research view, insufficient data) stays a full
  eligibility exclusion on BOTH rungs, for incumbents and new entries
  alike. Whether an incumbent should be forced out on a blocking state at
  all is a separate claim about EXITS the pre-registration explicitly
  reserved for its own test.
- A BUG THE DIAGNOSTIC CAUGHT IS RECORDED, NOT SILENTLY FIXED.
  `select_portfolio_by_scores` builds and mutates its OWN internal row
  copies, never the caller's `scored` list — so a `selected` flag read off
  `scored`'s own rows is always stale or absent. The first sealed run of
  `entry_state_incidence` read exactly that flag and reported `heldByState:
  {}` and `namesTheDiscountLetIntoTheBook: 0` on every block, both
  mechanically impossible. The fix reads the held set from `retained`/
  `added` on the decision, the same fields every other diagnostic in this
  line already uses.
- THIS AXIS HAS BITE, MEASURED BEFORE THE LADDER. The discount changes
  which names are held on 130 of 155 control rebalances (83.87%) — 258
  names it kept out that alpha-only selection would hold, 258 it let in
  that alpha-only would drop (necessarily equal: both rungs hold the same
  COUNT per block under the same caps).
- AVERAGE CASH NEARLY DOUBLED, AND THAT IS THE MECHANISM, NOT A SIDE
  EFFECT. Moving the throttle to weight lifts average cash held from
  30.417% to 56.002%: alpha-only selection holds far more of the WATCH/
  WAIT_FOR_PULLBACK names the discount used to exclude, and 68.7% of held
  name-dates on the new rung then carry a throttled weight, withholding a
  mean of 66.7% of target when throttled. A materially smaller invested
  fraction mechanically shrinks realised volatility and drawdown, and also
  moves the region-weighted matched benchmark itself.
- THE GROSS GAP IS NOT MERELY A VOLATILITY EFFECT. Arithmetic stock
  selection rises 0.315pp -> 2.017pp while compounding is roughly flat
  (0.405pp -> 0.289pp): on this sample the names the discount used to
  exclude realised BETTER excess returns than the ones it favoured, not
  merely lower volatility from holding more cash. That is a claim about
  this historical sample's realised outcomes, not a mechanism this study
  tested or a prediction about future samples.
- THE PAIRED INTERVAL CONTAINS ZERO. Net excess moves from -0.684pp
  (control) to +1.385pp (entry-at-weight), paired difference +2.069pp, 95%
  CI [-1.881pp, +6.061pp] over 155 blocks. The point estimate is large and
  favourable, but the interval does not clear zero, and no permutation
  null was run — reported as CONTAINS ZERO, not as a result.
- THIS WAS THE FOURTH AND LAST STUDY `alpha-reliability-v1` pre-registered.
  `alpha_reliability.CONTROL` is called directly rather than reimplemented,
  exactly as in every prior study in this line.

## Alpha-risk-separation diagnostic-extension invariants (v2.18)

- A DIAGNOSTIC ADDED AFTER A LADDER IS SCORED MAY ONLY READ IT, AND HERE THAT
  IS PROVEN MECHANICALLY RATHER THAN ASSERTED. The frozen
  `alpha-risk-separation-v1` rungs are re-run by CALLING that study's own
  functions, and the runner recomputes all TEN of its scored blocks and
  compares them canonically against the checked-in
  `docs/results/alpha-risk-separation-report.json`. A mismatch raises
  `FROZEN_LADDER_MOVED` and refuses to publish. The runner's `_guard` also
  refuses the frozen report's own path as an output, so it cannot be
  overwritten by mistake, and the workflow runs `git diff --exit-code` on it.
- RE-RUNNING A SETTLED LADDER IS HOW A PROGRAMME TALKS ITSELF INTO A RESULT.
  The study this extends is scored, merged and CONTAINS ZERO; the correct
  response to a request to redo it was to establish that it already exists,
  say so, and extend only what it never measured.
- `risk_dominance` COMPARES HELD AGAINST REJECTED WITHIN A RUNG, WHICH CANNOT
  SAY WHAT REMOVING THE DENOMINATOR BOUGHT. Only the names the two rungs
  DISAGREE about can answer that. `set_difference_profiles` pairs the rungs
  by date and profiles `selectedByChallengerNotControl` against
  `selectedByControlNotChallenger`; paired WITHIN a rebalance, so it carries
  no market-timing term, and factor facts are read from ONE source (the
  control's own rows) so a profile gap cannot come from the source.
- THE DENOMINATOR WAS NOT HOLDING BACK HIGH-MOMENTUM OR HIGH-QUALITY NAMES,
  AND THAT REFRAMES THE AXIS. On the 233 name-dates the rungs disagree about,
  momentum separates them by +0.687 and quality by +0.626 — well under a
  percentile point — while `lowvol` moves -9.725 and realised downside
  volatility +5.157pp. Alpha percentile is 98.163 against 98.039. Removing
  the denominator did not buy different alpha; it bought THE SAME ALPHA MORE
  RISKILY, which is what a risk denominator is supposed to prevent.
- AND THOSE NAMES DID NOT GO ON TO DO BETTER. Challenger-only names realised
  0.587% mean forward block excess at a 46.78% win rate against
  control-only's 0.799% and 51.93% — a difference of -0.212pp. Descriptive
  only: a difference of two group means, not a paired test, with no
  multiplicity correction, read off the same priced cross-section
  `replacement_anatomy` reads, and entering no score, ranking or rule.
- A STACK THAT MOVES TWO AXES IS REPORTED OUTSIDE THE LADDER AND NAMED AS
  SUCH. k=6 persistence plus the denominator removal lands at -0.231pp
  against the control's -0.684pp (+0.454pp, 95% CI [-4.235, +5.570]). It is
  attributable to NEITHER axis alone and is never paired into the primary
  ladder — the same status `signal-persistence-v1` gave its own stacked path.
- A DIAGNOSTIC THAT PRINTS `n/a` FOR EVERY ROW LOOKS LIKE A MEASUREMENT.
  The observational region/entry table was first written against guessed key
  names (`rebalancesWhereRegionCapBoundPct`) that `region_cap_binding` does
  not emit. Read the function's actual output keys before formatting them;
  a silently blank row is worse than a missing section.

## Lowvol-alpha-separation invariants (v2.19)

- A SEALED LEDGER'S SCHEMA IS MEASURED BEFORE A STUDY IS DESIGNED, NOT
  ASSUMED FROM THE PRODUCTION CODE THAT WROTE IT. Production blends sleeve
  Z-SCORES; the replay-v16 ledger stores each sleeve's PERCENTILE
  (`factorPercentiles`) and `rawAlpha` as a single scalar, never the
  z-scores, so production's exact alpha arithmetic is UNREACHABLE from
  sealed inputs. Both rungs therefore blend percentiles, which keeps the
  axis between them exactly one thing but makes the harness's own control
  a DIFFERENT path from production's, at a measured rank correlation of
  0.906 to the published `alphaPercentile` over 1,430 cross-sections. That
  gap is published, not hidden, per `switch-hurdle-v1`'s rule that a ladder
  carries its own control.
- A CONSTRUCTION CHOICE MADE BEFORE A RUNG IS VALUED IS NOT THE SAME AS ONE
  MADE AFTER. `evidenceCoverage` shrinks production's SIGNED `rawAlpha`
  toward zero; a percentile blend is strictly positive, so multiplying it
  by coverage uncentred would push every weakly-covered name DOWN
  regardless of sign. Centring the blend at 50 before applying coverage was
  selected on fidelity to the PUBLISHED ranking (0.929 centred vs 0.746
  uncentred, measured against the sealed ledger's own `alphaPercentile`),
  before any rung's performance was computed.
- REMOVING A SLEEVE IS NOT A MISSING-DATA EVENT, AND THE DIFFERENCE COSTS
  ABOUT 14 POINTS OF COVERAGE IF CONFUSED. `longterm.factorCoverage =
  sleevesPresent / len(FACTOR_WEIGHTS)` and source quality is averaged over
  the sleeves a name HAS; naively deleting `lowvol` would drop coverage
  from 4/4 to 3/4 and source quality 0.80 -> 0.733 for a name that lost
  nothing but a factor DEFINITION. This study never recomputes coverage —
  it reads the sealed value, identical on both rungs — so the penalty
  cannot arise. Zero of 399,547 name-dates lack a three-factor sleeve, so
  no eligibility diverges between the rungs either.
- THE CHALLENGER'S WEIGHTS ARE DERIVED FROM PRODUCTION'S, NEVER FITTED.
  `THREE_FACTOR` is computed from `longterm.FACTOR_WEIGHTS` at import by
  renormalizing over the three non-`lowvol` sleeves, preserving the
  30:25:25 ratio exactly (momentum/value = 1.2 on both rungs). No weight
  sweep was performed.
- THE HYPOTHESIS'S OWN PREDICTED SHIFT HAPPENED, AND THE PORTFOLIO LOST
  ANYWAY. On the 336 name-dates the two rungs disagree about, the
  challenger's picks carry momentum +7.875, value +13.870, downside
  volatility +7.536pp and `lowvol` -25.411 against the control's, and held
  Technology exposure rose 4.570% -> 7.890% (+3.32pp) while Consumer
  Staples fell 14.130% -> 10.940% (-3.19pp). The higher-momentum,
  higher-volatility, more-technology book the hypothesis predicted is
  exactly what got built.
- AND IT WAS BUILT ON A WORSE CALIBRATED READING. The challenger-only
  names' own calibrated expected excess is 0.268pp against the
  control-only names' 0.565pp, at an alpha percentile of 92.461 against
  94.696 — LOWER on both counts, not higher. Net excess moves -1.647pp ->
  -4.556pp, arithmetic stock selection -0.355pp -> -2.565pp: the loss is
  concentrated in SELECTION, not compounding (0.190pp -> -0.282pp), so it
  is not a volatility-drag story either. Paired difference -2.909pp, 95%
  CI [-9.194pp, +3.417pp] — CONTAINS ZERO, verdict
  `DIRECTIONAL_BUT_NOT_STATISTICALLY_SEPARATED`, but the point estimate is
  unfavourable on every reading measured.
- THE NEWLY SELECTED NAMES DID NOT REALISE BETTER FORWARD RETURNS EITHER.
  Challenger-only mean forward block excess is -0.076% (47.02% win rate)
  against control-only's -0.077% (49.40%) — indistinguishable, and if
  anything the challenger's win rate is lower. Descriptive only, fitted to
  nothing, but it corroborates rather than complicates the calibrated
  reading.
- THREE STACKS THAT MOVE MORE THAN ONE AXIS ALL LAND WORSE, AND NONE MAY BE
  READ AS THE SLEEVE'S EFFECT. `+persistence k=6` (2 axes): -3.528pp,
  MDD -41.035%. `+entry-at-weight` (2 axes): -2.259pp. `+both` (3 axes):
  -1.878pp. Each is attributable to none of its own axes individually, and
  none is paired into the primary ladder — the same status
  `signal-persistence-v1` gave its own stacked path.
- THE COMBINED READING IS CASE D: KEEP THE SLEEVE. Of the five cases
  specified before the result (a favourable separation; no effect alone
  but a better persistence stack; no effect alone but a better
  entry-separation stack; both other axes strong while this one adds
  nothing; and a selection improvement bought with worse drawdown), what
  was measured matches none of the favourable ones — net excess worsens,
  arithmetic selection worsens, MDD worsens (-27.651% -> -31.733%), and
  every stacked path is worse still. Research attention belongs on signal
  persistence, role separation, and the calibration bucket RESOLUTION
  `alpha-reliability-v1` named as the bottleneck — not on the alpha's
  factor composition.
- NO PERMUTATION NULL WAS RUN, so no rung in this ladder may be described
  as beating random, and a CI containing zero on an already-unfavourable
  point estimate is reported as CONTAINS ZERO, never softened toward "no
  effect either way."

## Alpha-calibration-resolution invariants (v2.20)

- A SCORE CANNOT BE REORDERED BY REORDERING ROWS, ONLY BY MOVING ITS VALUE.
  `select_portfolio_by_scores` always re-sorts candidates by `(-score,
  ticker)` before selecting, so handing it candidate rows in a new order
  changes nothing — the re-sort erases any ordering not carried in the
  SCORE FIELD itself. `rescue_scores` therefore never permutes rows: it
  keeps the exact score VALUE Control computed at a given sort position and
  reassigns which candidate's identity carries it. `select_portfolio_by_
  scores` and `_select_scored` run completely unmodified as a result, and
  this is proved mechanically rather than argued: `assert_noop_blocks_
  match_control` checks, on every one of 155 real blocks, that an EMPTY
  swap list reproduces Control's held set exactly — a mathematical
  necessity of the construction, not a tolerance-based check.
- GROUPING BY ELIGIBLE ROWS ONLY MAKES A REGION-CAP CASCADE STRUCTURALLY
  IMPOSSIBLE, AND THIS IS MEASURED RATHER THAN ASSUMED. A group is
  `(region, calibrationBucket)` among `eligible=True` rows, so every
  member shares one region by construction — a swap can change which
  SECTOR occupies a position but never how many eligible names from a
  region reached the ordering. Measured: of 862 changed name-dates, 0 of
  the swap-bearing rebalances showed a changed regional shape in the held
  set; 853 (99.0%) are the direct reorder itself and 9 (1.0%) are a
  sector-cap cascade.
- THIS STUDY CARRIES NONE OF `lowvol-alpha-separation-v1`'S HARNESS-
  FIDELITY GAP, BECAUSE IT NEVER RECONSTRUCTS THE INPUT. `alphaPercentile`,
  `calibrationBucket` and `expectedGrossBenchmarkExcessPct` are read
  DIRECTLY from `alpha_reliability.reliability_scores`'s own sealed output,
  the exact fields production computed. There is no percentile rebuild and
  therefore no fidelity gap to publish.
- THE DISCARDED ORDINAL INFORMATION IS MEASURED BEFORE THE LADDER IS READ,
  AND IT IS NOT INFORMATIVE. Within a `(date, region, calibrationBucket)`
  group, pairwise concordance (higher `alphaPercentile` realised the better
  forward excess) is 49.06% over 9,375 pairs, mean within-group Spearman is
  0.006, and a parameter-free median-rank half split reads +0.075pp — all
  three at essentially CHANCE. This is measured on the CONTROL path's own
  scored candidates and enters no score, ranking or rule.
- THE POINT ESTIMATE IS UNFAVOURABLE AND THE INTERVAL CONTAINS ZERO — BOTH
  ARE PUBLISHED, NEITHER IS SOFTENED. Net excess moves -0.684pp (control) to
  -1.865pp (ordinal rescue), paired difference -1.181pp, 95% CI [-6.207pp,
  +3.955pp] over 155 blocks. Arithmetic stock selection moves +0.315pp to
  -0.402pp and compounding +0.405pp to -0.158pp — both terms unfavourable,
  not a volatility-drag story. Verdict:
  `DIRECTIONAL_BUT_NOT_STATISTICALLY_SEPARATED`.
- A THREE-CASE PRE-REGISTRATION DID NOT NAME A FOURTH CASE, AND THE FOURTH
  CASE IS NOT STRETCHED TO FIT ONE OF THE THREE. The design specified
  favourable-and-separated (A), doesn't-help (B), and directionally-good-
  but-uncertain (C) before the result was seen. A negative point estimate
  that does not statistically separate is not "directionally good," so it
  is routed to B on point-estimate sign rather than reported as C — which
  would have misrepresented an unfavourable reading as a promising one.
  Verdict: **CASE B — ordinal rescue does not help**, corroborated
  independently by Stage B's near-chance concordance.
- THE BOTTLENECK NAMED BY `alpha-reliability-v1` WAS RESOLUTION; THIS STUDY
  TESTED IT DIRECTLY AND FOUND DISCRIMINATION INSTEAD. The two-occupied-
  bucket calibration compresses production's ordering hard (3,028 eligible
  name-dates into 3 levels, the largest holding 53.70%), and there is real
  ordinal spread inside a level (mean range 2.979 points) for a rescue to
  use — but Stage B's near-chance concordance shows that spread does not
  order forward outcomes. A finer or continuous calibration would not be
  expected to recover value that Stage B shows is not there.
- NO BUCKET-COUNT SWEEP, NO PERCENTILE-COEFFICIENT OPTIMISATION, NO SPLINE
  OR ISOTONIC FIT, NO THRESHOLD SEARCH. One binary mechanistic test,
  specified before the result: does restoring discarded ordinal information
  inside a tied group help, yes or no. It does not, and re-specifying the
  calibration until it does would be the exact failure this repository's
  discipline exists to prevent.
- NO PERMUTATION NULL WAS RUN, so no rung here may be described as beating
  random, and this remains one historical sample after ten studies on this
  ledger, with no multiplicity correction.

## Four-factor-signal-attribution-audit invariants (v2.21)

- AN ATTRIBUTION AUDIT IS NOT A SELECTOR STUDY, AND NOTHING IN IT VALUES A
  PORTFOLIO. `kelly_portfolio.select_portfolio_by_scores` and
  `replay_valuation` are never called by
  `four_factor_signal_attribution_audit.py`; it reads `factorPercentiles`,
  `alphaPercentile`, `rawAlpha`, `alpha` and matured `excessReturn` directly
  from the sealed signals/outcomes and computes cross-sectional Spearman
  correlations, reusing `historical_outcomes.horizon_frame` and
  `portfolio_validation._nw_summary` exactly as production's own
  `alpha_diagnostics` already uses them.
- SUBFACTOR PROVENANCE IS MEASURED BY SCANNING THE SEALED LEDGER, NOT
  ASSUMED FROM THE PRODUCTION CODE THAT WROTE IT — the same discipline
  `lowvol-alpha-separation-v1` established one level up. Every raw
  subfactor input for momentum, value and quality is absent from the
  sealed signal record (`mom121`, `mom6`, `earningsYield`,
  `fwdEarningsYield`, `bookYield`, `fcfYield`, `roe`, `opMargin`,
  `profitMargin`, `earningsGrowth`, `debtToEquity`) — only each sleeve's
  already-blended percentile survives. Lowvol's one raw input (`vol252`)
  is the sole exception, via `risk.vol252Pct`. `mom20Pct`/`mom60Pct`/
  `relMomentum` exist on the record but are a DIFFERENT short-horizon
  feature (the entry/overheat layer) and are never substituted for
  production's actual momentum sleeve inputs.
- REGION POOLING COMBINES TWO ALREADY-COMPUTED SUMMARIES, NEVER TWO
  CROSS-SECTIONS. A naive concatenation of KR's and US's date-indexed IC
  series into one `kelly_portfolio._newey_west_stats` call was considered
  and rejected: `_sampling_step_days` filters non-positive gaps when
  estimating the HAC lag, so a same-calendar-date cross-region pair would
  be silently dropped from the LAG estimate while both rows still count in
  the VARIANCE term. `pool_region_summaries` instead applies fixed-effect
  inverse-variance weighting to the two regions' own independently-HAC-
  estimated mean/SE pairs — a standard, off-the-shelf combination method,
  not one invented for this study — and a region whose IC series has ZERO
  sampling variance is treated as infinitely informative, not as
  unusable: an early implementation read a falsy `se == 0.0` as "no
  usable estimate" and a regression test now pins the fix.
- A SILENT MISSING FIELD DROPPED EVERY POOLED SECONDARY READING TO
  `n/a`, WITH NO ERROR RAISED. `portfolio_validation._nw_summary` reports
  a 95% CI but never an `se` key; `sleeve_ic_table` recovered `se` from
  the CI half-width inline, but `incremental_ic_table` and
  `quartile_spread_table` returned `_nw_summary`'s dict as-is. The first
  full sealed run published real by-region incremental IC and quartile
  spread numbers next to a pooled column that was `None` for all four
  sleeves, because `pool_region_summaries` reads a missing `se` as "this
  region has no usable estimate." Centralized into `_with_se_and_p`,
  applied identically everywhere a HAC summary is pooled, with a
  regression test that pools a single region's own summary and checks
  the pooled mean reproduces it.
- NONE OF THE FOUR PRIMARY HYPOTHESES CLEARS RAW SIGNIFICANCE, LET ALONE
  HOLM CORRECTION. Pooled-within-region 126D Rank IC: momentum -0.0015
  (raw p=0.9155), value -0.0056 (p=0.7373), quality -0.0223 (p=0.0805),
  lowvol +0.0286 (p=0.1464); every 95% CI contains zero and every
  Holm-adjusted p exceeds 0.32. Measured on 399,547 sealed signals /
  396,358 matured outcomes.
- KR-ONLY LOWVOL IS THE ONE REGIONAL READING THAT CLEARS ZERO ON ITS OWN
  (+0.0511, 95% CI [+0.0047, +0.0974], raw p=0.031) — AND IT IS STILL NOT
  THE PRIMARY CLAIM. Section 8 forbids substituting a regional reading
  for the pooled one; pooled against US's -0.0225 it does not survive,
  and it is published as a secondary, descriptive number, not a finding.
- REDUNDANCY IS LOW ACROSS ALL SIX SLEEVE PAIRS (|ρ| <= 0.17 POOLED), SO
  THE COMPOSITE'S WEAKNESS IS NOT A DUPLICATION STORY. The four sleeves
  select largely different names; they are just not, individually or
  jointly, selecting names whose forward benchmark-relative return the
  percentile orders. No sleeve's own quintile bucket is monotone
  (best score 0.50 of 1.0; lowvol scores 0.00, the wrong direction).
- EVERY SLEEVE CLASSIFIES AS REGION-SIGN-UNSTABLE, A MORE SPECIFIC
  FINDING THAN "WEAK." `classify_sleeve` checks KR/US and first/second-half
  sign agreement before magnitude, and all four sleeves disagree in sign
  between KR and US at the primary horizon — not merely a small pooled
  point estimate, but a sign that does not generalize across the two
  regions the composite is applied to identically.
- KOREAN VALUE/QUALITY COVERAGE IS A REAL GAP THIS AUDIT CANNOT SEPARATE
  FROM A TRUE WEAK SIGNAL, AND IS PUBLISHED BESIDE THE IC RATHER THAN
  AVERAGED AWAY. Missing rate: KR value 55.45%, KR quality 53.99%, against
  US value 20.11%, US quality 0.96% — consistent with this repository's
  own PIT-fundamentals invariants (DART serves from 2015; Korean
  value/quality dark for the replay's first two years). A weak Korean
  value/quality IC is `NO EVIDENCE DUE TO COVERAGE`-adjacent, never
  reported as `EVIDENCE OF NO EFFECT`.
- CLASSIFICATION IS DESCRIPTIVE AND NEVER RECOMMENDS DELETING A SLEEVE ON
  ITS OWN. The four pre-specified cases (independent / redundant /
  potentially harmful / unstable) describe the measured evidence; removing
  a sleeve needs an independent sample, which this ledger — used by ten
  prior studies — is not.
- NO FACTOR WEIGHT WAS CHANGED, NO COMBINATION WAS SEARCHED, AND NO NEW
  ALPHA FORMULA WAS BUILT FROM THIS SAMPLE. This result reads closest to
  Case C (weak across the board) with a Case D (region-sign instability
  plus a genuine Korean coverage gap) overlay, and the proposed next step
  is new information sources evaluated as a separate CHALLENGER, not a
  same-sample reweighting of these four sleeves.

## Fundamental-acceleration-discovery invariants (v2.22)

- A DISCOVERY STUDY MEASURES COMPUTABILITY AND DISTINCTNESS BEFORE IT ASKS
  ABOUT RETURN, AND CASE D IS A REAL, PUBLISHABLE ANSWER. Fundamental
  acceleration (`accel_f = f(current filing) - f(previous filing)` for
  roe/operatingMargin/profitMargin/earningsGrowth, sector-neutral z,
  minimum 3 of 4 present) cleared both gates a same-sample re-tune would
  have been tempted to fail on purpose: overall coverage 64.95% (>= the
  pre-registered 0.60 floor) and |Spearman(accelerationPercentile,
  qualityPercentile)| = 0.118 (well under the 0.70 redundancy ceiling — this
  is genuinely distinct information from the existing Quality level
  factor, not a relabelling of it). The standalone and incremental pooled
  126D Rank IC point estimates are near zero regardless (-0.0026, -0.0009,
  both 95% CI containing zero, both Holm p = 1.0 of a 2-hypothesis family)
  and the sign disagrees KR-vs-US and first-half-vs-second-half. `CASE D —
  NO_DISCOVERY_EVIDENCE`, per the pre-registered routing that a negative
  point estimate is never stretched into "directionally promising" (Case
  E) regardless of how the coverage/orthogonality gates read.
- THE CURRENT FILING IS THE LATEST REPORT PERIOD VISIBLE, NEVER THE LATEST
  AVAILABILITY DATE. `resolve_filing_pair` filters to
  `availableFrom <= asOf` and THEN orders by fiscal period, because a
  severely delayed filing can in principle arrive out of period order; both
  legs' PIT visibility is asserted explicitly in code, exactly as
  `contraction_holds` is asserted for the confidence weight in
  `alpha_reliability.py`. Consecutiveness is a strict one-step adjacency in
  each region's own fixed report-code cadence (US Q1→Q2→Q3→FY; KR DART's
  11013→11012→11014→11011); a skipped period is `NOT_CONSECUTIVE` and
  contributes no reading — deliberately conservative, never adaptive
  per-company cadence detection, and any resulting coverage cost is
  measured rather than engineered around (9,725 of 399,547 name-dates).
- AMENDMENT RESOLUTION IS A DEFENSIVE-CORRECTNESS REQUIREMENT THAT CHANGES
  NO REAL NUMBER ON THIS LEDGER, AND BOTH FACTS ARE PUBLISHED TOGETHER.
  `resolve_filing_pair` groups visible filings by report period and keeps
  the max-`availableFrom` record per group before chronological ordering.
  Measured directly against the real sealed ledger: zero duplicate
  `(ticker, reportPeriod)` filings exist in either region (0 of 4,302 KR
  keys, 0 of 33,832 US keys), so this logic is exercised only by synthetic
  fixtures in the test suite — a correctness guarantee for filings this
  ledger does not currently contain, not a tuning knob.
- OVERALL COVERAGE PASSING HIDES A REGIONAL SPLIT WIDE ENOUGH TO BE ITS OWN
  FINDING, AND IT IS REPORTED RATHER THAN AVERAGED AWAY. KR data-sufficient
  ratio is 13.76% against US's 81.79% — a sixth as complete — because KR is
  24.7% of the sample by row count, so the US-dominated pooled ratio (64.95%)
  clears the 0.60 floor while the region that needed the floor most does
  not. Consistent with the PIT-fundamentals invariants' own finding that
  DART serves from 2015 while the replay starts 2013: by time half,
  coverage rises from 58.13% (first half) to 70.65% (second half) as more
  consecutive Korean filing pairs accumulate.
- THE SAME CONSTRUCTION SERVES BOTH VALIDATION LEGS, NEVER TWO
  IMPLEMENTATIONS OF "ACCELERATION". `pipeline/fundamental_acceleration.py`
  is the single shared PIT filing-pair resolver; the historical discovery
  study (`fundamental_acceleration_discovery.py`, scored against
  `replay-v16`) and prospective sealing
  (`fundamental_acceleration_seal.py`, appended immutably before an
  outcome can be known) both call it directly rather than each
  re-deriving "current" and "previous" filing on their own.
- A SEALED RECORD IS KEYED BY `(sealVersion, ticker, asOfDate)` AND A
  COLLIDING KEY REFUSES THE WHOLE BATCH RATHER THAN MERGING OR OVERWRITING
  IT. `fundamental_acceleration_seal.append_seal` raises rather than
  silently reseals a key that already exists, and every sealed row carries
  its own SHA-256 digest over its canonical content so a downstream reader
  can verify a row was not altered after sealing without trusting file
  mtime or git history alone. This mirrors the ledger's own append-only
  signal discipline (date x region x ticker x model version) one level
  down, at the record-digest level.
- THE PROSPECTIVE SEALING WORKFLOW SHIPS `workflow_dispatch`-ONLY,
  DELIBERATELY, BECAUSE ITS WIRING HAS NOT BEEN EXERCISED AGAINST REAL
  SECRETS. `Seal fundamental acceleration signal` builds `data/site-data
  .json` fresh, extracts the live candidate universe from its own
  `longTerm.regions.*.researchTable`
  (`scripts/extract_acceleration_candidates.py`), derives live PIT
  fundamentals from the raw collected shards via the SAME
  `scripts/build_pit_fundamentals.py` the sealed replay uses (never a
  second derivation path), and seals. `PROSPECTIVE_START_DATE` is fixed by
  whichever run a human first triggers after this PR merges; converting the
  workflow to a schedule is a follow-up decision, not made here.
- A DIAGNOSTIC THAT IS NEVER SCORED STILL RESPECTS THE SAME SECTOR
  EXEMPTION THE SCORED FACTOR DOES. `debt_acceleration_diagnostic` masks
  Financials/Utilities/Real Estate/Holding names' `debtToEquity`
  acceleration to unmeasured, exactly as production's own leverage penalty
  masks them (`lev.where(~lev_exempt)` in `longterm.score_cross_section`),
  never includes them at a neutral zero. 297,790 non-exempt observations
  measured, 17,617 exempt-sector observations masked; `debtToEquity`
  acceleration is never in the composite regardless.
- THE HISTORICAL DISCOVERY RUN IS DETERMINISTIC AND THE SEALED LEDGER IS
  UNCHANGED, BOTH VERIFIED MECHANICALLY, NOT ASSERTED. Two full runs
  against the real sealed `replay-v16` ledger (399,547 signals, 396,358
  outcomes, 38,134 PIT filings across 904 tickers) produced byte-identical
  JSON and Markdown reports, and the runner itself raises
  `SEALED_LEDGER_CHANGED` if the ledger's own content digest differs
  before and after — it did not, on either run.
- NO PORTFOLIO WAS SELECTED OR VALUED, NO WEIGHT WAS TUNED IN RESPONSE TO
  THIS RESULT, AND THE NEXT STEP NAMED IS A NEW SOURCE, NOT A RE-TUNE.
  `kelly_portfolio.select_portfolio_by_scores` and `replay_valuation` are
  never called anywhere in this study. Per the design's own case routing,
  Case D points at evaluating a new information source as a separate
  CHALLENGER rather than re-tuning this composite's fields, weights, or
  windows — and the KR/US and first-half/second-half sign instability is
  named as its own finding rather than folded into a bare "no effect".

## Alpha-information-inventory invariants (v2.23)

- A DATA INVENTORY IS NOT A STUDY AND DOES NOT SCORE A LADDER.
  `alpha-information-inventory-v1` measures no relationship to future
  returns, computes no IC, runs no backtest, and touches no `FACTOR_WEIGHTS`,
  CHAMPION, selector, Kelly parameter, entry rule, region cap, or macro
  multiplier. Its only output is a map of what information exists, what is
  used, what is collected but unused, and what is acquirable — graded on
  economic rationale, PIT correctness, coverage, and cost, never on a
  measured return.
- "THE 31 FEATURES" IS `regional_alpha_features.feature_manifest()`'S
  ELIGIBLE ROW COUNT, A RESEARCH-ONLY, NEVER-EXECUTED CHALLENGER MATRIX —
  NOT PRODUCTION AND NOT THE OPPORTUNITY RADAR. No literal "31" constant
  exists anywhere in the codebase; it is reproducible by counting
  (21 price + 5 fundamental level + 4 fundamental-acceleration delta + 1
  region-specific: US leadership breadth, KR market cap), identically in
  both regions. Production's `FACTOR_WEIGHTS` has 13 raw sub-inputs across
  4 sleeves; the Opportunity radar has 28 (`FEATURE_COLUMNS`). Three
  different constructs; conflating any two of them mis-describes what has
  actually been tried.
- "USED IN ALPHA SCORING" HAS TWO DIFFERENT ANSWERS DEPENDING ON WHICH BUILD
  IS ASKED ABOUT, AND BOTH MUST BE STATED. The live daily site build's
  value/quality/growth sleeve reads `fundamentals.py` (Yahoo current-snapshot,
  explicitly no PIT history, per `longterm.py:35-39`'s own design note).
  The PIT-safe DART/Finnhub pipelines feed the identical
  `score_cross_section` function, but only inside `historical_replay.py`'s
  backtest/validation path. A study that reads "the model uses PIT
  fundamentals" from the replay code and assumes the live build does the
  same would be wrong about what ships today.
- THE OPPORTUNITY MODEL ALREADY BLENDED VOLUME SHOCK, MOMENTUM
  ACCELERATION, AND FUNDAMENTAL PERCENTILE VIA ML, AND IT WAS REJECTED
  TWICE. Trained on `replay-v14` across 7 model families including a real
  executed LightGBM run (not merely wired up), the winning rung's own
  pooled test-period decile table is **negatively monotonic**
  (`[+2.83,+0.88,-1.31,-6.35,-1.75,+6.79,+2.31,+2.81,-2.36,-0.87]` —
  decile 10 underperforms decile 1) and failed to beat a plain logistic
  baseline. Both the opportunity and warning radars are `accepted: false`.
  A next study proposing this same information combination needs a stated,
  concrete construction difference (e.g. magnitude-preserving volume shock
  instead of percentile-only, or a hand-specified interaction instead of an
  ML blend) to not be a relabelled redo.
- A REJECTED MODEL CAN ALSO BE STRANDED, AND THE TWO FACTS ARE INDEPENDENT.
  The committed Opportunity model spec is trained on `replayVersion:
  replay-v14`; production has since moved to `replay-v16`, and
  `build.py`'s generation-match check silently discards the stale spec
  regardless of its own acceptance verdict. Fixing the generation mismatch
  alone would not resurrect a model that already failed acceptance; both
  causes of today's rule-based fallback are recorded separately, not
  merged into one explanation.
- `regional-alpha-model-v1` IS FULLY CODED, PRE-REGISTERED, AND HAS NEVER
  BEEN RUN. It needs no new data collection — the 31-feature matrix is
  already built and PIT-safe. Finishing it is unfinished prior work, not a
  new hypothesis, and per this repository's own discipline takes priority
  over starting anything new that would need a data build.
- THE ECOS FETCH LAYER IS CONFIRMED 100% DEAD CODE, AND ONE OF ITS NINE
  CONFIGURED SERIES IS A REAL, UNFIXED BUG. Grep across every `pipeline/*.py`
  file for "ecos" finds only a boolean diagnostic flag; no HTTP call to
  `ecos.bok.or.kr` exists anywhere. `config.json`'s `ecos.KR` block also
  points `KTB_3Y` and `CorpBond_3Y` at the identical series ID `817Y002`,
  which multiple independent secondary sources describe as a single broad
  table distinguished only by an `item_code` this config schema has no
  field for — even a working fetch function built against today's config
  could not currently tell these two series apart. Flagged, not fixed, per
  this inventory's own no-repair-work-here scope.
- KOREAN INVESTOR-BEHAVIOR DATA (FLOW, SHORT-SELLING, LARGE-HOLDINGS
  DISCLOSURE) IS REAL AND OFFICIAL, AND THE BLOCKER IS ACCESS, NOT
  EXISTENCE. Per-stock investor-type net trading and short-sale statistics
  are published free on KRX's own public data portal but sit behind a
  different endpoint than this repo's currently-subscribed Open API key
  reaches, and that portal was already found unreachable from this
  project's sandbox by `scripts/probe_krx_index_membership.py`. Large-
  holdings (5%-rule) disclosure is the one exception: it is served by
  DART, the same vendor, same key, and same receipt-date PIT mechanism
  `dart_fundamentals.py` already implements — the lowest-effort new data
  build identified anywhere in this inventory.
- KOREAN SHORT-SELLING SPANS AT LEAST THREE REGULATORY REGIMES WITHIN THE
  REPLAY WINDOW, AND A FACTOR BUILT ON IT MUST CARRY THAT FORWARD RATHER
  THAN AVERAGE IT AWAY. Full-market bans ran approximately 2020-03 to
  2021-05 and 2023-11-05 to 2025-03-31 (the second paired with a structural
  reporting overhaul), during which the variable is either illegal-to-
  observe or measured under a materially different microstructure.
- `fxBeta26w`/`absFxBeta26w`'S EXCLUSION IS RECONFIRMED OPEN, AND GOT MORE
  CERTAIN, NOT LESS, SINCE THE EARLIER DESIGN DOC. The pre-registration
  (`kr-alpha-research-design-v1.md`) had said FX-beta's PIT semantics
  "pass, cleanly," before the feature matrix was actually built; the built
  matrix (`regional_alpha_features.py:88`) excludes it as
  `FX_PUBLICATION_TIME_UNRESOLVED`. FRED's `DEXKOUS` (already fetched,
  display-only) is a noon-New-York rate, confirmed mismatched to a same-day
  KRX-close regression; ECOS `731Y001` is a better-timed candidate,
  contingent on the same unbuilt fetch layer above and an unverified live
  timing check against the KRX close.
- THE SEC DOMAIN-WIDE BLOCK ALREADY ESTABLISHED IN THE VENDOR REFUSAL
  INVARIANTS ALSO BLOCKS FORM 4 AND 8-K ACCESS, AND NO FREE ALTERNATE
  VENDOR RE-SERVES EITHER THE WAY FINNHUB RE-SERVES 10-Q/10-K FUNDAMENTALS.
  Both are free, official, sufficiently historical (Form 4 structured
  extraction from 2006; 8-K since 2001/2004) — the blocker is this
  project's current CI egress, not the data's existence, exactly the
  pattern already measured for SEC's other bulk products.
- ANALYST ESTIMATE REVISIONS ARE NOT FREELY BUILDABLE IN EITHER REGION, AND
  THIS CORROBORATES RATHER THAN OVERTURNS A PRIOR SUSPICION. Finnhub's free
  tier reads as a current-snapshot or shallow-rolling-window product (two
  independently surfaced sources disagree on retention depth, neither
  describing a stable 2013-2026 panel), and Finnhub sells a *separate*
  paid tier specifically for historical estimates. Korea's FnGuide/FnSpace
  equivalent was already found ToS-blocked in `challenger-2-signal-source
  -feasibility-v1.md`, not re-tested here.
- A US DIVIDEND-CHANGE SIGNAL COULD BE BUILT TODAY WITH ZERO NEW
  COLLECTION. `finnhub_fundamentals.py`'s `UNIT_ANCHORS[PER_SHARE]` already
  includes `CommonStockDividendsPerShareDeclared`, sealed into the US PIT
  store since replay-v15 — the raw field for a corporate-payout-policy
  signal is already inside the canonical store; only a derived
  period-over-period field is missing, the same shape of gap as the raw
  debt/asset/equity levels already collected but not exposed standalone.
- `sentiment.py` IS PRICE/BREADTH-DERIVED, NOT NEWS OR SEARCH SENTIMENT,
  AND ITS MEASUREMENT-ABSENCE DEFECT (v2.11) IS CONFIRMED FIXED. No news
  article, headline, or search-trend data is read anywhere in the module;
  it blends 200D/50D breadth, %-Bull share, and median momentum with
  region-specific market gauges. The denominator is now restricted to
  measurable names, absence returns `(None, 0)` not `(0.0, 0)`, and the
  measured-name counts are published alongside the share.
- A REGIME×BUCKET PORTFOLIO-OUTCOME INTERACTION DIAGNOSTIC EXISTS AND IS
  NEVER CONSUMED; A STOCK-LEVEL FEATURE×REGIME INTERACTION HAS NEVER BEEN
  CODED ANYWHERE. `historical_calibration.regime_interaction()`'s
  `activate` flag is read by nothing downstream (confirmed by grep across
  `kelly_portfolio.py`, `validate.py`, `build.py`). Momentum acceleration ×
  financial conditions and volume shock × quality × liquidity regime are
  both confirmed genuinely absent, not merely untested by omission.
- THE DECISION GATE IS CASE B — DATA BUILD REQUIRED — AND THE CHEAPEST NEXT
  ACTION NEEDS NO DATA BUILD AT ALL. Real, `HIGHLY_DISTINCT` candidate axes
  exist (KR investor flow, KR macro, KR large-holdings, accounting-quality
  ratios, US dividend-change), but none is Grade A end-to-end. Running and
  publishing `regional-alpha-model-v1` — already coded, already PIT-safe —
  is unfinished prior work and outranks starting any new data build.

## Lint gate invariants (v2.11)

- The enabled rule set reports ZERO findings on `main`. A rule is turned on in the
  same change that fixes its existing instances; a gate with a standing backlog is a
  warning nobody reads and then a gate somebody switches off.
- The set is defect-finding, not style-enforcing. The first full run over this
  repository reported 455 findings, and almost all of them were opinions this code
  deliberately disagrees with. `ruff.toml` argues each rule that is on; a rule that
  needs arguing with on every pull request does not belong there.
- Lint runs BEFORE the suite in `Tests`, because it catches a class the suite
  structurally cannot: a name no test reaches, an import two modules disagree about, a
  value computed and then dropped. Both of the defects the first run found —
  `sentiment`'s discarded coverage count and two whole-ledger index passes in
  `portfolio_replay` that nothing read — were invisible to 1,345 passing tests.

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
- An absence is an ANSWER and is recorded. DART returns 013 both for a filing a
  company never made and for one whose period has not closed, and a run that
  forgets either re-asks it forever: the first two real runs spent 950 of every
  1,500 calls on filings that do not exist, and the work list did not shrink by
  one of them. An absence settles only once the filing's legal deadline plus a
  grace period has passed — permanent for a 2016 quarter, still open for a 2026
  one — and settled absences count as done, because a backfill that reports them
  as pending can never reach 100%.
- Absences live beside the shards, never inside them. `FundamentalStore` would
  read an absence row as a filing with no accounts.
- Collection is append-only and identified by ticker x fiscal year x report code. A
  restatement arrives as its own filing with its own receipt date rather than
  overwriting the number that was actually visible at the time.
- DART serves from 2015 and the replay starts 2013, so Korean value and quality are
  dark for the first two years however complete the collection is. That gap is
  reported per year, not averaged away, and it is not a reason to move the replay
  start: it would trade two years of price-sleeve evidence for uniformity.

- A trailing twelve months is a ROLLFORWARD, never an annualisation. Multiplying
  a nine-month figure by 4/3 invents a quarter nobody reported:
  `TTM(Y,Q3) = FY(Y-1) - cum(Y-1,Q3) + cum(Y,Q3)`. When either prior-year filing
  is missing the answer is None — a factor that is absent costs coverage, and a
  factor that is invented costs the whole claim.
- Income and cash flow are read by DIFFERENT rules, established from the data and
  not from memory. The income statement states the quarter in `thstrm_amount` and
  the year-to-date in `thstrm_add_amount` (measured present on ~100% of quarterly
  IS rows, 0% of annual ones). The cash flow statement states ONE column at every
  report and it is the report period's cumulative figure — settled by value over
  84 companies: Q3/FY median 0.68 against the 0.75 cumulative implies, while
  (Q1+H1+Q3)/FY of 1.31 rules out standalone quarters, which would give 0.75.
  Reading a Q3 operating cash flow as three months and annualising it inflates
  free cash flow fourfold with nothing raising an error.
- Balance-sheet items are levels and are never rolled forward or averaged.
- A ratio whose denominator must be positive to mean anything returns None when
  it is not. A ROE on negative equity is a number with the wrong sign that ranks
  a distressed company as a quality name.
- Per-share numerators, not yields, are what a filing may state: a yield needs a
  price and the price moves every day after the filing. `pit_data.
  derive_price_relative` divides them by the close on the replay date.
- Share counts are a SECOND collection pass and net of treasury stock. Without
  them the entire value sleeve is dark, and computing per-share figures on the
  issued total understates every company with a buyback behind it by exactly the
  amount that made the buyback worth doing. Quality coverage and value coverage
  are reported separately, so "we collected fundamentals" is never read as "the
  value sleeve works".
- A missing quarterly share count may be CARRIED FORWARD from the nearest earlier
  filing, never a later one. Measured against the real store: Q1/Q3 filings
  answered 013 at a rising rate from 2022 (0% in 2015-21 to 77-78% by 2025) while
  half-year and annual filings stayed at 0% — Korean quarterly reports may omit
  restating 주식총수 현황 when it has not changed, not a coverage gap. Which each
  row got — `AS_FILED` or `CARRIED_FORWARD` — is published on `derivation.
  sharesBasis` and tallied in the coverage report, the same discipline as the TTM
  basis.

## Replay determinism invariants (v2.10)

- A backtest that is not reproducible is not evidence. Two runs from one
  commit over one set of replay dates published CAGRs of 19.47% and 16.77%
  and drawdowns of -13.35% and -9.85%, and nothing in either report said they
  disagreed. Both looked plausible alone; only side by side was either wrong.
  So the check is not optional reporting — a divergence blocks the report.
- The invariant is PREFIX STABILITY, never immutability. The ledger must grow
  daily, so "nothing changed" would fail every night and get switched off.
  What must hold is that everything already published is still there,
  unchanged, and new work only appends after it.
- Fingerprint what the schedule is ANCHORED on, not just what it is indexed
  by. `shared_block_dates` chains each block off the previous block's end and
  takes the later of the two selectors' ends, so an end date can move while
  its entry date does not — and that alone shifts every later block. Entry
  dates alone would have called the 2026-09-05 divergence stable.
- A tiny input change is not a tiny output change when selection is greedy.
  250 added rows out of 120,371 (0.2%) turned over 84% of the evaluation
  dates, because one added date re-anchors every block after it. Never reason
  about the size of a result change from the size of the input change.
- When two runs disagree, find the variable in the INPUTS before theorising
  about the model. The benchmark's own CAGR moving is what ruled out a model
  change; diffing the ledger commits then named three tickers. Existing rows
  being byte-identical is as much of a finding as the added ones — it is what
  says the recomputation was deterministic and the UNIVERSE was not.
- Floating-point drift is not the finding, and mistaking it for one hides the
  real one. 2,386 of 2,470 outcome rows "changed" between the two runs, all at
  the sixth decimal. Rank a diff by magnitude before reading meaning into its
  row count.
- The baseline has to be read before it is overwritten. The ledger records
  outcomes but never recorded the calendar they were graded on, which is why
  two runs could disagree with nothing to compare; the previous report is now
  read at the top of `audit_portfolio.py`, before the write.

## Vendor refusal invariants (v2.9)

- A vendor's refusal is attributed only after OUR side of the request has been
  ruled out. The SEC conclusion — "the Actions IP pool is blocked site-wide" —
  was first reached while sending a header set that does not meet SEC's stated
  policy, so it was an assumption; the isolation run then measured it and the
  assumption turned out to be RIGHT. Ruling our side out is not a way of
  overturning a conclusion, it is how one stops being a guess.
- What settled it was byte identity, not the status code. Four header sets
  across two hosts returned the same 403 with the same body length every time
  (4,819B on data.sec.gov, 1,925B on www.sec.gov). A refusal that does not
  change when the request changes is not reading the request. That is the
  reading a status code alone cannot support, and it is why the probe records
  body size per variant.
- Corroboration must be INDEPENDENT of the suspect. `institutional_13f`
  falling back to cache on the same day was cited as evidence for the IP
  reading, and it sends the same headers — so it corroborated the shared
  suspect rather than the conclusion.
- An authenticated service refusing a KEY is a third thing again, distinct
  from both a blocked address and a wrong path. KRX's Open API answered every
  endpoint with `{"respMsg":"Unauthorized Key","respCode":"401"}` — structured
  JSON in the service's own protocol, which establishes that the base and the
  paths are right (a wrong path answers 404, not this) and that the key was
  read rather than missing. It gets its own verdict; rolled into "the source
  could not answer" it would retire a source that was never actually asked.
- A status code is not the variable that produced it. FMP answered
  `limit=4` with HTTP 200 and real statements, and `limit=400` with HTTP 402,
  on the same endpoint with the same key in the same minute. Only `limit`
  differed, so only `limit` could be blamed — yet the 402 alone had already
  been written up as "the free tier excludes statements", a claim about the
  PLAN made from a run that had also, in its own log, been served. When two
  calls to one endpoint disagree, the difference between them is the finding;
  look for it before attributing the refusal to the vendor's product.
- A cap is a number to measure, not a tier to infer. `find_limit_cap()` walks
  the request upward until the first refusal and stops there, because FMP's
  caps are monotonic and buying rungs above a refusal only spends quota. The
  answer is "served up to N", which is actionable; "the free tier is
  insufficient" is not.
- A vendor renaming a field is indistinguishable from the field being absent,
  and reads as the WORSE finding. FMP's `/api/v3` shipped a misspelt
  `fillingDate` for years and `/stable` corrected it to `filingDate`; a probe
  that knew only the old spelling would have counted zero filing dates on a
  response carrying one in every row, and reported "no point-in-time" about
  the source that has it. Field names get candidate lists for the same reason
  endpoint paths do — and which name answered is recorded, not assumed.
- A name missing from an old cross-section is two different findings that
  need opposite fixes: it was LISTED LATER (the dated cross-section is right
  and the fixed universe list is the anachronism), or the source never
  carries it at all (wrong market, wrong code, a real gap). KRX held 51 of
  the replay's 68 KR names at 2013 and all 68 today. Pooled, that reads as a
  25% hole in the source; split by first-seen date it reads as a source
  behaving exactly as a point-in-time source must. `universe_reach()` reports
  `missingListedLater` and `missingNeverHeld` separately and never sums them.
- Access granted per service is measured per service. The KRX approval opened
  `sto/stk_bydd_trd` and left `sto/ksq_bydd_trd`, `sto/stk_isu_base_info` and
  `idx/kosdaq_dd_trd` answering the same `Unauthorized API Call` as before.
  "KRX works now" and "KRX still refuses" were both true in one run, so the
  verdict is per endpoint; whether a still-refused service MATTERS is a
  separate question answered from the universe (all 68 KR names are `.KS`,
  so the KOSDAQ refusal does not touch this one).
- Isolating one variable FIXES the others, which makes them untested rather
  than ruled out. The header run held the runner constant and so held the
  egress address constant; one address refused eight times is one observation
  repeated eight times, and reading it as "the pool is blocked" mistook the
  constant for a control. A vendor that once served us and no longer does
  (SEC did, on 2026-08-15, `sourceMode: LIVE_SEC`) has a variable nobody has
  moved yet — find it before concluding.
- A fan-out only buys the axis it was meant to buy if the axis actually
  varied. Parallel runners usually get distinct addresses and sometimes do
  not, so the summary counts DISTINCT addresses first and refuses a verdict
  below two. "Every address refused" from one address is the same error the
  fan-out exists to correct.
- A refusal body is read and KEPT, never read and dropped. The FMP probe
  fetched the 402 body and then replaced it with "non-JSON response" in an
  `except ValueError`, and that empty status became "FMP dropped statements
  from the free tier" — a third conclusion inferred from a bare status code
  with the vendor's own explanation discarded. FMP's 402 names the plan the
  endpoint needs; that sentence was the finding.
- A credential that fails on the endpoints you want is not evidence about the
  credential until it has been tried on one you already expect to work. A dead
  key and a plan that excludes an endpoint produce the same failure on that
  endpoint and have completely different fixes, so the probe asks a liveness
  endpoint first and reports the two apart.
- A vendor's own error text is REPORTED, never paraphrased into our own label.
  The KRX probe hardcoded "Unauthorized Key" for any 401 while the service was
  actually answering `Unauthorized API Call` — two different statements
  collapsed into one, and they point in opposite directions: the first says the
  key is not recognised, the second that it IS and the call is not authorised
  for it. Only the second means a subscription rather than a bad key, and the
  label was hiding exactly the change that showed the new key had taken.
- How a credential is PRESENTED is a variable too, not something to infer from
  an error string. KRX's "Unauthorized Key" was read as proof the header name
  was right, on the reasoning that a missing key would say "missing" — an
  inference about someone else's wording. The transport is now resolved by
  trying header and query forms and reporting which was served.
- Isolating a refusal means one variable at a time, in ONE run: the shipped
  request is included as the baseline, everything else is held fixed (host,
  endpoint, pacing, runner, minute), and only the header set moves. Without
  the baseline in the same run a later success is attributable to the day
  rather than to the change.
- A block page is not data whatever status it wears. SEC serves its refusals
  with 403 and sometimes with 200, so the body decides, never the status code.
  And a request that asks for `gzip` must decompress before it judges: reading
  compressed bytes as text turns a served response into an apparent refusal.

## Macro vintage invariants (v2.9)

- A panel column that is COMPUTED from other columns has no vendor series id, so
  no vintage source can ever answer for it by name. Subtracting the vintaged
  names from the panel's columns therefore finds it missing forever, and the
  aggregate `pit_status` is capped below PIT_EXACT however many series are opted
  in — the `vintageMacro` gate was unreachable by construction, not by anything
  in the data. A derived column is neither exempted nor fetched: it is
  RECOMPUTED from its vintaged inputs, and it counts as vintaged only when
  EVERY input is. One vintaged input and one revised one is a revised column.
- The derivation lives in one place (`pit_data.DERIVED_MACRO_COLUMNS` /
  `derive_macro_columns`) and the fetch site imports it. Two copies of the
  arithmetic is how a replay silently stops replaying the production panel.
- Opting a series into `macroVintageSeries` is measured before it is done.
  `vintage_column` keeps only the prints published by the as-of date, so a
  series whose release history begins after the replay start returns an EMPTY
  column on early replay dates: that column goes dark for years while
  `pit_status` UPGRADES to PIT_EXACT and the gate turns green. Trading a
  revised number for no number and receiving a better label for it is the
  failure this measurement exists to prevent. Row counts and a first-observation
  date cannot see it; only reconstructing the column on the replay's own start
  date can, and that is what `probe_alfred_macro_vintages` runs — with the
  replay's own `vintage_column`, not a re-implementation.
- The panel verdict is all-or-nothing because PIT_EXACT is. One usable series
  among many is not partial credit.
- MEASURED 2026-09-04 and it settles the gate: 10 of the 28 panel columns have
  NO ALFRED vintages at all — `series/vintagedates` refuses them with "The
  series does not exist in ALFRED but may exist in FRED". FRED serves the
  numbers and keeps no pre-revision history of them. So `vintageMacro` is
  unreachable at EVERY start date, not merely at 2013-01-01, and moving the
  replay start buys nothing: the first run read those series' `realtime_start`
  values (2014, 2019, 2023) as first vintages when they are the dates FRED
  began carrying the series, and the "move the start and six recover" reading
  built on that is withdrawn. Never vintaged is an ANSWER and gets its own
  verdict; filed as a fetch failure it looks like something a retry fixes.
- Both integrity gates are therefore permanently closed as defined, for
  different reasons, and neither opens by collecting more. The only remaining
  moves are to change what the macro panel contains (a model change) or what
  the gate requires, and both belong to a human.
- A vintage that carries MORE of a span than today's series does is a series
  redefined under its own id, not a healthy column — measured on TGA
  (`WTREGEN`), 1,408 periods served to 2013 against 524 today. Conditioning a
  replay on it would use a definition that no longer exists, so it is flagged
  rather than published as coverage or dropped in silence.
- A vintage source is asked for the FIRST VINTAGE DATE, never for the whole
  release matrix. ALFRED caps a request at 2,000 vintage dates and 100,000
  rows, and a daily series blows both: the first run lost DGS10, DGS2, DFF,
  DFII10, T10YIE and RRPONTSYD to the first cap and silently clipped NFCI and
  ANFCI at the second. `series/vintagedates` answers the verdict, and a request
  pinned to `realtime_start = realtime_end = T` answers what the column served
  on T — both are small, neither can be capped, and the second is the vendor's
  own reconstruction rather than a second implementation of ours.

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

## Promotion gate invariants (v2.9)

- `universe_ready` requires `constituentCoveragePct` AND `membershipCoveragePct`
  at exactly 100.0. On the free vendors available that is not a bar more
  collection reaches: the US half is at 99.80% membership and 83.02% pricing
  because the panel cannot price 17% of the name-dates the membership file
  describes, and Korean membership, if it were built, would stop near 40%
  unvouched because only 34.55% of departed KOSPI names can be priced at all
  (measured 2026-08-30). The gate is unreachable, and that fact is published
  rather than worked around.
- Lowering the bar is not the answer, and neither is leaving it undescribed. If
  there is an answer it is to BOUND the bias rather than demand it be zero:
  whether the paired selector difference keeps its sign when the missing
  name-dates are assigned their worst plausible outcome. Until that is measured,
  no promotion claim is made in either direction, and the favourable reading is
  not taken on the strength of the gap being unmeasured.
- A challenger separating from the champion is not a promotion trigger and is
  never reported as one. On `replay-v6` the paired difference cleared zero for
  the first time (-0.684pp, 95% CI [-1.127, -0.225] over 132 shared blocks)
  while `promotionEligible` stayed false — both facts are published together or
  neither is.

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
- Selectors are compared on ONE precomputed common KRX/NYSE session schedule, with
  a 21-session stride for the primary horizon. Data availability and actual portfolio
  end dates MUST NOT move anchors. Missing matured blocks block headline publication;
  unmatured blocks are pending, and empty portfolios are disclosed KRW cash windows.
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
