# kr-alpha-discovery-tournament-v1 post-outcome audit: reproducing it under the formal execution environment

Status: `POST_OUTCOME_FORENSIC_REPRODUCIBILITY_ENGINEERING`. This is not model rescue, not tuning, not Alpha Tournament v2. No tolerance, model, target, recency scheme, calibration, allocator, cost, terminal rule, benchmark, data, snapshot, lock, spec, result or formal workflow changed. The expensive audit was **not** dispatched by this change.

## 1. What the logs say (read from the Actions job logs, not from a prompt)

The formal result was computed in the **`execute`** job of run `37535814142` (job `112519474120`). The `frozen-machine` job of the same run installed separately and computed no result, so it is not the reference. The first audit is run `37688582489`, job `113022667916`.

| | Formal execute job | First audit job |
|---|---|---|
| CPython | **3.11.16** | **3.11.17** |
| Runner image | `ubuntu-24.04`, version `20260927.320.1` | `ubuntu-24.04`, version `20261004.327.1` |
| Provisioner | `20260901.588` | `20261002.596` |
| Azure region | centralus | northcentralus |
| Runner version | 2.337.0 | 2.337.0 |
| Architecture | x64 (cache key `Linux-x64-24.04`; wheels `manylinux_*_x86_64`) | same |
| Threads | `OMP/OPENBLAS/MKL_NUM_THREADS=1` | identical |
| numpy / scipy / scikit-learn / pandas / lightgbm | 2.3.1 / 1.16.0 / 1.7.0 / 2.3.0 / 4.6.0 | identical, **identical wheel files** |
| `iniconfig` | 2.3.0 | 2.3.1 |
| `peewee` | 4.5.2 | 4.5.3 |
| `toolz` | 1.1.0 | 1.2.0 |

Both installs list 47 packages. Those three are the only version differences; the other 44 are identical. The package list in the task statement equals the formal log's list exactly (no extra, no missing, no value difference).

Not recorded by the formal log, and therefore unrecoverable: CPU model and flags, the BLAS kernel set chosen at run time, `numpy.show_config()`, kernel/uname, locale, `TZ`, `PYTHONHASHSEED`, and the versions of `pip`, `setuptools` and `wheel` (pip's "Successfully installed" line lists only what it installed that run).

## 2. Why a 1.31e-7 mismatch can plausibly come from the environment (not proven)

The first audit's only divergence from the sealed result is `PRIMARY_ROBUST_KELLY:COST_X2/annualLogGrowth`, reconstructed 0.10176568680470117 against sealed 0.101765555609953: a gap of 1.31e-7, about 131 times the registered 1e-9 tolerance. The complete-path flags, fold states, ensemble IDs, counters and process structure all matched (see the diagnostics below), so this looks like numerical drift in a floating-point pipeline, not a different decision.

- The three drifted packages are pure Python (a test-runner dependency, a `yfinance` dependency, a functional-programming helper). They are not in the numerical path and are very unlikely to be the cause. They are pinned anyway, because the gate is "same environment", not "same environment except the parts I believe don't matter".
- A Python patch release (3.11.16 to 3.11.17) is also an unlikely source of different float arithmetic, and is pinned for the same reason.
- The more plausible candidates are on the host. As far as I know the numpy and scipy wheels bundle an OpenBLAS built to choose its kernels from the CPU at run time (this is not verifiable from the logs). The same wheel on a different CPU generation can then use different vector kernels and a different summation order. The pipeline fits 3,960 models and solves the allocator 24,231 times, and iterative solvers and constrained optimisers can turn a last-bit difference into a 1e-7 one.

None of this is established. The honest status is: the Python-level differences are small and unlikely to matter, the host-level difference is a candidate, and the formal CPU was never recorded, so it cannot even be compared. It is also possible that the formal result is simply not reproducible bit-for-bit on a different host. In that case the audit will keep reading `RECONSTRUCTION_MISMATCH`, and that is the registered outcome; the tolerance is not loosened to avoid it.

## 3. What is now pinned

- `docs/results/kr-alpha-discovery-tournament-v1-formal-environment-37535814142.json`: the manifest, derived mechanically from the two logs, with its own digest. It records the formal run and job, the exact Python, the 47 packages, the numerical wheel file names, the thread variables, the host facts the log did state, and the first audit's differences.
- `constraints/kr-alpha-discovery-tournament-v1-formal-env-37535814142.txt`: the audit-only constraint file, byte-for-byte what the manifest implies (a test enforces it). With the repository's `requirements*.txt`, pip's resolver (targeted at CPython 3.11 on Linux) selects exactly the 47 formal versions.
- `.github/workflows/kr-alpha-discovery-tournament-v1-postoutcome-integrity-audit.yml` (the **audit** workflow only): `python-version: '3.11.16'`, no pip cache, `runs-on: ubuntu-24.04`, install with `-c` the constraint file, and the preflight below. It also refuses an `audit_ref` whose copy of the byte-pinned formal workflow differs from the execution commit.

## 4. The preflight (cheap, before the expensive work)

`scripts/check_kr_alpha_tournament_formal_environment.py` runs right after the install and before the 336 MB snapshot download and the roughly 1.5 hour reconstruction. It exits non-zero, and the job stops, unless: the interpreter is CPython 3.11.16; every one of the 47 packages is installed at its formal version; the three thread variables are `1`; and the constraint file equals the manifest. It always writes `audit/environment-parity.json` (printed to the log and uploaded), including `pip freeze`, `numpy.show_config()`, the threadpool/OpenBLAS dispatch architecture, CPU model and flags, `uname`, the runner image and the thread variables. In the authoring sandbox (Python 3.13, other package versions, no thread variables) it correctly refuses and names every difference.

Two classifications are kept apart:

- `PYTHON_ENVIRONMENT_EXACT_MATCH` / `PYTHON_ENVIRONMENT_MISMATCH`: gating.
- `HOST_HARDWARE_IMAGE_MATCH` / `_DIFFERS` / `_UNVERIFIABLE`: recorded, never gating. `MATCH` requires a recorded formal CPU model and BLAS architecture to compare with; the formal log has neither, so today the honest values are `DIFFERS` (the runner image has rolled) or `UNVERIFIABLE`.

## 5. What remains unpinnable on GitHub-hosted runners

The CPU model and microarchitecture, the BLAS kernels selected from it, the kernel, and the runner image (a historical image is not selectable; `ubuntu-24.04` pins only the OS major). The audit records all of them so that a second run can say exactly what is still uncontrolled.

## 6. Diagnostics when the reproduction is still refused

The 1e-9 gate and its status are unchanged. When it refuses, the output now also carries `reproduction.diagnostics`, descriptive only: the first divergence with its absolute and relative difference, whether the complete-path flags, outer fold states, selected ensemble IDs by year, counters and process structure matched, the maximum numeric difference among fields compared before the refusal point and across all registered fields, a per-key table, and the formal-versus-this-run environment comparison. It names no ticker, event date, held weight or cause, and a refused reproduction still returns before any attribution code runs (a test checks the ordering in the code). On the exact registered success, the existing forensic sections run unchanged.

## 7. What this does not do

It does not run the audit, does not make the reproduction pass, does not change what a pass means, and does not claim the environment is the cause. The next step is a human-dispatched run of the same unchanged audit after this is merged; if it reproduces, the registered forensic sections run, and if it refuses, the diagnostics say how.
