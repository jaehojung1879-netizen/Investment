# Alpha inference calibration v4 — methodology diagnosis and frozen protocol

Status: **PROTOCOL FROZEN (pre-merge revision 2), NOT EXECUTED.** Synthetic/statistical methodology only.
No historical Alpha outcome, label, return, score, prediction, Alpha result
report or `signal-history` artifact was read to produce anything here. v1, v2
and v3 remain closed substantive FAILs and are not modified. This is step 1 of
the sequence (inference methodology → original-XBRL value validation → repaired
KR snapshot freeze → accounting semantic contract → v5 preregistration → one
authorized historical execution). It authorizes no v5 execution.

## Revision history and chronology (read this first)

- **Revision 1** (commits `60fc002`, `0300bf2`, `39e0a9c`, `5caa0d9`): diagnosis,
  calendar-time attribution method, protocol, implementation, workflow.
- **Revision 2** (this update, before merge; no formal run exists): adds an explicit
  Monte Carlo decision rule (§6b) and corrects the chronology below. It changes no
  DGP, depth, seed, statistic partition, critical value, threshold, attribution rule
  or replicate count; a semantic diff of the spec against revision 1 confirms this.
- **Accurate chronology.** The calendar-time attribution method was derived from the
  structural decomposition of overlapping returns. Development-only exact-Gaussian
  coverage diagnostics, *including the exact coverage of the v4 calendar-time
  interval*, were then computed **before the revision-1 protocol freeze commit** and
  are fully disclosed in `docs/results/alpha-inference-calibration-v4-development-diagnostics.json`.
  The v4 exact-coverage numbers were therefore seen before freeze. No free parameter,
  threshold, DGP, depth, statistic partition, critical value or tuning parameter was
  selected by optimizing those development coverage results; the method has none,
  and the only choice they could have informed is the replicate count, through the
  Monte Carlo operating characteristic, which does not depend on any method's
  coverage. An earlier draft of this document, the PR body and `AGENTS.md` said the
  method was "fixed before any v4 coverage was computed"; that was too strong and is
  corrected here.

Machine-readable protocol: `research_specs/alpha-inference-calibration-v4.json`.
Analytic diagnostics (DEVELOPMENT_ONLY):
`docs/results/alpha-inference-calibration-v4-development-diagnostics.json`,
reproduced by `scripts/diagnose_alpha_inference_calibration_v3.py`.

## 1. Verified starting state

