# Alpha inference calibration v5 — precision-only replication of v4

Status: **PROTOCOL FROZEN, NOT EXECUTED.** Synthetic/statistical methodology only. No historical Alpha outcome, label, return, score, prediction, Alpha result report or `signal-history` artifact was read. This is a calibration replication. It is **not** Alpha model v5, not a historical experiment, and it authorizes no Alpha execution.

Machine-readable protocol: `research_specs/alpha-inference-calibration-v5.json`.
Predecessor record: `docs/results/alpha-inference-calibration-v4-report.md`.
Development diagnostics (DEVELOPMENT_ONLY): `docs/results/alpha-inference-calibration-v5-precision-diagnostics.json`, reproduced by `scripts/diagnose_alpha_inference_calibration_v5.py`.

## 1. What v4 returned, and why v5 exists

Verified directly from GitHub Actions (run, job, artifact listing and job log): workflow `Synthetic alpha inference calibration v4`, run `36493207997`, main `4b5cd78f8d23d4b7572e6eddbaf262cce5e35fb3`, frozen spec sha256 `012e43177b8e8ec7143eff30d7280c4cf8015b32b464bcddd87c09f75c984a5d`, artifact `11002423544` (zip sha256 `0013579e661e026a592a658dfbaf3337ff5f6741d7432d1a7557332ba9dc08a8`), `primaryStatus: INCONCLUSIVE`, 24 cells: **22 PASS, 2 INCONCLUSIVE, 0 FAIL**. The two INCONCLUSIVE cells are `PERSISTENT_SHARED_HEAVY` and `PERSISTENT_SHARED_HEAVY_TAILED_PERSISTENT_PREDICTORS`, both at H21 / 78 weeks. Every H126 cell, at 312 and 624 weeks, passed.

That is not a methodological FAIL. It says the simulation could not certify two cells against the frozen 0.95 coverage floor under the predeclared exact Clopper–Pearson rule at 2,000 replicates. **v4 is closed** and is never rerun, re-seeded, re-thresholded or reinterpreted as PASS, and there is no v4.1.

v5 asks one question: **can the already-frozen v4 inference method be classified more precisely under a separately preregistered, larger Monte Carlo budget?**

## 2. v5 is a replication, not a new method

The scientific method is **identical** to v4: calendar-time attribution, the unchanged v3 self-normalized U1 pivot (critical value 66.57), the five confirmatory statistics (`dateMean`, `selectedMean`, `selectedMinusUniverse`, `pairedMseImprovement`, `rankWeightedSpread`), Spearman `rankIC` descriptive only, the six DGPs, horizons 21/126, calendar depths 78/156 and 312/624, minimum confirmatory depths, 60 names, 5-session step, 20% selection, forecast scale 0.25, persistent-predictor and Student-t (4 df) settings, the 0.95 coverage floor, the 0.05 false-positive and undefined-frequency ceilings, the Clopper–Pearson three-state decision rule with its levels (PASS side one-sided α = 0.025, FAIL side familywise 0.05 Bonferroni over 360 decisions), the verdict precedence (INFRASTRUCTURE_ERROR > FAIL > INCONCLUSIVE > DATA_INSUFFICIENT > PASS) and the anti-rerun stopping rule.

No statistic is promoted or demoted, the two difficult H21 / 78-week cells stay, no DGP is removed, and no easier DGP is added. The estimator families adjudicated in v4 (moving/circular/stationary block bootstrap, HAC, fixed-b alternatives, batch-t, subsampling, equal-weighted cosine and the rest) are **not** reopened; v4 §4 stands.

The only differences from v4 are: the contract name, a new seed, a larger replicate budget, and the documentation and workflow that go with them.

### Machine-verifiable equivalence

- **Engine reuse, not copy.** `pipeline/alpha_inference_calibration_v5.py` calls the v4 engine (`pipeline.alpha_inference_calibration_v4.run_calibration`) with the v5 protocol under the v4 contract label. It contains no simulation, interval or decision code. The sha256 of every file the engine executes (`alpha_inference_calibration_v1.py`, `_v3.py`, `_v4.py`, `alpha_inference_mc_decision.py`) is pinned in the v5 module and in the v5 spec, and the runner verifies the bytes before any simulation; a changed engine file is `ENGINE_FILE_CHANGED`.
- **Key-by-key protocol equivalence.** `semantic_differences` classifies every top-level key of the v4 and v5 protocols. The 17 scientific keys must be equal; the permitted differences are an explicit list (identity, seed, budget, provenance, prose); any other key fails. A formal run refuses a protocol that violates this, and the tests assert it.
- **Same predecessor.** The runner checks that the v4 protocol on disk has sha256 `012e4317…`, and the workflow refuses to run if either protocol file differs from the repository.
- **Same numbers for the same inputs.** A test runs the v4 engine and the v5 wrapper on an identical small protocol and requires identical cell results.

## 3. The replication budget: a general precision rule

R is fixed by a rule about a probability estimate at the coverage floor. It is **not** chosen by asking how many replicates would classify the two v4 INCONCLUSIVE cells, and no v4 cell value enters it.

**Rule.** The 95% Monte Carlo half-width of a probability estimate at p = 0.95 must be at most **0.5 percentage points**, by both the normal approximation and the exact two-sided Clopper–Pearson interval. The budget is the smallest multiple of 500 satisfying both.

