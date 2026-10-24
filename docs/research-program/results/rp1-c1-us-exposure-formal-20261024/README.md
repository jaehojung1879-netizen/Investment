# RP1 C1 US — one-shot formal result preservation candidate

**Status:** `FORMAL_EXECUTION_COMPLETE; ARCHIVE_READY_FOR_INDEPENDENT_AUDIT; NOT_MERGED_OR_PROMOTED`

The only formal execution was performed by the repository owner on **2026-10-24 18:30–18:32 KST**, workflow run [40082205870](https://github.com/jaehojung1879-netizen/Investment/actions/runs/40082205870), main commit `591f182955ab85bc527ddedc41c2d77d1fd24eaa`.

This PR is a **read-only, self-contained archive** of five original GitHub Actions artifact files. Their exact bytes are preserved as gzip+base64 text, one line per file in `payload/` (a Git-friendly transport; decoding yields identical bytes). Original artifact: `rp1-c1-us-exposure-results-40082205870`, GitHub artifact ID `12555293944`, ZIP SHA256 `8c42557fd57c98a8215ff6b62075f77221260be1856e1594f4ea5dbb26bf2764`. GitHub's transient artifact expiration does not remove this candidate archive once merged.

## Provenance and byte identity

| Exact original | SHA-256 of decoded original |
|---|---|
| `execution-started.json` | `0a999b082fcf0cda69bc1bcee35ee423e8b4dd49dda08ae6ac1d475c0aab05df` |
| `manifest.json` | `2022efbfdd65a54f1c57879ef85f06ddb7845af55853c5e899d8784230b69994` |
| `report.md` | `ade771b6837ff0d93e282d997c320f0809fc4f05916e178bd19e234619df5f45` |
| `result.json` | `910215317eedcaf45f293dc056749688f9400cd00f95102b565d265f552e3938` |
| `validation.json` | `7ca6bd5b53b456f7e5ae874e1f1281c9071a292608013585d3c017fda3257437` |

Authorization SHA256 `cf53d08c70216ea02321688a07a53ba9b4f9dfc1cf47a2e3591d49a4890aba48`; frozen spec SHA256 `4106709c48690a230e6ee07c782a5ea2d3374b3e8780bf31ecbdad97b0a00127`. Execution lock refs are already on GitHub. Do not trigger a retry.

Run `python docs/research-program/results/rp1-c1-us-exposure-formal-20261024/verify.py` to decompress in memory, verify all five exact original-byte SHA256 values, reconcile the original manifest's per-file hashes and check result/authorization/lock/validation invariants. Verification only: no research run, market API, secrets or Git writes.

## What the fixed historical replication actually found

The scope is **1993-02-05 through 2026-09-14**, 8,459 trading sessions, 1,754 weekly decisions. This is `FROZEN_RULE_REPLICATION_ON_PUBLICLY_KNOWN_US_HISTORY`: the rules were fixed using KR outcome-exposed history, then mechanically applied to public US history. Not independent prospective validation.

| Primary S&P500 price-index / zero-cash | Net CAGR | Max drawdown |
|---|---:|---:|
| Passive 100% | 8.82% | -56.78% |
| C0 | 7.77% | -42.33% |
| C1 | 7.98% | -43.43% |
| C2 | 7.41% | -39.27% |
| C3 | 7.62% | -40.42% |

The separately frozen cash-reinvestment economic reading (SPY dividend reinvestment + DTB3 cash) has passive CAGR 10.76%, C0 9.72%, C1 9.94%, C2 9.40%, and C3 9.61%; its **separate** input and economics must not replace primary evidence. The remaining original vendor economic hash mismatch `BLOCKED_HASH_MISMATCH` is not silently resolved.

Original `validation.json`: 160 independent checks, `CONSISTENT`, zero mismatches, max absolute difference zero. Frozen decision: `NO_CANDIDATE_NOMINATED_CONTROL_RETAINED`; interpretation `REPLICATED_CONTROL_RETAINED`. No strategy nomination, no production weight change. Passive ETF remains default unless the owner explicitly documents a separate risk budget.

## Review and lifecycle

- Confirm all decoded hashes and check the archived result against actual execution lock and authorization.
- Inspect original `report.md`, `manifest.json`, `validation.json`, `result.json` for consistent financial interpretation, provenance, errors and scope.
- Verify result read after the lock; note `evaluations=2`, `lockClaims=1`, `markerWrites=1`, `usValueReads=2`.
- Independent reviewer should inspect and comment on this exact PR HEAD. **Do not merge automatically or run the experiment again.**
- Existing sealed KR studies, C1 source freeze, workflow, current research policies and production are unchanged.