- `main` = `faff543fd0516e734d14d680cecf0f12b8850fd6` (merge of PR #166, v3), unchanged since.
- v3 run `36483954346`, workflow `Synthetic alpha inference calibration v3`, on
  `faff543`, event `workflow_dispatch`, conclusion `failure`. The job log shows the
  simulation completed and printed `contract: ALPHA_INFERENCE_CALIBRATION_V3`,
  `primaryStatus: FAIL`, `cells: 16`, `specSha256:
  e8340ac3541e8981983996b8a66b54030757c2cd0419aab2140f8e3fe41d1d59`, then exited 2 by
  design; the upload step succeeded. Artifact `alpha-inference-calibration-v3`,
  id `10998470853`, 3,736 bytes, zip digest
  `sha256:c9ee787aaa34d0102e0cef13505195b1b40d19b5bbfb74f1998e27c6fb2abe14`.
- The artifact blob host (`*.blob.core.windows.net`) is refused by this
  environment's egress (the same block recorded in v2.29), so the zip itself was
  not downloadable here. v3 is fully seeded and deterministic, so its per-cell
  values below come from re-running the unmodified v3 runner at `faff543` with the
  pinned `requirements.txt` (numpy 2.3.1, scipy 1.16.0). The reproduction
  printed the same status, cell count and spec hash as the log. **This is a
  reproduction of the recorded result for diagnosis, not a new v3 run, and no
  v3 file was touched.**

## 2. Reconstructed history

| | v1 (run `36472769120`) | v2 (run `36476033206`) | v3 (run `36483954346`) |
|---|---|---|---|
| Interval | non-circular moving-block bootstrap, percentile | circular moving-block bootstrap, basic (centered-error) | Shao/Lobato self-normalized (SN), Bartlett fixed-b `b=1`, `U1` 97.5% = 66.57 |
| Series it was applied to | weekly signal-date statistic | same | same |
| Tuning | block 10 (H21), 52 (H126) | same | none |
| What changed from predecessor | — | endpoint start asymmetry removed; centered error distribution | no block length; normalizer randomness built into the pivot |
| Result | 16/16 primary cells FAIL; H126/312 coverage 86.7–92.3% | 16/16 FAIL; H126/312 `dateMean` 87.3% | 3/16 FAIL, only H126/312, only `dateMean`/`selectedMean` |
| Cause (this diagnosis) | variance of the mean estimated from ~6 block sums and used as if known, plus non-circular edge under-weighting | the same variance-estimation defect; the edge repair was real but second-order (analytic ≈88.9% at H126/312) | finite-sample SN distortion when the dependence span is 1/12 of the sample (exact 95.8% vs nominal 97.5%), read through 300-replicate Monte Carlo noise against a 95% floor |

### 2.1 Exact v3 failure cells (coverage, nominal 97.5%, floor 95%)

| DGP | H126 / 312 weeks | failing statistic(s) |
|---|---|---|
| IID_SHARED | `selectedMean` 0.9467 (`dateMean` 0.9500 passes at the floor) | MATERIAL_UNDERCOVERAGE |
| WEAK_SERIAL | `dateMean` 0.9367, `selectedMean` 0.9400 | MATERIAL_UNDERCOVERAGE |
| PERSISTENT_SHARED_HEAVY | `dateMean` 0.9433, `selectedMean` 0.9433 | MATERIAL_UNDERCOVERAGE |

PERSISTENT_SERIAL / H126 / 312 passed (`dateMean` 0.9600). Every H21 cell and
every H126/624 cell passed. No directional-false-positive, undefined-frequency or
Monte Carlo-precision failure occurred. Across all 80 statistic-cells `rankIC`,
`pairedMseImprovement` and `selectedMinusUniverse` ranged 0.953–0.997.

## 3. Mathematical diagnosis

### 3.1 The dependence is mechanical and its size is known

Signals are weekly (5 sessions); a target sums `H` sessions. Two signal dates `k`
weeks apart share `max(0, H − 5k)` sessions. H21 overlaps `ceil(21/5) = 5` signal
dates; H126 overlaps **26**. For the universe mean the analytic lag-1
autocorrelation at H126 is 0.960 **even in `IID_SHARED`** (0.990 under
PERSISTENT_SHARED_HEAVY); the long-run variance is 25–27× the per-date variance.
The v1/v2 reports' reading that failure "under IID" rules out a dependence
explanation is wrong: `IID_SHARED` has iid *daily* shocks, not iid *signal-date*
observations.

| Horizon | calendar weeks | non-overlapping windows `n·5/H` | 26-wk blocks | 52-wk blocks | 104-wk blocks | v4 calendar-time observations |
|---|---:|---:|---:|---:|---:|---:|
| H21 | 78 | 18.6 | — | (10-wk: 7) | — | 82 |
| H21 | 156 | 37.1 | — | (10-wk: 15) | — | 160 |
| H126 | 312 | **12.4** | 12 | **6** | 3 | 337 |
| H126 | 624 | 24.8 | 24 | 12 | 6 | 649 |

### 3.2 Why only `dateMean` and `selectedMean` failed

Under the v1–v3 null, every predictor and selection score is redrawn
independently each week and is independent of returns. Then for
`rankIC`, `pairedMseImprovement` and `selectedMinusUniverse` the statistic at date
`t` has conditional mean zero given all returns and all other dates' scores, so
the signal-date series is a **martingale-difference sequence with zero
autocorrelation at every lag, whatever the overlap**. Those three statistics
were never exposed to the mechanism that broke the other two; their "stability"
is a property of the null, not of the method. `dateMean` carries the shared
factor through the full overlap. `selectedMean` equals `dateMean` plus a
selection term that is (by the same argument) white, so it inherits `dateMean`'s
dependence with slightly diluted strength — which is why the two fail together.

Candidates the task listed, checked: skewness and heavy tails — **no** (all v3
DGPs are Gaussian; the exact analysis below is Gaussian and reproduces the
distortion); selection-induced nonlinearity — **no** (selection is independent
and frozen; it adds white noise); bootstrap edge behaviour — **v1 only**;
studentization instability — **absent in v2, present by design in v3**;
long-run-variance estimation error with a small number of effective
independent blocks, entering through a random denominator — **yes, the
mechanism for all three versions**.

### 3.3 v1/v2: variance estimated from six blocks and treated as known

A percentile or basic block-bootstrap interval is, to first order,
`θ̂ ± z·sqrt(V*)` with `V*` the bootstrap variance of the mean. At H126/312 with
52-week blocks `V*` is built from six block sums: it is biased downward (it
misses the cross-block covariance an overlapping series has at every boundary)
and has roughly five degrees of freedom, yet the interval uses normal-like
quantiles as if `V*` were the variance. Treating the circular-block `V*` as a
quadratic form gives an analytic normal-quantile coverage of **0.889** at
H126/312 and **0.927** at H126/624 for every inherited DGP (observed v2 `dateMean`:
0.873 / 0.877 at 312). Circular blocks (v2) fixed an edge asymmetry that was not
the binding problem. A longer block reduces bias and removes degrees of freedom;
no block length fixes both at 312 weeks.

### 3.4 v3: SN is correct, but its finite-sample normalizer is biased at 12 windows

Implementation audit of `pipeline/alpha_inference_calibration_v3.py`:

- estimator: `W_n = n⁻² Σ_t (S_t − (t/n) S_n)²` and pivot `n(x̄−θ)²/W_n` are exactly
  Lobato (2001) / Shao (2010) for a scalar mean; centering uses the full-sample
  mean in both the pivot and the bridge, consistently;
- interval inversion is exact for a scalar (the pivot is quadratic in `θ`);
- the critical value is right: the exact iid coverage of `x̄ ± sqrt(66.57·W_n/n)`
  is 0.97497 at `n = 200` and 0.97499 at `n = 1000`;
- cross-sectional dependence is retained (statistics are per-date aggregates);
  selection is frozen at the signal date; there is no bootstrap to re-centre;
- zero normalizer → undefined (correct); a *near-zero* positive normalizer would
  produce a falsely narrow interval — not triggered by the synthetic designs, but
  v4 adds a relative tolerance.

The implementation is correct. The method's `U1` limit assumes the partial-sum
process is Brownian at the scale of the sample. With a 26-date overlap the partial
sums are smooth below ~26 weeks, which lowers the Brownian-bridge normalizer by a
term of order `(dependence span)/n`. Exactly, at H126/312: `E[W_n]` is 0.872 of its
limit while the numerator's variance is 0.973 of its limit (0.934 / 0.987 at
624), so the pivot is inflated about 11.6%. Imhof's (1961) exact distribution of
the resulting quadratic form gives the **exact Gaussian coverage of v3's
`dateMean` interval: 0.957–0.958 at H126/312, 0.967 at H126/624, 0.956–0.970 at
H21** across the inherited DGPs (validated against brute-force Monte Carlo in the
tests). Two-sided rejection is therefore ~4.2% against a 2.5% budget at H126/312.