- **Normal approximation:** 1.96·√(0.95·0.05/R) ≤ 0.005 ⇒ R ≥ (1.96/0.005)²·0.0475 = 7,299.04, so **R ≥ 7,299**.
- **Exact Clopper–Pearson** (k = round(0.95 R), two-sided 95%): the half-width at R = 7,500 is 0.0050001, over target by 1.3×10⁻⁷, and it first meets the target at **R = 7,501** (and stays under it for every larger R checked).
- **Rounding up to a multiple of 500:** 7,500 satisfies the normal criterion but not the exact one, so the budget is **R = 8,000** (exact half-width 0.00484). The exact rule is the one that matters because it is the interval family the decision rule itself uses.
- Runtime scales from v4's 488.5 s at R = 2,000 to roughly 33 minutes; the workflow timeout is 180 minutes.

R is frozen before the formal run and validated by recomputation (`chosen_replicates()`), not just compared with a constant.

### Operating characteristic at generic true values (DEVELOPMENT_ONLY, computed before freeze)

Exact probabilities of each formal state for the **coverage** metric under the frozen decision rule, at generic true coverage values near the 0.95 floor. The grid is generic and not tuned to any v4 cell.

| true coverage | R = 2,000 (v4) P(PASS / INCONC / FAIL) | R = 8,000 (v5) P(PASS / INCONC / FAIL) |
|---:|---|---|
| 0.930 | 0.000 / 0.418 / 0.582 | 0.000 / 0.0001 / 0.9999 |
| 0.940 | 0.000 / 0.948 / 0.052 | 0.000 / 0.382 / 0.618 |
| 0.945 | 0.001 / 0.994 / 0.005 | 0.000 / 0.949 / 0.051 |
| 0.950 | 0.020 / 0.980 / 0.0001 | 0.023 / 0.977 / 0.0001 |
| 0.955 | 0.152 / 0.848 / 0.000 | 0.536 / 0.465 / 0.000 |
| 0.960 | 0.530 / 0.470 / 0.000 | 0.990 / 0.010 / 0.000 |
| 0.965 | 0.897 / 0.103 / 0.000 | 1.000 / 0.000 / 0.000 |
| 0.975 | 1.000 / 0.000 / 0.000 | 1.000 / 0.000 / 0.000 |

At R = 8,000, PASS needs at least 7,639 of 8,000 covered (0.9549) and FAIL at most 7,526 (0.9408); at R = 2,000 those were 0.9600 and 0.9310. The false-positive and undefined-frequency ceilings mirror this around 0.05 (diagnostics file).

**What this does and does not buy.** The PASS boundary falls from 0.960 to 0.955 and the FAIL boundary rises from 0.931 to 0.941, so the ambiguous band narrows from about 0.931–0.960 to about 0.941–0.955. A true coverage from about 0.960 up is now almost certain to PASS, and one below about 0.94 to FAIL. **A true coverage inside roughly 0.941–0.955 remains INCONCLUSIVE with high probability, and v5 does not promise a PASS or a FAIL.** A cell whose true coverage lies in that neighbourhood, such as the exact-Gaussian values near 0.957 published with v4, is not guaranteed to classify; whether it does is exactly what the formal run measures. INCONCLUSIVE is a complete, legitimate result and R is not raised further.

## 4. Seed

The formal seed is `20261002`, one deterministic value chosen before any formal run and different from v1 (`20260928`), v2 (`20260929`), v3 (`20260930`) and v4 (`20261001`). No seeds were searched or previewed. Every replicate stream is `SeedSequence([seed, dgp, horizon, weeks, replicate])`, so v5 draws are independent of v4's; the larger budget is a fresh replication, not an extension of v4's draws. A development smoke may not use the formal seed or any closed protocol's seed.

## 5. Chronology

The precision diagnostics (budget derivation and generic operating characteristic) were computed **before** the v5 protocol was frozen and are disclosed in full. Nothing in them uses a registered cell, a v4 coverage value or a v4 result. No v5 formal run has been executed; only DEVELOPMENT_ONLY smoke runs on other seeds and unit tests were run.

## 6. Formal states and what follows

`PASS`, `FAIL`, `INCONCLUSIVE`, `DATA_INSUFFICIENT`, `INFRASTRUCTURE_ERROR`, with the v4 precedence. Only PASS licenses the calibrated confirmatory inference contract. A complete result closes v5.

- **PASS:** inference calibration is complete. Next, in order: fixed-sample original-XBRL value validation; repaired KR snapshot freeze/hash; final accounting semantic contract; a future Alpha-v5 preregistration (including the open rank-IC versus `rankWeightedSpread` decision); one authorized historical Alpha execution.
- **FAIL:** not rescued. The inference methodology is reconsidered in a separately justified future study.
- **INCONCLUSIVE:** not resolved by rerunning with more replicates or another seed. A further precision study would be a new preregistered calibration version.

## 7. Execution

This PR contains protocol, implementation, workflow and tests only. After review and merge, on `main`, exactly once: **Actions → Synthetic alpha inference calibration v5 → Run workflow (`main`)**. The workflow refuses any other ref, has no inputs and no secrets, reads no market data and no `signal-history`, uploads the complete artifact even on a non-PASS verdict, and stays green for every complete methodological result; only `INFRASTRUCTURE_ERROR` fails the job. A rerun is allowed only if no complete artifact was produced, after an infrastructure-only repair documented with the result.
