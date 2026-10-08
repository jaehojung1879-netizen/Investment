# kr-alpha-discovery-tournament-v1: forensic closure

Status: `CLOSED`. The formal decision stands unchanged, the post-outcome audit has reproduced it, and no further formal or audit run is authorized.
This document closes the investigation. It is not a rescue, not a re-seal and not a new result.

## 1. The formal decision (unchanged)

| | |
|---|---|
| Formal run | `37535814142`, execution commit `eac50fdf725ac797e5c37044246e2a7ffa9b1e64` |
| Spec | `a8acb44c4b685e06ce7692e44461147110e2e2d32a119adef0dd216476f50e7f` |
| Sealed result | `docs/results/kr-alpha-discovery-tournament-v1-result.json`, sha256 `4a117ed2…cc5d` (byte-identical, test-pinned) |
| Verdict | **`BLOCKED_BY_DATA_INTEGRITY`** (code `E`; `pathsComplete: false`) |
| Promotion | **not eligible** (`promotionEligible: false`) |
| Lock refs | both `refs/tags/kr-alpha-discovery-tournament-v1-execution-lock*` still point at `eac50fdf` (checked with `git ls-remote`, 2026-10-08) |

The verdict order is `E, A, B, C, D` and it stopped at `E`. No performance gate (DSR, PBO, SPA, bootstrap) was evaluated as a verdict input, so the
tournament says nothing about whether its process had alpha. The one complete active path, `PRIMARY_ROBUST_KELLY:COST_X2`, recorded annual log growth
0.1018 against 0.1790 for 100% passive. That is a number in the sealed file, not a verdict, and it is not reinterpreted here.

## 2. The audit that reproduced it