### 3.5 What the v3 verdict does and does not say

The exact coverage (≈95.8%) sits **above** the frozen 95% floor, and the observed
93.7–95.0% are that distortion plus Monte Carlo noise: at 300 replicates the
coverage SE is ≈1.2pp, and a cell whose true coverage is 0.958 reads below 0.95
with probability **0.198**. With eight correlated H126/312 mean-type cells a
FAIL was likely. This is recorded because it is true, and it does **not** reopen
v3: v3's frozen rule produced FAIL and v3 stays FAIL. Nor is v3's construction
"really fine": a method that spends 70% more than its two-sided error budget at
the one depth where H126 is hardest is a defensible reason to replace it on its
own. The observation that matters for the future is about the rule: at 300
replicates it cannot distinguish a 1–2pp distortion from noise in either
direction.

## 4. Literature assessment

Bibliographic details are from the cited primary sources as known to this
review; the full texts were not re-read in this session and DOIs should be
checked before citation elsewhere.

| Method | Assumptions / regime | Finite-sample weakness here | Overlapping H21/H126 | Nonlinear selected statistics | Complexity | Changes estimand? | Verdict |
|---|---|---|---|---|---|---|---|
| Moving-block bootstrap — Künsch (1989) *Ann. Stat.* 17:1217; Liu & Singh (1992) | stationary, mixing; `b→∞`, `b/n→0` | ~6 blocks at H126/312; percentile ignores variance-estimate error; edge under-weighting | needs `b ≫ 26` → too few blocks | valid in principle | low | no | **rejected (v1)** |
| Circular block bootstrap — Politis & Romano (1992) | as MBB | fixes edges only | same | same | low | no | **rejected (v2)** |
| Block choice — Hall, Horowitz & Jing (1995) *Biometrika* 82:561; Politis & White (2004) *Econ. Rev.* 23:53 (+ Patton, Politis & White 2009) | optimal `b ∝ n^{1/3}` for variance, different for distribution | data-driven `b` estimated from the same ~12 windows; any choice after v1–v3 would be a tuned sensitivity | — | — | medium | no | **rejected**: selection by the evaluated data is what the protocol forbids |
| Stationary bootstrap — Politis & Romano (1994) *JASA* 89:1303 | random geometric blocks | same effective-block count, extra variance from random lengths | same | same | low | no | rejected |
| Tapered block bootstrap — Paparoditis & Politis (2001) *Biometrika* 88:1105 | smooth taper | improves bias order, not the count of independent blocks | same | same | medium | no | rejected |
| Studentized block bootstrap — Götze & Künsch (1996) *Ann. Stat.* 24:1914 | nested block variance | second-order accuracy needs many blocks; nested variance from 6 blocks | poor at 312 | yes | high | no | rejected |
| Subsampling — Politis & Romano (1994) *Ann. Stat.* 22:2031; Politis, Romano & Wolf (1999) | `b→∞`, `b/n→0` | with ~12 windows there is no `b` satisfying both | infeasible at H126/312 | yes | medium | no | rejected |
| HAC (Newey & West 1987; Andrews 1991) with normal critical values | small-`b` asymptotics | known over-rejection with strong dependence; bandwidth ≥ 26 at `n = 312` | poor | via linearization | low | no | rejected |
| Hansen & Hodrick (1980) truncated kernel at the overlap | known MA(H−1) | not PSD; 25 autocovariances from 312 obs; Richardson & Stock (1989), Hodrick (1992), Valkanov (2003) document size distortion in long-horizon overlap | poor | — | low | no | rejected |
| Fixed-b HAC — Kiefer, Vogelsang & Bunzel (2000) *Econometrica* 68:695; Kiefer & Vogelsang (2002, 2005) | `b = M/n` fixed | smaller `b` is more powerful and more size-distorted (Sun, Phillips & Jin 2008 *Econometrica* 76:175); `b` becomes a tuning choice | usable | yes | low | no | subsumed by SN (`b=1` is the most size-robust Bartlett choice) |
| Self-normalization — Lobato (2001) *JASA* 96:1066; Shao (2010) *JRSS-B* 72:343; Shao (2015) *JASA* 110:1797 | FCLT for partial sums | distortion when dependence span is not ≪ n (§3.4) | acceptable only if the span is short | yes | low | no | **kept as the pivot** |
| Batch means / few-cluster t — Ibragimov & Müller (2010) *JBES* 28:453 | ≥2 nearly independent group estimates | adjacent contiguous groups share a 25-week boundary overlap at H126; making them independent discards ~25 weeks per boundary; group count is a choice | usable but wasteful | yes | low | no | rejected as primary; a defensible fallback if v4 fails |
| Strong-dependence corrections — Müller (2014) *JBES* 32:311; Lazarus, Lewis, Stock & Watson (2018) *JBES* 36:541 | local-to-unity / equal-weighted cosine | designed for persistence of unknown form; here the dominant dependence is of **known** form | usable | yes | medium–high | no | rejected: solves a harder problem than the one present |
| **Realization-time (calendar-time) attribution** — Jegadeesh & Titman (1993) *JF* 48:65; Fama (1998) *JFE* 49:283; the same logic as Hodrick's (1992) *RFS* 5:357 1B reverse regression and Britten-Jones, Neuberger & Nolte (2011) | statistic linear in returns with weights fixed at the signal date | ramp-up/ramp-down weeks are heteroskedastic (≤15% of observations at H126/312); remaining dependence is the return process's own | **removes the mechanical overlap exactly** | only for linear statistics | low | **no** — exact identity | **adopted** |

