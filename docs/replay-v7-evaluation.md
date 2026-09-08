# Replay v7: fixed evaluation and immutable inputs

This changes experiment definitions, not production scoring. v6 and v7 headline results are **not directly comparable**. The complete v7 historical strategy replay has not been run in this PR.

## Calendar and input contract

The evaluation origin is 2013-01-01. The first entry follows the first completed weekly signal period; subsequent primary entries are exactly 21 common XKRX/XNYS sessions apart. Other horizons use their own 63/126/252-session schedules. Each entry uses the latest **scheduled**, strictly earlier weekly signal date. An absent signal is a missing block, never a reason to select a different date. Weekly decisions remain available for calibration and empty-portfolio diagnostics; monthly trading anchors need not themselves be weekly signal dates. This preserves the weekly scoring grid without letting observed prices or portfolio maturity choose evaluation dates. Entry/exit use session-date closes, not simultaneous Korean/US execution timestamps.

The calendar dependency and calendar identifier are pinned. The supported session table is 1990–2035; requests outside it fail. Calendar corrections require a new calendar/experiment version. Exchange calendars, particularly future exceptional closures, are not an oracle. See the [calendar implementation and scope](https://github.com/gerrymanoim/exchange_calendars).

Inputs are canonicalized **before use** and recorded in content-addressed gzip objects under `ledger/replay-inputs/objects`. Prices and benchmarks use monthly components; universe membership, PIT records, macro vintages and releases, VIX, FX, dated rate coverage and calendar rows are also bound. A generation manifest lives at `ledger/historical/<replayVersion>/inputs.json`; every manifest revision is retained under `input-manifests`. Unchanged objects are reused. This is not a second full copy per run; a changed monthly object necessarily stores a new object. Source history completeness is not improved merely by hashing it.

A generation may append observations strictly after its committed cutoff. Revised values, recovered missing historical rows, removals, changes to undated universe metadata or to the configuration/policy fail before replay writes. In particular, adjusted-price vendor restatements and newly recovered PIT releases are **not silently spliced** into the old experiment. The conservative alternative chosen here is to require a new DATA_VERSION and a new REPLAY_VERSION directory. Automatic vendor revision acceptance would improve operational convenience but destroy the immutable-prefix claim. Ordinary refreshes can consequently fail and require deliberate version management. `--full` cannot bypass this rule. `--frozen-inputs` consumes the committed snapshot without refreshing external data, and requires the stored cutoff/configuration. Missing snapshot objects or hash mismatches fail.

PR #85's replay determinism guard remains the final check. A matching snapshot is not a substitute for that guard. Reports retain their snapshot hash, calendar anchors/hash and metric definition. Previous-generation reports and new report content hashes are archived; old signal/outcome generations remain untouched.

## Measurement definitions

- Calendar years = `(lastEndDate - firstDate).days / 365.2425`; CAGR = `terminalNAV ** (1 / years) - 1`. Rolling windows use their actual first and last observation dates, including leap-year effects.
- Portfolio holdings are bought at the anchor, held through the block, and marked on the union of KR/US trading dates. A closed exchange may carry its last official close; an open-market observation gap cannot. No interpolation fills prices, FX, benchmarks or rates. Entry transaction costs reduce investable NAV multiplicatively. Subsequent turnover uses drifted terminal holdings.
- MDD includes initial NAV, daily intra-block marks and entry-cost drawdowns. Intraday drawdowns are not measured. CVaR and headline Sharpe/Sortino now use daily observations; annualization uses observed daily intervals per actual calendar year.
- US local gross growth is multiplied by `USDKRW(t) / USDKRW(entry)`. Each selector's benchmark has the same initial regional weights and cash as that selector and uses the same dates and KRW conversion. Benchmark blends can differ across selectors; paired excess tests compare performance against each matched blend, not identical benchmark holdings.
- Cash and risk-free excess returns use the dated **BOK policy-rate proxy**, effective no earlier than the next calendar day after announcement, compounded daily ACT/365 across weekends. Sharpe uses daily return minus contemporaneous risk-free return; Sortino's downside RMS includes all daily observations. The [BOK rate history](https://www.bok.or.kr/portal/singl/baseRate/list.do?dataSeCd=01&menuNo=200643) is not an investable cash total-return series. Its coverage cutoff is recorded; unavailable rates block measurement rather than default to zero.
- Regional stock-horizon alpha diagnostics and challenger calibration remain regional/local-currency signal diagnostics. The fixed-window selection null uses KRW returns but block-sampled Sharpe, explicitly distinguished from daily headline Sharpe.

`HORIZON_NOT_MATURED` is pending, not a missing-data failure, and is excluded from the eligible completeness denominator. A genuinely missing matured block prevents a continuous headline NAV from being published even if the old percentage threshold would pass. Unknown intervals are never joined as flat cash.

An `EMPTY_PORTFOLIO` decision stays in the evaluation as 100% KRW proxy cash, with entry/exit turnover. This changes the estimand from performance conditional on selecting stocks to performance of the complete decision policy. Weekly empty stretches of at least 45 calendar days report dates, duration, exclusion reasons, champion availability and potential bias from excluding the interval. Missing rate data still blocks an empty cash window.

The survivorship coarse sweep is retained. The first verdict-change bracket is bisected to width at most 0.001 (maximum 12 iterations). The report stores midpoint, bounds, half-width error and refinement steps. This is numerical precision conditional on the configured verdict test/bootstrap, **not** a statistical confidence interval or proof that verdicts are globally monotonic.

## Observed historical check

Source: [`signal-history` report at bcfe868](https://github.com/jaehojung1879-netizen/Investment/blob/bcfe86800403c5911c0c24305bea7d9e467306fa/ledger/historical-portfolio-validation.json). The committed compact fixture retains provenance and observed NAVs. Its 132 blocks span 2013-11-15–2026-08-25: **12.775074 years**, although the old formula treated them as 132/12 = **11 years**.

| Metric | Published v6 Champion | Same v6 NAV, span correction only | Published v6 Challenger | Same v6 NAV, span correction only |
|---|---:|---:|---:|---:|
| CAGR % | 9.480 | 8.111 | 16.324 | 13.906 |
| Matched benchmark CAGR % | 9.641 | 8.248 | 9.536 | 8.159 |
| Annualized excess, pp | -0.162 | -0.137 | 6.788 | 5.747 |
| Sharpe | 0.970 | Not recoverable with dated RF/daily NAV | 1.298 | Not recoverable with dated RF/daily NAV |
| MDD % | -13.734 | Daily MDD not recoverable from block endpoints | -9.052 | Daily MDD not recoverable from block endpoints |

This table isolates a denominator error on the **same old path**; it does not estimate v7 strategy performance. Fixed anchors, inclusion of empty cash windows, FX, daily marks and costs may all change the new result. No full-v7 headline number is claimed.

Tests also value the actual committed 2019–2020 KOSPI 200 benchmark observations on the new fixed daily schedule, reconcile terminal NAV to observed price ratios and reject a changed historical observation. Synthetic unit fixtures separately exercise FX, missing inputs, intra-block crashes and threshold precision; those fixtures are not historical performance evidence. An additional index-only CLI smoke attempt correctly failed the existing benchmark gate because benchmarks are excluded from the stock universe and supplied no matured stock signals; it is not counted as a successful full replay.

## Migration and operator sequence

The observed v6 manifest contains **377,248 signals and 372,014 outcomes**. They remain available as old-generation evidence, but cannot become v7 inputs by relabeling. This PR increments REPLAY_VERSION to `replay-v7` and adds immutable-input/calendar/USDKRW-rate identifiers to DATA_VERSION; MODEL_VERSION and FEATURE_VERSION are unchanged. The first replacement generation is created by the first post-merge full workflow, not by this PR. Expect unavailable v7 evidence until that run and its gates succeed.

1. Run **Historical point-in-time replay** (`.github/workflows/replay.yml`) with `full=true`, `frozen_inputs=false`, `retrain=false` to acquire and commit the initial v7 inputs and rebuild outcomes/report. Existing Sunday automatic training remains for acquisition runs; this change does not authorize additional sealed-holdout trials.
2. Run **Historical point-in-time replay** with `full=true`, `frozen_inputs=true`, `retrain=false` to verify the same snapshot again. Frozen verification suppresses automatic Sunday retraining. Inspect the input hash, report contract and replayDeterminism result; a baseline-only result is not proof of a repeated match.
3. Only after those gates pass, run **Build insight data and deploy Pages** (`.github/workflows/pages.yml`) to present the validated generation. Do not lower gates to obtain a headline. No forced model retrain is necessary for these measurement changes; model promotion retains its existing separate requirements.

If acquisition or audit blocks, investigate the recorded missing inputs/conflict first. A vendor correction to an already committed cutoff requires **another DATA_VERSION and REPLAY_VERSION**, even after merge. Frozen reruns of the same inputs require neither. Sparse PIT, historical survivorship coverage, vendor-adjusted history, stale FX/rates, execution/market-close alignment, and full-universe compute/storage costs still need validation on the real full workflow. Snapshotting does not solve these limitations or confer PIT_EXACT/liveValidated status.