| | |
|---|---|
| Audit run | `37757869994` (`workflow_dispatch` on `main`, conclusion `success`), job `113246784127` |
| Audit code | `685b33dea77a032a56f6780d6213c396802da367` (PR #210) |
| Environment | `PYTHON_ENVIRONMENT_EXACT_MATCH` (CPython 3.11.16, 47 packages, three thread variables = 1); host `HOST_HARDWARE_IMAGE_DIFFERS` (recorded, never gating) |
| Reproduction | **`RECONSTRUCTION_REPRODUCES_THE_SEALED_RESULT`**, `firstDivergence: null` across `complete, paths, process, prediction, evidence, verdict, outerAnchors, signalCoveragePercent, inputIdentitySha256, counters` at the registered 1e-9 tolerance |
| Input identity | `233df37e…66a7` before and after the run |
| Artifact | `…-37757869994`, id `11543019315`, zip `sha256:1fed282b…ceac` (quoted from the API, not downloaded) |
| Committed bytes | `docs/results/…-run37757869994-full.json` (`75093ed6…730c`, 53,450 B) and `…-environment-parity.json` (`ea35959f…4f03`, 8,958 B), decoded from the job log and matched to the digests the run printed; provenance in `…-run37757869994-provenance.json` |

The model-free scan this run wrote is byte-identical to the one run `37688582489` wrote (`9dca9508…4e1f`, already committed). The earlier
`RECONSTRUCTION_MISMATCH` (1.31e-7 on `COST_X2/annualLogGrowth`) did not recur once the Python environment matched the formal one. Which of the
differences (CPython 3.11.17, `iniconfig`, `peewee`, `toolz`) caused it is not established, and the host hardware still differed.

A successful reproduction means the audit computed the same numbers as the formal run. It does **not** mean the investment model passed anything.

## 3. Failure mechanisms (from the audit's own `firstFailures`)

Every incomplete path fails for one mechanism, `RAW_PRICE_ABSENT_AFTER_LAST_TRADING_DATE_HELD_THROUGH_PRE_TERMINAL_TRADING_SUSPENSION`
(`PORTFOLIO_MARK_OR_TERMINAL_ECONOMICS_UNRESOLVED`):

| Path | Security | First failing session | Held weight just before | Suspension | Terminal action | Consideration |
|---|---|---|---|---|---|---|
| `DECISION_FOCUSED_CHALLENGER:BASE` | 000030.KS 우리은행 | 2019-02-13 | 0.020% of NAV | 22 sessions from 2019-01-09 | `SHARE_TRANSFER` | `BLOCKED` |
| `PRIMARY_ROBUST_KELLY:BASE` | 079440.KS 오렌지라이프 | 2020-02-14 | 0.730% | 15 sessions from 2020-01-22 | `SHARE_EXCHANGE` | `BLOCKED` |
| `PRIMARY_ROBUST_KELLY:EXECUTION_DELAY_ONE_SESSION` | 079440.KS | 2020-02-14 | 0.659% | same | same | `BLOCKED` |
| `PRIMARY_ROBUST_KELLY:LIQUIDITY_HAIRCUT_HALF_ADV` | 079440.KS | 2020-02-14 | 0.730% | same | same | `BLOCKED` |

What the audit shows about each:

- The names were bought legitimately: tradable at the entry signal, no hindsight label rule applied at entry, and no registered information class
  carried the coming termination (`terminationInformationAvailableToTheFrozenProcess: false`; DART events were excluded as not PIT-ready).
- 우리은행: the 2019-01-10 decision set the target to 0, but the name was already suspended (zero volume), so the ledger deferred the sale
  (`deferredAtTrades`) and the position was still held when prices stopped.
- 오렌지라이프: no outer anchor fell inside the suspension; the last decision before it (2020-01-20) still targeted about 0.7%.
- `COST_X2` completed because it never entered either name (`costX2EverEntered: false` for both): doubled costs kept them below the hurdle.
- The terminal-action foundation resolves the termination *type* for both names, but `terminalConsiderationResolved`, `exchangeRatioResolved` and
  `terminalActionChainResolved` are `BLOCKED`. The ledger has no route to value what a holder received, so the mark fails closed, as registered.

So the early failures came from **missing terminal-action economics for securities the paths actually held**. They do not come from a `mark()` defect,
a benchmark gap or a mid-series gap (the scan finds none of either). Small weights are not evidence that the effect is immaterial: the path cannot be
valued past the event at all, and nothing here estimates what the missing consideration would have done to the rest of the backtest.

## 4. Decisions carried forward

1. The official decision remains `BLOCKED_BY_DATA_INTEGRITY`, not eligible for promotion. No alpha was validated.
2. The historical portfolio outcomes of the four paths remain **incomplete**. They are not imputed, truncated or re-run without the two names.
3. **No further formal rerun and no further audit dispatch is authorized.** The one-shot is spent and the forensic question is answered.
4. **Prioritization decision, not an integrity waiver:** a dedicated historical KR corporate-action reconstruction project (terminal consideration,
   exchange ratios, successor chains for the 22 terminated securities) is **not** pursued now. The `PARTIALLY_REPAIRED` foundation stays as it is.
5. Residual limitations carried forward: the 22-name terminal-economics gap; partial distributions on the adjusted-index return basis; the unresolved
   069500.KS accrual anomaly; the PIT top-120 large-cap scope; DART fundamentals dark in 2015 and partial in 2016.
6. **Prospective research must handle terminal events conservatively:** a held name that stops trading is never marked at its last price, never
   silently dropped and never assumed to receive anything. Its outcome is `TERMINAL_ECONOMICS_UNRESOLVED` until a cited terminal consideration exists,
   and an evaluation that needs it reports that state instead of a number. `kr-alpha-signal-v2` builds this rule into its receipt and outcome contract
   (`pipeline/prospective_receipt_core.py`, `docs/kr-alpha-signal-v2-design.md` §9).

Nothing in this closure edits the sealed result, the frozen spec, the tournament workflows, the lock refs, the input snapshot, the registered
tolerance, or any model, training or portfolio code.