Imhof (1961) *Biometrika* 48:419 is used only as a diagnostic instrument.

## 5. The v4 method and why it is not a response chosen to make v3 pass

**One change.** v4 keeps v3's pivot, critical value and scalar-mean
self-normalization, and changes the series it is applied to. For a statistic that
is linear in forward returns with weights fixed at the signal date,

`Σ_t stat(t) = Σ_t Σ_i w(t,i) Σ_{s∈window(t)} r(s,i) = Σ_w D(w)`,
`D(w) = Σ_{s∈week w} Σ_i (Σ_{t active at s} w(t,i)) r(s,i)`,

so each realized shock is attributed to the **one calendar week in which it
occurs**, not to the 25–26 signal dates whose windows contain it. The point
estimate is the same number (a test proves the identity to 1e−10), so the
estimand and estimator are unchanged. The mean profile of `D` is the known
exposure `x(w)` (active cohort-sessions ÷ H), so the SN residual partial sums are
formed around `θ̂·x(w)`; with `x ≡ 1` the interval is bit-for-bit v3's (tested).

**Why this is a structural rationale.** The overlap is a design fact whose exact
form is known before any data exist; a generic long-run-variance estimator is
asked to rediscover it from ~12 windows. Attribution uses the knowledge instead
of estimating it, and leaves only the return process's own persistence to the
pivot: weekly lag-1 autocorrelation of the interior calendar series is 0.00 /
0.06 / 0.49 / 0.71 for the four inherited DGPs, against 0.96–0.99 for the
signal-date series at H126. It has no tuning parameter, so there is nothing to
select from v1–v3 sensitivities. It was derived from the overlap structure before
the v4 coverage diagnostics were run, but those diagnostics were computed before
the protocol was frozen (see the chronology at the top), so "fixed before any v4
coverage was seen" would be wrong.

