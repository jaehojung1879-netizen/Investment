# kr-alpha-discovery-tournament-v1 post-outcome integrity audit: recovery of run 37688582489

Status: `POST_OUTCOME_FORENSIC_DIAGNOSTIC_NOT_CONFIRMATORY`. No formal rerun, no reconstruction rerun, no model fitted, no lock touched, no sealed file edited.

## 1. What happened

The audit's `full` reconstruction ran for about 1h31m (step 9, 21:21:37Z to 22:53:01Z) and wrote `audit/integrity-audit-full.json`. The step then died on
`KeyError: 'evidenceClass'` in the final status print of `scripts/run_kr_alpha_discovery_tournament_v1_postoutcome_integrity_audit.py`:
`document.get("reproduction", {}).get("status", document["evidenceClass"])` evaluates its default eagerly, and a full document has no `evidenceClass`.
The job concluded `failure`, but the next steps (print to log, artifact upload) still ran and succeeded, so the file existed before the failure.

## 2. How the bytes were recovered (no recomputation)

The authoring sandbox cannot reach the Actions blob host (`CONNECT` 403), so the artifact ZIP was not downloaded. The audit workflow had already printed both files to
the job log as gzip + base64 (step 10). Those lines were decoded and each file was checked against the sha256 and size that the same step printed:

| File | sha256 | bytes |
|---|---|---|
| `audit/model-free-scan.json` | `9dca9508dc8899db01ca1d78777da986acc90b074f7fe973f1468df74f4f4e1f` | 16,012 |
| `audit/integrity-audit-full.json` | `3de415bf6e0646dbae6cde2d7da8a6645c50776697e6663122a97f94fc01766c` | 1,875 |

The ZIP digest `f4ff29d8…fe73` (artifact 11516337822, 3,729 bytes) is quoted from the Actions API and the upload step's log line; it was not recomputed here.
The files are committed unchanged as `docs/results/…-run37688582489-{full,model-free-scan}.json`, with a provenance record `…-run37688582489-recovery-provenance.json`.

## 3. The recovered result

`reproduction.status` is **`RECONSTRUCTION_MISMATCH`**.

```
firstDivergence: paths/PRIMARY_ROBUST_KELLY:COST_X2/annualLogGrowth (0.10176568680470117 vs 0.101765555609953)
```

The comparison prints `(reconstructed vs sealed)`. The sealed value is the one in the committed `docs/results/kr-alpha-discovery-tournament-v1-result.json`.

- Absolute gap 1.3119e-07, relative 1.289e-06. The registered tolerance is 1e-9 (`math.isclose` with `rel_tol = abs_tol = 1e-9`), so the gap is about 131 times the tolerance.
- It is small, and it is not zero. The gate is a registered refusal and is not softened.
- Keys are compared in the registered order (`complete`, `paths`, `process`, ...), so `complete` agreed and the paths sorted before `PRIMARY_ROBUST_KELLY:COST_X2` agreed. The gate stops at the first divergence, so nothing after that point was compared.
- The audit therefore attributed nothing. The 1,875-byte file has no per-path section by design, and none is fabricated here.

The file also confirms the identities it was run against: result sha `4a117ed2…cc5d`, spec `a8acb44c…0e7f`, input identity unchanged before and after (`233df37e…66a7`), both lock refs it records.

What is **not** known: why the reconstruction differs by 1.3e-7 on a statistic that is a function of fitted models. `requirements.txt` and `requirements-dev.txt` are byte-identical between the formal commit `eac50fdf` and the audited `main`, the tournament workflow is unchanged between them, and both set `OMP_NUM_THREADS=1`, so the pinned direct dependencies are not the difference. Unpinned transitive packages, the Python patch release and runner hardware are untested candidates; none is claimed.

## 4. The model-free scan, replicated

The recovered scan equals the committed model-free scan in every substantive field; the only differences are two prose provenance strings the run's own output does not carry. It is an independent
replication on the real raw snapshot (2,116 sessions, 101 outer anchors): no benchmark session missing, no Top120 mid-series gap, exactly eight terminal ends.

## 5. The nine audit questions, against what exists

1. `PRIMARY_ROBUST_KELLY:BASE` exact cause: **not determined** (attribution was withheld by the gate).
2. `DECISION_FOCUSED_CHALLENGER` exact cause: **not determined**.
3. `EXECUTION_DELAY_ONE_SESSION` exact cause: **not determined**.
4. `LIQUIDITY_HAIRCUT_HALF_ADV` exact cause: **not determined**.
5. Why `COST_X2` completed: **not determined**. All that is established is the consequence of its completing: it held none of the eight names on their first unpriced sessions, and whether it never bought them or sold them earlier needs the held-book reconstruction.
6. Pre-outcome detectability: **not determined by the audit**. The scan records that each terminal end was preceded by a 12-22 session suspension, that six of the eight names were in the Top120 at the last outer signal before their suspension, and that the terminal action chain is `BLOCKED` for all eight. Whether the frozen process could have seen the suspension at a decision date is a reconstruction question.
7. Data-foundation limitation or ledger defect: **the sealed run's own evidence supports a data-foundation limitation** (the terminal chain is unresolved for every end and the ledger has no terminal-economics path); the reconstruction that would separate this from a ledger defect did not pass its gate, so **it is not confirmed** by this audit.
8. Whether a valid forensic completion is permitted: see section 6.
9. Next scientifically legitimate step: see section 6.

## 6. What follows

A reconstruction that does not reproduce the sealed result is not a basis for attributing failures, and the audit says so by construction. Three things are permitted and none is done here:

- A **second, separately dispatched run** of the same unchanged audit to see whether `RECONSTRUCTION_MISMATCH` is stable or environment-dependent (the result would be a new, separately recorded run, not an edit of this one). It costs about 1.5 hours and needs a human dispatch.
- A **cheap, outcome-free** comparison of the dependency versions the formal run and run 37688582489 actually installed (both job logs print them). That tests the environment hypothesis without recomputing anything.
- Nothing may reinterpret the 1.3e-7 gap as "close enough"; the tolerance is part of the audit's registration.

No formal execution may ever be rerun.
