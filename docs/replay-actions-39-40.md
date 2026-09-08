# Replay #39 / #40 failure investigation

The Actions scheduler and runner worked. Both jobs deliberately failed the final portfolio contract step after preserving the blocked report. Re-running unchanged inputs is not a remedy.

| Run | Code | Actual block reason |
|---|---|---|
| [#39](https://github.com/jaehojung1879-netizen/Investment/actions/runs/34199152895) | main b651235, replay-v6 | PR85 determinism guard: first block changed from 2013-11-15..2013-12-17 to 2014-01-03..2014-02-05 |
| [#40](https://github.com/jaehojung1879-netizen/Investment/actions/runs/34206878163) | main eabe1ef, replay-v7 | genuine_missing_fixed_blocks; version transition itself accepted |

Run #40's pinned input hash is `93d94ce0a024b87d64f57e47928117eeb3179f23ddece0c29f3396f753c821e3`, cutoff 2026-09-07. Its matured primary schedule has 154 blocks: Champion measured 131 (85.065%), missing 23; Challenger measured 138 (89.610%), missing 16. One additional block is correctly pending. Challenger's ten empty/cash blocks are included in the 138 measured windows. No headline CAGR is available. A transient push rejection was retried/rebased successfully, and did not cause the final failure.

## Confirmed defects and residual data gaps

The pinned exchange-calendars 4.11.1 table treats 2026-05-25, 2026-06-03 and 2026-07-17 as KRX sessions. Published closures contradict that table: [broker's 2026 market schedule](https://corp.tossinvest.com/en/post?category=52&id=21740&type=notice); [KRX announcement reported May 20](https://www.newspim.com/news/view/20260520000433). This PR adds only those explicitly sourced closures. NYSE remains independently scheduled. Prices are never used to infer a holiday.

This corrects a defect in PR86's calendar validation; its 2019–2020 artifact test could not catch newly announced 2026 closures. New tests cover all three closures and union-session carry without concealing a following open-day price gap.

Other defects in the inputs remain. The actual immutable February 2013 benchmark object has no KOSPI 200 close on **2013-02-19**, an open session. That observation is committed as a regression fixture and continues to fail measurement. The report also identifies USD/KRW gaps and a held ESRX window spanning 2018-11-30..2019-01-04; the latter requires investigating corporate-action/delisting proceeds, not assuming a return or dropping the stock. This PR neither fills those inputs nor claims full replay will become green.

Input-gap diagnostics now list the exact absent/nonpositive/nonfinite open-session dates per ticker and FX series, with a bounded sample in Actions logs. Previously only broad reason codes and block counts appeared in the console. Full dates stay in the report.

## Version and execution implications

Correcting common sessions changes anchors. Applying that correction inside the existing v7 generation would violate its immutable calendar. Therefore the fix explicitly starts **replay-v8 / common-calendar-v2-kr-2026-closures**, leaving MODEL_VERSION and FEATURE_VERSION unchanged. Observed v7 contains **345,956 signals / 343,081 outcomes**; none are deleted, relabeled or rewritten. Its snapshots and blocked report remain evidence. A new generation is more expensive than relabeling v7, but preserves the experiment contract.

Do not repeatedly acquire the same incomplete history expecting a green result. First use the preserved v7 report/snapshot to investigate genuine benchmark, FX and held-name gaps. Source-backed repairs must enter a new experiment; no interpolation, date skipping, benchmark substitution or completeness relaxation is authorized by this fix.

After merge, an operator who wants the corrected-calendar diagnostic generation can run **Historical point-in-time replay** with `full=true`, `frozen_inputs=false`, `retrain=false` to create v8. Expect a blocked report if the documented data gaps remain. Then the same workflow with `full=true`, `frozen_inputs=true`, `retrain=false` checks the frozen inputs; it cannot repair missing data. Only publish through **Build insight data and deploy Pages** after the report contract passes. No workflow is dispatched automatically by this PR.

The v6/v7/v8 headline definitions/calendars are not directly comparable. This investigation does not produce new strategy performance numbers. The older v7 design document remains historical documentation; this note supersedes its active version instructions.