**Honest analytic preview (DEVELOPMENT_ONLY, computed before freeze and disclosed).** Exact Gaussian `dateMean` coverage of the v4 interval under the four
inherited DGPs: H126/312 0.966–0.970 (v3: 0.957–0.958); H126/624 0.971–0.972;
H21/156 0.966–0.973; H21/78 0.957–0.972 — the lowest is PERSISTENT_SHARED_HEAVY
at H21/78 (0.9569, v3 0.9557), where the residual distortion is ordinary
short-sample SN distortion from genuine weekly persistence, not overlap. Under the
three-state rule of §6b that one cell has probability 0.265 of PASS, 0.735 of
INCONCLUSIVE and about 0 of FAIL at 2,000 replicates. **v4 can FAIL or be
INCONCLUSIVE.** Nothing was changed in response; the new DGPs (§6) have not been
analysed and may be harder.

### Statistic partition

- **Confirmatory** (gate PASS/FAIL): `dateMean`, `selectedMean`,
  `selectedMinusUniverse`, `pairedMseImprovement` (the `y²` terms cancel, so it is
  linear in `y` plus a forecast-only term attributed to the signal week), and
  `rankWeightedSpread` (return of a dollar-neutral portfolio weighted by centred
  ranks of the score).
- **Descriptive only**: Spearman `rankIC`. It ranks the forward target, so it
  cannot be attributed to realization weeks; with persistent predictors it
  inherits the full overlap that §3 identifies as the failure mechanism. It is
  reported with v3's interval and cannot pass or fail the protocol. It passed in
  v3 — the reclassification is structural, not a removal of a failing statistic.
- `rankWeightedSpread` is the decomposable, return-unit counterpart of a within-date
  ordering claim. It is **not** the same estimand as Spearman IC (not scale-free,
  sensitive to cross-sectional dispersion). The design review's v5 composite
  requires a positive lower bound on mean within-date rank correlation; whether v5
  replaces that with `rankWeightedSpread`, or keeps Spearman IC as descriptive, is
  a v5 design decision this protocol does not make.

## 6. Frozen v4 protocol (summary)

Changed from v3, each for a stated reason:

1. interval method (above);
2. statistic partition (above);
3. **two added DGPs, none removed**: `PERSISTENT_SERIAL_PERSISTENT_PREDICTORS`
   (weekly score AR 0.95) — because under v1–v3 the three "stable" statistics were
   martingale differences by construction and real scores persist; and
   `PERSISTENT_SHARED_HEAVY_TAILED_PERSISTENT_PREDICTORS` (Student-t, 4 df,
   unit variance, plus persistent scores) — the heaviest integer tail with the
   finite 2+δ moments the pivot's FCLT needs. Both make the test harder;
4. **replicates 300 → 2,000**, by a precision criterion: Monte Carlo 95% half-width
   at the 0.95 floor ≤ 1pp requires R ≥ 1,825. Under the v1–v3 point-estimate rule at
   300 a true-0.958 method failed a cell with probability 0.198. Revision 2 **retains**
   2,000 and does not raise it to force a classification: cells whose true coverage is
   within about one Monte Carlo half-width of a threshold are expected to return
   INCONCLUSIVE, and that is what 2,000 replicates can honestly resolve (§6b);
5. new seed `20261001`;
6. near-zero-normalizer tolerance (relative `1e−12`) so a vanishing but positive
   normalizer is undefined rather than falsely certain;
7. minimum confirmatory depth = the shallowest depth calibrated per horizon (H21:
   78 weeks, H126: 312). Shallower v5 calendars are
   `DATA_INSUFFICIENT_FOR_CONFIRMATORY_H{h}_INFERENCE`, never unlocked by another
   interval.

Unchanged: horizons and depths (78/156, 312/624), all four inherited DGPs' outcome
parameters, 60 names, 5-session step, 20% selection, forecast scale, 97.5%
claim-level interval (Bonferroni over two KR horizon claims), the 95% coverage
floor, 5% directional-FP ceiling, 5% undefined ceiling, 4pp Monte Carlo
half-width ceiling, `U1 = 66.57`, and the conjunctive rule: any confirmatory
statistic failing any tolerance in any cell is FAIL.

Statuses and their precedence are in §6b. The job exits 0 on every methodological
verdict (PASS, FAIL, INCONCLUSIVE, DATA_INSUFFICIENT) and 1 only on
`INFRASTRUCTURE_ERROR`, which is still written to the artifact.

## 6b. Monte Carlo decision rule (revision 2)

**Problem.** v1–v3 and revision 1 classified a cell from the simulated point
estimate (`coverage >= 0.95`). The simulation is stochastic, so that verdict hides
its own noise. Under that old rule at 2,000 replicates a method whose true coverage
is 0.945 reads PASS with probability 0.176, one at exactly 0.950 reads FAIL with
probability 0.473, and one at 0.958 still reads FAIL with probability 0.036 (0.198
at 300 replicates). The development operating characteristic
(`threeStateRuleOperatingCharacteristic`, and the retained
`acceptanceRuleOperatingCharacteristic` for the old rule) lists the numbers.

**Rule.** Every Monte Carlo-estimated probability gets exact one-sided
Clopper–Pearson bounds on its true value (scipy `beta.ppf`; integer counts; no
asymptotics) and is classified:

| metric | PASS | FAIL | else |
|---|---|---|---|
| coverage (floor 0.95) | lower bound (α=0.025) ≥ 0.95 | upper bound (α=0.05/360) < 0.95 | INCONCLUSIVE |
| positive false-positive rate (ceiling 0.05) | upper bound (α=0.025) ≤ 0.05 | lower bound (α=0.05/360) > 0.05 | INCONCLUSIVE |
| undefined frequency (ceiling 0.05) | upper bound (α=0.025) ≤ 0.05 | lower bound (α=0.05/360) > 0.05 | INCONCLUSIVE |

Coverage and false-positive rate are counted over replicates with a defined
interval, undefined frequency over all replicates. The 4pp half-width diagnostic is
kept as a usability guard: a metric too imprecise to be a calibration reading can
never PASS (INCONCLUSIVE, `MONTE_CARLO_PRECISION_INSUFFICIENT`) but can still FAIL.
Zero measured replicates is INCONCLUSIVE for coverage and false-positive rate and a
FAIL for the undefined-frequency metric of the same statistic.

**Two confidence concepts, kept apart.** The 97.5% level (Bonferroni over the two
KR horizon claims) is the *statistical interval* whose coverage is being measured.
The levels above govern only *Monte Carlo classification error*. They are unrelated
and neither is derived from the other.

**Multiplicity of the Monte Carlo decision.** PASS is an intersection of per-metric
claims: a method with even one metric truly unsafe reaches PASS only if that
metric's own safe-side bound clears its threshold, which has probability at most
the per-metric level (0.025), so PASS needs no adjustment. FAIL is a union of
per-metric claims, so its familywise false-FAIL probability grows with the number of
decisions and is budgeted at 0.05 by Bonferroni over all registered decisions:
24 cells × 5 confirmatory statistics × 3 metrics = **360** (α = 0.05/360 =
1.39×10⁻⁴). The cost is stated plainly: FAIL is reserved for clear refutation, and a
moderately deficient method will usually be INCONCLUSIVE, never PASS. rankIC is
descriptive and enters no decision.

**Cell, statistic and protocol states.** A statistic takes the worst of its three
metric states, a cell the worst of its statistics (FAIL, then INCONCLUSIVE, then
PASS). Top-level precedence: (1) `INFRASTRUCTURE_ERROR` if no complete result exists;
(2) `FAIL` if any evaluated confirmatory cell is FAIL; (3) `INCONCLUSIVE` if any
evaluated cell is INCONCLUSIVE; (4) `DATA_INSUFFICIENT` if any registered cell is
below its minimum confirmatory depth (none is, by construction); (5) `PASS`. A
definite refutation outranks everything; an evaluated cell the simulation cannot
resolve outranks an unevaluated one because it is information about the method,
whereas a depth shortfall is information about the calendar. Only PASS licenses
confirmatory inference.

**What 2,000 replicates can and cannot resolve** (development operating
characteristic, coverage metric): PASS needs an observed coverage of at least
0.960 (1,920/2,000); FAIL needs at most 0.931 (1,862/2,000). A true coverage of
0.975 PASSes with probability 1.000, 0.970 with 0.995, 0.965 with 0.897, 0.960 with
0.530, 0.957 with 0.276, 0.950 with 0.020; true 0.940 is FAIL with probability
0.052 and INCONCLUSIVE 0.948, true 0.920 is FAIL with 0.970, true 0.900 FAIL with
1.000. **Consequence for this protocol, stated before the run:** the
PERSISTENT_SHARED_HEAVY / H21 / 78-week cell has exact Gaussian `dateMean` coverage
0.9569, so it is INCONCLUSIVE with probability about 0.735 even if the method is
exactly as analysed; treating the 16 inherited-DGP `dateMean` coverage cells as
independent, the probability that all of them PASS is about 0.20. The formal
verdict is therefore **more likely INCONCLUSIVE than PASS**, and an INCONCLUSIVE
result is a complete, legitimate outcome: it says a 0.957 method cannot be
certified against a 0.95 floor with 2,000 replicates. R was not raised to avoid it.
Resolving it would need a larger R (a separately justified v5 calibration-method
study), not a rerun of this protocol.

**Rank IC.** Nothing here decides the future ordering claim. The accepted Alpha
design review expects a positive rank-IC lower bound in the v5 evidence contract.
`rankWeightedSpread` is **not** silently substituted for it. Before v5
preregistration a separate design decision must choose among: keeping rank IC
confirmatory with another valid inference treatment; adopting `rankWeightedSpread` as
the ordering criterion; or making rank IC descriptive and formally revising the
composite primary claim.

## 7. Feasibility of each horizon

- **H21** (78 and 156 weeks): feasible under the proposed method; the calendar
  series has 82/160 observations with only return persistence. The tight point is
  strong weekly persistence at 78 weeks (analytic ≈95.7%).
- **H126 at 312 weeks**: the mean is identifiable and its variance is estimable
  from 337 weekly observations **if weekly realized returns are short-memory**.
  Overlap does not destroy information about the mean — it only hides it from a
  signal-date variance estimator. What 312 weeks cannot do is (a) detect or
  correct dependence with memory of a year or more (regimes, slow expected-return
  variation), which no method can separate from a mean over six years, and (b)
  give power: the interval's width reflects ~12 windows of information. A PASS
  therefore licenses a calibrated interval, not a powerful one.
- **H126 at 624 weeks**: feasible, with the same short-memory caveat.
- Below 78 (H21) or 312 (H126) weeks: `DATA_INSUFFICIENT_FOR_CONFIRMATORY_H{h}_INFERENCE`.

## 8. Limitations

- Calibration is conditional on the registered DGPs; it certifies nothing about
  real returns' stationarity, memory or tails.
- The exposure ramps (first/last ~25 calendar weeks at H126) are heteroskedastic;
  the `U1` limit ignores them asymptotically, and their finite-sample effect is
  inside the analytic numbers above, not corrected.
- Under an alternative with a nonzero forecast-only mean, attributing
  `pairedMseImprovement`'s forecast term to the signal week makes the normalizer
  conservative; it does not affect the null calibration.
- Nonlinear statistics (Spearman IC, probability scores, calibration slopes) get
  no confirmatory inference from this protocol.
- The v5 sample has been used by earlier research; a calibrated interval does not
  make it confirmatory in the prospective sense (design review §1).

## 9. Execution and stopping rule

This PR contains **no** formal v4 result. Only DEVELOPMENT_ONLY checks were run:
unit tests, 40-replicate smoke runs on non-formal seeds (every smoke cell is
INCONCLUSIVE, as it must be at that budget), an
implementation-vs-analytic check on replicate indices ≥ 10⁶, and the exact
Gaussian analysis. None selected a parameter.

After review and merge, the operator runs **once**, from `main`:
Actions → **Synthetic alpha inference calibration v4** → Run workflow (branch
`main`). The workflow refuses any other ref, has no inputs and no secrets. A
complete PASS, FAIL, INCONCLUSIVE or DATA_INSUFFICIENT artifact closes v4;
INCONCLUSIVE is not resolved by rerunning with more replicates or another seed. A FAIL is preserved,
never followed by a reseeded rerun, altered threshold, sensitivity swap or v4.1;
any further method is a separately justified v5 calibration-method study. Only a
run that produced no complete artifact (or `INFRASTRUCTURE_ERROR`) may be rerun,
after an infrastructure-only fix documented with the result.
